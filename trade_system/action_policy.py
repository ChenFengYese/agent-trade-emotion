"""Frozen, research-only candidate-action policy over G1 feature bundles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple

from .types import parse_utc


FROZEN_ACTION_POLICY = "FROZEN_RESEARCH_ACTION_POLICY"
ACTION_POLICY_V2 = "research-action-policy-v2"
COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY = "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY"


class ActionPolicyError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActionPolicyError("%s must be a non-empty string" % field)
    return value


def _number(value: Any, field: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ActionPolicyError("%s must be numeric" % field) from exc
    if positive and result <= 0:
        raise ActionPolicyError("%s must be positive" % field)
    return result


@dataclass(frozen=True)
class ActionRule:
    rule_id: str
    side: str
    feature: str
    operator: str
    threshold: Decimal
    take_profit_bps: Decimal
    stop_loss_bps: Decimal
    horizon_seconds: Decimal
    stage: str = "ENTER_PROBE"
    eligible_episode_states: Tuple[str, ...] = ()
    entry_policy: str = ""
    structure_exit_states: Tuple[str, ...] = ()
    require_decision_eligible_for_structure_exit: bool = False

    def matches(self, values: Dict[str, Any]) -> bool:
        if self.feature not in values:
            return False
        value = _number(values[self.feature], "feature %s" % self.feature)
        return value <= self.threshold if self.operator == "LTE" else value >= self.threshold


@dataclass(frozen=True)
class ResearchActionPolicy:
    policy_id: str
    frozen_at: str
    feature_bundle_manifest_sha256: str
    min_seconds_between_actions: Decimal
    rules: Tuple[ActionRule, ...]
    digest: str
    schema_version: str = "research-action-policy-v1"
    research_scope: str = "LEGACY"
    episode_policy_id: str = ""
    episode_policy_sha256: str = ""
    feature_version: str = ""
    derived_semantics_version: str = ""
    decision_bucket_seconds: Decimal = Decimal("0")
    context_policy_id: str = ""
    context_policy_sha256: str = ""
    context_artifact_sha256: str = ""

    @property
    def is_v2(self) -> bool:
        return self.schema_version == ACTION_POLICY_V2

    @classmethod
    def load(cls, path: Path) -> "ResearchActionPolicy":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ActionPolicyError("cannot load action policy") from exc
        if not isinstance(raw, dict) or raw.get("status") != FROZEN_ACTION_POLICY:
            raise ActionPolicyError("action policy must have status %s" % FROZEN_ACTION_POLICY)
        policy_id = _non_empty(raw.get("policy_id"), "policy_id")
        frozen_at = _non_empty(raw.get("frozen_at"), "frozen_at")
        try:
            parse_utc(frozen_at)
        except ValueError as exc:
            raise ActionPolicyError("frozen_at must be UTC ISO-8601") from exc
        bundle_sha = _non_empty(raw.get("feature_bundle_manifest_sha256"), "feature_bundle_manifest_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", bundle_sha):
            raise ActionPolicyError("feature_bundle_manifest_sha256 must be lowercase SHA-256")
        cooldown = _number(raw.get("min_seconds_between_actions"), "min_seconds_between_actions", positive=True)
        schema_version = raw.get("schema_version", "research-action-policy-v1")
        is_v2 = schema_version == ACTION_POLICY_V2
        if schema_version not in {"research-action-policy-v1", ACTION_POLICY_V2}:
            raise ActionPolicyError("unsupported action policy schema_version")
        research_scope = raw.get("research_scope", "LEGACY")
        episode_policy_id = episode_policy_sha256 = feature_version = derived_semantics_version = ""
        decision_bucket_seconds = Decimal("0")
        context_policy_id = context_policy_sha256 = context_artifact_sha256 = ""
        if is_v2:
            if research_scope != "PROBE_ONLY":
                raise ActionPolicyError("v2 action policy research_scope must be PROBE_ONLY")
            binding = raw.get("episode_binding")
            if not isinstance(binding, dict):
                raise ActionPolicyError("v2 action policy requires episode_binding")
            episode_policy_id = _non_empty(binding.get("policy_id"), "episode_binding.policy_id")
            episode_policy_sha256 = _non_empty(binding.get("sha256"), "episode_binding.sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", episode_policy_sha256):
                raise ActionPolicyError("episode_binding.sha256 must be lowercase SHA-256")
            feature_version = _non_empty(binding.get("feature_version"), "episode_binding.feature_version")
            derived_semantics_version = _non_empty(binding.get("derived_semantics_version"), "episode_binding.derived_semantics_version")
            decision_bucket_seconds = _number(binding.get("decision_frequency_seconds"), "episode_binding.decision_frequency_seconds", positive=True)
            if decision_bucket_seconds != Decimal("1"):
                raise ActionPolicyError("v2 action policy requires a one-second decision bucket")
            context = raw.get("context_binding")
            if context is not None:
                if not isinstance(context, dict):
                    raise ActionPolicyError("context_binding must be an object")
                context_policy_id = _non_empty(context.get("policy_id"), "context_binding.policy_id")
                context_policy_sha256 = _non_empty(context.get("policy_sha256"), "context_binding.policy_sha256")
                context_artifact_sha256 = _non_empty(context.get("artifact_sha256"), "context_binding.artifact_sha256")
                if not re.fullmatch(r"[0-9a-f]{64}", context_policy_sha256) or not re.fullmatch(r"[0-9a-f]{64}", context_artifact_sha256):
                    raise ActionPolicyError("context_binding digests must be lowercase SHA-256")
        rules_raw = raw.get("rules")
        if not isinstance(rules_raw, list) or not rules_raw:
            raise ActionPolicyError("rules must be a non-empty list")
        rules = []
        ids = set()
        for index, value in enumerate(rules_raw):
            if not isinstance(value, dict):
                raise ActionPolicyError("rules[%d] must be an object" % index)
            rule_id = _non_empty(value.get("rule_id"), "rules[%d].rule_id" % index)
            if rule_id in ids:
                raise ActionPolicyError("rule IDs must be unique")
            ids.add(rule_id)
            side = _non_empty(value.get("side"), "rules[%d].side" % index)
            if side not in {"BUY", "SELL"}:
                raise ActionPolicyError("rules[%d].side must be BUY or SELL" % index)
            operator = _non_empty(value.get("operator"), "rules[%d].operator" % index)
            if operator not in {"LTE", "GTE"}:
                raise ActionPolicyError("rules[%d].operator must be LTE or GTE" % index)
            rules.append(ActionRule(
                rule_id=rule_id,
                side=side,
                feature=_non_empty(value.get("feature"), "rules[%d].feature" % index),
                operator=operator,
                threshold=_number(value.get("threshold"), "rules[%d].threshold" % index),
                take_profit_bps=_number(value.get("take_profit_bps"), "rules[%d].take_profit_bps" % index, positive=True),
                stop_loss_bps=_number(value.get("stop_loss_bps"), "rules[%d].stop_loss_bps" % index, positive=True),
                horizon_seconds=_number(value.get("horizon_seconds"), "rules[%d].horizon_seconds" % index, positive=True),
                stage=_non_empty(value.get("stage"), "rules[%d].stage" % index) if is_v2 else "ENTER_PROBE",
                eligible_episode_states=tuple(value.get("eligible_episode_states", ())) if is_v2 else (),
                entry_policy=_non_empty(value.get("entry_policy"), "rules[%d].entry_policy" % index) if is_v2 else "",
                structure_exit_states=tuple(value.get("structure_exit_rule", {}).get("episode_states", ())) if is_v2 and isinstance(value.get("structure_exit_rule"), dict) else (),
                require_decision_eligible_for_structure_exit=value.get("structure_exit_rule", {}).get("require_decision_eligible", False) if is_v2 and isinstance(value.get("structure_exit_rule"), dict) else False,
            ))
        if is_v2:
            if {rule.side for rule in rules} != {"BUY", "SELL"}:
                raise ActionPolicyError("v2 action policy requires independent BUY and SELL rules")
            for rule in rules:
                if rule.stage != "ENTER_PROBE":
                    raise ActionPolicyError("v2 action policy only permits ENTER_PROBE")
                if rule.eligible_episode_states != ("RESPONDING",):
                    raise ActionPolicyError("v2 action rules must be RESPONDING-only")
                if rule.entry_policy != COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY:
                    raise ActionPolicyError("v2 action rules require counterfactual label-only entry")
                if rule.structure_exit_states != ("FAILED",) or rule.require_decision_eligible_for_structure_exit is not True:
                    raise ActionPolicyError("v2 action rules require decision-eligible FAILED structure exit")
                if (rule.take_profit_bps, rule.stop_loss_bps, rule.horizon_seconds) != (Decimal("20"), Decimal("12"), Decimal("300")):
                    raise ActionPolicyError("v2 PROBE rules require the frozen 20/12/300 contract")
        return cls(
            policy_id, frozen_at, bundle_sha, cooldown, tuple(rules), hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
            schema_version, research_scope, episode_policy_id, episode_policy_sha256, feature_version,
            derived_semantics_version, decision_bucket_seconds, context_policy_id, context_policy_sha256, context_artifact_sha256,
        )
