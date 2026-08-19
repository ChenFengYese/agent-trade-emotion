"""Evidence-bound action labels derived from a verified G1 feature bundle."""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .decision import PathPoint
from .action_bundle import ActionBundleError, load_verified_action_bundle_manifest
from .feature_bundle import FeatureBundleError, load_verified_feature_bundle_manifest
from .labeling import ActionRecord, EpisodePathContext, generate_labels, load_actions, write_label_rows
from .research_report import sha256_file
from .types import parse_utc


class LabelBundleError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LabelBundleError("%s must be a non-empty string" % field)
    return value


def load_verified_label_bundle_manifest(path: Path, *, labels_path: Path) -> Dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelBundleError("cannot load label bundle manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("record_type") != "label_bundle_manifest":
        raise LabelBundleError("invalid label bundle manifest record type")
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str):
        raise LabelBundleError("label bundle manifest digest is missing")
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    if digest != _sha256(body):
        raise LabelBundleError("label bundle manifest digest does not match content")
    if manifest.get("labels_artifact_sha256") != sha256_file(Path(labels_path)):
        raise LabelBundleError("labels artifact digest does not match manifest")
    _non_empty(manifest.get("feature_bundle_manifest_sha256"), "feature_bundle_manifest_sha256")
    if "evidence_binding" not in manifest:
        _non_empty(manifest.get("g1_policy_id"), "g1_policy_id")
        _non_empty(manifest.get("g1_report_sha256"), "g1_report_sha256")
    return manifest


def _feature_points_by_evidence(
    feature_path: Path, allowed_evidence_ids: set,
) -> Tuple[Dict[str, List[PathPoint]], Dict[str, List[EpisodePathContext]], Dict[Tuple[str, str], Dict[str, Any]]]:
    points: Dict[str, List[PathPoint]] = {evidence_id: [] for evidence_id in allowed_evidence_ids}
    contexts: Dict[str, List[EpisodePathContext]] = {evidence_id: [] for evidence_id in allowed_evidence_ids}
    rows_by_event: Dict[Tuple[str, str], Dict[str, Any]] = {}
    try:
        handle = Path(feature_path).open("r", encoding="utf-8")
    except OSError as exc:
        raise LabelBundleError("cannot load feature artifact") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                evidence = row["evidence"]
                evidence_id = _non_empty(evidence.get("evidence_id"), "feature evidence_id") if isinstance(evidence, dict) else ""
                if evidence_id not in allowed_evidence_ids:
                    raise ValueError("feature evidence_id is not in bundle manifest")
                if row.get("availability_kind") != "ACTUAL":
                    raise ValueError("non-ACTUAL feature row is not eligible")
                event_id = _non_empty(row.get("event_id"), "feature event_id")
                event_key = (evidence_id, event_id)
                if event_key in rows_by_event:
                    raise ValueError("feature event_id is repeated within evidence")
                rows_by_event[event_key] = row
                points[evidence_id].append(PathPoint(
                    observed_at=parse_utc(row["available_at"]),
                    price=Decimal(str(row["values"]["mid_price"])),
                ))
                flags = row.get("quality_flags", [])
                if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
                    raise ValueError("feature quality_flags must be a list of strings")
                episode_id = row.get("episode_id")
                if episode_id is not None and (not isinstance(episode_id, str) or not episode_id):
                    raise ValueError("feature episode_id must be a non-empty string when supplied")
                episode_state = row.get("episode_state")
                if episode_state is not None and (not isinstance(episode_state, str) or not episode_state):
                    raise ValueError("feature episode_state must be a non-empty string when supplied")
                eligible = row.get("episode_decision_eligible")
                if eligible is not None and not isinstance(eligible, bool):
                    raise ValueError("feature episode_decision_eligible must be boolean when supplied")
                contexts[evidence_id].append(EpisodePathContext(
                    observed_at=parse_utc(row["available_at"]),
                    episode_id=episode_id,
                    episode_state=episode_state,
                    decision_eligible=eligible,
                    quality_flags=tuple(flags),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LabelBundleError("invalid feature row at line %d: %s" % (line_number, exc)) from exc
    return (
        {key: sorted(value, key=lambda item: item.observed_at) for key, value in points.items()},
        {key: sorted(value, key=lambda item: item.observed_at) for key, value in contexts.items()},
        rows_by_event,
    )


def _validate_v2_action_provenance(
    *,
    actions: List[ActionRecord],
    action_manifest: Dict[str, Any],
    feature_manifest: Dict[str, Any],
    rows_by_event: Dict[Tuple[str, str], Dict[str, Any]],
) -> None:
    """Require every v2 label input to point at its exact decision feature.

    A content digest protects an already-written artifact, but this check also
    makes a wrong producer or hand-assembled action artifact fail closed at the
    G1 labeling boundary.
    """
    try:
        if action_manifest.get("action_schema_version") != "research-action-v2":
            raise ValueError("v2 actions require a v2 action manifest")
        if action_manifest.get("research_scope") != "PROBE_ONLY":
            raise ValueError("v2 action manifest research_scope must be PROBE_ONLY")
        if action_manifest.get("execution_evidence") is not False:
            raise ValueError("v2 action manifest must not claim execution evidence")
        if action_manifest.get("market_path_entry_assumption") != "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY":
            raise ValueError("v2 action manifest has invalid entry assumption")
        if not isinstance(action_manifest.get("actions_written"), int) or isinstance(action_manifest.get("actions_written"), bool) or action_manifest["actions_written"] != len(actions):
            raise ValueError("v2 action manifest action count does not match artifact")
        binding = action_manifest.get("episode_binding")
        if not isinstance(binding, dict):
            raise ValueError("v2 action manifest requires episode_binding")
        policy_id = _non_empty(binding.get("policy_id"), "episode_binding.policy_id")
        policy_sha = _non_empty(binding.get("sha256"), "episode_binding.sha256")
        feature_version = _non_empty(binding.get("feature_version"), "episode_binding.feature_version")
        _non_empty(binding.get("derived_semantics_version"), "episode_binding.derived_semantics_version")
        if feature_manifest.get("episode_policy_id") != policy_id or feature_manifest.get("episode_policy_sha256") != policy_sha:
            raise ValueError("v2 action manifest does not match feature bundle episode policy")
        for action in actions:
            if action.action_schema_version != "research-action-v2":
                raise ValueError("v2 action manifest cannot wrap a legacy action")
            if action.execution_evidence is not False or action.feature_event_id is None:
                raise ValueError("v2 action provenance fields are invalid")
            row = rows_by_event.get((str(action.evidence_id), action.feature_event_id))
            if row is None:
                raise ValueError("v2 action feature_event_id is not present in its evidence path")
            if (
                parse_utc(row["available_at"]) != action.decision_at
                or row.get("episode_id") != action.episode_id
                or row.get("episode_state") != "RESPONDING"
                or row.get("episode_decision_eligible") is not True
                or row.get("feature_version") != feature_version
                or row.get("episode_policy_id") != policy_id
                or row.get("episode_policy_sha256") != policy_sha
            ):
                raise ValueError("v2 action does not match its decision-eligible feature row")
            if feature_manifest.get("context_binding") is not None and row.get("episode_reversal_side") != action.contract.side.value:
                raise ValueError("context-bound action side does not match declared episode reversal side")
            expected_features = {key: float(value) for key, value in row["values"].items()}
            if action.features != expected_features or action.contract.entry_price != Decimal(str(row["values"]["mid_price"])):
                raise ValueError("v2 action features or entry price do not match its decision feature row")
    except (KeyError, TypeError, ValueError) as exc:
        raise LabelBundleError(str(exc)) from exc


def build_label_bundle(
    *,
    actions_path: Path,
    action_manifest_path: Path,
    feature_path: Path,
    feature_manifest_path: Path,
    output_path: Path,
    manifest_path: Path,
    labels_id: str,
) -> Dict[str, Any]:
    _non_empty(labels_id, "labels_id")
    try:
        feature_manifest = load_verified_feature_bundle_manifest(feature_manifest_path, feature_path=feature_path)
    except FeatureBundleError as exc:
        raise LabelBundleError(str(exc)) from exc
    allowed = {item["evidence_id"] for item in feature_manifest["collections"]}
    try:
        action_manifest = load_verified_action_bundle_manifest(
            action_manifest_path, actions_path=actions_path, feature_manifest_sha256=feature_manifest["manifest_sha256"],
        )
    except ActionBundleError as exc:
        raise LabelBundleError(str(exc)) from exc
    if feature_manifest.get("evidence_binding") != action_manifest.get("evidence_binding"):
        raise LabelBundleError("action and feature evidence bindings do not match")
    if feature_manifest.get("context_binding") != action_manifest.get("context_binding"):
        raise LabelBundleError("action and feature context bindings do not match")
    try:
        actions = load_actions(actions_path)
    except ValueError as exc:
        raise LabelBundleError(str(exc)) from exc
    if not actions:
        raise LabelBundleError("actions artifact has no rows")
    points, contexts, rows_by_event = _feature_points_by_evidence(feature_path, allowed)
    action_schemas = {action.action_schema_version for action in actions}
    if action_schemas == {"research-action-v2"}:
        _validate_v2_action_provenance(
            actions=actions,
            action_manifest=action_manifest,
            feature_manifest=feature_manifest,
            rows_by_event=rows_by_event,
        )
    elif "research-action-v2" in action_schemas:
        raise LabelBundleError("action artifact cannot mix v1 and v2 schemas")
    rows: List[Dict[str, Any]] = []
    action_counts: Dict[str, int] = {evidence_id: 0 for evidence_id in allowed}
    for action in actions:
        evidence_id = _non_empty(action.evidence_id, "action evidence_id")
        if evidence_id not in allowed:
            raise LabelBundleError("action references evidence_id not present in feature bundle")
        action_counts[evidence_id] += 1
        labels = generate_labels((action,), points[evidence_id], episode_contexts=contexts[evidence_id])
        if len(labels) != 1:
            raise LabelBundleError("action did not generate exactly one label")
        rows.append(labels[0])
    output, manifest_output = Path(output_path), Path(manifest_path)
    if output.resolve() == manifest_output.resolve():
        raise LabelBundleError("label artifact and manifest must be different paths")
    if output.exists() or manifest_output.exists():
        raise LabelBundleError("label artifact and manifest paths must both be new")
    label_count = write_label_rows(output, rows)
    manifest = {
        "record_type": "label_bundle_manifest",
        "labels_id": labels_id,
        "labels_artifact": str(output),
        "labels_artifact_sha256": sha256_file(output),
        "labels_written": label_count,
        "actions_artifact": str(actions_path),
        "actions_artifact_sha256": sha256_file(actions_path),
        "action_bundle_manifest_sha256": action_manifest["manifest_sha256"],
        "action_policy_id": action_manifest["action_policy_id"],
        "action_policy_sha256": action_manifest["action_policy_sha256"],
        "feature_bundle_manifest_sha256": feature_manifest["manifest_sha256"],
        "feature_artifact_sha256": feature_manifest["feature_artifact_sha256"],
        "action_counts_by_evidence": action_counts,
    }
    if "evidence_binding" in feature_manifest:
        manifest["evidence_binding"] = feature_manifest["evidence_binding"]
    else:
        manifest["g1_policy_id"] = feature_manifest["g1_policy_id"]
        manifest["g1_report_sha256"] = feature_manifest["g1_report_sha256"]
    if "context_binding" in feature_manifest:
        manifest["context_binding"] = feature_manifest["context_binding"]
    manifest["manifest_sha256"] = _sha256(manifest)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with manifest_output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LabelBundleError("cannot write label bundle manifest") from exc
    return dict(manifest, manifest_path=str(manifest_output))
