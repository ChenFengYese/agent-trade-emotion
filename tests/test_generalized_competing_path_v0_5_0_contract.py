"""Pure synthetic executable checks for generalized competing paths v0.5.0.

This module reads only the five local theory/contract inputs. It does not
read market data, outcomes, active G1 state, adapters, backtests or accounts.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = PROJECT_ROOT / "archive/authority/CORE_TRADING_THEORY_v2_1.md"
IMMUTABLE_CORE_PATH = PROJECT_ROOT / "archive/authority/CORE_TRADING_THEORY_v2_1.md"
CORE_AUTHORITY_PATH = PROJECT_ROOT / "config" / "core_trading_theory.authority.v2_1.json"
THEORY_PATH = PROJECT_ROOT / "theory/history/GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md"
METHOD_PATH = PROJECT_ROOT / "config" / "generalized_competing_path.method_contract.v0_5_0.json"
REGISTRY_PATH = PROJECT_ROOT / "config" / "generalized_competing_path.hypothesis_registry.v0_5_0.json"
SYNTHETIC_PATH = PROJECT_ROOT / "config" / "generalized_competing_path.synthetic_measurement_contract.v0_5_0.json"
METHOD_AUTHORITY_RAW_SHA256 = "18ef5234cb018d1a89252733a6d66903a145864031a2c8d663f021abe79740b0"

MECHANISMS = (
    "CONTINUATION",
    "ABSORPTION_REVERSAL",
    "RANGE",
    "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM",
    "EVENT_REPRICING",
    "ARTIFACT",
    "OTHER",
)
SCENARIOS = ("UPSIDE", "DOWNSIDE", "RANGE", "UNRESOLVED")
ACTION_OUTCOMES = ("NO_FILL", "TP_FIRST", "SL_FIRST", "STRUCTURE_EXIT", "TIMEOUT")
POST_POSITION_ACTIONS = ("KEEP", "TIGHTEN", "REDUCE", "EXIT")
QUALITATIVE_VALUES = ("LEADING", "SUPPORTED", "WEAK", "UNSUPPORTED", "UNKNOWN")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject_duplicate_json_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"DUPLICATE_JSON_KEY:{key}")
        value[key] = item
    return value


def _load_method_authority_view() -> dict[str, object]:
    if METHOD_PATH.resolve() != (
        PROJECT_ROOT
        / "config"
        / "generalized_competing_path.method_contract.v0_5_0.json"
    ).resolve():
        raise ValueError("METHOD_AUTHORITY_PATH_INVALID")
    raw = METHOD_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != METHOD_AUTHORITY_RAW_SHA256:
        raise ValueError("METHOD_AUTHORITY_RAW_SHA256_INVALID")
    try:
        method = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("METHOD_AUTHORITY_JSON_INVALID") from error
    if (
        type(method) is not dict
        or method.get("contract_id")
        != "GENERALIZED_COMPETING_PATH_METHOD_CONTRACT.v0.5.0"
        or method.get("stage") != "V5-M00"
        or method.get("status")
        != "E0_NO_NEW_OUTCOME_ACCESS_SYNTHETIC_ONLY"
    ):
        raise ValueError("METHOD_AUTHORITY_IDENTITY_INVALID")
    return method


def _utc(value: object) -> datetime:
    if type(value) is not str or not value:
        raise ValueError("TIMESTAMP_TYPE_OR_EMPTY")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc)


def _canonical_utc_text(value: object) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _record_visible(record: dict[str, object], decision_time: object) -> bool:
    try:
        source_at = _utc(record.get("source_timestamp"))
        available_at = _utc(record.get("available_at"))
        decision_at = _utc(decision_time)
    except (TypeError, ValueError, OverflowError):
        return False
    return source_at <= decision_at and available_at <= decision_at


def _exact_keys(value: object, fields: tuple[str, ...]) -> bool:
    return type(value) is dict and set(value) == set(fields)


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def _probability_vector_valid(values: object, branches: tuple[str, ...]) -> bool:
    if type(values) is not dict or set(values) != set(branches):
        return False
    if not all(_finite_number(value) and 0.0 <= value <= 1.0 for value in values.values()):
        return False
    return math.isclose(sum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-12)


def _scenario_distribution_valid(
    payload: object,
    exact_fields: tuple[str, ...],
    decision_time: object,
) -> bool:
    if not _exact_keys(payload, exact_fields):
        return False
    try:
        as_of = _utc(payload.get("as_of"))
        decision_at = _utc(decision_time)
    except (TypeError, ValueError, OverflowError):
        return False
    if (
        as_of > decision_at
        or type(payload.get("distribution_id")) is not str
        or payload["distribution_id"] == ""
    ):
        return False
    mode = payload.get("mode")
    values = payload.get("values")
    if tuple(payload.get("branches", ())) != SCENARIOS:
        return False
    if mode == "SYNTHETIC_COUNTERFACTUAL_ONLY":
        return (
            payload.get("normalization_status") == "NORMALIZED"
            and payload.get("calibration_version") == "SYNTHETIC-CAL-V1"
            and payload.get("unknown_reason") is None
            and _probability_vector_valid(values, SCENARIOS)
        )
    if mode == "QUALITATIVE_E0":
        return (
            payload.get("normalization_status") == "NOT_APPLICABLE_UNCALIBRATED"
            and payload.get("calibration_version") is None
            and payload.get("unknown_reason") is None
            and type(values) is dict
            and set(values) == set(SCENARIOS)
            and all(type(value) is str and value in QUALITATIVE_VALUES for value in values.values())
        )
    if mode == "UNKNOWN":
        return (
            values == {}
            and payload.get("normalization_status") == "UNKNOWN"
            and payload.get("calibration_version") is None
            and type(payload.get("unknown_reason")) is str
            and payload["unknown_reason"] != ""
        )
    return False


def _scenario_distribution_digest(
    payload: object,
    exact_fields: tuple[str, ...],
    decision_time: object,
) -> str:
    if not _scenario_distribution_valid(payload, exact_fields, decision_time):
        raise ValueError("SCENARIO_INVALID")
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _action_outcome_valid(values: object) -> bool:
    return _probability_vector_valid(values, ACTION_OUTCOMES)


def _optional_missing(rule: str) -> str:
    actions = {
        "IGNORE_WITH_MISSING_FLAG": "MISSING_FLAG",
        "BLOCK_TARGET": "TARGET_BLOCKED",
        "UNKNOWN": "UNKNOWN",
    }
    if rule not in actions:
        raise ValueError("OPTIONAL_RULE_UNREGISTERED")
    return actions[rule]


def _required_input_disposition(missing_required: object) -> str:
    if type(missing_required) is not list:
        return "UNKNOWN"
    return "UNKNOWN" if missing_required else "CONTINUE"


def _evidence_increment(evidence: dict[str, object]) -> int:
    strength = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
    direction = evidence.get("direction")
    ordinal = evidence.get("ordinal_strength")
    if ordinal not in strength:
        raise ValueError("EVIDENCE_STRENGTH_INVALID")
    if direction == "SUPPORT":
        return strength[ordinal]
    if direction == "SOFT_CONTRADICTION":
        return -strength[ordinal]
    if direction == "HARD_FALSIFIER":
        raise RuntimeError("HARD_FALSIFIER")
    raise ValueError("EVIDENCE_DIRECTION_INVALID")


def _canonical_digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _evidence_lineage_authority(
    method: dict[str, object],
) -> dict[str, object]:
    authority = method.get("evidence_contract", {}).get(
        "source_lineage_authority"
    )
    expected_fields = {
        "authority_id",
        "mode",
        "evidence_id_prefix",
        "dependency_group_prefix",
        "evidence_identity_fields",
        "underlying_increment_identity_fields",
        "target_ids_canonicalization",
        "timestamp_canonicalization",
        "target_routing_identity_boundary",
        "allowed_perspective_ids",
        "allowed_source_versions",
        "digest_rule",
        "exact_carrier_limitation",
        "future_runtime_requirement",
    }
    if (
        type(authority) is not dict
        or set(authority) != expected_fields
        or authority.get("authority_id")
        != "V5-M00-SYNTHETIC-EVIDENCE-LINEAGE-V1"
        or authority.get("mode")
        != "SYNTHETIC_CANONICAL_PROJECTION_ONLY_NOT_RUNTIME_RAW_LINEAGE"
        or authority.get("target_ids_canonicalization")
        != "SORTED_UNIQUE_STRINGS"
        or authority.get("timestamp_canonicalization")
        != "PARSE_TIMEZONE_AWARE_AND_RENDER_UTC_ISO8601_WITH_Z_BEFORE_IDENTITY_DIGEST"
    ):
        raise ValueError("EVIDENCE_LINEAGE_AUTHORITY_INVALID")
    all_fields = set(method["evidence_contract"]["exact_fields"])
    evidence_fields = authority["evidence_identity_fields"]
    underlying_fields = authority["underlying_increment_identity_fields"]
    if (
        type(evidence_fields) is not list
        or type(underlying_fields) is not list
        or not evidence_fields
        or not underlying_fields
        or len(evidence_fields) != len(set(evidence_fields))
        or len(underlying_fields) != len(set(underlying_fields))
        or not set(evidence_fields).issubset(all_fields - {"evidence_id"})
        or not set(underlying_fields).issubset(all_fields - {"evidence_id", "dependency_group"})
        or authority.get("allowed_perspective_ids")
        != ["PERSPECTIVE-SYNTHETIC-E0", "PERSPECTIVE-SYNTHETIC-E0-ALT"]
        or authority.get("allowed_source_versions")
        != ["SYNTHETIC-SOURCE-V1"]
    ):
        raise ValueError("EVIDENCE_LINEAGE_AUTHORITY_INVALID")
    return authority


def _canonical_evidence_projection(
    row: dict[str, object],
    fields: list[str],
) -> dict[str, object]:
    projection = {field: copy.deepcopy(row[field]) for field in fields}
    if "target_ids" in projection:
        projection["target_ids"] = sorted(projection["target_ids"])
    if "available_at" in projection:
        projection["available_at"] = (
            _utc(projection["available_at"])
            .isoformat()
            .replace("+00:00", "Z")
        )
    return projection


def _authority_bound_evidence_row(
    row: dict[str, object],
    authority: dict[str, object],
) -> tuple[dict[str, object], dict[str, str]]:
    canonical_underlying = _canonical_evidence_projection(
        row,
        authority["underlying_increment_identity_fields"],
    )
    underlying_increment_id = (
        "UNDERLYING-V5M00-" + _canonical_digest(canonical_underlying)
    )
    bound = copy.deepcopy(row)
    bound["dependency_group"] = (
        authority["dependency_group_prefix"]
        + _canonical_digest(canonical_underlying)
    )
    canonical_identity = _canonical_evidence_projection(
        bound,
        authority["evidence_identity_fields"],
    )
    bound["evidence_id"] = (
        authority["evidence_id_prefix"] + _canonical_digest(canonical_identity)
    )
    canonical_content = copy.deepcopy(bound)
    canonical_content["target_ids"] = sorted(canonical_content["target_ids"])
    canonical_content["available_at"] = (
        _utc(canonical_content["available_at"])
        .isoformat()
        .replace("+00:00", "Z")
    )
    identity_entry = {
        "evidence_id": bound["evidence_id"],
        "content_digest": _canonical_digest(canonical_content),
        "underlying_increment_id": underlying_increment_id,
        "dependency_group": bound["dependency_group"],
    }
    return bound, identity_entry


def _synthetic_evidence(
    case_label: str,
    target_ids: list[str],
    *,
    direction: str,
    ordinal_strength: str,
    quality: str = "VALID",
    available_at: str = "2026-01-01T00:00:00Z",
    perspective_id: str = "PERSPECTIVE-SYNTHETIC-E0",
    source_version: str = "SYNTHETIC-SOURCE-V1",
) -> dict[str, object]:
    if type(case_label) is not str or case_label == "":
        raise ValueError("SYNTHETIC_CASE_LABEL_INVALID")
    method = _load_method_authority_view()
    authority = _evidence_lineage_authority(method)
    row = {
        "evidence_id": "UNBOUND",
        "available_at": available_at,
        "perspective_id": perspective_id,
        "dependency_group": "UNBOUND",
        "target_ids": target_ids,
        "direction": direction,
        "ordinal_strength": ordinal_strength,
        "quality": quality,
        "source_version": source_version,
    }
    bound, _ = _authority_bound_evidence_row(row, authority)
    return bound


def _admit_evidence_row(
    row: object,
    *,
    exact_fields: tuple[str, ...],
    authority: dict[str, object],
    decision_at: datetime,
) -> tuple[dict[str, str] | None, str | None, tuple[str, ...] | None]:
    evidence_id = (
        row.get("evidence_id")
        if type(row) is dict
        and type(row.get("evidence_id")) is str
        and row["evidence_id"] != ""
        else "UNKNOWN_EVIDENCE"
    )
    target_ids = row.get("target_ids") if type(row) is dict else None
    target_scope = (
        tuple(target_ids)
        if type(target_ids) is list
        and len(target_ids) > 0
        and len(target_ids) == len(set(target_ids))
        and all(type(value) is str and value != "" for value in target_ids)
        else None
    )
    if not _exact_keys(row, exact_fields):
        return None, f"{evidence_id}:SCHEMA_INVALID", target_scope
    if target_scope is None:
        return (
            None,
            f"{evidence_id}:TARGET_IDS_INVALID_SCOPE_UNDETERMINED",
            None,
        )
    if (
        any(
            type(row.get(field)) is not str or row[field] == ""
            for field in (
                "evidence_id",
                "perspective_id",
                "dependency_group",
                "source_version",
            )
        )
        or row.get("direction")
        not in {"SUPPORT", "SOFT_CONTRADICTION", "HARD_FALSIFIER"}
        or row.get("ordinal_strength") not in {"WEAK", "MODERATE", "STRONG"}
        or row.get("quality")
        not in {
            "VALID",
            "UNAVAILABLE",
            "STALE",
            "GAP",
            "CONFLICT",
            "DATA_INVALID",
            "UNKNOWN",
        }
        or row.get("perspective_id")
        not in authority["allowed_perspective_ids"]
        or row.get("source_version") not in authority["allowed_source_versions"]
    ):
        return None, f"{evidence_id}:FIELD_ENUM_OR_AUTHORITY_INVALID", target_scope
    try:
        available_at = _utc(row.get("available_at"))
    except (TypeError, ValueError, OverflowError):
        return None, f"{evidence_id}:AVAILABLE_AT_INVALID", target_scope
    if available_at > decision_at:
        return (
            None,
            f"{evidence_id}:"
            "RETRYABLE_AT_LATER_DECISION_TIME:"
            "AVAILABLE_AT_FUTURE",
            target_scope,
        )
    if row["quality"] != "VALID":
        return None, f"{evidence_id}:QUALITY_{row['quality']}", target_scope
    expected_row, identity_entry = _authority_bound_evidence_row(row, authority)
    if row["dependency_group"] != expected_row["dependency_group"]:
        return None, f"{evidence_id}:DEPENDENCY_GROUP_AUTHORITY_MISMATCH", target_scope
    if row["evidence_id"] != expected_row["evidence_id"]:
        return None, f"{evidence_id}:EVIDENCE_ID_AUTHORITY_MISMATCH", target_scope
    return identity_entry, None, target_scope


def _aggregate_evidence(
    prior: object,
    evidence_rows: object,
    target_id: object,
    decision_time: object,
    exact_fields: tuple[str, ...],
) -> dict[str, object]:
    if (
        type(prior) is not int
        or type(evidence_rows) is not list
        or type(target_id) is not str
        or target_id == ""
    ):
        raise ValueError("EVIDENCE_AGGREGATION_INPUT_INVALID")
    try:
        decision_at = _utc(decision_time)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("EVIDENCE_DECISION_TIME_INVALID") from error
    method = _load_method_authority_view()
    if exact_fields != tuple(method["evidence_contract"]["exact_fields"]):
        raise ValueError("EVIDENCE_SCHEMA_AUTHORITY_MISMATCH")
    authority = _evidence_lineage_authority(method)
    valid_relevant: list[tuple[dict[str, object], dict[str, str]]] = []
    rejected: list[str] = []
    for row in evidence_rows:
        identity_entry, reason, target_scope = _admit_evidence_row(
            row,
            exact_fields=exact_fields,
            authority=authority,
            decision_at=decision_at,
        )
        if target_scope is None:
            rejected.append(reason or "UNKNOWN_EVIDENCE:TARGET_SCOPE_UNDETERMINED")
            continue
        if target_id not in target_scope:
            continue
        if reason is not None:
            rejected.append(reason)
            continue
        valid_relevant.append((row, identity_entry))
    if rejected:
        return {
            "status": "UNKNOWN",
            "support": prior,
            "accepted_evidence_ids": (),
            "rejected_evidence": tuple(sorted(rejected)),
            "admitted_identity_entries": (),
        }

    relevant_evidence_ids = [
        row["evidence_id"] for row, _identity_entry in valid_relevant
    ]
    duplicate_ids = tuple(
        sorted(
            evidence_id
            for evidence_id in set(relevant_evidence_ids)
            if relevant_evidence_ids.count(evidence_id) > 1
        )
    )
    if duplicate_ids:
        return {
            "status": "UNKNOWN",
            "support": prior,
            "accepted_evidence_ids": (),
            "rejected_evidence": tuple(
                f"{evidence_id}:EVIDENCE_ID_DUPLICATE_IN_TARGET_BATCH"
                for evidence_id in duplicate_ids
            ),
            "admitted_identity_entries": (),
        }
    groups: dict[str, list[tuple[int, str]]] = {}
    hard_falsifiers: list[str] = []
    for row, _identity_entry in valid_relevant:
        evidence_id = row["evidence_id"]
        if row["direction"] == "HARD_FALSIFIER":
            hard_falsifiers.append(evidence_id)
            continue
        increment = _evidence_increment(row)
        dependency_group = row.get("dependency_group")
        groups.setdefault(dependency_group, []).append((increment, evidence_id))
    admitted_entries = tuple(
        sorted(
            (entry for _row, entry in valid_relevant),
            key=lambda entry: entry["evidence_id"],
        )
    )
    if hard_falsifiers:
        return {
            "status": "FALSIFIED",
            "support": prior,
            "accepted_evidence_ids": (sorted(hard_falsifiers)[0],),
            "rejected_evidence": (),
            "admitted_identity_entries": admitted_entries,
        }
    accepted: list[str] = []
    total = prior
    for dependency_group in sorted(groups):
        selected = sorted(groups[dependency_group], key=lambda item: (-abs(item[0]), item[1]))[0]
        total += selected[0]
        accepted.append(selected[1])
    return {
        "status": "UNKNOWN" if rejected and not accepted else "ACTIVE",
        "support": max(-9, min(9, total)),
        "accepted_evidence_ids": tuple(accepted),
        "rejected_evidence": (),
        "admitted_identity_entries": admitted_entries,
    }


def _typed_canonical_value(value: object) -> dict[str, object]:
    if value is None:
        return {"type": "NULL", "value": None}
    if type(value) is bool:
        return {"type": "BOOL", "value": value}
    if type(value) is int:
        return {"type": "INT", "value": value}
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("TYPED_CANONICAL_FLOAT_NONFINITE")
        return {"type": "FLOAT", "value": value}
    if type(value) is str:
        return {"type": "STRING", "value": value}
    if type(value) is list:
        return {
            "type": "LIST",
            "value": [_typed_canonical_value(item) for item in value],
        }
    if type(value) is tuple:
        return {
            "type": "TUPLE",
            "value": [_typed_canonical_value(item) for item in value],
        }
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise ValueError("TYPED_CANONICAL_DICT_KEY_INVALID")
        return {
            "type": "DICT",
            "value": [
                [key, _typed_canonical_value(value[key])]
                for key in sorted(value)
            ],
        }
    raise ValueError("TYPED_CANONICAL_TYPE_UNSUPPORTED")


def _decode_typed_canonical_value(value: object) -> object:
    if (
        type(value) is not dict
        or set(value) != {"type", "value"}
        or type(value.get("type")) is not str
    ):
        raise ValueError("TYPED_CANONICAL_SCHEMA_INVALID")
    kind = value["type"]
    payload = value["value"]
    if kind == "NULL" and payload is None:
        return None
    if kind == "BOOL" and type(payload) is bool:
        return payload
    if kind == "INT" and type(payload) is int:
        return payload
    if kind == "FLOAT" and type(payload) is float and math.isfinite(payload):
        return payload
    if kind == "STRING" and type(payload) is str:
        return payload
    if kind in {"LIST", "TUPLE"} and type(payload) is list:
        decoded = [
            _decode_typed_canonical_value(item)
            for item in payload
        ]
        return decoded if kind == "LIST" else tuple(decoded)
    if kind == "DICT" and type(payload) is list:
        decoded_dict: dict[str, object] = {}
        prior_key: str | None = None
        for pair in payload:
            if (
                type(pair) is not list
                or len(pair) != 2
                or type(pair[0]) is not str
                or pair[0] in decoded_dict
                or (prior_key is not None and pair[0] <= prior_key)
            ):
                raise ValueError("TYPED_CANONICAL_DICT_INVALID")
            decoded_dict[pair[0]] = _decode_typed_canonical_value(pair[1])
            prior_key = pair[0]
        return decoded_dict
    raise ValueError("TYPED_CANONICAL_VALUE_INVALID")


def _canonical_batch_member(input_kind: str, payload: object) -> dict[str, object]:
    typed_payload = _typed_canonical_value(payload)
    bound = {
        "input_kind": input_kind,
        "typed_payload": typed_payload,
    }
    return bound | {"member_digest": _canonical_digest(bound)}


def _canonical_transition_batch(
    evidence_rows: object,
    lifecycle_events: object,
    method: dict[str, object],
) -> tuple[str | None, list[dict[str, object]]]:
    if type(evidence_rows) is not list or type(lifecycle_events) is not list:
        raise ValueError("LEDGER_TRANSITION_INPUT_INVALID")
    if evidence_rows and lifecycle_events:
        raise ValueError("LEDGER_TRANSITION_KIND_MIXED")
    if lifecycle_events and len(lifecycle_events) != 1:
        raise ValueError("LIFECYCLE_TRANSITION_CARDINALITY_INVALID")
    if not evidence_rows and not lifecycle_events:
        return None, []
    transition_kind = (
        "EVIDENCE_BATCH" if evidence_rows else "LIFECYCLE_TERMINAL"
    )
    input_kind = (
        "EVIDENCE" if evidence_rows else "LIFECYCLE_TERMINAL"
    )
    if transition_kind not in method["evidence_ledger_contract"][
        "transition_kinds"
    ]:
        raise ValueError("LEDGER_TRANSITION_KIND_INVALID")
    rows = evidence_rows if evidence_rows else lifecycle_events
    members = [
        _canonical_batch_member(input_kind, row)
        for row in rows
    ]
    return transition_kind, sorted(
        members,
        key=lambda member: (
            member["member_digest"],
            json.dumps(
                member,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def _transition_batch_digest(canonical_batch: object) -> str:
    if type(canonical_batch) is not list:
        raise ValueError("CANONICAL_BATCH_INVALID")
    return _canonical_digest(canonical_batch)


def _rejection_class(
    rejected_evidence: object,
    method: dict[str, object],
) -> str:
    if type(rejected_evidence) is not list:
        raise ValueError("LEDGER_REJECTION_CLASS_INPUT_INVALID")
    allowed = set(
        method["evidence_ledger_contract"]["rejection_classes"]
    )
    if not rejected_evidence:
        result = "NONE"
    elif any(
        type(reason) is not str
        or "RETRYABLE_AT_LATER_DECISION_TIME" not in reason
        and "RESOURCE_CAPACITY_REQUIRED" not in reason
        for reason in rejected_evidence
    ):
        result = "PERMANENT"
    elif any(
        "RESOURCE_CAPACITY_REQUIRED" in reason
        for reason in rejected_evidence
    ):
        result = "RESOURCE_CAPACITY_REQUIRED"
    else:
        result = "RETRYABLE_AT_LATER_DECISION_TIME"
    if result not in allowed:
        raise ValueError("LEDGER_REJECTION_CLASS_AUTHORITY_INVALID")
    return result


def _transition_idempotency_key(
    *,
    scope_digest: str,
    transition_kind: str,
    batch_digest: str,
    decision_time: object,
    rejection_class: str,
) -> str:
    return _canonical_digest(
        {
            "scope_digest": scope_digest,
            "transition_kind": transition_kind,
            "batch_digest": batch_digest,
            "decision_time": _canonical_utc_text(decision_time),
            "rejection_class": rejection_class,
        }
    )


def _semantic_terminal_id(
    *,
    scope_digest: str,
    target_id: str,
    terminal_status: str,
    terminal_event_at: object,
    terminal_authority_id: str,
    terminal_reason_priority: int,
    reason_code: str,
) -> str:
    return (
        "TERMINAL-SEMANTIC-V5M00-"
        + _canonical_digest(
            {
                "scope_digest": scope_digest,
                "target_id": target_id,
                "terminal_status": terminal_status,
                "terminal_event_at": _canonical_utc_text(
                    terminal_event_at
                ),
                "terminal_authority_id": terminal_authority_id,
                "terminal_reason_priority": terminal_reason_priority,
                "reason_code": reason_code,
            }
        )
    )


def _evidence_batch_digest(evidence_rows: object) -> str:
    method = _load_method_authority_view()
    _kind, canonical_batch = _canonical_transition_batch(
        evidence_rows,
        [],
        method,
    )
    return _transition_batch_digest(canonical_batch)


def _episode_scope_digest(episode: dict[str, object]) -> str:
    return _canonical_digest(
        {
            "observation_frame_id": episode["observation_frame_id"],
            "episode_id": episode["episode_id"],
            "path_instance_id": episode["path_instance_id"],
            "mechanism_id": episode["mechanism_id"],
        }
    )


def _lifecycle_event_digest(event: object) -> str:
    if type(event) is not dict or "lifecycle_event_digest" not in event:
        raise ValueError("LIFECYCLE_EVENT_DIGEST_INPUT_INVALID")
    return _canonical_digest(
        {
            key: value
            for key, value in event.items()
            if key != "lifecycle_event_digest"
        }
    )


def _lifecycle_event_id(event: object) -> str:
    if type(event) is not dict:
        raise ValueError("LIFECYCLE_EVENT_ID_INPUT_INVALID")
    excluded = {"lifecycle_event_id", "lifecycle_event_digest"}
    if not excluded.issubset(event):
        raise ValueError("LIFECYCLE_EVENT_ID_INPUT_INVALID")
    return (
        "LIFECYCLE-V5M00-"
        + _canonical_digest(
            {
                key: value
                for key, value in event.items()
                if key not in excluded
            }
        )
    )


def _synthetic_lifecycle_event(
    episode: dict[str, object],
    *,
    terminal_status: str,
    terminal_reason: str,
    path_started_at: str = "2025-12-31T23:59:50Z",
    requested_horizon_seconds: int = 10,
) -> dict[str, object]:
    method = _load_method_authority_view()
    spec = copy.deepcopy(
        _json(SYNTHETIC_PATH)["sample_path_specs"][0]
    )
    started_at = _utc(path_started_at)
    if terminal_reason == "EXPIRY":
        terminal_at = started_at + timedelta(
            seconds=requested_horizon_seconds
        )
    else:
        terminal_at = started_at + timedelta(seconds=2)
    terminal_at_text = terminal_at.isoformat().replace("+00:00", "Z")
    terminal_trigger_id = (
        "PREDECLARED_INVALIDATION"
        if terminal_reason == "HARD_FALSIFIER"
        else None
    )
    path_events = _synthetic_path_events(
        ["ANCHOR", "TERMINAL"],
        path_started_at=path_started_at,
        path_instance_id=episode["path_instance_id"],
        terminal_reason=terminal_reason,
        terminal_trigger_id=terminal_trigger_id,
        terminal_event_at=terminal_at_text,
    )
    event = {
        "lifecycle_event_id": "",
        "target_id": episode["path_instance_id"],
        "scope_digest": _episode_scope_digest(episode),
        "terminal_reason": terminal_reason,
        "terminal_status": terminal_status,
        "terminal_event_at": terminal_at_text,
        "path_started_at": (
            started_at.isoformat().replace("+00:00", "Z")
        ),
        "requested_horizon_seconds": requested_horizon_seconds,
        "path_spec": spec,
        "path_events": path_events,
        "source_version": method["evidence_ledger_contract"][
            "lifecycle_source_version"
        ],
        "lifecycle_event_digest": "",
    }
    event["lifecycle_event_id"] = _lifecycle_event_id(event)
    event["lifecycle_event_digest"] = _lifecycle_event_digest(event)
    return event


def _lifecycle_event_rejection(
    event: object,
    *,
    episode: dict[str, object],
    decision_time: object,
    method: dict[str, object],
) -> str | None:
    contract = method["evidence_ledger_contract"]
    if not _exact_keys(
        event,
        tuple(contract["lifecycle_event_exact_fields"]),
    ):
        return "LIFECYCLE_EVENT_SCHEMA_INVALID"
    if (
        type(event.get("lifecycle_event_id")) is not str
        or event["lifecycle_event_id"] == ""
        or event.get("target_id") != episode["path_instance_id"]
        or event.get("scope_digest") != _episode_scope_digest(episode)
        or event.get("source_version") != contract["lifecycle_source_version"]
        or event.get("terminal_reason")
        not in contract["lifecycle_terminal_mapping"]
        or event.get("terminal_status")
        != contract["lifecycle_terminal_mapping"].get(
            event.get("terminal_reason")
        )
        or event.get("lifecycle_event_id")
        != _lifecycle_event_id(event)
        or event.get("lifecycle_event_digest")
        != _lifecycle_event_digest(event)
    ):
        return "LIFECYCLE_EVENT_AUTHORITY_INVALID"
    path_events = event.get("path_events")
    path_spec = event.get("path_spec")
    path_valid, path_reason = _path_valid(
        path_events,
        path_spec,
        decision_time=decision_time,
        path_started_at=event.get("path_started_at"),
        requested_horizon_seconds=event.get(
            "requested_horizon_seconds"
        ),
        path_spec_fields=tuple(
            method["object_schemas"]["PathSpec"]["exact_fields"]
        ),
        path_event_fields=tuple(
            method["object_schemas"]["PathEvent"]["exact_fields"]
        ),
    )
    if not path_valid:
        if path_reason in {
            "EVENT_NOT_CAUSALLY_AVAILABLE",
            "PATH_START_AFTER_DECISION_TIME",
        }:
            return (
                "RETRYABLE_AT_LATER_DECISION_TIME:"
                f"LIFECYCLE_PATH_AUTHORITY_PENDING:{path_reason}"
            )
        return f"LIFECYCLE_PATH_AUTHORITY_INVALID:{path_reason}"
    if path_reason != "VALID":
        if path_reason == "COMPACT_REQUIRED_RECEIPT_CONTINUATION":
            return (
                "RESOURCE_CAPACITY_REQUIRED:UNKNOWN_RESOURCE:"
                "COMPACT_REQUIRED_RECEIPT_CONTINUATION"
            )
        return f"LIFECYCLE_PATH_AUTHORITY_INVALID:{path_reason}"
    if (
        type(path_events) is not list
        or not path_events
        or episode["mechanism_id"]
        not in path_spec.get("primitive_mechanism_ids", [])
        or any(
            path_event.get("path_instance_id")
            != episode["path_instance_id"]
            or path_event.get("source_version")
            not in method["path_contract"][
                "path_event_source_versions"
            ]
            for path_event in path_events
        )
        or path_events[-1].get("terminal_reason")
        != event["terminal_reason"]
    ):
        return "LIFECYCLE_PATH_EVENT_SCOPE_OR_SOURCE_INVALID"
    try:
        terminal_event_at = (
            _utc(event.get("terminal_event_at"))
            .isoformat()
            .replace("+00:00", "Z")
        )
        last_event_at = (
            _utc(path_events[-1].get("event_at"))
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OverflowError):
        return "LIFECYCLE_TERMINAL_EVENT_TIME_INVALID"
    if terminal_event_at != last_event_at:
        return "LIFECYCLE_TERMINAL_EVENT_TIME_MISMATCH"
    return None


def _effect_digest(effect: object) -> str:
    if type(effect) is not dict or "effect_digest" not in effect:
        raise ValueError("LEDGER_EFFECT_DIGEST_INPUT_INVALID")
    return _canonical_digest(
        {
            key: value
            for key, value in effect.items()
            if key != "effect_digest"
        }
    )


def _build_effect(
    *,
    method: dict[str, object],
    effect_kind: str,
    target_id: str,
    scope_digest: str,
    batch_digest: str,
    batch_member_digest: str,
    identity_entry: dict[str, str] | None = None,
    selected_evidence: dict[str, object] | None = None,
    direction: str,
    signed_ordinal_delta: int,
    effective_at: str | None = None,
    terminal_status: str | None = None,
    terminal_event_at: str | None = None,
    terminal_source_digest: str | None = None,
    terminal_authority_id: str | None = None,
    semantic_terminal_id: str | None = None,
    reason_code: str | None = None,
) -> dict[str, object]:
    contract = method["evidence_ledger_contract"]
    effect = {
        "effect_kind": effect_kind,
        "target_id": target_id,
        "scope_digest": scope_digest,
        "batch_digest": batch_digest,
        "batch_member_digest": batch_member_digest,
        "dependency_group": (
            identity_entry["dependency_group"]
            if identity_entry is not None
            else None
        ),
        "evidence_id": (
            identity_entry["evidence_id"]
            if identity_entry is not None
            else None
        ),
        "content_digest": (
            identity_entry["content_digest"]
            if identity_entry is not None
            else None
        ),
        "underlying_increment_id": (
            identity_entry["underlying_increment_id"]
            if identity_entry is not None
            else None
        ),
        "direction": direction,
        "signed_ordinal_delta": signed_ordinal_delta,
        "effective_at": effective_at,
        "terminal_status": terminal_status,
        "terminal_event_at": terminal_event_at,
        "terminal_source_digest": terminal_source_digest,
        "terminal_authority_id": terminal_authority_id,
        "semantic_terminal_id": semantic_terminal_id,
        "reason_code": reason_code,
        "selected_evidence": copy.deepcopy(selected_evidence),
        "effect_digest": "",
    }
    if (
        effect_kind not in contract["effect_kinds"]
        or not _exact_keys(effect, tuple(contract["effect_exact_fields"]))
    ):
        raise ValueError("LEDGER_EFFECT_SCHEMA_INVALID")
    effect["effect_digest"] = _effect_digest(effect)
    return effect


def _effects_digest(effects: object) -> str:
    if type(effects) is not list:
        raise ValueError("LEDGER_EFFECTS_INVALID")
    return _canonical_digest(effects)


def _group_winner_from_effect(
    effect: dict[str, object],
    method: dict[str, object],
) -> dict[str, object]:
    winner = {
        field: effect[field]
        for field in method["evidence_ledger_contract"][
            "group_winner_exact_fields"
        ]
    }
    if not _exact_keys(
        winner,
        tuple(
            method["evidence_ledger_contract"][
                "group_winner_exact_fields"
            ]
        ),
    ):
        raise ValueError("GROUP_WINNER_SCHEMA_INVALID")
    return winner


def _winner_rank(winner: dict[str, object]) -> tuple[int, str]:
    return (-abs(winner["signed_ordinal_delta"]), winner["evidence_id"])


def _terminal_winner_from_effect(
    effect: dict[str, object],
    method: dict[str, object],
) -> dict[str, object]:
    winner = {
        "terminal_status": effect["terminal_status"],
        "terminal_event_at": _canonical_utc_text(
            effect["terminal_event_at"]
        ),
        "terminal_authority_id": effect["terminal_authority_id"],
        "semantic_terminal_id": effect["semantic_terminal_id"],
        "terminal_reason_priority": method[
            "evidence_ledger_contract"
        ]["terminal_reason_priority"][effect["reason_code"]],
        "reason_code": effect["reason_code"],
    }
    if not _exact_keys(
        winner,
        tuple(
            method["evidence_ledger_contract"][
                "terminal_winner_exact_fields"
            ]
        ),
    ):
        raise ValueError("TERMINAL_WINNER_SCHEMA_INVALID")
    return winner


def _terminal_winner_rank(
    winner: dict[str, object],
) -> tuple[datetime, int, str, str]:
    return (
        _utc(winner["terminal_event_at"]),
        winner["terminal_reason_priority"],
        winner["terminal_authority_id"],
        winner["semantic_terminal_id"],
    )


def _ledger_state_projection(
    state: dict[str, object],
) -> dict[str, object]:
    return {
        "scope_digest": state["scope_digest"],
        "status": state["status"],
        "raw_support": state["raw_support"],
        "support": state["support"],
        "group_winners": [
            copy.deepcopy(state["group_winners"][group])
            for group in sorted(state["group_winners"])
        ],
        "group_candidates": [
            copy.deepcopy(
                state["group_candidates"][evidence_id]
            )
            for evidence_id in sorted(state["group_candidates"])
        ],
        "terminal_winner": copy.deepcopy(
            state["terminal_winner"]
        ),
        "admitted_identity_entries": [
            copy.deepcopy(state["evidence_identities"][evidence_id])
            for evidence_id in sorted(state["evidence_identities"])
        ],
    }


def _ledger_state_digest(state: dict[str, object]) -> str:
    return _canonical_digest(_ledger_state_projection(state))


def _initial_ledger_state(episode: dict[str, object]) -> dict[str, object]:
    return {
        "scope_digest": _episode_scope_digest(episode),
        "status": "ACTIVE",
        "raw_support": 0,
        "support": 0,
        "group_winners": {},
        "group_candidates": {},
        "terminal_winner": None,
        "evidence_identities": {},
        "lifecycle_identities": {},
        "underlying_groups": {},
    }


def _recompute_candidate_state(
    state: dict[str, object],
) -> None:
    terminal_winner = state["terminal_winner"]
    if terminal_winner is not None:
        cutoff = _utc(terminal_winner["terminal_event_at"])
        ineligible_ids = [
            evidence_id
            for evidence_id, candidate in state[
                "group_candidates"
            ].items()
            if _utc(candidate["effective_at"]) >= cutoff
        ]
        for evidence_id in ineligible_ids:
            state["group_candidates"].pop(evidence_id)
            state["evidence_identities"].pop(evidence_id, None)
    state["underlying_groups"] = {}
    for identity in state["evidence_identities"].values():
        underlying_id = identity["underlying_increment_id"]
        dependency_group = identity["dependency_group"]
        prior_group = state["underlying_groups"].setdefault(
            underlying_id,
            dependency_group,
        )
        if prior_group != dependency_group:
            raise ValueError(
                "LEDGER_REPLAY_UNDERLYING_GROUP_INCONSISTENT"
            )
    grouped: dict[str, list[dict[str, object]]] = {}
    for candidate in state["group_candidates"].values():
        grouped.setdefault(
            candidate["dependency_group"],
            [],
        ).append(candidate)
    state["group_winners"] = {
        dependency_group: copy.deepcopy(
            min(candidates, key=_winner_rank)
        )
        for dependency_group, candidates in grouped.items()
    }
    state["raw_support"] = sum(
        winner["signed_ordinal_delta"]
        for winner in state["group_winners"].values()
    )
    state["support"] = max(-9, min(9, state["raw_support"]))


def _rejection_effects(
    *,
    method: dict[str, object],
    episode: dict[str, object],
    batch_digest: str,
    members_and_reasons: list[tuple[dict[str, object], str]],
) -> list[dict[str, object]]:
    effects = [
        _build_effect(
            method=method,
            effect_kind="REJECTION",
            target_id=episode["path_instance_id"],
            scope_digest=_episode_scope_digest(episode),
            batch_digest=batch_digest,
            batch_member_digest=member["member_digest"],
            direction="REJECTION",
            signed_ordinal_delta=0,
            reason_code=reason,
        )
        for member, reason in members_and_reasons
    ]
    return sorted(effects, key=lambda effect: effect["effect_digest"])


def _derive_validated_effects(
    *,
    episode: dict[str, object],
    state: dict[str, object],
    transition_kind: str,
    canonical_batch: list[dict[str, object]],
    decision_time: object,
    method: dict[str, object],
) -> dict[str, object]:
    contract = method["evidence_ledger_contract"]
    batch_digest = _transition_batch_digest(canonical_batch)
    batch_fields = tuple(contract["batch_member_exact_fields"])
    allowed_input_kinds = set(contract["batch_input_kinds"])
    decoded: list[tuple[dict[str, object], object]] = []
    expected_sorted = sorted(
        canonical_batch,
        key=lambda member: (
            member.get("member_digest", ""),
            json.dumps(
                member,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    if canonical_batch != expected_sorted:
        raise ValueError("CANONICAL_BATCH_ORDER_INVALID")
    for member in canonical_batch:
        if (
            not _exact_keys(member, batch_fields)
            or member.get("input_kind") not in allowed_input_kinds
            or member.get("member_digest")
            != _canonical_digest(
                {
                    "input_kind": member.get("input_kind"),
                    "typed_payload": member.get("typed_payload"),
                }
            )
        ):
            raise ValueError("CANONICAL_BATCH_MEMBER_INVALID")
        payload = _decode_typed_canonical_value(member["typed_payload"])
        if _typed_canonical_value(payload) != member["typed_payload"]:
            raise ValueError("CANONICAL_BATCH_TYPED_PAYLOAD_INVALID")
        decoded.append((member, payload))
    expected_input_kind = (
        "EVIDENCE"
        if transition_kind == "EVIDENCE_BATCH"
        else "LIFECYCLE_TERMINAL"
    )
    if (
        transition_kind not in contract["transition_kinds"]
        or not decoded
        or any(
            member["input_kind"] != expected_input_kind
            for member, _payload in decoded
        )
        or (
            transition_kind == "LIFECYCLE_TERMINAL"
            and len(decoded) != 1
        )
    ):
        raise ValueError("CANONICAL_BATCH_TRANSITION_KIND_INVALID")
    terminal_statuses = set(contract["terminal_statuses"])
    if transition_kind == "LIFECYCLE_TERMINAL":
        member, event = decoded[0]
        lifecycle_event_id = (
            event.get("lifecycle_event_id")
            if type(event) is dict
            and type(event.get("lifecycle_event_id")) is str
            else None
        )
        prior_lifecycle_identity = (
            state["lifecycle_identities"].get(lifecycle_event_id)
            if lifecycle_event_id is not None
            else None
        )
        if prior_lifecycle_identity is not None:
            reason = (
                "LIFECYCLE_EVENT_ID_REPLAY"
                if event.get("lifecycle_event_digest")
                == prior_lifecycle_identity[
                    "lifecycle_event_digest"
                ]
                else "LIFECYCLE_EVENT_ID_CONTENT_DRIFT"
            )
            effects = _rejection_effects(
                method=method,
                episode=episode,
                batch_digest=batch_digest,
                members_and_reasons=[(member, reason)],
            )
            return {
                "effects": effects,
                "accepted_evidence_ids": [],
                "rejected_evidence": [reason],
                "admitted_identity_entries": [],
                "admitted_lifecycle_identity_entries": [],
            }
        rejection = _lifecycle_event_rejection(
            event,
            episode=episode,
            decision_time=decision_time,
            method=method,
        )
        if rejection is not None:
            effects = _rejection_effects(
                method=method,
                episode=episode,
                batch_digest=batch_digest,
                members_and_reasons=[(member, rejection)],
            )
            return {
                "effects": effects,
                "accepted_evidence_ids": [],
                "rejected_evidence": [rejection],
                "admitted_identity_entries": [],
                "admitted_lifecycle_identity_entries": [],
            }
        terminal_authority_id = (
            f'PATHSPEC-AUTHORITY:{event["path_spec"]["path_id"]}:'
            f'{_path_spec_digest(event["path_spec"], tuple(method["object_schemas"]["PathSpec"]["exact_fields"]))}'
        )
        terminal_reason_priority = contract[
            "terminal_reason_priority"
        ][event["terminal_reason"]]
        semantic_terminal_id = _semantic_terminal_id(
            scope_digest=_episode_scope_digest(episode),
            target_id=episode["path_instance_id"],
            terminal_status=event["terminal_status"],
            terminal_event_at=event["terminal_event_at"],
            terminal_authority_id=terminal_authority_id,
            terminal_reason_priority=terminal_reason_priority,
            reason_code=event["terminal_reason"],
        )
        effect = _build_effect(
            method=method,
            effect_kind="LIFECYCLE_TERMINAL",
            target_id=episode["path_instance_id"],
            scope_digest=_episode_scope_digest(episode),
            batch_digest=batch_digest,
            batch_member_digest=member["member_digest"],
            direction="LIFECYCLE_TERMINAL",
            signed_ordinal_delta=0,
            effective_at=event["terminal_event_at"],
            terminal_status=event["terminal_status"],
            terminal_event_at=event["terminal_event_at"],
            terminal_source_digest=event[
                "lifecycle_event_digest"
            ],
            terminal_authority_id=terminal_authority_id,
            semantic_terminal_id=semantic_terminal_id,
            reason_code=event["terminal_reason"],
        )
        return {
            "effects": [effect],
            "accepted_evidence_ids": [],
            "rejected_evidence": [],
            "admitted_identity_entries": [],
            "admitted_lifecycle_identity_entries": [
                {
                    "lifecycle_event_id": event[
                        "lifecycle_event_id"
                    ],
                    "lifecycle_event_digest": event[
                        "lifecycle_event_digest"
                    ],
                    "semantic_terminal_id": semantic_terminal_id,
                }
            ],
        }

    evidence_fields = tuple(method["evidence_contract"]["exact_fields"])
    authority = _evidence_lineage_authority(method)
    try:
        decision_at = _utc(decision_time)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("EVIDENCE_DECISION_TIME_INVALID") from error
    valid_rows: list[
        tuple[
            dict[str, object],
            dict[str, object],
            dict[str, str],
        ]
    ] = []
    invalid_rows: list[tuple[dict[str, object], str]] = []
    for member, row in decoded:
        identity, reason, target_scope = _admit_evidence_row(
            row,
            exact_fields=evidence_fields,
            authority=authority,
            decision_at=decision_at,
        )
        if reason is None and target_scope != (
            episode["path_instance_id"],
        ):
            reason = (
                f'{row["evidence_id"]}:'
                "TARGET_SCOPE_NOT_EXACT_LEDGER_TARGET"
            )
        if reason is not None or identity is None:
            invalid_rows.append(
                (
                    member,
                    reason
                    or "UNKNOWN_EVIDENCE:LEDGER_ADMISSION_INVALID",
                )
            )
        else:
            valid_rows.append((member, row, identity))
    if invalid_rows:
        effects = _rejection_effects(
            method=method,
            episode=episode,
            batch_digest=batch_digest,
            members_and_reasons=invalid_rows,
        )
        return {
            "effects": effects,
            "accepted_evidence_ids": [],
            "rejected_evidence": sorted(
                reason for _member, reason in invalid_rows
            ),
            "admitted_identity_entries": [],
        }
    evidence_ids = [identity["evidence_id"] for _m, _r, identity in valid_rows]
    duplicate_ids = {
        evidence_id
        for evidence_id in evidence_ids
        if evidence_ids.count(evidence_id) > 1
    }
    if duplicate_ids:
        duplicate_rows = [
            (
                member,
                f'{identity["evidence_id"]}:'
                "EVIDENCE_ID_DUPLICATE_IN_TARGET_BATCH",
            )
            for member, _row, identity in valid_rows
            if identity["evidence_id"] in duplicate_ids
        ]
        effects = _rejection_effects(
            method=method,
            episode=episode,
            batch_digest=batch_digest,
            members_and_reasons=duplicate_rows,
        )
        return {
            "effects": effects,
            "accepted_evidence_ids": [],
            "rejected_evidence": sorted(
                reason for _member, reason in duplicate_rows
            ),
            "admitted_identity_entries": [],
        }
    cross_receipt_rejections: list[
        tuple[dict[str, object], str]
    ] = []
    for member, _row, identity in valid_rows:
        evidence_id = identity["evidence_id"]
        underlying_id = identity["underlying_increment_id"]
        dependency_group = identity["dependency_group"]
        if evidence_id in state["evidence_identities"]:
            prior = state["evidence_identities"][evidence_id]
            reason = (
                "EVIDENCE_ID_REPLAY"
                if prior["content_digest"] == identity["content_digest"]
                else "EVIDENCE_ID_CONTENT_OR_LINEAGE_DRIFT"
            )
            cross_receipt_rejections.append(
                (member, f"{evidence_id}:{reason}")
            )
        elif (
            underlying_id in state["underlying_groups"]
            and state["underlying_groups"][underlying_id]
            != dependency_group
        ):
            cross_receipt_rejections.append(
                (
                    member,
                    f"{evidence_id}:"
                    "UNDERLYING_INCREMENT_DIFFERENT_GROUP_ALIAS",
                )
            )
    if cross_receipt_rejections:
        effects = _rejection_effects(
            method=method,
            episode=episode,
            batch_digest=batch_digest,
            members_and_reasons=cross_receipt_rejections,
        )
        return {
            "effects": effects,
            "accepted_evidence_ids": [],
            "rejected_evidence": sorted(
                reason
                for _member, reason in cross_receipt_rejections
            ),
            "admitted_identity_entries": [],
        }
    hard_rows = [
        item
        for item in valid_rows
        if item[1]["direction"] == "HARD_FALSIFIER"
    ]
    ordinary_rows = [
        item
        for item in valid_rows
        if item[1]["direction"] != "HARD_FALSIFIER"
    ]
    terminal_authority_id = (
        f'EVIDENCE-AUTHORITY:{authority["authority_id"]}:'
        f'{episode["mechanism_id"]}'
    )
    hard_effects: list[dict[str, object]] = []
    for member, row, identity in hard_rows:
        effective_at = _canonical_utc_text(row["available_at"])
        semantic_terminal_id = _semantic_terminal_id(
            scope_digest=_episode_scope_digest(episode),
            target_id=episode["path_instance_id"],
            terminal_status="FALSIFIED",
            terminal_event_at=effective_at,
            terminal_authority_id=terminal_authority_id,
            terminal_reason_priority=contract[
                "terminal_reason_priority"
            ]["HARD_FALSIFIER"],
            reason_code="HARD_FALSIFIER",
        )
        hard_effects.append(
            _build_effect(
                method=method,
                effect_kind="HARD_FALSIFIER",
                target_id=episode["path_instance_id"],
                scope_digest=_episode_scope_digest(episode),
                batch_digest=batch_digest,
                batch_member_digest=member["member_digest"],
                identity_entry=identity,
                selected_evidence=row,
                direction="HARD_FALSIFIER",
                signed_ordinal_delta=0,
                effective_at=effective_at,
                terminal_status="FALSIFIED",
                terminal_event_at=effective_at,
                terminal_source_digest=identity["content_digest"],
                terminal_authority_id=terminal_authority_id,
                semantic_terminal_id=semantic_terminal_id,
                reason_code="HARD_FALSIFIER",
            )
        )
    terminal_candidates = [
        _terminal_winner_from_effect(effect, method)
        for effect in hard_effects
    ]
    if state["terminal_winner"] is not None:
        terminal_candidates.append(
            copy.deepcopy(state["terminal_winner"])
        )
    cutoff = (
        _utc(
            min(
                terminal_candidates,
                key=_terminal_winner_rank,
            )["terminal_event_at"]
        )
        if terminal_candidates
        else None
    )
    ordinary_effects: list[dict[str, object]] = []
    cutoff_rejections: list[tuple[dict[str, object], str]] = []
    admitted_rows = [
        (member, row, identity)
        for member, row, identity in hard_rows
    ]
    for member, row, identity in ordinary_rows:
        effective_at = _utc(row["available_at"])
        if cutoff is not None and effective_at >= cutoff:
            cutoff_rejections.append(
                (
                    member,
                    f'{identity["evidence_id"]}:'
                    "TERMINAL_CUTOFF_NOT_STRICTLY_BEFORE",
                )
            )
            continue
        increment = _evidence_increment(row)
        admitted_rows.append((member, row, identity))
        ordinary_effects.append(
            _build_effect(
                method=method,
                effect_kind="DEPENDENCY_GROUP_CANDIDATE",
                target_id=episode["path_instance_id"],
                scope_digest=_episode_scope_digest(episode),
                batch_digest=batch_digest,
                batch_member_digest=member["member_digest"],
                identity_entry=identity,
                selected_evidence=row,
                direction=row["direction"],
                signed_ordinal_delta=increment,
                effective_at=_canonical_utc_text(
                    row["available_at"]
                ),
            )
        )
    rejection_effects = _rejection_effects(
        method=method,
        episode=episode,
        batch_digest=batch_digest,
        members_and_reasons=cutoff_rejections,
    )
    effects = sorted(
        [*hard_effects, *ordinary_effects, *rejection_effects],
        key=lambda effect: effect["effect_digest"],
    )
    accepted_ids = sorted(
        identity["evidence_id"]
        for _member, _row, identity in admitted_rows
    )
    admitted = sorted(
        (
            copy.deepcopy(identity)
            for _member, _row, identity in admitted_rows
        ),
        key=lambda identity: identity["evidence_id"],
    )
    effects.sort(key=lambda effect: effect["effect_digest"])
    return {
        "effects": effects,
        "accepted_evidence_ids": accepted_ids,
        "rejected_evidence": sorted(
            reason for _member, reason in cutoff_rejections
        ),
        "admitted_identity_entries": admitted,
    }


def _apply_validated_effects(
    *,
    state: dict[str, object],
    derivation: dict[str, object],
    method: dict[str, object],
) -> dict[str, object]:
    updated = copy.deepcopy(state)
    effects = derivation["effects"]
    terminal_statuses = set(
        method["evidence_ledger_contract"]["terminal_statuses"]
    )
    for identity in derivation["admitted_identity_entries"]:
        updated["evidence_identities"][identity["evidence_id"]] = (
            copy.deepcopy(identity)
        )
        updated["underlying_groups"].setdefault(
            identity["underlying_increment_id"],
            identity["dependency_group"],
        )
    for identity in derivation.get(
        "admitted_lifecycle_identity_entries",
        [],
    ):
        if not _exact_keys(
            identity,
            tuple(
                method["evidence_ledger_contract"][
                    "lifecycle_identity_entry_exact_fields"
                ]
            ),
        ):
            raise ValueError("LIFECYCLE_IDENTITY_SCHEMA_INVALID")
        updated["lifecycle_identities"][
            identity["lifecycle_event_id"]
        ] = copy.deepcopy(identity)
    ordinary_effects = [
        effect
        for effect in effects
        if effect["effect_kind"] == "DEPENDENCY_GROUP_CANDIDATE"
    ]
    terminal_effects = [
        effect
        for effect in effects
        if effect["effect_kind"]
        in {"HARD_FALSIFIER", "LIFECYCLE_TERMINAL"}
    ]
    if any(
        effect["effect_kind"]
        not in {
            "DEPENDENCY_GROUP_CANDIDATE",
            "HARD_FALSIFIER",
            "LIFECYCLE_TERMINAL",
            "REJECTION",
        }
        for effect in effects
    ):
        raise ValueError("LEDGER_EFFECT_KIND_COMBINATION_INVALID")
    for effect in ordinary_effects:
        candidate = _group_winner_from_effect(effect, method)
        updated["group_candidates"][candidate["evidence_id"]] = (
            candidate
        )
    if terminal_effects:
        candidate = min(
            (
                _terminal_winner_from_effect(effect, method)
                for effect in terminal_effects
            ),
            key=_terminal_winner_rank,
        )
        prior = updated["terminal_winner"]
        if (
            prior is None
            or _terminal_winner_rank(candidate)
            < _terminal_winner_rank(prior)
        ):
            updated["terminal_winner"] = candidate
    _recompute_candidate_state(updated)
    if updated["terminal_winner"] is not None:
        updated["status"] = updated["terminal_winner"][
            "terminal_status"
        ]
        return updated
    updated["status"] = (
        "ACTIVE"
        if ordinary_effects
        else "UNKNOWN"
    )
    return updated


def _evidence_receipt_hash(receipt: object) -> str:
    if type(receipt) is not dict or "receipt_hash" not in receipt:
        raise ValueError("EVIDENCE_RECEIPT_HASH_INPUT_INVALID")
    return _canonical_digest(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_hash"
        }
    )


def _episode_shape_valid(
    episode: object,
    method: dict[str, object],
) -> bool:
    required = {
        "episode_id",
        "observation_frame_id",
        "path_instance_id",
        "mechanism_id",
        "status",
        "support",
        "receipt_chain",
    }
    return (
        type(episode) is dict
        and set(episode) == required
        and all(
            type(episode.get(field)) is str
            and episode[field] != ""
            for field in (
                "episode_id",
                "observation_frame_id",
                "path_instance_id",
                "mechanism_id",
                "status",
            )
        )
        and episode["mechanism_id"]
        in method["finite_mechanism_library"]["mechanism_ids"]
        and type(episode.get("support")) is int
        and type(episode.get("receipt_chain")) is list
    )


def _reduce_evidence_receipt_chain(
    episode: dict[str, object],
    method: dict[str, object] | None = None,
    *,
    expected_tip_hash: str | None = None,
) -> dict[str, object]:
    pinned_method = _load_method_authority_view()
    if method is not None and method != pinned_method:
        raise ValueError("METHOD_AUTHORITY_IN_MEMORY_SUBSTITUTION")
    method = pinned_method
    if not _episode_shape_valid(episode, method):
        raise ValueError("EPISODE_SCHEMA_IDENTITY_OR_AUTHORITY_INVALID")
    contract = method["evidence_ledger_contract"]
    receipt_fields = tuple(contract["receipt_exact_fields"])
    scope_digest = _episode_scope_digest(episode)
    state = _initial_ledger_state(episode)
    batch_receipts: dict[str, list[dict[str, object]]] = {}
    previous_hash = "GENESIS"
    previous_decision_at: datetime | None = None
    seen_idempotency_keys: set[str] = set()
    accepted_lifecycle_contexts: set[
        tuple[str, str, str]
    ] = set()
    chain = episode["receipt_chain"]
    if not chain and (
        episode["status"] != "ACTIVE"
        or episode["support"] != 0
    ):
        raise ValueError("EVIDENCE_LEDGER_GENESIS_INVALID")
    for index, receipt in enumerate(chain, start=1):
        if not _exact_keys(receipt, receipt_fields):
            raise ValueError("EVIDENCE_RECEIPT_SCHEMA_INVALID")
        if (
            receipt.get("receipt_id") != f'{episode["episode_id"]}-R{index}'
            or receipt.get("receipt_schema_id")
            != contract["receipt_schema_id"]
            or receipt.get("scope_digest") != scope_digest
            or receipt.get("method_authority_id")
            != method["contract_id"]
            or receipt.get("method_authority_raw_sha256")
            != METHOD_AUTHORITY_RAW_SHA256
            or receipt.get("previous_receipt_hash") != previous_hash
            or receipt.get("expected_prefix_hash") != previous_hash
            or receipt.get("transition_kind")
            not in contract["transition_kinds"]
            or type(receipt.get("canonical_batch")) is not list
            or not receipt["canonical_batch"]
        ):
            raise ValueError("EVIDENCE_RECEIPT_AUTHORITY_OR_PREFIX_INVALID")
        try:
            decision_at = _utc(receipt.get("decision_time"))
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("EVIDENCE_RECEIPT_DECISION_TIME_INVALID") from error
        if receipt.get("decision_time") != _canonical_utc_text(
            receipt.get("decision_time")
        ):
            raise ValueError(
                "EVIDENCE_RECEIPT_DECISION_TIME_NOT_CANONICAL_UTC"
            )
        if (
            previous_decision_at is not None
            and decision_at < previous_decision_at
        ):
            raise ValueError(
                "EVIDENCE_RECEIPT_DECISION_TIME_REGRESSION"
            )
        if receipt.get("batch_digest") != _transition_batch_digest(
            receipt["canonical_batch"]
        ):
            raise ValueError("EVIDENCE_RECEIPT_BATCH_DIGEST_INVALID")
        derivation = _derive_validated_effects(
            episode=episode,
            state=state,
            transition_kind=receipt["transition_kind"],
            canonical_batch=receipt["canonical_batch"],
            decision_time=receipt["decision_time"],
            method=method,
        )
        effects = derivation["effects"]
        rejection_class = _rejection_class(
            derivation["rejected_evidence"],
            method,
        )
        idempotency_key = _transition_idempotency_key(
            scope_digest=scope_digest,
            transition_kind=receipt["transition_kind"],
            batch_digest=receipt["batch_digest"],
            decision_time=receipt["decision_time"],
            rejection_class=rejection_class,
        )
        lifecycle_context = (
            receipt["transition_kind"],
            receipt["batch_digest"],
            receipt["decision_time"],
        )
        if (
            idempotency_key in seen_idempotency_keys
            or (
                receipt["transition_kind"]
                == "LIFECYCLE_TERMINAL"
                and lifecycle_context
                in accepted_lifecycle_contexts
            )
        ):
            raise ValueError(
                "EVIDENCE_RECEIPT_IDEMPOTENT_DUPLICATE_FORBIDDEN"
            )
        if not effects and not derivation["rejected_evidence"]:
            raise ValueError("EVIDENCE_RECEIPT_EMPTY_EFFECT_NOOP_MUST_NOT_EXIST")
        for effect in effects:
            if (
                not _exact_keys(
                    effect,
                    tuple(contract["effect_exact_fields"]),
                )
                or effect.get("effect_digest") != _effect_digest(effect)
                or effect.get("scope_digest") != scope_digest
                or effect.get("target_id")
                != episode["path_instance_id"]
                or effect.get("batch_digest")
                != receipt["batch_digest"]
            ):
                raise ValueError("EVIDENCE_LEDGER_EFFECT_INVALID")
        state_before = copy.deepcopy(state)
        state_after = _apply_validated_effects(
            state=state_before,
            derivation=derivation,
            method=method,
        )
        expected_projection = {
            "validated_effects": effects,
            "effects_digest": _effects_digest(effects),
            "accepted_evidence_ids": derivation[
                "accepted_evidence_ids"
            ],
            "rejected_evidence": derivation["rejected_evidence"],
            "admitted_identity_entries": derivation[
                "admitted_identity_entries"
            ],
            "admitted_lifecycle_identity_entries": derivation.get(
                "admitted_lifecycle_identity_entries",
                [],
            ),
            "rejection_class": rejection_class,
            "idempotency_key": idempotency_key,
            "group_winners_after": _ledger_state_projection(state_after)[
                "group_winners"
            ],
            "group_candidates_after": _ledger_state_projection(
                state_after
            )["group_candidates"],
            "terminal_winner_after": _ledger_state_projection(
                state_after
            )["terminal_winner"],
            "raw_support_before": state_before["raw_support"],
            "raw_support_after": state_after["raw_support"],
            "status_before": state_before["status"],
            "status_after": state_after["status"],
            "support_before": state_before["support"],
            "support_after": state_after["support"],
            "state_before_digest": _ledger_state_digest(state_before),
            "state_after_digest": _ledger_state_digest(state_after),
        }
        if any(
            receipt.get(field) != value
            for field, value in expected_projection.items()
        ):
            raise ValueError("EVIDENCE_RECEIPT_TRANSITION_NOT_DERIVABLE")
        if receipt.get("receipt_hash") != _evidence_receipt_hash(receipt):
            raise ValueError("EVIDENCE_RECEIPT_HASH_INVALID")
        batch_receipts.setdefault(receipt["batch_digest"], []).append(
            receipt
        )
        state = state_after
        previous_hash = receipt["receipt_hash"]
        previous_decision_at = decision_at
        seen_idempotency_keys.add(idempotency_key)
        if (
            receipt["transition_kind"] == "LIFECYCLE_TERMINAL"
            and rejection_class == "NONE"
        ):
            accepted_lifecycle_contexts.add(lifecycle_context)
    if (
        state["status"] != episode["status"]
        or state["support"] != episode["support"]
    ):
        raise ValueError("EVIDENCE_RECEIPT_EPISODE_TIP_MISMATCH")
    if expected_tip_hash is not None:
        if (
            type(expected_tip_hash) is not str
            or expected_tip_hash != previous_hash
        ):
            raise ValueError("EVIDENCE_EXPECTED_TIP_MISMATCH")
    return {
        "tip_hash": previous_hash,
        "last_decision_time": (
            _canonical_utc_text(previous_decision_at.isoformat())
            if previous_decision_at is not None
            else None
        ),
        "status": state["status"],
        "raw_support": state["raw_support"],
        "support": state["support"],
        "group_winners": copy.deepcopy(state["group_winners"]),
        "group_candidates": copy.deepcopy(
            state["group_candidates"]
        ),
        "terminal_winner": copy.deepcopy(
            state["terminal_winner"]
        ),
        "evidence_identities": copy.deepcopy(
            state["evidence_identities"]
        ),
        "lifecycle_identities": copy.deepcopy(
            state["lifecycle_identities"]
        ),
        "underlying_groups": copy.deepcopy(state["underlying_groups"]),
        "batch_receipts": batch_receipts,
        "state_digest": _ledger_state_digest(state),
    }


def _append_evidence_receipt(
    episode: dict[str, object],
    *,
    transition_kind: str,
    canonical_batch: list[dict[str, object]],
    decision_time: object,
) -> dict[str, object]:
    method = _load_method_authority_view()
    reduced = _reduce_evidence_receipt_chain(episode, method)
    try:
        canonical_decision_time = _canonical_utc_text(decision_time)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("EVIDENCE_DECISION_TIME_INVALID") from error
    if (
        reduced["last_decision_time"] is not None
        and _utc(canonical_decision_time)
        < _utc(reduced["last_decision_time"])
    ):
        raise ValueError("EVIDENCE_DECISION_TIME_REGRESSION")
    state_before = {
        "scope_digest": _episode_scope_digest(episode),
        "status": reduced["status"],
        "raw_support": reduced["raw_support"],
        "support": reduced["support"],
        "group_winners": copy.deepcopy(reduced["group_winners"]),
        "group_candidates": copy.deepcopy(
            reduced["group_candidates"]
        ),
        "terminal_winner": copy.deepcopy(
            reduced["terminal_winner"]
        ),
        "evidence_identities": copy.deepcopy(
            reduced["evidence_identities"]
        ),
        "lifecycle_identities": copy.deepcopy(
            reduced["lifecycle_identities"]
        ),
        "underlying_groups": copy.deepcopy(
            reduced["underlying_groups"]
        ),
    }
    derivation = _derive_validated_effects(
        episode=episode,
        state=state_before,
        transition_kind=transition_kind,
        canonical_batch=canonical_batch,
        decision_time=canonical_decision_time,
        method=method,
    )
    if not derivation["effects"] and not derivation["rejected_evidence"]:
        return copy.deepcopy(episode)
    state_after = _apply_validated_effects(
        state=state_before,
        derivation=derivation,
        method=method,
    )
    contract = method["evidence_ledger_contract"]
    batch_digest = _transition_batch_digest(canonical_batch)
    effects = derivation["effects"]
    rejection_class = _rejection_class(
        derivation["rejected_evidence"],
        method,
    )
    idempotency_key = _transition_idempotency_key(
        scope_digest=_episode_scope_digest(episode),
        transition_kind=transition_kind,
        batch_digest=batch_digest,
        decision_time=canonical_decision_time,
        rejection_class=rejection_class,
    )
    prior_batch_receipts = reduced["batch_receipts"].get(
        batch_digest,
        [],
    )
    if any(
        receipt["idempotency_key"] == idempotency_key
        or (
            transition_kind == "LIFECYCLE_TERMINAL"
            and receipt["transition_kind"]
            == "LIFECYCLE_TERMINAL"
            and receipt["decision_time"]
            == canonical_decision_time
            and receipt["rejection_class"] == "NONE"
        )
        for receipt in prior_batch_receipts
    ):
        return copy.deepcopy(episode)
    receipt = {
        "receipt_id": (
            f'{episode["episode_id"]}-R'
            f'{len(episode["receipt_chain"]) + 1}'
        ),
        "receipt_schema_id": contract["receipt_schema_id"],
        "scope_digest": _episode_scope_digest(episode),
        "method_authority_id": method["contract_id"],
        "method_authority_raw_sha256": METHOD_AUTHORITY_RAW_SHA256,
        "previous_receipt_hash": reduced["tip_hash"],
        "expected_prefix_hash": reduced["tip_hash"],
        "decision_time": canonical_decision_time,
        "transition_kind": transition_kind,
        "idempotency_key": idempotency_key,
        "rejection_class": rejection_class,
        "canonical_batch": copy.deepcopy(canonical_batch),
        "batch_digest": batch_digest,
        "validated_effects": copy.deepcopy(effects),
        "effects_digest": _effects_digest(effects),
        "accepted_evidence_ids": list(
            derivation["accepted_evidence_ids"]
        ),
        "rejected_evidence": list(derivation["rejected_evidence"]),
        "admitted_identity_entries": copy.deepcopy(
            derivation["admitted_identity_entries"]
        ),
        "admitted_lifecycle_identity_entries": copy.deepcopy(
            derivation.get(
                "admitted_lifecycle_identity_entries",
                [],
            )
        ),
        "group_winners_after": _ledger_state_projection(state_after)[
            "group_winners"
        ],
        "group_candidates_after": _ledger_state_projection(
            state_after
        )["group_candidates"],
        "terminal_winner_after": _ledger_state_projection(
            state_after
        )["terminal_winner"],
        "raw_support_before": state_before["raw_support"],
        "raw_support_after": state_after["raw_support"],
        "status_before": state_before["status"],
        "status_after": state_after["status"],
        "support_before": state_before["support"],
        "support_after": state_after["support"],
        "state_before_digest": _ledger_state_digest(state_before),
        "state_after_digest": _ledger_state_digest(state_after),
        "receipt_hash": "",
    }
    receipt["receipt_hash"] = _evidence_receipt_hash(receipt)
    updated = copy.deepcopy(episode)
    updated["status"] = state_after["status"]
    updated["support"] = state_after["support"]
    updated["receipt_chain"].append(receipt)
    _reduce_evidence_receipt_chain(updated, method)
    return updated


def _episode_reinstantiation_valid(
    terminal_episode: object,
    candidate_episode: object,
) -> bool:
    try:
        method = _load_method_authority_view()
        terminal = _reduce_evidence_receipt_chain(
            terminal_episode,
            method,
        )
        candidate = _reduce_evidence_receipt_chain(
            candidate_episode,
            method,
        )
    except (TypeError, ValueError):
        return False
    identity_fields = (
        "episode_id",
        "observation_frame_id",
        "path_instance_id",
    )
    return (
        terminal["status"]
        in set(method["evidence_ledger_contract"]["terminal_statuses"])
        and terminal_episode["receipt_chain"] != []
        and candidate["status"] == "ACTIVE"
        and candidate["support"] == 0
        and candidate_episode["receipt_chain"] == []
        and candidate_episode["mechanism_id"]
        == terminal_episode["mechanism_id"]
        and all(
            candidate_episode[field] != terminal_episode[field]
            for field in identity_fields
        )
    )


def _update_episode(
    episode: dict[str, object],
    evidence_rows: list[dict[str, object]],
    decision_time: object,
    evidence_fields: tuple[str, ...],
    *,
    lifecycle_events: list[dict[str, object]] | None = None,
    expected_tip_hash: str | None = None,
    predecessor_episode: dict[str, object] | None = None,
) -> dict[str, object]:
    method = _load_method_authority_view()
    if evidence_fields != tuple(method["evidence_contract"]["exact_fields"]):
        raise ValueError("EVIDENCE_SCHEMA_AUTHORITY_MISMATCH")
    if type(evidence_rows) is not list:
        raise ValueError("EVIDENCE_BATCH_INVALID")
    lifecycle_events = [] if lifecycle_events is None else lifecycle_events
    if type(lifecycle_events) is not list:
        raise ValueError("LIFECYCLE_BATCH_INVALID")
    if predecessor_episode is not None and not _episode_reinstantiation_valid(
        predecessor_episode,
        episode,
    ):
        raise ValueError("EPISODE_REINSTANTIATION_INVALID")
    updated = copy.deepcopy(episode)
    ledger = _reduce_evidence_receipt_chain(
        updated,
        method,
        expected_tip_hash=expected_tip_hash,
    )
    try:
        canonical_decision_time = _canonical_utc_text(decision_time)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("EVIDENCE_DECISION_TIME_INVALID") from error
    if (
        ledger["last_decision_time"] is not None
        and _utc(canonical_decision_time)
        < _utc(ledger["last_decision_time"])
    ):
        raise ValueError("EVIDENCE_DECISION_TIME_REGRESSION")
    transition_kind, canonical_batch = _canonical_transition_batch(
        evidence_rows,
        lifecycle_events,
        method,
    )
    if transition_kind is None:
        return updated
    batch_digest = _transition_batch_digest(canonical_batch)
    prior_batch_receipts = ledger["batch_receipts"].get(
        batch_digest,
        [],
    )
    if any(
        receipt["rejection_class"]
        in {"PERMANENT", "RESOURCE_CAPACITY_REQUIRED"}
        for receipt in prior_batch_receipts
    ):
        return updated
    if (
        transition_kind == "LIFECYCLE_TERMINAL"
        and any(
            receipt["rejection_class"] == "NONE"
            and receipt["decision_time"]
            == canonical_decision_time
            for receipt in prior_batch_receipts
        )
    ):
        return updated
    return _append_evidence_receipt(
        updated,
        transition_kind=transition_kind,
        canonical_batch=canonical_batch,
        decision_time=canonical_decision_time,
    )


def _synthetic_episode(label: str) -> dict[str, object]:
    if type(label) is not str or label == "":
        raise ValueError("SYNTHETIC_EPISODE_LABEL_INVALID")
    return {
        "episode_id": f"EP-{label}",
        "observation_frame_id": f"OF-{label}",
        "path_instance_id": f"PI-{label}",
        "mechanism_id": "CONTINUATION",
        "status": "ACTIVE",
        "support": 0,
        "receipt_chain": [],
    }


def _expiry_disposition(*, expired: object, current: str) -> str:
    if type(expired) is not bool:
        return "UNKNOWN"
    if expired:
        return "EXPIRED"
    return current


def _synthetic_path_events(
    milestones: list[str],
    *,
    path_started_at: str,
    path_instance_id: str = "PI-SYNTHETIC-001",
    terminal_reason: str = "TERMINAL_MILESTONE",
    terminal_trigger_id: str | None = None,
    terminal_event_at: str | None = None,
) -> list[dict[str, object]]:
    started_at = _utc(path_started_at)
    events: list[dict[str, object]] = []
    for index, milestone in enumerate(milestones):
        event_at = started_at + timedelta(seconds=index + 1)
        is_final = index == len(milestones) - 1
        if is_final and terminal_event_at is not None:
            event_at = _utc(terminal_event_at)
        timestamp = event_at.isoformat().replace("+00:00", "Z")
        events.append(
            {
                "path_event_id": f"PATH-EVENT-{index + 1:03d}",
                "path_instance_id": path_instance_id,
                "milestone": milestone,
                "event_at": timestamp,
                "available_at": timestamp,
                "terminal_reason": terminal_reason if is_final else None,
                "terminal_trigger_id": terminal_trigger_id if is_final else None,
                "source_version": "SYNTHETIC-PATH-EVENT-V1",
            }
        )
    return events


def _path_spec_digest(spec: object, path_spec_fields: tuple[str, ...]) -> str:
    if not _exact_keys(spec, path_spec_fields):
        raise ValueError("PATH_SPEC_DIGEST_INPUT_INVALID")
    canonical = json.dumps(
        spec,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _path_spec_authorities_by_id(
    authority_registry: object,
    authority_fields: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if type(authority_registry) is not list or not authority_registry:
        raise ValueError("PATH_SPEC_AUTHORITY_REGISTRY_INVALID")
    indexed: dict[str, dict[str, object]] = {}
    for authority in authority_registry:
        if not _exact_keys(authority, authority_fields):
            raise ValueError("PATH_SPEC_AUTHORITY_INVALID")
        path_id = authority.get("path_id")
        digest = authority.get("path_spec_digest")
        if (
            type(path_id) is not str
            or path_id == ""
            or path_id in indexed
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("PATH_SPEC_AUTHORITY_INVALID")
        indexed[path_id] = authority
    return indexed


def _path_valid(
    events: object,
    spec: object,
    *,
    decision_time: object,
    path_started_at: object,
    requested_horizon_seconds: object,
    path_spec_fields: tuple[str, ...],
    path_event_fields: tuple[str, ...],
) -> tuple[bool, str]:
    if not _exact_keys(spec, path_spec_fields):
        return False, "PATH_SPEC_SCHEMA_INVALID"
    try:
        method = _load_method_authority_view()
        path_contract = method["path_contract"]
        path_authorities = _path_spec_authorities_by_id(
            path_contract["path_spec_authority_registry"],
            tuple(path_contract["path_spec_authority_exact_fields"]),
        )
        path_id = spec.get("path_id")
        if type(path_id) is not str or path_id not in path_authorities:
            return False, "PATH_SPEC_UNREGISTERED"
        if _path_spec_digest(spec, path_spec_fields) != path_authorities[path_id]["path_spec_digest"]:
            return False, "PATH_SPEC_AUTHORITY_DIGEST_MISMATCH"
    except ValueError:
        return False, "PATH_SPEC_AUTHORITY_INVALID"
    if (
        spec.get("observation_count_rule") != "VARIABLE_POSITIVE_COUNT"
        or spec.get("event_time_stopping_rule")
        != "STOP_AT_FROZEN_EXPIRY_HARD_FALSIFIER_OR_TERMINAL"
        or spec.get("stopping_policy_id")
        != "EARLIEST_OF_TERMINAL_EXPIRY_HARD_FALSIFIER_V1"
    ):
        return False, "STOPPING_POLICY_INVALID"
    if (
        spec.get("horizon_rule") != "EVENT_TIME_EXPIRY_NOT_DAY_COUNT"
        or spec.get("expiry_rule") != "NO_EXTENSION"
        or spec.get("path_event_schema_id") != "PATH_EVENT_EXACT_V1"
    ):
        return False, "HORIZON_POLICY_INVALID"
    frozen_horizon = spec.get("frozen_horizon_seconds")
    if (
        type(frozen_horizon) is not int
        or frozen_horizon <= 0
        or type(requested_horizon_seconds) is not int
        or requested_horizon_seconds <= 0
        or requested_horizon_seconds > frozen_horizon
    ):
        return False, "HORIZON_EXTENSION_OR_TYPE_INVALID"
    try:
        decision_at = _utc(decision_time)
        started_at = _utc(path_started_at)
    except (TypeError, ValueError, OverflowError):
        return False, "PATH_CLOCK_INVALID"
    if started_at > decision_at:
        return False, "PATH_START_AFTER_DECISION_TIME"
    if type(events) is not list or not events:
        return False, "SEQUENCE_INVALID"

    event_ids: list[str] = []
    path_instance_ids: list[str] = []
    milestones: list[str] = []
    event_times: list[datetime] = []
    terminal_indexes: list[int] = []
    expiry_at = started_at + timedelta(seconds=requested_horizon_seconds)
    for index, event in enumerate(events):
        if not _exact_keys(event, path_event_fields):
            return False, "PATH_EVENT_SCHEMA_INVALID"
        if (
            type(event.get("path_event_id")) is not str
            or event["path_event_id"] == ""
            or type(event.get("path_instance_id")) is not str
            or event["path_instance_id"] == ""
            or type(event.get("milestone")) is not str
            or event["milestone"] == ""
            or type(event.get("source_version")) is not str
            or event["source_version"] == ""
        ):
            return False, "PATH_EVENT_IDENTITY_INVALID"
        try:
            event_at = _utc(event.get("event_at"))
            available_at = _utc(event.get("available_at"))
        except (TypeError, ValueError, OverflowError):
            return False, "PATH_EVENT_TIME_INVALID"
        if event_at < started_at:
            return False, "EVENT_BEFORE_PATH_START"
        if event_times and event_at <= event_times[-1]:
            return False, "EVENT_TIME_ORDER_INVALID"
        if event_at > available_at or available_at > decision_at:
            return False, "EVENT_NOT_CAUSALLY_AVAILABLE"
        if event_at > expiry_at:
            return False, "EVENT_AFTER_EXPIRY"
        terminal_reason = event.get("terminal_reason")
        terminal_trigger_id = event.get("terminal_trigger_id")
        if terminal_reason is not None:
            terminal_indexes.append(index)
            if terminal_reason not in {
                "TERMINAL_MILESTONE",
                "HARD_FALSIFIER",
                "EXPIRY",
            }:
                return False, "TERMINAL_REASON_INVALID"
            if terminal_reason == "HARD_FALSIFIER":
                if (
                    type(terminal_trigger_id) is not str
                    or terminal_trigger_id not in spec.get("hard_falsifiers", ())
                ):
                    return False, "HARD_FALSIFIER_TRIGGER_INVALID"
            elif terminal_trigger_id is not None:
                return False, "TERMINAL_TRIGGER_INVALID"
            if terminal_reason == "EXPIRY" and event_at != expiry_at:
                return False, "EXPIRY_TIMESTAMP_MISMATCH"
        elif terminal_trigger_id is not None:
            return False, "TERMINAL_TRIGGER_WITHOUT_REASON"
        event_ids.append(event["path_event_id"])
        path_instance_ids.append(event["path_instance_id"])
        milestones.append(event["milestone"])
        event_times.append(event_at)

    if len(event_ids) != len(set(event_ids)) or len(set(path_instance_ids)) != 1:
        return False, "PATH_EVENT_IDENTITY_INVALID"
    if terminal_indexes != [len(events) - 1]:
        return False, (
            "EVENT_AFTER_TERMINAL"
            if terminal_indexes
            else "STOPPING_RULE_VIOLATION"
        )
    if milestones[-1] != "TERMINAL":
        return False, "STOPPING_RULE_VIOLATION"

    vocabulary = tuple(spec.get("milestone_vocabulary", ()))
    if any(milestone not in vocabulary for milestone in milestones):
        return False, "MILESTONE_UNREGISTERED"
    repeatable = set(spec.get("repeatable_milestones", ()))
    for milestone in vocabulary:
        if milestones.count(milestone) > 1 and milestone not in repeatable:
            return False, "REPEAT_NOT_DECLARED"
    skippable = set(spec.get("skippable_milestones", ()))
    for milestone in vocabulary:
        if milestone not in skippable and milestone not in milestones:
            return False, "REQUIRED_MILESTONE_MISSING"
    for left, right in [
        *spec.get("required_partial_order_edges", ()),
        *spec.get("optional_partial_order_edges", ()),
    ]:
        if (
            left in milestones
            and right in milestones
            and milestones.index(left) >= milestones.index(right)
        ):
            return False, "PARTIAL_ORDER_VIOLATION"
    guard = spec.get("runtime_capacity_guard")
    if (
        type(guard) is not dict
        or type(guard.get("max_in_memory_observations")) is not int
        or guard["max_in_memory_observations"] <= 0
    ):
        return False, "CAPACITY_GUARD_INVALID"
    if len(milestones) > guard["max_in_memory_observations"]:
        return True, "COMPACT_REQUIRED_RECEIPT_CONTINUATION"
    return True, "VALID"


def _can_merge(left: dict[str, object], right: dict[str, object]) -> bool:
    left_class = left.get("merge_equivalence_class")
    return type(left_class) is str and left_class != "" and left_class == right.get("merge_equivalence_class")


def _registered_mechanism(mechanism_id: object, library: tuple[str, ...]) -> bool:
    return type(mechanism_id) is str and mechanism_id in library


def _volume_wick_candidates(*, volume_spike: object, long_wick: object, declared: tuple[str, ...]) -> tuple[str, ...]:
    if type(volume_spike) is not bool or type(long_wick) is not bool:
        return ("OTHER",)
    if volume_spike and long_wick:
        return declared
    return ("OTHER",)


def _feed_disposition(*, covered: object, events: object) -> str:
    if type(covered) is not bool or type(events) is not list:
        return "UNKNOWN"
    if not covered:
        return "UNKNOWN"
    return "NO_EVENT_OBSERVED" if not events else "OBSERVED"


def _append_late_event(receipts: list[dict[str, object]], event: dict[str, object]) -> list[dict[str, object]]:
    updated = copy.deepcopy(receipts)
    prior_id = updated[-1]["receipt_id"] if updated else None
    updated.append({"receipt_id": f"r{len(updated) + 1}", "previous_receipt_id": prior_id, "event_id": event["event_id"]})
    return updated


def _primitive_support_update(
    prior: dict[str, int],
    evidence_rows: list[dict[str, object]],
    decision_time: object,
    evidence_fields: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if type(prior) is not dict or set(prior) != set(MECHANISMS) or any(type(value) is not int for value in prior.values()):
        raise ValueError("PRIMITIVE_SUPPORT_INVALID")
    updated: dict[str, dict[str, object]] = {}
    for mechanism_id in MECHANISMS:
        result = _aggregate_evidence(
            prior[mechanism_id],
            evidence_rows,
            mechanism_id,
            decision_time,
            evidence_fields,
        )
        updated[mechanism_id] = result
    return updated


def _primitive_support_summary(support: dict[str, int]) -> dict[str, object]:
    if type(support) is not dict or set(support) != set(MECHANISMS) or any(type(value) is not int for value in support.values()):
        raise ValueError("PRIMITIVE_SUPPORT_INVALID")
    active = tuple(sorted(mechanism_id for mechanism_id, value in support.items() if value > 1))
    reason = "ALL_WEAK" if not active else "UNKNOWN_NO_VALID_COMPETITION_SET"
    return {
        "active_primitive_mechanism_ids": active if active else ("OTHER",),
        "top_path_hypothesis_id": "UNKNOWN",
        "margin": "UNKNOWN_UNCALIBRATED",
        "entropy": "UNKNOWN_UNCALIBRATED",
        "unknown_reason": reason,
    }


def _path_spec_primitives_valid(spec: dict[str, object], mechanism_library: tuple[str, ...]) -> bool:
    values = spec.get("primitive_mechanism_ids")
    return (
        type(values) is list
        and len(values) > 0
        and all(type(value) is str and value in mechanism_library for value in values)
        and len(values) == len(set(values))
    )


def _path_registry_by_id(path_registry: object) -> dict[str, dict[str, object]]:
    if type(path_registry) is not list:
        raise ValueError("PATH_REGISTRY_INVALID")
    indexed: dict[str, dict[str, object]] = {}
    for row in path_registry:
        if type(row) is not dict or set(row) != {"path_hypothesis_id", "primitive_mechanism_ids", "role"}:
            raise ValueError("PATH_REGISTRY_INVALID")
        path_id = row.get("path_hypothesis_id")
        if type(path_id) is not str or path_id == "" or path_id in indexed:
            raise ValueError("PATH_REGISTRY_INVALID")
        if not _path_spec_primitives_valid(row, MECHANISMS):
            raise ValueError("PATH_REGISTRY_INVALID")
        if row.get("role") not in {"MARKET_PATH", "RESIDUAL_PATH"}:
            raise ValueError("PATH_REGISTRY_INVALID")
        if "ARTIFACT" in row["primitive_mechanism_ids"]:
            raise ValueError("ARTIFACT_MIXTURE_PATH_FORBIDDEN")
        if row["role"] == "MARKET_PATH" and "OTHER" in row["primitive_mechanism_ids"]:
            raise ValueError("OTHER_MARKET_PATH_FORBIDDEN")
        if row["role"] == "RESIDUAL_PATH" and (
            path_id != "OTHER_PATH" or row["primitive_mechanism_ids"] != ["OTHER"]
        ):
            raise ValueError("RESIDUAL_PATH_NOT_EXACT_OTHER")
        indexed[path_id] = row
    return indexed


def _path_registry_digest(path_registry: object) -> str:
    _path_registry_by_id(path_registry)
    canonical = json.dumps(
        path_registry,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _partition_proof_digest(proof: object) -> str:
    if type(proof) is not dict or "partition_proof_digest" not in proof:
        raise ValueError("PARTITION_PROOF_DIGEST_INPUT_INVALID")
    canonical_body = {
        key: value
        for key, value in proof.items()
        if key != "partition_proof_digest"
    }
    canonical = json.dumps(
        canonical_body,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _partition_proof_authorities_by_id(
    authority_registry: object,
    authority_fields: tuple[str, ...],
    path_registry: object,
) -> dict[str, dict[str, object]]:
    indexed_paths = _path_registry_by_id(path_registry)
    path_registry_digest = _path_registry_digest(path_registry)
    if type(authority_registry) is not list or not authority_registry:
        raise ValueError("PARTITION_PROOF_AUTHORITY_REGISTRY_INVALID")
    indexed: dict[str, dict[str, object]] = {}
    for authority in authority_registry:
        if not _exact_keys(authority, authority_fields):
            raise ValueError("PARTITION_PROOF_AUTHORITY_SCHEMA_INVALID")
        proof_id = authority.get("partition_proof_id")
        proof_digest = authority.get("partition_proof_digest")
        path_ids = authority.get("path_hypothesis_ids")
        domain_values = authority.get("domain_values")
        residual = authority.get("residual_path_id")
        residual_domain_values = authority.get("residual_domain_values")
        if (
            type(proof_id) is not str
            or proof_id == ""
            or proof_id in indexed
            or type(proof_digest) is not str
            or len(proof_digest) != 64
            or any(character not in "0123456789abcdef" for character in proof_digest)
            or authority.get("path_registry_digest") != path_registry_digest
            or type(path_ids) is not list
            or len(path_ids) < 2
            or len(path_ids) != len(set(path_ids))
            or not all(type(path_id) is str and path_id in indexed_paths for path_id in path_ids)
            or not any(indexed_paths[path_id]["role"] == "MARKET_PATH" for path_id in path_ids)
            or type(domain_values) is not list
            or len(domain_values) < 2
            or len(domain_values) != len(set(domain_values))
            or not all(type(value) is str and value != "" for value in domain_values)
            or residual != "OTHER_PATH"
            or residual not in path_ids
            or indexed_paths[residual]["role"] != "RESIDUAL_PATH"
            or residual_domain_values != ["OTHER_OR_UNRESOLVED_TERMINAL"]
            or residual_domain_values[0] not in domain_values
        ):
            raise ValueError("PARTITION_PROOF_AUTHORITY_INVALID")
        for field in (
            "competition_set_id",
            "partition_version",
            "partition_domain_id",
            "calibration_version",
            "verification_scope",
        ):
            if type(authority.get(field)) is not str or authority[field] == "":
                raise ValueError("PARTITION_PROOF_AUTHORITY_IDENTITY_INVALID")
        if authority["verification_scope"] != (
            "SYNTHETIC_FINITE_DOMAIN_PARTITION_ONLY_NOT_REAL_MARKET_MATHEMATICAL_PROOF"
        ):
            raise ValueError("PARTITION_PROOF_AUTHORITY_SCOPE_INVALID")
        indexed[proof_id] = authority
    return indexed


def _registered_compound_path(spec: dict[str, object], path_registry: object) -> bool:
    try:
        indexed = _path_registry_by_id(path_registry)
    except ValueError:
        return False
    path_id = spec.get("path_id")
    if type(path_id) is not str or path_id not in indexed or not _path_spec_primitives_valid(spec, MECHANISMS):
        return False
    return sorted(spec["primitive_mechanism_ids"]) == sorted(indexed[path_id]["primitive_mechanism_ids"])


def _partition_proof_registry_by_id(
    proof_registry: object,
    path_registry: object,
    proof_fields: tuple[str, ...],
    cell_fields: tuple[str, ...],
    authority_registry: object,
    authority_fields: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    indexed_paths = _path_registry_by_id(path_registry)
    authorities = _partition_proof_authorities_by_id(
        authority_registry,
        authority_fields,
        path_registry,
    )
    if type(proof_registry) is not list:
        raise ValueError("PARTITION_PROOF_REGISTRY_INVALID")
    indexed_proofs: dict[str, dict[str, object]] = {}
    for proof in proof_registry:
        if not _exact_keys(proof, proof_fields):
            raise ValueError("PARTITION_PROOF_SCHEMA_INVALID")
        proof_id = proof.get("partition_proof_id")
        partition_version = proof.get("partition_version")
        domain_id = proof.get("partition_domain_id")
        calibration_version = proof.get("calibration_version")
        competition_set_id = proof.get("competition_set_id")
        path_registry_digest = proof.get("path_registry_digest")
        proof_digest = proof.get("partition_proof_digest")
        if (
            type(proof_id) is not str
            or proof_id == ""
            or proof_id in indexed_proofs
            or type(competition_set_id) is not str
            or competition_set_id == ""
            or type(partition_version) is not str
            or partition_version == ""
            or type(domain_id) is not str
            or domain_id == ""
            or type(calibration_version) is not str
            or calibration_version == ""
            or type(path_registry_digest) is not str
            or len(path_registry_digest) != 64
            or any(character not in "0123456789abcdef" for character in path_registry_digest)
            or type(proof_digest) is not str
            or len(proof_digest) != 64
            or any(character not in "0123456789abcdef" for character in proof_digest)
        ):
            raise ValueError("PARTITION_PROOF_IDENTITY_INVALID")
        if path_registry_digest != _path_registry_digest(path_registry):
            raise ValueError("PARTITION_PROOF_PATH_REGISTRY_DIGEST_INVALID")
        if proof_id not in authorities:
            raise ValueError("PARTITION_PROOF_NOT_AUTHORIZED")
        authority = authorities[proof_id]
        if proof.get("verification_scope") != "SYNTHETIC_FINITE_DOMAIN_PARTITION_ONLY_NOT_REAL_MARKET_MATHEMATICAL_PROOF":
            raise ValueError("PARTITION_PROOF_SCOPE_INVALID")
        path_ids = proof.get("path_hypothesis_ids")
        domain_values = proof.get("domain_values")
        cells = proof.get("partition_cells")
        residual = proof.get("residual_path_id")
        residual_domain_values = proof.get("residual_domain_values")
        if (
            type(path_ids) is not list
            or len(path_ids) == 0
            or len(path_ids) != len(set(path_ids))
            or not all(type(path_id) is str and path_id in indexed_paths for path_id in path_ids)
            or type(domain_values) is not list
            or len(domain_values) == 0
            or len(domain_values) != len(set(domain_values))
            or not all(type(item) is str and item != "" for item in domain_values)
            or type(cells) is not list
            or len(cells) != len(path_ids)
            or proof.get("mutually_exclusive") is not True
            or proof.get("exhaustive") is not True
            or type(residual) is not str
            or residual not in path_ids
            or indexed_paths[residual]["role"] != "RESIDUAL_PATH"
            or type(residual_domain_values) is not list
            or residual_domain_values != ["OTHER_OR_UNRESOLVED_TERMINAL"]
            or residual_domain_values[0] not in domain_values
        ):
            raise ValueError("PARTITION_PROOF_PARTITION_INVALID")
        seen_paths: set[str] = set()
        seen_domain: set[str] = set()
        cell_domain_by_path: dict[str, list[str]] = {}
        for expected_path_id, cell in zip(path_ids, cells):
            if not _exact_keys(cell, cell_fields):
                raise ValueError("PARTITION_CELL_SCHEMA_INVALID")
            cell_path = cell.get("path_hypothesis_id")
            cell_domain = cell.get("domain_values")
            if (
                type(cell_path) is not str
                or cell_path not in path_ids
                or cell_path != expected_path_id
                or cell_path in seen_paths
                or type(cell_domain) is not list
                or len(cell_domain) == 0
                or len(cell_domain) != len(set(cell_domain))
                or not all(type(item) is str and item in domain_values for item in cell_domain)
                or seen_domain.intersection(cell_domain)
            ):
                raise ValueError("PARTITION_CELL_INVALID")
            seen_paths.add(cell_path)
            seen_domain.update(cell_domain)
            cell_domain_by_path[cell_path] = cell_domain
        if seen_paths != set(path_ids) or seen_domain != set(domain_values):
            raise ValueError("PARTITION_PROOF_NOT_EXHAUSTIVE")
        if cell_domain_by_path[residual] != residual_domain_values:
            raise ValueError("PARTITION_PROOF_RESIDUAL_CELL_INVALID")
        if proof_digest != _partition_proof_digest(proof):
            raise ValueError("PARTITION_PROOF_CONTENT_DIGEST_INVALID")
        if any(proof.get(field) != authority[field] for field in authority_fields):
            raise ValueError("PARTITION_PROOF_AUTHORITY_MISMATCH")
        indexed_proofs[proof_id] = proof
    if set(indexed_proofs) != set(authorities):
        raise ValueError("PARTITION_PROOF_AUTHORITY_SET_MISMATCH")
    return indexed_proofs


def _competition_set_valid(
    value: object,
    path_registry: object,
    proof_registry: object,
    exact_fields: tuple[str, ...],
    proof_fields: tuple[str, ...],
    cell_fields: tuple[str, ...],
    authority_registry: object,
    authority_fields: tuple[str, ...],
) -> bool:
    try:
        indexed = _path_registry_by_id(path_registry)
        proofs = _partition_proof_registry_by_id(
            proof_registry,
            path_registry,
            proof_fields,
            cell_fields,
            authority_registry,
            authority_fields,
        )
    except ValueError:
        return False
    if not _exact_keys(value, exact_fields):
        return False
    path_ids = value.get("path_hypothesis_ids")
    residual = value.get("residual_path_id")
    proof_id = value.get("partition_proof_id")
    if type(proof_id) is not str or proof_id not in proofs:
        return False
    proof = proofs[proof_id]
    return (
        type(value.get("competition_set_id")) is str
        and value["competition_set_id"] != ""
        and value["competition_set_id"] == proof["competition_set_id"]
        and type(path_ids) is list
        and len(path_ids) > 0
        and all(type(path_id) is str and path_id in indexed for path_id in path_ids)
        and len(path_ids) == len(set(path_ids))
        and path_ids == proof["path_hypothesis_ids"]
        and value.get("partition_proof_digest") == proof["partition_proof_digest"]
        and value.get("partition_version") == proof["partition_version"]
        and value.get("exhaustive") is True
        and value["exhaustive"] is proof["exhaustive"]
        and type(residual) is str
        and residual in path_ids
        and indexed[residual]["role"] == "RESIDUAL_PATH"
        and residual == proof["residual_path_id"]
        and type(value.get("calibration_version")) is str
        and value["calibration_version"] != ""
        and value["calibration_version"] == proof["calibration_version"]
    )


def _path_hypothesis_weights_valid(
    weights: object,
    competition_set: object,
    path_registry: object,
    proof_registry: object,
    exact_fields: tuple[str, ...],
    proof_fields: tuple[str, ...],
    cell_fields: tuple[str, ...],
    authority_registry: object,
    authority_fields: tuple[str, ...],
) -> bool:
    if not _competition_set_valid(
        competition_set,
        path_registry,
        proof_registry,
        exact_fields,
        proof_fields,
        cell_fields,
        authority_registry,
        authority_fields,
    ):
        return False
    return _probability_vector_valid(weights, tuple(competition_set["path_hypothesis_ids"]))


def _calibrated_path_summary(
    weights: dict[str, object],
    competition_set: dict[str, object],
    path_registry: object,
    proof_registry: object,
    exact_fields: tuple[str, ...],
    proof_fields: tuple[str, ...],
    cell_fields: tuple[str, ...],
    authority_registry: object,
    authority_fields: tuple[str, ...],
) -> dict[str, object]:
    if not _path_hypothesis_weights_valid(
        weights,
        competition_set,
        path_registry,
        proof_registry,
        exact_fields,
        proof_fields,
        cell_fields,
        authority_registry,
        authority_fields,
    ):
        raise ValueError("PATH_WEIGHTS_INVALID")
    ordered = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    margin = ordered[0][1] - ordered[1][1] if len(ordered) > 1 else ordered[0][1]
    entropy = -sum(value * math.log(value) for value in weights.values() if value > 0.0)
    top = "UNKNOWN" if len(ordered) > 1 and ordered[0][1] == ordered[1][1] else ordered[0][0]
    return {"top_path_hypothesis_id": top, "margin": margin, "entropy": entropy, "unknown_reason": None}


def _evaluation_runs(trigger: object, rsi: object, registered_triggers: tuple[str, ...]) -> bool:
    if type(trigger) is not str or trigger not in registered_triggers:
        return False
    if rsi is None:
        return trigger in {
            "SCHEDULED",
            "STATE_CHANGE",
            "EVENT_ARRIVAL",
            "DATA_QUALITY_CHANGE",
            "POSITION_RISK",
        }
    return _finite_number(rsi)


def _intersect_zones(zones: object) -> tuple[float, float] | None:
    if type(zones) is not list or not zones:
        return None
    if any(type(zone) is not list or len(zone) != 2 or not all(_finite_number(value) for value in zone) or zone[0] > zone[1] for zone in zones):
        return None
    lower = max(zone[0] for zone in zones)
    upper = min(zone[1] for zone in zones)
    return (float(lower), float(upper)) if lower <= upper else None


def _conservative_utility(
    scenario_distribution: object,
    scenario_fields: tuple[str, ...],
    decision_time: object,
    utility_receipt_fields: tuple[str, ...],
    utility_by_scenario: dict[str, object],
    *,
    stress_cost: object,
    tail: object,
    uncertainty_penalty: object,
) -> dict[str, object]:
    if (
        not _scenario_distribution_valid(
            scenario_distribution,
            scenario_fields,
            decision_time,
        )
        or scenario_distribution["mode"] != "SYNTHETIC_COUNTERFACTUAL_ONLY"
    ):
        raise ValueError("SCENARIO_INVALID")
    if set(utility_by_scenario) != set(SCENARIOS) or not all(_finite_number(value) for value in utility_by_scenario.values()):
        raise ValueError("UTILITY_INVALID")
    deductions = (stress_cost, tail, uncertainty_penalty)
    if not all(_finite_number(value) and value >= 0 for value in deductions):
        raise ValueError("DEDUCTION_INVALID")
    values = scenario_distribution["values"]
    expected = sum(values[name] * utility_by_scenario[name] for name in SCENARIOS)
    receipt = {
        "utility_receipt_id": "UR-SYNTHETIC-COUNTERFACTUAL-001",
        "as_of": decision_time,
        "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
        "scenario_distribution_id": scenario_distribution["distribution_id"],
        "scenario_distribution_digest": _scenario_distribution_digest(
            scenario_distribution,
            scenario_fields,
            decision_time,
        ),
        "utility_by_scenario": copy.deepcopy(utility_by_scenario),
        "stress_cost": stress_cost,
        "tail": tail,
        "uncertainty_penalty": uncertainty_penalty,
        "conservative_utility": expected - stress_cost - tail - uncertainty_penalty,
        "authority_version": "V5-M00-E0-SYNTHETIC-COUNTERFACTUAL-NO-ACTION",
        "utility_receipt_digest": "",
    }
    if not _exact_keys(receipt, utility_receipt_fields):
        raise ValueError("UTILITY_RECEIPT_SCHEMA_INVALID")
    receipt["utility_receipt_digest"] = _utility_receipt_digest(receipt)
    return receipt


def _utility_receipt_digest(receipt: object) -> str:
    if type(receipt) is not dict or "utility_receipt_digest" not in receipt:
        raise ValueError("UTILITY_RECEIPT_DIGEST_INPUT_INVALID")
    canonical = json.dumps(
        {
            key: value
            for key, value in receipt.items()
            if key != "utility_receipt_digest"
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _utility_receipt_valid(
    receipt: object,
    utility_receipt_fields: tuple[str, ...],
    scenario_distribution: object,
    scenario_fields: tuple[str, ...],
    decision_time: object,
) -> bool:
    if (
        not _exact_keys(receipt, utility_receipt_fields)
        or receipt.get("mode") != "SYNTHETIC_COUNTERFACTUAL_ONLY"
        or receipt.get("authority_version")
        != "V5-M00-E0-SYNTHETIC-COUNTERFACTUAL-NO-ACTION"
    ):
        return False
    try:
        if _utc(receipt.get("as_of")) > _utc(decision_time):
            return False
        expected = _conservative_utility(
            scenario_distribution,
            scenario_fields,
            receipt["as_of"],
            utility_receipt_fields,
            receipt.get("utility_by_scenario"),
            stress_cost=receipt.get("stress_cost"),
            tail=receipt.get("tail"),
            uncertainty_penalty=receipt.get("uncertainty_penalty"),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return receipt == expected


def _path_conditioned_utility(
    path_weights: dict[str, object],
    competition_set: dict[str, object],
    path_registry: object,
    proof_registry: object,
    exact_fields: tuple[str, ...],
    proof_fields: tuple[str, ...],
    cell_fields: tuple[str, ...],
    authority_registry: object,
    authority_fields: tuple[str, ...],
    scenarios_by_path: dict[str, dict[str, object]],
    scenario_fields: tuple[str, ...],
    decision_time: object,
    utility_by_scenario: dict[str, object],
) -> float:
    if not _path_hypothesis_weights_valid(
        path_weights,
        competition_set,
        path_registry,
        proof_registry,
        exact_fields,
        proof_fields,
        cell_fields,
        authority_registry,
        authority_fields,
    ):
        raise ValueError("PATH_COMPETITION_INVALID")
    if set(scenarios_by_path) != set(path_weights):
        raise ValueError("PATH_SCENARIO_KEYS_INVALID")
    if set(utility_by_scenario) != set(SCENARIOS) or not all(_finite_number(value) for value in utility_by_scenario.values()):
        raise ValueError("UTILITY_INVALID")
    expected = 0.0
    for path_id, path_weight in path_weights.items():
        scenario = scenarios_by_path[path_id]
        if (
            not _scenario_distribution_valid(
                scenario,
                scenario_fields,
                decision_time,
            )
            or scenario["mode"] != "SYNTHETIC_COUNTERFACTUAL_ONLY"
        ):
            raise ValueError("SCENARIO_INVALID")
        expected += path_weight * sum(
            scenario["values"][name] * utility_by_scenario[name]
            for name in SCENARIOS
        )
    return expected


def _permission_envelope_digest(envelope: object) -> str:
    if type(envelope) is not dict:
        raise ValueError("PERMISSION_ENVELOPE_DIGEST_INPUT_INVALID")
    canonical = json.dumps(
        envelope,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _permission_envelope_valid(
    envelope: object,
    exact_fields: tuple[str, ...],
    decision_time: object,
) -> bool:
    if not _exact_keys(envelope, exact_fields):
        return False
    try:
        as_of = _utc(envelope.get("as_of"))
        decision_at = _utc(decision_time)
    except (TypeError, ValueError, OverflowError):
        return False
    vetoes = envelope.get("vetoes")
    return (
        as_of <= decision_at
        and type(envelope.get("envelope_id")) is str
        and envelope["envelope_id"] != ""
        and envelope.get("permission_state") in {"DENY", "UNKNOWN"}
        and envelope.get("allowed_actions") == ["ABSTAIN"]
        and _finite_number(envelope.get("max_risk"))
        and envelope["max_risk"] == 0
        and type(vetoes) is list
        and len(vetoes) > 0
        and len(vetoes) == len(set(vetoes))
        and all(type(veto) is str and veto != "" for veto in vetoes)
        and envelope.get("authority_version") == "V5-M00-E0-NO-NEW-RISK"
    )


def _research_geometry_candidate(
    *,
    zones: object,
    side: object,
    stop: object,
    target: object,
    entry_reference: object,
    horizon: object,
    risk_budget: object,
    worst_cost_per_unit: object,
    tail_per_unit: object,
    liquidity_cap: object,
    venue_cap: object,
    margin_cap: object,
) -> dict[str, object]:
    zone = _intersect_zones(zones)
    if zone is None:
        return {"valid": False, "reason": "EMPTY_ENTRY_ZONE"}
    numeric = (stop, target, entry_reference, horizon, risk_budget, worst_cost_per_unit, tail_per_unit, liquidity_cap, venue_cap, margin_cap)
    if not all(_finite_number(value) for value in numeric):
        return {"valid": False, "reason": "TYPE_OR_NUMBER"}
    if side == "LONG":
        geometry_valid = stop < zone[0] <= entry_reference <= zone[1] < target
    elif side == "SHORT":
        geometry_valid = target < zone[0] <= entry_reference <= zone[1] < stop
    else:
        geometry_valid = False
    if not geometry_valid or horizon <= 0:
        return {"valid": False, "reason": "GEOMETRY"}
    capacities = (risk_budget, liquidity_cap, venue_cap, margin_cap)
    if any(value <= 0 for value in capacities) or worst_cost_per_unit < 0 or tail_per_unit < 0:
        return {"valid": False, "reason": "RISK_INPUT"}
    denominator = abs(entry_reference - stop) + worst_cost_per_unit + tail_per_unit
    if denominator <= 0:
        return {"valid": False, "reason": "RISK_INPUT"}
    size = min(risk_budget / denominator, liquidity_cap, venue_cap, margin_cap)
    if size <= 0:
        return {"valid": False, "reason": "RISK_INPUT"}
    return {
        "valid": True,
        "reason": "RESEARCH_GEOMETRY_VALID_NOT_ACTION_PERMISSION",
        "entry_zone": zone,
        "size": size,
        "stop": stop,
        "target": target,
        "horizon": horizon,
    }


def _action_candidate(
    *,
    permission_envelope: object,
    permission_fields: tuple[str, ...],
    scenario_distribution: object,
    scenario_fields: tuple[str, ...],
    utility_receipt: object,
    utility_receipt_fields: tuple[str, ...],
    action_candidate_fields: tuple[str, ...],
    decision_time: object,
    zones: object,
    side: object,
    stop: object,
    target: object,
    entry_reference: object,
    horizon: object,
    risk_budget: object,
    worst_cost_per_unit: object,
    tail_per_unit: object,
    liquidity_cap: object,
    venue_cap: object,
    margin_cap: object,
) -> dict[str, object]:
    scenario_valid = _scenario_distribution_valid(
        scenario_distribution,
        scenario_fields,
        decision_time,
    )
    utility_valid = scenario_valid and _utility_receipt_valid(
        utility_receipt,
        utility_receipt_fields,
        scenario_distribution,
        scenario_fields,
        decision_time,
    )
    permission_valid = _permission_envelope_valid(
        permission_envelope,
        permission_fields,
        decision_time,
    )
    geometry = _research_geometry_candidate(
        zones=zones,
        side=side,
        stop=stop,
        target=target,
        entry_reference=entry_reference,
        horizon=horizon,
        risk_budget=risk_budget,
        worst_cost_per_unit=worst_cost_per_unit,
        tail_per_unit=tail_per_unit,
        liquidity_cap=liquidity_cap,
        venue_cap=venue_cap,
        margin_cap=margin_cap,
    )
    if not scenario_valid:
        reason = "SCENARIO_DISTRIBUTION_INVALID"
    elif not utility_valid:
        reason = "UTILITY_RECEIPT_INVALID"
    elif not permission_valid:
        reason = "PERMISSION_ENVELOPE_INVALID"
    else:
        reason = "V5_M00_NEW_RISK_FORBIDDEN"
    candidate = {
        "candidate_id": "AC-V5-M00-ABSTAIN-001",
        "as_of": decision_time,
        "action": "ABSTAIN",
        "side": side if type(side) is str and side in {"LONG", "SHORT"} else None,
        "entry_zone": list(geometry["entry_zone"]) if geometry.get("valid") else None,
        "stop": stop if geometry.get("valid") else None,
        "target": target if geometry.get("valid") else None,
        "horizon": horizon if geometry.get("valid") else None,
        "size": 0.0,
        "conservative_utility": (
            utility_receipt.get("conservative_utility")
            if utility_valid
            else None
        ),
        "reason_codes": [reason],
        "scenario_distribution_id": (
            scenario_distribution.get("distribution_id")
            if scenario_valid
            else None
        ),
        "scenario_distribution_digest": (
            _scenario_distribution_digest(
                scenario_distribution,
                scenario_fields,
                decision_time,
            )
            if scenario_valid
            else None
        ),
        "utility_receipt_id": (
            utility_receipt.get("utility_receipt_id") if utility_valid else None
        ),
        "utility_receipt_digest": (
            utility_receipt.get("utility_receipt_digest") if utility_valid else None
        ),
        "permission_envelope_id": (
            permission_envelope.get("envelope_id") if permission_valid else None
        ),
        "permission_envelope_digest": (
            _permission_envelope_digest(permission_envelope)
            if permission_valid
            else None
        ),
        "authority_version": "V5-M00-E0-NO-NEW-RISK",
    }
    if not _exact_keys(candidate, action_candidate_fields):
        raise ValueError("ACTION_CANDIDATE_SCHEMA_INVALID")
    return candidate


def _post_position_valid(
    *,
    action: object,
    side: object,
    prior_stop: object,
    updated_stop: object,
    prior_target: object,
    updated_target: object,
    prior_horizon: object,
    updated_horizon: object,
    prior_size: object,
    updated_size: object,
) -> bool:
    if action not in POST_POSITION_ACTIONS or side not in {"LONG", "SHORT"}:
        return False
    numeric = (prior_stop, updated_stop, prior_target, updated_target, prior_horizon, updated_horizon, prior_size, updated_size)
    if not all(_finite_number(value) for value in numeric):
        return False
    if updated_size > prior_size or min(prior_size, updated_size) < 0 or prior_horizon <= 0 or updated_horizon <= 0 or updated_horizon > prior_horizon:
        return False
    if side == "LONG":
        return updated_stop >= prior_stop and updated_target <= prior_target and updated_stop < updated_target
    return updated_stop <= prior_stop and updated_target >= prior_target and updated_target < updated_stop


def _pattern_instance_valid(instance: dict[str, object], required_fields: tuple[str, ...]) -> bool:
    if not _exact_keys(instance, required_fields):
        return False
    return (
        instance["pattern_instance_id"] == "CASE-USER-EXPERIENCE-SHOCK-COMPRESSION-001"
        and instance["origin"] == "USER_EXPERIENCE"
        and instance["instrument_id"] == "UNSPECIFIED"
        and instance["time_range"] == "UNSPECIFIED"
        and instance["truth_status"] == "ANECDOTAL_UNVERIFIED"
        and instance["outcome_visibility"] == "SEEN_NARRATIVE"
        and instance["not_for_holdout_selection"] is True
        and instance["opportunity_universe_role"] == "NONE_DIAGNOSTIC_ONLY"
        and instance["observation_count"] == len(instance["observed_sequence"])
        and type(instance["candidate_mechanism_ids"]) is list
        and len(instance["candidate_mechanism_ids"]) > 1
        and len(instance["candidate_mechanism_ids"])
        == len(set(instance["candidate_mechanism_ids"]))
        and all(type(item) is str and item in MECHANISMS for item in instance["candidate_mechanism_ids"])
    )


class GeneralizedCompetingPathContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core = CORE_PATH.read_text(encoding="utf-8")
        cls.core_raw = CORE_PATH.read_bytes()
        cls.immutable_core_raw = IMMUTABLE_CORE_PATH.read_bytes()
        cls.core_authority = _json(CORE_AUTHORITY_PATH)
        cls.theory = THEORY_PATH.read_text(encoding="utf-8")
        cls.method = _json(METHOD_PATH)
        cls.registry = _json(REGISTRY_PATH)
        cls.synthetic = _json(SYNTHETIC_PATH)

    def test_artifact_identity_stage_and_authority_are_e0_only(self) -> None:
        self.assertEqual(self.method["stage"], "V5-M00")
        self.assertEqual(self.registry["stage"], "V5-M00")
        self.assertEqual(self.synthetic["stage"], "V5-M00")
        self.assertEqual(self.synthetic["evidence_level"], "E0")
        self.assertEqual(self.method["status"], "E0_NO_NEW_OUTCOME_ACCESS_SYNTHETIC_ONLY")
        self.assertEqual(self.registry["status"], "E0_NO_NEW_OUTCOME_ACCESS_SYNTHETIC_ONLY")
        self.assertEqual(self.synthetic["status"], "PURE_SYNTHETIC_NO_NEW_OUTCOME_ACCESS")
        self.assertEqual(self.method["authority_boundary"]["next_gate"], "AWAITING_SOL_V5_M00_REGATE")
        self.assertEqual(self.registry["milestones"][0]["result_status"], "NOT_RUN")
        self.assertEqual(self.registry["milestones"][0]["test_execution_status"], "SYNTHETIC_TESTS_PASS_AWAITING_SOL_REGATE")
        forbidden = set(self.method["authority_boundary"]["forbidden"])
        self.assertTrue({"REAL_MARKET_DATA", "OUTCOME_ACCESS", "B4", "BACKTEST", "CALIBRATION", "HOLDOUT", "PAPER", "LIVE"}.issubset(forbidden))
        self.assertFalse(self.method["authority_boundary"]["general_theory_expands_v1_permission"])

    def test_versioned_core_authority_hash_size_pointers_and_root_mirror_are_exact(self) -> None:
        expected_fields = {"id", "version", "path", "raw_sha256", "size_bytes", "status", "root_mirror_path"}
        authority = self.core_authority
        self.assertEqual(set(authority), expected_fields)
        self.assertEqual(authority["id"], "CORE_TRADING_THEORY.v2.1")
        self.assertEqual(authority["version"], "2.1")
        self.assertEqual(authority["path"], "archive/authority/CORE_TRADING_THEORY_v2_1.md")
        self.assertEqual(authority["root_mirror_path"], "archive/authority/CORE_TRADING_THEORY_v2_1.md")
        self.assertEqual(authority["status"], "CURRENT_IMMUTABLE_AUTHORITY")
        self.assertEqual(self.core_raw, self.immutable_core_raw)
        self.assertEqual(len(self.immutable_core_raw), authority["size_bytes"])
        self.assertEqual(hashlib.sha256(self.immutable_core_raw).hexdigest(), authority["raw_sha256"])
        self.assertEqual(self.method["theory_authority"]["core_authority"], authority)
        self.assertEqual(self.registry["core_authority"], authority)
        self.assertIn(f"> 权威原始 SHA-256：`{authority['raw_sha256']}`", self.theory)
        self.assertIn(f"> 权威大小：`{authority['size_bytes']}` bytes", self.theory)

    def test_legacy_v0_2_authority_artifacts_remain_at_frozen_bytes(self) -> None:
        frozen = {
            "config/rsi_mtf_drl_pm.research_contract.v0_2.json": "33d84ce8fdfa7766fbce340beac9916344655c002e39ed6c8db29cefaaa6b047",
            "config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json": "631f8187e9eb81465718156736045c3ca5cc7ec5e33bbba7b063354cefeb792c",
            "config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json": "26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc",
            "archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md": "021053480fe9a49b3902803e2d363793416a120263551fb741fb3444af6550fd",
            "archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md": "43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6",
            "archive/authority/RSI_MTF_DRL_PM_AUTHORITY_BUNDLE_SPEC_v0_2_2.md": "9b2446de9e0549579d52bc8ce2bc3bd124885203a52855f0dbf0f1324f9f1295",
            "archive/authority/RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md": "4971a337605b7d3bbfdae3657a47498c2cfeb2d055f0e861339c57e02968aa48",
        }
        for relative_path, expected_sha256 in frozen.items():
            with self.subTest(relative_path=relative_path):
                raw = (PROJECT_ROOT / relative_path).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha256)

    def test_core_version_claims_hypotheses_and_separation_are_registered(self) -> None:
        self.assertIn("> 版本：2.1", self.core)
        self.assertIn("> 版本日期：2026-07-26", self.core)
        for claim in range(26, 37):
            self.assertIn(f"`T-{claim:03d}`", self.core)
        for hypothesis in range(15, 24):
            self.assertIn(f"`H-{hypothesis:03d}`", self.core)
        self.assertEqual(tuple(self.method["concept_separation"]["ordered_kinds"]), ("DATA_LAYER", "STATE_AXIS", "ANALYTICAL_PERSPECTIVE", "MECHANISM_HYPOTHESIS", "PATH", "ACTION"))
        for perspective in ("价格结构", "成交/订单流", "流动性", "衍生品/杠杆", "波动", "事件/宏观", "跨场", "数据质量"):
            self.assertIn(f"| {perspective} |", self.core)
            self.assertIn(f"| {perspective} |", self.theory)
        self.assertIn("下一可观测支持 / soft contradiction / hard falsifier / expiry", self.core)
        self.assertIn("下一支持/反证/hard falsifier/expiry", self.theory)

    def test_exact_object_schemas_match_across_all_three_json_contracts(self) -> None:
        method_fields = {name: schema["exact_fields"] for name, schema in self.method["object_schemas"].items()}
        self.assertEqual(method_fields, self.registry["object_required_fields"])
        self.assertEqual(method_fields, self.synthetic["object_required_fields"])
        for name, fields in method_fields.items():
            sample = {field: object() for field in fields}
            with self.subTest(name=name):
                self.assertTrue(_exact_keys(sample, tuple(fields)))
                self.assertFalse(_exact_keys(sample | {"unexpected": 1}, tuple(fields)))
                removed = dict(sample)
                removed.pop(fields[0])
                self.assertFalse(_exact_keys(removed, tuple(fields)))

    def test_finite_mechanism_library_signatures_other_and_runtime_injection(self) -> None:
        method_library = tuple(self.method["finite_mechanism_library"]["mechanism_ids"])
        registry_library = tuple(self.registry["common_rules"]["mechanism_ids"])
        synthetic_library = tuple(self.synthetic["mechanism_library"]["mechanism_ids"])
        self.assertEqual(method_library, MECHANISMS)
        self.assertEqual(method_library, registry_library)
        self.assertEqual(method_library, synthetic_library)
        signatures = self.synthetic["mechanism_library"]["mechanism_signatures"]
        self.assertEqual(set(signatures), set(MECHANISMS))
        signature_fields = {"antecedent", "next_support", "soft_contradiction", "hard_falsifier", "expiry_or_terminal", "forbidden_intent"}
        self.assertTrue(all(set(signature) == signature_fields for signature in signatures.values()))
        self.assertTrue(_registered_mechanism("OTHER", MECHANISMS))
        self.assertFalse(_registered_mechanism("LLM_NEW_STORY", MECHANISMS))
        self.assertFalse(_registered_mechanism(1, MECHANISMS))
        self.assertEqual(self.method["finite_mechanism_library"]["mechanism_semantics"], "NON_EXCLUSIVE_PRIMITIVE_MULTI_LABEL")
        self.assertEqual(self.method["finite_mechanism_library"]["primitive_support_normalization"], "FORBIDDEN")
        self.assertEqual(self.method["finite_mechanism_library"]["mechanism_roles"]["EPISTEMIC_DATA_QUALITY"], ["ARTIFACT"])
        self.assertEqual(self.method["finite_mechanism_library"]["artifact_direct_utility_weight"], "FORBIDDEN")

    def test_scenario_is_exact_mutually_exclusive_price_terminal_and_action_outcome_is_separate(self) -> None:
        self.assertEqual(tuple(self.method["scenario_contract"]["branches"]), SCENARIOS)
        self.assertEqual(tuple(self.registry["common_rules"]["scenario_branches"]), SCENARIOS)
        self.assertEqual(tuple(self.synthetic["scenario_contract"]["branches"]), SCENARIOS)
        self.assertEqual(tuple(self.method["scenario_contract"]["action_outcome_branches"]), ACTION_OUTCOMES)
        self.assertEqual(tuple(self.synthetic["scenario_contract"]["action_outcome_branches"]), ACTION_OUTCOMES)
        fields = tuple(self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        counterfactual = {
            "distribution_id": "SD-SYNTHETIC-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": 0.4, "DOWNSIDE": 0.3, "RANGE": 0.2, "UNRESOLVED": 0.1},
            "normalization_status": "NORMALIZED",
            "calibration_version": "SYNTHETIC-CAL-V1",
            "unknown_reason": None,
        }
        qualitative = {
            "distribution_id": "SD-E0-QUALITATIVE-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "QUALITATIVE_E0",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": "SUPPORTED", "DOWNSIDE": "WEAK", "RANGE": "WEAK", "UNRESOLVED": "LEADING"},
            "normalization_status": "NOT_APPLICABLE_UNCALIBRATED",
            "calibration_version": None,
            "unknown_reason": None,
        }
        unknown = {
            "distribution_id": "SD-UNKNOWN-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "UNKNOWN",
            "branches": list(SCENARIOS),
            "values": {},
            "normalization_status": "UNKNOWN",
            "calibration_version": None,
            "unknown_reason": "NO_VALID_INPUT",
        }
        self.assertTrue(_scenario_distribution_valid(counterfactual, fields, decision_time))
        self.assertTrue(_scenario_distribution_valid(qualitative, fields, decision_time))
        self.assertTrue(_scenario_distribution_valid(unknown, fields, decision_time))
        self.assertEqual(
            len(_scenario_distribution_digest(counterfactual, fields, decision_time)),
            64,
        )
        self.assertTrue(_action_outcome_valid({"NO_FILL": 0.2, "TP_FIRST": 0.3, "SL_FIRST": 0.2, "STRUCTURE_EXIT": 0.2, "TIMEOUT": 0.1}))

    def test_scenario_rejects_mechanism_action_outcome_pseudoprobability_and_non_normalization(self) -> None:
        fields = tuple(self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        base = {
            "distribution_id": "SD-SYNTHETIC-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": 0.4, "DOWNSIDE": 0.3, "RANGE": 0.2, "UNRESOLVED": 0.1},
            "normalization_status": "NORMALIZED",
            "calibration_version": "SYNTHETIC-CAL-V1",
            "unknown_reason": None,
        }
        mechanism_terminal = copy.deepcopy(base)
        mechanism_terminal["branches"] = [*SCENARIOS[:-1], "EVENT_REPRICING"]
        mechanism_terminal["values"] = {"UPSIDE": 0.4, "DOWNSIDE": 0.3, "RANGE": 0.2, "EVENT_REPRICING": 0.1}
        action_terminal = copy.deepcopy(base)
        action_terminal["branches"] = [*SCENARIOS[:-1], "TP_FIRST"]
        action_terminal["values"] = {"UPSIDE": 0.4, "DOWNSIDE": 0.3, "RANGE": 0.2, "TP_FIRST": 0.1}
        nonnormalized = copy.deepcopy(base)
        nonnormalized["values"]["UPSIDE"] = 0.7
        boolean_value = copy.deepcopy(base)
        boolean_value["values"]["UPSIDE"] = True
        uncalibrated_numeric = {
            "distribution_id": "SD-E0-INVALID-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "QUALITATIVE_E0",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": 0.4, "DOWNSIDE": "WEAK", "RANGE": "WEAK", "UNRESOLVED": "UNKNOWN"},
            "normalization_status": "NOT_APPLICABLE_UNCALIBRATED",
            "calibration_version": None,
            "unknown_reason": None,
        }
        raw_probability_map = copy.deepcopy(base["values"])
        pseudo_calibrated_bool = base | {"calibrated": True}
        future_as_of = base | {"as_of": "2099-01-01T00:00:00Z"}
        missing_as_of = dict(base)
        missing_as_of.pop("as_of")
        naive_as_of = base | {"as_of": "2026-01-01T00:00:00"}
        unauthorized_calibrated_mode = base | {
            "mode": "CALIBRATED_PROBABILITY",
            "calibration_version": "REAL-CAL-NOT-AUTHORIZED",
        }
        for mutation in (
            mechanism_terminal,
            action_terminal,
            nonnormalized,
            boolean_value,
            uncalibrated_numeric,
            raw_probability_map,
            pseudo_calibrated_bool,
            future_as_of,
            missing_as_of,
            naive_as_of,
            unauthorized_calibrated_mode,
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(
                    _scenario_distribution_valid(mutation, fields, decision_time)
                )

    def test_required_missing_unknown_and_optional_missing_never_zero(self) -> None:
        self.assertEqual(_required_input_disposition(["decision_time"]), "UNKNOWN")
        self.assertEqual(_required_input_disposition(None), "UNKNOWN")
        self.assertEqual(_required_input_disposition([]), "CONTINUE")
        self.assertEqual(_optional_missing("IGNORE_WITH_MISSING_FLAG"), "MISSING_FLAG")
        self.assertEqual(_optional_missing("BLOCK_TARGET"), "TARGET_BLOCKED")
        self.assertEqual(_optional_missing("UNKNOWN"), "UNKNOWN")
        self.assertNotEqual(_optional_missing("IGNORE_WITH_MISSING_FLAG"), 0)
        with self.assertRaisesRegex(ValueError, "OPTIONAL_RULE_UNREGISTERED"):
            _optional_missing("ZERO")

    def test_dependency_group_aggregation_counts_one_increment_and_is_order_invariant(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        rows = [
            _synthetic_evidence("b", ["P1"], direction="SUPPORT", ordinal_strength="MODERATE"),
            _synthetic_evidence("a", ["P1"], direction="SUPPORT", ordinal_strength="MODERATE", perspective_id="PERSPECTIVE-SYNTHETIC-E0-ALT"),
            _synthetic_evidence("c", ["P1"], direction="SOFT_CONTRADICTION", ordinal_strength="WEAK", available_at="2026-01-01T00:00:00.500000Z"),
        ]
        first = _aggregate_evidence(0, rows, "P1", decision_time, fields)
        second = _aggregate_evidence(0, list(reversed(rows)), "P1", decision_time, fields)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ACTIVE")
        self.assertEqual(first["support"], 1)
        self.assertEqual(
            set(first["accepted_evidence_ids"]),
            {rows[2]["evidence_id"], min(rows[0]["evidence_id"], rows[1]["evidence_id"])},
        )
        self.assertEqual(first["rejected_evidence"], ())
        duplicate_only = _aggregate_evidence(0, rows[:2], "P1", decision_time, fields)
        self.assertEqual(duplicate_only["support"], 2)
        self.assertEqual(len(duplicate_only["accepted_evidence_ids"]), 1)

    def test_target_scoped_duplicate_evidence_id_fails_closed_before_group_or_falsifier_effect(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        support = _synthetic_evidence(
            "E-SAME",
            ["P1"],
            direction="SUPPORT",
            ordinal_strength="STRONG",
        )
        cases = {
            "same-group-same-content": [support, copy.deepcopy(support)],
            "cross-group-same-content": [
                support,
                support | {"dependency_group": "g-cross"},
            ],
            "cross-group-conflicting-content": [
                support,
                support
                | {
                    "dependency_group": "g-conflict",
                    "direction": "SOFT_CONTRADICTION",
                    "ordinal_strength": "WEAK",
                },
            ],
            "support-plus-hard-falsifier": [
                support,
                support
                | {
                    "dependency_group": "g-hard",
                    "direction": "HARD_FALSIFIER",
                    "ordinal_strength": "STRONG",
                },
            ],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                first = _aggregate_evidence(4, rows, "P1", decision_time, fields)
                reordered = _aggregate_evidence(
                    4,
                    list(reversed(rows)),
                    "P1",
                    decision_time,
                    fields,
                )
                self.assertEqual(first, reordered)
                self.assertEqual(first["status"], "UNKNOWN")
                self.assertEqual(first["support"], 4)
                self.assertEqual(first["accepted_evidence_ids"], ())
                self.assertGreaterEqual(len(first["rejected_evidence"]), 1)
        same_group = _aggregate_evidence(
            4,
            cases["same-group-same-content"],
            "P1",
            decision_time,
            fields,
        )
        self.assertEqual(
            same_group["rejected_evidence"],
            (
                f'{support["evidence_id"]}:EVIDENCE_ID_DUPLICATE_IN_TARGET_BATCH',
            ),
        )

    def test_hard_falsifier_soft_contradiction_and_expiry_have_distinct_effects(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        hard = [_synthetic_evidence("hf", ["P"], direction="HARD_FALSIFIER", ordinal_strength="WEAK")]
        soft = [_synthetic_evidence("sc", ["P"], direction="SOFT_CONTRADICTION", ordinal_strength="MODERATE")]
        hard_result = _aggregate_evidence(3, hard, "P", decision_time, fields)
        soft_result = _aggregate_evidence(3, soft, "P", decision_time, fields)
        self.assertEqual(hard_result["status"], "FALSIFIED")
        self.assertEqual(hard_result["support"], 3)
        self.assertEqual(hard_result["accepted_evidence_ids"], (hard[0]["evidence_id"],))
        self.assertEqual(soft_result["status"], "ACTIVE")
        self.assertEqual(soft_result["support"], 1)
        self.assertEqual(soft_result["accepted_evidence_ids"], (soft[0]["evidence_id"],))
        self.assertEqual(_expiry_disposition(expired=True, current="ACTIVE"), "EXPIRED")
        self.assertEqual(_expiry_disposition(expired=False, current="ACTIVE"), "ACTIVE")
        self.assertEqual(_expiry_disposition(expired="true", current="ACTIVE"), "UNKNOWN")

    def test_hard_falsifier_is_irreversible_within_episode_but_new_episode_can_reinstantiate_mechanism(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        episode = {
            "episode_id": "EP-1",
            "observation_frame_id": "OF-1",
            "path_instance_id": "PI-1",
            "mechanism_id": "CONTINUATION",
            "status": "ACTIVE",
            "support": 0,
            "receipt_chain": [],
        }
        hard = [_synthetic_evidence("hf", ["PI-1"], direction="HARD_FALSIFIER", ordinal_strength="STRONG")]
        support_old = [_synthetic_evidence("s-old", ["PI-1"], direction="SUPPORT", ordinal_strength="STRONG")]
        supported = _update_episode(
            episode,
            [
                _synthetic_evidence(
                    "setup-support",
                    ["PI-1"],
                    direction="SUPPORT",
                    ordinal_strength="MODERATE",
                )
            ],
            decision_time,
            fields,
        )
        self.assertEqual(supported["support"], 2)
        falsified = _update_episode(
            supported,
            hard,
            decision_time,
            fields,
        )
        frozen_receipts = copy.deepcopy(falsified["receipt_chain"])
        self.assertEqual(falsified["status"], "FALSIFIED")
        rejected_after_terminal = _update_episode(
            falsified,
            support_old,
            decision_time,
            fields,
        )
        self.assertEqual(rejected_after_terminal["status"], "FALSIFIED")
        self.assertEqual(rejected_after_terminal["support"], falsified["support"])
        self.assertEqual(
            rejected_after_terminal["receipt_chain"][: len(frozen_receipts)],
            frozen_receipts,
        )
        self.assertEqual(
            len(rejected_after_terminal["receipt_chain"]),
            len(frozen_receipts) + 1,
        )
        self.assertIn(
            "TERMINAL_CUTOFF_NOT_STRICTLY_BEFORE",
            rejected_after_terminal["receipt_chain"][-1]["rejected_evidence"][0],
        )

        fresh = episode | {
            "episode_id": "EP-2",
            "observation_frame_id": "OF-2",
            "path_instance_id": "PI-2",
            "status": "ACTIVE",
            "support": 0,
            "receipt_chain": [],
        }
        self.assertTrue(_episode_reinstantiation_valid(falsified, fresh))
        for mutation in (
            {"episode_id": falsified["episode_id"]},
            {"observation_frame_id": falsified["observation_frame_id"]},
            {"path_instance_id": falsified["path_instance_id"]},
            {"mechanism_id": "RANGE"},
            {"status": "FALSIFIED"},
            {"support": 1},
            {"support": True},
            {"receipt_chain": copy.deepcopy(falsified["receipt_chain"])},
        ):
            with self.subTest(reinstantiation_mutation=mutation):
                self.assertFalse(
                    _episode_reinstantiation_valid(
                        falsified,
                        fresh | mutation,
                    )
                )
        missing_identity = dict(fresh)
        missing_identity.pop("episode_id")
        self.assertFalse(
            _episode_reinstantiation_valid(falsified, missing_identity)
        )
        support_new = [_synthetic_evidence("s-new", ["PI-2"], direction="SUPPORT", ordinal_strength="MODERATE")]
        reinstantiated = _update_episode(
            fresh,
            support_new,
            decision_time,
            fields,
            predecessor_episode=falsified,
        )
        self.assertEqual(reinstantiated["mechanism_id"], falsified["mechanism_id"])
        self.assertEqual(reinstantiated["status"], "ACTIVE")
        self.assertEqual(reinstantiated["support"], 2)
        self.assertNotEqual(reinstantiated["observation_frame_id"], falsified["observation_frame_id"])
        self.assertEqual(falsified["status"], "FALSIFIED")
        self.assertEqual(self.method["evidence_contract"]["hard_falsifier_scope"], "CURRENT_PATH_INSTANCE_AND_OPPORTUNITY_EPISODE_ONLY")

    def test_validate_before_filter_rejects_malformed_target_scope_without_partial_update(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        valid = _synthetic_evidence(
            "valid-target",
            ["P1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
        )
        malformed_targets: tuple[object, ...] = (
            "P1",
            ("P1",),
            ["P1", 1],
            ["P1", "P1"],
            [],
        )
        for malformed_target in malformed_targets:
            malformed = copy.deepcopy(valid)
            malformed["target_ids"] = malformed_target
            for rows in ([malformed, valid], [valid, malformed]):
                with self.subTest(
                    malformed_target=malformed_target,
                    order="malformed-first" if rows[0] is malformed else "valid-first",
                ):
                    result = _aggregate_evidence(
                        4,
                        rows,
                        "P1",
                        decision_time,
                        fields,
                    )
                    self.assertEqual(result["status"], "UNKNOWN")
                    self.assertEqual(result["support"], 4)
                    self.assertEqual(result["accepted_evidence_ids"], ())
                    self.assertEqual(result["admitted_identity_entries"], ())
                    self.assertTrue(
                        any(
                            reason.endswith(
                                "TARGET_IDS_INVALID_SCOPE_UNDETERMINED"
                            )
                            for reason in result["rejected_evidence"]
                        )
                    )

    def test_cross_receipt_replay_semantic_drift_and_underlying_alias_are_fail_closed_and_idempotent(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        base_episode = {
            "episode_id": "EP-LEDGER-1",
            "observation_frame_id": "OF-LEDGER-1",
            "path_instance_id": "PI-LEDGER-1",
            "mechanism_id": "CONTINUATION",
            "status": "ACTIVE",
            "support": 0,
            "receipt_chain": [],
        }
        support = _synthetic_evidence(
            "ledger-support",
            ["PI-LEDGER-1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
        )
        first = _update_episode(
            base_episode,
            [support],
            decision_time,
            fields,
        )
        self.assertEqual(first["support"], 2)
        self.assertEqual(first["status"], "ACTIVE")
        replay = _update_episode(first, [support], decision_time, fields)
        self.assertEqual(replay["support"], 2)
        self.assertEqual(replay["status"], "UNKNOWN")
        self.assertIn(
            "EVIDENCE_ID_REPLAY",
            replay["receipt_chain"][-1]["rejected_evidence"][0],
        )
        self.assertEqual(
            _update_episode(replay, [support], decision_time, fields),
            replay,
        )

        semantic_drift = copy.deepcopy(support)
        semantic_drift["direction"] = "HARD_FALSIFIER"
        drifted = _update_episode(
            first,
            [semantic_drift],
            decision_time,
            fields,
        )
        self.assertEqual(drifted["support"], 2)
        self.assertEqual(drifted["status"], "UNKNOWN")
        self.assertIn(
            "EVIDENCE_ID_AUTHORITY_MISMATCH",
            drifted["receipt_chain"][-1]["rejected_evidence"][0],
        )

        alias = _synthetic_evidence(
            "underlying-alias",
            ["PI-LEDGER-1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
            perspective_id="PERSPECTIVE-SYNTHETIC-E0-ALT",
        )
        self.assertNotEqual(alias["evidence_id"], support["evidence_id"])
        self.assertEqual(
            alias["dependency_group"],
            support["dependency_group"],
        )
        aliased = _update_episode(first, [alias], decision_time, fields)
        self.assertEqual(aliased["support"], 2)
        self.assertEqual(aliased["status"], "ACTIVE")
        self.assertEqual(
            aliased["receipt_chain"][-1]["rejected_evidence"],
            [],
        )
        self.assertEqual(
            (
                aliased_state := _reduce_evidence_receipt_chain(
                    aliased,
                    _load_method_authority_view(),
                )
            )["raw_support"],
            2,
        )
        self.assertEqual(len(aliased_state["group_winners"]), 1)
        self.assertEqual(len(aliased_state["evidence_identities"]), 2)

        other_group = _synthetic_evidence(
            "underlying-other-group-source",
            ["PI-LEDGER-1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
            available_at="2026-01-01T00:00:00.250000Z",
        )["dependency_group"]
        different_group_alias = copy.deepcopy(alias)
        different_group_alias["dependency_group"] = other_group
        authority = _evidence_lineage_authority(
            _load_method_authority_view()
        )
        different_group_alias["evidence_id"] = (
            authority["evidence_id_prefix"]
            + _canonical_digest(
                _canonical_evidence_projection(
                    different_group_alias,
                    authority["evidence_identity_fields"],
                )
            )
        )
        different_group_result = _update_episode(
            first,
            [different_group_alias],
            decision_time,
            fields,
        )
        self.assertEqual(different_group_result["support"], 2)
        self.assertEqual(different_group_result["status"], "UNKNOWN")
        self.assertIn(
            "DEPENDENCY_GROUP_AUTHORITY_MISMATCH",
            different_group_result["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        self.assertEqual(
            _reduce_evidence_receipt_chain(
                aliased,
                _load_method_authority_view(),
            )["raw_support"],
            2,
        )

        renamed = copy.deepcopy(support)
        renamed["evidence_id"] = "ATTACKER-RENAMED-ID"
        renamed["dependency_group"] = "ATTACKER-RENAMED-GROUP"
        renamed_result = _update_episode(
            first,
            [renamed],
            decision_time,
            fields,
        )
        self.assertEqual(renamed_result["support"], 2)
        self.assertEqual(renamed_result["status"], "UNKNOWN")
        self.assertTrue(
            any(
                "AUTHORITY_MISMATCH" in reason
                for reason in renamed_result["receipt_chain"][-1][
                    "rejected_evidence"
                ]
            )
        )

    def test_all_episode_terminal_states_are_monotonic_and_later_support_is_idempotently_rejected(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        for index, terminal_status in enumerate(
            ("FALSIFIED", "EXPIRED", "TERMINAL"),
            start=1,
        ):
            episode = {
                "episode_id": f"EP-TERMINAL-{index}",
                "observation_frame_id": f"OF-TERMINAL-{index}",
                "path_instance_id": f"PI-TERMINAL-{index}",
                "mechanism_id": "CONTINUATION",
                "status": "ACTIVE",
                "support": 0,
                "receipt_chain": [],
            }
            if terminal_status == "FALSIFIED":
                terminal = _update_episode(
                    episode,
                    [
                        _synthetic_evidence(
                            f"terminal-hard-{index}",
                            [episode["path_instance_id"]],
                            direction="HARD_FALSIFIER",
                            ordinal_strength="STRONG",
                        )
                    ],
                    decision_time,
                    fields,
                )
            else:
                terminal_reason = {
                    "EXPIRED": "EXPIRY",
                    "TERMINAL": "TERMINAL_MILESTONE",
                }[terminal_status]
                lifecycle_event = _synthetic_lifecycle_event(
                    episode,
                    terminal_status=terminal_status,
                    terminal_reason=terminal_reason,
                )
                terminal = _update_episode(
                    episode,
                    [],
                    decision_time,
                    fields,
                    lifecycle_events=[lifecycle_event],
                )
            self.assertEqual(terminal["status"], terminal_status)
            support = _synthetic_evidence(
                f"terminal-support-{index}",
                [episode["path_instance_id"]],
                direction="SUPPORT",
                ordinal_strength="STRONG",
            )
            first = _update_episode(
                terminal,
                [support],
                decision_time,
                fields,
            )
            self.assertEqual(first["status"], terminal_status)
            self.assertEqual(first["support"], 0)
            self.assertEqual(
                first["receipt_chain"][:-1],
                terminal["receipt_chain"],
            )
            self.assertIn(
                "TERMINAL_CUTOFF_NOT_STRICTLY_BEFORE",
                first["receipt_chain"][-1]["rejected_evidence"][0],
            )
            self.assertEqual(
                _update_episode(first, [support], decision_time, fields),
                first,
            )

    def test_receipt_chain_scope_order_hash_tamper_and_input_permutation_are_executable(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = {
            "episode_id": "EP-RECEIPT-1",
            "observation_frame_id": "OF-RECEIPT-1",
            "path_instance_id": "PI-RECEIPT-1",
            "mechanism_id": "CONTINUATION",
            "status": "ACTIVE",
            "support": 0,
            "receipt_chain": [],
        }
        first_row = _synthetic_evidence(
            "receipt-1",
            ["PI-RECEIPT-1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
        )
        second_row = _synthetic_evidence(
            "receipt-2",
            ["PI-RECEIPT-1"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
            available_at="2026-01-01T00:00:00.500000Z",
        )
        self.assertEqual(
            _evidence_batch_digest([first_row, second_row]),
            _evidence_batch_digest([second_row, first_row]),
        )
        first = _update_episode(
            episode,
            [first_row],
            decision_time,
            fields,
        )
        second = _update_episode(
            first,
            [second_row],
            decision_time,
            fields,
        )
        self.assertEqual(second["support"], 4)
        reduced = _reduce_evidence_receipt_chain(second, method)
        self.assertEqual(
            reduced["tip_hash"],
            second["receipt_chain"][-1]["receipt_hash"],
        )
        attacks: list[tuple[str, dict[str, object]]] = []
        reordered = copy.deepcopy(second)
        reordered["receipt_chain"] = list(reversed(reordered["receipt_chain"]))
        attacks.append(("reorder", reordered))
        deleted = copy.deepcopy(second)
        deleted["receipt_chain"] = deleted["receipt_chain"][1:]
        attacks.append(("delete-prefix", deleted))
        tampered = copy.deepcopy(second)
        tampered["receipt_chain"][0]["support_after"] = 9
        attacks.append(("content-without-rehash", tampered))
        forged_previous = copy.deepcopy(second)
        forged_previous["receipt_chain"][1]["previous_receipt_hash"] = "0" * 64
        forged_previous["receipt_chain"][1]["receipt_hash"] = _evidence_receipt_hash(
            forged_previous["receipt_chain"][1]
        )
        attacks.append(("forged-previous-with-rehash", forged_previous))
        wrong_scope = copy.deepcopy(second)
        wrong_scope["episode_id"] = "EP-RECEIPT-ALIASED"
        attacks.append(("scope-alias", wrong_scope))
        for label, attacked in attacks:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    _reduce_evidence_receipt_chain(attacked, method)

    def test_receipt_transition_is_rederived_from_typed_batch_not_trusted_self_consistency(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = _synthetic_episode("DERIVATION")
        row = _synthetic_evidence(
            "derivation-source",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
        )
        valid = _update_episode(
            episode,
            [row],
            decision_time,
            fields,
        )

        empty_effect_forgery = copy.deepcopy(valid)
        forged = empty_effect_forgery["receipt_chain"][0]
        forged["validated_effects"] = []
        forged["effects_digest"] = _effects_digest([])
        forged["accepted_evidence_ids"] = []
        forged["rejected_evidence"] = []
        forged["admitted_identity_entries"] = []
        forged["group_winners_after"] = []
        forged["raw_support_after"] = 9
        forged["support_after"] = 9
        forged["state_after_digest"] = _canonical_digest(
            {"attacker_claimed_support": 9}
        )
        forged["receipt_hash"] = _evidence_receipt_hash(forged)
        empty_effect_forgery["support"] = 9
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_RECEIPT_TRANSITION_NOT_DERIVABLE",
        ):
            _reduce_evidence_receipt_chain(
                empty_effect_forgery,
                method,
            )

        other_episode = _synthetic_episode("DERIVATION-OTHER")
        other_row = _synthetic_evidence(
            "derivation-other-source",
            [other_episode["path_instance_id"]],
            direction="SOFT_CONTRADICTION",
            ordinal_strength="STRONG",
            available_at="2026-01-01T00:00:00.250000Z",
        )
        other = _update_episode(
            other_episode,
            [other_row],
            decision_time,
            fields,
        )
        foreign_effect_forgery = copy.deepcopy(valid)
        forged = foreign_effect_forgery["receipt_chain"][0]
        forged["validated_effects"] = copy.deepcopy(
            other["receipt_chain"][0]["validated_effects"]
        )
        forged["effects_digest"] = _effects_digest(
            forged["validated_effects"]
        )
        forged["receipt_hash"] = _evidence_receipt_hash(forged)
        with self.assertRaises(ValueError):
            _reduce_evidence_receipt_chain(
                foreign_effect_forgery,
                method,
            )

        second_row = _synthetic_evidence(
            "derivation-second",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="WEAK",
            available_at="2026-01-01T00:00:00.500000Z",
        )
        two_receipts = _update_episode(
            valid,
            [second_row],
            decision_time,
            fields,
        )
        whole_chain_forgery = copy.deepcopy(two_receipts)
        prior_hash = "GENESIS"
        for index, receipt in enumerate(
            whole_chain_forgery["receipt_chain"],
            start=1,
        ):
            receipt["previous_receipt_hash"] = prior_hash
            receipt["expected_prefix_hash"] = prior_hash
            receipt["raw_support_before"] = 9
            receipt["raw_support_after"] = 9
            receipt["support_before"] = 9
            receipt["support_after"] = 9
            receipt["state_before_digest"] = _canonical_digest(
                {"attacker_receipt": index, "side": "before"}
            )
            receipt["state_after_digest"] = _canonical_digest(
                {"attacker_receipt": index, "side": "after"}
            )
            receipt["receipt_hash"] = _evidence_receipt_hash(receipt)
            prior_hash = receipt["receipt_hash"]
        whole_chain_forgery["support"] = 9
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_RECEIPT_TRANSITION_NOT_DERIVABLE",
        ):
            _reduce_evidence_receipt_chain(
                whole_chain_forgery,
                method,
            )

        substituted_method = copy.deepcopy(method)
        substituted_method["evidence_ledger_contract"][
            "lifecycle_source_version"
        ] = "ATTACKER-SOURCE"
        with self.assertRaisesRegex(
            ValueError,
            "METHOD_AUTHORITY_IN_MEMORY_SUBSTITUTION",
        ):
            _reduce_evidence_receipt_chain(
                valid,
                substituted_method,
            )

    def test_ledger_genesis_empty_noop_and_rejection_only_transition_are_fail_closed(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = _synthetic_episode("GENESIS")
        self.assertEqual(
            _reduce_evidence_receipt_chain(episode, method)["tip_hash"],
            "GENESIS",
        )
        self.assertEqual(
            _update_episode(
                episode,
                [],
                decision_time,
                fields,
            ),
            episode,
        )
        for invalid in (
            episode | {"support": 9},
            episode | {"status": "FALSIFIED"},
            episode | {"status": "EXPIRED"},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError,
                    "EVIDENCE_LEDGER_GENESIS_INVALID",
                ):
                    _reduce_evidence_receipt_chain(
                        invalid,
                        method,
                    )

        supported = _update_episode(
            episode,
            [
                _synthetic_evidence(
                    "genesis-support",
                    [episode["path_instance_id"]],
                    direction="SUPPORT",
                    ordinal_strength="MODERATE",
                )
            ],
            decision_time,
            fields,
        )
        aliased_target = _synthetic_evidence(
            "genesis-target-alias",
            [episode["path_instance_id"], "PI-UNRELATED"],
            direction="SUPPORT",
            ordinal_strength="STRONG",
            available_at="2026-01-01T00:00:00.250000Z",
        )
        rejected = _update_episode(
            supported,
            [aliased_target],
            decision_time,
            fields,
        )
        self.assertEqual(rejected["support"], supported["support"])
        self.assertEqual(rejected["status"], "UNKNOWN")
        self.assertIn(
            "TARGET_SCOPE_NOT_EXACT_LEDGER_TARGET",
            rejected["receipt_chain"][-1]["rejected_evidence"][0],
        )
        self.assertEqual(
            _update_episode(
                rejected,
                [aliased_target],
                decision_time,
                fields,
            ),
            rejected,
        )

    def test_dependency_group_winner_is_segmentation_invariant_and_raw_support_is_retained(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:10Z"
        episode = _synthetic_episode("SEGMENTATION")
        weak = _synthetic_evidence(
            "same-group-weak",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="WEAK",
        )
        strong = _synthetic_evidence(
            "same-group-strong",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="STRONG",
        )
        self.assertEqual(
            weak["dependency_group"],
            strong["dependency_group"],
        )

        one_batch = _update_episode(
            episode,
            [weak, strong],
            decision_time,
            fields,
        )
        weak_then_strong = _update_episode(
            _update_episode(
                episode,
                [weak],
                decision_time,
                fields,
            ),
            [strong],
            decision_time,
            fields,
        )
        strong_then_weak = _update_episode(
            _update_episode(
                episode,
                [strong],
                decision_time,
                fields,
            ),
            [weak],
            decision_time,
            fields,
        )
        final_states = [
            _reduce_evidence_receipt_chain(
                candidate,
                _load_method_authority_view(),
            )
            for candidate in (
                one_batch,
                weak_then_strong,
                strong_then_weak,
            )
        ]
        for final_state in final_states:
            self.assertEqual(final_state["raw_support"], 3)
            self.assertEqual(final_state["support"], 3)
            self.assertEqual(final_state["status"], "ACTIVE")
        self.assertEqual(
            len(
                {
                    final_state["state_digest"]
                    for final_state in final_states
                }
            ),
            1,
        )

        saturated_episode = _synthetic_episode("RAW-SATURATION")
        saturated = saturated_episode
        for index in range(4):
            saturated = _update_episode(
                saturated,
                [
                    _synthetic_evidence(
                        f"raw-strong-{index}",
                        [saturated_episode["path_instance_id"]],
                        direction="SUPPORT",
                        ordinal_strength="STRONG",
                        available_at=(
                            "2026-01-01T00:00:"
                            f"0{index}.000000Z"
                        ),
                    )
                ],
                decision_time,
                fields,
            )
        saturated_state = _reduce_evidence_receipt_chain(
            saturated,
            _load_method_authority_view(),
        )
        self.assertEqual(saturated_state["raw_support"], 12)
        self.assertEqual(saturated_state["support"], 9)
        weaker_same_group = _synthetic_evidence(
            "raw-weaker-same-group",
            [saturated_episode["path_instance_id"]],
            direction="SOFT_CONTRADICTION",
            ordinal_strength="WEAK",
            available_at="2026-01-01T00:00:00.000000Z",
        )
        after_weaker = _update_episode(
            saturated,
            [weaker_same_group],
            decision_time,
            fields,
        )
        after_weaker_state = _reduce_evidence_receipt_chain(
            after_weaker,
            _load_method_authority_view(),
        )
        self.assertEqual(after_weaker_state["raw_support"], 12)
        self.assertEqual(after_weaker_state["support"], 9)

        tie_episode = _synthetic_episode("LEXICAL-TIE")
        positive = _synthetic_evidence(
            "tie-positive",
            [tie_episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="STRONG",
        )
        negative = _synthetic_evidence(
            "tie-negative",
            [tie_episode["path_instance_id"]],
            direction="SOFT_CONTRADICTION",
            ordinal_strength="STRONG",
        )
        expected_tie_winner = min(
            (positive, negative),
            key=lambda row: row["evidence_id"],
        )
        tie_candidates = (
            _update_episode(
                tie_episode,
                [positive, negative],
                decision_time,
                fields,
            ),
            _update_episode(
                _update_episode(
                    tie_episode,
                    [positive],
                    decision_time,
                    fields,
                ),
                [negative],
                decision_time,
                fields,
            ),
            _update_episode(
                _update_episode(
                    tie_episode,
                    [negative],
                    decision_time,
                    fields,
                ),
                [positive],
                decision_time,
                fields,
            ),
        )
        tie_states = [
            _reduce_evidence_receipt_chain(
                candidate,
                _load_method_authority_view(),
            )
            for candidate in tie_candidates
        ]
        self.assertEqual(
            {
                next(iter(state["group_winners"].values()))["evidence_id"]
                for state in tie_states
            },
            {expected_tie_winner["evidence_id"]},
        )
        self.assertEqual(
            len({state["state_digest"] for state in tie_states}),
            1,
        )

    def test_external_expected_tip_is_required_to_detect_valid_prefix_or_chain_replacement(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = _synthetic_episode("PREFIX")
        first = _update_episode(
            episode,
            [
                _synthetic_evidence(
                    "prefix-first",
                    [episode["path_instance_id"]],
                    direction="SUPPORT",
                    ordinal_strength="MODERATE",
                )
            ],
            decision_time,
            fields,
        )
        full = _update_episode(
            first,
            [
                _synthetic_evidence(
                    "prefix-second",
                    [episode["path_instance_id"]],
                    direction="SUPPORT",
                    ordinal_strength="WEAK",
                    available_at="2026-01-01T00:00:00.500000Z",
                )
            ],
            decision_time,
            fields,
        )
        full_tip = full["receipt_chain"][-1]["receipt_hash"]
        self.assertEqual(
            _reduce_evidence_receipt_chain(first, method)["support"],
            2,
        )
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_EXPECTED_TIP_MISMATCH",
        ):
            _reduce_evidence_receipt_chain(
                first,
                method,
                expected_tip_hash=full_tip,
            )
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_EXPECTED_TIP_MISMATCH",
        ):
            _update_episode(
                first,
                [],
                decision_time,
                fields,
                expected_tip_hash=full_tip,
            )

        replacement = _update_episode(
            episode,
            [
                _synthetic_evidence(
                    "replacement-valid-prefix",
                    [episode["path_instance_id"]],
                    direction="SOFT_CONTRADICTION",
                    ordinal_strength="WEAK",
                    available_at="2026-01-01T00:00:00.250000Z",
                )
            ],
            decision_time,
            fields,
        )
        self.assertEqual(
            _reduce_evidence_receipt_chain(
                replacement,
                method,
            )["support"],
            -1,
        )
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_EXPECTED_TIP_MISMATCH",
        ):
            _reduce_evidence_receipt_chain(
                replacement,
                method,
                expected_tip_hash=full_tip,
            )

    def test_lifecycle_terminal_requires_complete_path_authority_and_earliest_terminal_wins(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = _synthetic_episode("LIFECYCLE-AUTHORITY")
        expiry = _synthetic_lifecycle_event(
            episode,
            terminal_status="EXPIRED",
            terminal_reason="EXPIRY",
        )
        valid_expiry = _update_episode(
            episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        self.assertEqual(valid_expiry["status"], "EXPIRED")
        self.assertEqual(
            valid_expiry["receipt_chain"][-1]["validated_effects"][0][
                "terminal_event_at"
            ],
            expiry["path_events"][-1]["event_at"],
        )

        forged_expiry = copy.deepcopy(expiry)
        forged_expiry["path_events"][-1]["event_at"] = (
            "2025-12-31T23:59:59Z"
        )
        forged_expiry["path_events"][-1]["available_at"] = (
            "2025-12-31T23:59:59Z"
        )
        forged_expiry["terminal_event_at"] = (
            "2025-12-31T23:59:59Z"
        )
        forged_expiry["lifecycle_event_id"] = _lifecycle_event_id(
            forged_expiry
        )
        forged_expiry["lifecycle_event_digest"] = (
            _lifecycle_event_digest(forged_expiry)
        )
        forged_result = _update_episode(
            episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[forged_expiry],
        )
        self.assertEqual(forged_result["status"], "UNKNOWN")
        self.assertEqual(forged_result["support"], 0)
        self.assertIn(
            "EXPIRY_TIMESTAMP_MISMATCH",
            forged_result["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        self_signed_old_shape = {
            "lifecycle_event_id": "ATTACKER-SELF-SIGNED",
            "target_id": episode["path_instance_id"],
            "scope_digest": _episode_scope_digest(episode),
            "terminal_reason": "EXPIRY",
            "terminal_status": "EXPIRED",
            "available_at": "2026-01-01T00:00:00Z",
            "path_id": "PATH-GENERIC-COMPETING-001",
            "path_spec_digest": method["path_contract"][
                "path_spec_authority_registry"
            ][0]["path_spec_digest"],
            "source_version": method["evidence_ledger_contract"][
                "lifecycle_source_version"
            ],
            "lifecycle_event_digest": "ATTACKER",
        }
        old_shape_result = _update_episode(
            episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[self_signed_old_shape],
        )
        self.assertEqual(old_shape_result["status"], "UNKNOWN")
        self.assertIn(
            "LIFECYCLE_EVENT_SCHEMA_INVALID",
            old_shape_result["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        earlier_hard = _synthetic_evidence(
            "earlier-hard",
            [episode["path_instance_id"]],
            direction="HARD_FALSIFIER",
            ordinal_strength="STRONG",
            available_at="2025-12-31T23:59:59.500000Z",
        )
        expiry_then_hard = _update_episode(
            valid_expiry,
            [earlier_hard],
            decision_time,
            fields,
        )
        hard_then_expiry = _update_episode(
            _update_episode(
                episode,
                [earlier_hard],
                decision_time,
                fields,
            ),
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        expiry_then_hard_state = _reduce_evidence_receipt_chain(
            expiry_then_hard,
            method,
        )
        hard_then_expiry_state = _reduce_evidence_receipt_chain(
            hard_then_expiry,
            method,
        )
        self.assertEqual(expiry_then_hard_state["status"], "FALSIFIED")
        self.assertEqual(hard_then_expiry_state["status"], "FALSIFIED")
        self.assertEqual(
            expiry_then_hard_state["terminal_winner"],
            hard_then_expiry_state["terminal_winner"],
        )
        self.assertEqual(
            expiry_then_hard_state["state_digest"],
            hard_then_expiry_state["state_digest"],
        )

        simultaneous_terminal = _synthetic_lifecycle_event(
            episode,
            terminal_status="TERMINAL",
            terminal_reason="TERMINAL_MILESTONE",
            path_started_at="2025-12-31T23:59:58Z",
            requested_horizon_seconds=2,
        )
        self.assertEqual(
            simultaneous_terminal["terminal_event_at"],
            expiry["terminal_event_at"],
        )
        tie_expiry_first = _update_episode(
            _update_episode(
                episode,
                [],
                decision_time,
                fields,
                lifecycle_events=[expiry],
            ),
            [],
            decision_time,
            fields,
            lifecycle_events=[simultaneous_terminal],
        )
        tie_terminal_first = _update_episode(
            _update_episode(
                episode,
                [],
                decision_time,
                fields,
                lifecycle_events=[simultaneous_terminal],
            ),
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        tie_states = [
            _reduce_evidence_receipt_chain(candidate, method)
            for candidate in (tie_expiry_first, tie_terminal_first)
        ]
        self.assertEqual(
            {
                state["terminal_winner"]["reason_code"]
                for state in tie_states
            },
            {"EXPIRY"},
        )
        self.assertEqual(
            len({state["state_digest"] for state in tie_states}),
            1,
        )

    def test_terminal_cutoff_compensation_mechanism_scope_and_semantic_tie_priority_are_order_invariant(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        episode = _synthetic_episode("TERMINAL-COMPENSATION")
        expiry = _synthetic_lifecycle_event(
            episode,
            terminal_status="EXPIRED",
            terminal_reason="EXPIRY",
        )
        support = _synthetic_evidence(
            "intervening-support",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="WEAK",
            available_at="2025-12-31T23:59:59.750000Z",
        )
        earlier_hard = _synthetic_evidence(
            "cutoff-earlier-hard",
            [episode["path_instance_id"]],
            direction="HARD_FALSIFIER",
            ordinal_strength="STRONG",
            available_at="2025-12-31T23:59:59.500000Z",
        )
        support_then_expiry = _update_episode(
            _update_episode(
                episode,
                [support],
                decision_time,
                fields,
            ),
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        historical_prefix = copy.deepcopy(
            support_then_expiry["receipt_chain"]
        )
        support_expiry_hard = _update_episode(
            support_then_expiry,
            [earlier_hard],
            decision_time,
            fields,
        )
        hard_support_expiry = _update_episode(
            _update_episode(
                _update_episode(
                    episode,
                    [earlier_hard],
                    decision_time,
                    fields,
                ),
                [support],
                decision_time,
                fields,
            ),
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        self.assertEqual(
            support_expiry_hard["receipt_chain"][
                : len(historical_prefix)
            ],
            historical_prefix,
        )
        compensated_states = [
            _reduce_evidence_receipt_chain(candidate, method)
            for candidate in (
                support_expiry_hard,
                hard_support_expiry,
            )
        ]
        for state in compensated_states:
            self.assertEqual(state["status"], "FALSIFIED")
            self.assertEqual(state["raw_support"], 0)
            self.assertEqual(state["support"], 0)
            self.assertEqual(state["group_candidates"], {})
            self.assertEqual(state["group_winners"], {})
        self.assertEqual(
            compensated_states[0]["terminal_winner"],
            compensated_states[1]["terminal_winner"],
        )
        self.assertEqual(
            compensated_states[0]["state_digest"],
            compensated_states[1]["state_digest"],
        )

        range_episode = _synthetic_episode("RANGE-MECHANISM-SCOPE")
        range_episode["mechanism_id"] = "RANGE"
        cross_mechanism_expiry = _synthetic_lifecycle_event(
            range_episode,
            terminal_status="EXPIRED",
            terminal_reason="EXPIRY",
        )
        cross_mechanism_result = _update_episode(
            range_episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[cross_mechanism_expiry],
        )
        self.assertEqual(cross_mechanism_result["status"], "UNKNOWN")
        self.assertEqual(cross_mechanism_result["support"], 0)
        self.assertIn(
            "LIFECYCLE_PATH_EVENT_SCOPE_OR_SOURCE_INVALID",
            cross_mechanism_result["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        simultaneous_terminal = _synthetic_lifecycle_event(
            episode,
            terminal_status="TERMINAL",
            terminal_reason="TERMINAL_MILESTONE",
            path_started_at="2025-12-31T23:59:58Z",
            requested_horizon_seconds=2,
        )
        ground_terminal = None
        for index in range(1, 1025):
            candidate = copy.deepcopy(simultaneous_terminal)
            candidate["path_events"][0]["path_event_id"] = (
                f"GRIND-{index:04d}"
            )
            candidate["lifecycle_event_id"] = _lifecycle_event_id(
                candidate
            )
            candidate["lifecycle_event_digest"] = (
                _lifecycle_event_digest(candidate)
            )
            if (
                candidate["lifecycle_event_digest"]
                < expiry["lifecycle_event_digest"]
            ):
                ground_terminal = candidate
                break
        self.assertIsNotNone(ground_terminal)
        self.assertLess(
            ground_terminal["lifecycle_event_digest"],
            expiry["lifecycle_event_digest"],
        )
        priority_orders = (
            (expiry, ground_terminal),
            (ground_terminal, expiry),
        )
        priority_states = []
        for first_event, second_event in priority_orders:
            candidate = _update_episode(
                _update_episode(
                    episode,
                    [],
                    decision_time,
                    fields,
                    lifecycle_events=[first_event],
                ),
                [],
                decision_time,
                fields,
                lifecycle_events=[second_event],
            )
            priority_states.append(
                _reduce_evidence_receipt_chain(candidate, method)
            )
        for state in priority_states:
            self.assertEqual(state["status"], "EXPIRED")
            self.assertEqual(
                state["terminal_winner"][
                    "terminal_reason_priority"
                ],
                method["evidence_ledger_contract"][
                    "terminal_reason_priority"
                ]["EXPIRY"],
            )
        self.assertEqual(
            priority_states[0]["terminal_winner"],
            priority_states[1]["terminal_winner"],
        )
        self.assertEqual(
            priority_states[0]["state_digest"],
            priority_states[1]["state_digest"],
        )

        self.assertIn(
            "synthetic structural derivability only",
            method["evidence_ledger_contract"][
                "terminal_derivation_rule"
            ],
        )
        self.assertEqual(
            method["evidence_ledger_contract"][
                "terminal_reason_priority"
            ],
            {
                "HARD_FALSIFIER": 0,
                "EXPIRY": 1,
                "TERMINAL_MILESTONE": 2,
            },
        )
        self.assertIn(
            "frozen semantic-priority rank",
            method["evidence_ledger_contract"][
                "terminal_monotonicity"
            ],
        )
        self.assertIn(
            "frozen terminal reason priority",
            method["evidence_ledger_contract"][
                "terminal_winner_rule"
            ],
        )
        self.assertIn(
            "no independent path-instance event-log tip",
            method["evidence_ledger_contract"][
                "lifecycle_fact_authority_boundary"
            ],
        )

    def test_receipt_decision_time_is_canonical_utc_and_chain_is_nondecreasing_at_entry_and_replay(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        episode = _synthetic_episode("DECISION-CLOCK")
        rows = [
            _synthetic_evidence(
                "clock-a",
                [episode["path_instance_id"]],
                direction="SUPPORT",
                ordinal_strength="WEAK",
                available_at="2026-01-01T00:00:00Z",
            ),
            _synthetic_evidence(
                "clock-b",
                [episode["path_instance_id"]],
                direction="SOFT_CONTRADICTION",
                ordinal_strength="WEAK",
                available_at="2026-01-01T00:00:00.250000Z",
            ),
            _synthetic_evidence(
                "clock-c",
                [episode["path_instance_id"]],
                direction="SUPPORT",
                ordinal_strength="MODERATE",
                available_at="2026-01-01T00:00:00.500000Z",
                perspective_id="PERSPECTIVE-SYNTHETIC-E0-ALT",
            ),
        ]
        first = _update_episode(
            episode,
            [rows[0]],
            "2026-01-01T08:00:01+08:00",
            fields,
        )
        equal = _update_episode(
            first,
            [rows[1]],
            "2026-01-01T00:00:01Z",
            fields,
        )
        increasing = _update_episode(
            equal,
            [rows[2]],
            "2026-01-01T00:00:02Z",
            fields,
        )
        self.assertEqual(
            [
                receipt["decision_time"]
                for receipt in increasing["receipt_chain"]
            ],
            [
                "2026-01-01T00:00:01Z",
                "2026-01-01T00:00:01Z",
                "2026-01-01T00:00:02Z",
            ],
        )
        with self.assertRaisesRegex(
            ValueError,
            "EVIDENCE_DECISION_TIME_REGRESSION",
        ):
            _update_episode(
                increasing,
                [
                    _synthetic_evidence(
                        "clock-regression",
                        [episode["path_instance_id"]],
                        direction="SUPPORT",
                        ordinal_strength="STRONG",
                        available_at=(
                            "2026-01-01T00:00:00.600000Z"
                        ),
                    )
                ],
                "2026-01-01T00:00:00.750000Z",
                fields,
            )

        noncanonical = copy.deepcopy(first)
        noncanonical["receipt_chain"][0]["decision_time"] = (
            "2026-01-01T08:00:01+08:00"
        )
        noncanonical["receipt_chain"][0]["receipt_hash"] = (
            _evidence_receipt_hash(
                noncanonical["receipt_chain"][0]
            )
        )
        with self.assertRaisesRegex(
            ValueError,
            "DECISION_TIME_NOT_CANONICAL_UTC",
        ):
            _reduce_evidence_receipt_chain(noncanonical)

        regressed_chain = copy.deepcopy(increasing)
        regressed = regressed_chain["receipt_chain"][-1]
        regressed["decision_time"] = (
            "2026-01-01T00:00:00.750000Z"
        )
        regressed["idempotency_key"] = (
            _transition_idempotency_key(
                scope_digest=regressed["scope_digest"],
                transition_kind=regressed["transition_kind"],
                batch_digest=regressed["batch_digest"],
                decision_time=regressed["decision_time"],
                rejection_class=regressed["rejection_class"],
            )
        )
        regressed["receipt_hash"] = _evidence_receipt_hash(
            regressed
        )
        with self.assertRaisesRegex(
            ValueError,
            "DECISION_TIME_REGRESSION",
        ):
            _reduce_evidence_receipt_chain(regressed_chain)

    def test_retryable_causal_rejections_rederive_later_for_evidence_and_lifecycle_but_permanent_rejections_do_not(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        evidence_episode = _synthetic_episode("RETRY-EVIDENCE")
        future = _synthetic_evidence(
            "future-retry",
            [evidence_episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="STRONG",
            available_at="2026-01-01T00:00:02Z",
        )
        early = _update_episode(
            evidence_episode,
            [future],
            "2026-01-01T00:00:01Z",
            fields,
        )
        self.assertEqual(early["status"], "UNKNOWN")
        self.assertEqual(
            early["receipt_chain"][-1]["rejection_class"],
            "RETRYABLE_AT_LATER_DECISION_TIME",
        )
        self.assertIn(
            "RETRYABLE_AT_LATER_DECISION_TIME",
            early["receipt_chain"][-1]["rejected_evidence"][0],
        )
        self.assertEqual(
            _update_episode(
                early,
                [future],
                "2026-01-01T08:00:01+08:00",
                fields,
            ),
            early,
        )
        visible = _update_episode(
            early,
            [future],
            "2026-01-01T00:00:03Z",
            fields,
        )
        self.assertEqual(visible["status"], "ACTIVE")
        self.assertEqual(visible["support"], 3)
        self.assertEqual(
            visible["receipt_chain"][-1]["rejection_class"],
            "NONE",
        )
        self.assertNotEqual(
            visible["receipt_chain"][-1]["idempotency_key"],
            early["receipt_chain"][-1]["idempotency_key"],
        )

        permanently_invalid = copy.deepcopy(
            _synthetic_evidence(
                "permanent-schema",
                [evidence_episode["path_instance_id"]],
                direction="SUPPORT",
                ordinal_strength="WEAK",
                available_at="2026-01-01T00:00:03Z",
            )
        )
        permanently_invalid.pop("quality")
        permanent = _update_episode(
            visible,
            [permanently_invalid],
            "2026-01-01T00:00:04Z",
            fields,
        )
        self.assertEqual(
            permanent["receipt_chain"][-1]["rejection_class"],
            "PERMANENT",
        )
        self.assertEqual(
            _update_episode(
                permanent,
                [permanently_invalid],
                "2026-01-01T00:00:05Z",
                fields,
            ),
            permanent,
        )

        lifecycle_episode = _synthetic_episode(
            "RETRY-LIFECYCLE"
        )
        expiry = _synthetic_lifecycle_event(
            lifecycle_episode,
            terminal_status="EXPIRED",
            terminal_reason="EXPIRY",
        )
        lifecycle_early = _update_episode(
            lifecycle_episode,
            [],
            "2025-12-31T23:59:59Z",
            fields,
            lifecycle_events=[expiry],
        )
        self.assertEqual(lifecycle_early["status"], "UNKNOWN")
        self.assertEqual(
            lifecycle_early["receipt_chain"][-1][
                "rejection_class"
            ],
            "RETRYABLE_AT_LATER_DECISION_TIME",
        )
        self.assertEqual(
            _update_episode(
                lifecycle_early,
                [],
                "2025-12-31T23:59:59Z",
                fields,
                lifecycle_events=[expiry],
            ),
            lifecycle_early,
        )
        lifecycle_visible = _update_episode(
            lifecycle_early,
            [],
            "2026-01-01T00:00:01Z",
            fields,
            lifecycle_events=[expiry],
        )
        self.assertEqual(lifecycle_visible["status"], "EXPIRED")
        self.assertEqual(
            lifecycle_visible["receipt_chain"][-1][
                "rejection_class"
            ],
            "NONE",
        )

    def test_lifecycle_identity_idempotency_content_drift_and_semantic_terminal_merge_are_executable(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        episode = _synthetic_episode("LIFECYCLE-IDENTITY")
        expiry = _synthetic_lifecycle_event(
            episode,
            terminal_status="EXPIRED",
            terminal_reason="EXPIRY",
        )
        accepted = _update_episode(
            episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[expiry],
        )
        accepted_state = _reduce_evidence_receipt_chain(accepted)
        self.assertEqual(
            set(accepted_state["lifecycle_identities"]),
            {expiry["lifecycle_event_id"]},
        )
        self.assertEqual(
            _update_episode(
                accepted,
                [],
                "2026-01-01T08:00:01+08:00",
                fields,
                lifecycle_events=[expiry],
            ),
            accepted,
        )

        drift = copy.deepcopy(expiry)
        drift["path_events"][0]["path_event_id"] = (
            "PATH-EVENT-DRIFT"
        )
        drift["lifecycle_event_digest"] = (
            _lifecycle_event_digest(drift)
        )
        drifted = _update_episode(
            accepted,
            [],
            "2026-01-01T00:00:02Z",
            fields,
            lifecycle_events=[drift],
        )
        self.assertEqual(drifted["status"], "EXPIRED")
        self.assertIn(
            "LIFECYCLE_EVENT_ID_CONTENT_DRIFT",
            drifted["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        earlier_hard = _synthetic_lifecycle_event(
            episode,
            terminal_status="FALSIFIED",
            terminal_reason="HARD_FALSIFIER",
        )
        corrected = _update_episode(
            drifted,
            [],
            "2026-01-01T00:00:02Z",
            fields,
            lifecycle_events=[earlier_hard],
        )
        corrected_state = _reduce_evidence_receipt_chain(
            corrected
        )
        self.assertEqual(corrected_state["status"], "FALSIFIED")
        self.assertEqual(
            set(corrected_state["lifecycle_identities"]),
            {
                expiry["lifecycle_event_id"],
                earlier_hard["lifecycle_event_id"],
            },
        )

        semantic_episode = _synthetic_episode(
            "SEMANTIC-MERGE"
        )
        terminal_a = _synthetic_lifecycle_event(
            semantic_episode,
            terminal_status="TERMINAL",
            terminal_reason="TERMINAL_MILESTONE",
        )
        terminal_b = copy.deepcopy(terminal_a)
        terminal_b["path_events"][0]["path_event_id"] = (
            "PATH-EVENT-ALTERNATE-PROVENANCE"
        )
        terminal_b["lifecycle_event_id"] = _lifecycle_event_id(
            terminal_b
        )
        terminal_b["lifecycle_event_digest"] = (
            _lifecycle_event_digest(terminal_b)
        )
        first = _update_episode(
            semantic_episode,
            [],
            decision_time,
            fields,
            lifecycle_events=[terminal_a],
        )
        first_state = _reduce_evidence_receipt_chain(first)
        merged = _update_episode(
            first,
            [],
            "2026-01-01T00:00:02Z",
            fields,
            lifecycle_events=[terminal_b],
        )
        merged_state = _reduce_evidence_receipt_chain(merged)
        self.assertNotEqual(
            terminal_a["lifecycle_event_digest"],
            terminal_b["lifecycle_event_digest"],
        )
        self.assertEqual(
            first_state["terminal_winner"],
            merged_state["terminal_winner"],
        )
        self.assertEqual(
            first_state["state_digest"],
            merged_state["state_digest"],
        )
        self.assertEqual(
            len(merged_state["lifecycle_identities"]),
            2,
        )
        self.assertEqual(
            _update_episode(
                merged,
                [],
                "2026-01-01T00:00:02Z",
                fields,
                lifecycle_events=[terminal_b],
            ),
            merged,
        )

    def test_event_time_b_late_ordinary_and_mixed_hard_batches_converge_for_all_receipt_orders(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        episode = _synthetic_episode("EVENT-TIME-B")
        target = [episode["path_instance_id"]]
        before_support = _synthetic_evidence(
            "before-support",
            target,
            direction="SUPPORT",
            ordinal_strength="WEAK",
            available_at="2025-12-31T23:59:59.200000Z",
        )
        before_soft = _synthetic_evidence(
            "before-soft",
            target,
            direction="SOFT_CONTRADICTION",
            ordinal_strength="MODERATE",
            available_at="2025-12-31T23:59:59.300000Z",
        )
        equal_support = _synthetic_evidence(
            "equal-support",
            target,
            direction="SUPPORT",
            ordinal_strength="STRONG",
            available_at="2025-12-31T23:59:59.500000Z",
        )
        after_soft = _synthetic_evidence(
            "after-soft",
            target,
            direction="SOFT_CONTRADICTION",
            ordinal_strength="STRONG",
            available_at="2025-12-31T23:59:59.700000Z",
        )
        hard = _synthetic_evidence(
            "cutoff-hard",
            target,
            direction="HARD_FALSIFIER",
            ordinal_strength="STRONG",
            available_at="2025-12-31T23:59:59.500000Z",
        )
        rows = (
            before_support,
            before_soft,
            equal_support,
            after_soft,
            hard,
        )
        one_batch = _update_episode(
            episode,
            list(rows),
            decision_time,
            fields,
        )
        expected = _reduce_evidence_receipt_chain(one_batch)
        self.assertEqual(expected["status"], "FALSIFIED")
        self.assertEqual(expected["raw_support"], -1)
        self.assertEqual(expected["support"], -1)
        self.assertEqual(len(expected["group_candidates"]), 2)
        self.assertEqual(
            len(one_batch["receipt_chain"][-1][
                "rejected_evidence"
            ]),
            2,
        )

        for order in itertools.permutations(rows):
            candidate = episode
            for row in order:
                candidate = _update_episode(
                    candidate,
                    [row],
                    decision_time,
                    fields,
                )
            state = _reduce_evidence_receipt_chain(candidate)
            self.assertEqual(state["status"], "FALSIFIED")
            self.assertEqual(state["raw_support"], -1)
            self.assertEqual(
                state["terminal_winner"],
                expected["terminal_winner"],
            )
            self.assertEqual(
                state["state_digest"],
                expected["state_digest"],
            )

        hard_first = _update_episode(
            episode,
            [hard],
            decision_time,
            fields,
        )
        late_before = _update_episode(
            hard_first,
            [before_support],
            decision_time,
            fields,
        )
        late_receipt = late_before["receipt_chain"][-1]
        self.assertEqual(late_receipt["status_before"], "FALSIFIED")
        self.assertEqual(late_receipt["status_after"], "FALSIFIED")
        self.assertEqual(late_receipt["support_before"], 0)
        self.assertEqual(late_receipt["support_after"], 1)

    def test_lifecycle_capacity_overflow_is_resource_unknown_at_ledger_level_never_terminal(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        episode = _synthetic_episode("LIFECYCLE-OVERFLOW")
        overflow = _synthetic_lifecycle_event(
            episode,
            terminal_status="TERMINAL",
            terminal_reason="TERMINAL_MILESTONE",
            requested_horizon_seconds=1000,
        )
        started_at = overflow["path_started_at"]
        terminal_at = (
            _utc(started_at) + timedelta(seconds=257)
        ).isoformat().replace("+00:00", "Z")
        overflow["path_events"] = _synthetic_path_events(
            ["ANCHOR", *(["TEST"] * 255), "TERMINAL"],
            path_started_at=started_at,
            path_instance_id=episode["path_instance_id"],
            terminal_reason="TERMINAL_MILESTONE",
            terminal_event_at=terminal_at,
        )
        overflow["terminal_event_at"] = terminal_at
        overflow["lifecycle_event_id"] = _lifecycle_event_id(
            overflow
        )
        overflow["lifecycle_event_digest"] = (
            _lifecycle_event_digest(overflow)
        )
        result = _update_episode(
            episode,
            [],
            "2026-01-01T00:05:00Z",
            fields,
            lifecycle_events=[overflow],
        )
        state = _reduce_evidence_receipt_chain(result)
        receipt = result["receipt_chain"][-1]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(state["terminal_winner"])
        self.assertEqual(
            receipt["rejection_class"],
            "RESOURCE_CAPACITY_REQUIRED",
        )
        self.assertIn(
            "UNKNOWN_RESOURCE:"
            "COMPACT_REQUIRED_RECEIPT_CONTINUATION",
            receipt["rejected_evidence"][0],
        )
        self.assertTrue(
            all(
                effect["effect_kind"] == "REJECTION"
                for effect in receipt["validated_effects"]
            )
        )
        self.assertEqual(
            _update_episode(
                result,
                [],
                "2026-01-01T00:06:00Z",
                fields,
                lifecycle_events=[overflow],
            ),
            result,
        )

    def test_exact_target_typed_carrier_and_equivalent_utc_identity_are_not_alias_bypasses(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        method = _load_method_authority_view()
        authority = _evidence_lineage_authority(method)
        episode = _synthetic_episode("TYPED-TIME")
        utc_row = _synthetic_evidence(
            "utc-z",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
            available_at="2026-01-01T00:00:00Z",
        )
        offset_row = _synthetic_evidence(
            "utc-offset",
            [episode["path_instance_id"]],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
            available_at="2026-01-01T08:00:00+08:00",
        )
        utc_identity = _authority_bound_evidence_row(
            utc_row,
            authority,
        )[1]
        offset_identity = _authority_bound_evidence_row(
            offset_row,
            authority,
        )[1]
        self.assertEqual(utc_identity, offset_identity)
        first = _update_episode(
            episode,
            [utc_row],
            decision_time,
            fields,
        )
        equivalent_replay = _update_episode(
            first,
            [offset_row],
            decision_time,
            fields,
        )
        self.assertEqual(equivalent_replay["support"], 2)
        self.assertEqual(equivalent_replay["status"], "UNKNOWN")
        self.assertIn(
            "EVIDENCE_ID_REPLAY",
            equivalent_replay["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

        tuple_target = copy.deepcopy(utc_row)
        tuple_target["target_ids"] = (
            episode["path_instance_id"],
        )
        tuple_target, _identity = _authority_bound_evidence_row(
            tuple_target,
            authority,
        )
        list_member = _canonical_batch_member(
            "EVIDENCE",
            utc_row,
        )
        tuple_member = _canonical_batch_member(
            "EVIDENCE",
            tuple_target,
        )
        self.assertNotEqual(
            list_member["typed_payload"],
            tuple_member["typed_payload"],
        )
        self.assertNotEqual(
            list_member["member_digest"],
            tuple_member["member_digest"],
        )
        tuple_result = _update_episode(
            episode,
            [tuple_target],
            decision_time,
            fields,
        )
        self.assertEqual(tuple_result["status"], "UNKNOWN")
        self.assertEqual(tuple_result["support"], 0)
        self.assertIn(
            "TARGET_IDS_INVALID_SCOPE_UNDETERMINED",
            tuple_result["receipt_chain"][-1][
                "rejected_evidence"
            ][0],
        )

    def test_method_authority_is_reloaded_per_call_and_exact_evidence_carrier_remains_unchanged(self) -> None:
        first = _load_method_authority_view()
        first["path_contract"]["path_spec_authority_registry"][0][
            "path_spec_digest"
        ] = "0" * 64
        second = _load_method_authority_view()
        self.assertNotEqual(
            second["path_contract"]["path_spec_authority_registry"][0][
                "path_spec_digest"
            ],
            "0" * 64,
        )
        self.assertEqual(
            hashlib.sha256(METHOD_PATH.read_bytes()).hexdigest(),
            METHOD_AUTHORITY_RAW_SHA256,
        )
        evidence_fields = second["evidence_contract"]["exact_fields"]
        self.assertNotIn("underlying_increment_id", evidence_fields)
        self.assertNotIn("raw_record_id", evidence_fields)
        self.assertIn(
            "lacks raw source record identity",
            second["evidence_contract"]["source_lineage_authority"][
                "exact_carrier_limitation"
            ],
        )

    def test_future_missing_and_malformed_evidence_is_rejected_unknown_without_support_update(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        valid = _synthetic_evidence(
            "valid",
            ["P"],
            direction="SUPPORT",
            ordinal_strength="MODERATE",
        )
        valid_result = _aggregate_evidence(0, [valid], "P", decision_time, fields)
        self.assertEqual(valid_result["status"], "ACTIVE")
        self.assertEqual(valid_result["support"], 2)

        future = _synthetic_evidence(
            "future",
            ["P"],
            direction="SUPPORT",
            ordinal_strength="STRONG",
            available_at="2099-01-01T00:00:00Z",
        )
        missing_available_at = dict(valid | {"evidence_id": "missing"})
        missing_available_at.pop("available_at")
        naive_available_at = valid | {
            "evidence_id": "naive",
            "available_at": "2026-01-01T00:00:00",
        }
        malformed_available_at = valid | {
            "evidence_id": "malformed",
            "available_at": "NOT_A_TIMESTAMP",
        }
        invalid_source_version = valid | {
            "evidence_id": "source-invalid",
            "source_version": "",
        }
        invalid_quality = valid | {
            "evidence_id": "gap",
            "quality": "GAP",
        }
        for label, row, reason in (
            ("future", future, "AVAILABLE_AT_FUTURE"),
            ("missing", missing_available_at, "SCHEMA_INVALID"),
            ("naive", naive_available_at, "AVAILABLE_AT_INVALID"),
            ("malformed", malformed_available_at, "AVAILABLE_AT_INVALID"),
            ("source-version", invalid_source_version, "FIELD_ENUM_OR_AUTHORITY_INVALID"),
            ("quality", invalid_quality, "QUALITY_GAP"),
        ):
            with self.subTest(label=label):
                result = _aggregate_evidence(4, [row], "P", decision_time, fields)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["support"], 4)
                self.assertEqual(result["accepted_evidence_ids"], ())
                self.assertEqual(len(result["rejected_evidence"]), 1)
                self.assertIn(reason, result["rejected_evidence"][0])

    def test_variable_path_accepts_2_8_20_and_more_without_fixed_day_semantics(self) -> None:
        spec = self.synthetic["sample_path_specs"][0]
        path_event_fields = tuple(
            self.method["object_schemas"]["PathEvent"]["exact_fields"]
        )
        path_spec_fields = tuple(
            self.method["object_schemas"]["PathSpec"]["exact_fields"]
        )
        path_started_at = "2026-01-01T00:00:00Z"
        decision_time = "2026-01-02T00:00:01Z"
        sequences = {
            2: ["ANCHOR", "TERMINAL"],
            8: ["ANCHOR", *["PRESSURE"] * 3, *["RESPONSE"] * 3, "TERMINAL"],
            20: ["ANCHOR", *["PRESSURE"] * 9, *["RESPONSE"] * 9, "TERMINAL"],
            21: ["ANCHOR", *["PRESSURE"] * 10, *["RESPONSE"] * 9, "TERMINAL"],
        }
        for count, sequence in sequences.items():
            with self.subTest(count=count):
                self.assertEqual(len(sequence), count)
                events = _synthetic_path_events(
                    sequence,
                    path_started_at=path_started_at,
                )
                self.assertEqual(
                    _path_valid(
                        events,
                        spec,
                        decision_time=decision_time,
                        path_started_at=path_started_at,
                        requested_horizon_seconds=spec["frozen_horizon_seconds"],
                        path_spec_fields=path_spec_fields,
                        path_event_fields=path_event_fields,
                    ),
                    (True, "VALID"),
                )
        self.assertIn("EVENT_TIME", spec["horizon_rule"])
        self.assertIn("RESOURCE_ONLY", spec["runtime_capacity_guard"]["semantic_boundary"])

    def test_path_skip_repeat_partial_order_and_capacity_guard_are_executable(self) -> None:
        spec = self.synthetic["sample_path_specs"][0]
        fields = tuple(self.method["object_schemas"]["PathEvent"]["exact_fields"])
        spec_fields = tuple(
            self.method["object_schemas"]["PathSpec"]["exact_fields"]
        )
        path_started_at = "2026-01-01T00:00:00Z"
        kwargs = {
            "decision_time": "2026-01-02T00:00:01Z",
            "path_started_at": path_started_at,
            "requested_horizon_seconds": spec["frozen_horizon_seconds"],
            "path_spec_fields": spec_fields,
            "path_event_fields": fields,
        }

        def validate(sequence: list[str]) -> tuple[bool, str]:
            return _path_valid(
                _synthetic_path_events(
                    sequence,
                    path_started_at=path_started_at,
                ),
                spec,
                **kwargs,
            )

        self.assertEqual(validate(["ANCHOR", "RESPONSE", "TERMINAL"]), (True, "VALID"))
        self.assertEqual(validate(["ANCHOR", "PRESSURE", "PRESSURE", "TERMINAL"]), (True, "VALID"))
        self.assertEqual(validate(["ANCHOR", "RESPONSE", "PRESSURE", "TERMINAL"])[1], "PARTIAL_ORDER_VIOLATION")
        self.assertEqual(validate(["ANCHOR", "ANCHOR", "TERMINAL"])[1], "REPEAT_NOT_DECLARED")
        self.assertEqual(validate(["ANCHOR", "UNREGISTERED", "TERMINAL"])[1], "MILESTONE_UNREGISTERED")
        over_capacity = _synthetic_path_events(
            ["ANCHOR", *["PRESSURE"] * 255, "TERMINAL"],
            path_started_at=path_started_at,
        )
        semantically_valid, resource_disposition = _path_valid(
            over_capacity,
            spec,
            **kwargs,
        )
        self.assertTrue(semantically_valid)
        self.assertEqual(resource_disposition, "COMPACT_REQUIRED_RECEIPT_CONTINUATION")
        self.assertNotIn(resource_disposition, {"FALSIFIED", "EXPIRED", "TERMINAL"})
        self.assertEqual(spec["runtime_capacity_guard"]["overflow_disposition"], "COMPACT_OR_CONTINUE_RECEIPT_ELSE_UNKNOWN_RESOURCE")
        self.assertFalse(self.synthetic["path_contract"]["capacity_overflow_is_path_semantics"])

    def test_path_event_time_clock_stopping_expiry_and_horizon_are_fail_closed(self) -> None:
        spec = self.synthetic["sample_path_specs"][0]
        fields = tuple(self.method["object_schemas"]["PathEvent"]["exact_fields"])
        spec_fields = tuple(
            self.method["object_schemas"]["PathSpec"]["exact_fields"]
        )
        path_started_at = "2026-01-01T00:00:00Z"
        decision_time = "2026-01-02T00:00:01Z"
        horizon = spec["frozen_horizon_seconds"]
        base = _synthetic_path_events(
            ["ANCHOR", "PRESSURE", "TERMINAL"],
            path_started_at=path_started_at,
        )

        def validate(
            events: object,
            *,
            candidate_spec: object = spec,
            candidate_horizon: object = horizon,
        ) -> tuple[bool, str]:
            return _path_valid(
                events,
                candidate_spec,
                decision_time=decision_time,
                path_started_at=path_started_at,
                requested_horizon_seconds=candidate_horizon,
                path_spec_fields=spec_fields,
                path_event_fields=fields,
            )

        self.assertEqual(validate(base), (True, "VALID"))
        no_stop = copy.deepcopy(base)
        no_stop[-1]["terminal_reason"] = None
        self.assertEqual(validate(no_stop)[1], "STOPPING_RULE_VIOLATION")
        self.assertEqual(
            validate(
                base,
                candidate_spec=spec | {"event_time_stopping_rule": "NEVER_STOP"},
            )[1],
            "PATH_SPEC_AUTHORITY_DIGEST_MISMATCH",
        )
        self.assertEqual(
            validate(
                base,
                candidate_spec=spec | {"horizon_rule": "FIXED_8_DAY"},
            )[1],
            "PATH_SPEC_AUTHORITY_DIGEST_MISMATCH",
        )
        self.assertEqual(
            validate(
                base,
                candidate_spec=spec | {"fixed_day_count": 8},
            )[1],
            "PATH_SPEC_SCHEMA_INVALID",
        )
        self.assertEqual(
            validate(base, candidate_horizon=horizon + 1)[1],
            "HORIZON_EXTENSION_OR_TYPE_INVALID",
        )

        future = copy.deepcopy(base)
        future[1]["available_at"] = "2099-01-01T00:00:00Z"
        self.assertEqual(validate(future)[1], "EVENT_NOT_CAUSALLY_AVAILABLE")
        naive = copy.deepcopy(base)
        naive[1]["event_at"] = "2026-01-01T00:00:02"
        self.assertEqual(validate(naive)[1], "PATH_EVENT_TIME_INVALID")
        missing = copy.deepcopy(base)
        missing[1].pop("available_at")
        self.assertEqual(validate(missing)[1], "PATH_EVENT_SCHEMA_INVALID")

        early_terminal = copy.deepcopy(base)
        early_terminal[1]["terminal_reason"] = "TERMINAL_MILESTONE"
        self.assertEqual(validate(early_terminal)[1], "EVENT_AFTER_TERMINAL")

        hard_stop = _synthetic_path_events(
            ["ANCHOR", "TERMINAL"],
            path_started_at=path_started_at,
            terminal_reason="HARD_FALSIFIER",
            terminal_trigger_id="PREDECLARED_INVALIDATION",
        )
        self.assertEqual(validate(hard_stop), (True, "VALID"))
        invalid_hard = copy.deepcopy(hard_stop)
        invalid_hard[-1]["terminal_trigger_id"] = "RUNTIME_HARD_FALSIFIER"
        self.assertEqual(
            validate(invalid_hard)[1],
            "HARD_FALSIFIER_TRIGGER_INVALID",
        )
        after_hard = copy.deepcopy(hard_stop)
        after_hard.append(
            {
                "path_event_id": "PATH-EVENT-003",
                "path_instance_id": "PI-SYNTHETIC-001",
                "milestone": "RESPONSE",
                "event_at": "2026-01-01T00:00:03Z",
                "available_at": "2026-01-01T00:00:03Z",
                "terminal_reason": None,
                "terminal_trigger_id": None,
                "source_version": "SYNTHETIC-PATH-EVENT-V1",
            }
        )
        self.assertEqual(validate(after_hard)[1], "EVENT_AFTER_TERMINAL")

        exact_expiry = "2026-01-02T00:00:00Z"
        expiry_stop = _synthetic_path_events(
            ["ANCHOR", "TERMINAL"],
            path_started_at=path_started_at,
            terminal_reason="EXPIRY",
            terminal_event_at=exact_expiry,
        )
        self.assertEqual(validate(expiry_stop), (True, "VALID"))
        premature_expiry = copy.deepcopy(expiry_stop)
        premature_expiry[-1]["event_at"] = "2026-01-01T23:59:59Z"
        premature_expiry[-1]["available_at"] = "2026-01-01T23:59:59Z"
        self.assertEqual(
            validate(premature_expiry)[1],
            "EXPIRY_TIMESTAMP_MISMATCH",
        )
        after_expiry = copy.deepcopy(expiry_stop)
        after_expiry[-1]["event_at"] = "2026-01-02T00:00:01Z"
        after_expiry[-1]["available_at"] = "2026-01-02T00:00:01Z"
        self.assertEqual(validate(after_expiry)[1], "EVENT_AFTER_EXPIRY")

    def test_path_spec_authority_binds_complete_canonical_spec_before_event_validation(self) -> None:
        spec = self.synthetic["sample_path_specs"][0]
        spec_fields = tuple(
            self.method["object_schemas"]["PathSpec"]["exact_fields"]
        )
        event_fields = tuple(
            self.method["object_schemas"]["PathEvent"]["exact_fields"]
        )
        authority = self.method["path_contract"]["path_spec_authority_registry"]
        reloaded_method = _load_method_authority_view()
        self.assertEqual(
            reloaded_method["path_contract"]["path_spec_authority_registry"],
            authority,
        )
        self.assertEqual(
            _path_spec_authorities_by_id(
                authority,
                tuple(self.method["path_contract"]["path_spec_authority_exact_fields"]),
            )[spec["path_id"]]["path_spec_digest"],
            _path_spec_digest(spec, spec_fields),
        )
        events = _synthetic_path_events(
            ["ANCHOR", "PRESSURE", "TERMINAL"],
            path_started_at="2026-01-01T00:00:00Z",
        )

        def validate(candidate_spec: object) -> tuple[bool, str]:
            return _path_valid(
                events,
                candidate_spec,
                decision_time="2026-01-02T00:00:01Z",
                path_started_at="2026-01-01T00:00:00Z",
                requested_horizon_seconds=spec["frozen_horizon_seconds"],
                path_spec_fields=spec_fields,
                path_event_fields=event_fields,
            )

        self.assertEqual(validate(spec), (True, "VALID"))
        mutations: list[tuple[str, dict[str, object]]] = [
            ("horizon", {"frozen_horizon_seconds": 172800}),
            ("falsifier", {"hard_falsifiers": ["ATTACKER_INVALIDATION"]}),
            ("milestone-order", {"milestone_vocabulary": list(reversed(spec["milestone_vocabulary"]))}),
            ("primitive-order", {"primitive_mechanism_ids": list(reversed(spec["primitive_mechanism_ids"]))}),
        ]
        nested_guard = copy.deepcopy(spec["runtime_capacity_guard"])
        nested_guard["max_in_memory_observations"] = 255
        mutations.append(("nested-capacity-guard", {"runtime_capacity_guard": nested_guard}))
        for label, mutation in mutations:
            with self.subTest(label=label):
                attacker_candidate = spec | mutation
                attacker_recomputed_digest = _path_spec_digest(
                    attacker_candidate,
                    spec_fields,
                )
                self.assertNotEqual(
                    attacker_recomputed_digest,
                    authority[0]["path_spec_digest"],
                )
                self.assertEqual(
                    validate(attacker_candidate),
                    (False, "PATH_SPEC_AUTHORITY_DIGEST_MISMATCH"),
                )

        self_signed_payload = spec | {
            "path_spec_digest": _path_spec_digest(spec, spec_fields)
        }
        self.assertEqual(
            validate(self_signed_payload),
            (False, "PATH_SPEC_SCHEMA_INVALID"),
        )

    def test_path_merge_requires_predeclared_nonempty_equivalence(self) -> None:
        left = {"merge_equivalence_class": "E1"}
        self.assertTrue(_can_merge(left, {"merge_equivalence_class": "E1"}))
        self.assertFalse(_can_merge(left, {"merge_equivalence_class": "E2"}))
        self.assertFalse(_can_merge({"merge_equivalence_class": ""}, {"merge_equivalence_class": ""}))
        self.assertFalse(_can_merge({}, {}))

    def test_volume_wick_keeps_five_competitors_and_does_not_force_absorption(self) -> None:
        declared = tuple(self.synthetic["mechanism_library"]["volume_wick_candidate_ids"])
        candidates = _volume_wick_candidates(volume_spike=True, long_wick=True, declared=declared)
        self.assertEqual(candidates, ("CONTINUATION", "ABSORPTION_REVERSAL", "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM", "ARTIFACT", "OTHER"))
        self.assertGreater(len(candidates), 1)
        self.assertNotEqual(candidates, ("ABSORPTION_REVERSAL",))
        self.assertEqual(_volume_wick_candidates(volume_spike="true", long_wick=True, declared=declared), ("OTHER",))

    def test_uncovered_feed_silence_is_unknown_not_zero_or_no_event(self) -> None:
        self.assertEqual(_feed_disposition(covered=False, events=[]), "UNKNOWN")
        self.assertEqual(_feed_disposition(covered=True, events=[]), "NO_EVENT_OBSERVED")
        self.assertEqual(_feed_disposition(covered=True, events=[{"event_id": "e"}]), "OBSERVED")
        self.assertEqual(_feed_disposition(covered=0, events=[]), "UNKNOWN")

    def test_late_event_appends_receipt_without_prefix_rewrite(self) -> None:
        original = [{"receipt_id": "r1", "belief": {"P1": 2}}]
        before = copy.deepcopy(original)
        updated = _append_late_event(original, {"event_id": "e2"})
        self.assertEqual(original, before)
        self.assertEqual(updated[0], before[0])
        self.assertEqual(updated[-1], {"receipt_id": "r2", "previous_receipt_id": "r1", "event_id": "e2"})
        self.assertEqual(len(updated), len(original) + 1)

    def test_primitive_support_summary_is_multi_label_and_does_not_invent_a_top_path(self) -> None:
        all_weak_support = {mechanism_id: 0 for mechanism_id in MECHANISMS}
        all_weak = _primitive_support_summary(all_weak_support)
        multi_support = all_weak_support | {
            "CONTINUATION": 3,
            "EVENT_REPRICING": 2,
            "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM": 4,
        }
        multi = _primitive_support_summary(multi_support)
        self.assertEqual(all_weak["active_primitive_mechanism_ids"], ("OTHER",))
        self.assertEqual(all_weak["unknown_reason"], "ALL_WEAK")
        self.assertEqual(set(multi["active_primitive_mechanism_ids"]), {"CONTINUATION", "EVENT_REPRICING", "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"})
        self.assertEqual(multi["top_path_hypothesis_id"], "UNKNOWN")
        self.assertEqual(multi["unknown_reason"], "UNKNOWN_NO_VALID_COMPETITION_SET")
        self.assertEqual(multi["margin"], "UNKNOWN_UNCALIBRATED")
        self.assertEqual(multi["entropy"], "UNKNOWN_UNCALIBRATED")

    def test_primitive_support_updates_coexist_without_simplex_displacement(self) -> None:
        fields = tuple(self.method["evidence_contract"]["exact_fields"])
        decision_time = "2026-01-01T00:00:01Z"
        prior = {mechanism_id: 0 for mechanism_id in MECHANISMS}
        rows = [
            _synthetic_evidence("event", ["EVENT_REPRICING"], direction="SUPPORT", ordinal_strength="MODERATE"),
            _synthetic_evidence("vacuum", ["LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"], direction="SUPPORT", ordinal_strength="STRONG"),
            _synthetic_evidence("continue", ["CONTINUATION"], direction="SUPPORT", ordinal_strength="MODERATE"),
        ]
        first = _primitive_support_update(prior, rows, decision_time, fields)
        first_values = {mechanism_id: row["support"] for mechanism_id, row in first.items()}
        self.assertEqual(first_values["EVENT_REPRICING"], 2)
        self.assertEqual(first_values["LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"], 3)
        self.assertEqual(first_values["CONTINUATION"], 2)
        self.assertGreater(sum(first_values.values()), 1)
        self.assertFalse(_probability_vector_valid(first_values, MECHANISMS))

        additional_event = rows + [
            _synthetic_evidence("event-2", ["EVENT_REPRICING"], direction="SUPPORT", ordinal_strength="WEAK", available_at="2026-01-01T00:00:00.500000Z")
        ]
        second = _primitive_support_update(prior, additional_event, decision_time, fields)
        self.assertGreater(second["EVENT_REPRICING"]["support"], first["EVENT_REPRICING"]["support"])
        self.assertEqual(second["CONTINUATION"]["support"], first["CONTINUATION"]["support"])
        self.assertEqual(second["LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"]["support"], first["LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"]["support"])

    def test_compound_path_requires_nonempty_unique_registered_primitives_and_registry_membership(self) -> None:
        spec = self.synthetic["sample_path_specs"][0]
        path_registry = self.synthetic["path_contract"]["path_hypothesis_registry"]
        self.assertTrue(_path_spec_primitives_valid(spec, MECHANISMS))
        self.assertGreater(len(spec["primitive_mechanism_ids"]), 1)
        self.assertTrue(_registered_compound_path(spec, path_registry))
        for mutation in (
            {"primitive_mechanism_ids": []},
            {"primitive_mechanism_ids": ["CONTINUATION", "CONTINUATION"]},
            {"primitive_mechanism_ids": ["CONTINUATION", "LLM_NEW_STORY"]},
            {"path_id": "RUNTIME-POWER-SET-INJECTION"},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_registered_compound_path(spec | mutation, path_registry))
        self.assertEqual(self.synthetic["path_contract"]["runtime_power_set_or_cartesian_product"], "FORBIDDEN")
        self.assertEqual(self.synthetic["path_contract"]["runtime_or_llm_compound_injection"], "FORBIDDEN")

    def test_path_normalization_requires_a_complete_auditable_competition_set(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof_registry = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        weights = {
            "PATH-GENERIC-COMPETING-001": 0.4,
            "PATH-ABSORPTION-REVERSAL-001": 0.3,
            "PATH-RANGE-001": 0.2,
            "OTHER_PATH": 0.1,
        }
        self.assertEqual(
            set(
                _partition_proof_registry_by_id(
                    proof_registry,
                    registry,
                    proof_fields,
                    cell_fields,
                    authority_registry,
                    authority_fields,
                )
            ),
            {"PP-SYNTHETIC-COMPOUND-TERMINAL-V1"},
        )
        self.assertEqual(proof_registry[0]["path_registry_digest"], _path_registry_digest(registry))
        self.assertTrue(
            _competition_set_valid(
                competition,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        )
        self.assertTrue(
            _path_hypothesis_weights_valid(
                weights,
                competition,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        )
        for mutation in (
            {"competition_set_id": ""},
            {"competition_set_id": "PCS-NOT-BOUND-TO-PROOF"},
            {"partition_proof_id": "NOT_A_PROOF"},
            {"partition_version": "9.9.9"},
            {"exclusivity_basis": "ANALYST_SAYS_PATHS_ARE_EXCLUSIVE"},
            {"exhaustive": False},
            {"exhaustive": "true"},
            {"residual_path_id": "PATH-RANGE-001"},
            {"calibration_version": ""},
            {"calibration_version": "SYNTHETIC-CAL-DRIFT"},
            {"path_hypothesis_ids": ["PATH-GENERIC-COMPETING-001", "RUNTIME-COMPOUND", "OTHER_PATH"]},
            {"path_hypothesis_ids": ["PATH-GENERIC-COMPETING-001", "PATH-GENERIC-COMPETING-001", "OTHER_PATH"]},
            {"path_hypothesis_ids": list(reversed(competition["path_hypothesis_ids"]))},
        ):
            with self.subTest(mutation=mutation):
                invalid = competition | mutation
                self.assertFalse(
                    _competition_set_valid(
                        invalid,
                        registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )
                self.assertFalse(
                    _path_hypothesis_weights_valid(
                        weights,
                        invalid,
                        registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )
        missing = dict(competition)
        missing.pop("partition_proof_id")
        self.assertFalse(
            _competition_set_valid(
                missing,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        )

    def test_partition_proof_registry_executes_finite_disjoint_exhaustive_residual_checks(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        valid_proofs = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        proof = valid_proofs[0]

        malformed_registries: list[tuple[str, list[dict[str, object]]]] = []

        duplicate_id = [copy.deepcopy(proof), copy.deepcopy(proof)]
        malformed_registries.append(("duplicate-proof-id", duplicate_id))

        wrong_registry_digest = [copy.deepcopy(proof)]
        wrong_registry_digest[0]["path_registry_digest"] = "0" * 64
        malformed_registries.append(("path-registry-digest-mismatch", wrong_registry_digest))

        nonexclusive = [copy.deepcopy(proof)]
        nonexclusive[0]["mutually_exclusive"] = False
        malformed_registries.append(("mutually-exclusive-false", nonexclusive))

        nonexclusive_string = [copy.deepcopy(proof)]
        nonexclusive_string[0]["mutually_exclusive"] = "true"
        malformed_registries.append(("mutually-exclusive-string", nonexclusive_string))

        nonexhaustive = [copy.deepcopy(proof)]
        nonexhaustive[0]["exhaustive"] = False
        malformed_registries.append(("exhaustive-false", nonexhaustive))

        nonexhaustive_string = [copy.deepcopy(proof)]
        nonexhaustive_string[0]["exhaustive"] = "true"
        malformed_registries.append(("exhaustive-string", nonexhaustive_string))

        missing_residual = [copy.deepcopy(proof)]
        missing_residual[0].pop("residual_path_id")
        malformed_registries.append(("missing-residual", missing_residual))

        wrong_residual = [copy.deepcopy(proof)]
        wrong_residual[0]["residual_path_id"] = "PATH-RANGE-001"
        malformed_registries.append(("wrong-residual-role", wrong_residual))

        empty_cell = [copy.deepcopy(proof)]
        empty_cell[0]["partition_cells"][0]["domain_values"] = []
        malformed_registries.append(("empty-cell", empty_cell))

        overlap = [copy.deepcopy(proof)]
        overlap[0]["partition_cells"][1]["domain_values"] = [
            overlap[0]["partition_cells"][0]["domain_values"][0]
        ]
        malformed_registries.append(("cell-overlap", overlap))

        gap = [copy.deepcopy(proof)]
        gap[0]["domain_values"].append("UNASSIGNED_TERMINAL")
        malformed_registries.append(("domain-union-gap", gap))

        duplicate_domain = [copy.deepcopy(proof)]
        duplicate_domain[0]["domain_values"].append(duplicate_domain[0]["domain_values"][0])
        malformed_registries.append(("duplicate-domain-value", duplicate_domain))

        reordered_cells = [copy.deepcopy(proof)]
        reordered_cells[0]["partition_cells"][0], reordered_cells[0]["partition_cells"][1] = (
            reordered_cells[0]["partition_cells"][1],
            reordered_cells[0]["partition_cells"][0],
        )
        malformed_registries.append(("cell-path-order-drift", reordered_cells))

        residual_cell_mismatch = [copy.deepcopy(proof)]
        residual_cell_mismatch[0]["residual_domain_values"] = ["RANGE_TERMINAL"]
        malformed_registries.append(("residual-cell-mismatch", residual_cell_mismatch))

        residual_semantic_drift = [copy.deepcopy(proof)]
        residual_semantic_drift[0]["domain_values"][-1] = "NOT_OTHER_TERMINAL"
        residual_semantic_drift[0]["partition_cells"][-1]["domain_values"] = ["NOT_OTHER_TERMINAL"]
        residual_semantic_drift[0]["residual_domain_values"] = ["NOT_OTHER_TERMINAL"]
        malformed_registries.append(("residual-semantic-drift", residual_semantic_drift))

        path_set_drift = [copy.deepcopy(proof)]
        path_set_drift[0]["path_hypothesis_ids"] = list(reversed(path_set_drift[0]["path_hypothesis_ids"]))
        malformed_registries.append(("proof-path-order-drift", path_set_drift))

        unknown_cell_path = [copy.deepcopy(proof)]
        unknown_cell_path[0]["partition_cells"][0]["path_hypothesis_id"] = "UNKNOWN_PATH"
        malformed_registries.append(("unknown-cell-path", unknown_cell_path))

        for label, invalid_proofs in malformed_registries:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    _partition_proof_registry_by_id(
                        invalid_proofs,
                        registry,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                self.assertFalse(
                    _competition_set_valid(
                        competition,
                        registry,
                        invalid_proofs,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )

        for field, value in (
            ("competition_set_id", "PCS-PROOF-SET-DRIFT"),
            ("partition_version", "2.0.0"),
            ("calibration_version", "SYNTHETIC-CAL-DRIFT"),
        ):
            with self.subTest(binding_field=field):
                drifted_proofs = [copy.deepcopy(proof)]
                drifted_proofs[0][field] = value
                drifted_proofs[0]["partition_proof_digest"] = _partition_proof_digest(
                    drifted_proofs[0]
                )
                with self.assertRaisesRegex(ValueError, "PARTITION_PROOF_AUTHORITY_MISMATCH"):
                    _partition_proof_registry_by_id(
                        drifted_proofs,
                        registry,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                self.assertFalse(
                    _competition_set_valid(
                        competition,
                        registry,
                        drifted_proofs,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )

    def test_partition_proof_rejects_same_path_ids_with_definition_or_order_drift(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof_registry = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        expected_digest = proof_registry[0]["path_registry_digest"]

        for label, definition_drift in (
            (
                "same-id-primitive-definition-drift",
                {"index": 2, "primitive_mechanism_ids": ["CONTINUATION"]},
            ),
            (
                "same-id-primitive-order-drift",
                {
                    "index": 0,
                    "primitive_mechanism_ids": [
                        "CONTINUATION",
                        "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM",
                        "EVENT_REPRICING",
                    ],
                },
            ),
        ):
            with self.subTest(label=label):
                drifted_registry = copy.deepcopy(registry)
                row_index = definition_drift["index"]
                drifted_registry[row_index]["primitive_mechanism_ids"] = definition_drift[
                    "primitive_mechanism_ids"
                ]
                self.assertEqual(set(_path_registry_by_id(drifted_registry)), set(_path_registry_by_id(registry)))
                self.assertNotEqual(_path_registry_digest(drifted_registry), expected_digest)
                with self.assertRaisesRegex(ValueError, "PARTITION_PROOF_AUTHORITY_INVALID"):
                    _partition_proof_registry_by_id(
                        proof_registry,
                        drifted_registry,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                self.assertFalse(
                    _competition_set_valid(
                        competition,
                        drifted_registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )

        role_drift_registry = copy.deepcopy(registry)
        role_drift_registry[0]["role"] = "RESIDUAL_PATH"
        with self.assertRaisesRegex(ValueError, "RESIDUAL_PATH_NOT_EXACT_OTHER"):
            _path_registry_by_id(role_drift_registry)
        with self.assertRaises(ValueError):
            _partition_proof_registry_by_id(
                proof_registry,
                role_drift_registry,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        self.assertFalse(
            _competition_set_valid(
                competition,
                role_drift_registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        )

    def test_partition_proof_full_content_is_bound_to_method_authority(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof = path_contract["partition_proof_registry"][0]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )

        residual_only = copy.deepcopy(proof)
        residual_only["domain_values"] = ["OTHER_OR_UNRESOLVED_TERMINAL"]
        residual_only["path_hypothesis_ids"] = ["OTHER_PATH"]
        residual_only["partition_cells"] = [copy.deepcopy(proof["partition_cells"][-1])]

        domain_and_cell_rename = copy.deepcopy(proof)
        domain_and_cell_rename["domain_values"][0] = "RENAMED_MARKET_TERMINAL"
        domain_and_cell_rename["partition_cells"][0]["domain_values"] = [
            "RENAMED_MARKET_TERMINAL"
        ]

        market_cell_swap = copy.deepcopy(proof)
        (
            market_cell_swap["partition_cells"][0]["domain_values"],
            market_cell_swap["partition_cells"][1]["domain_values"],
        ) = (
            market_cell_swap["partition_cells"][1]["domain_values"],
            market_cell_swap["partition_cells"][0]["domain_values"],
        )

        domain_id_drift = copy.deepcopy(proof)
        domain_id_drift["partition_domain_id"] = "SYNTHETIC_DOMAIN_DRIFT"

        ordered_content_drift = copy.deepcopy(proof)
        ordered_content_drift["domain_values"][0], ordered_content_drift["domain_values"][1] = (
            ordered_content_drift["domain_values"][1],
            ordered_content_drift["domain_values"][0],
        )

        for label, drifted_proof in (
            ("residual-only-shrink", residual_only),
            ("domain-and-cell-rename", domain_and_cell_rename),
            ("market-cell-swap", market_cell_swap),
            ("partition-domain-id-drift", domain_id_drift),
            ("ordered-proof-content-drift", ordered_content_drift),
        ):
            with self.subTest(label=label):
                drifted_proof["partition_proof_digest"] = _partition_proof_digest(
                    drifted_proof
                )
                drifted_registry = [drifted_proof]
                drifted_competition = copy.deepcopy(competition)
                drifted_competition["path_hypothesis_ids"] = list(
                    drifted_proof["path_hypothesis_ids"]
                )
                drifted_competition["partition_proof_digest"] = drifted_proof[
                    "partition_proof_digest"
                ]
                with self.assertRaisesRegex(ValueError, "PARTITION_PROOF_AUTHORITY_MISMATCH"):
                    _partition_proof_registry_by_id(
                        drifted_registry,
                        registry,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                self.assertFalse(
                    _competition_set_valid(
                        drifted_competition,
                        registry,
                        drifted_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )

        residual_only_authority = copy.deepcopy(authority_registry)
        residual_only_authority[0]["partition_proof_digest"] = residual_only[
            "partition_proof_digest"
        ]
        residual_only_authority[0]["domain_values"] = list(
            residual_only["domain_values"]
        )
        residual_only_authority[0]["path_hypothesis_ids"] = list(
            residual_only["path_hypothesis_ids"]
        )
        with self.assertRaisesRegex(ValueError, "PARTITION_PROOF_AUTHORITY_INVALID"):
            _partition_proof_authorities_by_id(
                residual_only_authority,
                authority_fields,
                registry,
            )

    def test_artifact_residual_registry_competition_and_utility_fail_closed(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof_registry = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        weights = {
            "PATH-GENERIC-COMPETING-001": 0.4,
            "PATH-ABSORPTION-REVERSAL-001": 0.3,
            "PATH-RANGE-001": 0.2,
            "OTHER_PATH": 0.1,
        }
        scenario_fields = tuple(
            self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"]
        )
        decision_time = "2026-01-01T00:00:01Z"
        scenarios_by_path = {
            path_id: {
                "distribution_id": f"SD-ARTIFACT-GUARD-{index:03d}",
                "as_of": "2026-01-01T00:00:00Z",
                "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
                "branches": list(SCENARIOS),
                "values": {"UPSIDE": 0.4, "DOWNSIDE": 0.2, "RANGE": 0.2, "UNRESOLVED": 0.2},
                "normalization_status": "NORMALIZED",
                "calibration_version": "SYNTHETIC-CAL-V1",
                "unknown_reason": None,
            }
            for index, path_id in enumerate(weights)
        }
        utility = {"UPSIDE": 3.0, "DOWNSIDE": -2.0, "RANGE": -0.5, "UNRESOLVED": -1.0}

        for primitives in (["ARTIFACT"], ["OTHER", "ARTIFACT"]):
            with self.subTest(residual_primitives=primitives):
                artifact_registry = copy.deepcopy(registry)
                artifact_registry[-1]["primitive_mechanism_ids"] = primitives
                with self.assertRaisesRegex(ValueError, "ARTIFACT_MIXTURE_PATH_FORBIDDEN"):
                    _path_registry_by_id(artifact_registry)
                self.assertFalse(
                    _competition_set_valid(
                        competition,
                        artifact_registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )
                with self.assertRaisesRegex(ValueError, "PATH_COMPETITION_INVALID"):
                    _path_conditioned_utility(
                        weights,
                        competition,
                        artifact_registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                        scenarios_by_path,
                        scenario_fields,
                        decision_time,
                        utility,
                    )

        for primitive, expected_error in (
            ("ARTIFACT", "ARTIFACT_MIXTURE_PATH_FORBIDDEN"),
            ("OTHER", "OTHER_MARKET_PATH_FORBIDDEN"),
        ):
            with self.subTest(market_primitive=primitive):
                invalid_registry = copy.deepcopy(registry)
                invalid_registry[0]["primitive_mechanism_ids"].append(primitive)
                with self.assertRaisesRegex(ValueError, expected_error):
                    _path_registry_by_id(invalid_registry)
                self.assertFalse(
                    _competition_set_valid(
                        competition,
                        invalid_registry,
                        proof_registry,
                        fields,
                        proof_fields,
                        cell_fields,
                        authority_registry,
                        authority_fields,
                    )
                )

    def test_calibrated_compound_path_summary_rejects_boolean_and_nonnormalized_weights(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof_registry = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        weights = {
            "PATH-GENERIC-COMPETING-001": 0.7,
            "PATH-ABSORPTION-REVERSAL-001": 0.1,
            "PATH-RANGE-001": 0.1,
            "OTHER_PATH": 0.1,
        }
        summary = _calibrated_path_summary(
            weights,
            competition,
            registry,
            proof_registry,
            fields,
            proof_fields,
            cell_fields,
            authority_registry,
            authority_fields,
        )
        self.assertEqual(summary["top_path_hypothesis_id"], "PATH-GENERIC-COMPETING-001")
        self.assertTrue(math.isclose(summary["margin"], 0.6))
        self.assertGreater(summary["entropy"], 0.0)
        with self.assertRaisesRegex(ValueError, "WEIGHTS_INVALID"):
            _calibrated_path_summary(
                weights | {"PATH-GENERIC-COMPETING-001": True},
                competition,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )
        with self.assertRaisesRegex(ValueError, "WEIGHTS_INVALID"):
            _calibrated_path_summary(
                weights | {"PATH-GENERIC-COMPETING-001": 0.8},
                competition,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
            )

    def test_rsi_absent_scheduled_and_state_change_evaluation_still_run(self) -> None:
        triggers = tuple(self.method["evaluation_contract"]["trigger_reasons"])
        self.assertTrue(_evaluation_runs("SCHEDULED", None, triggers))
        self.assertTrue(_evaluation_runs("STATE_CHANGE", None, triggers))
        self.assertTrue(_evaluation_runs("EVENT_ARRIVAL", None, triggers))
        self.assertTrue(_evaluation_runs("DATA_QUALITY_CHANGE", None, triggers))
        self.assertTrue(_evaluation_runs("POSITION_RISK", None, triggers))
        self.assertFalse(_evaluation_runs("RSI_ONLY", None, triggers))
        self.assertFalse(_evaluation_runs(1, None, triggers))

    def test_p0_conservative_utility_uses_scenario_only_and_rejects_primitive_weights(self) -> None:
        decision_time = "2026-01-01T00:00:01Z"
        scenario_fields = tuple(
            self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"]
        )
        utility_receipt_fields = tuple(
            self.method["object_schemas"]["UtilityReceipt"]["exact_fields"]
        )
        scenario = {
            "distribution_id": "SD-SYNTHETIC-UTILITY-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": 0.5, "DOWNSIDE": 0.2, "RANGE": 0.2, "UNRESOLVED": 0.1},
            "normalization_status": "NORMALIZED",
            "calibration_version": "SYNTHETIC-CAL-V1",
            "unknown_reason": None,
        }
        utility = {"UPSIDE": 3.0, "DOWNSIDE": -2.0, "RANGE": -0.5, "UNRESOLVED": -1.0}
        receipt = _conservative_utility(
            scenario,
            scenario_fields,
            decision_time,
            utility_receipt_fields,
            utility,
            stress_cost=0.1,
            tail=0.1,
            uncertainty_penalty=0.1,
        )
        self.assertTrue(math.isclose(receipt["conservative_utility"], 0.6, abs_tol=1e-12))
        self.assertTrue(
            _utility_receipt_valid(
                receipt,
                utility_receipt_fields,
                scenario,
                scenario_fields,
                decision_time,
            )
        )
        primitive_weights = {mechanism_id: 1.0 / len(MECHANISMS) for mechanism_id in MECHANISMS}
        with self.assertRaisesRegex(ValueError, "SCENARIO_INVALID"):
            _conservative_utility(
                primitive_weights,
                scenario_fields,
                decision_time,
                utility_receipt_fields,
                utility,
                stress_cost=0.1,
                tail=0.1,
                uncertainty_penalty=0.1,
            )
        with self.assertRaisesRegex(ValueError, "SCENARIO_INVALID"):
            _conservative_utility(
                {"ARTIFACT": 1.0},
                scenario_fields,
                decision_time,
                utility_receipt_fields,
                utility,
                stress_cost=0.1,
                tail=0.1,
                uncertainty_penalty=0.1,
            )
        bad_scenario = copy.deepcopy(scenario)
        bad_scenario["values"]["UPSIDE"] = 1.2
        with self.assertRaisesRegex(ValueError, "SCENARIO_INVALID"):
            _conservative_utility(
                bad_scenario,
                scenario_fields,
                decision_time,
                utility_receipt_fields,
                utility,
                stress_cost=0.1,
                tail=0.1,
                uncertainty_penalty=0.1,
            )
        tampered_receipt = copy.deepcopy(receipt)
        tampered_receipt["stress_cost"] = 0.0
        self.assertFalse(
            _utility_receipt_valid(
                tampered_receipt,
                utility_receipt_fields,
                scenario,
                scenario_fields,
                decision_time,
            )
        )

    def test_optional_path_conditioned_utility_rejects_primitive_or_unregistered_keys(self) -> None:
        path_contract = self.synthetic["path_contract"]
        competition = path_contract["sample_competition_set"]
        registry = path_contract["path_hypothesis_registry"]
        proof_registry = path_contract["partition_proof_registry"]
        fields = tuple(self.method["belief_contract"]["competition_set_exact_fields"])
        proof_fields = tuple(self.method["belief_contract"]["partition_proof_exact_fields"])
        cell_fields = tuple(self.method["belief_contract"]["partition_cell_exact_fields"])
        authority_registry = self.method["belief_contract"]["partition_proof_authority_registry"]
        authority_fields = tuple(
            self.method["belief_contract"]["partition_proof_authority_exact_fields"]
        )
        weights = {
            "PATH-GENERIC-COMPETING-001": 0.4,
            "PATH-ABSORPTION-REVERSAL-001": 0.3,
            "PATH-RANGE-001": 0.2,
            "OTHER_PATH": 0.1,
        }
        scenario_fields = tuple(
            self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"]
        )
        decision_time = "2026-01-01T00:00:01Z"
        scenarios_by_path = {
            path_id: {
                "distribution_id": f"SD-PATH-{index:03d}",
                "as_of": "2026-01-01T00:00:00Z",
                "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
                "branches": list(SCENARIOS),
                "values": {"UPSIDE": 0.4, "DOWNSIDE": 0.2, "RANGE": 0.2, "UNRESOLVED": 0.2},
                "normalization_status": "NORMALIZED",
                "calibration_version": "SYNTHETIC-CAL-V1",
                "unknown_reason": None,
            }
            for index, path_id in enumerate(weights)
        }
        utility = {"UPSIDE": 3.0, "DOWNSIDE": -2.0, "RANGE": -0.5, "UNRESOLVED": -1.0}
        value = _path_conditioned_utility(
            weights,
            competition,
            registry,
            proof_registry,
            fields,
            proof_fields,
            cell_fields,
            authority_registry,
            authority_fields,
            scenarios_by_path,
            scenario_fields,
            decision_time,
            utility,
        )
        self.assertTrue(math.isclose(value, 0.5, abs_tol=1e-12))
        primitive_weights = {
            "CONTINUATION": 0.4,
            "EVENT_REPRICING": 0.3,
            "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM": 0.2,
            "ARTIFACT": 0.1,
        }
        with self.assertRaisesRegex(ValueError, "PATH_COMPETITION_INVALID"):
            _path_conditioned_utility(
                primitive_weights,
                competition,
                registry,
                proof_registry,
                fields,
                proof_fields,
                cell_fields,
                authority_registry,
                authority_fields,
                scenarios_by_path,
                scenario_fields,
                decision_time,
                utility,
            )

    def test_v5_m00_exact_carriers_never_authorize_new_risk(self) -> None:
        decision_time = "2026-01-01T00:00:01Z"
        scenario_fields = tuple(
            self.method["object_schemas"]["ScenarioDistribution"]["exact_fields"]
        )
        utility_receipt_fields = tuple(
            self.method["object_schemas"]["UtilityReceipt"]["exact_fields"]
        )
        permission_fields = tuple(
            self.method["object_schemas"]["PermissionEnvelope"]["exact_fields"]
        )
        action_fields = tuple(
            self.method["object_schemas"]["ActionCandidate"]["exact_fields"]
        )
        scenario = {
            "distribution_id": "SD-SYNTHETIC-ACTION-BARRIER-001",
            "as_of": "2026-01-01T00:00:00Z",
            "mode": "SYNTHETIC_COUNTERFACTUAL_ONLY",
            "branches": list(SCENARIOS),
            "values": {"UPSIDE": 0.5, "DOWNSIDE": 0.2, "RANGE": 0.2, "UNRESOLVED": 0.1},
            "normalization_status": "NORMALIZED",
            "calibration_version": "SYNTHETIC-CAL-V1",
            "unknown_reason": None,
        }
        utility = {"UPSIDE": 3.0, "DOWNSIDE": -2.0, "RANGE": -0.5, "UNRESOLVED": -1.0}
        receipt = _conservative_utility(
            scenario,
            scenario_fields,
            decision_time,
            utility_receipt_fields,
            utility,
            stress_cost=0.1,
            tail=0.1,
            uncertainty_penalty=0.1,
        )
        permission = {
            "envelope_id": "PE-V5-M00-DENY-001",
            "as_of": "2026-01-01T00:00:00Z",
            "permission_state": "DENY",
            "allowed_actions": ["ABSTAIN"],
            "max_risk": 0,
            "vetoes": ["V5_M00_NO_NEW_RISK"],
            "authority_version": "V5-M00-E0-NO-NEW-RISK",
        }
        base = {
            "permission_envelope": permission,
            "permission_fields": permission_fields,
            "scenario_distribution": scenario,
            "scenario_fields": scenario_fields,
            "utility_receipt": receipt,
            "utility_receipt_fields": utility_receipt_fields,
            "action_candidate_fields": action_fields,
            "decision_time": decision_time,
            "zones": [[100.0, 102.0], [101.0, 103.0]],
            "side": "LONG",
            "stop": 99.0,
            "target": 104.0,
            "entry_reference": 101.5,
            "horizon": 60,
            "risk_budget": 10.0,
            "worst_cost_per_unit": 0.2,
            "tail_per_unit": 0.3,
            "liquidity_cap": 9.0,
            "venue_cap": 8.0,
            "margin_cap": 7.0,
        }
        candidate = _action_candidate(**base)
        self.assertTrue(_exact_keys(candidate, action_fields))
        self.assertEqual(candidate["action"], "ABSTAIN")
        self.assertEqual(candidate["reason_codes"], ["V5_M00_NEW_RISK_FORBIDDEN"])
        self.assertEqual(candidate["size"], 0.0)
        self.assertEqual(candidate["utility_receipt_digest"], receipt["utility_receipt_digest"])
        self.assertEqual(candidate["permission_envelope_digest"], _permission_envelope_digest(permission))

        tampered_receipt = copy.deepcopy(receipt)
        tampered_receipt["conservative_utility"] = 999.0
        future_permission = permission | {"as_of": "2099-01-01T00:00:00Z"}
        missing_permission_as_of = dict(permission)
        missing_permission_as_of.pop("as_of")
        pseudo_allow = permission | {
            "permission_state": "ALLOW_NEW_RISK",
            "allowed_actions": ["ABSTAIN", "EVALUATE_NEW_RISK"],
            "max_risk": 10,
        }
        pseudo_calibrated_bool = scenario | {"calibrated": True}
        future_scenario = scenario | {"as_of": "2099-01-01T00:00:00Z"}
        missing_scenario_as_of = dict(scenario)
        missing_scenario_as_of.pop("as_of")
        for label, mutation, reason, absent_fields in (
            (
                "raw-permission-string",
                {"permission_envelope": "ALLOW_NEW_RISK"},
                "PERMISSION_ENVELOPE_INVALID",
                ("permission_envelope_id", "permission_envelope_digest"),
            ),
            (
                "future-permission",
                {"permission_envelope": future_permission},
                "PERMISSION_ENVELOPE_INVALID",
                ("permission_envelope_id", "permission_envelope_digest"),
            ),
            (
                "missing-permission-as-of",
                {"permission_envelope": missing_permission_as_of},
                "PERMISSION_ENVELOPE_INVALID",
                ("permission_envelope_id", "permission_envelope_digest"),
            ),
            (
                "pseudo-allow-envelope",
                {"permission_envelope": pseudo_allow},
                "PERMISSION_ENVELOPE_INVALID",
                ("permission_envelope_id", "permission_envelope_digest"),
            ),
            (
                "raw-scenario-map",
                {"scenario_distribution": scenario["values"]},
                "SCENARIO_DISTRIBUTION_INVALID",
                (
                    "scenario_distribution_id",
                    "scenario_distribution_digest",
                    "utility_receipt_id",
                    "utility_receipt_digest",
                ),
            ),
            (
                "pseudo-calibrated-bool",
                {"scenario_distribution": pseudo_calibrated_bool},
                "SCENARIO_DISTRIBUTION_INVALID",
                (
                    "scenario_distribution_id",
                    "scenario_distribution_digest",
                    "utility_receipt_id",
                    "utility_receipt_digest",
                ),
            ),
            (
                "future-scenario-as-of",
                {"scenario_distribution": future_scenario},
                "SCENARIO_DISTRIBUTION_INVALID",
                (
                    "scenario_distribution_id",
                    "scenario_distribution_digest",
                    "utility_receipt_id",
                    "utility_receipt_digest",
                ),
            ),
            (
                "missing-scenario-as-of",
                {"scenario_distribution": missing_scenario_as_of},
                "SCENARIO_DISTRIBUTION_INVALID",
                (
                    "scenario_distribution_id",
                    "scenario_distribution_digest",
                    "utility_receipt_id",
                    "utility_receipt_digest",
                ),
            ),
            (
                "raw-utility-scalar",
                {"utility_receipt": 1.0},
                "UTILITY_RECEIPT_INVALID",
                ("utility_receipt_id", "utility_receipt_digest"),
            ),
            (
                "tampered-utility-receipt",
                {"utility_receipt": tampered_receipt},
                "UTILITY_RECEIPT_INVALID",
                ("utility_receipt_id", "utility_receipt_digest"),
            ),
        ):
            with self.subTest(label=label):
                rejected = _action_candidate(**(base | mutation))
                self.assertEqual(rejected["action"], "ABSTAIN")
                self.assertEqual(rejected["reason_codes"], [reason])
                self.assertEqual(rejected["size"], 0.0)
                for field in absent_fields:
                    self.assertIsNone(rejected[field])

    def test_research_geometry_size_and_margin_cap_are_separate_from_permission(self) -> None:
        base = {
            "zones": [[100.0, 102.0], [101.0, 103.0], [100.5, 101.5], [99.0, 104.0]],
            "side": "LONG",
            "stop": 99.0,
            "target": 104.0,
            "entry_reference": 101.0,
            "horizon": 60,
            "risk_budget": 100.0,
            "worst_cost_per_unit": 0.2,
            "tail_per_unit": 0.3,
            "liquidity_cap": 9.0,
            "venue_cap": 8.0,
            "margin_cap": 3.0,
        }
        accepted = _research_geometry_candidate(**base)
        self.assertTrue(accepted["valid"])
        self.assertEqual(accepted["entry_zone"], (101.0, 101.5))
        self.assertEqual(accepted["size"], 3.0)
        self.assertEqual(_research_geometry_candidate(**(base | {"stop": 101.2}))["reason"], "GEOMETRY")
        self.assertEqual(_research_geometry_candidate(**(base | {"entry_reference": 102.0}))["reason"], "GEOMETRY")
        short = base | {"side": "SHORT", "stop": 104.0, "target": 99.0, "entry_reference": 101.0}
        self.assertTrue(_research_geometry_candidate(**short)["valid"])
        self.assertEqual(_research_geometry_candidate(**(short | {"target": 101.2}))["reason"], "GEOMETRY")
        for mutation in (
            {"risk_budget": 0.0},
            {"risk_budget": -1.0},
            {"risk_budget": True},
            {"risk_budget": math.nan},
            {"risk_budget": math.inf},
            {"liquidity_cap": 0.0},
            {"venue_cap": 0.0},
            {"margin_cap": 0.0},
            {"worst_cost_per_unit": -0.1},
            {"tail_per_unit": -0.1},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_research_geometry_candidate(**(base | mutation))["valid"])

    def test_post_position_actions_are_one_way_and_path_switch_cannot_reverse(self) -> None:
        long = {
            "side": "LONG",
            "prior_stop": 98.0,
            "updated_stop": 98.0,
            "prior_target": 104.0,
            "updated_target": 104.0,
            "prior_horizon": 60,
            "updated_horizon": 60,
            "prior_size": 2.0,
            "updated_size": 2.0,
        }
        self.assertTrue(_post_position_valid(action="KEEP", **long))
        self.assertTrue(_post_position_valid(action="TIGHTEN", **(long | {"updated_stop": 99.0, "updated_target": 103.0, "updated_horizon": 45})))
        short = {
            "side": "SHORT",
            "prior_stop": 102.0,
            "updated_stop": 101.0,
            "prior_target": 98.0,
            "updated_target": 99.0,
            "prior_horizon": 60,
            "updated_horizon": 45,
            "prior_size": 2.0,
            "updated_size": 1.0,
        }
        self.assertTrue(_post_position_valid(action="REDUCE", **short))
        self.assertFalse(_post_position_valid(action="AUTO_REVERSE", **(long | {"updated_stop": 99.0, "updated_size": 1.0})))
        self.assertFalse(_post_position_valid(action="TIGHTEN", **(long | {"updated_stop": 97.0})))
        self.assertFalse(_post_position_valid(action="KEEP", **(long | {"updated_size": 3.0})))
        self.assertFalse(_post_position_valid(action="KEEP", **(long | {"updated_horizon": 61})))
        self.assertFalse(_post_position_valid(action="KEEP", **(long | {"updated_target": 105.0})))
        self.assertFalse(_post_position_valid(action="KEEP", **(short | {"updated_target": 97.0})))
        self.assertEqual(self.method["path_contract"]["path_switch_rule"], "A top-path switch updates belief only and cannot auto-reverse, auto-add or create a new opportunity.")

    def test_pattern_instance_is_seen_anecdotal_and_cannot_define_samples_prior_or_opportunity(self) -> None:
        fields = tuple(self.registry["object_required_fields"]["PatternInstance"])
        instance = self.synthetic["pattern_instance_case"]
        self.assertTrue(_pattern_instance_valid(instance, fields))
        for mutation in (
            {"truth_status": "VERIFIED_FACT"},
            {"outcome_visibility": "OUTCOME_FREE"},
            {"not_for_holdout_selection": False},
            {"opportunity_universe_role": "CREATES_OPPORTUNITY"},
            {"instrument_id": "BTCUSDT"},
            {"time_range": "D1_D8"},
            {"candidate_mechanism_ids": []},
            {"candidate_mechanism_ids": ["CONTINUATION", "CONTINUATION"]},
            {"candidate_mechanism_ids": ["CONTINUATION", "LLM_NEW_STORY"]},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_pattern_instance_valid(instance | mutation, fields))
        registry_case = self.registry["pattern_instance_case"]
        self.assertFalse(registry_case["provides_market_support"])
        self.assertFalse(registry_case["provides_prior"])
        self.assertEqual(registry_case["development_role"], "FORBIDDEN")
        self.assertEqual(registry_case["calibration_role"], "FORBIDDEN")
        self.assertEqual(registry_case["holdout_role"], "FORBIDDEN")
        self.assertFalse(self.synthetic["pattern_instance_use_boundary"]["known_result_adjusts_rules_or_synthetic_assertions"])

    def test_time_paths_fail_closed_for_future_missing_malformed_naive_and_pseudotypes(self) -> None:
        record = {"source_timestamp": "2026-01-01T00:00:00Z", "available_at": "2026-01-01T00:00:01Z"}
        decision = "2026-01-01T00:00:01Z"
        self.assertTrue(_record_visible(record, decision))
        mutations = (
            {"source_timestamp": "2026-01-01T00:00:02Z"},
            {"available_at": "2026-01-01T00:00:02Z"},
            {"source_timestamp": None},
            {"available_at": None},
            {"source_timestamp": "malformed"},
            {"available_at": "2026-01-01T00:00:00"},
            {"source_timestamp": True},
            {"available_at": 1},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertFalse(_record_visible(record | mutation, decision))
        self.assertFalse(_record_visible(record, "2026-01-01T00:00:01"))
        self.assertFalse(_record_visible(record, 1))

    def test_v0_4_fixed_sequence_is_not_migrated_and_general_event_timing_replaces_h12(self) -> None:
        supersedes = self.registry["supersedes"]
        self.assertEqual(supersedes["reason"], "USER_CLARIFICATION_REJECTED_FIXED_SEQUENCE_BEFORE_NEW_OUTCOME_ACCESS")
        self.assertEqual(supersedes["migration"]["fixed_d1_d8_sequence"], "NOT_MIGRATED")
        self.assertEqual(supersedes["migration"]["v4_h10"], "NOT_MIGRATED")
        self.assertEqual(supersedes["migration"]["v4_h11"], "NOT_MIGRATED")
        hypotheses = {item["hypothesis_id"]: item for item in self.registry["hypotheses"]}
        event = hypotheses["V5-H06-GENERAL_EVENT_TIMING"]
        self.assertEqual(event["replaces_v0_4_hypothesis_id"], "V4-H12-EVENT_ARRIVAL_ASSOCIATION")
        self.assertIn("does not directly provide directional alpha", event["claim"])
        variable = hypotheses["V5-H03-VARIABLE_PARTIAL_ORDER_PATH"]
        self.assertEqual(variable["comparator"], "FIXED_LENGTH_STRICT_ORDER_TEMPLATE")
        self.assertNotIn("D1-D8", variable["claim"])

    def test_all_synthetic_fixture_ids_are_unique_and_each_counterexample_family_is_present(self) -> None:
        fixtures = self.synthetic["synthetic_fixtures"]
        fixture_ids = [item["fixture_id"] for item in fixtures]
        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        expected = {
            "V5-F01-REQUIRED-MISSING",
            "V5-F03-DEPENDENCY-DUPLICATE",
            "V5-F04-PATH-COUNT-2",
            "V5-F05-PATH-COUNT-8",
            "V5-F06-PATH-COUNT-20",
            "V5-F09-HARD-FALSIFIER",
            "V5-F12-RUNTIME-MECHANISM-INJECTION",
            "V5-F13-UNCALIBRATED-PSEUDO-PROBABILITY",
            "V5-F14-MECHANISM-AS-SCENARIO",
            "V5-F16-RSI-ABSENT-SCHEDULED",
            "V5-F17-VOLUME-WICK",
            "V5-F18-UNCOVERED-FEED-SILENCE",
            "V5-F19-LATE-EVENT",
            "V5-F20-ALL-WEAK",
            "V5-F21-PATH-SWITCH",
            "V5-F22-EMPTY-ENTRY-ZONE",
            "V5-F23-PERMISSION-DENY",
            "V5-F24-PATTERN-OPPORTUNITY",
            "V5-F26-MARGIN-CAP",
            "V5-F27-NON-EQUIVALENT-MERGE",
            "V5-F29-NAIVE-TIMESTAMP",
            "V5-F30-BOOLEAN-PROBABILITY",
            "V5-F31-ACTION-OUTCOME-AS-SCENARIO",
            "V5-F32-HARD-FALSIFIER-EPISODE-SCOPE",
            "V5-F33-CAPACITY-OVERFLOW",
            "V5-F34-ZERO-RISK-CAPACITY",
            "V5-F35-POST-POSITION-HORIZON-TARGET-EXTENSION",
            "V5-F36-PRIMITIVE-COEXISTENCE",
            "V5-F37-PRIMITIVE-NON-SIMPLEX",
            "V5-F38-COMPOUND-PATH-MULTI-PRIMITIVE",
            "V5-F39-PATH-NORMALIZATION-MISSING-PARTITION-PROOF",
            "V5-F40-PRIMITIVE-WEIGHTS-AS-UTILITY-MIXTURE",
            "V5-F41-RUNTIME-POWER-SET-COMPOUND",
            "V5-F42-ARTIFACT-DIRECT-UTILITY",
            "V5-F43-ARTIFACT-RESIDUAL-INDIRECT-UTILITY",
            "V5-F44-PROOF-PATH-SET-DRIFT",
            "V5-F45-PROOF-CELL-OVERLAP",
            "V5-F46-PROOF-DOMAIN-GAP",
            "V5-F47-PROOF-RESIDUAL-MISMATCH",
            "V5-F48-PROOF-VERSION-CALIBRATION-DRIFT",
            "V5-F49-MARKET-PATH-OTHER",
            "V5-F50-PROOF-MISSING-RESIDUAL",
            "V5-F51-ARBITRARY-EXCLUSIVITY-BASIS",
            "V5-F52-PATH-REGISTRY-DEFINITION-DIGEST-DRIFT",
            "V5-F53-PROOF-AUTHORITY-RESIDUAL-ONLY-SHRINK",
            "V5-F54-PROOF-DOMAIN-CELL-RENAME",
            "V5-F55-PROOF-MARKET-CELL-SWAP",
            "V5-F56-PROOF-DOMAIN-ID-DRIFT",
            "V5-F57-PROOF-SAME-IDENTITY-CONTENT-DRIFT",
            "V5-F58-RAW-SCENARIO-MAP",
            "V5-F59-PSEUDO-CALIBRATED-BOOLEAN",
            "V5-F60-RAW-PERMISSION-STRING",
            "V5-F61-FUTURE-SCENARIO-AS-OF",
            "V5-F62-UTILITY-RECEIPT-TAMPER",
            "V5-F63-FUTURE-EVIDENCE-AVAILABLE-AT",
            "V5-F64-MISSING-EVIDENCE-AVAILABLE-AT",
            "V5-F65-RSI-NONE-EVENT-ARRIVAL",
            "V5-F66-PATH-NEVER-STOP",
            "V5-F67-PATH-FIXED-8-DAY",
            "V5-F68-PATH-HORIZON-EXTENSION",
            "V5-F69-PATH-EVENT-AFTER-HARD-FALSIFIER",
            "V5-F70-PATTERN-DUPLICATE-CANDIDATE",
            "V5-F71-EPISODE-IDENTITY-OR-PREFIX-REUSE",
            "V5-F72-CROSS-RECEIPT-EVIDENCE-ID-REPLAY",
            "V5-F73-CROSS-RECEIPT-EVIDENCE-SEMANTIC-DRIFT",
            "V5-F74-UNDERLYING-INCREMENT-RENAMED-ALIAS",
            "V5-F75-MALFORMED-TARGET-MIXED-WITH-VALID-SAME-ID",
            "V5-F76-TERMINAL-STATE-REACTIVATION",
            "V5-F77-EVIDENCE-RECEIPT-CHAIN-TAMPER",
            "V5-F78-METHOD-AUTHORITY-IN-MEMORY-SUBSTITUTION",
            "V5-F79-EMPTY-EFFECT-SUPPORT-FORGERY",
            "V5-F80-FULL-CHAIN-DECLARATION-REHASH",
            "V5-F81-NONZERO-OR-TERMINAL-EMPTY-GENESIS",
            "V5-F82-GROUP-WINNER-BATCH-SEGMENTATION",
            "V5-F83-EFFECT-ABSENT-FROM-CANONICAL-BATCH",
            "V5-F84-SELF-SIGNED-LIFECYCLE-EXPIRY",
            "V5-F85-EARLIEST-TERMINAL-LATE-ARRIVAL",
            "V5-F86-CALLER-EXPECTED-TIP-ROLLBACK-BOUNDARY",
            "V5-F87-EMPTY-TRANSITION-NOOP",
            "V5-F88-TARGET-ROUTING-ALIAS",
            "V5-F89-EQUIVALENT-TIMEZONE-IDENTITY",
            "V5-F90-RAW-SUPPORT-SATURATION-AND-WEAKER-REPLACEMENT",
            "V5-F91-EARLIER-TERMINAL-CUTOFF-COMPENSATION",
            "V5-F92-LIFECYCLE-CROSS-MECHANISM-SCOPE",
            "V5-F93-EQUAL-TIME-TERMINAL-DIGEST-GRIND",
            "V5-F94-FULL-LIFECYCLE-FACT-AUTHORITY-BOUNDARY",
            "V5-F95-RECEIPT-DECISION-TIME-CANONICAL-NONDECREASING",
            "V5-F96-IDEMPOTENCY-KEY-DECISION-CONTEXT-AND-REJECTION-CLASS",
            "V5-F97-EVIDENCE-FUTURE-THEN-CAUSALLY-VISIBLE",
            "V5-F98-LIFECYCLE-FUTURE-THEN-CAUSALLY-VISIBLE",
            "V5-F99-LIFECYCLE-IDENTITY-REPLAY-AND-CONTENT-DRIFT",
            "V5-F100-EVENT-TIME-B-LATE-PRECUTOFF-ORDINARY",
            "V5-F101-MIXED-SUPPORT-SOFT-HARD-SEGMENTATION",
            "V5-F102-SEMANTIC-TERMINAL-PROVENANCE-MERGE",
            "V5-F103-LIFECYCLE-CAPACITY-OVERFLOW-LEDGER-ROUTING",
        }
        self.assertTrue(expected.issubset(set(fixture_ids)))


if __name__ == "__main__":
    unittest.main()
