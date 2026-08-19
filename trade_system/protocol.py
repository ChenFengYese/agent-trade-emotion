"""Versioned research-protocol loading and data eligibility checks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .types import AvailabilityKind


class ProtocolError(ValueError):
    pass


FROZEN_STATUS = "FROZEN_RESEARCH_PROTOCOL"
V2_SCHEMA_VERSION = "research-protocol.v2"
V2_DRAFT_STATUS = "DRAFT_RESEARCH_PROTOCOL_V2"
PENDING_PROTOCOL_STATUS = "PREREGISTERED_PENDING_G1"
PENDING_G1_DIGEST = "PENDING_VERIFIED_PASS_REPORT"
FROZEN_SUPERSESSION_GUARD_STATUS = "FROZEN_PROTOCOL_SUPERSESSION_GUARD"

# v1 is historical evidence, not an eligible finalization candidate.  This
# exact pending artifact was replaced before G1, outcome inspection or the
# final holdout.  The finalizer additionally verifies that a supplied frozen
# guard carries this same fact, so passing an arbitrary empty guard cannot
# reactivate v1.
LEGACY_V1_PROTOCOL_ID = "btc-usdt-absorption-research-v1"
LEGACY_V1_PENDING_SHA256 = "4645fc18567e72c843e3e45d19cf0d5d0f72add025e17490d04f3ee282476d68"
V2_PROTOCOL_ID = "btc-usdt-absorption-research-v2"
SUPERSESSION_GUARD_V2_SCHEMA = "protocol-supersession-guard.v2"
TRUSTED_SUPERSESSION_GUARD_ID = "research-protocol-supersession.v2"
TRUSTED_SUPERSESSION_GUARD_SHA256 = "b748791371e436f35be9f217f89428722c242e39752fbcea25d252955c74bf75"
COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY = "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY"


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_explicit_unresolved(value: Any) -> bool:
    return isinstance(value, str) and (value.startswith("REQUIRED:") or value.startswith("PENDING_"))


def _require_mapping(raw: Dict[str, Any], key: str, fields) -> Dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ProtocolError("%s must be an object" % key)
    missing = [field for field in fields if field not in value]
    if missing:
        raise ProtocolError("%s missing fields: %s" % (key, ", ".join(missing)))
    return value


def _require_positive(value: Any, name: str, *, allow_zero: bool = False) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("%s must be numeric" % name) from exc
    if numeric < 0 or (numeric == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ProtocolError("%s must be %s" % (name, qualifier))


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProtocolError("%s must be a non-empty ISO-8601 timestamp" % name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError("%s must be ISO-8601" % name) from exc
    if parsed.tzinfo is None:
        raise ProtocolError("%s must include timezone" % name)
    return parsed


@dataclass(frozen=True)
class ProtocolSupersessionGuard:
    """Frozen lineage guard used by finalization, never a mutable registry."""

    guard_id: str
    raw: Dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "ProtocolSupersessionGuard":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolError("cannot load protocol supersession guard") from exc
        if not isinstance(raw, dict):
            raise ProtocolError("protocol supersession guard must be an object")
        if raw.get("schema_version") != SUPERSESSION_GUARD_V2_SCHEMA:
            raise ProtocolError("protocol supersession guard must use the v2 unambiguous schema")
        if raw.get("status") != FROZEN_SUPERSESSION_GUARD_STATUS:
            raise ProtocolError("protocol supersession guard is not frozen")
        guard_id = raw.get("guard_id")
        if not isinstance(guard_id, str) or not guard_id:
            raise ProtocolError("protocol supersession guard requires guard_id")
        _parse_timestamp(raw.get("frozen_at"), "protocol supersession guard frozen_at")
        predecessor = _require_mapping(raw, "supersedes_guard", ("guard_id", "sha256"))
        if predecessor["guard_id"] != "research-protocol-supersession.v1" or predecessor["sha256"] != "81090942bba517a60f695f00604099f4b815d831bf39a57f943c58a064ce2160":
            raise ProtocolError("v2 supersession guard must declare the retained v1 historical guard")
        entries = raw.get("superseded_protocols")
        if not isinstance(entries, list) or not entries:
            raise ProtocolError("protocol supersession guard requires superseded_protocols")
        observed = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ProtocolError("superseded_protocols[%d] must be an object" % index)
            protocol_id = entry.get("protocol_id")
            pending_sha = entry.get("preregistered_protocol_sha256")
            allowed = entry.get("allowed_successor_id")
            if not isinstance(protocol_id, str) or not protocol_id or not _is_sha256(pending_sha):
                raise ProtocolError("superseded_protocols[%d] has invalid protocol identity" % index)
            if not isinstance(allowed, str) or not allowed:
                raise ProtocolError("superseded_protocols[%d] requires allowed_successor_id" % index)
            key = (protocol_id, pending_sha)
            if key in observed:
                raise ProtocolError("protocol supersession guard repeats a protocol identity")
            observed.add(key)
            if entry.get("superseded_before_g1_pass") is not True or entry.get("outcomes_inspected") is not False or entry.get("holdout_opened") is not False:
                raise ProtocolError("supersession guard requires explicit pre-G1, no-outcome, unopened-holdout facts")
        return cls(guard_id=guard_id, raw=raw)

    @property
    def digest(self) -> str:
        return canonical_sha256(self.raw)

    def entry_for(self, protocol_id: str, pending_sha256: str) -> Dict[str, Any] | None:
        for entry in self.raw["superseded_protocols"]:
            if entry["protocol_id"] == protocol_id and entry["preregistered_protocol_sha256"] == pending_sha256:
                return entry
        return None

    def assert_legacy_v1_is_protected(self) -> None:
        entry = self.entry_for(LEGACY_V1_PROTOCOL_ID, LEGACY_V1_PENDING_SHA256)
        if entry is None:
            raise ProtocolError("protocol supersession guard does not protect the retired v1 protocol")

    def assert_v2_lineage(self, raw: Dict[str, Any]) -> None:
        lineage = _require_mapping(raw, "protocol_lineage", ("supersedes", "finalization_guard"))
        parent = _require_mapping(lineage, "supersedes", ("protocol_id", "preregistered_protocol_sha256"))
        guard_binding = _require_mapping(lineage, "finalization_guard", ("guard_id", "sha256"))
        if guard_binding["guard_id"] != self.guard_id or guard_binding["sha256"] != self.digest:
            raise ProtocolError("v2 protocol lineage does not match the supplied frozen supersession guard")
        entry = self.entry_for(parent["protocol_id"], parent["preregistered_protocol_sha256"])
        if entry is None:
            raise ProtocolError("v2 protocol lineage parent is not retired by the supplied guard")
        if entry["allowed_successor_id"] != raw.get("protocol_id"):
            raise ProtocolError("v2 protocol ID is not the allowed successor in the frozen guard")

    def assert_trusted_v2_lineage(self, raw: Dict[str, Any]) -> None:
        """Require the one pinned supersession authority, not self-declared lineage."""
        if self.guard_id != TRUSTED_SUPERSESSION_GUARD_ID or self.digest != TRUSTED_SUPERSESSION_GUARD_SHA256:
            raise ProtocolError("protocol supersession guard is not the pinned v2 authority")
        self.assert_legacy_v1_is_protected()
        self.assert_v2_lineage(raw)

    @staticmethod
    def assert_pinned_v2_lineage(raw: Dict[str, Any]) -> None:
        """Validate frozen lineage from code-pinned identity, without a config file.

        Runtime research packages do not ship mutable repository configuration.
        The finalizer still reads and verifies the complete v2 guard artifact,
        while already-frozen protocols use these immutable pins.
        """
        lineage = _require_mapping(raw, "protocol_lineage", ("supersedes", "finalization_guard"))
        parent = _require_mapping(lineage, "supersedes", ("protocol_id", "preregistered_protocol_sha256"))
        guard_binding = _require_mapping(lineage, "finalization_guard", ("guard_id", "sha256"))
        if (
            raw.get("protocol_id") != V2_PROTOCOL_ID
            or parent.get("protocol_id") != LEGACY_V1_PROTOCOL_ID
            or parent.get("preregistered_protocol_sha256") != LEGACY_V1_PENDING_SHA256
            or guard_binding.get("guard_id") != TRUSTED_SUPERSESSION_GUARD_ID
            or guard_binding.get("sha256") != TRUSTED_SUPERSESSION_GUARD_SHA256
        ):
            raise ProtocolError("frozen v2 protocol lineage does not match the code-pinned supersession authority")


@dataclass(frozen=True)
class ResearchProtocol:
    protocol_id: str
    status: str
    raw: Dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "ResearchProtocol":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolError("cannot load protocol") from exc
        required = ("protocol_id", "status", "availability_policy", "action_contract", "execution_priors")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ProtocolError("missing protocol keys: %s" % ", ".join(missing))
        policy = raw["availability_policy"]
        if not isinstance(policy, dict) or "allow_actual" not in policy or "allow_reconstructed_for_g2" not in policy:
            raise ProtocolError("availability_policy is incomplete")
        labels = raw["action_contract"].get("labels", [])
        if set(labels) != {"TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"}:
            raise ProtocolError("action contract must define exactly four market-path labels")
        if raw["status"] != "SYNTHETIC_DEVELOPMENT_PROFILE" and "notice" not in raw:
            raise ProtocolError("non-synthetic protocol requires a frozen research notice")
        if raw.get("schema_version") == V2_SCHEMA_VERSION:
            cls._validate_v2(raw)
        elif raw["status"] == FROZEN_STATUS:
            cls._validate_frozen(raw)
        return cls(protocol_id=str(raw["protocol_id"]), status=str(raw["status"]), raw=raw)

    @staticmethod
    def _validate_frozen(raw: Dict[str, Any]) -> None:
        _parse_timestamp(raw.get("frozen_at"), "frozen_at")
        registry = _require_mapping(raw, "source_registry", ("registry_id", "sha256"))
        if not registry["registry_id"] or not isinstance(registry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", registry["sha256"]):
            raise ProtocolError("source_registry requires registry_id and lowercase SHA-256")
        gate_profile = _require_mapping(raw, "risk_gate_profile", ("profile_id", "digest"))
        if not gate_profile["profile_id"] or not isinstance(gate_profile["digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", gate_profile["digest"]):
            raise ProtocolError("risk_gate_profile requires profile_id and lowercase SHA-256 digest")
        eligibility = _require_mapping(raw, "data_eligibility", ("required_g1_policy_id", "required_g1_report_sha256", "require_g1_pass"))
        if not eligibility["required_g1_policy_id"] or eligibility["require_g1_pass"] is not True or not isinstance(eligibility["required_g1_report_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", eligibility["required_g1_report_sha256"]):
            raise ProtocolError("frozen protocol requires a passed G1 policy binding")
        policy_sha = eligibility.get("required_g1_policy_sha256")
        if policy_sha is not None and (not isinstance(policy_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", policy_sha)):
            raise ProtocolError("required_g1_policy_sha256 must be lowercase SHA-256")
        sources = raw.get("data_sources")
        if not isinstance(sources, list) or not sources:
            raise ProtocolError("frozen protocol requires non-empty data_sources")
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise ProtocolError("data_sources[%d] must be an object" % index)
            missing = [name for name in ("source_id", "endpoint_or_channel", "schema_version", "instrument", "allowed_availability") if not source.get(name)]
            if missing:
                raise ProtocolError("data_sources[%d] missing fields: %s" % (index, ", ".join(missing)))
            if source["allowed_availability"] not in ("ACTUAL_ONLY", "ACTUAL_AND_RECONSTRUCTED"):
                raise ProtocolError("data_sources[%d] has invalid allowed_availability" % index)

        episode = _require_mapping(raw, "episode_policy", ("trigger", "decision_frequency_seconds", "max_holding_seconds", "overlap_policy"))
        _require_positive(episode["decision_frequency_seconds"], "episode_policy.decision_frequency_seconds")
        _require_positive(episode["max_holding_seconds"], "episode_policy.max_holding_seconds")
        labels = _require_mapping(raw, "label_policy", ("barrier_rules", "same_timestamp_rule", "operational_override_rule"))
        if not all(labels[field] for field in labels):
            raise ProtocolError("label_policy values must be non-empty")
        execution = _require_mapping(raw, "execution_priors", ("latency_ms", "fee_rate", "funding_policy", "cost_scenarios"))
        _require_positive(execution["latency_ms"], "execution_priors.latency_ms", allow_zero=True)
        _require_positive(execution["fee_rate"], "execution_priors.fee_rate", allow_zero=True)
        if not isinstance(execution["cost_scenarios"], list) or not execution["cost_scenarios"]:
            raise ProtocolError("execution_priors.cost_scenarios must be non-empty")
        evaluation = _require_mapping(raw, "evaluation_policy", ("primary_metrics", "min_effective_episodes", "calibration_rule", "cost_after_utility_rule", "confidence_interval_rule", "concentration_limits"))
        if not isinstance(evaluation["primary_metrics"], list) or not evaluation["primary_metrics"]:
            raise ProtocolError("evaluation_policy.primary_metrics must be non-empty")
        _require_positive(evaluation["min_effective_episodes"], "evaluation_policy.min_effective_episodes")
        if float(evaluation["min_effective_episodes"]) != int(float(evaluation["min_effective_episodes"])):
            raise ProtocolError("evaluation_policy.min_effective_episodes must be an integer")
        state_coverage = _require_mapping(raw, "state_coverage_policy", ("classifier_id", "classifier_digest", "required_state_ids", "min_effective_episodes_per_state", "insufficient_coverage_result"))
        if not isinstance(state_coverage["classifier_id"], str) or not state_coverage["classifier_id"]:
            raise ProtocolError("state_coverage_policy.classifier_id must be non-empty")
        if not isinstance(state_coverage["classifier_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", state_coverage["classifier_digest"]):
            raise ProtocolError("state_coverage_policy.classifier_digest must be a lowercase SHA-256")
        state_ids = state_coverage["required_state_ids"]
        if not isinstance(state_ids, list) or len(state_ids) < 2 or not all(isinstance(item, str) and item for item in state_ids) or len(set(state_ids)) != len(state_ids):
            raise ProtocolError("state_coverage_policy.required_state_ids must contain at least two unique non-empty IDs")
        _require_positive(state_coverage["min_effective_episodes_per_state"], "state_coverage_policy.min_effective_episodes_per_state")
        if float(state_coverage["min_effective_episodes_per_state"]) != int(float(state_coverage["min_effective_episodes_per_state"])):
            raise ProtocolError("state_coverage_policy.min_effective_episodes_per_state must be an integer")
        if state_coverage["insufficient_coverage_result"] != "INCONCLUSIVE/WAIT_DATA":
            raise ProtocolError("state coverage must stop at INCONCLUSIVE/WAIT_DATA")
        split = _require_mapping(raw, "split_policy", ("folds", "embargo_seconds", "training_calibration_policy", "final_holdout"))
        _require_positive(split["folds"], "split_policy.folds")
        if float(split["folds"]) != int(float(split["folds"])):
            raise ProtocolError("split_policy.folds must be an integer")
        _require_positive(split["embargo_seconds"], "split_policy.embargo_seconds", allow_zero=True)
        if float(split["embargo_seconds"]) < float(episode["max_holding_seconds"]):
            raise ProtocolError("split_policy.embargo_seconds must cover max_holding_seconds")
        if not split["training_calibration_policy"]:
            raise ProtocolError("split_policy.training_calibration_policy must be declared")
        holdout = split["final_holdout"]
        if not isinstance(holdout, dict):
            raise ProtocolError("split_policy.final_holdout must be an object")
        required_holdout = ("holdout_id", "start", "end", "opened_at", "reuse_policy")
        if any(field not in holdout for field in required_holdout):
            raise ProtocolError("split_policy.final_holdout is incomplete")
        if not holdout["holdout_id"] or holdout["reuse_policy"] != "ONE_TIME_ONLY":
            raise ProtocolError("split_policy.final_holdout must be one-time and identified")
        if holdout["opened_at"] is not None:
            raise ProtocolError("a frozen research protocol must be created before final holdout is opened")
        start = _parse_timestamp(holdout["start"], "split_policy.final_holdout.start")
        end = _parse_timestamp(holdout["end"], "split_policy.final_holdout.end")
        if end <= start:
            raise ProtocolError("split_policy.final_holdout end must follow start")
        hypotheses = raw.get("hypotheses")
        if not isinstance(hypotheses, list) or not hypotheses:
            raise ProtocolError("frozen protocol requires hypotheses")
        for index, hypothesis in enumerate(hypotheses):
            if not isinstance(hypothesis, dict) or any(not hypothesis.get(field) for field in ("hypothesis_id", "pass_condition", "failure_condition")):
                raise ProtocolError("hypotheses[%d] must declare id, pass and failure conditions" % index)

    @staticmethod
    def _validate_v2(raw: Dict[str, Any]) -> None:
        """Validate the v2 lineage and gate contract without creating another route."""
        status = raw.get("status")
        if status not in (V2_DRAFT_STATUS, PENDING_PROTOCOL_STATUS, FROZEN_STATUS):
            raise ProtocolError("v2 protocol has an unsupported status")
        draft = status == V2_DRAFT_STATUS

        lineage = _require_mapping(raw, "protocol_lineage", ("supersedes", "finalization_guard"))
        parent = _require_mapping(lineage, "supersedes", ("protocol_id", "preregistered_protocol_sha256"))
        guard_binding = _require_mapping(lineage, "finalization_guard", ("guard_id", "sha256"))
        if parent["protocol_id"] != LEGACY_V1_PROTOCOL_ID or parent["preregistered_protocol_sha256"] != LEGACY_V1_PENDING_SHA256:
            raise ProtocolError("v2 protocol must supersede the exact retired v1 preregistration")
        if not isinstance(guard_binding["guard_id"], str) or not guard_binding["guard_id"]:
            raise ProtocolError("v2 protocol lineage requires guard_id")
        ResearchProtocol._validate_sha_or_required(guard_binding["sha256"], "protocol_lineage.finalization_guard.sha256", draft=draft)

        hypotheses = raw.get("theory_hypotheses")
        if not isinstance(hypotheses, list) or len(hypotheses) != 4:
            raise ProtocolError("v2 protocol requires exactly four theory_hypotheses")
        expected_hypotheses = {"H-001", "H-002", "H-003", "H-004"}
        observed_hypotheses = set()
        for index, hypothesis in enumerate(hypotheses):
            if not isinstance(hypothesis, dict):
                raise ProtocolError("theory_hypotheses[%d] must be an object" % index)
            required = ("hypothesis_id", "statement", "mechanism", "population", "falsifiability_note")
            if any(not isinstance(hypothesis.get(name), str) or not hypothesis[name] for name in required):
                raise ProtocolError("theory_hypotheses[%d] is incomplete" % index)
            observed_hypotheses.add(hypothesis["hypothesis_id"])
        if observed_hypotheses != expected_hypotheses:
            raise ProtocolError("v2 theory_hypotheses must be H-001 through H-004 exactly once")

        criteria = raw.get("gate_criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ProtocolError("v2 protocol requires gate_criteria")
        gate_ids = set()
        referenced = set()
        theory_development_gates = {hypothesis_id: 0 for hypothesis_id in expected_hypotheses}
        for index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                raise ProtocolError("gate_criteria[%d] must be an object" % index)
            required = ("gate_id", "stage", "gate_kind", "hypothesis_ids", "required_inputs", "metric_definition", "pass_rule", "fail_rule", "insufficient_data_result")
            if any(name not in criterion for name in required):
                raise ProtocolError("gate_criteria[%d] is incomplete" % index)
            gate_id = criterion["gate_id"]
            if not isinstance(gate_id, str) or not gate_id or gate_id in gate_ids:
                raise ProtocolError("gate_criteria gate_id values must be unique")
            gate_ids.add(gate_id)
            stage = criterion["stage"]
            if stage not in ("DEVELOPMENT", "HOLDOUT"):
                raise ProtocolError("gate_criteria stage must be DEVELOPMENT or HOLDOUT")
            gate_kind = criterion["gate_kind"]
            if gate_kind not in {"THEORY_ABLATION_CONTROL", "ECONOMIC", "STABILITY", "FINAL_HOLDOUT"}:
                raise ProtocolError("gate_criteria gate_kind is unsupported")
            hypothesis_ids = criterion["hypothesis_ids"]
            if not isinstance(hypothesis_ids, list) or not hypothesis_ids or not all(item in expected_hypotheses for item in hypothesis_ids):
                raise ProtocolError("gate_criteria must reference declared theory hypotheses")
            if len(set(hypothesis_ids)) != len(hypothesis_ids):
                raise ProtocolError("gate_criteria must not repeat a hypothesis ID")
            if gate_kind == "THEORY_ABLATION_CONTROL":
                if stage != "DEVELOPMENT" or len(hypothesis_ids) != 1:
                    raise ProtocolError("each theory ablation/control gate must be a single-hypothesis DEVELOPMENT gate")
                theory_development_gates[hypothesis_ids[0]] += 1
            elif gate_kind in {"ECONOMIC", "STABILITY"}:
                if stage != "DEVELOPMENT" or set(hypothesis_ids) != expected_hypotheses:
                    raise ProtocolError("economic and stability gates must be DEVELOPMENT gates referencing all theory hypotheses")
            elif stage != "HOLDOUT" or set(hypothesis_ids) != expected_hypotheses:
                raise ProtocolError("the final holdout gate must reference all theory hypotheses")
            if any(not isinstance(criterion[name], str) or not criterion[name] for name in ("required_inputs", "metric_definition", "pass_rule", "fail_rule")):
                raise ProtocolError("gate_criteria rules must be non-empty strings")
            if criterion["insufficient_data_result"] != "INCONCLUSIVE/WAIT_DATA":
                raise ProtocolError("gate_criteria insufficient data must fail closed to INCONCLUSIVE/WAIT_DATA")
            referenced.update(hypothesis_ids)
        if referenced != expected_hypotheses or any(count < 1 for count in theory_development_gates.values()):
            raise ProtocolError("every v2 theory hypothesis requires its own DEVELOPMENT ablation/control gate")

        eligibility = _require_mapping(raw, "data_eligibility", ("g1_qualification", "admitted_collection_roles"))
        g1 = _require_mapping(eligibility, "g1_qualification", ("role", "required_g1_policy_id", "required_g1_policy_sha256", "required_g1_report_sha256", "require_g1_pass"))
        if g1["role"] != "QUALIFICATION_ONLY" or g1["require_g1_pass"] is not True:
            raise ProtocolError("v2 G1 is qualification-only and requires PASS")
        if not isinstance(g1["required_g1_policy_id"], str) or not g1["required_g1_policy_id"]:
            raise ProtocolError("v2 G1 qualification requires policy ID")
        ResearchProtocol._validate_sha_or_required(g1["required_g1_policy_sha256"], "data_eligibility.g1_qualification.required_g1_policy_sha256", draft=draft)
        report_digest = g1["required_g1_report_sha256"]
        if status == FROZEN_STATUS:
            if not _is_sha256(report_digest):
                raise ProtocolError("frozen v2 protocol requires a verified G1 report digest")
        elif report_digest != PENDING_G1_DIGEST:
            raise ProtocolError("unfrozen v2 protocol requires the untouched pending G1 report digest")

        roles = eligibility["admitted_collection_roles"]
        if not isinstance(roles, list) or len(roles) != 2:
            raise ProtocolError("v2 protocol requires DEVELOPMENT and HOLDOUT collection roles")
        observed_roles = set()
        for index, role in enumerate(roles):
            if not isinstance(role, dict):
                raise ProtocolError("admitted_collection_roles[%d] must be an object" % index)
            required = ("role", "capture_plan", "acceptance_policy", "acceptance_report", "quality_equivalence", "allowed_availability", "time_window")
            if any(name not in role for name in required):
                raise ProtocolError("admitted_collection_roles[%d] is incomplete" % index)
            role_name = role["role"]
            if role_name not in ("DEVELOPMENT", "HOLDOUT") or role_name in observed_roles:
                raise ProtocolError("collection roles must be unique DEVELOPMENT and HOLDOUT")
            observed_roles.add(role_name)
            if role["allowed_availability"] != "ACTUAL_ONLY":
                raise ProtocolError("v2 research collection roles require ACTUAL_ONLY")
            for field in ("capture_plan", "acceptance_policy"):
                binding = _require_mapping(role, field, ("id", "sha256"))
                if not isinstance(binding["id"], str) or not binding["id"]:
                    raise ProtocolError("%s binding requires ID" % field)
                ResearchProtocol._validate_sha_or_required(binding["sha256"], "collection role %s sha256" % field, draft=draft)
            report_contract = _require_mapping(role, "acceptance_report", ("schema_version", "require_pass"))
            if report_contract["schema_version"] != "data_acceptance_report.v1" or report_contract["require_pass"] is not True:
                raise ProtocolError("collection role requires a PASS data_acceptance_report.v1")
            equivalence = _require_mapping(role, "quality_equivalence", ("baseline_g1_policy_id", "baseline_g1_policy_sha256", "comparison_rule"))
            if equivalence["baseline_g1_policy_id"] != g1["required_g1_policy_id"]:
                raise ProtocolError("collection quality equivalence must reference the frozen G1 policy ID")
            ResearchProtocol._validate_sha_or_required(equivalence["baseline_g1_policy_sha256"], "collection role quality equivalence sha256", draft=draft)
            if equivalence["comparison_rule"] != "EQUAL_OR_STRICTER_THAN_G1":
                raise ProtocolError("collection quality equivalence must be EQUAL_OR_STRICTER_THAN_G1")
            window = _require_mapping(role, "time_window", ("decision_start", "decision_end", "label_horizon_seconds"))
            if draft and any(_is_explicit_unresolved(window[field]) for field in ("decision_start", "decision_end", "label_horizon_seconds")):
                continue
            start = _parse_timestamp(window["decision_start"], "collection role decision_start")
            end = _parse_timestamp(window["decision_end"], "collection role decision_end")
            if end <= start:
                raise ProtocolError("collection role decision window end must follow start")
            _require_positive(window["label_horizon_seconds"], "collection role label_horizon_seconds", allow_zero=True)
        if observed_roles != {"DEVELOPMENT", "HOLDOUT"}:
            raise ProtocolError("v2 protocol requires one DEVELOPMENT and one HOLDOUT role")

        # G2 is executable only from this machine-readable declaration.  The
        # prose gates below remain explanatory, never the source of runtime
        # thresholds or a second, ambiguous 4/5 rule.
        g2 = raw.get("g2_evaluator")
        if not isinstance(g2, dict):
            raise ProtocolError("v2 protocol requires machine-readable g2_evaluator")
        required_g2 = ("folds", "embargo_seconds", "calibration_fraction", "min_effective_episodes", "min_effective_episodes_per_state", "required_state_ids", "required_sides", "modeling_policy", "min_effective_episodes_per_side", "min_effective_episodes_per_state_per_side", "min_successful_folds", "relative_logloss_improvement_min", "utility_feature_group", "bootstrap", "cost_scenarios", "payoff_proxy_bps", "concentration_limits", "feature_groups", "ablation_pairs")
        if any(name not in g2 for name in required_g2):
            raise ProtocolError("g2_evaluator is incomplete")
        if g2["folds"] != raw["split_policy"]["folds"] or g2["embargo_seconds"] != raw["split_policy"]["embargo_seconds"]:
            raise ProtocolError("g2_evaluator folds and embargo must equal split_policy")
        if g2["min_effective_episodes"] != raw["evaluation_policy"]["min_effective_episodes"] or g2["min_effective_episodes_per_state"] != raw["state_coverage_policy"]["min_effective_episodes_per_state"] or g2["required_state_ids"] != raw["state_coverage_policy"]["required_state_ids"]:
            raise ProtocolError("g2_evaluator coverage contract must equal protocol evaluation/state policy")
        if g2["folds"] != 5 or g2["min_successful_folds"] != 4:
            raise ProtocolError("v2 G2 preregistration requires exactly four successful folds of five")
        if g2["modeling_policy"] != "SEPARATE_MODELS" or g2["required_sides"] != ["BUY", "SELL"]:
            raise ProtocolError("v2 G2 requires separately trained/calibrated BUY and SELL models")
        context = _require_mapping(raw, "context_evidence", ("policy", "artifact", "role_window", "archive_receipts"))
        for name, required in (("policy", ("id", "sha256")), ("artifact", ("sha256", "manifest_sha256")), ("role_window", ("id", "sha256"))):
            item = _require_mapping(context, name, required)
            for key in required:
                value = item[key]
                if key == "id":
                    if not isinstance(value, str) or not value:
                        raise ProtocolError("context evidence %s requires ID" % name)
                else:
                    ResearchProtocol._validate_sha_or_required(value, "context evidence %s.%s" % (name, key), draft=draft)
        receipts = _require_mapping(context, "archive_receipts", ("schema_version", "require_verified_per_collection"))
        if receipts["schema_version"] != "evidence-archive-receipt.v1" or receipts["require_verified_per_collection"] is not True:
            raise ProtocolError("context evidence requires verified archive receipts")
        if not isinstance(g2["feature_groups"], dict) or not isinstance(g2["ablation_pairs"], dict) or set(g2["ablation_pairs"]) != expected_hypotheses:
            raise ProtocolError("g2_evaluator requires four declared ablation pairs")
        if g2["utility_feature_group"] not in g2["feature_groups"]:
            raise ProtocolError("g2_evaluator utility feature group is undeclared")
        limits = g2["concentration_limits"]
        if not isinstance(limits, dict) or limits.get("utc_day") != 0.40 or limits.get("state") != 0.40 or limits.get("direction") != 0.70:
            raise ProtocolError("g2_evaluator concentration limits must be day/state 0.40 and direction 0.70")

        bindings = raw.get("software_bindings")
        if not isinstance(bindings, dict) or set(bindings) != {"pipeline", "episode", "action", "label", "evaluator"}:
            raise ProtocolError("v2 protocol requires exactly pipeline, episode, action, label and evaluator software bindings")
        for component, binding in bindings.items():
            if not isinstance(binding, dict):
                raise ProtocolError("software binding %s must be an object" % component)
            if not isinstance(binding.get("component_id"), str) or not binding["component_id"]:
                raise ProtocolError("software binding %s requires component_id" % component)
            if not isinstance(binding.get("entrypoint"), str) or not binding["entrypoint"]:
                raise ProtocolError("software binding %s requires entrypoint" % component)
            ResearchProtocol._validate_sha_or_required(binding.get("source_sha256"), "software binding %s source_sha256" % component, draft=draft)

        episode = _require_mapping(raw, "episode_policy", ("policy_id", "digest", "trigger", "decision_frequency_seconds", "max_holding_seconds", "overlap_policy"))
        if episode["policy_id"] != "btc-usdt-absorption-episode-v2" or episode["digest"] != "d919eb5bd8eaf3a01e9a6e316a8d0876f00cbe9a55e14826b4c48f13440b2242":
            raise ProtocolError("v2 protocol must bind the frozen episode policy v2 identity and digest")

        action_contract = _require_mapping(raw, "action_contract", ("stages", "entry_policy"))
        if action_contract["stages"] != ["ENTER_PROBE"]:
            raise ProtocolError("v2 research protocol only permits the ENTER_PROBE stage")
        if action_contract["entry_policy"] != COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY:
            raise ProtocolError("v2 research protocol requires counterfactual label-only entry")

        if status == FROZEN_STATUS:
            # Reuse the mature v1 frozen checks for the shared scientific
            # contract, replacing only the v1 eligibility/hypothesis shape.
            legacy_view = dict(raw)
            legacy_view["data_eligibility"] = {
                "required_g1_policy_id": g1["required_g1_policy_id"],
                "required_g1_policy_sha256": g1["required_g1_policy_sha256"],
                "required_g1_report_sha256": g1["required_g1_report_sha256"],
                "require_g1_pass": g1["require_g1_pass"],
            }
            legacy_view["hypotheses"] = [
                {"hypothesis_id": item["hypothesis_id"], "pass_condition": "bound by gate_criteria", "failure_condition": "bound by gate_criteria"}
                for item in hypotheses
            ]
            ResearchProtocol._validate_frozen(legacy_view)

    @staticmethod
    def _validate_sha_or_required(value: Any, name: str, *, draft: bool) -> None:
        if _is_sha256(value):
            return
        if draft and _is_explicit_unresolved(value):
            return
        raise ProtocolError("%s must be a lowercase SHA-256%s" % (name, " or explicit REQUIRED placeholder while DRAFT" if draft else ""))

    @property
    def digest(self) -> str:
        payload = json.dumps(self.raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def is_frozen_for_research(self) -> bool:
        return self.status == FROZEN_STATUS

    def assert_frozen_for_research(self) -> None:
        if not self.is_frozen_for_research:
            raise ProtocolError("research evidence requires status %s" % FROZEN_STATUS)
        if self.raw.get("schema_version") == V2_SCHEMA_VERSION:
            ProtocolSupersessionGuard.assert_pinned_v2_lineage(self.raw)

    @property
    def g1_qualification(self) -> Dict[str, Any]:
        """Return the stable G1 binding across the historical v1 and v2 shapes."""
        eligibility = self.raw.get("data_eligibility")
        if not isinstance(eligibility, dict):
            raise ProtocolError("protocol data_eligibility is invalid")
        if self.raw.get("schema_version") == V2_SCHEMA_VERSION:
            qualification = eligibility.get("g1_qualification")
            if not isinstance(qualification, dict):
                raise ProtocolError("v2 protocol data_eligibility.g1_qualification is invalid")
            return qualification
        return eligibility

    def eligible(self, availability_kind: AvailabilityKind, evidence_stage: str) -> bool:
        policy = self.raw["availability_policy"]
        if availability_kind == AvailabilityKind.ACTUAL:
            return bool(policy["allow_actual"])
        if evidence_stage.upper() == "E3":
            return False
        if evidence_stage.upper() == "G2":
            return bool(policy["allow_reconstructed_for_g2"])
        return False
