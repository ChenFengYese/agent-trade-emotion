"""Point-in-time contracts for V3.1 market associations.

The contract keeps five epistemically different relations mechanically
separate.  In particular, predictive precedence (including a Granger test) is
never represented as a structural causal effect.  Revisions are append-only:
changing the epistemic type, endpoints, or creation identity requires a new
``association_id`` rather than rewriting history.

This module is pure Domain code.  It performs no IO, estimation, model calls,
or execution.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .contracts.canonical import (
    canonical_decimal,
    self_digest,
    verify_self_digest,
)


class AssociationModelError(ValueError):
    """A V3.1 association contract failed closed."""


ASSOCIATION_TYPES = frozenset(
    {
        "OBSERVED_ASSOCIATION",
        "CONDITIONAL_DEPENDENCE",
        "PREDICTIVE_LEAD",
        "MECHANISM_HYPOTHESIS",
        "IDENTIFIED_CAUSAL_EFFECT",
    }
)

INTERPRETATION_BOUNDARIES = {
    "OBSERVED_ASSOCIATION": "ASSOCIATIONAL_NOT_CAUSAL",
    "CONDITIONAL_DEPENDENCE": "CONDITIONAL_NOT_CAUSAL",
    "PREDICTIVE_LEAD": "PREDICTIVE_NOT_STRUCTURAL_CAUSAL",
    "MECHANISM_HYPOTHESIS": "HYPOTHESIZED_NOT_IDENTIFIED",
    "IDENTIFIED_CAUSAL_EFFECT": "IDENTIFIED_UNDER_STATED_ASSUMPTIONS",
}

RELATION_TYPES = frozenset(
    {
        "EMITS",
        "TARGETS",
        "OBSERVED_BY",
        "TRANSMITS_TO",
        "DESCRIBES",
        "DERIVED_FROM",
        "CONDITIONED_BY",
        "ASSOCIATED_WITH",
        "LEADS",
        "SUPPORTS",
        "OPPOSES",
        "EXPLAINS",
        "ALTERNATIVE_TO",
        "SUPERSEDES",
        "INSTANTIATES",
        "TRIGGERS",
        "SELECTS",
        "PRODUCES",
        "EVALUATES",
    }
)

ESTIMATE_SCALES = frozenset(
    {
        "CORRELATION",
        "PARTIAL_CORRELATION",
        "REGRESSION_COEFFICIENT",
        "EFFECT_SIZE",
        "MUTUAL_INFORMATION",
        "HAZARD_RATIO",
        "ODDS_RATIO",
        "ORDINAL_SCORE",
        "NOT_ESTIMATED",
    }
)
INTERVAL_KINDS = frozenset(
    {
        "ESTIMATION_INTERVAL",
        "IDENTIFICATION_INTERVAL",
        "CREDIBLE_INTERVAL",
        "NOT_ESTIMATED",
    }
)
ASSOCIATION_STATUSES = frozenset({"ACTIVE", "SUPERSEDED", "RETIRED"})
COVERAGE_STATUSES = frozenset({"COMPLETE", "PARTIAL", "UNKNOWN"})
STABILITY_ASSESSMENTS = frozenset(
    {"UNKNOWN", "FRAGILE", "REGIME_DEPENDENT", "STABLE_WITHIN_WINDOW"}
)
LAG_DIRECTIONS = frozenset(
    {"SOURCE_LEADS_TARGET", "SYNCHRONOUS", "UNKNOWN"}
)
IDENTIFICATION_DESIGNS = frozenset(
    {
        "RANDOMIZED_EXPERIMENT",
        "NATURAL_EXPERIMENT",
        "INSTRUMENTAL_VARIABLE",
        "REGRESSION_DISCONTINUITY",
        "DIFFERENCE_IN_DIFFERENCES",
        "SYNTHETIC_CONTROL",
        "BACKDOOR_ADJUSTMENT",
        "FRONTDOOR_ADJUSTMENT",
        "STRUCTURAL_CAUSAL_MODEL",
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ASSOCIATION_FIELDS = frozenset(
    {
        "schema_version",
        "association_id",
        "revision",
        "predecessor_digest",
        "source_node_id",
        "target_node_id",
        "relation",
        "association_type",
        "method",
        "interpretation_boundary",
        "estimate_interval",
        "window",
        "lag",
        "regime",
        "coverage",
        "stability",
        "dependency_group_ids",
        "provenance",
        "validity",
        "identification_contract",
        "status",
        "created_at",
        "available_at",
        "limitations",
        "association_digest",
    }
)
_ESTIMATE_FIELDS = frozenset(
    {"lower", "point", "upper", "scale", "unit", "interval_kind"}
)
_WINDOW_FIELDS = frozenset({"start_at", "end_at", "timeframe", "sample_count"})
_LAG_FIELDS = frozenset({"value", "unit", "direction"})
_REGIME_FIELDS = frozenset({"regime_ids", "condition_refs"})
_COVERAGE_FIELDS = frozenset({"ratio", "status", "limitations"})
_STABILITY_FIELDS = frozenset(
    {"assessment", "evidence_window_count", "break_refs"}
)
_PROVENANCE_FIELDS = frozenset(
    {"source_ref", "source_digest", "observed_at", "available_at", "revision_ref"}
)
_VALIDITY_FIELDS = frozenset({"valid_from", "valid_until"})
_IDENTIFICATION_FIELDS = frozenset(
    {
        "design",
        "estimand",
        "treatment_ref",
        "outcome_ref",
        "assignment_or_instrument_ref",
        "assumptions",
        "diagnostics",
        "scope",
        "limitations",
        "identification_contract_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssociationModelError(code)
    return value.strip()


def _optional_text(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _text(value, code)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AssociationModelError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssociationModelError(code) from exc
    if result.tzinfo is None:
        raise AssociationModelError(code)
    return result.astimezone(UTC)


def _timestamp_text(value: Any, code: str) -> str:
    parsed = _timestamp(value, code)
    return parsed.isoformat().replace("+00:00", "Z")


def _integer(value: Any, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AssociationModelError(code)
    return value


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise AssociationModelError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AssociationModelError(code) from exc
    if not result.is_finite():
        raise AssociationModelError(code)
    return result


def _strings(value: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise AssociationModelError(code)
    result = list(value)
    if (
        (not allow_empty and not result)
        or any(not isinstance(item, str) or not item.strip() for item in result)
        or len(result) != len(set(result))
    ):
        raise AssociationModelError(code)
    return sorted(item.strip() for item in result)


def _mapping(value: Any, fields: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AssociationModelError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise AssociationModelError(code)
    return value


def _normalize_estimate(value: Any) -> dict[str, Any]:
    raw = _mapping(value, _ESTIMATE_FIELDS, "ASSOCIATION_ESTIMATE_SCHEMA_INVALID")
    scale = str(raw.get("scale") or "")
    interval_kind = str(raw.get("interval_kind") or "")
    if scale not in ESTIMATE_SCALES or interval_kind not in INTERVAL_KINDS:
        raise AssociationModelError("ASSOCIATION_ESTIMATE_TYPE_INVALID")
    unit = _text(raw.get("unit"), "ASSOCIATION_ESTIMATE_UNIT_INVALID")
    numeric = (raw.get("lower"), raw.get("point"), raw.get("upper"))
    if scale == "NOT_ESTIMATED" or interval_kind == "NOT_ESTIMATED":
        if scale != "NOT_ESTIMATED" or interval_kind != "NOT_ESTIMATED":
            raise AssociationModelError("ASSOCIATION_ESTIMATE_ABSENCE_INCONSISTENT")
        if any(item is not None for item in numeric) or unit != "NONE":
            raise AssociationModelError("ASSOCIATION_ESTIMATE_ABSENCE_INVALID")
        return {
            "lower": None,
            "point": None,
            "upper": None,
            "scale": scale,
            "unit": unit,
            "interval_kind": interval_kind,
        }
    if any(item is None for item in numeric):
        raise AssociationModelError("ASSOCIATION_ESTIMATE_INTERVAL_REQUIRED")
    lower, point, upper = (
        _decimal(raw.get("lower"), "ASSOCIATION_ESTIMATE_NUMBER_INVALID"),
        _decimal(raw.get("point"), "ASSOCIATION_ESTIMATE_NUMBER_INVALID"),
        _decimal(raw.get("upper"), "ASSOCIATION_ESTIMATE_NUMBER_INVALID"),
    )
    if lower > point or point > upper:
        raise AssociationModelError("ASSOCIATION_ESTIMATE_INTERVAL_INVALID")
    if scale in {"CORRELATION", "PARTIAL_CORRELATION"} and (
        lower < Decimal("-1") or upper > Decimal("1")
    ):
        raise AssociationModelError("ASSOCIATION_CORRELATION_RANGE_INVALID")
    return {
        "lower": canonical_decimal(lower),
        "point": canonical_decimal(point),
        "upper": canonical_decimal(upper),
        "scale": scale,
        "unit": unit,
        "interval_kind": interval_kind,
    }


def _normalize_window(value: Any, *, available_at: datetime) -> dict[str, Any]:
    raw = _mapping(value, _WINDOW_FIELDS, "ASSOCIATION_WINDOW_SCHEMA_INVALID")
    start_at = _timestamp(raw.get("start_at"), "ASSOCIATION_WINDOW_START_INVALID")
    end_at = _timestamp(raw.get("end_at"), "ASSOCIATION_WINDOW_END_INVALID")
    if start_at > end_at:
        raise AssociationModelError("ASSOCIATION_WINDOW_ORDER_INVALID")
    if end_at > available_at:
        raise AssociationModelError("ASSOCIATION_WINDOW_NOT_PIT")
    return {
        "start_at": start_at.isoformat().replace("+00:00", "Z"),
        "end_at": end_at.isoformat().replace("+00:00", "Z"),
        "timeframe": _text(raw.get("timeframe"), "ASSOCIATION_TIMEFRAME_INVALID"),
        "sample_count": _integer(
            raw.get("sample_count"), "ASSOCIATION_SAMPLE_COUNT_INVALID", minimum=1
        ),
    }


def _normalize_lag(value: Any, *, association_type: str) -> dict[str, Any]:
    raw = _mapping(value, _LAG_FIELDS, "ASSOCIATION_LAG_SCHEMA_INVALID")
    lag_value = _integer(raw.get("value"), "ASSOCIATION_LAG_VALUE_INVALID")
    lag_unit = _text(raw.get("unit"), "ASSOCIATION_LAG_UNIT_INVALID")
    direction = str(raw.get("direction") or "")
    if direction not in LAG_DIRECTIONS:
        raise AssociationModelError("ASSOCIATION_LAG_DIRECTION_INVALID")
    if association_type == "PREDICTIVE_LEAD" and (
        lag_value == 0 or direction != "SOURCE_LEADS_TARGET"
    ):
        raise AssociationModelError("PREDICTIVE_LEAD_REQUIRES_POSITIVE_SOURCE_LAG")
    if direction == "SYNCHRONOUS" and lag_value != 0:
        raise AssociationModelError("SYNCHRONOUS_LAG_MUST_BE_ZERO")
    return {"value": lag_value, "unit": lag_unit, "direction": direction}


def _normalize_regime(value: Any) -> dict[str, Any]:
    raw = _mapping(value, _REGIME_FIELDS, "ASSOCIATION_REGIME_SCHEMA_INVALID")
    return {
        "regime_ids": _strings(
            raw.get("regime_ids"), "ASSOCIATION_REGIME_IDS_INVALID", allow_empty=True
        ),
        "condition_refs": _strings(
            raw.get("condition_refs"),
            "ASSOCIATION_CONDITION_REFS_INVALID",
            allow_empty=True,
        ),
    }


def _normalize_coverage(value: Any) -> dict[str, Any]:
    raw = _mapping(value, _COVERAGE_FIELDS, "ASSOCIATION_COVERAGE_SCHEMA_INVALID")
    ratio = _decimal(raw.get("ratio"), "ASSOCIATION_COVERAGE_RATIO_INVALID")
    status = str(raw.get("status") or "")
    if ratio < 0 or ratio > 1 or status not in COVERAGE_STATUSES:
        raise AssociationModelError("ASSOCIATION_COVERAGE_INVALID")
    if (status == "COMPLETE") != (ratio == 1):
        raise AssociationModelError("ASSOCIATION_COVERAGE_STATUS_INCONSISTENT")
    if status == "UNKNOWN" and ratio != 0:
        raise AssociationModelError("UNKNOWN_COVERAGE_RATIO_MUST_BE_ZERO")
    return {
        "ratio": canonical_decimal(ratio),
        "status": status,
        "limitations": _strings(
            raw.get("limitations"),
            "ASSOCIATION_COVERAGE_LIMITATIONS_INVALID",
            allow_empty=status == "COMPLETE",
        ),
    }


def _normalize_stability(value: Any) -> dict[str, Any]:
    raw = _mapping(value, _STABILITY_FIELDS, "ASSOCIATION_STABILITY_SCHEMA_INVALID")
    assessment = str(raw.get("assessment") or "")
    if assessment not in STABILITY_ASSESSMENTS:
        raise AssociationModelError("ASSOCIATION_STABILITY_INVALID")
    window_count = _integer(
        raw.get("evidence_window_count"),
        "ASSOCIATION_STABILITY_WINDOW_COUNT_INVALID",
    )
    if assessment != "UNKNOWN" and window_count == 0:
        raise AssociationModelError("ASSOCIATION_STABILITY_EVIDENCE_REQUIRED")
    return {
        "assessment": assessment,
        "evidence_window_count": window_count,
        "break_refs": _strings(
            raw.get("break_refs"),
            "ASSOCIATION_STABILITY_BREAK_REFS_INVALID",
            allow_empty=True,
        ),
    }


def _normalize_provenance(value: Any, *, available_at: datetime) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise AssociationModelError("ASSOCIATION_PROVENANCE_INVALID")
    result: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for item in value:
        raw = _mapping(
            item, _PROVENANCE_FIELDS, "ASSOCIATION_PROVENANCE_SCHEMA_INVALID"
        )
        observed_at = _timestamp(
            raw.get("observed_at"), "ASSOCIATION_PROVENANCE_OBSERVED_AT_INVALID"
        )
        source_available_at = _timestamp(
            raw.get("available_at"), "ASSOCIATION_PROVENANCE_AVAILABLE_AT_INVALID"
        )
        if observed_at > source_available_at or source_available_at > available_at:
            raise AssociationModelError("ASSOCIATION_PROVENANCE_NOT_PIT")
        source_ref = _text(
            raw.get("source_ref"), "ASSOCIATION_PROVENANCE_SOURCE_REF_INVALID"
        )
        source_digest = _digest(
            raw.get("source_digest"), "ASSOCIATION_PROVENANCE_DIGEST_INVALID"
        )
        identity = (source_ref, source_digest)
        if identity in identities:
            raise AssociationModelError("ASSOCIATION_PROVENANCE_DUPLICATE")
        identities.add(identity)
        result.append(
            {
                "source_ref": source_ref,
                "source_digest": source_digest,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "available_at": source_available_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "revision_ref": _text(
                    raw.get("revision_ref"),
                    "ASSOCIATION_PROVENANCE_REVISION_REF_INVALID",
                ),
            }
        )
    return sorted(result, key=lambda item: (item["available_at"], item["source_ref"]))


def _normalize_validity(value: Any, *, available_at: datetime) -> dict[str, Any]:
    raw = _mapping(value, _VALIDITY_FIELDS, "ASSOCIATION_VALIDITY_SCHEMA_INVALID")
    valid_from = _timestamp(
        raw.get("valid_from"), "ASSOCIATION_VALID_FROM_INVALID"
    )
    valid_until_raw = raw.get("valid_until")
    valid_until = (
        None
        if valid_until_raw is None
        else _timestamp(valid_until_raw, "ASSOCIATION_VALID_UNTIL_INVALID")
    )
    # Validity time and knowledge time are distinct.  Retrospective estimates
    # may apply to a window that started before the estimate became available.
    if valid_until is not None and valid_until < valid_from:
        raise AssociationModelError("ASSOCIATION_VALIDITY_INTERVAL_INVALID")
    return {
        "valid_from": valid_from.isoformat().replace("+00:00", "Z"),
        "valid_until": (
            None
            if valid_until is None
            else valid_until.isoformat().replace("+00:00", "Z")
        ),
    }


def build_identification_contract(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and self-digest a stated causal-identification contract."""

    if not isinstance(candidate, Mapping) or set(candidate) not in {
        _IDENTIFICATION_FIELDS,
        _IDENTIFICATION_FIELDS - {"identification_contract_digest"},
    }:
        raise AssociationModelError("IDENTIFICATION_CONTRACT_SCHEMA_INVALID")
    design = str(candidate.get("design") or "")
    if design not in IDENTIFICATION_DESIGNS:
        raise AssociationModelError("IDENTIFICATION_DESIGN_INVALID")
    normalized = {
        "design": design,
        "estimand": _text(candidate.get("estimand"), "IDENTIFICATION_ESTIMAND_INVALID"),
        "treatment_ref": _text(
            candidate.get("treatment_ref"), "IDENTIFICATION_TREATMENT_INVALID"
        ),
        "outcome_ref": _text(
            candidate.get("outcome_ref"), "IDENTIFICATION_OUTCOME_INVALID"
        ),
        "assignment_or_instrument_ref": _text(
            candidate.get("assignment_or_instrument_ref"),
            "IDENTIFICATION_ASSIGNMENT_INVALID",
        ),
        "assumptions": _strings(
            candidate.get("assumptions"), "IDENTIFICATION_ASSUMPTIONS_INVALID"
        ),
        "diagnostics": _strings(
            candidate.get("diagnostics"), "IDENTIFICATION_DIAGNOSTICS_INVALID"
        ),
        "scope": _text(candidate.get("scope"), "IDENTIFICATION_SCOPE_INVALID"),
        "limitations": _strings(
            candidate.get("limitations"), "IDENTIFICATION_LIMITATIONS_INVALID"
        ),
    }
    result = self_digest(normalized, "identification_contract_digest")
    supplied = candidate.get("identification_contract_digest")
    if supplied is not None and supplied != result["identification_contract_digest"]:
        raise AssociationModelError("IDENTIFICATION_CONTRACT_DIGEST_MISMATCH")
    return result


def build_association_revision(
    candidate: Mapping[str, Any],
    *,
    decision_at: str,
    prior_revision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one immutable, point-in-time association revision.

    A later revision may update evidence, estimates, regime, or validity, but it
    may not change identity, endpoints, relation, epistemic type, or creation
    time.  This is the mechanical barrier against upgrading a correlation or a
    Granger-style lead into a causal effect by relabelling it in place.
    """

    if not isinstance(candidate, Mapping) or set(candidate) not in {
        _ASSOCIATION_FIELDS,
        _ASSOCIATION_FIELDS - {"association_digest"},
    }:
        raise AssociationModelError("ASSOCIATION_SCHEMA_INVALID")
    if candidate.get("schema_version") != "V3_1_ASSOCIATION_REVISION":
        raise AssociationModelError("ASSOCIATION_SCHEMA_VERSION_INVALID")
    cutoff = _timestamp(decision_at, "ASSOCIATION_DECISION_AT_INVALID")
    created_at = _timestamp(candidate.get("created_at"), "ASSOCIATION_CREATED_AT_INVALID")
    available_at = _timestamp(
        candidate.get("available_at"), "ASSOCIATION_AVAILABLE_AT_INVALID"
    )
    if created_at > available_at or available_at > cutoff:
        raise AssociationModelError("ASSOCIATION_NOT_POINT_IN_TIME")

    association_type = str(candidate.get("association_type") or "")
    if association_type not in ASSOCIATION_TYPES:
        raise AssociationModelError("ASSOCIATION_TYPE_INVALID")
    interpretation_boundary = str(candidate.get("interpretation_boundary") or "")
    if interpretation_boundary != INTERPRETATION_BOUNDARIES[association_type]:
        raise AssociationModelError("ASSOCIATION_INTERPRETATION_BOUNDARY_INVALID")
    method = _text(candidate.get("method"), "ASSOCIATION_METHOD_INVALID")
    if "GRANGER" in method.upper() and association_type != "PREDICTIVE_LEAD":
        raise AssociationModelError("GRANGER_MUST_BE_PREDICTIVE_NOT_CAUSAL")
    relation = str(candidate.get("relation") or "")
    if relation not in RELATION_TYPES:
        raise AssociationModelError("ASSOCIATION_RELATION_INVALID")

    estimate = _normalize_estimate(candidate.get("estimate_interval"))
    identification_raw = candidate.get("identification_contract")
    if association_type == "IDENTIFIED_CAUSAL_EFFECT":
        if identification_raw is None or estimate["scale"] == "NOT_ESTIMATED":
            raise AssociationModelError("IDENTIFIED_CAUSAL_CONTRACT_AND_ESTIMATE_REQUIRED")
        identification = build_identification_contract(identification_raw)
    else:
        if identification_raw is not None:
            raise AssociationModelError("NONCAUSAL_ASSOCIATION_FORBIDS_IDENTIFICATION_CONTRACT")
        identification = None

    revision = _integer(
        candidate.get("revision"), "ASSOCIATION_REVISION_INVALID", minimum=1
    )
    predecessor_digest = candidate.get("predecessor_digest")
    immutable = (
        "association_id",
        "source_node_id",
        "target_node_id",
        "relation",
        "association_type",
    )
    if prior_revision is None:
        if revision != 1 or predecessor_digest is not None:
            raise AssociationModelError("ASSOCIATION_INITIAL_REVISION_INVALID")
    else:
        try:
            prior_digest = verify_self_digest(prior_revision, "association_digest")
        except ValueError as exc:
            raise AssociationModelError("ASSOCIATION_PRIOR_DIGEST_INVALID") from exc
        if revision != prior_revision.get("revision", 0) + 1:
            raise AssociationModelError("ASSOCIATION_REVISION_NOT_CONTIGUOUS")
        if predecessor_digest != prior_digest:
            raise AssociationModelError("ASSOCIATION_PREDECESSOR_DIGEST_INVALID")
        if any(candidate.get(field) != prior_revision.get(field) for field in immutable):
            raise AssociationModelError("ASSOCIATION_IDENTITY_OR_TYPE_REWRITE_FORBIDDEN")
        if candidate.get("created_at") != prior_revision.get("created_at"):
            raise AssociationModelError("ASSOCIATION_CREATION_TIME_REWRITE_FORBIDDEN")
        prior_available = _timestamp(
            prior_revision.get("available_at"), "ASSOCIATION_PRIOR_AVAILABLE_AT_INVALID"
        )
        if available_at <= prior_available:
            raise AssociationModelError("ASSOCIATION_REVISION_TIME_NOT_MONOTONIC")
        if prior_revision.get("status") in {"SUPERSEDED", "RETIRED"}:
            raise AssociationModelError("ASSOCIATION_TERMINAL_REVISION_FORBIDDEN")

    status = str(candidate.get("status") or "")
    if status not in ASSOCIATION_STATUSES:
        raise AssociationModelError("ASSOCIATION_STATUS_INVALID")
    association_id = _text(
        candidate.get("association_id"), "ASSOCIATION_ID_INVALID"
    )
    source_node_id = _text(
        candidate.get("source_node_id"), "ASSOCIATION_SOURCE_NODE_INVALID"
    )
    target_node_id = _text(
        candidate.get("target_node_id"), "ASSOCIATION_TARGET_NODE_INVALID"
    )
    if source_node_id == target_node_id:
        raise AssociationModelError("ASSOCIATION_SELF_EDGE_FORBIDDEN")
    normalized = {
        "schema_version": "V3_1_ASSOCIATION_REVISION",
        "association_id": association_id,
        "revision": revision,
        "predecessor_digest": (
            None
            if predecessor_digest is None
            else _digest(predecessor_digest, "ASSOCIATION_PREDECESSOR_DIGEST_INVALID")
        ),
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relation": relation,
        "association_type": association_type,
        "method": method,
        "interpretation_boundary": interpretation_boundary,
        "estimate_interval": estimate,
        "window": _normalize_window(candidate.get("window"), available_at=available_at),
        "lag": _normalize_lag(candidate.get("lag"), association_type=association_type),
        "regime": _normalize_regime(candidate.get("regime")),
        "coverage": _normalize_coverage(candidate.get("coverage")),
        "stability": _normalize_stability(candidate.get("stability")),
        "dependency_group_ids": _strings(
            candidate.get("dependency_group_ids"),
            "ASSOCIATION_DEPENDENCY_GROUPS_INVALID",
        ),
        "provenance": _normalize_provenance(
            candidate.get("provenance"), available_at=available_at
        ),
        "validity": _normalize_validity(
            candidate.get("validity"), available_at=available_at
        ),
        "identification_contract": identification,
        "status": status,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "available_at": available_at.isoformat().replace("+00:00", "Z"),
        "limitations": _strings(
            candidate.get("limitations"), "ASSOCIATION_LIMITATIONS_INVALID"
        ),
    }
    result = self_digest(normalized, "association_digest")
    supplied = candidate.get("association_digest")
    if supplied is not None and supplied != result["association_digest"]:
        raise AssociationModelError("ASSOCIATION_DIGEST_MISMATCH")
    return result


def verify_association_revision(
    document: Mapping[str, Any],
    *,
    decision_at: str,
    prior_revision: Mapping[str, Any] | None = None,
) -> str:
    """Verify schema, semantics, PIT boundary, lineage, and self digest."""

    normalized = build_association_revision(
        document, decision_at=decision_at, prior_revision=prior_revision
    )
    try:
        supplied = verify_self_digest(document, "association_digest")
    except ValueError as exc:
        raise AssociationModelError("ASSOCIATION_DIGEST_INVALID") from exc
    if normalized["association_digest"] != supplied:
        raise AssociationModelError("ASSOCIATION_CANONICAL_FORM_INVALID")
    return supplied
