"""Fail-closed validator for the MSTA-HED research-system contract bundle.

The validator intentionally performs no filesystem, network, market-data, adapter,
backtest, paper-trading, or execution work.  Its sole input is a mapping from the
seven externally fixed relative paths to their raw JSON text.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import unquote

__all__ = ["validate_research_system_bundle"]


_SOL_DECISION_ID = "SOL_RESEARCH_SYSTEM_RECONSTRUCTION.v1"
_SOL_DECISION_PHYSICAL_SHA256 = (
    "2cf37e54989d3fd09846cacdbe622de26a4c0bd60e46cb0650f67b2827bf5586"
)
_SOL_DECISION_CANONICAL_SHA256 = (
    "2a434f542f58c6d43798e1562b7f203336eae7e5db4b6745095e3c9e7633ddb6"
)
_AUTHORIZED_BRANCH = "codex/s0-research-foundation"
_AUTHORIZED_HEAD = "7ca3fc4f99a57f98217e703f222b295653ace87e"
_AUTHORIZED_DECISION_STATE = "AUTHORIZED_P0_E0_RESEARCH_SYSTEM_RECONSTRUCTION"

_OBJECT_PATH = "config/research_system.object_dictionary.v1.json"
_HYPOTHESIS_PATH = "config/research_system.hypothesis_validation_queue.v1.json"
_MEASUREMENT_PATH = "config/research_system.measurement_contract.v1.json"
_PARAMETER_PATH = "config/research_system.parameter_registry.v1.json"
_SOURCE_PATH = "config/research_system.source_authority_registry.v1.json"
_DISPUTE_PATH = "config/research_system.dispute_registry.v1.json"
_STAGE_PATH = "config/research_system.stage_contract.v1.json"

_DOCUMENT_SPECS = {
    _OBJECT_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_RESEARCH_OBJECT_DICTIONARY.v1",
        "schema": "research-object-dictionary.v1",
        "status_key": "status",
        "status": "E0_CANDIDATE_NOT_THEORY_AUTHORITY",
        "evidence": "E0_THEORY_MEASUREMENT_AND_CONTRACT_DESIGN_ONLY",
        "domain": "msta-hed/research-object-dictionary/v1",
        "digest_key": "registry_sha256",
        "authority": "branch",
    },
    _HYPOTHESIS_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_HYPOTHESIS_VALIDATION_QUEUE.v1",
        "schema": "research-hypothesis-queue.v1",
        "status_key": "status",
        "status": "E0_PRIORITIZED_VALIDATION_QUEUE_NO_MARKET_CLAIM",
        "evidence": "E0_THEORY_AND_MEASUREMENT_DESIGN_ONLY",
        "domain": "msta-hed/hypothesis-validation-queue/v1",
        "digest_key": "registry_sha256",
        "authority": "common",
    },
    _MEASUREMENT_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_MEASUREMENT_CONTRACT_REGISTRY.v1",
        "schema": "research-measurement-contract.v1",
        "status_key": "status",
        "status": "E0_MEASUREMENT_DESIGN_NO_DATASET_NO_BACKTEST",
        "evidence": "E0_SYNTHETIC_AND_DESIGN_ONLY",
        "domain": "msta-hed/measurement-contract-registry/v1",
        "digest_key": "registry_sha256",
        "authority": "common",
    },
    _PARAMETER_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_PARAMETER_REGISTRY.v1",
        "schema": "research-parameter-registry.v1",
        "status_key": "status",
        "status": "E0_INITIAL_ASSUMPTION_RANGES_NOT_ESTIMATED",
        "evidence": "E0_DESIGN_ONLY",
        "domain": "msta-hed/parameter-registry/v1",
        "digest_key": "registry_sha256",
        "authority": "common",
    },
    _SOURCE_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_SOURCE_AUTHORITY_REGISTRY.v1",
        "schema": "research-source-authority-registry.v1",
        "status_key": "registry_status",
        "status": "DOCUMENT_DISCOVERY_ONLY_NO_DATA_ACQUIRED",
        "domain": "msta-hed/source-authority-registry/v1",
        "digest_key": "registry_sha256",
        "authority": "none",
    },
    _DISPUTE_PATH: {
        "id_key": "registry_id",
        "id": "MSTA_HED_DISPUTE_REGISTRY.v1",
        "schema": "research-dispute-registry.v1",
        "status_key": "status",
        "status": "E0_AUDIT_FINDINGS_AND_RESOLUTION_PLAN",
        "evidence": "E0_STATIC_CROSS_DOCUMENT_AUDIT",
        "domain": "msta-hed/dispute-registry/v1",
        "digest_key": "registry_sha256",
        "authority": "common",
    },
    _STAGE_PATH: {
        "id_key": "stage_contract_id",
        "id": "MSTA_HED_RESEARCH_STAGE_CONTRACT.v1",
        "schema": "research-stage-contract.v1",
        "status_key": "status",
        "status": "EXTERNAL_AUTHORITY_BOUND_P0_CANDIDATE",
        "domain": "msta-hed/research-stage-contract/v1",
        "digest_key": "contract_sha256",
        "authority": "stage",
    },
}
_REQUIRED_PATHS = frozenset(_DOCUMENT_SPECS)

_TOP_LEVEL_KEYS = {
    _OBJECT_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "status",
            "evidence_level",
            "authority_binding",
            "object_types",
            "variables",
            "claims",
            "dependency_edges",
            "empty_semantics",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _HYPOTHESIS_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "status",
            "evidence_level",
            "authority_binding",
            "lifecycle_states",
            "priority_scale",
            "active_path_policy",
            "failure_policy",
            "hypotheses",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _MEASUREMENT_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "status",
            "evidence_level",
            "authority_binding",
            "global_rules",
            "contracts",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _PARAMETER_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "status",
            "evidence_level",
            "authority_binding",
            "source_types",
            "sensitivity_classes",
            "current_statuses",
            "global_rules",
            "parameters",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _SOURCE_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "registry_status",
            "scope",
            "evidence_grade_definitions",
            "status_axes",
            "global_admission_rule",
            "sources",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _DISPUTE_PATH: frozenset(
        {
            "registry_id",
            "schema_version",
            "created_at",
            "status",
            "evidence_level",
            "authority_binding",
            "disputes",
            "canonicalization",
            "registry_sha256",
        }
    ),
    _STAGE_PATH: frozenset(
        {
            "stage_contract_id",
            "schema_version",
            "created_at",
            "status",
            "route_id",
            "current_stage",
            "authority_binding",
            "immutable_baseline",
            "permission_matrix",
            "gates",
            "dynamic_roles",
            "escalation_rules",
            "claim_boundary",
            "canonicalization",
            "contract_sha256",
        }
    ),
}

_LIFECYCLE_STATES = (
    "DORMANT",
    "QUEUED",
    "ACTIVE_DESIGN",
    "READY_FOR_GATE",
    "TESTING",
    "WEAK_EVIDENCE",
    "CONTRADICTED",
    "LOCALLY_REVISED",
    "RETEST_REQUIRED",
    "FALSIFIED",
    "EXPIRED",
    "ARCHIVED",
)
_HYPOTHESIS_TYPES = frozenset(
    {
        "CALIBRATION_HYPOTHESIS",
        "DATA_METHOD_HYPOTHESIS",
        "DECISION_SYSTEM_HYPOTHESIS",
        "EXECUTION_HYPOTHESIS",
        "FEATURE_ABLATION_HYPOTHESIS",
        "MEASUREMENT_AND_DECISION_HYPOTHESIS",
        "MECHANISM_HYPOTHESIS",
        "MODEL_HYPOTHESIS",
        "PATH_HYPOTHESIS",
        "PATH_SPEC_HYPOTHESIS",
        "RESEARCH_NOTE_ONLY",
        "RISK_AND_CONTEXT_HYPOTHESIS",
        "STATE_HYPOTHESIS",
        "SYSTEM_HYPOTHESIS",
        "TAIL_PATH_HYPOTHESIS",
        "TRADE_HYPOTHESIS",
    }
)
_MEASUREMENT_STATUSES = frozenset(
    {
        "ARCHIVED_NO_MEASUREMENT",
        "DESIGN_ONLY",
        "DORMANT_UNTIL_COMPONENTS",
        "DORMANT_UNTIL_E3",
        "DORMANT_UNTIL_SIMPLE_BASELINE",
        "SYNTHETIC_INVARIANTS_ONLY",
        "SYNTHETIC_READY",
        "WAIT_AUTHORITATIVE_EVENT_CLOCK",
        "WAIT_CALIBRATED_SCENARIOS",
        "WAIT_DATA_STRICT_SEQUENCE",
    }
)
_PARAMETER_SOURCE_TYPES = (
    "DIRECT_COMPUTATION",
    "PRIMARY_LITERATURE",
    "SAMPLE_ESTIMATE",
    "INITIAL_VALIDATION_ASSUMPTION",
    "SENSITIVITY_BOUND",
    "THEORY_CONSTRAINT",
    "UNSUPPORTED_PLACEHOLDER",
)
_PARAMETER_STATUSES = ("UNESTIMATED", "FROZEN_E0", "WAIT_DATA", "DORMANT")
_PARAMETER_SENSITIVITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_DISPUTE_STATUSES = frozenset(
    {
        "DISCRIMINATING_TEST_REQUIRED",
        "RESOLVED_BY_COMMON_DENOMINATOR_RULE",
        "RESOLVED_BY_DEFINITION",
        "RESOLVED_BY_HIGHER_AUTHORITY",
        "RESOLVED_BY_VERSIONED_ADAPTER_ONLY",
        "RESOLVED_BY_VERSIONED_OVERLAY",
        "RESOLVED_BY_WINDOW_SEPARATION_RULE",
        "SPLIT_SCOPE",
        "UNRESOLVED_DISPUTE_POOL",
    }
)
_DISPUTE_CATEGORIES = frozenset(
    {
        "ACTION_SEMANTICS",
        "AUTHORITY_ROUTE",
        "CATEGORY_CONFLATION",
        "CAUSAL_WINDOW",
        "CLOCK_INTERFACE",
        "DEPENDENCY_AGGREGATION",
        "DEPENDENCY_TOPOLOGY",
        "EPISTEMIC_VS_MARKET",
        "GOVERNANCE_STATUS",
        "LEGACY_ADAPTER",
        "LINEAGE_TRACEABILITY",
        "MEASUREMENT_GAP",
        "MISSING_CHAIN",
        "SCORING_TARGET",
        "SELECTIVE_PREDICTION",
        "TARGET_POLICY",
        "TIMEFRAME_AUTHORITY",
    }
)
_SOURCE_STATUS_AXES = {
    "integrity": (
        "UNKNOWN_NOT_VERIFIED",
        "DOCUMENT_IDENTITY_DISCOVERED",
        "VERIFIED",
        "FAILED",
    ),
    "coverage": (
        "UNKNOWN_NOT_ACQUIRED",
        "NOT_APPLICABLE_TARGET_DATA",
        "VERIFIED_PARTIAL",
        "VERIFIED_COMPLETE",
        "GAP_CONFIRMED",
    ),
    "revision": (
        "UNKNOWN_NOT_VERIFIED",
        "PUBLISHED_VERSION_IDENTIFIED",
        "VERIFIED_VERSIONED",
        "VERIFIED_NON_REVISING",
        "REVISION_CONFLICT",
    ),
    "pit": (
        "UNKNOWN_NOT_VERIFIED",
        "NOT_MARKET_DATA_SOURCE",
        "DOCUMENT_SEMANTICS_ONLY",
        "VERIFIED_AVAILABLE_AT",
        "FAILED_LOOKAHEAD",
    ),
}

_PERMISSION_MATRIX = {
    "read_only_workspace_audit": True,
    "authoritative_document_discovery": True,
    "new_versioned_theory_candidates": True,
    "registries_and_measurement_contracts": True,
    "pure_validators_and_synthetic_tests": True,
    "market_row_download": False,
    "historical_data_acquisition": False,
    "active_application_support_root_access": False,
    "raw_admission_runtime": False,
    "adapter_implementation_or_execution": False,
    "dataset_or_feature_build": False,
    "backtest": False,
    "calibration": False,
    "holdout": False,
    "paper_or_testnet": False,
    "deployment": False,
    "live_or_trading": False,
}
_GATE_AUTHORITY = {
    "RSR-P0": (
        "EXTERNALLY_AUTHORIZED_WORK_IN_PROGRESS",
        "GPT-5.6-SOL-ULTRA_PROGRAM_ROUTE",
        "NONE_AUTOMATIC",
    ),
    "D0": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_ACQUISITION_PLAN",
    ),
    "D1": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_RAW_ARTIFACT_ADMISSION",
    ),
    "D2": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_OFFLINE_ADAPTER_AND_REPLAY",
    ),
    "D3": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_DATASET_GENERATION_NO_SCORING",
    ),
    "E2": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_EVALUATION_NO_PAPER",
    ),
    "E3": (
        "CLOSED_REQUIRES_NEW_SOL_DECISION",
        "GPT-5.6-SOL-ULTRA_STAGE_GATE",
        "ONLY_EXACT_PAPER_OR_TESTNET_NO_FUNDS",
    ),
}
_GATE_ORDER = ("RSR-P0", "D0", "D1", "D2", "D3", "E2", "E3")
_GATE_CONTENT = {
    "RSR-P0": {
        "prerequisites": ("External reconstruction decision already bound",),
        "deliverables": (
            "immutable inventory",
            "theory object map",
            "hypothesis queue",
            "source registry",
            "measurement and parameter contracts",
            "pure total validator",
            "independent adversarial report",
            "integrated roadmap",
        ),
    },
    "D0": {
        "prerequisites": (
            "RSR-P0 Sol PASS",
            "exact source/license/schema/date/cost/storage/resource plan",
            "frozen chronology roles",
            "new non-aliasing identities",
        ),
        "deliverables": ("exact acquisition authorization only",),
    },
    "D1": {
        "prerequisites": (
            "D0 receipt or explicitly supplied raw artifact",
            "external authority values",
            "byte digest and coverage/revision/PIT facts",
            "independent mutation closure",
        ),
        "deliverables": ("exact raw artifact admission receipt",),
    },
    "D2": {
        "prerequisites": (
            "D1 PASS",
            "frozen source schema and units",
            "sequence/gap/clock/revision rules",
            "supplied-fixture tests",
            "deterministic replay identity",
        ),
        "deliverables": ("exact offline adapter and replay scope",),
    },
    "D3": {
        "prerequisites": (
            "D2 PASS",
            "PIT replay",
            "frozen features/states/zones/paths/labels/censoring",
            "chronology and coverage proof",
        ),
        "deliverables": ("exact preregistered research dataset",),
    },
    "E2": {
        "prerequisites": (
            "D3 PASS",
            "sufficient support",
            "frozen candidate/baselines/cost/splits/metrics",
            "one-time unseen holdout",
            "trial registry",
        ),
        "deliverables": (
            "exact backtest/calibration/one-time holdout evaluation",
        ),
    },
    "E3": {
        "prerequisites": (
            "E2 evidence decision",
            "independent risk engine",
            "OMS invariants",
            "failure injection",
            "account/legal/operator boundaries",
        ),
        "deliverables": ("exact paper or testnet validation scope",),
    },
}
_ROLE_STATES = frozenset(
    {
        "ACTIVE_P0",
        "DORMANT_UNTIL_D0",
        "DORMANT_UNTIL_E2",
        "DORMANT_UNTIL_E3",
        "DYNAMIC_P0",
        "ON_DEMAND_STAGE_GATE",
        "REQUIRED_FOR_P0_REVIEW",
    }
)
_ROLE_MODELS = frozenset({"gpt-5.6-sol-ultra", "gpt-5.6-terra-high"})
_CLAIM_BOUNDARY = {
    "research_reconstruction": "AUTHORIZED_E0_P0_WORK_ONLY",
    "theory_authority": "CURRENT_CORE_V2_1_UNCHANGED",
    "new_theory_validity": "NOT_EVALUATED",
    "source_data_validity": "NOT_EVALUATED",
    "market_validity": "NOT_EVALUATED",
    "profitability": "NOT_EVALUATED",
    "data_acquisition": "NOT_AUTHORIZED",
    "backtest": "NOT_AUTHORIZED",
    "paper": "NOT_AUTHORIZED",
    "deployment": "DENIED",
    "trading": "DENIED",
}
_IMMUTABLE_BASELINE = {
    "CURRENT_CORE_THEORY": (
        "archive/authority/CORE_TRADING_THEORY_v2_1.md",
        "2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d",
        "READ_ONLY_NOT_PROMOTED",
    ),
    "CURRENT_CORE_THEORY_MIRROR": (
        "archive/authority/CORE_TRADING_THEORY_v2_1.md",
        "2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d",
        "READ_ONLY_NOT_PROMOTED",
    ),
    "PROGRAM_GOVERNANCE_SNAPSHOT": (
        "archive/authority/PROGRAM_GOVERNANCE_v1_5_2026-07-30.md",
        "69125790fa36c0c4f72ebdecea4f5415be73a9e4fba78c6c1aa53b9639ef6f09",
        "READ_ONLY_HISTORICAL_STAGE_NARRATIVE",
    ),
    "OLD_ACTIVE_ROUTE_TERMINAL_DECISION": (
        "config/sol_decision.active-g1-plan-unreachable.v2.json",
        "3417205afc38247bc8463ddd6e18cf54dffe51724571100a974f9572309127c8",
        "TERMINAL_IMMUTABLE_NOT_RECOVERED",
    ),
    "OLD_RAW_AUTHORITY_ROUTE_TERMINAL_DECISION": (
        "config/sol_decision.p1a-authority-chain-block.v1.json",
        "26355176199bde8cc20e73e2183b43a14bf6210b3a3c41c9480c51b204b9d759",
        "TERMINAL_IMMUTABLE_NOT_REPAIRED",
    ),
}

_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PARAMETER_REF_RE = re.compile(r"\bPAR-[A-Z0-9][A-Z0-9_-]*\b")


class _ContractError(Exception):
    def __init__(self, reason_code: str, **details: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.details = dict(sorted(details.items()))


class _DuplicateKey(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class _NonFiniteNumber(Exception):
    pass


def _reject(reason_code: str, path: str, field: str = "") -> None:
    details = {"path": path}
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


def _parse_json(path: str, raw: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey as exc:
        _reject("E_JSON_DUPLICATE_KEY", path, exc.key)
    except _NonFiniteNumber:
        _reject("E_JSON_NONFINITE", path)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        _reject("E_JSON_MALFORMED", path)
    _reject_invalid_numbers(value, path, "$")
    if type(value) is not dict:
        _reject("E_TOP_LEVEL_TYPE", path, "$")
    return value


def _reject_invalid_numbers(value: Any, path: str, field: str) -> None:
    if type(value) is float:
        if not math.isfinite(value):
            _reject("E_JSON_NONFINITE", path, field)
        _reject("E_FIELD_TYPE", path, field)
    if type(value) is dict:
        for key, child in value.items():
            _reject_invalid_numbers(child, path, f"{field}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_invalid_numbers(child, path, f"{field}[{index}]")


def _exact_object(
    value: Any, keys: frozenset[str] | set[str], path: str, field: str
) -> dict[str, Any]:
    if type(value) is not dict:
        _reject("E_FIELD_TYPE", path, field)
    actual = frozenset(value)
    expected = frozenset(keys)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        suffix = extra[0] if extra else missing[0]
        _reject("E_UNKNOWN_FIELD" if extra else "E_FIELD_EMPTY", path, f"{field}.{suffix}")
    return value


def _text(value: Any, path: str, field: str) -> str:
    if type(value) is not str:
        _reject("E_FIELD_TYPE", path, field)
    if not value.strip():
        _reject("E_FIELD_EMPTY", path, field)
    return value


def _exact_text(value: Any, expected: str, path: str, field: str, code: str) -> None:
    if type(value) is not str:
        _reject("E_FIELD_TYPE", path, field)
    if value != expected:
        _reject(code, path, field)


def _boolean(value: Any, path: str, field: str) -> bool:
    if type(value) is not bool:
        _reject("E_FIELD_TYPE", path, field)
    return value


def _integer(value: Any, path: str, field: str) -> int:
    if type(value) is not int:
        _reject("E_FIELD_TYPE", path, field)
    return value


def _string_list(
    value: Any,
    path: str,
    field: str,
    *,
    nonempty: bool,
    unique: bool = False,
) -> list[str]:
    if type(value) is not list:
        _reject("E_FIELD_TYPE", path, field)
    if nonempty and not value:
        _reject("E_FIELD_EMPTY", path, field)
    for index, item in enumerate(value):
        _text(item, path, f"{field}[{index}]")
    if unique and len(set(value)) != len(value):
        _reject("E_ID_DUPLICATE", path, field)
    return value


def _object_list(value: Any, path: str, field: str, *, nonempty: bool) -> list[Any]:
    if type(value) is not list:
        _reject("E_FIELD_TYPE", path, field)
    if nonempty and not value:
        _reject("E_FIELD_EMPTY", path, field)
    return value


def _utc(value: Any, path: str, field: str) -> None:
    text = _text(value, path, field)
    if not _UTC_RE.fullmatch(text):
        _reject("E_CLOCK", path, field)
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject("E_CLOCK", path, field)


def _sha(value: Any, path: str, field: str) -> str:
    text = _text(value, path, field)
    if not _SHA_RE.fullmatch(text):
        _reject("E_SHA256", path, field)
    return text


def _unique_values(values: list[str], path: str, field: str) -> None:
    if len(values) != len(set(values)):
        _reject("E_ID_DUPLICATE", path, field)


def _text_object(value: Any, keys: set[str], path: str, field: str) -> dict[str, Any]:
    obj = _exact_object(value, keys, path, field)
    for key in sorted(keys):
        _text(obj[key], path, f"{field}.{key}")
    return obj


def _validate_authority(doc: dict[str, Any], path: str, authority_kind: str) -> None:
    if authority_kind == "none":
        return
    if authority_kind == "common":
        keys = {"decision_id", "decision_physical_sha256", "decision_canonical_sha256"}
    elif authority_kind == "branch":
        keys = {
            "decision_id",
            "decision_physical_sha256",
            "decision_canonical_sha256",
            "branch",
            "head",
        }
    else:
        keys = {
            "decision_id",
            "decision_state",
            "decision_physical_sha256",
            "decision_canonical_sha256",
            "branch",
            "head",
        }
    authority = _exact_object(doc["authority_binding"], keys, path, "authority_binding")
    expected = {
        "decision_id": _SOL_DECISION_ID,
        "decision_physical_sha256": _SOL_DECISION_PHYSICAL_SHA256,
        "decision_canonical_sha256": _SOL_DECISION_CANONICAL_SHA256,
    }
    if authority_kind in {"branch", "stage"}:
        expected.update({"branch": _AUTHORIZED_BRANCH, "head": _AUTHORIZED_HEAD})
    if authority_kind == "stage":
        expected["decision_state"] = _AUTHORIZED_DECISION_STATE
    for key, expected_value in expected.items():
        _exact_text(
            authority[key],
            expected_value,
            path,
            f"authority_binding.{key}",
            "E_STAGE_AUTHORITY" if authority_kind == "stage" else "E_AUTHORITY_BINDING",
        )


def _validate_canonicalization(doc: dict[str, Any], path: str) -> None:
    spec = _DOCUMENT_SPECS[path]
    canonicalization = _exact_object(
        doc["canonicalization"],
        {
            "algorithm",
            "domain",
            "domain_prefix_utf8",
            "domain_separator_hex",
            "encoding",
            "ensure_ascii",
            "exclude_fields",
            "formula",
            "separators",
            "sort_keys",
        },
        path,
        "canonicalization",
    )
    expected_text = {
        "algorithm": "SHA-256",
        "domain": spec["domain"],
        "domain_prefix_utf8": spec["domain"],
        "domain_separator_hex": "00",
        "encoding": "UTF-8",
        "formula": "SHA256(domain_prefix_utf8 || HEX(domain_separator_hex) || canonical_json_utf8)",
    }
    for key, expected in expected_text.items():
        _exact_text(
            canonicalization[key],
            expected,
            path,
            f"canonicalization.{key}",
            "E_CANONICALIZATION",
        )
    if _boolean(
        canonicalization["ensure_ascii"], path, "canonicalization.ensure_ascii"
    ) is not True:
        _reject("E_CANONICALIZATION", path, "canonicalization.ensure_ascii")
    if _boolean(canonicalization["sort_keys"], path, "canonicalization.sort_keys") is not True:
        _reject("E_CANONICALIZATION", path, "canonicalization.sort_keys")
    if canonicalization["exclude_fields"] != [spec["digest_key"]]:
        _reject("E_CANONICALIZATION", path, "canonicalization.exclude_fields")
    if canonicalization["separators"] != [",", ":"]:
        _reject("E_CANONICALIZATION", path, "canonicalization.separators")


def _validate_common_metadata(doc: dict[str, Any], path: str) -> None:
    spec = _DOCUMENT_SPECS[path]
    _exact_object(doc, _TOP_LEVEL_KEYS[path], path, "$")
    _exact_text(doc[spec["id_key"]], spec["id"], path, spec["id_key"], "E_IDENTITY")
    _exact_text(
        doc["schema_version"], spec["schema"], path, "schema_version", "E_IDENTITY"
    )
    _utc(doc["created_at"], path, "created_at")
    _exact_text(
        doc[spec["status_key"]],
        spec["status"],
        path,
        spec["status_key"],
        "E_STATUS",
    )
    if "evidence" in spec:
        _exact_text(
            doc["evidence_level"],
            spec["evidence"],
            path,
            "evidence_level",
            "E_STATUS",
        )
    _validate_authority(doc, path, spec["authority"])
    _validate_canonicalization(doc, path)
    _sha(doc[spec["digest_key"]], path, spec["digest_key"])


def _validate_object_dictionary(doc: dict[str, Any]) -> None:
    path = _OBJECT_PATH
    object_keys = {
        "object_id",
        "object_type",
        "definition",
        "required_inputs",
        "required_outputs",
        "clock_rule",
        "unknown_semantics",
        "can_authorize_order",
        "evidence_status",
    }
    object_ids: list[str] = []
    object_types: list[str] = []
    for index, row in enumerate(_object_list(doc["object_types"], path, "object_types", nonempty=True)):
        field = f"object_types[{index}]"
        obj = _exact_object(row, object_keys, path, field)
        object_ids.append(_text(obj["object_id"], path, f"{field}.object_id"))
        object_types.append(_text(obj["object_type"], path, f"{field}.object_type"))
        for key in ("definition", "clock_rule", "unknown_semantics", "evidence_status"):
            _text(obj[key], path, f"{field}.{key}")
        _string_list(obj["required_inputs"], path, f"{field}.required_inputs", nonempty=True)
        _string_list(obj["required_outputs"], path, f"{field}.required_outputs", nonempty=True)
        can_authorize = _boolean(
            obj["can_authorize_order"], path, f"{field}.can_authorize_order"
        )
        if can_authorize is not (
            obj["object_id"] == "OBJ-PERMISSION"
            and obj["object_type"] == "PERMISSION"
        ):
            _reject("E_PERMISSION_MATRIX", path, f"{field}.can_authorize_order")
    _unique_values(object_ids, path, "object_types.object_id")
    _unique_values(object_types, path, "object_types.object_type")

    variable_keys = {
        "variable_id",
        "symbol",
        "definition",
        "domain",
        "source_type",
        "unknown_rule",
        "unit",
    }
    variable_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["variables"], path, "variables", nonempty=True)):
        field = f"variables[{index}]"
        obj = _exact_object(row, variable_keys, path, field)
        variable_ids.append(_text(obj["variable_id"], path, f"{field}.variable_id"))
        for key in variable_keys - {"variable_id"}:
            _text(obj[key], path, f"{field}.{key}")
    _unique_values(variable_ids, path, "variables.variable_id")

    claim_keys = {
        "claim_id",
        "claim_class",
        "claim_text",
        "evidence_status",
        "scope",
        "falsifier",
        "limitations",
    }
    claim_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["claims"], path, "claims", nonempty=True)):
        field = f"claims[{index}]"
        obj = _exact_object(row, claim_keys, path, field)
        claim_ids.append(_text(obj["claim_id"], path, f"{field}.claim_id"))
        for key in claim_keys - {"claim_id"}:
            _text(obj[key], path, f"{field}.{key}")
    _unique_values(claim_ids, path, "claims.claim_id")

    edges = _object_list(doc["dependency_edges"], path, "dependency_edges", nonempty=True)
    normalized_edges: list[tuple[str, str]] = []
    known_types = set(object_types)
    for index, edge in enumerate(edges):
        field = f"dependency_edges[{index}]"
        if type(edge) is not list or len(edge) != 2:
            _reject("E_FIELD_TYPE", path, field)
        left = _text(edge[0], path, f"{field}[0]")
        right = _text(edge[1], path, f"{field}[1]")
        if left not in known_types or right not in known_types:
            _reject("E_CROSS_OBJECT", path, field)
        normalized_edges.append((left, right))
    if len(normalized_edges) != len(set(normalized_edges)):
        _reject("E_ID_DUPLICATE", path, "dependency_edges")

    _text_object(
        doc["empty_semantics"],
        {
            "missing_required_object",
            "empty_required_collection",
            "empty_result_history_for_untested_hypothesis",
            "empty_market_message_interval",
            "empty_active_path_pool",
            "no_valid_zone",
        },
        path,
        "empty_semantics",
    )


def _validate_hypotheses(doc: dict[str, Any]) -> None:
    path = _HYPOTHESIS_PATH
    lifecycle = _string_list(
        doc["lifecycle_states"], path, "lifecycle_states", nonempty=True, unique=True
    )
    if tuple(lifecycle) != _LIFECYCLE_STATES:
        _reject("E_LIFECYCLE", path, "lifecycle_states")
    priorities = _text_object(doc["priority_scale"], {"P0", "P1", "P2"}, path, "priority_scale")

    policy = _exact_object(
        doc["active_path_policy"],
        {
            "leading_max",
            "alternatives_max",
            "tail_risk_max",
            "required_residual_paths",
            "abstain_is_action_not_path",
            "coverage_rule",
        },
        path,
        "active_path_policy",
    )
    expected_ints = {"leading_max": 1, "alternatives_max": 2, "tail_risk_max": 1}
    for key, expected in expected_ints.items():
        if _integer(policy[key], path, f"active_path_policy.{key}") != expected:
            _reject("E_RESIDUAL_PATH_POLICY", path, f"active_path_policy.{key}")
    residual = _string_list(
        policy["required_residual_paths"],
        path,
        "active_path_policy.required_residual_paths",
        nonempty=True,
        unique=True,
    )
    if residual != ["OTHER_PATH", "UNKNOWN_PATH"] or "ABSTAIN" in residual:
        _reject("E_RESIDUAL_PATH_POLICY", path, "active_path_policy.required_residual_paths")
    if _boolean(
        policy["abstain_is_action_not_path"],
        path,
        "active_path_policy.abstain_is_action_not_path",
    ) is not True:
        _reject("E_RESIDUAL_PATH_POLICY", path, "active_path_policy.abstain_is_action_not_path")
    _text(policy["coverage_rule"], path, "active_path_policy.coverage_rule")

    failure = _exact_object(
        doc["failure_policy"],
        {"diagnosis_order", "single_delta_rule", "preservation_rule", "no_post_hoc_rescue"},
        path,
        "failure_policy",
    )
    _string_list(
        failure["diagnosis_order"],
        path,
        "failure_policy.diagnosis_order",
        nonempty=True,
        unique=True,
    )
    for key in ("single_delta_rule", "preservation_rule", "no_post_hoc_rescue"):
        _text(failure[key], path, f"failure_policy.{key}")

    row_keys = {
        "hypothesis_id",
        "hypothesis_version",
        "family_id",
        "type",
        "claim_text",
        "evidence_level",
        "timeframe_role",
        "created_at",
        "prerequisites",
        "prediction_window",
        "expected_partial_order_path",
        "supporting_evidence_contracts",
        "contradicting_evidence_contracts",
        "hard_falsifier",
        "expiry_rule",
        "trade_link_or_none",
        "non_trade_conditions",
        "dependency_group_ids",
        "current_state",
        "priority",
        "next_cheapest_discriminating_test",
        "source_claim_ids",
        "measurement_contract_id",
        "result_history",
        "lineage",
    }
    lineage_keys = {"duplicates", "extends", "notes", "supersedes"}
    result_keys = {
        "artifact_reference",
        "candidate_version",
        "chronology_role",
        "claim_effect",
        "immutable",
        "outcome",
        "primary_error_class",
        "result_id",
    }
    hypothesis_ids: list[str] = []
    measurement_ids: list[str] = []
    result_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["hypotheses"], path, "hypotheses", nonempty=True)):
        field = f"hypotheses[{index}]"
        obj = _exact_object(row, row_keys, path, field)
        hypothesis_ids.append(_text(obj["hypothesis_id"], path, f"{field}.hypothesis_id"))
        measurement_ids.append(
            _text(obj["measurement_contract_id"], path, f"{field}.measurement_contract_id")
        )
        for key in (
            "hypothesis_version",
            "family_id",
            "claim_text",
            "evidence_level",
            "timeframe_role",
            "prediction_window",
            "hard_falsifier",
            "expiry_rule",
            "trade_link_or_none",
            "current_state",
            "priority",
            "next_cheapest_discriminating_test",
        ):
            _text(obj[key], path, f"{field}.{key}")
        _utc(obj["created_at"], path, f"{field}.created_at")
        if obj["type"] not in _HYPOTHESIS_TYPES:
            _reject("E_STATUS", path, f"{field}.type")
        if obj["current_state"] not in lifecycle:
            _reject("E_LIFECYCLE", path, f"{field}.current_state")
        if obj["priority"] not in priorities:
            _reject("E_STATUS", path, f"{field}.priority")
        for key in (
            "prerequisites",
            "expected_partial_order_path",
            "supporting_evidence_contracts",
            "contradicting_evidence_contracts",
            "non_trade_conditions",
            "dependency_group_ids",
            "source_claim_ids",
        ):
            _string_list(obj[key], path, f"{field}.{key}", nonempty=True, unique=True)
        lineage = _exact_object(obj["lineage"], lineage_keys, path, f"{field}.lineage")
        for key in ("duplicates", "extends", "supersedes"):
            _string_list(
                lineage[key], path, f"{field}.lineage.{key}", nonempty=False, unique=True
            )
        _text(lineage["notes"], path, f"{field}.lineage.notes")

        history = _object_list(
            obj["result_history"], path, f"{field}.result_history", nonempty=False
        )
        if (
            obj["current_state"]
            in {
                "ARCHIVED",
                "WEAK_EVIDENCE",
                "CONTRADICTED",
                "LOCALLY_REVISED",
                "RETEST_REQUIRED",
                "FALSIFIED",
                "EXPIRED",
            }
            and not history
        ):
            _reject("E_RESULT_HISTORY", path, f"{field}.result_history")
        for hindex, history_row in enumerate(history):
            hfield = f"{field}.result_history[{hindex}]"
            result = _exact_object(history_row, result_keys, path, hfield)
            result_ids.append(_text(result["result_id"], path, f"{hfield}.result_id"))
            for key in result_keys - {"result_id", "immutable"}:
                _text(result[key], path, f"{hfield}.{key}")
            if _boolean(result["immutable"], path, f"{hfield}.immutable") is not True:
                _reject("E_RESULT_HISTORY", path, f"{hfield}.immutable")
    _unique_values(hypothesis_ids, path, "hypotheses.hypothesis_id")
    _unique_values(measurement_ids, path, "hypotheses.measurement_contract_id")
    _unique_values(result_ids, path, "hypotheses.result_history.result_id")


def _validate_measurements(doc: dict[str, Any]) -> None:
    path = _MEASUREMENT_PATH
    _text_object(
        doc["global_rules"],
        {
            "common_denominator",
            "ev_outcome_partition",
            "first_hit",
            "negative_evidence",
            "machine_predicate_readiness",
            "measurement_totality",
            "ordinal_aggregation",
            "point_in_time",
            "probability",
            "unknown",
            "window_separation",
        },
        path,
        "global_rules",
    )
    row_keys = {
        "antecedent_window",
        "censoring",
        "comparator",
        "confirmation_window",
        "contract_version",
        "contradiction_rule",
        "data_requirements",
        "decision_relevance",
        "detection_cutoff",
        "evidence_claim_boundary",
        "hard_falsifier_rule",
        "hypothesis_id",
        "label_contract",
        "measurement_contract_id",
        "observables",
        "outcome_window",
        "power_and_coverage",
        "sensitivity_parameter_ids",
        "status",
        "stop_wait_rule",
        "support_rule",
    }
    contract_ids: list[str] = []
    hypothesis_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["contracts"], path, "contracts", nonempty=True)):
        field = f"contracts[{index}]"
        obj = _exact_object(row, row_keys, path, field)
        contract_ids.append(
            _text(obj["measurement_contract_id"], path, f"{field}.measurement_contract_id")
        )
        hypothesis_ids.append(_text(obj["hypothesis_id"], path, f"{field}.hypothesis_id"))
        for key in row_keys - {
            "data_requirements",
            "observables",
            "sensitivity_parameter_ids",
        }:
            _text(obj[key], path, f"{field}.{key}")
        if obj["status"] not in _MEASUREMENT_STATUSES:
            _reject("E_STATUS", path, f"{field}.status")
        _string_list(
            obj["data_requirements"], path, f"{field}.data_requirements", nonempty=True
        )
        _string_list(obj["observables"], path, f"{field}.observables", nonempty=True)
        _string_list(
            obj["sensitivity_parameter_ids"],
            path,
            f"{field}.sensitivity_parameter_ids",
            nonempty=False,
            unique=True,
        )
    _unique_values(contract_ids, path, "contracts.measurement_contract_id")
    _unique_values(hypothesis_ids, path, "contracts.hypothesis_id")


def _validate_parameters(doc: dict[str, Any]) -> None:
    path = _PARAMETER_PATH
    source_types = _string_list(
        doc["source_types"], path, "source_types", nonempty=True, unique=True
    )
    if tuple(source_types) != _PARAMETER_SOURCE_TYPES:
        _reject("E_STATUS", path, "source_types")
    sensitivity_classes = _string_list(
        doc["sensitivity_classes"],
        path,
        "sensitivity_classes",
        nonempty=True,
        unique=True,
    )
    if tuple(sensitivity_classes) != _PARAMETER_SENSITIVITY:
        _reject("E_STATUS", path, "sensitivity_classes")
    current_statuses = _string_list(
        doc["current_statuses"],
        path,
        "current_statuses",
        nonempty=True,
        unique=True,
    )
    if tuple(current_statuses) != _PARAMETER_STATUSES:
        _reject("E_STATUS", path, "current_statuses")
    _text_object(
        doc["global_rules"],
        {"holdout", "narrow_dependence", "no_false_precision", "real_risk", "three_point_minimum"},
        path,
        "global_rules",
    )
    row_keys = {
        "affected_outputs",
        "basis",
        "current_status",
        "extreme_bounds",
        "initial_value",
        "module",
        "parameter_id",
        "reality_meaning",
        "reasonable_range",
        "sensitivity_class",
        "sensitivity_low_base_high",
        "source_type",
        "unit",
        "update_condition",
    }
    parameter_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["parameters"], path, "parameters", nonempty=True)):
        field = f"parameters[{index}]"
        obj = _exact_object(row, row_keys, path, field)
        parameter_ids.append(_text(obj["parameter_id"], path, f"{field}.parameter_id"))
        for key in row_keys - {"affected_outputs", "sensitivity_low_base_high"}:
            _text(obj[key], path, f"{field}.{key}")
        if obj["source_type"] not in source_types:
            _reject("E_STATUS", path, f"{field}.source_type")
        if obj["current_status"] not in current_statuses:
            _reject("E_STATUS", path, f"{field}.current_status")
        if obj["sensitivity_class"] not in sensitivity_classes:
            _reject("E_STATUS", path, f"{field}.sensitivity_class")
        _string_list(
            obj["affected_outputs"], path, f"{field}.affected_outputs", nonempty=True, unique=True
        )
        sensitivity = _string_list(
            obj["sensitivity_low_base_high"],
            path,
            f"{field}.sensitivity_low_base_high",
            nonempty=True,
        )
        if len(sensitivity) != 3:
            _reject("E_FIELD_EMPTY", path, f"{field}.sensitivity_low_base_high")
    _unique_values(parameter_ids, path, "parameters.parameter_id")


def _validate_sources(doc: dict[str, Any]) -> None:
    path = _SOURCE_PATH
    _text(doc["scope"], path, "scope")
    _text_object(
        doc["evidence_grade_definitions"], {"A", "B", "C", "D", "E"}, path, "evidence_grade_definitions"
    )
    axes = _exact_object(doc["status_axes"], set(_SOURCE_STATUS_AXES), path, "status_axes")
    for axis, expected in _SOURCE_STATUS_AXES.items():
        values = _string_list(
            axes[axis], path, f"status_axes.{axis}", nonempty=True, unique=True
        )
        if tuple(values) != expected:
            _reject("E_STATUS", path, f"status_axes.{axis}")
    _text(doc["global_admission_rule"], path, "global_admission_rule")

    row_keys = {
        "accessed_at",
        "adapter_boundary",
        "authority_grade",
        "authority_owner",
        "canonical_url",
        "claim_ids_contradicted",
        "claim_ids_supported",
        "clock_and_point_in_time_semantics",
        "content_digest_if_locally_preserved",
        "coverage_status",
        "cross_validation",
        "document_version_or_publication_date",
        "gap_semantics",
        "instrument_mapping",
        "integrity_status",
        "known_limitations",
        "license_or_terms_status",
        "next_gate",
        "pit_status",
        "replacement_or_usage_status",
        "revision_semantics",
        "revision_status",
        "schema_or_measurement_scope",
        "source_class",
        "source_id",
        "title",
    }
    source_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["sources"], path, "sources", nonempty=True)):
        field = f"sources[{index}]"
        obj = _exact_object(row, row_keys, path, field)
        source_ids.append(_text(obj["source_id"], path, f"{field}.source_id"))
        for key in row_keys - {
            "accessed_at",
            "claim_ids_contradicted",
            "claim_ids_supported",
            "content_digest_if_locally_preserved",
            "known_limitations",
        }:
            _text(obj[key], path, f"{field}.{key}")
        if not (
            obj["canonical_url"].startswith("https://")
            or obj["canonical_url"].startswith("http://")
        ):
            _reject("E_FIELD_TYPE", path, f"{field}.canonical_url")
        _utc(obj["accessed_at"], path, f"{field}.accessed_at")
        if obj["authority_grade"] not in {"A", "B", "C", "D", "E"}:
            _reject("E_STATUS", path, f"{field}.authority_grade")
        if obj["integrity_status"] not in axes["integrity"]:
            _reject("E_STATUS", path, f"{field}.integrity_status")
        if obj["coverage_status"] not in axes["coverage"]:
            _reject("E_STATUS", path, f"{field}.coverage_status")
        if obj["revision_status"] not in axes["revision"]:
            _reject("E_STATUS", path, f"{field}.revision_status")
        if obj["pit_status"] not in axes["pit"]:
            _reject("E_STATUS", path, f"{field}.pit_status")
        _string_list(
            obj["claim_ids_supported"],
            path,
            f"{field}.claim_ids_supported",
            nonempty=True,
            unique=True,
        )
        _string_list(
            obj["claim_ids_contradicted"],
            path,
            f"{field}.claim_ids_contradicted",
            nonempty=False,
            unique=True,
        )
        _string_list(
            obj["known_limitations"],
            path,
            f"{field}.known_limitations",
            nonempty=True,
        )
        digest = obj["content_digest_if_locally_preserved"]
        if digest is not None:
            _sha(digest, path, f"{field}.content_digest_if_locally_preserved")
    _unique_values(source_ids, path, "sources.source_id")


def _validate_disputes(doc: dict[str, Any]) -> None:
    path = _DISPUTE_PATH
    row_keys = {
        "affected_claim_ids",
        "affected_hypothesis_ids",
        "blocks",
        "category",
        "dispute_id",
        "evidence_refs",
        "next_test",
        "priority",
        "resolution",
        "statement",
        "status",
    }
    dispute_ids: list[str] = []
    for index, row in enumerate(_object_list(doc["disputes"], path, "disputes", nonempty=True)):
        field = f"disputes[{index}]"
        obj = _exact_object(row, row_keys, path, field)
        dispute_ids.append(_text(obj["dispute_id"], path, f"{field}.dispute_id"))
        for key in row_keys - {
            "affected_claim_ids",
            "affected_hypothesis_ids",
            "blocks",
            "evidence_refs",
        }:
            _text(obj[key], path, f"{field}.{key}")
        if obj["category"] not in _DISPUTE_CATEGORIES:
            _reject("E_STATUS", path, f"{field}.category")
        if obj["status"] not in _DISPUTE_STATUSES:
            _reject("E_STATUS", path, f"{field}.status")
        if obj["priority"] not in {"P0", "P1", "P2"}:
            _reject("E_STATUS", path, f"{field}.priority")
        for key in ("affected_claim_ids", "affected_hypothesis_ids", "blocks", "evidence_refs"):
            _string_list(obj[key], path, f"{field}.{key}", nonempty=True, unique=True)
    _unique_values(dispute_ids, path, "disputes.dispute_id")


def _validate_stage(doc: dict[str, Any]) -> None:
    path = _STAGE_PATH
    _exact_text(doc["route_id"], "RSR-P0-NEW-PROGRAM-ROUTE-v1", path, "route_id", "E_STAGE_AUTHORITY")
    _exact_text(doc["current_stage"], "RSR-P0", path, "current_stage", "E_STAGE_AUTHORITY")

    baseline_keys = {"path", "physical_sha256", "role", "state"}
    actual_baseline: dict[str, tuple[str, str, str]] = {}
    for index, row in enumerate(
        _object_list(doc["immutable_baseline"], path, "immutable_baseline", nonempty=True)
    ):
        field = f"immutable_baseline[{index}]"
        obj = _exact_object(row, baseline_keys, path, field)
        role = _text(obj["role"], path, f"{field}.role")
        if role in actual_baseline:
            _reject("E_ID_DUPLICATE", path, "immutable_baseline.role")
        actual_baseline[role] = (
            _text(obj["path"], path, f"{field}.path"),
            _sha(obj["physical_sha256"], path, f"{field}.physical_sha256"),
            _text(obj["state"], path, f"{field}.state"),
        )
    if actual_baseline != _IMMUTABLE_BASELINE:
        _reject("E_IMMUTABLE_BASELINE", path, "immutable_baseline")

    permissions = _exact_object(
        doc["permission_matrix"], set(_PERMISSION_MATRIX), path, "permission_matrix"
    )
    for key, expected in _PERMISSION_MATRIX.items():
        if _boolean(permissions[key], path, f"permission_matrix.{key}") is not expected:
            _reject("E_PERMISSION_MATRIX", path, f"permission_matrix.{key}")

    gate_keys = {
        "acceptance_owner",
        "deliverables",
        "gate_id",
        "permission_on_acceptance",
        "prerequisites",
        "status",
    }
    actual_gates: set[str] = set()
    actual_gate_order: list[str] = []
    for index, row in enumerate(_object_list(doc["gates"], path, "gates", nonempty=True)):
        field = f"gates[{index}]"
        obj = _exact_object(row, gate_keys, path, field)
        gate_id = _text(obj["gate_id"], path, f"{field}.gate_id")
        if gate_id in actual_gates:
            _reject("E_ID_DUPLICATE", path, "gates.gate_id")
        actual_gates.add(gate_id)
        actual_gate_order.append(gate_id)
        if gate_id not in _GATE_AUTHORITY:
            _reject("E_GATE_STATUS", path, f"{field}.gate_id")
        expected_status, expected_owner, expected_permission = _GATE_AUTHORITY[gate_id]
        for key, expected in (
            ("status", expected_status),
            ("acceptance_owner", expected_owner),
            ("permission_on_acceptance", expected_permission),
        ):
            _exact_text(obj[key], expected, path, f"{field}.{key}", "E_GATE_STATUS")
        prerequisites = _string_list(
            obj["prerequisites"],
            path,
            f"{field}.prerequisites",
            nonempty=True,
            unique=True,
        )
        deliverables = _string_list(
            obj["deliverables"],
            path,
            f"{field}.deliverables",
            nonempty=True,
            unique=True,
        )
        if tuple(prerequisites) != _GATE_CONTENT[gate_id]["prerequisites"]:
            _reject("E_GATE_STATUS", path, f"{field}.prerequisites")
        if tuple(deliverables) != _GATE_CONTENT[gate_id]["deliverables"]:
            _reject("E_GATE_STATUS", path, f"{field}.deliverables")
    if actual_gates != set(_GATE_AUTHORITY):
        _reject("E_GATE_STATUS", path, "gates")
    if tuple(actual_gate_order) != _GATE_ORDER:
        _reject("E_GATE_STATUS", path, "gates")

    role_keys = {"can_accept_own_candidate", "model", "role_id", "state"}
    role_ids: list[str] = []
    for index, row in enumerate(
        _object_list(doc["dynamic_roles"], path, "dynamic_roles", nonempty=True)
    ):
        field = f"dynamic_roles[{index}]"
        obj = _exact_object(row, role_keys, path, field)
        role_ids.append(_text(obj["role_id"], path, f"{field}.role_id"))
        _text(obj["model"], path, f"{field}.model")
        _text(obj["state"], path, f"{field}.state")
        if obj["model"] not in _ROLE_MODELS or obj["state"] not in _ROLE_STATES:
            _reject("E_STAGE_AUTHORITY", path, field)
        if _boolean(
            obj["can_accept_own_candidate"], path, f"{field}.can_accept_own_candidate"
        ):
            _reject("E_STAGE_AUTHORITY", path, f"{field}.can_accept_own_candidate")
    _unique_values(role_ids, path, "dynamic_roles.role_id")

    escalation = _exact_object(
        doc["escalation_rules"],
        {"immediate_stop", "no_sol_for", "sol_when"},
        path,
        "escalation_rules",
    )
    for key in ("immediate_stop", "no_sol_for", "sol_when"):
        _string_list(escalation[key], path, f"escalation_rules.{key}", nonempty=True)

    boundary = _exact_object(
        doc["claim_boundary"], set(_CLAIM_BOUNDARY), path, "claim_boundary"
    )
    for key, expected in _CLAIM_BOUNDARY.items():
        _exact_text(
            boundary[key], expected, path, f"claim_boundary.{key}", "E_PERMISSION_MATRIX"
        )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _validate_self_digest(doc: dict[str, Any], path: str) -> None:
    spec = _DOCUMENT_SPECS[path]
    digest_key = spec["digest_key"]
    unsigned = dict(doc)
    supplied = unsigned.pop(digest_key)
    calculated = hashlib.sha256(
        spec["domain"].encode("utf-8") + b"\0" + _canonical_bytes(unsigned)
    ).hexdigest()
    if supplied != calculated:
        _reject("E_SELF_DIGEST", path, digest_key)


def _decoded_normalized(value: str) -> str:
    decoded = value
    seen: set[str] = set()
    while decoded not in seen:
        seen.add(decoded)
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    normalized = unicodedata.normalize("NFKC", decoded).casefold().replace("\\", "/")
    return "".join(character for character in normalized if character.isalnum())


def _walk_candidate_identifiers(value: Any, field: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if type(value) is dict:
        for key, child in value.items():
            child_field = f"{field}.{key}"
            is_identifier = (
                key == "path"
                or key == "artifact_reference"
                or key.endswith("_id")
                or key.endswith("_ids")
            )
            if is_identifier:
                if type(child) is str:
                    found.append((child_field, child))
                elif type(child) is list:
                    found.extend(
                        (f"{child_field}[{index}]", item)
                        for index, item in enumerate(child)
                        if type(item) is str
                    )
            found.extend(_walk_candidate_identifiers(child, child_field))
    elif type(value) is list:
        for index, child in enumerate(value):
            found.extend(_walk_candidate_identifiers(child, f"{field}[{index}]"))
    return found


def _validate_aliases(docs: dict[str, dict[str, Any]]) -> None:
    for path, doc in docs.items():
        for field, value in _walk_candidate_identifiers(doc):
            if path == _STAGE_PATH and field.startswith("$.immutable_baseline["):
                continue
            compact = _decoded_normalized(value)
            if (
                "activeg1" in compact
                or "applicationsupport" in compact
                or "p1a" in compact
            ):
                _reject("E_ALIAS", path, field)


def _walk_strings(value: Any, field: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if type(value) is str:
        found.append((field, value))
    elif type(value) is dict:
        for key, child in value.items():
            found.extend(_walk_strings(child, f"{field}.{key}"))
    elif type(value) is list:
        for index, child in enumerate(value):
            found.extend(_walk_strings(child, f"{field}[{index}]"))
    return found


def _validate_cross_bindings(docs: dict[str, dict[str, Any]]) -> None:
    object_doc = docs[_OBJECT_PATH]
    hypothesis_doc = docs[_HYPOTHESIS_PATH]
    measurement_doc = docs[_MEASUREMENT_PATH]
    parameter_doc = docs[_PARAMETER_PATH]
    source_doc = docs[_SOURCE_PATH]
    dispute_doc = docs[_DISPUTE_PATH]

    claim_ids = {row["claim_id"] for row in object_doc["claims"]}
    hypothesis_ids = {row["hypothesis_id"] for row in hypothesis_doc["hypotheses"]}
    parameter_ids = {row["parameter_id"] for row in parameter_doc["parameters"]}
    for path, doc in docs.items():
        for field, text in _walk_strings(doc):
            if any(
                parameter_id not in parameter_ids
                for parameter_id in _PARAMETER_REF_RE.findall(text)
            ):
                _reject("E_PARAMETER_REF", path, field)

    for index, hypothesis in enumerate(hypothesis_doc["hypotheses"]):
        for claim_id in hypothesis["source_claim_ids"]:
            if claim_id not in claim_ids:
                _reject(
                    "E_CROSS_CLAIM",
                    _HYPOTHESIS_PATH,
                    f"hypotheses[{index}].source_claim_ids",
                )

    for index, source in enumerate(source_doc["sources"]):
        for key in ("claim_ids_supported", "claim_ids_contradicted"):
            if any(claim_id not in claim_ids for claim_id in source[key]):
                _reject("E_CROSS_CLAIM", _SOURCE_PATH, f"sources[{index}].{key}")

    for index, dispute in enumerate(dispute_doc["disputes"]):
        if any(claim_id not in claim_ids for claim_id in dispute["affected_claim_ids"]):
            _reject(
                "E_CROSS_CLAIM",
                _DISPUTE_PATH,
                f"disputes[{index}].affected_claim_ids",
            )
        if any(
            hypothesis_id not in hypothesis_ids
            for hypothesis_id in dispute["affected_hypothesis_ids"]
        ):
            _reject(
                "E_CROSS_HYPOTHESIS",
                _DISPUTE_PATH,
                f"disputes[{index}].affected_hypothesis_ids",
            )

    contracts_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for index, contract in enumerate(measurement_doc["contracts"]):
        hypothesis_id = contract["hypothesis_id"]
        if hypothesis_id not in hypothesis_ids:
            _reject(
                "E_MEASUREMENT_BINDING",
                _MEASUREMENT_PATH,
                f"contracts[{index}].hypothesis_id",
            )
        contracts_by_hypothesis.setdefault(hypothesis_id, []).append(contract)
        if any(
            parameter_id not in parameter_ids
            for parameter_id in contract["sensitivity_parameter_ids"]
        ):
            _reject(
                "E_PARAMETER_REF",
                _MEASUREMENT_PATH,
                f"contracts[{index}].sensitivity_parameter_ids",
            )

    for index, hypothesis in enumerate(hypothesis_doc["hypotheses"]):
        matches = contracts_by_hypothesis.get(hypothesis["hypothesis_id"], [])
        if (
            len(matches) != 1
            or matches[0]["measurement_contract_id"]
            != hypothesis["measurement_contract_id"]
        ):
            _reject(
                "E_MEASUREMENT_BINDING",
                _HYPOTHESIS_PATH,
                f"hypotheses[{index}].measurement_contract_id",
            )
    if len(measurement_doc["contracts"]) != len(hypothesis_doc["hypotheses"]):
        _reject("E_MEASUREMENT_BINDING", _MEASUREMENT_PATH, "contracts")


def _bundle_digest(docs: dict[str, dict[str, Any]]) -> str:
    manifest = [
        {
            "path": path,
            "self_digest": docs[path][_DOCUMENT_SPECS[path]["digest_key"]],
        }
        for path in sorted(_REQUIRED_PATHS)
    ]
    return hashlib.sha256(
        b"msta-hed/research-system-contract-bundle/v1\0" + _canonical_bytes(manifest)
    ).hexdigest()


def validate_research_system_bundle(raw_by_path: Mapping[str, str]) -> dict[str, Any]:
    """Validate the complete seven-document bundle without performing I/O.

    The public boundary is total and fail-closed: every input either returns an
    ACCEPTED result or a stable REJECTED result; malformed caller objects and
    unexpected internal exceptions never escape.
    """

    try:
        if not isinstance(raw_by_path, Mapping):
            raise _ContractError("E_INPUT_TYPE", field="$")
        actual_paths = list(raw_by_path.keys())
        if any(type(path) is not str for path in actual_paths):
            raise _ContractError("E_INPUT_TYPE", field="$")
        actual_set = frozenset(actual_paths)
        if actual_set != _REQUIRED_PATHS or len(actual_paths) != len(_REQUIRED_PATHS):
            missing = sorted(_REQUIRED_PATHS - actual_set)
            extra = sorted(actual_set - _REQUIRED_PATHS)
            details: dict[str, str] = {}
            if missing:
                details["missing"] = missing[0]
            if extra:
                details["extra"] = extra[0]
            raise _ContractError("E_FILE_SET", **details)

        docs: dict[str, dict[str, Any]] = {}
        for path in sorted(_REQUIRED_PATHS):
            raw = raw_by_path[path]
            if type(raw) is not str:
                _reject("E_RAW_TYPE", path)
            docs[path] = _parse_json(path, raw)

        for path in sorted(_REQUIRED_PATHS):
            _validate_common_metadata(docs[path], path)
        _validate_object_dictionary(docs[_OBJECT_PATH])
        _validate_hypotheses(docs[_HYPOTHESIS_PATH])
        _validate_measurements(docs[_MEASUREMENT_PATH])
        _validate_parameters(docs[_PARAMETER_PATH])
        _validate_sources(docs[_SOURCE_PATH])
        _validate_disputes(docs[_DISPUTE_PATH])
        _validate_stage(docs[_STAGE_PATH])
        for path in sorted(_REQUIRED_PATHS):
            _validate_self_digest(docs[path], path)
        _validate_aliases(docs)
        _validate_cross_bindings(docs)

        return {
            "status": "ACCEPTED",
            "reason_code": "OK",
            "details": {
                "document_count": len(_REQUIRED_PATHS),
                "validated_paths": sorted(_REQUIRED_PATHS),
            },
            "bundle_digest": _bundle_digest(docs),
        }
    except _ContractError as exc:
        return {
            "status": "REJECTED",
            "reason_code": exc.reason_code,
            "details": exc.details,
            "bundle_digest": None,
        }
    except Exception as exc:  # Total fail-closed public boundary.
        return {
            "status": "REJECTED",
            "reason_code": "E_INTERNAL_TOTALITY",
            "details": {"error_type": type(exc).__name__},
            "bundle_digest": None,
        }
