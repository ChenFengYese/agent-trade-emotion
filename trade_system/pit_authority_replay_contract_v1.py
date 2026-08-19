"""Pure, total E0 contract validator for the independent PITAR1 candidate.

This module intentionally performs no filesystem, network, environment, wall
clock, randomness, or subprocess operations.  Every public validator receives
all candidate material explicitly and returns a structured fail-closed result.
It validates synthetic semantics only and cannot authorize any later stage.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_ZERO_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

ROUTE_AUTHORITY = {
    "route_id": "RSR-PITAR1-POINT_IN_TIME-AUTHORITY-REPLAY-v1",
    "route_version": "1.0.0",
    "decision_id": "SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_ROUTE.v1",
    "decision_physical_sha256": "a3dcb124477ac4f54189d659b7438431ea62ba6785f4c248fe2448e55f28035f",
    "decision_canonical_sha256": "7e141bd47a728078c3a4dca02d231eae2bcbe6a3f12ff39c6e01c37e92556932",
    "cwd": "/Users/wt/Documents/agent-trade-emotion",
    "branch": "codex/s0-research-foundation",
    "head": "7ca3fc4f99a57f98217e703f222b295653ace87e",
}

CONTRACT_DOCUMENTS = {
    "config/pit_authority_replay.authority_bundle_contract.v1.json": {
        "domain": "pitar1/authority-bundle-contract/v1",
        "digest": "5352ece7122480723cfc069b987663ccb089a5887688e30f52204e3179c3f722",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "external_authority_bindings",
            "authority_identity_types",
            "authority_bundle_schema",
            "admission_receipt_schema",
            "raw_byte_contract",
            "external_pinning_rules",
            "validator_profile",
            "permission_ceiling",
            "canonicalization",
            "contract_sha256",
        },
    },
    "config/pit_authority_replay.pit_admission_contract.v1.json": {
        "domain": "pitar1/pit-admission-contract/v1",
        "digest": "4a0e5715b0fcb97917149a0fabfd489318f31c0580e5896ee90e71d51cbaa3e5",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "admission_mode",
            "row_identity_schema",
            "clock_schema",
            "available_at_contract",
            "revision_contract",
            "as_of_selection_contract",
            "duplicate_conflict_contract",
            "coverage_contract",
            "quarantine_contract",
            "permission_ceiling",
            "canonicalization",
            "contract_sha256",
        },
    },
    "config/pit_authority_replay.source_inventory.v1.json": {
        "domain": "pitar1/source-inventory-contract/v1",
        "digest": "32764ee39297ddcb9f64ef32f0a5734a34f085045f14087e3cc886e597f6f9b8",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "source_discovery_binding",
            "discovery_policy",
            "source_dispositions",
            "d0_plan_candidate",
            "global_disposition",
            "canonicalization",
            "contract_sha256",
        },
    },
    "config/pit_authority_replay.chronology_contract.v1.json": {
        "domain": "pitar1/chronology-contract/v1",
        "digest": "40338cbac39e4a25ebdab9e710fcb11370c95e929acfc0ea62a9ec292a7ca913",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "current_route_role",
            "permanently_seen_or_excluded",
            "role_values",
            "first_access_contract",
            "role_lock_contract",
            "window_contract",
            "permission_ceiling",
            "canonicalization",
            "contract_sha256",
        },
    },
    "config/pit_authority_replay.adapter_replay_contract.v1.json": {
        "domain": "pitar1/adapter-replay-contract/v1",
        "digest": "2da2595895f27029d970217b5d34e91285159b74aaf7fd0c77c15ce84f0e3550",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "adapter_interface",
            "normalized_row_schema",
            "adapter_forbidden_operations",
            "replay_interface",
            "receipt_chain_schema",
            "bar_and_outcome_contract",
            "gap_contract",
            "permission_ceiling",
            "canonicalization",
            "contract_sha256",
        },
    },
    "config/pit_authority_replay.development_comparison_contract.v1.json": {
        "domain": "pitar1/development-comparison-contract/v1",
        "digest": "bb4046b84f18ab5fd368e3cec658aae6c197abaac34ca1871206972aab2998c3",
        "top_keys": {
            "schema_version",
            "contract_id",
            "namespace",
            "artifact_role",
            "stage",
            "route_binding",
            "d3_boundary",
            "policy_ids",
            "dynamic_policy_binding",
            "common_information_contract",
            "opportunity_denominator_contract",
            "trajectory_schema",
            "evaluation_boundary",
            "permission_ceiling",
            "canonicalization",
            "contract_sha256",
        },
    },
}

SOURCE_DISCOVERY_DOCUMENT = {
    "path": "artifacts/pit_authority_replay_source_discovery.v1.json",
    "domain": "pitar1/source-discovery-record/v1",
    "digest": "7aecbf426befa8efae10e55e4998fb5431d172b7a7b4a27372971af2119f2d10",
    "top_keys": {
        "schema_version",
        "record_id",
        "namespace",
        "artifact_role",
        "status",
        "route_binding",
        "discovery_method",
        "resource_caps",
        "sources",
        "summary",
        "claim_boundary",
        "canonicalization",
        "record_sha256",
    },
}

_COVERAGE_STATES = {
    "CONTINUOUS_OBSERVED",
    "MARKET_INACTIVE_PROVEN",
    "SEQUENCE_GAP",
    "SOURCE_OUTAGE",
    "ACQUISITION_FAILURE",
    "SCHEDULED_NON_PUBLICATION",
    "CENSORED_OBSERVATION",
    "UNKNOWN_COVERAGE",
    "QUARANTINED",
}
_OPERATIONS = {"INITIAL", "CORRECT", "RETRACT", "TOMBSTONE", "REINSTATE"}
_POLICIES = (
    "DYNAMIC_MULTI_PATH",
    "FROZEN_ENTRY_STATIC_EXIT",
    "SINGLE_PATH",
    "NO_TRADE",
)
_ROW_FIELDS = {
    "source_id",
    "authority_grade",
    "instrument_id",
    "source_event_id",
    "event_id",
    "logical_id",
    "revision_id",
    "supersedes_revision_id",
    "operation",
    "revision_ordinal",
    "revision_fork_id",
    "event_time",
    "published_at",
    "received_at",
    "ingested_at",
    "admission_validated_at",
    "available_at",
    "raw_artifact_sha256",
    "raw_byte_offset_or_member_id",
    "payload_sha256",
    "parser_version",
    "source_sequence",
    "source_sequence_kind",
    "coverage_state",
}
_BUNDLE_FIELDS = {
    "bundle_id",
    "route_id",
    "plan_id",
    "lane",
    "source_authority",
    "artifact_authority",
    "transform_authority",
    "proof_authority",
    "tip_authority",
    "coverage_state",
    "revision_chain_sha256",
    "created_at",
    "bundle_sha256",
}
_RECEIPT_FIELDS = {
    "receipt_id",
    "admission_id",
    "bundle_sha256",
    "raw_artifact_sha256",
    "raw_byte_length",
    "payload_sha256",
    "source_authority_sha256",
    "schema_sha256",
    "transform_sha256",
    "parser_sha256",
    "proof_sha256",
    "tip_sha256",
    "coverage_state",
    "revision_chain_sha256",
    "admission_validated_at",
    "decision_at",
    "permission",
    "action",
    "max_risk",
    "receipt_sha256",
}
_SOURCE_AUTHORITY_FIELDS = {
    "authority_id",
    "authority_grade",
    "authority_owner",
    "source_contract_id",
    "source_contract_sha256",
    "terms_id",
    "terms_sha256",
}
_ARTIFACT_AUTHORITY_FIELDS = {
    "artifact_id",
    "plan_id",
    "raw_artifact_sha256",
    "raw_byte_length",
    "compressed_sha256",
    "member_sha256",
    "member_id",
}
_TRANSFORM_AUTHORITY_FIELDS = {
    "schema_id",
    "schema_sha256",
    "transform_id",
    "transform_sha256",
    "parser_id",
    "parser_sha256",
}
_PROOF_AUTHORITY_FIELDS = {"proof_id", "proof_sha256", "proof_kind"}
_TIP_AUTHORITY_FIELDS = {
    "tip_id",
    "tip_sha256",
    "committed_at",
    "valid_from",
    "valid_until",
}
_PROOF_FIELDS = {
    "proof_id",
    "proof_sha256",
    "coverage_state",
    "source_event_id",
    "logical_id",
    "decision_at",
    "evidence_available_at",
}


class _Failure(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _result(status: str, reason_code: str, **details: Any) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason_code,
        "permission": "DENIED",
        "action": "ABSTAIN",
        "max_risk": 0,
        "details": details,
    }


def _fail(code: str, detail: str = "") -> None:
    raise _Failure(code, detail)


def _pin(label: str) -> str:
    return hashlib.sha256(b"pitar1/external-synthetic-pin/v1\x00" + label.encode("utf-8")).hexdigest()


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> Any:
    _fail("NONFINITE_NUMBER", token)


def _walk_json(value: Any, pointer: str = "") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("NONFINITE_NUMBER", pointer)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_json(item, f"{pointer}/{index}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("JSON_KEY_TYPE", pointer)
            _walk_json(item, f"{pointer}/{key}")
        return
    _fail("UNSUPPORTED_JSON_TYPE", pointer)


def _parse_json(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _fail("INVALID_UTF8")
    elif isinstance(raw, str):
        text = raw
    else:
        _fail("DOCUMENT_TYPE")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
        )
    except _Failure:
        raise
    except (ValueError, TypeError) as exc:
        _fail("INVALID_JSON", str(exc))
    if not isinstance(value, dict):
        _fail("DOCUMENT_ROOT_TYPE")
    _walk_json(value)
    return value


def _canonical_bytes(document: Mapping[str, Any], digest_field: str) -> bytes:
    unsigned = dict(document)
    unsigned.pop(digest_field, None)
    return json.dumps(
        unsigned,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def domain_digest(domain: str, document: Mapping[str, Any], digest_field: str) -> str:
    """Return the domain-separated canonical digest without reading external state."""
    return hashlib.sha256(
        domain.encode("utf-8") + b"\x00" + _canonical_bytes(document, digest_field)
    ).hexdigest()


def _require_exact_keys(value: Any, fields: set[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(code, "not_object")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        _fail(code, f"missing={missing};extra={extra}")
    return value


def _require_string(value: Any, code: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        _fail(code)
    return value


def _require_int(value: Any, code: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(code)
    if minimum is not None and value < minimum:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    value = _require_string(value, code)
    if not _HEX64.fullmatch(value):
        _fail(code)
    return value


def _require_identifier(value: Any, code: str) -> str:
    value = _require_string(value, code)
    if not _IDENTIFIER.fullmatch(value):
        _fail(code)
    return value


def _parse_time(value: Any, code: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    text = _require_string(value, code)
    if not text.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.tzinfo != timezone.utc:
        _fail(code)
    return parsed


def _contains_forbidden_alias(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower().replace("\\", "/")
        return (
            "application support" in lowered
            or "active-g1" in lowered
            or "active_g1" in lowered
            or "/active/g1" in lowered
            or ".." in lowered
        )
    if isinstance(value, list):
        return any(_contains_forbidden_alias(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_forbidden_alias(key) or _contains_forbidden_alias(item)
            for key, item in value.items()
        )
    return False


def _route_fields_match(route_binding: Mapping[str, Any]) -> bool:
    for key, value in route_binding.items():
        if key in ROUTE_AUTHORITY and ROUTE_AUTHORITY[key] != value:
            return False
    return route_binding.get("route_id") == ROUTE_AUTHORITY["route_id"]


def validate_pitar1_contract_bundle(
    raw_documents: Mapping[str, str | bytes] | Sequence[tuple[str, str | bytes]],
    external_route_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact six-document E0 contract bundle.

    The result can only be a local review candidate.  It is never an acceptance
    or permission decision.
    """
    try:
        if not isinstance(external_route_authority, dict) or dict(external_route_authority) != ROUTE_AUTHORITY:
            _fail("EXTERNAL_ROUTE_AUTHORITY_MISMATCH")
        if isinstance(raw_documents, dict):
            items = list(raw_documents.items())
        elif isinstance(raw_documents, Sequence) and not isinstance(raw_documents, (str, bytes)):
            items = list(raw_documents)
        else:
            _fail("DOCUMENT_SET_TYPE")
        normalized: dict[str, str | bytes] = {}
        for item in items:
            if not isinstance(item, tuple) or len(item) != 2:
                _fail("DOCUMENT_ENTRY_TYPE")
            path, raw = item
            if not isinstance(path, str):
                _fail("DOCUMENT_PATH_TYPE")
            if path in normalized:
                _fail("DUPLICATE_DOCUMENT_PATH", path)
            normalized[path] = raw
        expected_paths = set(CONTRACT_DOCUMENTS)
        if set(normalized) != expected_paths:
            _fail(
                "DOCUMENT_SET_MISMATCH",
                f"missing={sorted(expected_paths-set(normalized))};extra={sorted(set(normalized)-expected_paths)}",
            )
        verified: dict[str, str] = {}
        for path in sorted(normalized):
            profile = CONTRACT_DOCUMENTS[path]
            document = _parse_json(normalized[path])
            _require_exact_keys(document, profile["top_keys"], "TOP_LEVEL_SCHEMA_MISMATCH")
            if document.get("namespace") != "pitar1":
                _fail("NAMESPACE_MISMATCH", path)
            route_binding = document.get("route_binding")
            if not isinstance(route_binding, dict) or not _route_fields_match(route_binding):
                _fail("ROUTE_BINDING_MISMATCH", path)
            canonicalization = document.get("canonicalization")
            if not isinstance(canonicalization, dict):
                _fail("CANONICALIZATION_MISMATCH", path)
            expected_canonicalization = {
                "algorithm": "SHA-256",
                "encoding": "UTF-8",
                "ensure_ascii": True,
                "sort_keys": True,
                "separators": [",", ":"],
                "domain_prefix_utf8": profile["domain"],
                "domain_separator_hex": "00",
                "digest_field": "contract_sha256",
                "excluded_fields": ["contract_sha256"],
            }
            if canonicalization != expected_canonicalization:
                _fail("CANONICALIZATION_MISMATCH", path)
            supplied_digest = _require_hash(document.get("contract_sha256"), "CONTRACT_DIGEST_TYPE")
            computed_digest = domain_digest(profile["domain"], document, "contract_sha256")
            if supplied_digest != computed_digest:
                _fail("CONTRACT_SELF_DIGEST_MISMATCH", path)
            if supplied_digest != profile["digest"]:
                _fail("PINNED_CONTRACT_DIGEST_MISMATCH", path)
            if path == "config/pit_authority_replay.source_inventory.v1.json":
                disposition = document.get("global_disposition")
                if not isinstance(disposition, dict) or (
                    disposition.get("d0_activation") != "DENIED"
                    or disposition.get("candidate_may_accept_itself") is not False
                    or disposition.get("real_action") != "ABSTAIN"
                    or disposition.get("real_max_risk") != 0
                    or disposition.get("trading") != "DENIED"
                ):
                    _fail("PERMISSION_ESCALATION", path)
            else:
                permission = document.get("permission_ceiling")
                if not isinstance(permission, dict):
                    _fail("PERMISSION_CEILING_MISSING", path)
                if (
                    permission.get("real_action") != "ABSTAIN"
                    or permission.get("real_max_risk") != 0
                    or any(
                        value not in {"DENIED", "ABSTAIN", 0}
                        for key, value in permission.items()
                        if key not in {"real_action", "real_max_risk"}
                    )
                ):
                    _fail("PERMISSION_ESCALATION", path)
            verified[path] = supplied_digest
        return _result(
            "VALID_E0_CANDIDATE",
            "LOCAL_REVIEW_READY_NOT_ACCEPTED",
            document_count=len(verified),
            verified_contract_digests=verified,
            external_stage_gate_required=True,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:  # total fail-closed boundary
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_source_discovery_document(
    raw_document: str | bytes,
    external_route_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the frozen documentation-only discovery record."""
    try:
        if not isinstance(external_route_authority, dict) or dict(external_route_authority) != ROUTE_AUTHORITY:
            _fail("EXTERNAL_ROUTE_AUTHORITY_MISMATCH")
        document = _parse_json(raw_document)
        _require_exact_keys(document, SOURCE_DISCOVERY_DOCUMENT["top_keys"], "TOP_LEVEL_SCHEMA_MISMATCH")
        if document.get("namespace") != "pitar1" or document.get("status") != "WAIT_DATA":
            _fail("DISCOVERY_DISPOSITION_MISMATCH")
        if not _route_fields_match(document.get("route_binding", {})):
            _fail("ROUTE_BINDING_MISMATCH")
        sources = document.get("sources")
        if not isinstance(sources, list) or len(sources) != 9:
            _fail("DISCOVERY_SOURCE_SET_MISMATCH")
        if any(not isinstance(item, dict) or item.get("d0_disposition") != "WAIT_DATA" for item in sources):
            _fail("DISCOVERY_READY_WITH_UNKNOWNS")
        summary = document.get("summary")
        if not isinstance(summary, dict) or (
            summary.get("source_count"),
            summary.get("ready_count"),
            summary.get("wait_data_count"),
        ) != (9, 0, 9):
            _fail("DISCOVERY_SUMMARY_MISMATCH")
        method = document.get("discovery_method")
        if not isinstance(method, dict) or (
            method.get("market_or_macro_rows_accessed") is not False
            or method.get("archive_or_bulk_objects_accessed") is not False
            or method.get("authenticated_or_paid_access_used") is not False
            or method.get("builder_network_requests") != 0
        ):
            _fail("DISCOVERY_SCOPE_ESCALATION")
        canonicalization = document.get("canonicalization")
        expected = {
            "algorithm": "SHA-256",
            "encoding": "UTF-8",
            "ensure_ascii": True,
            "sort_keys": True,
            "separators": [",", ":"],
            "domain_prefix_utf8": SOURCE_DISCOVERY_DOCUMENT["domain"],
            "domain_separator_hex": "00",
            "digest_field": "record_sha256",
            "excluded_fields": ["record_sha256"],
        }
        if canonicalization != expected:
            _fail("CANONICALIZATION_MISMATCH")
        supplied = _require_hash(document.get("record_sha256"), "DISCOVERY_DIGEST_TYPE")
        computed = domain_digest(SOURCE_DISCOVERY_DOCUMENT["domain"], document, "record_sha256")
        if supplied != computed:
            _fail("DISCOVERY_SELF_DIGEST_MISMATCH")
        if supplied != SOURCE_DISCOVERY_DOCUMENT["digest"]:
            _fail("PINNED_DISCOVERY_DIGEST_MISMATCH")
        return _result(
            "WAIT_DATA",
            "DOCUMENT_DISCOVERY_VALID_NO_D0_PERMISSION",
            source_count=9,
            ready_count=0,
            market_or_macro_rows_accessed=False,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def synthetic_raw_bytes(profile: str = "nonempty") -> bytes:
    if profile == "nonempty":
        return b"PITAR1 independent synthetic raw fixture\n"
    if profile == "zero":
        return b""
    raise ValueError("unknown synthetic profile")


def _synthetic_authority_profile(profile: str) -> dict[str, Any]:
    raw = synthetic_raw_bytes(profile)
    raw_sha = hashlib.sha256(raw).hexdigest()
    return {
        "authority_set_id": f"pitar1.synthetic-authority.{profile}.v1",
        "route_id": ROUTE_AUTHORITY["route_id"],
        "plan_id": f"pitar1-synthetic-{profile}-plan-v1",
        "lane": "SYNTHETIC_E0",
        "coverage_state": "CONTINUOUS_OBSERVED",
        "revision_chain_sha256": _pin(f"{profile}/revision-chain"),
        "source_authority": {
            "authority_id": f"pitar1.synthetic-source.{profile}.v1",
            "authority_grade": "A",
            "authority_owner": "PITAR1_SYNTHETIC_ONLY",
            "source_contract_id": f"pitar1.synthetic-source-contract.{profile}.v1",
            "source_contract_sha256": _pin(f"{profile}/source-contract"),
            "terms_id": f"pitar1.synthetic-terms.{profile}.v1",
            "terms_sha256": _pin(f"{profile}/terms"),
        },
        "artifact_authority": {
            "artifact_id": f"pitar1-synthetic-artifact-{profile}-v1",
            "plan_id": f"pitar1-synthetic-{profile}-plan-v1",
            "raw_artifact_sha256": raw_sha,
            "raw_byte_length": len(raw),
            "compressed_sha256": _pin(f"{profile}/compressed-container"),
            "member_sha256": raw_sha,
            "member_id": f"pitar1-synthetic-member-{profile}-v1",
        },
        "transform_authority": {
            "schema_id": f"pitar1.synthetic-schema.{profile}.v1",
            "schema_sha256": _pin(f"{profile}/schema"),
            "transform_id": f"pitar1.synthetic-transform.{profile}.v1",
            "transform_sha256": _pin(f"{profile}/transform"),
            "parser_id": f"pitar1.synthetic-parser.{profile}.v1",
            "parser_sha256": _pin(f"{profile}/parser"),
        },
        "proof_authority": {
            "proof_id": f"pitar1.synthetic-proof.{profile}.v1",
            "proof_sha256": _pin(f"{profile}/proof"),
            "proof_kind": "SYNTHETIC_CONTINUOUS_COVERAGE",
        },
        "tip_authority": {
            "tip_id": f"pitar1.synthetic-tip.{profile}.v1",
            "tip_sha256": _pin(f"{profile}/tip"),
            "committed_at": "2024-06-01T00:00:00Z",
            "valid_from": "2024-06-01T00:00:00Z",
            "valid_until": "2024-07-01T00:00:00Z",
        },
    }


_SYNTHETIC_AUTHORITY_PROFILES = {
    name: _synthetic_authority_profile(name) for name in ("nonempty", "zero")
}


def synthetic_external_authority(profile: str = "nonempty") -> dict[str, Any]:
    """Return a copy of one validator-pinned E0 synthetic authority profile."""
    if profile not in _SYNTHETIC_AUTHORITY_PROFILES:
        raise ValueError("unknown synthetic profile")
    return deepcopy(_SYNTHETIC_AUTHORITY_PROFILES[profile])


def _authority_profile_matches(external_authority: Any) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(external_authority, dict):
        _fail("EXTERNAL_AUTHORITY_TYPE")
    for profile, pinned in _SYNTHETIC_AUTHORITY_PROFILES.items():
        if external_authority == pinned:
            return profile, pinned
    _fail("EXTERNAL_AUTHORITY_NOT_PINNED")


def _validate_row(row: Any) -> tuple[Mapping[str, Any], dict[str, datetime | None]]:
    row = _require_exact_keys(row, _ROW_FIELDS, "ROW_SCHEMA_INVALID")
    for field in (
        "source_id",
        "instrument_id",
        "source_event_id",
        "event_id",
        "logical_id",
        "revision_id",
        "revision_fork_id",
        "parser_version",
    ):
        _require_identifier(row[field], "ROW_IDENTIFIER_INVALID")
    if row["supersedes_revision_id"] is not None:
        _require_identifier(row["supersedes_revision_id"], "ROW_IDENTIFIER_INVALID")
    if row["authority_grade"] not in {"A", "B"}:
        _fail("ROW_AUTHORITY_GRADE_INVALID")
    if row["operation"] not in _OPERATIONS:
        _fail("ROW_OPERATION_INVALID")
    _require_int(row["revision_ordinal"], "ROW_REVISION_ORDINAL_INVALID", minimum=0)
    _require_int(row["source_sequence"], "ROW_SOURCE_SEQUENCE_INVALID", minimum=0)
    if row["source_sequence_kind"] not in {"NATIVE", "LOCAL_RECEIPT_ORDINAL"}:
        _fail("ROW_SOURCE_SEQUENCE_KIND_INVALID")
    if row["coverage_state"] not in _COVERAGE_STATES:
        _fail("ROW_COVERAGE_STATE_INVALID")
    _require_hash(row["raw_artifact_sha256"], "ROW_RAW_HASH_INVALID")
    _require_hash(row["payload_sha256"], "ROW_PAYLOAD_HASH_INVALID")
    offset = row["raw_byte_offset_or_member_id"]
    if isinstance(offset, bool) or not isinstance(offset, (int, str)):
        _fail("ROW_OFFSET_INVALID")
    if isinstance(offset, int) and offset < 0:
        _fail("ROW_OFFSET_INVALID")
    if isinstance(offset, str):
        _require_identifier(offset, "ROW_OFFSET_INVALID")
    clocks = {
        "event_time": _parse_time(row["event_time"], "CLOCK_INVALID"),
        "published_at": _parse_time(row["published_at"], "CLOCK_INVALID", nullable=True),
        "received_at": _parse_time(row["received_at"], "CLOCK_INVALID"),
        "ingested_at": _parse_time(row["ingested_at"], "CLOCK_INVALID"),
        "admission_validated_at": _parse_time(row["admission_validated_at"], "CLOCK_INVALID"),
        "available_at": _parse_time(row["available_at"], "CLOCK_INVALID"),
    }
    if not clocks["received_at"] <= clocks["ingested_at"] <= clocks["admission_validated_at"]:
        _fail("CLOCK_ORDER_INVALID")
    knowledge_clocks = [
        clocks["received_at"],
        clocks["ingested_at"],
        clocks["admission_validated_at"],
    ]
    if clocks["published_at"] is not None:
        knowledge_clocks.append(clocks["published_at"])
    if clocks["available_at"] != max(knowledge_clocks):
        _fail("AVAILABLE_AT_NOT_CONSERVATIVE_MAX")
    if clocks["event_time"] > clocks["available_at"]:
        _fail("EVENT_AFTER_AVAILABILITY")
    return row, clocks


def validate_admission_fixture(
    raw_documents: Mapping[str, str | bytes] | Sequence[tuple[str, str | bytes]],
    external_route_authority: Mapping[str, Any],
    supplied_raw_bytes: bytes,
    external_authority: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a caller-supplied synthetic admission candidate fail-closed."""
    bundle_result = validate_pitar1_contract_bundle(raw_documents, external_route_authority)
    if bundle_result["status"] != "VALID_E0_CANDIDATE":
        return _result("REJECT", "CONTRACT_BUNDLE_NOT_VALID", nested=bundle_result["reason_code"])
    try:
        profile, pinned = _authority_profile_matches(external_authority)
        if not isinstance(supplied_raw_bytes, bytes):
            _fail("RAW_BYTES_TYPE")
        candidate = _require_exact_keys(
            candidate,
            {"authority_bundle", "raw_record", "coverage_proof", "admission_receipt"},
            "ADMISSION_CANDIDATE_SCHEMA_INVALID",
        )
        if _contains_forbidden_alias(candidate):
            _fail("FORBIDDEN_ALIAS")
        bundle = _require_exact_keys(candidate["authority_bundle"], _BUNDLE_FIELDS, "BUNDLE_SCHEMA_INVALID")
        _require_identifier(bundle["bundle_id"], "BUNDLE_IDENTIFIER_INVALID")
        if bundle["route_id"] != ROUTE_AUTHORITY["route_id"]:
            _fail("BUNDLE_ROUTE_MISMATCH")
        for field in (
            "plan_id",
            "lane",
            "coverage_state",
            "revision_chain_sha256",
            "source_authority",
            "artifact_authority",
            "transform_authority",
            "proof_authority",
            "tip_authority",
        ):
            if bundle[field] != pinned[field]:
                _fail("BUNDLE_EXTERNAL_AUTHORITY_MISMATCH", field)
        bundle_created_at = _parse_time(bundle["created_at"], "BUNDLE_CREATED_AT_INVALID")
        _require_exact_keys(bundle["source_authority"], _SOURCE_AUTHORITY_FIELDS, "SOURCE_AUTHORITY_SCHEMA_INVALID")
        _require_exact_keys(bundle["artifact_authority"], _ARTIFACT_AUTHORITY_FIELDS, "ARTIFACT_AUTHORITY_SCHEMA_INVALID")
        _require_exact_keys(bundle["transform_authority"], _TRANSFORM_AUTHORITY_FIELDS, "TRANSFORM_AUTHORITY_SCHEMA_INVALID")
        _require_exact_keys(bundle["proof_authority"], _PROOF_AUTHORITY_FIELDS, "PROOF_AUTHORITY_SCHEMA_INVALID")
        _require_exact_keys(bundle["tip_authority"], _TIP_AUTHORITY_FIELDS, "TIP_AUTHORITY_SCHEMA_INVALID")
        expected_bundle_digest = domain_digest(
            "pitar1/synthetic-authority-bundle/v1", bundle, "bundle_sha256"
        )
        if _require_hash(bundle["bundle_sha256"], "BUNDLE_DIGEST_INVALID") != expected_bundle_digest:
            _fail("BUNDLE_DIGEST_MISMATCH")

        row, clocks = _validate_row(candidate["raw_record"])
        raw_sha = hashlib.sha256(supplied_raw_bytes).hexdigest()
        if raw_sha != pinned["artifact_authority"]["raw_artifact_sha256"]:
            _fail("RAW_EXTERNAL_IDENTITY_MISMATCH")
        if len(supplied_raw_bytes) != pinned["artifact_authority"]["raw_byte_length"]:
            _fail("RAW_LENGTH_MISMATCH")
        if len(supplied_raw_bytes) == 0 and raw_sha != _ZERO_SHA256:
            _fail("ZERO_BYTE_HASH_MISMATCH")
        if row["raw_artifact_sha256"] != raw_sha or row["payload_sha256"] != raw_sha:
            _fail("RAW_OR_PAYLOAD_HASH_MISMATCH")
        if row["parser_version"] != pinned["transform_authority"]["parser_id"]:
            _fail("PARSER_IDENTITY_MISMATCH")
        if row["coverage_state"] != pinned["coverage_state"]:
            _fail("COVERAGE_AUTHORITY_MISMATCH")

        proof = _require_exact_keys(candidate["coverage_proof"], _PROOF_FIELDS, "COVERAGE_PROOF_SCHEMA_INVALID")
        if proof["proof_id"] != pinned["proof_authority"]["proof_id"]:
            _fail("PROOF_AUTHORITY_MISMATCH")
        if proof["proof_sha256"] != pinned["proof_authority"]["proof_sha256"]:
            _fail("PROOF_AUTHORITY_MISMATCH")
        if proof["coverage_state"] != pinned["coverage_state"]:
            _fail("PROOF_COVERAGE_MISMATCH")
        if proof["source_event_id"] != row["source_event_id"] or proof["logical_id"] != row["logical_id"]:
            _fail("PROOF_RECORD_BINDING_MISMATCH")
        decision_at = _parse_time(proof["decision_at"], "PROOF_DECISION_TIME_INVALID")
        evidence_at = _parse_time(proof["evidence_available_at"], "PROOF_EVIDENCE_TIME_INVALID")
        if evidence_at > decision_at:
            _fail("FUTURE_EVIDENCE")
        if bundle_created_at > decision_at:
            _fail("FUTURE_BUNDLE")

        tip = pinned["tip_authority"]
        committed_at = _parse_time(tip["committed_at"], "TIP_CLOCK_INVALID")
        valid_from = _parse_time(tip["valid_from"], "TIP_CLOCK_INVALID")
        valid_until = _parse_time(tip["valid_until"], "TIP_CLOCK_INVALID")
        if committed_at > decision_at or not (valid_from <= decision_at < valid_until):
            _fail("FUTURE_OR_INACTIVE_TIP")
        if clocks["available_at"] > decision_at:
            _fail("FUTURE_ROW")

        receipt = _require_exact_keys(candidate["admission_receipt"], _RECEIPT_FIELDS, "RECEIPT_SCHEMA_INVALID")
        _require_identifier(receipt["receipt_id"], "RECEIPT_IDENTIFIER_INVALID")
        _require_identifier(receipt["admission_id"], "ADMISSION_IDENTIFIER_INVALID")
        _require_int(receipt["raw_byte_length"], "RECEIPT_RAW_LENGTH_INVALID", minimum=0)
        _require_int(receipt["max_risk"], "RECEIPT_MAX_RISK_INVALID", minimum=0)
        if receipt["bundle_sha256"] != bundle["bundle_sha256"]:
            _fail("RECEIPT_BUNDLE_MISMATCH")
        source_authority_sha = domain_digest(
            "pitar1/source-authority/v1",
            bundle["source_authority"],
            "__no_digest_field__",
        )
        expected_bindings = {
            "raw_artifact_sha256": raw_sha,
            "raw_byte_length": len(supplied_raw_bytes),
            "payload_sha256": raw_sha,
            "source_authority_sha256": source_authority_sha,
            "schema_sha256": pinned["transform_authority"]["schema_sha256"],
            "transform_sha256": pinned["transform_authority"]["transform_sha256"],
            "parser_sha256": pinned["transform_authority"]["parser_sha256"],
            "proof_sha256": pinned["proof_authority"]["proof_sha256"],
            "tip_sha256": pinned["tip_authority"]["tip_sha256"],
            "coverage_state": pinned["coverage_state"],
            "revision_chain_sha256": pinned["revision_chain_sha256"],
            "admission_validated_at": row["admission_validated_at"],
            "decision_at": proof["decision_at"],
            "permission": "DENIED",
            "action": "ABSTAIN",
            "max_risk": 0,
        }
        for field, expected_value in expected_bindings.items():
            if receipt[field] != expected_value:
                _fail("RECEIPT_BINDING_MISMATCH", field)
        expected_receipt_digest = domain_digest(
            "pitar1/synthetic-admission-receipt/v1", receipt, "receipt_sha256"
        )
        if _require_hash(receipt["receipt_sha256"], "RECEIPT_DIGEST_INVALID") != expected_receipt_digest:
            _fail("RECEIPT_DIGEST_MISMATCH")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "SYNTHETIC_ADMISSION_SEMANTICS_VALID_NOT_ACCEPTED",
            profile=profile,
            raw_sha256=raw_sha,
            raw_byte_length=len(supplied_raw_bytes),
            available_at=row["available_at"],
            decision_at=proof["decision_at"],
            external_stage_gate_required=True,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_revision_fixture(rows: Any, decision_at: Any) -> dict[str, Any]:
    """Validate synthetic revision, duplicate, ordering, and coverage semantics."""
    try:
        decision_time = _parse_time(decision_at, "DECISION_TIME_INVALID")
        if not isinstance(rows, list):
            _fail("REVISION_FIXTURE_TYPE")
        parsed: list[tuple[Mapping[str, Any], dict[str, datetime | None]]] = []
        exact_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
        for candidate in rows:
            row, clocks = _validate_row(candidate)
            identity = (row["source_id"], row["event_id"])
            previous = exact_by_identity.get(identity)
            if previous is not None:
                if previous == row:
                    continue
                return _result(
                    "SUSPEND",
                    "IDENTITY_PAYLOAD_CONFLICT",
                    quarantine=True,
                    denominator_retained=True,
                    conflicting_identity=list(identity),
                )
            exact_by_identity[identity] = row
            parsed.append((row, clocks))
        by_logical: dict[str, list[Mapping[str, Any]]] = {}
        for row, _ in parsed:
            by_logical.setdefault(row["logical_id"], []).append(row)
        for logical_id, chain in by_logical.items():
            ordered = sorted(chain, key=lambda item: (item["revision_ordinal"], item["revision_id"]))
            fork_keys: set[tuple[int, str | None]] = set()
            for row in chain:
                fork_key = (row["revision_ordinal"], row["supersedes_revision_id"])
                if fork_key in fork_keys:
                    return _result(
                        "SUSPEND",
                        "REVISION_FORK_CONFLICT",
                        quarantine=True,
                        denominator_retained=True,
                        logical_id=logical_id,
                    )
                fork_keys.add(fork_key)
            seen_revisions: set[str] = set()
            previous_revision: str | None = None
            for index, row in enumerate(ordered):
                if row["revision_id"] in seen_revisions:
                    _fail("REVISION_ID_DUPLICATE", logical_id)
                seen_revisions.add(row["revision_id"])
                if index == 0:
                    if row["revision_ordinal"] != 0 or row["operation"] != "INITIAL":
                        _fail("REVISION_GENESIS_INVALID", logical_id)
                    if row["supersedes_revision_id"] is not None:
                        _fail("REVISION_GENESIS_INVALID", logical_id)
                else:
                    if row["revision_ordinal"] != index:
                        _fail("REVISION_ORDINAL_GAP", logical_id)
                    if row["supersedes_revision_id"] != previous_revision:
                        _fail("REVISION_CHAIN_INVALID", logical_id)
                    if row["operation"] == "INITIAL":
                        _fail("REVISION_OPERATION_INVALID", logical_id)
                previous_revision = row["revision_id"]
        replay = sorted(
            (row for row, _ in parsed),
            key=lambda item: (item["available_at"], item["source_sequence"], item["event_id"]),
        )
        visible = [row for row in replay if _parse_time(row["available_at"], "CLOCK_INVALID") <= decision_time]
        suspending_states = {
            "SEQUENCE_GAP",
            "SOURCE_OUTAGE",
            "ACQUISITION_FAILURE",
            "CENSORED_OBSERVATION",
            "UNKNOWN_COVERAGE",
            "QUARANTINED",
        }
        has_suspending_state = any(row["coverage_state"] in suspending_states for row in visible)
        return _result(
            "SUSPEND" if has_suspending_state else "VALID_E0_SYNTHETIC_FIXTURE",
            "TYPED_COVERAGE_RETAINED" if has_suspending_state else "REVISION_REPLAY_SEMANTICS_VALID",
            input_count=len(rows),
            unique_effect_count=len(parsed),
            visible_event_ids=[row["event_id"] for row in visible],
            replay_order=[row["event_id"] for row in replay],
            denominator_count=len(visible),
            denominator_retained=True,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_chronology_fixture(windows: Any) -> dict[str, Any]:
    """Validate synthetic half-open window and immutable-role assertions."""
    try:
        if not isinstance(windows, list):
            _fail("CHRONOLOGY_FIXTURE_TYPE")
        exact_fields = {"window_id", "start_inclusive", "end_exclusive", "role", "accessed"}
        parsed: list[tuple[datetime, datetime, Mapping[str, Any]]] = []
        seen_ids: set[str] = set()
        allowed_roles = {
            "ENGINEERING_REPLAY_QA_ONLY",
            "DEVELOPMENT_SEEN",
            "CALIBRATION_RESERVED_UNSEEN",
            "ONE_TIME_HOLDOUT_RESERVED_UNSEEN",
            "READ_ONLY_NEGATIVE_AUDIT_ONLY",
            "EXCLUDED",
        }
        jan_start = _parse_time("2025-01-01T00:00:00Z", "CLOCK_INVALID")
        mar_start = _parse_time("2025-03-01T00:00:00Z", "CLOCK_INVALID")
        isolated_start = _parse_time("2026-07-23T00:00:00Z", "CLOCK_INVALID")
        isolated_end = _parse_time("2026-07-30T00:00:00Z", "CLOCK_INVALID")
        for item in windows:
            item = _require_exact_keys(item, exact_fields, "CHRONOLOGY_WINDOW_SCHEMA_INVALID")
            window_id = _require_identifier(item["window_id"], "CHRONOLOGY_WINDOW_ID_INVALID")
            if window_id in seen_ids:
                _fail("CHRONOLOGY_WINDOW_ID_DUPLICATE")
            seen_ids.add(window_id)
            start = _parse_time(item["start_inclusive"], "CHRONOLOGY_CLOCK_INVALID")
            end = _parse_time(item["end_exclusive"], "CHRONOLOGY_CLOCK_INVALID")
            if start >= end:
                _fail("CHRONOLOGY_INTERVAL_INVALID")
            if item["role"] not in allowed_roles or not isinstance(item["accessed"], bool):
                _fail("CHRONOLOGY_ROLE_INVALID")
            if item["accessed"] and item["role"] in {
                "CALIBRATION_RESERVED_UNSEEN",
                "ONE_TIME_HOLDOUT_RESERVED_UNSEEN",
            }:
                _fail("SEEN_ROLE_RELABELING")
            overlaps_consumed = start < mar_start and end > jan_start
            if overlaps_consumed and item["role"] in {
                "CALIBRATION_RESERVED_UNSEEN",
                "ONE_TIME_HOLDOUT_RESERVED_UNSEEN",
            }:
                _fail("CONSUMED_WINDOW_REUSE")
            if start < isolated_end and end > isolated_start:
                _fail("ISOLATED_SCOPE_OVERLAP")
            parsed.append((start, end, item))
        parsed.sort(key=lambda entry: (entry[0], entry[1], entry[2]["window_id"]))
        for left, right in zip(parsed, parsed[1:]):
            if left[1] > right[0]:
                _fail("CHRONOLOGY_OVERLAP")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "CHRONOLOGY_SEMANTICS_VALID",
            window_count=len(parsed),
            ordered_window_ids=[item["window_id"] for _, _, item in parsed],
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_adapter_fixture(fixture: Any) -> dict[str, Any]:
    """Validate a non-executing future adapter/replay interface assertion."""
    try:
        fields = {
            "fixture_id",
            "fixture_kind",
            "request_fields",
            "result_fields",
            "sort_key",
            "observed_operations",
            "runtime_executed",
            "permission",
            "action",
            "max_risk",
        }
        fixture = _require_exact_keys(fixture, fields, "ADAPTER_FIXTURE_SCHEMA_INVALID")
        _require_identifier(fixture["fixture_id"], "ADAPTER_FIXTURE_ID_INVALID")
        if fixture["fixture_kind"] != "SYNTHETIC_INTERFACE_ASSERTION":
            _fail("ADAPTER_FIXTURE_KIND_INVALID")
        expected_request = [
            "request_id",
            "plan_id",
            "artifact_id",
            "admission_receipt_sha256",
            "schema_sha256",
            "transform_sha256",
            "parser_sha256",
            "prior_cursor_sha256",
            "decision_at",
        ]
        expected_result = [
            "result_id",
            "request_id",
            "record_digests",
            "coverage_event_digests",
            "quarantine_event_digests",
            "next_cursor_sha256",
            "adapter_receipt_sha256",
            "result_class",
        ]
        if fixture["request_fields"] != expected_request or fixture["result_fields"] != expected_result:
            _fail("ADAPTER_FIELD_SET_MISMATCH")
        if fixture["sort_key"] != ["available_at", "source_sequence", "event_id"]:
            _fail("REPLAY_ORDER_MISMATCH")
        if not isinstance(fixture["observed_operations"], list):
            _fail("ADAPTER_OPERATIONS_TYPE")
        forbidden = {
            "NETWORK_ACCESS",
            "FILESYSTEM_DISCOVERY",
            "ENVIRONMENT_ACCESS",
            "WALL_CLOCK_ACCESS",
            "RANDOMNESS",
            "SUBPROCESS_ACCESS",
            "IMPUTATION",
            "FORWARD_FILL",
            "ZERO_FILL",
            "FEATURE_OR_OUTCOME_LABEL",
            "PREDICTION_OR_UTILITY",
            "CURRENT_REVISION_BACKFILL",
        }
        if any(operation in forbidden for operation in fixture["observed_operations"]):
            _fail("ADAPTER_FORBIDDEN_OPERATION")
        if (
            fixture["runtime_executed"] is not False
            or fixture["permission"] != "DENIED"
            or fixture["action"] != "ABSTAIN"
        ):
            _fail("ADAPTER_RUNTIME_OR_PERMISSION_ESCALATION")
        if _require_int(fixture["max_risk"], "ADAPTER_MAX_RISK_INVALID", minimum=0) != 0:
            _fail("ADAPTER_RUNTIME_OR_PERMISSION_ESCALATION")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "ADAPTER_INTERFACE_ONLY_VALID_NOT_EXECUTED",
            runtime_executed=False,
            sort_key=fixture["sort_key"],
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_replay_receipt_fixture(receipts: Any) -> dict[str, Any]:
    """Validate a synthetic domain-separated replay receipt chain."""
    try:
        fields = {
            "replay_receipt_id",
            "prior_replay_receipt_sha256",
            "admitted_artifact_set_sha256",
            "adapter_version_sha256",
            "configuration_sha256",
            "first_event_key",
            "last_event_key",
            "event_count",
            "state_transition_sha256",
            "created_at",
            "replay_receipt_sha256",
        }
        if not isinstance(receipts, list) or not receipts:
            _fail("REPLAY_RECEIPT_FIXTURE_TYPE")
        prior_digest: str | None = None
        seen_ids: set[str] = set()
        seen_digests: set[str] = set()
        for index, item in enumerate(receipts):
            item = _require_exact_keys(item, fields, "REPLAY_RECEIPT_SCHEMA_INVALID")
            receipt_id = _require_identifier(
                item["replay_receipt_id"], "REPLAY_RECEIPT_ID_INVALID"
            )
            if receipt_id in seen_ids:
                _fail("REPLAY_RECEIPT_ID_DUPLICATE")
            seen_ids.add(receipt_id)
            if index == 0:
                if item["prior_replay_receipt_sha256"] is not None:
                    _fail("REPLAY_RECEIPT_GENESIS_INVALID")
            elif item["prior_replay_receipt_sha256"] != prior_digest:
                _fail("REPLAY_RECEIPT_CHAIN_BROKEN")
            for field in (
                "admitted_artifact_set_sha256",
                "adapter_version_sha256",
                "configuration_sha256",
                "state_transition_sha256",
            ):
                _require_hash(item[field], "REPLAY_RECEIPT_HASH_INVALID")
            event_count = _require_int(
                item["event_count"], "REPLAY_RECEIPT_EVENT_COUNT_INVALID", minimum=0
            )
            for key_name in ("first_event_key", "last_event_key"):
                key = item[key_name]
                if not isinstance(key, list) or len(key) != 3:
                    _fail("REPLAY_EVENT_KEY_INVALID", key_name)
                _parse_time(key[0], "REPLAY_EVENT_KEY_INVALID")
                _require_int(key[1], "REPLAY_EVENT_KEY_INVALID", minimum=0)
                _require_identifier(key[2], "REPLAY_EVENT_KEY_INVALID")
            if event_count == 0:
                _fail("REPLAY_EMPTY_RECEIPT_REQUIRES_SEPARATE_EMPTY_IDENTITY")
            if tuple(item["first_event_key"]) > tuple(item["last_event_key"]):
                _fail("REPLAY_EVENT_KEY_ORDER_INVALID")
            _parse_time(item["created_at"], "REPLAY_RECEIPT_CLOCK_INVALID")
            computed = domain_digest(
                "pitar1/synthetic-replay-receipt/v1",
                item,
                "replay_receipt_sha256",
            )
            supplied = _require_hash(
                item["replay_receipt_sha256"], "REPLAY_RECEIPT_DIGEST_INVALID"
            )
            if supplied != computed:
                _fail("REPLAY_RECEIPT_DIGEST_MISMATCH")
            if supplied in seen_digests:
                _fail("REPLAY_RECEIPT_DIGEST_DUPLICATE")
            seen_digests.add(supplied)
            prior_digest = supplied
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "REPLAY_RECEIPT_CHAIN_VALID_NOT_EXECUTED",
            receipt_count=len(receipts),
            terminal_receipt_sha256=prior_digest,
            runtime_executed=False,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_barrier_fixture(fixture: Any) -> dict[str, Any]:
    """Validate aggregate-bar visibility and ambiguous barrier semantics."""
    try:
        fields = {
            "bar_closed_and_admitted",
            "ohlc_extrema_visible",
            "finer_grained_source_admitted",
            "upper_barrier_touched",
            "lower_barrier_touched",
            "declared_outcome",
            "mfe_mae_used_as_input",
        }
        fixture = _require_exact_keys(fixture, fields, "BARRIER_FIXTURE_SCHEMA_INVALID")
        for field in (
            "bar_closed_and_admitted",
            "ohlc_extrema_visible",
            "finer_grained_source_admitted",
            "upper_barrier_touched",
            "lower_barrier_touched",
            "mfe_mae_used_as_input",
        ):
            if not isinstance(fixture[field], bool):
                _fail("BARRIER_FIXTURE_TYPE_INVALID", field)
        if fixture["ohlc_extrema_visible"] and not fixture["bar_closed_and_admitted"]:
            _fail("FULL_BAR_FUTURE_LEAKAGE")
        if fixture["mfe_mae_used_as_input"]:
            _fail("POST_OUTCOME_LEAKAGE")
        if (
            fixture["upper_barrier_touched"]
            and fixture["lower_barrier_touched"]
            and not fixture["finer_grained_source_admitted"]
            and fixture["declared_outcome"] != "AMBIGUOUS_OR_CENSORED"
        ):
            _fail("FAVORABLE_FIRST_ASSUMPTION")
        if fixture["declared_outcome"] not in {
            "UPPER_FIRST",
            "LOWER_FIRST",
            "NEITHER",
            "AMBIGUOUS_OR_CENSORED",
        }:
            _fail("BARRIER_OUTCOME_INVALID")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "BAR_AND_BARRIER_SEMANTICS_VALID",
            declared_outcome=fixture["declared_outcome"],
            runtime_executed=False,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_comparison_fixture(fixture: Any) -> dict[str, Any]:
    """Validate four-policy equal-information preregistration semantics only."""
    try:
        fields = {
            "policy_ids",
            "information_digest_by_policy",
            "denominator_digest_by_policy",
            "cost_model_digest_by_policy",
            "risk_model_digest_by_policy",
            "policy_input_fields",
            "outcome_only_fields",
            "real_data",
            "scoring_executed",
            "permission",
            "action",
            "max_risk",
        }
        fixture = _require_exact_keys(fixture, fields, "COMPARISON_FIXTURE_SCHEMA_INVALID")
        if fixture["policy_ids"] != list(_POLICIES):
            _fail("POLICY_SET_MISMATCH")
        for field in (
            "information_digest_by_policy",
            "denominator_digest_by_policy",
            "cost_model_digest_by_policy",
            "risk_model_digest_by_policy",
        ):
            values = fixture[field]
            if not isinstance(values, dict) or set(values) != set(_POLICIES):
                _fail("COMPARISON_MAPPING_MISMATCH", field)
            digests = list(values.values())
            if any(not isinstance(value, str) or not _HEX64.fullmatch(value) for value in digests):
                _fail("COMPARISON_DIGEST_INVALID", field)
            if len(set(digests)) != 1:
                _fail("UNEQUAL_POLICY_INFORMATION", field)
        if not isinstance(fixture["policy_input_fields"], list):
            _fail("POLICY_INPUT_FIELDS_INVALID")
        if fixture["outcome_only_fields"] != [
            "mfe_post_outcome_only",
            "mae_post_outcome_only",
        ]:
            _fail("OUTCOME_FIELD_SET_MISMATCH")
        if any(field in fixture["policy_input_fields"] for field in fixture["outcome_only_fields"]):
            _fail("POST_OUTCOME_LEAKAGE")
        if (
            fixture["real_data"] is not False
            or fixture["scoring_executed"] is not False
            or fixture["permission"] != "DENIED"
            or fixture["action"] != "ABSTAIN"
        ):
            _fail("EVALUATION_OR_PERMISSION_ESCALATION")
        if _require_int(fixture["max_risk"], "COMPARISON_MAX_RISK_INVALID", minimum=0) != 0:
            _fail("EVALUATION_OR_PERMISSION_ESCALATION")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "FOUR_POLICY_PREREGISTRATION_VALID_NO_SCORING",
            policy_count=4,
            scoring_executed=False,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_trajectory_fixture(rows: Any) -> dict[str, Any]:
    """Validate synthetic D3 trajectory rows without scoring or ranking."""
    try:
        fields = {
            "opportunity_id",
            "policy_id",
            "graph_revision_count",
            "path_revision_count",
            "leader_switch_count",
            "graph_update_latency",
            "decision_latency",
            "entry_count",
            "cancel_count",
            "replace_count",
            "fill_count",
            "partial_fill_count",
            "stop_revision_count",
            "target_revision_count",
            "horizon_revision_count",
            "fees",
            "slippage",
            "funding",
            "tail_loss",
            "risk_breach_count",
            "coverage_state",
            "abstain_state",
            "unknown_state",
            "censor_state",
            "mfe_post_outcome_only",
            "mae_post_outcome_only",
        }
        count_fields = {
            "graph_revision_count",
            "path_revision_count",
            "leader_switch_count",
            "entry_count",
            "cancel_count",
            "replace_count",
            "fill_count",
            "partial_fill_count",
            "stop_revision_count",
            "target_revision_count",
            "horizon_revision_count",
            "risk_breach_count",
        }
        numeric_fields = {
            "graph_update_latency",
            "decision_latency",
            "fees",
            "slippage",
            "funding",
            "tail_loss",
        }
        if not isinstance(rows, list):
            _fail("TRAJECTORY_FIXTURE_TYPE")
        seen: set[tuple[str, str]] = set()
        for item in rows:
            item = _require_exact_keys(item, fields, "TRAJECTORY_SCHEMA_INVALID")
            opportunity_id = _require_identifier(
                item["opportunity_id"], "TRAJECTORY_IDENTIFIER_INVALID"
            )
            if item["policy_id"] not in _POLICIES:
                _fail("TRAJECTORY_POLICY_INVALID")
            identity = (opportunity_id, item["policy_id"])
            if identity in seen:
                _fail("TRAJECTORY_IDENTITY_DUPLICATE")
            seen.add(identity)
            for field in count_fields:
                _require_int(item[field], "TRAJECTORY_COUNT_INVALID", minimum=0)
            for field in numeric_fields:
                value = item[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    _fail("TRAJECTORY_NUMERIC_INVALID", field)
                if not math.isfinite(float(value)):
                    _fail("TRAJECTORY_NUMERIC_INVALID", field)
            if item["graph_update_latency"] < 0 or item["decision_latency"] < 0:
                _fail("TRAJECTORY_LATENCY_INVALID")
            if item["coverage_state"] not in _COVERAGE_STATES:
                _fail("TRAJECTORY_COVERAGE_INVALID")
            for field in ("abstain_state", "unknown_state", "censor_state"):
                if not isinstance(item[field], bool):
                    _fail("TRAJECTORY_STATE_TYPE_INVALID", field)
            for field in ("mfe_post_outcome_only", "mae_post_outcome_only"):
                value = item[field]
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    _fail("TRAJECTORY_OUTCOME_DIAGNOSTIC_INVALID", field)
        by_opportunity: dict[str, set[str]] = {}
        for opportunity_id, policy_id in seen:
            by_opportunity.setdefault(opportunity_id, set()).add(policy_id)
        if any(policies != set(_POLICIES) for policies in by_opportunity.values()):
            _fail("TRAJECTORY_POLICY_DENOMINATOR_INCOMPLETE")
        return _result(
            "VALID_E0_SYNTHETIC_FIXTURE",
            "TRAJECTORY_SCHEMA_VALID_NO_SCORING",
            row_count=len(rows),
            opportunity_count=len(by_opportunity),
            scoring_executed=False,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


def validate_d0_candidate(candidate: Any) -> dict[str, Any]:
    """Validate a non-executing D0 plan candidate; never grant acquisition."""
    try:
        fields = {
            "plan_id",
            "status",
            "non_executing",
            "source_id",
            "authority_grade",
            "authority_owner",
            "canonical_source_url",
            "terms_url",
            "public_free_no_auth_evidence",
            "venue",
            "product_family",
            "instrument_id",
            "contract_metadata_identity",
            "schema_identity",
            "exact_object_urls",
            "per_object_checksum_expectations",
            "start_inclusive",
            "end_exclusive",
            "event_clock_semantics",
            "publication_clock_semantics",
            "revision_semantics",
            "gap_semantics",
            "maximum_objects",
            "maximum_single_object_bytes",
            "maximum_total_bytes",
            "maximum_requests",
            "maximum_concurrency",
            "minimum_free_disk_after_bytes",
            "maximum_cost_usd",
            "output_root",
            "chronology_role",
            "abort_and_quarantine_rules",
            "blocking_unknowns",
            "acquisition_permission",
        }
        candidate = _require_exact_keys(candidate, fields, "D0_PLAN_SCHEMA_INVALID")
        _require_identifier(candidate["plan_id"], "D0_PLAN_ID_INVALID")
        if _contains_forbidden_alias(candidate):
            _fail("D0_FORBIDDEN_ALIAS")
        if candidate["source_id"] != "SRC-BINANCE-PUBLIC-DATA-README":
            _fail("D0_SOURCE_NOT_ELIGIBLE")
        if candidate["authority_grade"] not in {"A", "B"}:
            _fail("D0_AUTHORITY_GRADE_INVALID")
        if candidate["non_executing"] is not True:
            _fail("D0_EXECUTION_ESCALATION")
        cap_limits = {
            "maximum_objects": 64,
            "maximum_single_object_bytes": 67108864,
            "maximum_total_bytes": 268435456,
            "maximum_requests": 128,
            "maximum_concurrency": 1,
            "minimum_free_disk_after_bytes": 16106127360,
            "maximum_cost_usd": 0,
        }
        for field, limit in cap_limits.items():
            value = _require_int(candidate[field], "D0_CAP_TYPE_INVALID", minimum=0)
            if field == "minimum_free_disk_after_bytes":
                if value < limit:
                    _fail("D0_CAP_EXCEEDED", field)
            elif value > limit:
                _fail("D0_CAP_EXCEEDED", field)
        if not isinstance(candidate["exact_object_urls"], list):
            _fail("D0_OBJECT_URLS_TYPE")
        if not isinstance(candidate["per_object_checksum_expectations"], list):
            _fail("D0_CHECKSUMS_TYPE")
        if not isinstance(candidate["abort_and_quarantine_rules"], list):
            _fail("D0_ABORT_RULES_TYPE")
        if not isinstance(candidate["blocking_unknowns"], list):
            _fail("D0_UNKNOWNS_TYPE")
        if candidate["acquisition_permission"] != "DENIED_REQUIRES_NEW_SOL_D0_DECISION":
            _fail("D0_PERMISSION_ESCALATION")
        unknown_present = any(
            isinstance(value, str) and "UNKNOWN_WAIT_DATA" in value
            for value in candidate.values()
        ) or bool(candidate["blocking_unknowns"])
        if unknown_present:
            if candidate["status"] != "WAIT_DATA":
                _fail("D0_READY_WITH_UNKNOWNS")
            return _result(
                "WAIT_DATA",
                "D0_UNKNOWNS_RETAINED_NO_ACQUISITION_PERMISSION",
                blocking_unknowns=list(candidate["blocking_unknowns"]),
                non_executing=True,
            )
        if candidate["status"] != "READY_FOR_EXTERNAL_D0_REVIEW":
            _fail("D0_STATUS_INVALID")
        start = _parse_time(candidate["start_inclusive"], "D0_WINDOW_INVALID")
        end = _parse_time(candidate["end_exclusive"], "D0_WINDOW_INVALID")
        if start >= end:
            _fail("D0_WINDOW_INVALID")
        jan_start = _parse_time("2025-01-01T00:00:00Z", "D0_WINDOW_INVALID")
        mar_start = _parse_time("2025-03-01T00:00:00Z", "D0_WINDOW_INVALID")
        if start < mar_start and end > jan_start:
            _fail("D0_CONSUMED_WINDOW_OVERLAP")
        return _result(
            "READY_FOR_EXTERNAL_D0_REVIEW",
            "D0_PLAN_COMPLETE_BUT_NOT_AUTHORIZED",
            non_executing=True,
            external_decision_required=True,
        )
    except _Failure as exc:
        return _result("REJECT", exc.code, detail=exc.detail)
    except Exception as exc:
        return _result("REJECT", "UNEXPECTED_INPUT_REJECTED", error_type=type(exc).__name__)


__all__ = [
    "CONTRACT_DOCUMENTS",
    "ROUTE_AUTHORITY",
    "SOURCE_DISCOVERY_DOCUMENT",
    "domain_digest",
    "synthetic_external_authority",
    "synthetic_raw_bytes",
    "validate_adapter_fixture",
    "validate_admission_fixture",
    "validate_barrier_fixture",
    "validate_chronology_fixture",
    "validate_comparison_fixture",
    "validate_d0_candidate",
    "validate_pitar1_contract_bundle",
    "validate_replay_receipt_fixture",
    "validate_revision_fixture",
    "validate_source_discovery_document",
    "validate_trajectory_fixture",
]
