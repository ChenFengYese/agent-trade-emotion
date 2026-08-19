"""Versioned semantic-boundary successor for the frozen v1 research bundle.

This module performs no filesystem, network, data, adapter, backtest, paper, or
execution I/O.  It first delegates the seven frozen predecessor documents to the
public v1 validator, then enforces the externally fixed REWORK_LOCAL overlay and
the exact clean-E0 nested semantic ceiling.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from trade_system.research_system_contract_v1 import (
    validate_research_system_bundle as _validate_v1_bundle,
)

__all__ = ["validate_research_system_bundle_v1_1"]


_OBJECT_PATH = "config/research_system.object_dictionary.v1.json"
_HYPOTHESIS_PATH = "config/research_system.hypothesis_validation_queue.v1.json"
_MEASUREMENT_PATH = "config/research_system.measurement_contract.v1.json"
_PARAMETER_PATH = "config/research_system.parameter_registry.v1.json"
_SOURCE_PATH = "config/research_system.source_authority_registry.v1.json"
_DISPUTE_PATH = "config/research_system.dispute_registry.v1.json"
_STAGE_PATH = "config/research_system.stage_contract.v1.json"
_OVERLAY_PATH = "config/research_system.semantic_claim_boundary.v1_1.json"

_V1_PATHS = frozenset(
    {
        _OBJECT_PATH,
        _HYPOTHESIS_PATH,
        _MEASUREMENT_PATH,
        _PARAMETER_PATH,
        _SOURCE_PATH,
        _DISPUTE_PATH,
        _STAGE_PATH,
    }
)
_REQUIRED_PATHS = _V1_PATHS | {_OVERLAY_PATH}

_PREDECESSOR_PHYSICAL_SHA256 = {
    _OBJECT_PATH: "9a167daea7bf05d1022e65da40be5b87786139a9e0f74d52994cbc2fd4915fff",
    _HYPOTHESIS_PATH: "e76ab11983326ab53d209b6efd362deb91a00215a0c47b14d5930457c614b4cb",
    _MEASUREMENT_PATH: "2e8d162f9be5182fbe25fd4e5d0c96fd817edc010b92ac61aa03f991aac20651",
    _PARAMETER_PATH: "a5321385626f2acd67063fed1cf8138b400c5911265ad333aed4da3958ca2a26",
    _SOURCE_PATH: "693cc7361c16fb154df97bf2c58a1e68807f990dc976df949658e7ce635abb12",
    _DISPUTE_PATH: "ae137bcb46051dd7ddb0b71f8c2b01390fcf9ff21d3d409fc7776ef1cb791ba3",
    _STAGE_PATH: "ab81251c0ea70e945d9ea7176e9cb59e7353477212dcf36a2d9e4424f944674b",
}
_PREDECESSOR_BUNDLE_DIGEST = (
    "c4eb9da641ee6a8f2971d06174f9eaa2c970122fa106acc9a2e8f584833b085d"
)

_OVERLAY_ID = "MSTA_HED_RESEARCH_SYSTEM_SEMANTIC_CLAIM_BOUNDARY.v1_1"
_OVERLAY_SCHEMA = "research-system-semantic-claim-boundary.v1_1"
_OVERLAY_STATUS = "REWORK_LOCAL_SUCCESSOR_CANDIDATE_E0_ONLY"
_OVERLAY_EVIDENCE = "E0_STATIC_SEMANTIC_BOUNDARY_NO_MARKET_PROOF"
_OVERLAY_DOMAIN = "msta-hed/research-system-semantic-claim-boundary/v1_1"
_OVERLAY_DIGEST_FIELD = "overlay_sha256"

_INITIAL_SOL_AUTHORITY = {
    "decision_id": "SOL_RESEARCH_SYSTEM_RECONSTRUCTION.v1",
    "decision_state": "AUTHORIZED_P0_E0_RESEARCH_SYSTEM_RECONSTRUCTION",
    "path": "config/sol_decision.research-system-reconstruction.v1.json",
    "physical_sha256": "2cf37e54989d3fd09846cacdbe622de26a4c0bd60e46cb0650f67b2827bf5586",
    "canonical_sha256": "2a434f542f58c6d43798e1562b7f203336eae7e5db4b6745095e3c9e7633ddb6",
}
_FAILED_GATE_AUTHORITY = {
    "decision_id": "SOL_RESEARCH_SYSTEM_RECONSTRUCTION_P0_GATE.v1",
    "decision_state": "REWORK_LOCAL",
    "path": "config/sol_decision.research-system-reconstruction-p0-gate.v1.json",
    "physical_sha256": "368dba95967e6abb85119728b1637a115c2c4553b39f3782db9c44b9dfd3a473",
    "canonical_sha256": "45f2f9a3a7040a552b25e7249bd29c2e13de66277bacbd4266978cc6a0aa2482",
}
_FROZEN_INVENTORY_AUTHORITY = {
    "inventory_id": "MSTA_HED_RESEARCH_SYSTEM_P0_ARTIFACT_INVENTORY.v1",
    "status": "REVIEW_READY_CANDIDATE_AWAITING_EXTERNAL_SOL_GATE",
    "path": "config/research_system.p0_artifact_inventory.v1.json",
    "artifact_count": 21,
    "physical_sha256": "bfffb9eda8e3cb5a4e0b562bbf532b0e9e72fff3f6064c82ee66a719c29af29c",
    "canonical_sha256": "a64d0036f08f6849619562a0079d03ea64f436518eefa41b3fe5b48cdd3acf30",
}
_PREDECESSOR_BUNDLE_AUTHORITY = {
    "schema_version": "research-system-contract-bundle.v1",
    "document_count": 7,
    "bundle_digest": _PREDECESSOR_BUNDLE_DIGEST,
}

_CLAIM_EVIDENCE_STATUS = (
    "CONFIRMED_CONSTRAINT",
    "QUEUED_HYPOTHESIS",
    "TEMPORARILY_SUPPORTED",
)
_HYPOTHESIS_EVIDENCE_LEVEL = (
    "E0_CONFIRMED_CAUSAL_CONSTRAINT_EFFECT_SIZE_UNTESTED",
    "E0_STRICT_VERSION_UNTESTED_PRIOR_PROXY_INCONCLUSIVE",
    "E0_UNTESTED",
    "E0_UNTESTED_HIGH_PRIORITY",
    "E0_USER_CLARIFICATION",
    "E0_USER_EXPERIENCE_DERIVED_UNTESTED",
)
_SOURCE_INTEGRITY_STATUS = ("DOCUMENT_IDENTITY_DISCOVERED",)
_SOURCE_COVERAGE_STATUS = (
    "UNKNOWN_NOT_ACQUIRED",
    "NOT_APPLICABLE_TARGET_DATA",
)
_SOURCE_REVISION_STATUS = (
    "UNKNOWN_NOT_VERIFIED",
    "PUBLISHED_VERSION_IDENTIFIED",
)
_SOURCE_PIT_STATUS = (
    "DOCUMENT_SEMANTICS_ONLY",
    "NOT_MARKET_DATA_SOURCE",
)
_SOURCE_USAGE_STATUS = (
    "DISCOVERED_NOT_ACQUIRED_NOT_ADMITTED",
    "DISCOVERED_NO_ENTITLEMENT_NO_PURCHASE",
    "METHOD_EVIDENCE_DISCOVERED",
    "THEORY_EVIDENCE_DISCOVERED_NOT_TARGET_VALIDATION",
)
_TRUSTED_SEMANTIC_CEILINGS = {
    "claim_evidence_status": _CLAIM_EVIDENCE_STATUS,
    "hypothesis_evidence_level": _HYPOTHESIS_EVIDENCE_LEVEL,
    "source_integrity_status": _SOURCE_INTEGRITY_STATUS,
    "source_coverage_status": _SOURCE_COVERAGE_STATUS,
    "source_revision_status": _SOURCE_REVISION_STATUS,
    "source_pit_status": _SOURCE_PIT_STATUS,
    "source_usage_status": _SOURCE_USAGE_STATUS,
}

_STAGE_DENIALS = {
    "D0": "DENIED",
    "D1": "DENIED",
    "D2": "DENIED",
    "D3": "DENIED",
    "E2": "DENIED",
    "E3": "DENIED",
}
_CLAIM_BOUNDARY = {
    "p0_design_package": "VERSIONED_SUCCESSOR_CANDIDATE_NOT_ACCEPTED",
    "semantic_contract_scope": "E0_NESTED_CLAIM_MONOTONICITY_ONLY",
    "source_data_validity": "NOT_EVALUATED",
    "market_validity": "NOT_EVALUATED",
    "predictive_validity": "NOT_EVALUATED",
    "profitability": "NOT_EVALUATED",
    "historical_data_acquisition": "NOT_AUTHORIZED",
    "backtest": "NOT_AUTHORIZED",
    "paper": "NOT_AUTHORIZED",
    "deployment": "DENIED",
    "trading": "DENIED",
    "maximum_positive_claim": (
        "The v1.1 overlay only enforces the exact clean E0 nested semantic ceiling "
        "over the frozen v1 predecessor; it does not accept P0 or authorize data, "
        "backtest, paper, deployment or trading."
    ),
}

_TOP_LEVEL_KEYS = frozenset(
    {
        "overlay_id",
        "schema_version",
        "created_at",
        "status",
        "evidence_level",
        "authority_binding",
        "trusted_semantic_ceilings",
        "stage_denials",
        "claim_boundary",
        "canonicalization",
        "overlay_sha256",
    }
)
_CANONICALIZATION = {
    "algorithm": "SHA-256",
    "domain": _OVERLAY_DOMAIN,
    "formula": (
        "SHA256(domain_prefix_utf8 || HEX(domain_separator_hex) || canonical_json_utf8)"
    ),
    "domain_prefix_utf8": _OVERLAY_DOMAIN,
    "domain_separator_hex": "00",
    "exclude_fields": [_OVERLAY_DIGEST_FIELD],
    "ensure_ascii": True,
    "sort_keys": True,
    "separators": [",", ":"],
    "encoding": "UTF-8",
}

_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class _BoundaryError(Exception):
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


def _reject(reason_code: str, path: str = "", field: str = "", **extra: str) -> None:
    details = dict(extra)
    if path:
        details["path"] = path
    if field:
        details["field"] = field
    raise _BoundaryError(reason_code, **details)


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise _NonFiniteNumber


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


def _strict_parse(path: str, raw: str) -> dict[str, Any]:
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


def _boundary_parse_or_none(raw: Any) -> dict[str, Any] | None:
    if type(raw) is not str:
        return None
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except Exception:
        return None
    return value if type(value) is dict else None


def _exact_object(value: Any, keys: set[str] | frozenset[str], field: str) -> dict[str, Any]:
    if type(value) is not dict:
        _reject("E_FIELD_TYPE", _OVERLAY_PATH, field)
    actual = frozenset(value)
    expected = frozenset(keys)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        suffix = extra[0] if extra else missing[0]
        _reject(
            "E_UNKNOWN_FIELD" if extra else "E_FIELD_EMPTY",
            _OVERLAY_PATH,
            f"{field}.{suffix}",
        )
    return value


def _text(value: Any, field: str) -> str:
    if type(value) is not str:
        _reject("E_FIELD_TYPE", _OVERLAY_PATH, field)
    if not value.strip():
        _reject("E_FIELD_EMPTY", _OVERLAY_PATH, field)
    return value


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        _reject("E_FIELD_TYPE", _OVERLAY_PATH, field)
    return value


def _sha(value: Any, field: str) -> str:
    text = _text(value, field)
    if not _SHA_RE.fullmatch(text):
        _reject("E_SHA256", _OVERLAY_PATH, field)
    return text


def _utc(value: Any, field: str) -> None:
    text = _text(value, field)
    if not _UTC_RE.fullmatch(text):
        _reject("E_CLOCK", _OVERLAY_PATH, field)
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject("E_CLOCK", _OVERLAY_PATH, field)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _validate_authority_record(
    value: Any, expected: dict[str, Any], field: str
) -> None:
    record = _exact_object(value, set(expected), field)
    for key, expected_value in expected.items():
        child_field = f"{field}.{key}"
        if key.endswith("_sha256") or key == "bundle_digest":
            _sha(record[key], child_field)
        elif type(expected_value) is int:
            _integer(record[key], child_field)
        else:
            _text(record[key], child_field)
        if type(record[key]) is not type(expected_value) or record[key] != expected_value:
            _reject("E_AUTHORITY_BINDING", _OVERLAY_PATH, child_field)


def _validate_overlay(doc: dict[str, Any]) -> str:
    _exact_object(doc, _TOP_LEVEL_KEYS, "$")
    expected_metadata = {
        "overlay_id": _OVERLAY_ID,
        "schema_version": _OVERLAY_SCHEMA,
        "status": _OVERLAY_STATUS,
        "evidence_level": _OVERLAY_EVIDENCE,
    }
    for key, expected in expected_metadata.items():
        _text(doc[key], key)
        if doc[key] != expected:
            _reject("E_AUTHORITY_BINDING", _OVERLAY_PATH, key)
    _utc(doc["created_at"], "created_at")

    authority = _exact_object(
        doc["authority_binding"],
        {
            "initial_sol_decision",
            "failed_p0_gate_decision",
            "frozen_p0_inventory",
            "predecessor_bundle",
        },
        "authority_binding",
    )
    _validate_authority_record(
        authority["initial_sol_decision"],
        _INITIAL_SOL_AUTHORITY,
        "authority_binding.initial_sol_decision",
    )
    _validate_authority_record(
        authority["failed_p0_gate_decision"],
        _FAILED_GATE_AUTHORITY,
        "authority_binding.failed_p0_gate_decision",
    )
    _validate_authority_record(
        authority["frozen_p0_inventory"],
        _FROZEN_INVENTORY_AUTHORITY,
        "authority_binding.frozen_p0_inventory",
    )
    _validate_authority_record(
        authority["predecessor_bundle"],
        _PREDECESSOR_BUNDLE_AUTHORITY,
        "authority_binding.predecessor_bundle",
    )

    ceilings = _exact_object(
        doc["trusted_semantic_ceilings"],
        set(_TRUSTED_SEMANTIC_CEILINGS),
        "trusted_semantic_ceilings",
    )
    for key, expected in _TRUSTED_SEMANTIC_CEILINGS.items():
        value = ceilings[key]
        if type(value) is not list:
            _reject("E_FIELD_TYPE", _OVERLAY_PATH, f"trusted_semantic_ceilings.{key}")
        for index, item in enumerate(value):
            _text(item, f"trusted_semantic_ceilings.{key}[{index}]")
        if tuple(value) != expected:
            _reject(
                "E_AUTHORITY_BINDING",
                _OVERLAY_PATH,
                f"trusted_semantic_ceilings.{key}",
            )

    denials = _exact_object(doc["stage_denials"], set(_STAGE_DENIALS), "stage_denials")
    for key, expected in _STAGE_DENIALS.items():
        _text(denials[key], f"stage_denials.{key}")
        if denials[key] != expected:
            _reject("E_STAGE_DENIAL", _OVERLAY_PATH, f"stage_denials.{key}")

    boundary = _exact_object(
        doc["claim_boundary"], set(_CLAIM_BOUNDARY), "claim_boundary"
    )
    for key, expected in _CLAIM_BOUNDARY.items():
        _text(boundary[key], f"claim_boundary.{key}")
        if boundary[key] != expected:
            _reject("E_STAGE_DENIAL", _OVERLAY_PATH, f"claim_boundary.{key}")

    canonicalization = _exact_object(
        doc["canonicalization"], set(_CANONICALIZATION), "canonicalization"
    )
    for key, expected in _CANONICALIZATION.items():
        value = canonicalization[key]
        if type(value) is not type(expected) or value != expected:
            _reject("E_CANONICALIZATION", _OVERLAY_PATH, f"canonicalization.{key}")

    supplied = _sha(doc[_OVERLAY_DIGEST_FIELD], _OVERLAY_DIGEST_FIELD)
    unsigned = dict(doc)
    unsigned.pop(_OVERLAY_DIGEST_FIELD)
    calculated = hashlib.sha256(
        _OVERLAY_DOMAIN.encode("utf-8") + b"\0" + _canonical_bytes(unsigned)
    ).hexdigest()
    if supplied != calculated:
        _reject("E_SELF_DIGEST", _OVERLAY_PATH, _OVERLAY_DIGEST_FIELD)
    return supplied


def _nested_boundary_violation(
    base_raw: Mapping[str, Any],
) -> tuple[str, str] | None:
    object_doc = _boundary_parse_or_none(base_raw.get(_OBJECT_PATH))
    hypothesis_doc = _boundary_parse_or_none(base_raw.get(_HYPOTHESIS_PATH))
    source_doc = _boundary_parse_or_none(base_raw.get(_SOURCE_PATH))
    if object_doc is None or hypothesis_doc is None or source_doc is None:
        return None

    claims = object_doc.get("claims")
    hypotheses = hypothesis_doc.get("hypotheses")
    sources = source_doc.get("sources")
    if type(claims) is not list or type(hypotheses) is not list or type(sources) is not list:
        return None

    for index, claim in enumerate(claims):
        if type(claim) is not dict:
            return None
        value = claim.get("evidence_status")
        if type(value) is not str or value not in _CLAIM_EVIDENCE_STATUS:
            return _OBJECT_PATH, f"claims[{index}].evidence_status"

    for index, hypothesis in enumerate(hypotheses):
        if type(hypothesis) is not dict:
            return None
        value = hypothesis.get("evidence_level")
        if type(value) is not str or value not in _HYPOTHESIS_EVIDENCE_LEVEL:
            return _HYPOTHESIS_PATH, f"hypotheses[{index}].evidence_level"

    source_fields = {
        "integrity_status": _SOURCE_INTEGRITY_STATUS,
        "coverage_status": _SOURCE_COVERAGE_STATUS,
        "revision_status": _SOURCE_REVISION_STATUS,
        "pit_status": _SOURCE_PIT_STATUS,
        "replacement_or_usage_status": _SOURCE_USAGE_STATUS,
    }
    for index, source in enumerate(sources):
        if type(source) is not dict:
            return None
        for key, allowed in source_fields.items():
            value = source.get(key)
            if type(value) is not str or value not in allowed:
                return _SOURCE_PATH, f"sources[{index}].{key}"
    return None


def _successor_bundle_digest(overlay_digest: str) -> str:
    manifest = [
        {
            "component": "frozen_predecessor_bundle",
            "digest": _PREDECESSOR_BUNDLE_DIGEST,
        },
        {
            "component": "semantic_claim_boundary_overlay",
            "path": _OVERLAY_PATH,
            "digest": overlay_digest,
        },
    ]
    return hashlib.sha256(
        b"msta-hed/research-system-contract-bundle/v1_1\0"
        + _canonical_bytes(manifest)
    ).hexdigest()


def validate_research_system_bundle_v1_1(
    raw_by_path: Mapping[str, str],
) -> dict[str, Any]:
    """Validate the frozen v1 bundle plus its REWORK_LOCAL semantic overlay."""

    try:
        if not isinstance(raw_by_path, Mapping):
            raise _BoundaryError("E_INPUT_TYPE", field="$")
        actual_paths = list(raw_by_path.keys())
        if any(type(path) is not str for path in actual_paths):
            raise _BoundaryError("E_INPUT_TYPE", field="$")
        actual_set = frozenset(actual_paths)
        if actual_set != _REQUIRED_PATHS or len(actual_paths) != len(_REQUIRED_PATHS):
            missing = sorted(_REQUIRED_PATHS - actual_set)
            extra = sorted(actual_set - _REQUIRED_PATHS)
            details: dict[str, str] = {}
            if missing:
                details["missing"] = missing[0]
            if extra:
                details["extra"] = extra[0]
            raise _BoundaryError("E_FILE_SET", **details)

        base_raw = {path: raw_by_path[path] for path in _V1_PATHS}
        v1_result = _validate_v1_bundle(base_raw)

        nested_violation = _nested_boundary_violation(base_raw)
        if nested_violation is not None:
            path, field = nested_violation
            _reject("E_NESTED_CLAIM_BOUNDARY", path, field)
        if v1_result.get("status") != "ACCEPTED":
            _reject(
                "E_V1_BASE_CONTRACT",
                v1_reason_code=str(v1_result.get("reason_code", "UNKNOWN")),
            )
        if v1_result.get("bundle_digest") != _PREDECESSOR_BUNDLE_DIGEST:
            _reject("E_PREDECESSOR_BUNDLE", field="bundle_digest")

        for path, expected_sha in _PREDECESSOR_PHYSICAL_SHA256.items():
            raw = base_raw[path]
            if type(raw) is not str:
                _reject("E_V1_BASE_CONTRACT", path, v1_reason_code="E_RAW_TYPE")
            if hashlib.sha256(raw.encode("utf-8")).hexdigest() != expected_sha:
                _reject("E_PREDECESSOR_BYTES", path)

        overlay_raw = raw_by_path[_OVERLAY_PATH]
        if type(overlay_raw) is not str:
            _reject("E_RAW_TYPE", _OVERLAY_PATH)
        overlay = _strict_parse(_OVERLAY_PATH, overlay_raw)
        overlay_digest = _validate_overlay(overlay)

        return {
            "status": "ACCEPTED",
            "reason_code": "OK",
            "details": {
                "document_count": len(_REQUIRED_PATHS),
                "predecessor_bundle_digest": _PREDECESSOR_BUNDLE_DIGEST,
                "overlay_digest": overlay_digest,
                "stage_denials": dict(_STAGE_DENIALS),
            },
            "bundle_digest": _successor_bundle_digest(overlay_digest),
        }
    except _BoundaryError as exc:
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
