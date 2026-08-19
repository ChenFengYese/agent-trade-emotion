"""Research-only candidate actions derived from a frozen policy and G1 features."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .action_policy import ActionPolicyError, ResearchActionPolicy
from .feature_bundle import FeatureBundleError, load_verified_feature_bundle_manifest
from .research_report import sha256_file
from .types import parse_utc


class ActionBundleError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActionBundleError("%s must be a non-empty string" % field)
    return value


def load_verified_action_bundle_manifest(path: Path, *, actions_path: Path, feature_manifest_sha256: str) -> Dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionBundleError("cannot load action bundle manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("record_type") != "research_action_bundle_manifest":
        raise ActionBundleError("invalid action bundle manifest record type")
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str):
        raise ActionBundleError("action bundle manifest digest is missing")
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    if digest != _sha256(body):
        raise ActionBundleError("action bundle manifest digest does not match content")
    if manifest.get("actions_artifact_sha256") != sha256_file(Path(actions_path)):
        raise ActionBundleError("actions artifact digest does not match manifest")
    if manifest.get("feature_bundle_manifest_sha256") != feature_manifest_sha256:
        raise ActionBundleError("action bundle feature manifest does not match supplied feature manifest")
    if "evidence_binding" not in manifest:
        _non_empty(manifest.get("g1_policy_id"), "g1_policy_id")
        _non_empty(manifest.get("g1_report_sha256"), "g1_report_sha256")
    return manifest


def _candidate_action(policy: ResearchActionPolicy, rule, row: Dict[str, Any], *, evidence_id: str, episode_id: str, context_binding: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        decision_at = parse_utc(row["available_at"])
        feature_event_id = _non_empty(row["event_id"], "feature event_id")
        entry = Decimal(str(row["values"]["mid_price"]))
        features = {key: float(value) for key, value in row["values"].items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise ActionBundleError("invalid feature row for action generation") from exc
    scale = Decimal("10000")
    target = entry * (Decimal("1") + rule.take_profit_bps / scale) if rule.side == "BUY" else entry * (Decimal("1") - rule.take_profit_bps / scale)
    stop = entry * (Decimal("1") - rule.stop_loss_bps / scale) if rule.side == "BUY" else entry * (Decimal("1") + rule.stop_loss_bps / scale)
    action_id = _sha256({
        "policy_id": policy.policy_id, "policy_sha256": policy.digest, "rule_id": rule.rule_id,
        "evidence_id": evidence_id, "episode_id": episode_id, "decision_at": decision_at.isoformat(),
    })
    common = {
        "decision_id": action_id,
        "episode_id": episode_id,
        "decision_at": decision_at.isoformat(),
        "side": rule.side,
        "stage": rule.stage,
        "entry_price": str(entry),
        "take_profit": str(target),
        "stop_loss": str(stop),
        "horizon_seconds": str(rule.horizon_seconds),
        "features": features,
        "evidence_id": evidence_id,
        "action_policy_id": policy.policy_id,
        "action_policy_sha256": policy.digest,
        "action_rule_id": rule.rule_id,
    }
    if policy.is_v2:
        payload = dict(common, **{
            "action_schema_version": "research-action-v2",
            "feature_event_id": feature_event_id,
            "market_path_entry_at": decision_at.isoformat(),
            "market_path_entry_assumption": rule.entry_policy,
            "execution_evidence": False,
            "structure_exit_rule": {
                "episode_states": list(rule.structure_exit_states),
                "require_decision_eligible": rule.require_decision_eligible_for_structure_exit,
                "unknown_or_data_failure": "OPERATIONAL_CENSOR",
            },
        })
        if context_binding is not None:
            payload["context_binding"] = context_binding
        return payload
    return dict(common, **{
        "filled_at": decision_at.isoformat(),
        "execution_outcome": "FILLED",
        "fill_fraction": "1",
        "execution_assumption": "COUNTERFACTUAL_FILLED_FOR_MARKET_LABEL_ONLY",
    })


def _decision_bucket(decision_at, seconds: Decimal) -> int:
    return int(decision_at.timestamp() // float(seconds))


def _context_allows_enter_probe(row: Dict[str, Any], binding: Dict[str, Any]) -> bool:
    """The context gate is deliberately a skip, never a permissive default."""
    context = row.get("context")
    if not isinstance(context, dict):
        return False
    if context.get("context_policy_id") != binding.get("policy_id") or context.get("context_policy_sha256") != binding.get("policy_sha256"):
        return False
    if context.get("context_status") != "READY" or context.get("decision_permission") != "ELIGIBLE":
        return False
    reasons = context.get("reason_codes")
    values = context.get("values")
    if not isinstance(reasons, list) or not isinstance(values, dict):
        return False
    if "TREND_CONTINUATION_OR_CONTEXT_UNAVAILABLE" in reasons:
        return False
    if values.get("Z_episode_anchor_distance_bps") is None:
        return False
    if values.get("R_directional") is None or values.get("R_directional_improvement") is None or values.get("price_impact_1s") is None:
        return False
    if context.get("directional_resilience_feature") not in {"R_sell_bid_resilience_1s", "R_buy_ask_resilience_1s"}:
        return False
    flags = row.get("quality_flags", [])
    return isinstance(flags, list) and not {"book_invalid", "gap", "sequence_gap", "late_critical"}.intersection(flags)


def build_action_bundle(
    *,
    feature_path: Path,
    feature_manifest_path: Path,
    policy_path: Path,
    output_path: Path,
    manifest_path: Path,
    actions_id: str,
) -> Dict[str, Any]:
    _non_empty(actions_id, "actions_id")
    try:
        feature_manifest = load_verified_feature_bundle_manifest(feature_manifest_path, feature_path=feature_path)
    except FeatureBundleError as exc:
        raise ActionBundleError(str(exc)) from exc
    try:
        policy = ResearchActionPolicy.load(policy_path)
    except ActionPolicyError as exc:
        raise ActionBundleError(str(exc)) from exc
    if policy.feature_bundle_manifest_sha256 != feature_manifest["manifest_sha256"]:
        raise ActionBundleError("action policy does not match feature bundle manifest")
    if policy.is_v2 and (
        feature_manifest.get("episode_policy_id") != policy.episode_policy_id
        or feature_manifest.get("episode_policy_sha256") != policy.episode_policy_sha256
    ):
        raise ActionBundleError("v2 action policy does not match feature bundle episode policy")
    context_binding = feature_manifest.get("context_binding")
    if context_binding is not None:
        if not policy.is_v2 or not (policy.context_policy_id and policy.context_policy_sha256 and policy.context_artifact_sha256):
            raise ActionBundleError("context-bound feature bundle requires a context-bound v2 action policy")
        if (
            policy.context_policy_id != context_binding.get("policy_id")
            or policy.context_policy_sha256 != context_binding.get("policy_sha256")
            or policy.context_artifact_sha256 != context_binding.get("artifact_sha256")
        ):
            raise ActionBundleError("action policy context binding does not match feature bundle")
    allowed_evidence = {item["evidence_id"] for item in feature_manifest["collections"]}
    output, manifest_output = Path(output_path), Path(manifest_path)
    if output.resolve() == manifest_output.resolve():
        raise ActionBundleError("action artifact and manifest must be different paths")
    if output.exists() or manifest_output.exists():
        raise ActionBundleError("action artifact and manifest paths must both be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    emitted: List[Dict[str, Any]] = []
    last_by_rule_evidence: Dict[Tuple[str, str], Any] = {}
    seen_episode_rule = set()
    seen_episode_stage = set()
    seen_bucket_stage = set()
    try:
        with Path(feature_path).open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if row.get("availability_kind") != "ACTUAL" or not isinstance(row.get("values"), dict):
                        continue
                    evidence = row.get("evidence")
                    evidence_id = _non_empty(evidence.get("evidence_id"), "feature evidence_id") if isinstance(evidence, dict) else ""
                    if evidence_id not in allowed_evidence:
                        raise ValueError("feature evidence_id is not present in manifest")
                    episode_id = row.get("episode_id")
                    if not isinstance(episode_id, str) or not episode_id:
                        continue
                    decision_at = parse_utc(row["available_at"])
                    if policy.is_v2:
                        if row.get("feature_version") != policy.feature_version:
                            raise ValueError("v2 feature row version does not match action policy")
                        if row.get("episode_policy_id") != policy.episode_policy_id or row.get("episode_policy_sha256") != policy.episode_policy_sha256:
                            raise ValueError("v2 feature row episode policy does not match action policy")
                        if context_binding is not None and not _context_allows_enter_probe(row, context_binding):
                            continue
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ActionBundleError("invalid feature row at line %d: %s" % (line_number, exc)) from exc
                for rule in policy.rules:
                    if policy.is_v2:
                        if row.get("episode_decision_eligible") is not True or row.get("episode_state") not in rule.eligible_episode_states:
                            continue
                        if context_binding is not None and row.get("episode_reversal_side") != rule.side:
                            continue
                    if not rule.matches(row["values"]):
                        continue
                    episode_key = (evidence_id, episode_id, rule.rule_id)
                    stage_key = (evidence_id, episode_id, rule.stage)
                    bucket_key = (evidence_id, episode_id, rule.stage, _decision_bucket(decision_at, policy.decision_bucket_seconds)) if policy.is_v2 else None
                    cooldown_key = (evidence_id, rule.side, rule.stage) if policy.is_v2 else (evidence_id, rule.rule_id)
                    previous = last_by_rule_evidence.get(cooldown_key)
                    if (
                        episode_key in seen_episode_rule
                        or (policy.is_v2 and (stage_key in seen_episode_stage or bucket_key in seen_bucket_stage))
                        or (previous is not None and decision_at - previous < timedelta(seconds=float(policy.min_seconds_between_actions)))
                    ):
                        continue
                    emitted.append(_candidate_action(policy, rule, row, evidence_id=evidence_id, episode_id=episode_id, context_binding=context_binding))
                    seen_episode_rule.add(episode_key)
                    if policy.is_v2:
                        seen_episode_stage.add(stage_key)
                        seen_bucket_stage.add(bucket_key)
                    last_by_rule_evidence[cooldown_key] = decision_at
    except OSError as exc:
        raise ActionBundleError("cannot load feature artifact") from exc
    try:
        with output.open("x", encoding="utf-8") as handle:
            for action in emitted:
                handle.write(json.dumps(action, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ActionBundleError("cannot write action artifact") from exc
    manifest = {
        "record_type": "research_action_bundle_manifest",
        "actions_id": actions_id,
        "actions_artifact": str(output),
        "actions_artifact_sha256": sha256_file(output),
        "actions_written": len(emitted),
        "feature_bundle_manifest_sha256": feature_manifest["manifest_sha256"],
        "feature_artifact_sha256": feature_manifest["feature_artifact_sha256"],
        "action_policy_id": policy.policy_id,
        "action_policy_sha256": policy.digest,
        "rules": [rule.rule_id for rule in policy.rules],
        "execution_assumption": "COUNTERFACTUAL_FILLED_FOR_MARKET_LABEL_ONLY",
    }
    if policy.is_v2:
        manifest.update({
            "action_schema_version": "research-action-v2",
            "research_scope": policy.research_scope,
            "episode_binding": {
                "policy_id": policy.episode_policy_id,
                "sha256": policy.episode_policy_sha256,
                "feature_version": policy.feature_version,
                "derived_semantics_version": policy.derived_semantics_version,
                "decision_frequency_seconds": str(policy.decision_bucket_seconds),
            },
            "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY",
            "execution_assumption": "NO_EXECUTION_CLAIM",
            "execution_evidence": False,
        })
    if "evidence_binding" in feature_manifest:
        manifest["evidence_binding"] = feature_manifest["evidence_binding"]
    else:
        manifest["g1_policy_id"] = feature_manifest["g1_policy_id"]
        manifest["g1_report_sha256"] = feature_manifest["g1_report_sha256"]
    if context_binding is not None:
        manifest["context_binding"] = context_binding
    manifest["manifest_sha256"] = _sha256(manifest)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with manifest_output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ActionBundleError("cannot write action bundle manifest") from exc
    return dict(manifest, manifest_path=str(manifest_output))
