"""Pure E0 validator for the P0.1 dynamic-hypothesis-graph candidate.

The public function accepts the exact frozen v1.1 raw bundle plus the three v1.2
contract JSON texts as caller-supplied UTF-8 strings.  It first delegates the
eight predecessor documents to the public v1.1 validator, pins their exact bytes
and accepted bundle identity, then validates the three new contracts.  It
performs no filesystem, network, market-data, adapter, replay, calibration,
paper, order, or execution I/O.  Authority roots and semantic/permission
ceilings are pinned in this module rather than trusted from candidate content.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from itertools import combinations
from typing import Any

from trade_system.research_system_contract_v1_1 import (
    validate_research_system_bundle_v1_1 as _validate_v1_1_bundle,
)

__all__ = ["validate_research_system_bundle_v1_2"]


_V1_1_OBJECT_PATH = "config/research_system.object_dictionary.v1.json"
_V1_1_HYPOTHESIS_PATH = (
    "config/research_system.hypothesis_validation_queue.v1.json"
)
_V1_1_MEASUREMENT_PATH = "config/research_system.measurement_contract.v1.json"
_V1_1_PARAMETER_PATH = "config/research_system.parameter_registry.v1.json"
_V1_1_SOURCE_PATH = "config/research_system.source_authority_registry.v1.json"
_V1_1_DISPUTE_PATH = "config/research_system.dispute_registry.v1.json"
_V1_1_STAGE_PATH = "config/research_system.stage_contract.v1.json"
_V1_1_OVERLAY_PATH = "config/research_system.semantic_claim_boundary.v1_1.json"
_V1_1_PATHS = frozenset(
    {
        _V1_1_OBJECT_PATH,
        _V1_1_HYPOTHESIS_PATH,
        _V1_1_MEASUREMENT_PATH,
        _V1_1_PARAMETER_PATH,
        _V1_1_SOURCE_PATH,
        _V1_1_DISPUTE_PATH,
        _V1_1_STAGE_PATH,
        _V1_1_OVERLAY_PATH,
    }
)
_V1_1_PHYSICAL_SHA256 = {
    _V1_1_OBJECT_PATH: (
        "9a167daea7bf05d1022e65da40be5b87786139a9e0f74d52994cbc2fd4915fff"
    ),
    _V1_1_HYPOTHESIS_PATH: (
        "e76ab11983326ab53d209b6efd362deb91a00215a0c47b14d5930457c614b4cb"
    ),
    _V1_1_MEASUREMENT_PATH: (
        "2e8d162f9be5182fbe25fd4e5d0c96fd817edc010b92ac61aa03f991aac20651"
    ),
    _V1_1_PARAMETER_PATH: (
        "a5321385626f2acd67063fed1cf8138b400c5911265ad333aed4da3958ca2a26"
    ),
    _V1_1_SOURCE_PATH: (
        "693cc7361c16fb154df97bf2c58a1e68807f990dc976df949658e7ce635abb12"
    ),
    _V1_1_DISPUTE_PATH: (
        "ae137bcb46051dd7ddb0b71f8c2b01390fcf9ff21d3d409fc7776ef1cb791ba3"
    ),
    _V1_1_STAGE_PATH: (
        "ab81251c0ea70e945d9ea7176e9cb59e7353477212dcf36a2d9e4424f944674b"
    ),
    _V1_1_OVERLAY_PATH: (
        "0cba2b1bd57143d1057fcc777180a08b0d7645d4b6286d6bfaa819e436d355f9"
    ),
}
_V1_1_BUNDLE_DIGEST = (
    "8a607d9d472f5a26d05e4e74ddca27876621a52ec102a6088f723687c52950fe"
)

_GRAPH_PATH = "config/research_system.runtime_hypothesis_graph_contract.v1_2.json"
_REGISTRY_PATH = (
    "config/research_system.runtime_hypothesis_template_registry.v1_2.json"
)
_EVIDENCE_PATH = (
    "config/research_system.runtime_evidence_evaluation_contract.v1_2.json"
)
_V1_2_CONTRACT_PATHS = frozenset({_GRAPH_PATH, _REGISTRY_PATH, _EVIDENCE_PATH})
_REQUIRED_PATHS = _V1_1_PATHS | _V1_2_CONTRACT_PATHS

_ROUTE = {
    "path": "config/sol_decision.research-system-dynamic-hypothesis-graph-p0_1-route.v1.json",
    "decision_id": "SOL_RESEARCH_SYSTEM_DYNAMIC_HYPOTHESIS_GRAPH_P0_1_ROUTE.v1",
    "physical_sha256": "eb1ded24b8cb2792135422bc2cc28c52344e0a299354449fecfce43a83614e17",
    "canonical_sha256": "d2550e5eacd6a304eda141977eefec280d478c86bd3a13189277cc7c9ecfc1d2",
}
_GRAPH_AUTHORITY = {
    "route_decision": {
        **_ROUTE,
        "decision_state": (
            "AUTHORIZED_P0_1_E0_DYNAMIC_HYPOTHESIS_GRAPH_CHALLENGER"
        ),
    },
    "accepted_p0_foundation": {
        "path": "config/sol_decision.research-system-reconstruction-p0-gate.v1_1.json",
        "decision_id": "SOL_RESEARCH_SYSTEM_RECONSTRUCTION_P0_GATE.v1_1",
        "decision_state": "ACCEPT_P0",
        "physical_sha256": "ff9f2b608fe387b953e5d18e1a3cd0a246fcc43bf209f694ffab53f867a8f4cf",
        "canonical_sha256": "d0968a40d33cea693cd2ad979a656b7897c30fe58b3cd94d85b6f1ce5afd6a58",
    },
    "current_core_theory": {
        "path": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
        "authority_id": "CORE_TRADING_THEORY.v2.1",
        "version": "2.1",
        "status": "CURRENT_IMMUTABLE_AUTHORITY",
        "physical_sha256": "2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d",
    },
    "core_authority_manifest": {
        "path": "config/core_trading_theory.authority.v2_1.json",
        "physical_sha256": "a3e174c616b176253f4aef2ce267a932d43f7e64db3490db815a27f007df12d4",
    },
    "frozen_v1_1_inventory": {
        "path": "config/research_system.p0_artifact_inventory.v1_1.json",
        "inventory_id": "MSTA_HED_RESEARCH_SYSTEM_P0_ARTIFACT_INVENTORY.v1_1",
        "physical_sha256": "dc78634eb373aef988cc7a13a5bfdb87d03303b452b22b896d95c02d88a2ee26",
        "canonical_sha256": "c6cb8e84e37d858b971d02b2cf4aed7878804327922482460701ea4ef214cbc1",
    },
    "frozen_v1_1_bundle": {
        "schema_version": "research-system-contract-bundle.v1_1",
        "document_count": 8,
        "bundle_digest": "8a607d9d472f5a26d05e4e74ddca27876621a52ec102a6088f723687c52950fe",
    },
}
_GRAPH_CANONICAL_SHA = (
    "ecffaef260232b2e16eac8f2d80e49c44f97006a8cf8a1ca948a588f3ca1672b"
)
_REGISTRY_CANONICAL_SHA = (
    "11b9f1e85cbc7d0e8a1c4ad4b8cc90b8878eb335bd26d098503bbc1b44b02f6c"
)
_REGISTRY_AUTHORITY = {
    "route_decision": dict(_ROUTE),
    "graph_contract": {
        "path": _GRAPH_PATH,
        "contract_id": "MSTA_HED_RUNTIME_HYPOTHESIS_GRAPH_CONTRACT.v1_2",
        "canonical_sha256": _GRAPH_CANONICAL_SHA,
    },
    "frozen_research_hypothesis_queue": {
        "path": "config/research_system.hypothesis_validation_queue.v1.json",
        "physical_sha256": "e76ab11983326ab53d209b6efd362deb91a00215a0c47b14d5930457c614b4cb",
        "canonical_sha256": "a4675f506a617fc9b871088f2926a3a5f204c37cc7230222459e999bd3f57704",
    },
}
_EVIDENCE_AUTHORITY = {
    "route_decision": dict(_ROUTE),
    "graph_contract": {
        "path": _GRAPH_PATH,
        "contract_id": "MSTA_HED_RUNTIME_HYPOTHESIS_GRAPH_CONTRACT.v1_2",
        "canonical_sha256": _GRAPH_CANONICAL_SHA,
    },
    "template_registry": {
        "path": _REGISTRY_PATH,
        "registry_id": "MSTA_HED_RUNTIME_HYPOTHESIS_TEMPLATE_REGISTRY.v1_2",
        "canonical_sha256": _REGISTRY_CANONICAL_SHA,
    },
}

_STAGE_DENIALS = {
    "D0": "DENIED",
    "D1": "DENIED",
    "D2": "DENIED",
    "D3": "DENIED",
    "E2": "DENIED",
    "E3": "DENIED",
}
_GRAPH_CLAIM_BOUNDARY = {
    "candidate_acceptance": "NOT_EVALUATED",
    "current_core_theory": "UNCHANGED",
    "runtime_generator": "CONTRACT_ONLY_NOT_IMPLEMENTED",
    "dynamic_policy_runtime": "CONTRACT_ONLY_NOT_IMPLEMENTED",
    "event_driven_replay": "CONTRACT_ONLY_NOT_IMPLEMENTED_NOT_AUTHORIZED",
    "runtime_data": "NOT_ACCESSED",
    "machine_predicate_market_validity": "NOT_EVALUATED",
    "mechanism_truth": "NOT_ESTABLISHED",
    "probability_calibration": "NOT_AUTHORIZED",
    "predictive_validity": "NOT_EVALUATED",
    "profitability": "NOT_EVALUATED",
    "backtest": "NOT_AUTHORIZED",
    "paper": "NOT_AUTHORIZED",
    "deployment": "DENIED",
    "trading": "DENIED",
    "f005_dsp022": "REMAINS_OPEN_DEFERRED_BLOCKING",
    "maximum_positive_claim": (
        "Exact E0 runtime hypothesis graph schema and synthetic contract candidate only."
    ),
}
_REGISTRY_CLAIM_BOUNDARY = {
    "template_registry": "FINITE_E0_CANDIDATE_ONLY",
    "machine_predicate_execution": "SYNTHETIC_FIXTURES_ONLY",
    "machine_predicate_market_validity": "NOT_EVALUATED",
    "mechanism_truth": "NOT_ESTABLISHED",
    "probability_calibration": "NOT_AUTHORIZED",
    "backtest": "NOT_AUTHORIZED",
    "paper": "NOT_AUTHORIZED",
    "deployment": "DENIED",
    "trading": "DENIED",
    "f005_dsp022": "REMAINS_OPEN_DEFERRED_BLOCKING",
}
_EVIDENCE_CLAIM_BOUNDARY = {
    "evidence_contract": "E0_SYNTHETIC_STRUCTURE_ONLY",
    "runtime_raw_lineage": "NOT_ESTABLISHED",
    "machine_predicate_market_validity": "NOT_EVALUATED",
    "identifiability_market_validity": "NOT_EVALUATED",
    "probability_calibration": "NOT_AUTHORIZED",
    "numeric_information_gain": "FORBIDDEN",
    "future_evaluation_semantics": "E0_INTERFACE_ONLY_NO_EVALUATION",
    "backtest": "NOT_AUTHORIZED",
    "holdout": "NOT_AUTHORIZED",
    "paper": "NOT_AUTHORIZED",
    "deployment": "DENIED",
    "trading": "DENIED",
    "f005_dsp022": "REMAINS_OPEN_DEFERRED_BLOCKING",
}

_GRAPH_TOP_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "created_at",
        "status",
        "evidence_level",
        "authority_binding",
        "plane_contract",
        "object_schemas",
        "graph_semantics",
        "dynamic_policy_contract",
        "generation_contract",
        "path_identity_contract",
        "terminal_partition_contract",
        "direction_and_residual_contract",
        "stage_denials",
        "claim_boundary",
        "canonicalization",
        "contract_sha256",
    }
)
_REGISTRY_TOP_KEYS = frozenset(
    {
        "registry_id",
        "schema_version",
        "created_at",
        "status",
        "evidence_level",
        "authority_binding",
        "enum_registry",
        "required_machine_predicate_shape",
        "template_invariants",
        "machine_predicates",
        "mechanism_templates",
        "path_templates",
        "trade_templates",
        "topology_edges",
        "shock_crosswalk",
        "fixture_bindings",
        "stage_denials",
        "claim_boundary",
        "canonicalization",
        "registry_sha256",
    }
)
_EVIDENCE_TOP_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "created_at",
        "status",
        "evidence_level",
        "authority_binding",
        "evidence_item_schema",
        "target_effect_schema",
        "update_receipt_schema",
        "evidence_semantics",
        "conflict_contract",
        "mechanism_identifiability_classes",
        "path_discrimination_contracts",
        "next_observation_plans",
        "probability_contract",
        "terminal_scenario_aggregation_contract",
        "denominator_contract",
        "future_oos_gate",
        "failure_diagnosis_and_versioning",
        "event_driven_pit_replay_contract",
        "policy_trajectory_evaluation_contract",
        "synthetic_fixture_contract",
        "synthetic_fixture_sets",
        "stage_denials",
        "claim_boundary",
        "canonicalization",
        "contract_sha256",
    }
)
_CANONICAL_DOMAINS = {
    _GRAPH_PATH: "msta-hed/research-system-runtime-hypothesis-graph-contract/v1_2",
    _REGISTRY_PATH: (
        "msta-hed/research-system-runtime-hypothesis-template-registry/v1_2"
    ),
    _EVIDENCE_PATH: (
        "msta-hed/research-system-runtime-evidence-evaluation-contract/v1_2"
    ),
}
_DIGEST_FIELDS = {
    _GRAPH_PATH: "contract_sha256",
    _REGISTRY_PATH: "registry_sha256",
    _EVIDENCE_PATH: "contract_sha256",
}

_MACHINE_PREDICATE_FIELDS = (
    "predicate_id",
    "predicate_version",
    "observable_id",
    "operator",
    "threshold_or_interval",
    "clock",
    "window",
    "minimum_persistence",
    "quality_requirement",
    "gap_and_censoring_rule",
    "terminal_reason",
    "precedence",
)
_PREDICATE_IDS = frozenset(
    {
        "PRED-SHOCK-DOWNSIDE-ACTIVATE-01",
        "PRED-LOW-DOWNSIDE-EFFICIENCY-01",
        "PRED-STRUCTURE-RECLAIM-01",
        "PRED-HIGHER-LOW-ACCEPTED-01",
        "PRED-UPWARD-TRANSITION-RESOLVE-01",
        "PRED-ZONE-LOSS-HARD-01",
        "PRED-ABSORPTION-EXPIRY-01",
        "PRED-SHOCK-REBOUND-ACTIVATE-01",
        "PRED-NO-HTF-ACCEPTANCE-01",
        "PRED-LOWER-HIGH-01",
        "PRED-EVENT-VWAP-LOSS-01",
        "PRED-DOWNSIDE-RESUMPTION-RESOLVE-01",
        "PRED-UPWARD-ACCEPTANCE-HARD-01",
        "PRED-SQUEEZE-EXPIRY-01",
        "PRED-COMPRESSION-LOW-ER-01",
        "PRED-OVERLAP-ROTATION-01",
        "PRED-RANGE-PERSIST-RESOLVE-01",
        "PRED-DIRECTIONAL-ACCEPTANCE-HARD-01",
        "PRED-BALANCE-EXPIRY-01",
        "PRED-ZONE-TOUCHES-ACTIVATE-01",
        "PRED-DECLINING-REACTION-01",
        "PRED-EFFECTIVE-BREAK-01",
        "PRED-FAILED-RECLAIM-01",
        "PRED-DOWNSIDE-EXPANSION-RESOLVE-01",
        "PRED-RAPID-RECLAIM-HIGHER-LOW-HARD-01",
        "PRED-SUPPORT-CONSUME-EXPIRY-01",
        "PRED-TERMINAL-CELL-ABS-UP-01",
        "PRED-TERMINAL-CELL-SQUEEZE-DOWN-01",
        "PRED-TERMINAL-CELL-BALANCE-01",
        "PRED-TERMINAL-CELL-SUPPORT-DOWN-01",
    }
)
_MECHANISM_IDS = frozenset(
    {
        "MHT-ABSORPTION-REVERSAL-01",
        "MHT-SQUEEZE-CONTINUATION-01",
        "MHT-RANGE-BALANCE-01",
        "MHT-SUPPORT-CONSUMPTION-01",
    }
)
_PATH_IDS = frozenset(
    {
        "PHT-SHOCK-ABSORPTION-UP-01",
        "PHT-SHOCK-SQUEEZE-FAIL-DOWN-01",
        "PHT-SHOCK-BALANCE-01",
        "PHT-SHOCK-SUPPORT-CONSUME-DOWN-01",
    }
)
_TRADE_IDS = frozenset(
    {
        "THT-ABSORPTION-RECLAIM-LONG-01",
        "THT-SQUEEZE-FAIL-SHORT-01",
        "THT-SUPPORT-BREAK-RETEST-SHORT-01",
    }
)
_FIXTURE_IDS = frozenset(
    {
        "FIXSET-MHT-ABSORPTION-01",
        "FIXSET-MHT-SQUEEZE-01",
        "FIXSET-MHT-RANGE-01",
        "FIXSET-MHT-SUPPORT-CONSUME-01",
        "FIXSET-PHT-ABSORPTION-UP-01",
        "FIXSET-PHT-SQUEEZE-FAIL-DOWN-01",
        "FIXSET-PHT-BALANCE-01",
        "FIXSET-PHT-SUPPORT-CONSUME-DOWN-01",
        "FIXSET-THT-ABSORPTION-LONG-01",
        "FIXSET-THT-SQUEEZE-FAIL-SHORT-01",
        "FIXSET-THT-SUPPORT-BREAK-SHORT-01",
    }
)
_FIXTURE_BY_TEMPLATE = {
    "MHT-ABSORPTION-REVERSAL-01": ("MECHANISM", "FIXSET-MHT-ABSORPTION-01"),
    "MHT-SQUEEZE-CONTINUATION-01": (
        "MECHANISM",
        "FIXSET-MHT-SQUEEZE-01",
    ),
    "MHT-RANGE-BALANCE-01": ("MECHANISM", "FIXSET-MHT-RANGE-01"),
    "MHT-SUPPORT-CONSUMPTION-01": (
        "MECHANISM",
        "FIXSET-MHT-SUPPORT-CONSUME-01",
    ),
    "PHT-SHOCK-ABSORPTION-UP-01": (
        "PATH",
        "FIXSET-PHT-ABSORPTION-UP-01",
    ),
    "PHT-SHOCK-SQUEEZE-FAIL-DOWN-01": (
        "PATH",
        "FIXSET-PHT-SQUEEZE-FAIL-DOWN-01",
    ),
    "PHT-SHOCK-BALANCE-01": ("PATH", "FIXSET-PHT-BALANCE-01"),
    "PHT-SHOCK-SUPPORT-CONSUME-DOWN-01": (
        "PATH",
        "FIXSET-PHT-SUPPORT-CONSUME-DOWN-01",
    ),
    "THT-ABSORPTION-RECLAIM-LONG-01": (
        "TRADE",
        "FIXSET-THT-ABSORPTION-LONG-01",
    ),
    "THT-SQUEEZE-FAIL-SHORT-01": (
        "TRADE",
        "FIXSET-THT-SQUEEZE-FAIL-SHORT-01",
    ),
    "THT-SUPPORT-BREAK-RETEST-SHORT-01": (
        "TRADE",
        "FIXSET-THT-SUPPORT-BREAK-SHORT-01",
    ),
}
_IDENTIFIABILITY_IDS = frozenset(
    {
        "MIC-PRESSURE-RESPONSE-OBSERVATIONAL-01",
        "MIC-REBOUND-DRIVER-NONIDENTIFIABLE-01",
        "MIC-BOUNDED-RESPONSE-01",
    }
)
_MECHANISM_PRIMARY_CLASS = {
    "MHT-ABSORPTION-REVERSAL-01": "MIC-PRESSURE-RESPONSE-OBSERVATIONAL-01",
    "MHT-SQUEEZE-CONTINUATION-01": "MIC-REBOUND-DRIVER-NONIDENTIFIABLE-01",
    "MHT-RANGE-BALANCE-01": "MIC-BOUNDED-RESPONSE-01",
    "MHT-SUPPORT-CONSUMPTION-01": "MIC-PRESSURE-RESPONSE-OBSERVATIONAL-01",
}
_PLAN_IDS = frozenset(
    {
        "NOP-ABS-VS-SQUEEZE-01",
        "NOP-ABS-VS-BALANCE-01",
        "NOP-ABS-VS-SUPPORT-01",
        "NOP-SQUEEZE-VS-BALANCE-01",
        "NOP-SAME-DOWNSIDE-SHORT-01",
        "NOP-BALANCE-VS-SUPPORT-01",
    }
)

_MECHANISM_KEYS = frozenset(
    {
        "mechanism_template_id",
        "template_version",
        "status",
        "source_research_hypothesis_ids",
        "activation_predicate_ids",
        "support_predicate_ids",
        "soft_contradiction_predicate_ids",
        "hard_invalidation_predicate_ids",
        "expiry_predicate_ids",
        "identifiability_class_id",
        "truth_status",
        "fixture_set_id",
    }
)
_PATH_KEYS = frozenset(
    {
        "path_template_id",
        "template_version",
        "status",
        "source_research_hypothesis_id",
        "activation_predicate_ids",
        "support_predicate_ids",
        "soft_contradiction_predicate_ids",
        "hard_invalidation_predicate_ids",
        "resolution_predicate_ids",
        "expiry_predicate_ids",
        "partial_order_milestones",
        "required_partial_order_edges",
        "optional_partial_order_edges",
        "repeatable_milestones",
        "skippable_milestones",
        "terminal_cell_id",
        "terminal_matcher_predicate_ids",
        "terminal_scenario_id",
        "direction",
        "default_trade_side",
        "horizon_bars",
        "clock_profile",
        "identity_fields",
        "path_identity_digest",
        "fixture_set_id",
    }
)
_TRADE_KEYS = frozenset(
    {
        "trade_template_id",
        "template_version",
        "status",
        "source_research_hypothesis_id",
        "parent_path_template_id",
        "side",
        "activation_predicate_ids",
        "trade_trigger_predicate_ids",
        "trade_invalidation_predicate_ids",
        "expiry_predicate_ids",
        "mechanism_context_template_ids",
        "mechanism_context_effect",
        "permission_requirement",
        "permission_state",
        "max_risk",
        "fixture_set_id",
    }
)
_PATH_IDENTITY_FIELDS = (
    "activation_predicate_ids",
    "required_partial_order_edges",
    "optional_partial_order_edges",
    "repeatable_milestones",
    "skippable_milestones",
    "terminal_cell_id",
    "terminal_matcher_predicate_ids",
    "horizon_bars",
    "clock_profile",
    "hard_invalidation_predicate_ids",
    "expiry_predicate_ids",
)
_REQUIRED_CASE_KINDS = frozenset(
    {"POSITIVE", "BOUNDARY", "CLOCK", "GAP", "HARD_INVALIDATION", "EXPIRY"}
)

_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class _ContractError(Exception):
    def __init__(self, reason_code: str, **details: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.details = dict(sorted(details.items()))


class _DuplicateKey(Exception):
    pass


class _NonFiniteNumber(Exception):
    pass


def _reject(reason_code: str, path: str = "", field: str = "", **extra: str) -> None:
    details = dict(extra)
    if path:
        details["path"] = path
    if field:
        details["field"] = field
    raise _ContractError(reason_code, **details)


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise _NonFiniteNumber


def _check_finite(value: Any, path: str, field: str) -> None:
    if type(value) is float and not math.isfinite(value):
        _reject("E_JSON_NONFINITE", path, field)
    if type(value) is dict:
        for key, child in value.items():
            _check_finite(child, path, f"{field}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _check_finite(child, path, f"{field}[{index}]")


def _strict_parse(path: str, raw: Any) -> dict[str, Any]:
    if type(raw) is not str:
        _reject("E_RAW_TYPE", path)
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey as exc:
        _reject("E_JSON_DUPLICATE_KEY", path, str(exc))
    except _NonFiniteNumber:
        _reject("E_JSON_NONFINITE", path)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        _reject("E_JSON_MALFORMED", path)
    _check_finite(value, path, "$")
    if type(value) is not dict:
        _reject("E_TOP_LEVEL_TYPE", path, "$")
    return value


def _exact_object(
    value: Any,
    keys: frozenset[str] | set[str],
    path: str,
    field: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        _reject("E_FIELD_TYPE", path, field)
    actual = frozenset(value)
    expected = frozenset(keys)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        if extra:
            _reject("E_UNKNOWN_FIELD", path, f"{field}.{extra[0]}")
        _reject("E_FIELD_EMPTY", path, f"{field}.{missing[0]}")
    return value


def _list(value: Any, path: str, field: str, *, nonempty: bool = False) -> list[Any]:
    if type(value) is not list:
        _reject("E_FIELD_TYPE", path, field)
    if nonempty and not value:
        _reject("E_FIELD_EMPTY", path, field)
    return value


def _text(value: Any, path: str, field: str) -> str:
    if type(value) is not str:
        _reject("E_FIELD_TYPE", path, field)
    if not value.strip():
        _reject("E_FIELD_EMPTY", path, field)
    return value


def _integer(value: Any, path: str, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int:
        _reject("E_FIELD_TYPE", path, field)
    if value < minimum:
        _reject("E_FIELD_VALUE", path, field)
    return value


def _sha(value: Any, path: str, field: str) -> str:
    text = _text(value, path, field)
    if not _SHA_RE.fullmatch(text):
        _reject("E_SHA256", path, field)
    return text


def _utc(value: Any, path: str, field: str) -> datetime:
    text = _text(value, path, field)
    if not _UTC_RE.fullmatch(text):
        _reject("E_CLOCK", path, field)
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject("E_CLOCK", path, field)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _exact(value: Any, expected: Any, reason: str, path: str, field: str) -> None:
    if type(value) is not type(expected) or value != expected:
        _reject(reason, path, field)


def _validate_canonical(
    document: dict[str, Any], path: str, digest_field: str
) -> str:
    domain = _CANONICAL_DOMAINS[path]
    expected = {
        "algorithm": "SHA-256",
        "domain": domain,
        "domain_separator_hex": "00",
        "exclude_fields": [digest_field],
        "ensure_ascii": True,
        "sort_keys": True,
        "separators": [",", ":"],
        "encoding": "UTF-8",
    }
    _exact(
        document.get("canonicalization"),
        expected,
        "E_CANONICALIZATION",
        path,
        "canonicalization",
    )
    supplied = _sha(document.get(digest_field), path, digest_field)
    unsigned = dict(document)
    unsigned.pop(digest_field, None)
    calculated = hashlib.sha256(
        domain.encode("utf-8") + b"\0" + _canonical_bytes(unsigned)
    ).hexdigest()
    if supplied != calculated:
        _reject("E_SELF_DIGEST", path, digest_field)
    return supplied


def _validate_common(
    document: dict[str, Any],
    path: str,
    top_keys: frozenset[str],
    metadata: dict[str, str],
    authority: dict[str, Any],
    boundary: dict[str, str],
) -> str:
    _exact_object(document, top_keys, path, "$")
    for key, expected in metadata.items():
        _exact(document[key], expected, "E_METADATA", path, key)
    _utc(document["created_at"], path, "created_at")
    _exact(
        document["authority_binding"],
        authority,
        "E_AUTHORITY_BINDING",
        path,
        "authority_binding",
    )
    _exact(
        document["stage_denials"],
        _STAGE_DENIALS,
        "E_STAGE_DENIAL",
        path,
        "stage_denials",
    )
    _exact(
        document["claim_boundary"],
        boundary,
        "E_CLAIM_BOUNDARY",
        path,
        "claim_boundary",
    )
    return _validate_canonical(document, path, _DIGEST_FIELDS[path])


def _validate_graph(document: dict[str, Any]) -> str:
    digest = _validate_common(
        document,
        _GRAPH_PATH,
        _GRAPH_TOP_KEYS,
        {
            "contract_id": "MSTA_HED_RUNTIME_HYPOTHESIS_GRAPH_CONTRACT.v1_2",
            "schema_version": (
                "research-system-runtime-hypothesis-graph-contract.v1_2"
            ),
            "status": "E0_P0_1_CANDIDATE_NOT_ACCEPTED",
            "evidence_level": "E0_STATIC_AND_SYNTHETIC_CONTRACT_ONLY",
        },
        _GRAPH_AUTHORITY,
        _GRAPH_CLAIM_BOUNDARY,
    )
    _exact(
        document["plane_contract"],
        {
            "research_plane_object": "ResearchHypothesis",
            "runtime_plane_objects": [
                "MechanismHypothesisInstance",
                "PathHypothesisInstance",
                "TradeHypothesisInstance",
            ],
            "namespace_rule": "RESEARCH_AND_RUNTIME_IDENTITIES_ARE_DISJOINT",
            "runtime_result_rewrites_research_hypothesis": False,
            "runtime_revision_rewrites_prior_revision": False,
            "research_plane_authorizes_action": False,
            "runtime_plane_authorizes_action": False,
        },
        "E_GRAPH_SEMANTICS",
        _GRAPH_PATH,
        "plane_contract",
    )
    expected_schemas = {
        "MechanismHypothesisInstance": [
            "mechanism_instance_id",
            "opportunity_id",
            "mechanism_template_id",
            "graph_revision_id",
            "generated_at",
            "status",
            "ordinal_support",
            "identifiability_class_id",
            "accepted_evidence_ids",
            "conflict_ids",
            "terminal_reason",
            "receipt_tip_digest",
        ],
        "PathHypothesisInstance": [
            "path_instance_id",
            "opportunity_id",
            "path_template_id",
            "graph_revision_id",
            "generated_at",
            "current_milestones",
            "terminal_cell_id",
            "terminal_scenario_id",
            "direction",
            "status",
            "ordinal_support",
            "hard_invalidation_state",
            "expiry_at",
            "accepted_evidence_ids",
            "conflict_ids",
            "receipt_tip_digest",
        ],
        "TradeHypothesisInstance": [
            "trade_instance_id",
            "opportunity_id",
            "trade_template_id",
            "parent_path_instance_id",
            "graph_revision_id",
            "generated_at",
            "side",
            "trigger_state",
            "invalidation_state",
            "expiry_at",
            "status",
            "mechanism_context_instance_ids",
            "mechanism_context_effect",
            "permission_state",
            "max_risk",
            "receipt_tip_digest",
        ],
        "TypedGraphEdge": [
            "edge_instance_id",
            "edge_template_id",
            "graph_revision_id",
            "from_kind",
            "from_instance_id",
            "to_kind",
            "to_instance_id",
            "edge_type",
            "transfer_mode",
            "created_at",
        ],
        "GraphRevisionReceipt": [
            "graph_revision_id",
            "opportunity_id",
            "decision_at",
            "refresh_trigger",
            "state_snapshot_id",
            "state_snapshot_digest",
            "structural_position_id",
            "structural_position_digest",
            "data_quality_snapshot_id",
            "data_quality_snapshot_digest",
            "clock_snapshot_id",
            "clock_snapshot_digest",
            "template_registry_id",
            "template_registry_digest",
            "generator_policy_id",
            "generator_policy_version",
            "generator_policy_digest",
            "prior_revision_digest",
            "selected_template_ids",
            "rejected_template_ids_with_reasons",
            "generated_instance_ids",
            "generated_edge_instance_ids",
            "unknown_reasons",
            "action_disposition",
            "revision_digest",
        ],
        "TerminalScenarioAggregationReceipt": [
            "aggregation_receipt_id",
            "opportunity_id",
            "as_of",
            "aggregation_rule_version",
            "terminal_scenario_id",
            "source_path_instance_ids",
            "source_path_template_ids",
            "source_terminal_cell_ids",
            "source_path_receipt_tip_digests",
            "ordinal_only",
            "probability_values",
            "receipt_digest",
        ],
        "PolicyTrajectory": [
            "trajectory_id",
            "opportunity_id",
            "policy_version",
            "started_at",
            "latest_event_available_at",
            "event_ids",
            "graph_revision_ids",
            "trade_hypothesis_instance_ids",
            "decision_receipt_ids",
            "order_intent_ids",
            "position_transition_ids",
            "status",
            "previous_trajectory_digest",
            "trajectory_digest",
        ],
        "DecisionReceipt": [
            "decision_receipt_id",
            "trajectory_id",
            "opportunity_id",
            "event_id",
            "decision_at",
            "state_snapshot_digest",
            "graph_revision_id",
            "graph_revision_digest",
            "selected_trade_hypothesis_instance_id",
            "action_class",
            "policy_action",
            "reason_codes",
            "declared_risk_before",
            "declared_risk_after",
            "order_intent_ids",
            "position_transition_id",
            "previous_decision_receipt_digest",
            "receipt_digest",
        ],
        "OrderIntent": [
            "order_intent_id",
            "trajectory_id",
            "opportunity_id",
            "trade_hypothesis_instance_id",
            "permission_object_id",
            "permission_state",
            "created_at",
            "intent_action",
            "side",
            "order_type",
            "quantity",
            "limit_price",
            "stop_price",
            "target_prices",
            "time_in_force",
            "expires_at",
            "replaces_order_intent_id",
            "status",
            "previous_order_intent_digest",
            "intent_digest",
        ],
        "PositionStateTransition": [
            "position_transition_id",
            "trajectory_id",
            "opportunity_id",
            "position_id",
            "event_id",
            "decision_receipt_id",
            "transition_at",
            "policy_action",
            "position_state_before",
            "position_state_after",
            "quantity_before",
            "quantity_after",
            "stop_before",
            "stop_after",
            "target_set_before",
            "target_set_after",
            "declared_controllable_worst_case_risk_before",
            "declared_controllable_worst_case_risk_after",
            "monotonic_risk_check",
            "market_gap_or_slippage_observed",
            "previous_position_transition_digest",
            "transition_digest",
        ],
        "PolicyEvent": [
            "event_id",
            "opportunity_id",
            "available_at",
            "source_sequence",
            "event_kind",
            "source_or_measurement_id",
            "payload_digest",
            "data_quality_digest",
            "supersedes_event_id",
            "event_digest",
        ],
        "PositionLock": [
            "position_lock_id",
            "trajectory_id",
            "opportunity_id",
            "trade_hypothesis_instance_id",
            "parent_path_instance_id",
            "side",
            "locked_quantity",
            "locked_stop",
            "locked_target_set",
            "locked_horizon_end",
            "locked_total_risk_budget",
            "locked_permission_object_id",
            "locked_at",
            "lock_digest",
        ],
        "RiskEnvelopeSnapshot": [
            "risk_envelope_id",
            "trajectory_id",
            "event_id",
            "as_of",
            "risk_unit",
            "realized_loss_used",
            "open_position_worst_case_loss",
            "pending_order_worst_case_loss",
            "fees_reserve",
            "funding_reserve",
            "tail_reserve",
            "total_risk_used_or_reserved",
            "locked_total_risk_budget",
            "within_lock",
            "previous_risk_envelope_digest",
            "risk_envelope_digest",
        ],
    }
    _exact(
        document["object_schemas"],
        expected_schemas,
        "E_SCHEMA",
        _GRAPH_PATH,
        "object_schemas",
    )
    _exact(
        document["graph_semantics"],
        {
            "edge_types": ["MECHANISM_TO_PATH", "PATH_TO_TRADE"],
            "mechanism_to_path_cardinality": "MANY_TO_MANY",
            "mechanism_to_path_transfer_mode": "NO_SCORE_TRANSFER",
            "path_to_trade_cardinality": "ONE_PATH_TO_ZERO_OR_MORE_TRADES",
            "trade_parent_path_cardinality": "EXACTLY_ONE",
            "multi_path_composite_trade": "DEFERRED_NOT_IN_V1_2",
            "mechanism_context_in_trade": "CONTEXT_ONLY_EFFECT_NONE",
            "cross_layer_implicit_update": "FORBIDDEN",
            "top_path_auto_action": "FORBIDDEN",
            "scenario_aggregation_rewrites_path": "FORBIDDEN",
        },
        "E_GRAPH_SEMANTICS",
        _GRAPH_PATH,
        "graph_semantics",
    )
    dynamic = _exact_object(
        document["dynamic_policy_contract"],
        {
            "contract_id",
            "status",
            "policy_event_order",
            "policy_state_vector",
            "transition_function",
            "transition_function_pure",
            "same_state_event_and_package_same_output",
            "duplicate_event_idempotent_no_second_state_change_or_receipt",
            "event_update_chain",
            "exactly_one_decision_receipt_per_admitted_event",
            "counterfactual_lane_states",
            "counterfactual_state_transition_order",
            "real_permission_state",
            "real_action_state",
            "real_max_risk",
            "action_classes",
            "position_lock_contract",
            "position_management_risk_contract",
            "path_switch_contract",
            "gap_contract",
            "carrier_contract",
            "runtime_implementation",
            "backtest_implementation",
            "order_submission",
            "market_or_execution_claim",
        },
        _GRAPH_PATH,
        "dynamic_policy_contract",
    )
    dynamic_scalar_contract = {
        "contract_id": "MSTA_HED_DYNAMIC_POLICY_TRAJECTORY.v1_2",
        "status": "E0_INTERFACE_ONLY_NOT_IMPLEMENTED_NOT_AUTHORIZED",
        "policy_event_order": [
            "available_at_ASC",
            "source_sequence_ASC",
            "event_id_ASC",
        ],
        "policy_state_vector": [
            "information_set",
            "graph_revision",
            "policy_state",
            "position_lock",
            "position",
            "risk_envelope",
            "permission",
            "receipt_chain",
        ],
        "transition_function": (
            "F(Sigma_i,PolicyEvent_i,FrozenPolicyPackage)->"
            "(Sigma_i_plus_1,DecisionReceipt_i,Emissions_i)"
        ),
        "transition_function_pure": True,
        "same_state_event_and_package_same_output": True,
        "duplicate_event_idempotent_no_second_state_change_or_receipt": True,
        "event_update_chain": [
            "PIT_EVENT_ADMITTED",
            "STATE_SNAPSHOT_UPDATED_OR_NO_CHANGE_RECEIPT",
            "GRAPH_REVISION_CREATED_OR_NO_CHANGE_RECEIPT",
            "TRADE_HYPOTHESIS_CREATED_REVISED_EXPIRED_OR_NO_CHANGE_RECEIPT",
            "POLICY_ACTION_DECIDED",
            "DECISION_RECEIPT_APPENDED",
            "ORDER_INTENT_AND_POSITION_TRANSITION_APPENDED_IF_APPLICABLE",
        ],
        "exactly_one_decision_receipt_per_admitted_event": True,
        "counterfactual_lane_states": [
            "FLAT",
            "WATCH",
            "PREPARE",
            "CF_ENTRY_ELIGIBLE",
            "CF_OPEN_LOCKED",
            "CF_MANAGE",
            "CF_EXITED",
        ],
        "counterfactual_state_transition_order": (
            "MONOTONE_FORWARD_EXCEPT_WATCH_PREPARE_MAY_RETURN_TO_FLAT_WITH_RECEIPT"
        ),
        "real_permission_state": "DENIED_P0_1",
        "real_action_state": "ABSTAIN",
        "real_max_risk": 0,
        "runtime_implementation": "NOT_IMPLEMENTED",
        "backtest_implementation": "NOT_IMPLEMENTED",
        "order_submission": "DENIED",
        "market_or_execution_claim": "NONE",
    }
    for key, expected in dynamic_scalar_contract.items():
        reason = (
            "E_PERMISSION_ESCALATION"
            if key in {"real_permission_state", "real_action_state", "real_max_risk"}
            else "E_DYNAMIC_POLICY"
        )
        _exact(dynamic[key], expected, reason, _GRAPH_PATH, f"dynamic_policy_contract.{key}")
    _exact(
        dynamic["action_classes"],
        {
            "NEW_RISK": [
                "ABSTAIN_NEW_RISK",
                "CREATE_ENTRY_INTENT",
                "CANCEL_UNFILLED_ENTRY",
                "REPLACE_UNFILLED_ENTRY_NONINCREASING_DECLARED_RISK",
            ],
            "POSITION_MANAGEMENT": ["KEEP", "TIGHTEN", "REDUCE", "EXIT"],
        },
        "E_DYNAMIC_POLICY",
        _GRAPH_PATH,
        "dynamic_policy_contract.action_classes",
    )
    _exact(
        dynamic["position_lock_contract"],
        {
            "created_at_state": "CF_OPEN_LOCKED",
            "immutable_after_creation": True,
            "locks": [
                "opportunity_id",
                "trade_hypothesis_instance_id",
                "parent_path_instance_id",
                "side",
                "initial_quantity",
                "initial_stop",
                "initial_target_set",
                "horizon_end",
                "total_risk_budget",
                "permission_object_id",
            ],
            "graph_or_path_revision_rewrites_lock": "FORBIDDEN",
            "late_event_or_revision_rewrites_lock": "FORBIDDEN",
        },
        "E_POSITION_LOCK",
        _GRAPH_PATH,
        "dynamic_policy_contract.position_lock_contract",
    )
    _exact(
        dynamic["position_management_risk_contract"],
        {
            "risk_scope": (
                "DECLARED_CONTROLLABLE_WORST_CASE_RISK_NOT_REALIZED_GAP_OR_"
                "SLIPPAGE_LOSS"
            ),
            "risk_unit_must_match": True,
            "risk_after_lte_risk_before": True,
            "absolute_quantity_next_lte_absolute_quantity": True,
            "position_sign_stable_until_exit": True,
            "long_stop_next_gte_long_stop": True,
            "short_stop_next_lte_short_stop": True,
            "horizon_end_may_extend": False,
            "long_target_next_lte_long_target": True,
            "short_target_next_gte_short_target": True,
            "total_risk_components": [
                "REALIZED_LOSS_USED",
                "OPEN_POSITION_WORST_CASE_LOSS",
                "PENDING_ORDER_WORST_CASE_LOSS",
                "FEES_RESERVE",
                "FUNDING_RESERVE",
                "TAIL_RESERVE",
            ],
            "total_risk_used_or_reserved_lte_locked_total_risk_budget": True,
            "KEEP": "SAME_POSITION_SIZE_STOP_TARGET_AND_DECLARED_RISK",
            "TIGHTEN": (
                "NO_SIZE_INCREASE_AND_AT_LEAST_ONE_RISK_BOUND_STRICTLY_TIGHTER"
            ),
            "REDUCE": (
                "ABS_QUANTITY_STRICTLY_DECREASES_AND_DECLARED_RISK_DOES_NOT_INCREASE"
            ),
            "EXIT": (
                "TARGET_POSITION_QUANTITY_ZERO_AND_NEW_DECLARED_POSITION_RISK_ZERO"
            ),
            "increase_position_size": "FORBIDDEN",
            "widen_invalidation_or_stop": "FORBIDDEN",
            "extend_horizon": "FORBIDDEN",
            "move_target_outward": "FORBIDDEN",
            "loss_recovery_or_martingale": "FORBIDDEN",
            "omit_pending_fees_funding_or_tail_reserve": "FORBIDDEN",
            "endpoint_pnl_cannot_hide_intratrajectory_risk_breach": True,
            "market_gap_or_slippage": (
                "RECORD_SEPARATELY_NEVER_RECLASSIFY_AS_PLANNED_RISK_PERMISSION"
            ),
        },
        "E_RISK_MONOTONICITY",
        _GRAPH_PATH,
        "dynamic_policy_contract.position_management_risk_contract",
    )
    _exact(
        dynamic["path_switch_contract"],
        {
            "leading_path_change_auto_reverses_position": False,
            "leading_path_change_auto_creates_opposite_order": False,
            "leading_path_change_auto_adds_or_rescues_position": False,
            "leading_path_change_auto_reenters_after_exit": False,
            "existing_position_management_remains_bound_to_locked_trade_hypothesis": True,
            "opposite_new_risk_requires": [
                "NEW_OPPORTUNITY_ID",
                "NEW_TRADE_HYPOTHESIS_WITH_EXACTLY_ONE_PARENT_PATH",
                "NEW_SEPARATE_PERMISSION_OBJECT",
            ],
            "current_permission_state": "DENIED_P0_1",
        },
        "E_PATH_SWITCH",
        _GRAPH_PATH,
        "dynamic_policy_contract.path_switch_contract",
    )
    _exact(
        dynamic["gap_contract"],
        {
            "gap_or_ambiguous_fill_at_entry": "CENSORED_NO_COUNTERFACTUAL_ENTRY",
            "gap_with_open_counterfactual_position": (
                "RECORD_GAP_TRANSITION_AND_RISK_BREACH_IF_ANY"
            ),
            "gap_event_may_be_labeled_normal_ENTER_or_KEEP": False,
            "favorable_first_same_bar_assumption": "FORBIDDEN",
        },
        "E_REPLAY_CONTRACT",
        _GRAPH_PATH,
        "dynamic_policy_contract.gap_contract",
    )
    _exact(
        dynamic["carrier_contract"],
        {
            "required_carriers": [
                "PolicyEvent",
                "PolicyTrajectory",
                "DecisionReceipt",
                "OrderIntent",
                "PositionStateTransition",
                "PositionLock",
                "RiskEnvelopeSnapshot",
            ],
            "append_only": True,
            "prior_digest_required": True,
            "historical_rewrite": "FORBIDDEN",
            "missing_carrier_disposition": "SUSPEND_ABSTAIN_NO_NEW_RISK",
        },
        "E_DYNAMIC_POLICY",
        _GRAPH_PATH,
        "dynamic_policy_contract.carrier_contract",
    )
    generation = document["generation_contract"]
    _exact_object(
        generation,
        {
            "generator_policy_id",
            "generator_policy_version",
            "input_fields",
            "allowed_refresh_triggers",
            "selection_order",
            "runtime_template_creation",
            "llm_story_injection",
            "cartesian_or_power_set_generation",
            "outcome_conditioned_generation",
            "backdating",
            "prior_revision_rewrite",
            "same_input_same_output",
            "revision_receipt_required",
            "capacity_policy",
        },
        _GRAPH_PATH,
        "generation_contract",
    )
    forbidden_generation = (
        "runtime_template_creation",
        "llm_story_injection",
        "cartesian_or_power_set_generation",
        "outcome_conditioned_generation",
        "backdating",
        "prior_revision_rewrite",
    )
    for field in forbidden_generation:
        _exact(
            generation[field],
            "FORBIDDEN",
            "E_GENERATOR_POLICY",
            _GRAPH_PATH,
            f"generation_contract.{field}",
        )
    for field in ("same_input_same_output", "revision_receipt_required"):
        _exact(
            generation[field],
            True,
            "E_GENERATOR_POLICY",
            _GRAPH_PATH,
            f"generation_contract.{field}",
        )
    _exact(
        generation["generator_policy_id"],
        "GEN-PIT-STATE-CONDITIONED-FINITE-v1_2",
        "E_GENERATOR_POLICY",
        _GRAPH_PATH,
        "generation_contract.generator_policy_id",
    )
    _exact(
        generation["generator_policy_version"],
        "1.0.0",
        "E_GENERATOR_POLICY",
        _GRAPH_PATH,
        "generation_contract.generator_policy_version",
    )
    _exact(
        generation["selection_order"],
        "LEXICOGRAPHIC_TEMPLATE_ID_AFTER_PREDICATE_EVALUATION",
        "E_GENERATOR_POLICY",
        _GRAPH_PATH,
        "generation_contract.selection_order",
    )
    _exact(
        generation["allowed_refresh_triggers"],
        [
            "SCHEDULED_BAR_CLOSE",
            "STATE_CHANGE",
            "STRUCTURAL_POSITION_CHANGE",
            "NEW_ELIGIBLE_EVIDENCE",
            "DATA_QUALITY_CHANGE",
            "PATH_TERMINAL_OR_EXPIRY",
            "POSITION_RISK_CHANGE",
        ],
        "E_GENERATOR_POLICY",
        _GRAPH_PATH,
        "generation_contract.allowed_refresh_triggers",
    )
    required_inputs = {
        "decision_at",
        "state_snapshot_id",
        "state_snapshot_digest",
        "structural_position_id",
        "structural_position_digest",
        "data_quality_snapshot_id",
        "data_quality_snapshot_digest",
        "clock_snapshot_id",
        "clock_snapshot_digest",
        "template_registry_id",
        "template_registry_digest",
        "prior_revision_digest",
        "refresh_trigger",
    }
    if set(generation["input_fields"]) != required_inputs:
        _reject(
            "E_GENERATOR_POLICY",
            _GRAPH_PATH,
            "generation_contract.input_fields",
        )
    _exact(
        generation["capacity_policy"],
        {
            "max_named_market_path_instances": 4,
            "required_outcome_residual": "OTHER_PATH",
            "required_epistemic_meta_node": "UNKNOWN_PATH",
            "overflow_disposition": "POOL_OVERFLOW_UNKNOWN_ABSTAIN",
            "silent_pruning": "FORBIDDEN",
        },
        "E_GENERATOR_POLICY",
        _GRAPH_PATH,
        "generation_contract.capacity_policy",
    )
    identity = document["path_identity_contract"]
    _exact(
        identity,
        {
            "semantic_identity_fields": list(_PATH_IDENTITY_FIELDS),
            "excluded_identity_fields": [
                "mechanism_template_ids",
                "default_trade_side",
                "direction",
                "terminal_scenario_id",
                "natural_language_name",
            ],
            "digest_domain": "msta-hed/runtime-path-semantic-identity/v1_2",
            "exact_duplicate_disposition": (
                "REJECT_DUPLICATE_PATH_SEMANTIC_IDENTITY"
            ),
            "same_side_merge": "FORBIDDEN",
            "same_terminal_scenario_merge": "FORBIDDEN",
            "same_mechanism_merge": "FORBIDDEN",
            "distinct_path_history_merge": "FORBIDDEN",
            "named_terminal_cells_pairwise_disjoint": True,
            "unmatched_observable_outcome": "OTHER_PATH",
        },
        "E_PATH_IDENTITY",
        _GRAPH_PATH,
        "path_identity_contract",
    )
    _exact(
        document["terminal_partition_contract"],
        {
            "partition_observable_id": "OBS-FIRST-UNIQUE-TERMINAL-CELL-ID",
            "candidate_match_requires": [
                "ACTIVE_NONTERMINAL_PATH_INSTANCE",
                "FULL_REQUIRED_PARTIAL_ORDER_SATISFIED",
                "RESOLUTION_PREDICATES_TRUE",
                "HARD_INVALIDATION_FALSE",
                "EXPIRY_FALSE",
                "AVAILABLE_AT_LTE_DECISION_AT",
            ],
            "evaluation_order": (
                "ASCENDING_AVAILABLE_AT_FROM_OPPORTUNITY_START"
            ),
            "named_cell_assignment": (
                "EARLIEST_TIMESTAMP_WITH_EXACTLY_ONE_CANDIDATE_MATCH"
            ),
            "simultaneous_candidate_match_count_gt_one": (
                "OTHER_PATH_AMBIGUOUS_SIMULTANEOUS_TERMINAL_MATCH"
            ),
            "no_named_match_by_master_horizon": "OTHER_PATH",
            "insufficient_observability": (
                "UNKNOWN_PATH_OR_CENSORED_BY_TYPED_REASON"
            ),
            "later_match_after_terminal_assignment": (
                "PRESERVE_AS_EVIDENCE_DO_NOT_RELABEL"
            ),
            "identifier_tie_break": "FORBIDDEN",
            "assignment_receipt_required": True,
            "assignment_rewrite": "FORBIDDEN",
            "machine_proof_rule": (
                "EACH_NAMED_TERMINAL_MATCHER_IS_EQ_SINGLETON_OF_SAME_"
                "PARTITION_OBSERVABLE_AND_SINGLETON_VALUES_ARE_PAIRWISE_DISTINCT"
            ),
        },
        "E_TERMINAL_PARTITION",
        _GRAPH_PATH,
        "terminal_partition_contract",
    )
    residual = document["direction_and_residual_contract"]
    expected_residual = {
        "market_path_directions": [
            "UPWARD",
            "DOWNWARD",
            "BALANCE",
            "DOWNWARD_TAIL",
        ],
        "trade_sides": ["LONG", "SHORT", "NONE"],
        "terminal_scenarios": ["UPSIDE", "DOWNSIDE", "RANGE", "UNRESOLVED"],
        "required_named_direction_coverage": [
            "UPWARD",
            "DOWNWARD",
            "BALANCE",
            "DOWNWARD_TAIL",
        ],
        "OTHER_PATH": {
            "namespace": "MARKET_OUTCOME_RESIDUAL",
            "is_outcome": True,
            "is_probability_eligible_in_future": True,
            "is_tradeable": False,
        },
        "UNKNOWN_PATH": {
            "namespace": "EPISTEMIC_META_NODE",
            "is_outcome": False,
            "is_probability_eligible_in_future": False,
            "is_tradeable": False,
        },
        "CENSORED": {
            "namespace": "RESULT_LABELING_STATE",
            "is_outcome": False,
            "is_probability_eligible_in_future": False,
            "is_tradeable": False,
        },
        "ABSTAIN": {
            "namespace": "ACTION_ONLY",
            "is_outcome": False,
            "is_probability_eligible_in_future": False,
            "is_tradeable": False,
        },
        "ARTIFACT": {
            "namespace": "DATA_QUALITY_ONLY",
            "is_outcome": False,
            "is_probability_eligible_in_future": False,
            "is_tradeable": False,
        },
    }
    _exact(
        residual,
        expected_residual,
        "E_RESIDUAL_SEMANTICS",
        _GRAPH_PATH,
        "direction_and_residual_contract",
    )
    return digest


def _validate_predicate(predicate: Any, index: int) -> tuple[str, dict[str, Any]]:
    field = f"machine_predicates[{index}]"
    item = _exact_object(
        predicate, set(_MACHINE_PREDICATE_FIELDS), _REGISTRY_PATH, field
    )
    predicate_id = _text(item["predicate_id"], _REGISTRY_PATH, f"{field}.predicate_id")
    _text(item["predicate_version"], _REGISTRY_PATH, f"{field}.predicate_version")
    _text(item["observable_id"], _REGISTRY_PATH, f"{field}.observable_id")
    operator = _text(item["operator"], _REGISTRY_PATH, f"{field}.operator")
    if operator not in {"GE", "LE", "GT", "LT", "EQ", "IN", "BETWEEN"}:
        _reject("E_PREDICATE_SHAPE", _REGISTRY_PATH, f"{field}.operator")
    threshold = _exact_object(
        item["threshold_or_interval"],
        {
            "kind",
            "value",
            "lower",
            "upper",
            "values",
            "unit",
            "inclusive_lower",
            "inclusive_upper",
        },
        _REGISTRY_PATH,
        f"{field}.threshold_or_interval",
    )
    kind = threshold["kind"]
    if kind not in {"SCALAR", "INTERVAL", "ENUM_SET"}:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.threshold_or_interval.kind",
        )
    if type(threshold["inclusive_lower"]) is not bool or type(
        threshold["inclusive_upper"]
    ) is not bool:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.threshold_or_interval.inclusive_lower",
        )
    _text(threshold["unit"], _REGISTRY_PATH, f"{field}.threshold_or_interval.unit")
    if type(threshold["values"]) is not list:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.threshold_or_interval.values",
        )
    if kind == "SCALAR":
        if type(threshold["value"]) not in {int, float}:
            _reject(
                "E_PREDICATE_SHAPE",
                _REGISTRY_PATH,
                f"{field}.threshold_or_interval.value",
            )
        if threshold["lower"] is not None or threshold["upper"] is not None:
            _reject(
                "E_PREDICATE_SHAPE",
                _REGISTRY_PATH,
                f"{field}.threshold_or_interval",
            )
    elif kind == "INTERVAL":
        if type(threshold["lower"]) not in {int, float} or type(
            threshold["upper"]
        ) not in {int, float}:
            _reject(
                "E_PREDICATE_SHAPE",
                _REGISTRY_PATH,
                f"{field}.threshold_or_interval",
            )
        if threshold["lower"] > threshold["upper"]:
            _reject(
                "E_PREDICATE_SHAPE",
                _REGISTRY_PATH,
                f"{field}.threshold_or_interval",
            )
    elif not threshold["values"]:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.threshold_or_interval.values",
        )
    clock = _exact_object(
        item["clock"],
        {"timeframe", "source_clock", "available_relation"},
        _REGISTRY_PATH,
        f"{field}.clock",
    )
    for key in clock:
        _text(clock[key], _REGISTRY_PATH, f"{field}.clock.{key}")
    if clock["available_relation"] != "AVAILABLE_AT_LTE_DECISION_AT":
        _reject("E_CLOCK", _REGISTRY_PATH, f"{field}.clock.available_relation")
    window = _exact_object(
        item["window"],
        {"lookback_bars", "confirmation_bars", "max_horizon_bars"},
        _REGISTRY_PATH,
        f"{field}.window",
    )
    for key in window:
        _integer(window[key], _REGISTRY_PATH, f"{field}.window.{key}")
    _integer(
        item["minimum_persistence"],
        _REGISTRY_PATH,
        f"{field}.minimum_persistence",
        minimum=1,
    )
    if item["minimum_persistence"] > max(1, window["confirmation_bars"]):
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.minimum_persistence",
        )
    if item["quality_requirement"] not in {
        "VALID_COMPLETE",
        "VALID_OR_OPTIONAL_UNKNOWN",
    }:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.quality_requirement",
        )
    if item["gap_and_censoring_rule"] not in {
        "GAP_RETURNS_UNKNOWN",
        "GAP_RETURNS_CENSORED",
        "GAP_INVALIDATES_EVENT",
    }:
        _reject(
            "E_PREDICATE_SHAPE",
            _REGISTRY_PATH,
            f"{field}.gap_and_censoring_rule",
        )
    terminal = item["terminal_reason"]
    precedence = _integer(
        item["precedence"], _REGISTRY_PATH, f"{field}.precedence"
    )
    expected_precedence = {
        "HARD_INVALIDATION": 0,
        "TRADE_INVALIDATION": 0,
        "EXPIRY": 1,
        "RESOLUTION": 2,
        "NONE": 10,
    }
    if terminal not in expected_precedence or precedence != expected_precedence[terminal]:
        _reject(
            "E_PREDICATE_TERMINAL",
            _REGISTRY_PATH,
            f"{field}.terminal_reason",
        )
    return predicate_id, item


def _predicate_references(
    template: dict[str, Any], fields: tuple[str, ...], template_field: str
) -> set[str]:
    references: set[str] = set()
    for name in fields:
        values = _list(
            template[name], _REGISTRY_PATH, f"{template_field}.{name}"
        )
        for index, value in enumerate(values):
            references.add(
                _text(value, _REGISTRY_PATH, f"{template_field}.{name}[{index}]")
            )
    return references


def _validate_terminal_references(
    template: dict[str, Any],
    predicate_by_id: dict[str, dict[str, Any]],
    template_field: str,
) -> None:
    expected = {
        "hard_invalidation_predicate_ids": {"HARD_INVALIDATION"},
        "trade_invalidation_predicate_ids": {
            "HARD_INVALIDATION",
            "TRADE_INVALIDATION",
        },
        "resolution_predicate_ids": {"RESOLUTION"},
        "expiry_predicate_ids": {"EXPIRY"},
    }
    for name, terminal_reasons in expected.items():
        if name not in template:
            continue
        for predicate_id in template[name]:
            predicate = predicate_by_id.get(predicate_id)
            if (
                predicate is None
                or predicate["terminal_reason"] not in terminal_reasons
            ):
                _reject(
                    "E_PREDICATE_TERMINAL",
                    _REGISTRY_PATH,
                    f"{template_field}.{name}",
                )


def _validate_registry(
    document: dict[str, Any],
) -> tuple[str, dict[str, dict[str, Any]], dict[str, set[str]]]:
    digest = _validate_common(
        document,
        _REGISTRY_PATH,
        _REGISTRY_TOP_KEYS,
        {
            "registry_id": "MSTA_HED_RUNTIME_HYPOTHESIS_TEMPLATE_REGISTRY.v1_2",
            "schema_version": (
                "research-system-runtime-hypothesis-template-registry.v1_2"
            ),
            "status": "E0_P0_1_CANDIDATE_NOT_ACCEPTED",
            "evidence_level": (
                "E0_STATIC_AND_SYNTHETIC_TEMPLATE_CONTRACT_ONLY"
            ),
        },
        _REGISTRY_AUTHORITY,
        _REGISTRY_CLAIM_BOUNDARY,
    )
    _exact(
        document["required_machine_predicate_shape"],
        list(_MACHINE_PREDICATE_FIELDS),
        "E_PREDICATE_SHAPE",
        _REGISTRY_PATH,
        "required_machine_predicate_shape",
    )
    _exact(
        document["enum_registry"],
        {
            "template_statuses": ["ACTIVE_E0_TEMPLATE"],
            "predicate_operators": ["GE", "LE", "GT", "LT", "EQ", "IN", "BETWEEN"],
            "predicate_kinds": ["SCALAR", "INTERVAL", "ENUM_SET"],
            "quality_requirements": [
                "VALID_COMPLETE",
                "VALID_OR_OPTIONAL_UNKNOWN",
            ],
            "gap_rules": [
                "GAP_RETURNS_UNKNOWN",
                "GAP_RETURNS_CENSORED",
                "GAP_INVALIDATES_EVENT",
            ],
            "terminal_reasons": [
                "NONE",
                "HARD_INVALIDATION",
                "RESOLUTION",
                "EXPIRY",
                "TRADE_INVALIDATION",
            ],
            "path_directions": [
                "UPWARD",
                "DOWNWARD",
                "BALANCE",
                "DOWNWARD_TAIL",
            ],
            "trade_sides": ["LONG", "SHORT", "NONE"],
            "terminal_scenarios": ["UPSIDE", "DOWNSIDE", "RANGE", "UNRESOLVED"],
        },
        "E_TEMPLATE_INJECTION",
        _REGISTRY_PATH,
        "enum_registry",
    )
    invariants = {
        "finite_registry": True,
        "runtime_or_llm_template_injection": "FORBIDDEN",
        "outcome_conditioned_template_selection": "FORBIDDEN",
        "all_active_templates_bind_fixture_set": True,
        "path_identity_excludes_mechanism_and_side": True,
        "same_side_paths_remain_distinct": True,
        "duplicate_path_semantic_identity": "REJECT",
        "named_terminal_cell_ids_unique": True,
        "mechanism_path_transfer": "NO_SCORE_TRANSFER",
        "trade_exact_parent_count": 1,
        "multi_path_composite_trade": "DEFERRED",
        "permission_state": "DENIED_P0_1",
        "max_risk": 0,
    }
    _exact(
        document["template_invariants"],
        invariants,
        "E_TEMPLATE_INJECTION",
        _REGISTRY_PATH,
        "template_invariants",
    )
    predicates = _list(
        document["machine_predicates"],
        _REGISTRY_PATH,
        "machine_predicates",
        nonempty=True,
    )
    predicate_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_predicate in enumerate(predicates):
        predicate_id, predicate = _validate_predicate(raw_predicate, index)
        if predicate_id in predicate_by_id:
            _reject(
                "E_PREDICATE_SHAPE",
                _REGISTRY_PATH,
                f"machine_predicates[{index}].predicate_id",
            )
        predicate_by_id[predicate_id] = predicate
    if frozenset(predicate_by_id) != _PREDICATE_IDS:
        _reject("E_TEMPLATE_INJECTION", _REGISTRY_PATH, "machine_predicates")

    template_references: dict[str, set[str]] = {}
    template_sets: dict[str, dict[str, Any]] = {}
    template_specs = (
        (
            "mechanism_templates",
            "mechanism_template_id",
            _MECHANISM_IDS,
            _MECHANISM_KEYS,
            (
                "activation_predicate_ids",
                "support_predicate_ids",
                "soft_contradiction_predicate_ids",
                "hard_invalidation_predicate_ids",
                "expiry_predicate_ids",
            ),
        ),
        (
            "path_templates",
            "path_template_id",
            _PATH_IDS,
            _PATH_KEYS,
            (
                "activation_predicate_ids",
                "support_predicate_ids",
                "soft_contradiction_predicate_ids",
                "hard_invalidation_predicate_ids",
                "resolution_predicate_ids",
                "expiry_predicate_ids",
                "terminal_matcher_predicate_ids",
            ),
        ),
        (
            "trade_templates",
            "trade_template_id",
            _TRADE_IDS,
            _TRADE_KEYS,
            (
                "activation_predicate_ids",
                "trade_trigger_predicate_ids",
                "trade_invalidation_predicate_ids",
                "expiry_predicate_ids",
            ),
        ),
    )
    for collection_name, id_field, allowed_ids, keys, ref_fields in template_specs:
        values = _list(
            document[collection_name],
            _REGISTRY_PATH,
            collection_name,
            nonempty=True,
        )
        by_id: dict[str, dict[str, Any]] = {}
        for index, raw_template in enumerate(values):
            field = f"{collection_name}[{index}]"
            template = _exact_object(raw_template, keys, _REGISTRY_PATH, field)
            template_id = _text(template[id_field], _REGISTRY_PATH, f"{field}.{id_field}")
            if template_id in by_id:
                _reject("E_TEMPLATE_INJECTION", _REGISTRY_PATH, f"{field}.{id_field}")
            if template["status"] != "ACTIVE_E0_TEMPLATE":
                _reject("E_TEMPLATE_INJECTION", _REGISTRY_PATH, f"{field}.status")
            references = _predicate_references(template, ref_fields, field)
            if not references <= set(predicate_by_id):
                _reject("E_PREDICATE_REFERENCE", _REGISTRY_PATH, field)
            _validate_terminal_references(template, predicate_by_id, field)
            if collection_name == "mechanism_templates":
                if (
                    template["identifiability_class_id"]
                    != _MECHANISM_PRIMARY_CLASS.get(template_id)
                    or not template["truth_status"].startswith(
                        "OBSERVATIONAL_CANDIDATE_NOT_"
                    )
                ):
                    _reject("E_IDENTIFIABILITY", _REGISTRY_PATH, field)
            fixture_set_id = _text(
                template["fixture_set_id"], _REGISTRY_PATH, f"{field}.fixture_set_id"
            )
            if fixture_set_id not in _FIXTURE_IDS:
                _reject("E_FIXTURE_BINDING", _REGISTRY_PATH, f"{field}.fixture_set_id")
            by_id[template_id] = template
            template_references[template_id] = references
            template_sets[template_id] = template
        if frozenset(by_id) != allowed_ids:
            _reject("E_TEMPLATE_INJECTION", _REGISTRY_PATH, collection_name)

    paths = {
        template_id: template_sets[template_id]
        for template_id in sorted(_PATH_IDS)
    }
    path_identity_digests: set[str] = set()
    terminal_cells: set[str] = set()
    terminal_matcher_sets: list[set[str]] = []
    terminal_matcher_values: set[str] = set()
    directions: set[str] = set()
    for template_id, path_template in paths.items():
        if tuple(path_template["identity_fields"]) != _PATH_IDENTITY_FIELDS:
            _reject(
                "E_PATH_IDENTITY",
                _REGISTRY_PATH,
                f"path_templates.{template_id}.identity_fields",
            )
        identity = {
            field: path_template[field] for field in _PATH_IDENTITY_FIELDS
        }
        calculated = hashlib.sha256(
            b"msta-hed/runtime-path-semantic-identity/v1_2\0"
            + _canonical_bytes(identity)
        ).hexdigest()
        supplied = _sha(
            path_template["path_identity_digest"],
            _REGISTRY_PATH,
            f"path_templates.{template_id}.path_identity_digest",
        )
        if calculated != supplied:
            _reject(
                "E_PATH_IDENTITY",
                _REGISTRY_PATH,
                f"path_templates.{template_id}.path_identity_digest",
            )
        if supplied in path_identity_digests:
            _reject("E_DUPLICATE_PATH", _REGISTRY_PATH, "path_templates")
        path_identity_digests.add(supplied)
        terminal_cell = _text(
            path_template["terminal_cell_id"],
            _REGISTRY_PATH,
            f"path_templates.{template_id}.terminal_cell_id",
        )
        if terminal_cell in terminal_cells:
            _reject("E_TERMINAL_PARTITION", _REGISTRY_PATH, "path_templates")
        terminal_cells.add(terminal_cell)
        matcher_set = set(path_template["terminal_matcher_predicate_ids"])
        if (
            len(matcher_set) != 1
            or any(matcher_set & previous for previous in terminal_matcher_sets)
        ):
            _reject("E_TERMINAL_PARTITION", _REGISTRY_PATH, "path_templates")
        terminal_matcher_sets.append(matcher_set)
        matcher = predicate_by_id[next(iter(matcher_set))]
        matcher_threshold = matcher["threshold_or_interval"]
        matcher_values = matcher_threshold["values"]
        if (
            matcher["observable_id"] != "OBS-FIRST-UNIQUE-TERMINAL-CELL-ID"
            or matcher["operator"] != "EQ"
            or matcher_threshold["kind"] != "ENUM_SET"
            or len(matcher_values) != 1
            or matcher_values[0] != terminal_cell
            or matcher_values[0] in terminal_matcher_values
            or matcher["terminal_reason"] != "RESOLUTION"
        ):
            _reject(
                "E_TERMINAL_PARTITION",
                _REGISTRY_PATH,
                f"path_templates.{template_id}.terminal_matcher_predicate_ids",
            )
        terminal_matcher_values.add(matcher_values[0])
        directions.add(path_template["direction"])
        scenario_direction_side = {
            "UPSIDE": ("UPWARD", "LONG"),
            "DOWNSIDE": ({"DOWNWARD", "DOWNWARD_TAIL"}, "SHORT"),
            "RANGE": ("BALANCE", "NONE"),
        }
        scenario = path_template["terminal_scenario_id"]
        if scenario not in scenario_direction_side:
            _reject(
                "E_DIRECTION_COVERAGE",
                _REGISTRY_PATH,
                f"path_templates.{template_id}.terminal_scenario_id",
            )
        allowed_direction, expected_side = scenario_direction_side[scenario]
        direction_ok = (
            path_template["direction"] in allowed_direction
            if type(allowed_direction) is set
            else path_template["direction"] == allowed_direction
        )
        if not direction_ok or path_template["default_trade_side"] != expected_side:
            _reject(
                "E_DIRECTION_COVERAGE",
                _REGISTRY_PATH,
                f"path_templates.{template_id}",
            )
        milestones = set(path_template["partial_order_milestones"])
        for edge_name in (
            "required_partial_order_edges",
            "optional_partial_order_edges",
        ):
            for edge in path_template[edge_name]:
                if (
                    type(edge) is not list
                    or len(edge) != 2
                    or any(type(node) is not str for node in edge)
                    or not set(edge) <= milestones
                    or edge[0] == edge[1]
                ):
                    _reject(
                        "E_PATH_IDENTITY",
                        _REGISTRY_PATH,
                        f"path_templates.{template_id}.{edge_name}",
                    )
        if not set(path_template["repeatable_milestones"]) <= milestones:
            _reject("E_PATH_IDENTITY", _REGISTRY_PATH, "path_templates")
        if not set(path_template["skippable_milestones"]) <= milestones:
            _reject("E_PATH_IDENTITY", _REGISTRY_PATH, "path_templates")
    if directions != {"UPWARD", "DOWNWARD", "BALANCE", "DOWNWARD_TAIL"}:
        _reject("E_DIRECTION_COVERAGE", _REGISTRY_PATH, "path_templates")
    short_paths = [
        item
        for item in paths.values()
        if item["default_trade_side"] == "SHORT"
    ]
    if len(short_paths) < 2 or len(
        {item["path_identity_digest"] for item in short_paths}
    ) != len(short_paths):
        _reject("E_DUPLICATE_PATH", _REGISTRY_PATH, "path_templates")

    topology_edges = _list(
        document["topology_edges"],
        _REGISTRY_PATH,
        "topology_edges",
        nonempty=True,
    )
    edge_ids: set[str] = set()
    path_parent_edges: dict[str, list[str]] = {trade_id: [] for trade_id in _TRADE_IDS}
    mechanism_paths: dict[str, set[str]] = {
        mechanism_id: set() for mechanism_id in _MECHANISM_IDS
    }
    path_mechanisms: dict[str, set[str]] = {path_id: set() for path_id in _PATH_IDS}
    for index, raw_edge in enumerate(topology_edges):
        field = f"topology_edges[{index}]"
        edge = _exact_object(
            raw_edge,
            {
                "edge_template_id",
                "edge_type",
                "from_template_id",
                "to_template_id",
                "transfer_mode",
                "edge_role",
            },
            _REGISTRY_PATH,
            field,
        )
        edge_id = _text(
            edge["edge_template_id"], _REGISTRY_PATH, f"{field}.edge_template_id"
        )
        if edge_id in edge_ids:
            _reject("E_TOPOLOGY", _REGISTRY_PATH, f"{field}.edge_template_id")
        edge_ids.add(edge_id)
        if edge["edge_type"] == "MECHANISM_TO_PATH":
            if (
                edge["from_template_id"] not in _MECHANISM_IDS
                or edge["to_template_id"] not in _PATH_IDS
                or edge["transfer_mode"] != "NO_SCORE_TRANSFER"
                or edge["edge_role"] != "COMPATIBLE_EXPLANATION"
            ):
                _reject("E_MECHANISM_TRANSFER", _REGISTRY_PATH, field)
            mechanism_paths[edge["from_template_id"]].add(edge["to_template_id"])
            path_mechanisms[edge["to_template_id"]].add(edge["from_template_id"])
        elif edge["edge_type"] == "PATH_TO_TRADE":
            if (
                edge["from_template_id"] not in _PATH_IDS
                or edge["to_template_id"] not in _TRADE_IDS
                or edge["transfer_mode"]
                != "PARENT_IDENTITY_ONLY_NO_SCORE_TRANSFER"
                or edge["edge_role"] != "EXACT_PARENT"
            ):
                _reject("E_TRADE_PARENT", _REGISTRY_PATH, field)
            path_parent_edges[edge["to_template_id"]].append(
                edge["from_template_id"]
            )
        else:
            _reject("E_TOPOLOGY", _REGISTRY_PATH, f"{field}.edge_type")
    if not any(len(paths_for_mechanism) > 1 for paths_for_mechanism in mechanism_paths.values()):
        _reject("E_TOPOLOGY", _REGISTRY_PATH, "topology_edges")
    if not any(len(mechanisms) > 1 for mechanisms in path_mechanisms.values()):
        _reject("E_TOPOLOGY", _REGISTRY_PATH, "topology_edges")

    for trade_id in sorted(_TRADE_IDS):
        trade = template_sets[trade_id]
        parent = trade["parent_path_template_id"]
        if (
            parent not in _PATH_IDS
            or path_parent_edges[trade_id] != [parent]
            or trade["side"] != paths[parent]["default_trade_side"]
        ):
            _reject("E_TRADE_PARENT", _REGISTRY_PATH, f"trade_templates.{trade_id}")
        if trade["mechanism_context_effect"] != "NONE":
            _reject(
                "E_MECHANISM_TRANSFER",
                _REGISTRY_PATH,
                f"trade_templates.{trade_id}.mechanism_context_effect",
            )
        if (
            trade["permission_requirement"]
            != "SEPARATE_PERMISSION_OBJECT_REQUIRED"
            or trade["permission_state"] != "DENIED_P0_1"
            or type(trade["max_risk"]) is not int
            or trade["max_risk"] != 0
        ):
            _reject(
                "E_PERMISSION_ESCALATION",
                _REGISTRY_PATH,
                f"trade_templates.{trade_id}",
            )
        if not set(trade["mechanism_context_template_ids"]) <= _MECHANISM_IDS:
            _reject(
                "E_MECHANISM_TRANSFER",
                _REGISTRY_PATH,
                f"trade_templates.{trade_id}.mechanism_context_template_ids",
            )

    crosswalk = _list(
        document["shock_crosswalk"],
        _REGISTRY_PATH,
        "shock_crosswalk",
        nonempty=True,
    )
    if {item.get("path_template_id") for item in crosswalk} != _PATH_IDS:
        _reject("E_DIRECTION_COVERAGE", _REGISTRY_PATH, "shock_crosswalk")
    for index, item in enumerate(crosswalk):
        field = f"shock_crosswalk[{index}]"
        record = _exact_object(
            item,
            {
                "source_research_hypothesis_id",
                "path_template_id",
                "terminal_scenario_id",
                "direction",
                "default_trade_side",
            },
            _REGISTRY_PATH,
            field,
        )
        path_template = paths[record["path_template_id"]]
        for key in (
            "source_research_hypothesis_id",
            "terminal_scenario_id",
            "direction",
            "default_trade_side",
        ):
            if record[key] != path_template[key]:
                _reject("E_DIRECTION_COVERAGE", _REGISTRY_PATH, f"{field}.{key}")

    bindings = _list(
        document["fixture_bindings"],
        _REGISTRY_PATH,
        "fixture_bindings",
        nonempty=True,
    )
    binding_by_template: dict[str, str] = {}
    for index, item in enumerate(bindings):
        field = f"fixture_bindings[{index}]"
        binding = _exact_object(
            item,
            {
                "template_kind",
                "template_id",
                "fixture_set_id",
                "required_case_kinds",
            },
            _REGISTRY_PATH,
            field,
        )
        template_id = binding["template_id"]
        if template_id not in template_sets or template_id in binding_by_template:
            _reject("E_FIXTURE_BINDING", _REGISTRY_PATH, f"{field}.template_id")
        if set(binding["required_case_kinds"]) != _REQUIRED_CASE_KINDS:
            _reject(
                "E_FIXTURE_BINDING",
                _REGISTRY_PATH,
                f"{field}.required_case_kinds",
            )
        expected_kind, expected_fixture_id = _FIXTURE_BY_TEMPLATE[template_id]
        if (
            binding["template_kind"] != expected_kind
            or binding["fixture_set_id"] != expected_fixture_id
            or binding["fixture_set_id"]
            != template_sets[template_id]["fixture_set_id"]
        ):
            _reject(
                "E_FIXTURE_BINDING",
                _REGISTRY_PATH,
                f"{field}.fixture_set_id",
            )
        binding_by_template[template_id] = binding["fixture_set_id"]
    if set(binding_by_template) != set(template_sets):
        _reject("E_FIXTURE_BINDING", _REGISTRY_PATH, "fixture_bindings")
    return digest, predicate_by_id, template_references


def _predicate_result(
    predicate: dict[str, Any],
    observed_value: Any,
    available_at: datetime,
    decision_at: datetime,
    has_gap: bool,
) -> str:
    if available_at > decision_at:
        return "UNKNOWN_FUTURE"
    if has_gap:
        if predicate["gap_and_censoring_rule"] == "GAP_RETURNS_CENSORED":
            return "CENSORED_GAP"
        return "UNKNOWN_GAP"
    threshold = predicate["threshold_or_interval"]
    operator = predicate["operator"]
    try:
        if operator == "GE":
            passed = observed_value >= threshold["value"]
        elif operator == "LE":
            passed = observed_value <= threshold["value"]
        elif operator == "GT":
            passed = observed_value > threshold["value"]
        elif operator == "LT":
            passed = observed_value < threshold["value"]
        elif operator in {"EQ", "IN"}:
            passed = observed_value in threshold["values"]
        elif operator == "BETWEEN":
            lower_ok = (
                observed_value >= threshold["lower"]
                if threshold["inclusive_lower"]
                else observed_value > threshold["lower"]
            )
            upper_ok = (
                observed_value <= threshold["upper"]
                if threshold["inclusive_upper"]
                else observed_value < threshold["upper"]
            )
            passed = lower_ok and upper_ok
        else:
            return "UNKNOWN_GAP"
    except (TypeError, ValueError):
        return "UNKNOWN_GAP"
    return "TRUE" if passed else "FALSE"


def _validate_evidence(
    document: dict[str, Any],
    predicate_by_id: dict[str, dict[str, Any]],
    template_references: dict[str, set[str]],
) -> str:
    digest = _validate_common(
        document,
        _EVIDENCE_PATH,
        _EVIDENCE_TOP_KEYS,
        {
            "contract_id": "MSTA_HED_RUNTIME_EVIDENCE_EVALUATION_CONTRACT.v1_2",
            "schema_version": (
                "research-system-runtime-evidence-evaluation-contract.v1_2"
            ),
            "status": "E0_P0_1_CANDIDATE_NOT_ACCEPTED",
            "evidence_level": (
                "E0_STATIC_AND_SYNTHETIC_EVIDENCE_CONTRACT_ONLY"
            ),
        },
        _EVIDENCE_AUTHORITY,
        _EVIDENCE_CLAIM_BOUNDARY,
    )
    _exact(
        document["evidence_item_schema"],
        [
            "evidence_id",
            "source_or_measurement_id",
            "available_at",
            "quality",
            "lineage_root_id",
            "dependency_group_id",
            "expiry_at",
            "target_effects",
            "evidence_digest",
        ],
        "E_SCHEMA",
        _EVIDENCE_PATH,
        "evidence_item_schema",
    )
    _exact(
        document["target_effect_schema"],
        [
            "target_instance_id",
            "target_kind",
            "effect_kind",
            "ordinal_delta",
            "predicate_id",
            "effective_at",
        ],
        "E_SCHEMA",
        _EVIDENCE_PATH,
        "target_effect_schema",
    )
    required_update_fields = {
        "receipt_id",
        "opportunity_id",
        "graph_revision_id",
        "decision_at",
        "target_instance_id",
        "target_kind",
        "prior_target_digest",
        "accepted_evidence_ids",
        "rejected_evidence_with_reasons",
        "applied_atomic_effects",
        "material_conflicts",
        "status_before",
        "status_after",
        "ordinal_support_before",
        "ordinal_support_after",
        "terminal_reason",
        "new_target_digest",
        "previous_receipt_digest",
        "receipt_digest",
    }
    if set(document["update_receipt_schema"]) != required_update_fields:
        _reject("E_SCHEMA", _EVIDENCE_PATH, "update_receipt_schema")
    semantics = document["evidence_semantics"]
    required_semantics = {
        "target_kinds": ["MHI", "PHI", "THI"],
        "effect_kinds": [
            "SUPPORT",
            "SOFT_CONTRADICTION",
            "HARD_INVALIDATION",
            "NO_EFFECT",
        ],
        "quality_values": [
            "VALID_COMPLETE",
            "VALID_OPTIONAL_UNKNOWN",
            "STALE",
            "GAP",
            "CONFLICT",
            "DATA_INVALID",
            "UNKNOWN",
        ],
        "ordinal_delta_domain": [-2, -1, 0, 1, 2],
        "atomic_per_target": True,
        "one_lineage_per_target_update": True,
        "copied_alias_independent_support": False,
        "dependency_group_aliasing": "REJECT_DUPLICATE_LINEAGE",
        "future_available_at": "REJECT_UNKNOWN_NO_UPDATE",
        "expired_evidence": "REJECT_EXPIRED_NO_UPDATE",
        "invalid_quality": "REJECT_UNKNOWN_NO_UPDATE",
        "hard_invalidation_precedence": 0,
        "hard_invalidation_dominates_ordinal": True,
        "terminal_revival": "FORBIDDEN",
        "expiry_extension": "FORBIDDEN",
        "cross_target_implicit_effect": "FORBIDDEN",
        "mechanism_to_path_score_transfer": "FORBIDDEN",
        "idempotent_exact_replay": True,
        "receipt_chain_append_only_within_supplied_prefix": True,
        "runtime_raw_lineage_claim": "NOT_ESTABLISHED_AT_P0_1",
    }
    _exact(
        semantics,
        required_semantics,
        "E_EVIDENCE_SEMANTICS",
        _EVIDENCE_PATH,
        "evidence_semantics",
    )
    _exact(
        document["conflict_contract"],
        {
            "conflict_id_fields": [
                "target_instance_id",
                "dependency_group_id",
                "absolute_strength",
                "effective_at",
            ],
            "equal_opposing_effect_disposition": "MATERIAL_CONFLICT_UNKNOWN",
            "identifier_tie_break_as_semantic_winner": "FORBIDDEN",
            "conflict_remains_visible": True,
            "conflict_cannot_authorize_trade": True,
            "conflict_cannot_be_removed_by_score": True,
        },
        "E_CONFLICT_SEMANTICS",
        _EVIDENCE_PATH,
        "conflict_contract",
    )

    classes = _list(
        document["mechanism_identifiability_classes"],
        _EVIDENCE_PATH,
        "mechanism_identifiability_classes",
        nonempty=True,
    )
    class_ids: set[str] = set()
    covered_mechanisms: set[str] = set()
    for index, item in enumerate(classes):
        field = f"mechanism_identifiability_classes[{index}]"
        item = _exact_object(
            item,
            {
                "identifiability_class_id",
                "mechanism_template_ids",
                "status",
                "unique_causal_choice",
                "truth_label",
            },
            _EVIDENCE_PATH,
            field,
        )
        class_id = item["identifiability_class_id"]
        if class_id in class_ids:
            _reject("E_IDENTIFIABILITY", _EVIDENCE_PATH, field)
        class_ids.add(class_id)
        mechanisms = set(item["mechanism_template_ids"])
        if not mechanisms or not mechanisms <= _MECHANISM_IDS:
            _reject("E_IDENTIFIABILITY", _EVIDENCE_PATH, field)
        covered_mechanisms |= mechanisms
        if (
            item["unique_causal_choice"] != "FORBIDDEN"
            or item["truth_label"] != "NONE"
            or "IDENTIFIABLE_CAUSAL_TRUTH" in item["status"]
        ):
            _reject("E_IDENTIFIABILITY", _EVIDENCE_PATH, field)
    if frozenset(class_ids) != _IDENTIFIABILITY_IDS or covered_mechanisms != _MECHANISM_IDS:
        _reject(
            "E_IDENTIFIABILITY",
            _EVIDENCE_PATH,
            "mechanism_identifiability_classes",
        )

    discrimination = _list(
        document["path_discrimination_contracts"],
        _EVIDENCE_PATH,
        "path_discrimination_contracts",
        nonempty=True,
    )
    required_pairs = {frozenset(pair) for pair in combinations(sorted(_PATH_IDS), 2)}
    seen_pairs: set[frozenset[str]] = set()
    plan_for_pair: dict[frozenset[str], str] = {}
    for index, item in enumerate(discrimination):
        field = f"path_discrimination_contracts[{index}]"
        item = _exact_object(
            item,
            {
                "discriminator_id",
                "path_a_id",
                "path_b_id",
                "terminal_identifiable",
                "decision_identifiable",
                "predicate_ids_for_a",
                "predicate_ids_for_b",
                "deadline_rule",
                "next_observation_plan_id",
                "unavailable_disposition",
            },
            _EVIDENCE_PATH,
            field,
        )
        pair = frozenset({item["path_a_id"], item["path_b_id"]})
        if (
            len(pair) != 2
            or not pair <= _PATH_IDS
            or pair in seen_pairs
            or item["terminal_identifiable"] is not True
            or item["decision_identifiable"] is not True
            or item["deadline_rule"] != "BEFORE_MIN_PATH_EXPIRY"
            or item["unavailable_disposition"]
            != "UNKNOWN_NOT_DECISION_IDENTIFIABLE"
        ):
            _reject("E_PATH_DISCRIMINATION", _EVIDENCE_PATH, field)
        for side_field in ("predicate_ids_for_a", "predicate_ids_for_b"):
            predicates = set(item[side_field])
            if not predicates or not predicates <= set(predicate_by_id):
                _reject(
                    "E_PATH_DISCRIMINATION",
                    _EVIDENCE_PATH,
                    f"{field}.{side_field}",
                )
        seen_pairs.add(pair)
        plan_for_pair[pair] = item["next_observation_plan_id"]
    if seen_pairs != required_pairs:
        _reject(
            "E_PATH_DISCRIMINATION",
            _EVIDENCE_PATH,
            "path_discrimination_contracts",
        )

    plans = _list(
        document["next_observation_plans"],
        _EVIDENCE_PATH,
        "next_observation_plans",
        nonempty=True,
    )
    seen_plans: set[str] = set()
    for index, item in enumerate(plans):
        field = f"next_observation_plans[{index}]"
        item = _exact_object(
            item,
            {
                "plan_id",
                "unresolved_path_ids",
                "ranked_predicate_ids",
                "ranking_mode",
                "numeric_information_gain",
                "deadline_rule",
            },
            _EVIDENCE_PATH,
            field,
        )
        plan_id = item["plan_id"]
        pair = frozenset(item["unresolved_path_ids"])
        if (
            plan_id in seen_plans
            or plan_for_pair.get(pair) != plan_id
            or item["ranking_mode"] != "DETERMINISTIC_ORDINAL"
            or item["numeric_information_gain"] != "FORBIDDEN_UNCALIBRATED"
            or item["deadline_rule"] != "BEFORE_MIN_PATH_EXPIRY"
            or not item["ranked_predicate_ids"]
            or not set(item["ranked_predicate_ids"]) <= set(predicate_by_id)
        ):
            _reject("E_NEXT_OBSERVATION", _EVIDENCE_PATH, field)
        seen_plans.add(plan_id)
    if frozenset(seen_plans) != _PLAN_IDS:
        _reject("E_NEXT_OBSERVATION", _EVIDENCE_PATH, "next_observation_plans")

    _exact(
        document["event_driven_pit_replay_contract"],
        {
            "contract_id": "MSTA_HED_EVENT_DRIVEN_PIT_REPLAY_INTERFACE.v1_2",
            "status": "E0_INTERFACE_ONLY_NOT_IMPLEMENTED_NOT_AUTHORIZED",
            "policy_event_order": [
                "available_at_ASC",
                "source_sequence_ASC",
                "event_id_ASC",
            ],
            "admission_requires_available_at_lte_decision_at": True,
            "full_bar_backfill_into_earlier_decision": "FORBIDDEN",
            "future_high_low_close_mfe_or_mae_in_policy_information_set": (
                "FORBIDDEN"
            ),
            "unclosed_higher_timeframe_bar": "NOT_ADMITTED_AS_CLOSED_BAR",
            "late_source_revision": (
                "NEW_POLICY_EVENT_NEVER_OVERWRITE_PRIOR_EVENT_OR_RECEIPT"
            ),
            "same_bar_or_same_timestamp_barrier_order_unknown": (
                "CENSORED_AMBIGUOUS_NO_FAVORABLE_FIRST"
            ),
            "duplicate_event": (
                "IDEMPOTENT_NO_SECOND_STATE_CHANGE_RECEIPT_OR_EFFECT"
            ),
            "transition_function_contract": (
                "MSTA_HED_DYNAMIC_POLICY_TRAJECTORY.v1_2"
            ),
            "event_update_chain": [
                "POLICY_EVENT",
                "POINT_IN_TIME_INFORMATION_SET",
                "STATE_SNAPSHOT",
                "GRAPH_REVISION_OR_NO_CHANGE_RECEIPT",
                "TRADE_HYPOTHESIS_REVISION_OR_NO_CHANGE_RECEIPT",
                "POLICY_ACTION",
                "DECISION_RECEIPT",
                "ORDER_INTENT_OR_POSITION_TRANSITION_IF_APPLICABLE",
            ],
            "outcome_conditioned_policy_revision": "FORBIDDEN",
            "graph_or_position_lock_rewrite": "FORBIDDEN",
            "runtime_or_replay_engine": "NOT_IMPLEMENTED",
            "backtest_execution": "NOT_AUTHORIZED",
            "e2_proxy_or_synthetic_result_is_execution_proof": False,
        },
        "E_REPLAY_CONTRACT",
        _EVIDENCE_PATH,
        "event_driven_pit_replay_contract",
    )
    _exact(
        document["policy_trajectory_evaluation_contract"],
        {
            "contract_id": (
                "MSTA_HED_POLICY_TRAJECTORY_EVALUATION_INTERFACE.v1_2"
            ),
            "status": "E0_INTERFACE_ONLY_THRESHOLDS_UNSET_NOT_EXECUTED",
            "candidate_policy": "DYNAMIC_HYPOTHESIS_POLICY",
            "required_baselines": [
                {
                    "baseline_id": "FROZEN_ENTRY_STATIC_EXIT",
                    "interface_semantics": (
                        "ENTRY_DECISION_FROZEN_AT_ELIGIBILITY_AND_STOP_TARGET_"
                        "HORIZON_NOT_DYNAMICALLY_REVISED"
                    ),
                    "exact_parameters": "UNSET_BLOCKS_E2",
                },
                {
                    "baseline_id": "SINGLE_PATH",
                    "interface_semantics": (
                        "ONE_PREREGISTERED_PATH_ONLY_WITHOUT_PATH_SWITCH"
                    ),
                    "exact_parameters": "UNSET_BLOCKS_E2",
                },
                {
                    "baseline_id": "NO_TRADE",
                    "interface_semantics": (
                        "ALWAYS_ABSTAIN_ZERO_MARKET_EXPOSURE"
                    ),
                    "exact_parameters": "UNSET_BLOCKS_E2",
                },
            ],
            "comparison_fairness": {
                "same_policy_events": True,
                "same_point_in_time_information": True,
                "same_opportunity_denominator": True,
                "same_permission_and_risk_budget": True,
                "same_fee_funding_slippage_and_fill_model": True,
                "same_barrier_ambiguity_rule": True,
                "unequal_information_or_cost_advantage": "FORBIDDEN",
            },
            "required_trajectory_metrics": [
                "PATH_REVISION_COUNT",
                "PATH_LEADER_SWITCH_COUNT",
                "GRAPH_REVISION_LATENCY",
                "DECISION_LATENCY",
                "ENTRY_INTENT_COUNT",
                "CANCEL_INTENT_COUNT",
                "REPLACE_INTENT_COUNT",
                "FILL_AND_PARTIAL_FILL_STATE",
                "STOP_REVISION_COUNT",
                "TARGET_REVISION_COUNT",
                "HORIZON_REVISION_COUNT",
                "MFE",
                "MAE",
                "FEES",
                "SLIPPAGE",
                "FUNDING",
                "TAIL_LOSS",
                "INTRATRAJECTORY_RISK_BREACH_COUNT",
                "ABSTAIN_RATE",
                "COVERAGE",
                "UNKNOWN_RATE",
                "CENSORED_RATE",
            ],
            "metric_thresholds": {
                "path_revision_and_switch": "UNSET_BLOCKS_E2",
                "latency": "UNSET_BLOCKS_E2",
                "entry_cancel_replace_fill": "UNSET_BLOCKS_E2",
                "stop_target_horizon_revision": "UNSET_BLOCKS_E2",
                "mfe_mae": "UNSET_BLOCKS_E2",
                "cost_and_funding": "UNSET_BLOCKS_E2",
                "tail_and_risk_breach": "UNSET_BLOCKS_E2",
                "abstain_coverage_unknown_censored": "UNSET_BLOCKS_E2",
            },
            "endpoint_pnl_may_rescue_intratrajectory_risk_breach": False,
            "same_side_paths_reported_separately": True,
            "pooled_directional_rescue": "FORBIDDEN",
            "implementation": "NOT_IMPLEMENTED",
            "evaluation_run": "NOT_AUTHORIZED",
        },
        "E_POLICY_EVALUATION",
        _EVIDENCE_PATH,
        "policy_trajectory_evaluation_contract",
    )

    probability = document["probability_contract"]
    expected_probability = {
        "modes": [
            {
                "mode": "QUALITATIVE_E0",
                "allowed_values": [
                    "LEADING",
                    "SUPPORTED",
                    "WEAK",
                    "UNSUPPORTED",
                    "UNKNOWN",
                ],
                "numeric_probability_fields": "FORBIDDEN",
                "normalization": "FORBIDDEN",
                "calibration_version": None,
            },
            {
                "mode": "UNKNOWN",
                "allowed_values": [],
                "numeric_probability_fields": "FORBIDDEN",
                "normalization": "FORBIDDEN",
                "calibration_version": None,
            },
            {
                "mode": "CALIBRATED_PROBABILITY",
                "allowed_values": [],
                "numeric_probability_fields": "FUTURE_ONLY",
                "normalization": "REQUIRES_PARTITION_PROOF_AND_E2",
                "calibration_version": "UNSET_BLOCKS_E2",
            },
        ],
        "forbidden_transformations": [
            "SOFTMAX_ORDINAL",
            "NORMALIZE_ORDINAL",
            "CANDIDATE_ASSERTED_PROBABILITY",
            "MECHANISM_SUPPORT_TO_PROBABILITY",
            "PSEUDO_INFORMATION_GAIN",
            "UNCALIBRATED_EXPECTED_VALUE",
        ],
        "future_probability_members": (
            "NAMED_OBSERVABLE_PATH_TERMINAL_CELLS_PLUS_OTHER_PATH_ONLY"
        ),
        "unknown_path_in_probability_simplex": False,
        "censored_in_probability_simplex": False,
        "abstain_in_probability_simplex": False,
        "artifact_in_probability_simplex": False,
        "mechanism_probability": (
            "FORBIDDEN_WITHOUT_AUTHORITY_TRUTH_LABEL"
        ),
        "trade_success_probability": (
            "SEPARATE_CONDITIONAL_ON_EXACT_TRIGGER_AND_ONE_PARENT_PATH"
        ),
        "numeric_information_gain": (
            "FORBIDDEN_UNTIL_PATH_AND_CONDITIONAL_OBSERVATION_CALIBRATION"
        ),
    }
    _exact(
        probability,
        expected_probability,
        "E_PROBABILITY_ESCALATION",
        _EVIDENCE_PATH,
        "probability_contract",
    )
    _exact(
        document["terminal_scenario_aggregation_contract"],
        {
            "terminal_scenarios": ["UPSIDE", "DOWNSIDE", "RANGE", "UNRESOLVED"],
            "multiple_paths_same_terminal_scenario": True,
            "source_path_provenance_required": True,
            "source_path_receipt_tip_required": True,
            "aggregation_rewrites_path": False,
            "aggregation_merges_path_history": False,
            "ordinal_only_at_p0_1": True,
            "probability_values_at_p0_1": {},
        },
        "E_AGGREGATION",
        _EVIDENCE_PATH,
        "terminal_scenario_aggregation_contract",
    )
    _exact(
        document["denominator_contract"],
        {
            "master_opportunity_membership_frozen_before_outcome": True,
            "policy_event_membership_frozen_by_point_in_time_admission": True,
            "all_admitted_events_retained_in_trajectory": True,
            "unknown_opportunities_reported": True,
            "abstained_opportunities_reported": True,
            "censored_opportunities_reported": True,
            "other_path_outcomes_reported": True,
            "dropped_from_denominator": "FORBIDDEN",
            "same_side_path_results_pooled_for_acceptance": False,
            "endpoint_pnl_hides_risk_breach": False,
        },
        "E_DENOMINATOR",
        _EVIDENCE_PATH,
        "denominator_contract",
    )
    future_gate = document["future_oos_gate"]
    required_unset = {
        "status",
        "master_opportunity_denominator",
        "sample_unit",
        "minimum_total_independent_episodes",
        "minimum_stratified_support",
        "effect_or_noninferiority_margin",
        "coverage_and_abstain_limit",
        "unknown_and_censored_limit",
        "calibration_error_limit",
        "multiplicity_budget",
        "stability_neighborhood",
        "chronology_contract",
        "one_time_holdout_receipt",
    }
    expected_gate_keys = required_unset | {
        "evaluation_semantics",
        "event_driven_pit_replay_contract",
        "policy_trajectory_contract",
        "dynamic_order_and_position_management_contract",
        "static_baseline_contract",
        "same_side_path_separate_reporting",
        "pooled_directional_rescue",
    }
    _exact_object(future_gate, expected_gate_keys, _EVIDENCE_PATH, "future_oos_gate")
    if any(future_gate[key] != "UNSET_BLOCKS_E2" for key in required_unset):
        _reject("E_FUTURE_GATE", _EVIDENCE_PATH, "future_oos_gate")
    if (
        future_gate["evaluation_semantics"]
        != "E0_DYNAMIC_INTERFACE_DEFINED_IMPLEMENTATION_AND_THRESHOLDS_UNSET"
        or future_gate["event_driven_pit_replay_contract"]
        != "E0_INTERFACE_DEFINED_NOT_IMPLEMENTED"
        or future_gate["policy_trajectory_contract"]
        != "E0_INTERFACE_DEFINED_NOT_IMPLEMENTED"
        or future_gate["dynamic_order_and_position_management_contract"]
        != "E0_INTERFACE_DEFINED_NOT_IMPLEMENTED"
        or future_gate["static_baseline_contract"]
        != "E0_COMPARATOR_FAMILIES_DEFINED_PARAMETERS_UNSET_BLOCKS_E2"
        or future_gate["same_side_path_separate_reporting"]
        != "REQUIRED_FUTURE_GATE_UNSET_THRESHOLD"
        or future_gate["pooled_directional_rescue"] != "FORBIDDEN"
    ):
        _reject("E_FUTURE_GATE", _EVIDENCE_PATH, "future_oos_gate")

    fixture_contract = document["synthetic_fixture_contract"]
    _exact(
        fixture_contract,
        {
            "fixture_set_fields": [
                "fixture_set_id",
                "template_kind",
                "template_id",
                "cases",
            ],
            "fixture_case_fields": [
                "case_id",
                "case_kind",
                "decision_at",
                "predicate_inputs",
                "expected_template_disposition",
            ],
            "predicate_input_fields": [
                "predicate_id",
                "observed_value",
                "available_at",
                "quality",
                "has_gap",
                "expected_result",
            ],
            "required_case_kinds": [
                "POSITIVE",
                "BOUNDARY",
                "CLOCK",
                "GAP",
                "HARD_INVALIDATION",
                "EXPIRY",
            ],
            "case_result_values": [
                "TRUE",
                "FALSE",
                "UNKNOWN_FUTURE",
                "UNKNOWN_GAP",
                "CENSORED_GAP",
            ],
            "template_dispositions": [
                "ACTIVE_OR_SUPPORTED",
                "BOUNDARY_ACCEPTED",
                "UNKNOWN_CLOCK",
                "UNKNOWN_OR_CENSORED_GAP",
                "HARD_INVALIDATED",
                "EXPIRED",
            ],
            "fixtures_are_market_evidence": False,
            "fixtures_close_f005_dsp022": False,
        },
        "E_FIXTURE_CASE",
        _EVIDENCE_PATH,
        "synthetic_fixture_contract",
    )
    fixture_sets = _list(
        document["synthetic_fixture_sets"],
        _EVIDENCE_PATH,
        "synthetic_fixture_sets",
        nonempty=True,
    )
    seen_fixture_ids: set[str] = set()
    seen_template_ids: set[str] = set()
    for set_index, raw_fixture_set in enumerate(fixture_sets):
        set_field = f"synthetic_fixture_sets[{set_index}]"
        fixture_set = _exact_object(
            raw_fixture_set,
            {"fixture_set_id", "template_kind", "template_id", "cases"},
            _EVIDENCE_PATH,
            set_field,
        )
        fixture_id = fixture_set["fixture_set_id"]
        template_id = fixture_set["template_id"]
        expected_kind_and_fixture = _FIXTURE_BY_TEMPLATE.get(template_id)
        if (
            fixture_id in seen_fixture_ids
            or template_id in seen_template_ids
            or fixture_id not in _FIXTURE_IDS
            or template_id not in template_references
            or expected_kind_and_fixture is None
            or fixture_set["template_kind"] != expected_kind_and_fixture[0]
            or fixture_id != expected_kind_and_fixture[1]
        ):
            _reject("E_FIXTURE_BINDING", _EVIDENCE_PATH, set_field)
        seen_fixture_ids.add(fixture_id)
        seen_template_ids.add(template_id)
        cases = _list(
            fixture_set["cases"], _EVIDENCE_PATH, f"{set_field}.cases", nonempty=True
        )
        seen_case_kinds: set[str] = set()
        covered_predicates: set[str] = set()
        case_ids: set[str] = set()
        for case_index, raw_case in enumerate(cases):
            case_field = f"{set_field}.cases[{case_index}]"
            case = _exact_object(
                raw_case,
                {
                    "case_id",
                    "case_kind",
                    "decision_at",
                    "predicate_inputs",
                    "expected_template_disposition",
                },
                _EVIDENCE_PATH,
                case_field,
            )
            case_id = _text(case["case_id"], _EVIDENCE_PATH, f"{case_field}.case_id")
            if case_id in case_ids:
                _reject("E_FIXTURE_CASE", _EVIDENCE_PATH, f"{case_field}.case_id")
            case_ids.add(case_id)
            case_kind = case["case_kind"]
            if case_kind in seen_case_kinds or case_kind not in _REQUIRED_CASE_KINDS:
                _reject("E_FIXTURE_CASE", _EVIDENCE_PATH, f"{case_field}.case_kind")
            seen_case_kinds.add(case_kind)
            decision_at = _utc(
                case["decision_at"], _EVIDENCE_PATH, f"{case_field}.decision_at"
            )
            inputs = _list(
                case["predicate_inputs"],
                _EVIDENCE_PATH,
                f"{case_field}.predicate_inputs",
                nonempty=True,
            )
            local_predicates: set[str] = set()
            for input_index, raw_input in enumerate(inputs):
                input_field = f"{case_field}.predicate_inputs[{input_index}]"
                predicate_input = _exact_object(
                    raw_input,
                    {
                        "predicate_id",
                        "observed_value",
                        "available_at",
                        "quality",
                        "has_gap",
                        "expected_result",
                    },
                    _EVIDENCE_PATH,
                    input_field,
                )
                predicate_id = predicate_input["predicate_id"]
                if (
                    predicate_id in local_predicates
                    or predicate_id not in template_references[template_id]
                ):
                    _reject("E_FIXTURE_PREDICATE", _EVIDENCE_PATH, input_field)
                local_predicates.add(predicate_id)
                covered_predicates.add(predicate_id)
                if predicate_input["quality"] not in {
                    "VALID_COMPLETE",
                    "VALID_OPTIONAL_UNKNOWN",
                } or type(predicate_input["has_gap"]) is not bool:
                    _reject("E_FIXTURE_PREDICATE", _EVIDENCE_PATH, input_field)
                available_at = _utc(
                    predicate_input["available_at"],
                    _EVIDENCE_PATH,
                    f"{input_field}.available_at",
                )
                actual_result = _predicate_result(
                    predicate_by_id[predicate_id],
                    predicate_input["observed_value"],
                    available_at,
                    decision_at,
                    predicate_input["has_gap"],
                )
                if actual_result != predicate_input["expected_result"]:
                    _reject(
                        "E_FIXTURE_PREDICATE",
                        _EVIDENCE_PATH,
                        f"{input_field}.expected_result",
                    )
            expected_disposition = {
                "POSITIVE": "ACTIVE_OR_SUPPORTED",
                "BOUNDARY": "BOUNDARY_ACCEPTED",
                "CLOCK": "UNKNOWN_CLOCK",
                "GAP": "UNKNOWN_OR_CENSORED_GAP",
                "HARD_INVALIDATION": "HARD_INVALIDATED",
                "EXPIRY": "EXPIRED",
            }[case_kind]
            if case["expected_template_disposition"] != expected_disposition:
                _reject(
                    "E_FIXTURE_CASE",
                    _EVIDENCE_PATH,
                    f"{case_field}.expected_template_disposition",
                )
        if seen_case_kinds != _REQUIRED_CASE_KINDS:
            _reject("E_FIXTURE_CASE", _EVIDENCE_PATH, f"{set_field}.cases")
        if covered_predicates != template_references[template_id]:
            _reject("E_FIXTURE_PREDICATE", _EVIDENCE_PATH, set_field)
    if (
        frozenset(seen_fixture_ids) != _FIXTURE_IDS
        or seen_template_ids != set(template_references)
    ):
        _reject("E_FIXTURE_BINDING", _EVIDENCE_PATH, "synthetic_fixture_sets")
    return digest


def _bundle_digest(
    predecessor_bundle_digest: str, contract_digests: dict[str, str]
) -> str:
    manifest = [
        {
            "component": "frozen_v1_1_bundle",
            "document_count": len(_V1_1_PATHS),
            "bundle_digest": predecessor_bundle_digest,
        },
        *[
            {
                "component": "v1_2_contract",
                "path": path,
                "canonical_sha256": contract_digests[path],
            }
            for path in sorted(contract_digests)
        ],
    ]
    return hashlib.sha256(
        b"msta-hed/research-system-dynamic-hypothesis-graph-bundle/v1_2\0"
        + _canonical_bytes(manifest)
    ).hexdigest()


def validate_research_system_bundle_v1_2(
    raw_by_path: Mapping[str, str],
) -> dict[str, Any]:
    """Validate the frozen v1.1 bundle plus the exact P0.1 E0 contracts."""

    try:
        if not isinstance(raw_by_path, Mapping):
            raise _ContractError("E_INPUT_TYPE", field="$")
        actual_paths = list(raw_by_path.keys())
        if any(type(path) is not str for path in actual_paths):
            raise _ContractError("E_INPUT_TYPE", field="$")
        actual_set = frozenset(actual_paths)
        if actual_set != _REQUIRED_PATHS or len(actual_paths) != len(_REQUIRED_PATHS):
            details: dict[str, str] = {}
            missing = sorted(_REQUIRED_PATHS - actual_set)
            extra = sorted(actual_set - _REQUIRED_PATHS)
            if missing:
                details["missing"] = missing[0]
            if extra:
                details["extra"] = extra[0]
            raise _ContractError("E_FILE_SET", **details)

        predecessor_raw = {
            path: raw_by_path[path] for path in sorted(_V1_1_PATHS)
        }
        predecessor_result = _validate_v1_1_bundle(predecessor_raw)
        if (
            predecessor_result.get("status") != "ACCEPTED"
            or predecessor_result.get("reason_code") != "OK"
        ):
            wrapped_details = predecessor_result.get("details")
            nested = wrapped_details if type(wrapped_details) is dict else {}
            detail_values = {
                "v1_1_status": str(predecessor_result.get("status", "UNKNOWN")),
                "v1_1_reason_code": str(
                    predecessor_result.get("reason_code", "UNKNOWN")
                ),
            }
            for key in (
                "path",
                "field",
                "missing",
                "extra",
                "v1_reason_code",
            ):
                value = nested.get(key)
                if type(value) is str:
                    detail_values[f"v1_1_{key}"] = value
            raise _ContractError("E_V1_1_PREDECESSOR", **detail_values)
        if predecessor_result.get("bundle_digest") != _V1_1_BUNDLE_DIGEST:
            raise _ContractError(
                "E_V1_1_BUNDLE",
                expected_bundle_digest=_V1_1_BUNDLE_DIGEST,
                observed_bundle_digest=str(
                    predecessor_result.get("bundle_digest", "UNKNOWN")
                ),
            )
        for path in sorted(_V1_1_PATHS):
            raw = predecessor_raw[path]
            if type(raw) is not str:
                _reject("E_V1_1_PREDECESSOR_BYTES", path)
            observed_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if observed_sha != _V1_1_PHYSICAL_SHA256[path]:
                _reject("E_V1_1_PREDECESSOR_BYTES", path)

        documents = {
            path: _strict_parse(path, raw_by_path[path])
            for path in sorted(_V1_2_CONTRACT_PATHS)
        }
        graph_digest = _validate_graph(documents[_GRAPH_PATH])
        registry_digest, predicate_by_id, template_references = _validate_registry(
            documents[_REGISTRY_PATH]
        )
        if (
            graph_digest
            != documents[_REGISTRY_PATH]["authority_binding"]["graph_contract"][
                "canonical_sha256"
            ]
        ):
            _reject(
                "E_AUTHORITY_BINDING",
                _REGISTRY_PATH,
                "authority_binding.graph_contract.canonical_sha256",
            )
        evidence_digest = _validate_evidence(
            documents[_EVIDENCE_PATH], predicate_by_id, template_references
        )
        if (
            registry_digest
            != documents[_EVIDENCE_PATH]["authority_binding"]["template_registry"][
                "canonical_sha256"
            ]
        ):
            _reject(
                "E_AUTHORITY_BINDING",
                _EVIDENCE_PATH,
                "authority_binding.template_registry.canonical_sha256",
            )
        digests = {
            _GRAPH_PATH: graph_digest,
            _REGISTRY_PATH: registry_digest,
            _EVIDENCE_PATH: evidence_digest,
        }
        return {
            "status": "ACCEPTED",
            "reason_code": "OK",
            "details": {
                "document_count": len(_REQUIRED_PATHS),
                "predecessor_document_count": len(_V1_1_PATHS),
                "v1_2_contract_document_count": len(_V1_2_CONTRACT_PATHS),
                "predecessor_bundle_digest": _V1_1_BUNDLE_DIGEST,
                "graph_contract_digest": graph_digest,
                "template_registry_digest": registry_digest,
                "evidence_contract_digest": evidence_digest,
                "path_template_count": len(_PATH_IDS),
                "mechanism_template_count": len(_MECHANISM_IDS),
                "trade_template_count": len(_TRADE_IDS),
                "stage_denials": dict(_STAGE_DENIALS),
                "maximum_claim": "E0_CONTRACT_AND_SYNTHETIC_VALIDATION_ONLY",
            },
            "bundle_digest": _bundle_digest(_V1_1_BUNDLE_DIGEST, digests),
        }
    except _ContractError as exc:
        return {
            "status": "REJECTED",
            "reason_code": exc.reason_code,
            "details": exc.details,
            "bundle_digest": None,
        }
    except Exception as exc:
        return {
            "status": "REJECTED",
            "reason_code": "E_INTERNAL_TOTALITY",
            "details": {"error_type": type(exc).__name__},
            "bundle_digest": None,
        }
