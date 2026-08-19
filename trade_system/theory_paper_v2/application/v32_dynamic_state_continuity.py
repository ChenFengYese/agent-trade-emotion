"""Pure application composition for V3.2 dynamic-state continuity.

The V3.2 domain document intentionally carries previous-tier and previous-
expiry claims so an Agent can propose a revision.  Those claims are not an
authority: this composition compares them with the fully verified, durable
previous document and with the predecessor digest supplied by the controller.

The PIT, availability, and graph registry inputs are projections produced
after upstream public-source validation.  This module reconstructs evidence
availability from the fully verified public analysis bundle, closes every
evidence identity over all graph dependency groups, and treats those finite
sets as the only admissible source/dependency claims.  It performs no file,
clock, network, Agent, authority, or execution operation and does not persist
the returned receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import self_digest, verify_self_digest
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    NON_DIRECTIONAL_MARKET_REGIMES,
    REGIME_FEATURE_REQUIRED_COMBINATIONS,
    REGIME_FEATURE_REQUIRED_OBSERVABLE_FAMILIES,
    V32DynamicResearchError,
    verify_v32_dynamic_research_state_v1,
)
from .v32_public_evidence_port import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    INFORMATION_EVENT_DIGEST_FIELD,
    V32PublicEvidenceVerificationError,
    V32PublicEvidenceVerifierPort,
)


class V32DynamicStateContinuityError(ValueError):
    """A current V3.2 state was not grounded in durable prior/PIT state."""


SCHEMA_VERSION = "1.0.0"
PIT_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_pit_evidence_registry_v1"
GRAPH_REGISTRY_SCHEMA_ID = (
    "theory_paper_v32_verified_graph_dependency_registry_v1"
)
PIT_REGISTRY_DIGEST_FIELD = "pit_evidence_registry_digest"
GRAPH_REGISTRY_DIGEST_FIELD = "graph_dependency_registry_digest"
PIT_AVAILABILITY_REGISTRY_SCHEMA_ID = (
    "theory_paper_v32_verified_pit_evidence_availability_registry_v1"
)
PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD = (
    "pit_evidence_availability_registry_digest"
)
RECEIPT_SCHEMA_ID = "theory_paper_v32_dynamic_state_continuity_receipt_v1"
RECEIPT_DIGEST_FIELD = "dynamic_state_continuity_receipt_digest"
CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES = (
    NON_DIRECTIONAL_MARKET_REGIMES | frozenset({"TRANSITION"})
)
_PROVENANCE_ONLY_DEPENDENCY_PREFIXES = frozenset({"PROJECTION", "VENUE"})
_REQUEST_DEPENDENCY_PREFIX = "REQUEST"
_OBSERVABLE_FAMILY_DEPENDENCY_PREFIX = "OBSERVABLE_FAMILY"
_DIRECTIONAL_ADMISSIBLE_OBSERVABLE_FAMILY_GROUPS = frozenset(
    {
        "OBSERVABLE_FAMILY:PRICE_ACTION",
        "OBSERVABLE_FAMILY:POSITIONING",
        "OBSERVABLE_FAMILY:FUNDING_CROWDING",
        "OBSERVABLE_FAMILY:ORDERBOOK_LIQUIDITY",
        "OBSERVABLE_FAMILY:TRADE_FLOW",
    }
)

_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "current_state_digest",
        "durable_previous_state_digest",
        "pit_evidence_registry_digest",
        "pit_evidence_availability_registry_digest",
        "durable_previous_pit_evidence_availability_registry_digest",
        "public_market_analysis_bundle_digest",
        "graph_dependency_registry_digest",
        "continued_hypothesis_ids",
        "new_hypothesis_ids",
        "renewed_hypothesis_ids",
        "retired_hypothesis_ids",
        "continued_zone_ids",
        "new_zone_ids",
        "renewed_zone_ids",
        "retired_zone_ids",
        "continued_path_modifier_ids",
        "new_path_modifier_ids",
        "renewed_path_modifier_ids",
        "retired_path_modifier_ids",
        "fresh_lifecycle_evidence_refs",
        "lifecycle_reanalysis_required",
        "lifecycle_reanalysis_reasons",
        "verified_path_modifier_ids",
        "continuity_policy",
        "renewal_policy",
        "retirement_policy",
        "modifier_registry_policy",
        "evidence_dependency_closure_policy",
        "freshness_policy",
        "complete_registry_policy",
        "source_scope",
        "external_execution_authority",
        "executable",
        RECEIPT_DIGEST_FIELD,
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HYPOTHESIS_IDENTITY_FIELDS = (
    "hypothesis_type",
    "direction",
    "scope",
    "regime_scope",
    "mechanism",
    "horizon_seconds",
    "lineage_id",
    "lineage_revision",
    "predecessor_id",
    "predecessor_fingerprint",
    "semantic_fingerprint",
)
_ZONE_IDENTITY_FIELDS = (
    "instrument",
    "role",
    "lower_bound",
    "upper_bound",
    "construction_method",
    "created_at",
    "available_at",
    "expires_at",
    "lineage_id",
    "lineage_revision",
    "predecessor_id",
    "predecessor_fingerprint",
    "semantic_fingerprint",
)
_MODIFIER_IDENTITY_FIELDS = (
    "modifier_type",
    "scope",
    "effect",
    "mechanism",
    "source_refs",
    "dependency_groups",
    "affected_hypothesis_ids",
    "affected_zone_ids",
    "affected_action_kinds",
    "conditions",
    "trigger_effect",
    "protection_effect",
    "invalidators",
    "created_at",
    "available_at",
    "expires_at",
    "lineage_id",
    "lineage_revision",
    "predecessor_id",
    "predecessor_fingerprint",
    "semantic_fingerprint",
)
_ZONE_PIT_FIELDS = (
    "evidence_refs",
    "touch_refs",
    "reaction_refs",
    "volume_at_price_refs",
    "dwell_time_refs",
    "round_number_refs",
    "orderbook_flow_refs",
    "leverage_refs",
    "options_refs",
)
_HYPOTHESIS_PIT_FIELDS = (
    "source_refs",
    "supporting_refs",
    "opposing_refs",
    "tier_update_refs",
    "renewal_evidence_refs",
)
_BASE_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "members",
        "upstream_schema_id",
        "upstream_digest_field",
        "upstream_semantic_digest",
        "full_verification_receipt_digest",
        "source_scope",
        "external_execution_authority",
        "executable",
    }
)
_GRAPH_REGISTRY_FIELDS = _BASE_REGISTRY_FIELDS | {
    "evidence_dependency_policy",
    "evidence_dependency_closure",
}
_GRAPH_EVIDENCE_CLOSURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "evidence_digest",
        "evidence_refs",
        "node_ids",
        "association_ids",
        "dependency_group_ids",
        "evidence_dependency_closure_digest",
    }
)
_GRAPH_EVIDENCE_CLOSURE_POLICY = {
    "identity_key": "PAYLOAD_DIGEST",
    "node_scope": "LATEST_NODE_REVISIONS_ONLY",
    "association_scope": "ALL_LATEST_INCIDENT_ASSOCIATIONS",
    "dependency_operation": "UNION_NO_CALLER_SUBSETS",
    "same_digest_split_allowed": False,
}
_AVAILABILITY_ENTRY_FIELDS = frozenset({"evidence_ref", "available_at"})
_AVAILABILITY_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "entries",
        "pit_evidence_registry_digest",
        "public_market_analysis_bundle_digest",
        "availability_policy",
        "source_scope",
        "external_execution_authority",
        "executable",
        PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    }
)
_AVAILABILITY_POLICY = (
    "DETERMINISTIC_FROM_FULLY_VERIFIED_PUBLIC_MARKET_ANALYSIS_BUNDLE_"
    "EXACT_CURRENT_PIT_DIGEST_COVERAGE_FIRST_AVAILABLE_AT"
)
_PIT_DATUM_DIGEST_FIELD = "pit_datum_digest"
_AXIS_EVIDENCE_DIGEST_FIELD = "axis_source_evidence_digest"


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32DynamicStateContinuityError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32DynamicStateContinuityError(code)
    return value


def _time(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DynamicStateContinuityError(code) from exc
    if parsed.tzinfo is None:
        raise V32DynamicStateContinuityError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32DynamicStateContinuityError(code)
    return parsed.astimezone(UTC)


def _members(value: Any, code: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32DynamicStateContinuityError(code)
    members = tuple(_text(item, code) for item in value)
    if not members or list(members) != sorted(members) or len(members) != len(
        set(members)
    ):
        raise V32DynamicStateContinuityError(code)
    return members


def _verify_current_cycle_registry(
    registry: Mapping[str, Any],
    *,
    schema_id: str,
    digest_field: str,
    run_id: str,
    cycle_index: int,
    as_of: str,
    code_prefix: str,
    allow_as_of_not_after: bool = False,
) -> tuple[str, frozenset[str]]:
    expected_fields = _BASE_REGISTRY_FIELDS | {digest_field}
    if not isinstance(registry, Mapping) or set(registry) != expected_fields:
        raise V32DynamicStateContinuityError(f"{code_prefix}_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(registry, digest_field)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32DynamicStateContinuityError(
            f"{code_prefix}_DIGEST_INVALID"
        ) from exc
    if (
        registry.get("schema_id") != schema_id
        or registry.get("schema_version") != SCHEMA_VERSION
        or registry.get("run_id") != run_id
        or registry.get("cycle_index") != cycle_index
        or (
            _time(registry.get("as_of"), f"{code_prefix}_TIME_INVALID")
            > _time(as_of, f"{code_prefix}_TIME_INVALID")
            if allow_as_of_not_after
            else registry.get("as_of") != as_of
        )
        or registry.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or registry.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or registry.get("executable") is not False
    ):
        raise V32DynamicStateContinuityError(
            f"{code_prefix}_CURRENT_CYCLE_BINDING_INVALID"
        )
    _text(registry.get("upstream_schema_id"), f"{code_prefix}_UPSTREAM_INVALID")
    _text(
        registry.get("upstream_digest_field"),
        f"{code_prefix}_UPSTREAM_INVALID",
    )
    _digest(
        registry.get("upstream_semantic_digest"),
        f"{code_prefix}_UPSTREAM_INVALID",
    )
    _digest(
        registry.get("full_verification_receipt_digest"),
        f"{code_prefix}_VERIFICATION_RECEIPT_INVALID",
    )
    members = _members(registry.get("members"), f"{code_prefix}_MEMBERS_INVALID")
    return supplied, frozenset(members)


def _verify_graph_registry(
    registry: Mapping[str, Any],
    *,
    run_id: str,
    cycle_index: int,
    as_of: str,
) -> tuple[str, frozenset[str], dict[str, frozenset[str]]]:
    code = "V32_CONTINUITY_GRAPH_REGISTRY"
    expected_fields = _GRAPH_REGISTRY_FIELDS | {GRAPH_REGISTRY_DIGEST_FIELD}
    if not isinstance(registry, Mapping) or set(registry) != expected_fields:
        raise V32DynamicStateContinuityError(f"{code}_DOCUMENT_INVALID")
    # Reuse the complete base-registry validation without weakening the graph
    # schema's two additional closure fields.
    base = {
        key: value
        for key, value in registry.items()
        if key not in {"evidence_dependency_policy", "evidence_dependency_closure"}
    }
    base_digest = base.pop(GRAPH_REGISTRY_DIGEST_FIELD)
    # The base projection does not carry an independently meaningful digest;
    # validate its fields directly and validate the actual graph digest below.
    if (
        base.get("schema_id") != GRAPH_REGISTRY_SCHEMA_ID
        or base.get("schema_version") != SCHEMA_VERSION
        or base.get("run_id") != run_id
        or base.get("cycle_index") != cycle_index
        or base.get("as_of") != as_of
        or base.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or base.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or base.get("executable") is not False
    ):
        raise V32DynamicStateContinuityError(f"{code}_CURRENT_CYCLE_BINDING_INVALID")
    _text(base.get("upstream_schema_id"), f"{code}_UPSTREAM_INVALID")
    _text(base.get("upstream_digest_field"), f"{code}_UPSTREAM_INVALID")
    _digest(base.get("upstream_semantic_digest"), f"{code}_UPSTREAM_INVALID")
    _digest(
        base.get("full_verification_receipt_digest"),
        f"{code}_VERIFICATION_RECEIPT_INVALID",
    )
    members = frozenset(_members(base.get("members"), f"{code}_MEMBERS_INVALID"))
    if registry.get("evidence_dependency_policy") != _GRAPH_EVIDENCE_CLOSURE_POLICY:
        raise V32DynamicStateContinuityError(f"{code}_EVIDENCE_POLICY_INVALID")
    closure = registry.get("evidence_dependency_closure")
    if not isinstance(closure, Sequence) or isinstance(closure, (str, bytes)):
        raise V32DynamicStateContinuityError(f"{code}_EVIDENCE_CLOSURE_INVALID")
    digest_order: list[str] = []
    lookup: dict[str, frozenset[str]] = {}
    closure_member_union: set[str] = set()
    for row in closure:
        if (
            not isinstance(row, Mapping)
            or set(row) != _GRAPH_EVIDENCE_CLOSURE_FIELDS
            or row.get("schema_id")
            != "theory_paper_v32_evidence_dependency_closure_v1"
            or row.get("schema_version") != SCHEMA_VERSION
        ):
            raise V32DynamicStateContinuityError(
                f"{code}_EVIDENCE_CLOSURE_INVALID"
            )
        evidence_digest = _digest(
            row.get("evidence_digest"), f"{code}_EVIDENCE_CLOSURE_INVALID"
        )
        for field, allow_empty in (
            ("evidence_refs", False),
            ("node_ids", False),
            ("association_ids", True),
            ("dependency_group_ids", False),
        ):
            values = row.get(field)
            if (
                not isinstance(values, list)
                or (not allow_empty and not values)
                or values != sorted(set(values))
                or any(not isinstance(item, str) or not item for item in values)
            ):
                raise V32DynamicStateContinuityError(
                    f"{code}_EVIDENCE_CLOSURE_INVALID"
                )
        try:
            verify_self_digest(row, "evidence_dependency_closure_digest")
        except (KeyError, TypeError, ValueError) as exc:
            raise V32DynamicStateContinuityError(
                f"{code}_EVIDENCE_CLOSURE_INVALID"
            ) from exc
        digest_order.append(evidence_digest)
        groups = frozenset(str(item) for item in row["dependency_group_ids"])
        closure_member_union.update(groups)
        for identity in [evidence_digest, *row["evidence_refs"]]:
            if identity in lookup:
                # Even an identical group set under a duplicate identity is
                # forbidden: one evidence identity has exactly one closure row.
                raise V32DynamicStateContinuityError(
                    f"{code}_EVIDENCE_CLOSURE_SPLIT_FORBIDDEN"
                )
            lookup[identity] = groups
    if (
        not closure
        or digest_order != sorted(set(digest_order))
        or closure_member_union != set(members)
    ):
        raise V32DynamicStateContinuityError(f"{code}_EVIDENCE_CLOSURE_INVALID")
    try:
        supplied = verify_self_digest(registry, GRAPH_REGISTRY_DIGEST_FIELD)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32DynamicStateContinuityError(f"{code}_DIGEST_INVALID") from exc
    if supplied != base_digest:
        # ``base_digest`` was copied from the exact document before removal;
        # this explicit equality documents that no alternate digest was used.
        raise V32DynamicStateContinuityError(f"{code}_DIGEST_INVALID")
    return supplied, members, lookup


def _analysis_availability_entries(
    analysis_bundle: Mapping[str, Any],
) -> list[dict[str, str]]:
    availability: dict[str, str] = {}
    for collection, digest_field in (
        ("information_events", INFORMATION_EVENT_DIGEST_FIELD),
        ("datums", _PIT_DATUM_DIGEST_FIELD),
        ("axis_source_evidence", _AXIS_EVIDENCE_DIGEST_FIELD),
    ):
        for row in analysis_bundle[collection]:
            evidence_ref = _text(
                row[digest_field], "V32_CONTINUITY_AVAILABILITY_SOURCE_INVALID"
            )
            available_at = str(row["available_at"])
            _time(available_at, "V32_CONTINUITY_AVAILABILITY_SOURCE_INVALID")
            if evidence_ref in availability and availability[evidence_ref] != available_at:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_AVAILABILITY_SOURCE_COLLISION"
                )
            availability[evidence_ref] = available_at
    bundle_digest = _digest(
        analysis_bundle[ANALYSIS_BUNDLE_DIGEST_FIELD],
        "V32_CONTINUITY_AVAILABILITY_SOURCE_INVALID",
    )
    availability[bundle_digest] = str(analysis_bundle["available_at"])
    return [
        {"evidence_ref": evidence_ref, "available_at": availability[evidence_ref]}
        for evidence_ref in sorted(availability)
    ]


def build_v32_verified_pit_evidence_availability_registry_v1(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    public_market_analysis_bundle: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive immutable first-availability times from a verified source bundle."""

    try:
        analysis_digest = public_evidence_verifier.verify_public_market_analysis_bundle(
            public_market_analysis_bundle
        )
    except V32PublicEvidenceVerificationError as exc:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_ANALYSIS_BUNDLE_INVALID"
        ) from exc
    run_id = str(public_market_analysis_bundle["run_id"])
    cycle_index = public_market_analysis_bundle["cycle_index"]
    as_of = str(pit_evidence_registry.get("as_of"))
    pit_digest, pit_members = _verify_current_cycle_registry(
        pit_evidence_registry,
        schema_id=PIT_REGISTRY_SCHEMA_ID,
        digest_field=PIT_REGISTRY_DIGEST_FIELD,
        run_id=run_id,
        cycle_index=cycle_index,
        as_of=as_of,
        code_prefix="V32_CONTINUITY_AVAILABILITY_PIT_REGISTRY",
    )
    if (
        public_market_analysis_bundle.get("as_of") is None
        or public_market_analysis_bundle.get("run_id") != run_id
        or public_market_analysis_bundle.get("cycle_index") != cycle_index
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_SOURCE_BINDING_INVALID"
        )
    entries = _analysis_availability_entries(public_market_analysis_bundle)
    if {row["evidence_ref"] for row in entries} != set(pit_members):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_PIT_COVERAGE_INVALID"
        )
    cutoff = _time(as_of, "V32_CONTINUITY_AVAILABILITY_TIME_INVALID")
    if any(
        _time(row["available_at"], "V32_CONTINUITY_AVAILABILITY_TIME_INVALID")
        > cutoff
        for row in entries
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_FUTURE_EVIDENCE_FORBIDDEN"
        )
    return self_digest(
        {
            "schema_id": PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "as_of": as_of,
            "entries": entries,
            "pit_evidence_registry_digest": pit_digest,
            "public_market_analysis_bundle_digest": analysis_digest,
            "availability_policy": _AVAILABILITY_POLICY,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    )


def verify_v32_verified_pit_evidence_availability_registry_v1(
    document: Mapping[str, Any],
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    public_market_analysis_bundle: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _AVAILABILITY_REGISTRY_FIELDS:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_REGISTRY_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
        )
        rebuilt = build_v32_verified_pit_evidence_availability_registry_v1(
            public_evidence_verifier=public_evidence_verifier,
            public_market_analysis_bundle=public_market_analysis_bundle,
            pit_evidence_registry=pit_evidence_registry,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DynamicStateContinuityError):
            raise
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_REGISTRY_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD]:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_REGISTRY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _verify_durable_availability_registry(
    document: Mapping[str, Any],
    *,
    expected_digest: str,
    run_id: str,
    cycle_index: int,
    as_of: str,
) -> tuple[str, dict[str, datetime]]:
    if not isinstance(document, Mapping) or set(document) != _AVAILABILITY_REGISTRY_FIELDS:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_REGISTRY_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_REGISTRY_INVALID"
        ) from exc
    if (
        supplied != _digest(
            expected_digest,
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_DIGEST_INVALID",
        )
        or document.get("schema_id") != PIT_AVAILABILITY_REGISTRY_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("run_id") != run_id
        or document.get("cycle_index") != cycle_index
        or document.get("as_of") != as_of
        or document.get("availability_policy") != _AVAILABILITY_POLICY
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_BINDING_INVALID"
        )
    _digest(
        document.get("pit_evidence_registry_digest"),
        "V32_CONTINUITY_PREVIOUS_AVAILABILITY_BINDING_INVALID",
    )
    _digest(
        document.get("public_market_analysis_bundle_digest"),
        "V32_CONTINUITY_PREVIOUS_AVAILABILITY_BINDING_INVALID",
    )
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID"
        )
    result: dict[str, datetime] = {}
    cutoff = _time(as_of, "V32_CONTINUITY_PREVIOUS_AVAILABILITY_TIME_INVALID")
    for row in entries:
        if not isinstance(row, Mapping) or set(row) != _AVAILABILITY_ENTRY_FIELDS:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID"
            )
        evidence_ref = _text(
            row.get("evidence_ref"),
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID",
        )
        available_at = _time(
            row.get("available_at"),
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID",
        )
        if evidence_ref in result or available_at > cutoff:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID"
            )
        result[evidence_ref] = available_at
    if list(result) != sorted(result):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_AVAILABILITY_ENTRIES_INVALID"
        )
    return supplied, result


def _hypotheses_by_id(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["hypothesis_id"]): row
        for row in state["hypotheses"]
    }


def _rows_by_id(
    state: Mapping[str, Any], *, collection: str, key: str
) -> dict[str, Mapping[str, Any]]:
    return {str(row[key]): row for row in state[collection]}


def _refs(row: Mapping[str, Any], fields: Sequence[str]) -> set[str]:
    return {
        str(item)
        for field in fields
        for item in row[field]
    }


def _same_fields(
    left: Mapping[str, Any], right: Mapping[str, Any], fields: Sequence[str]
) -> bool:
    return all(left.get(field) == right.get(field) for field in fields)


def _postdating_fresh_refs(
    refs: set[str],
    *,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
    current_as_of: datetime,
) -> set[str]:
    fresh: set[str] = set()
    for evidence_ref in refs:
        available_at = current_availability.get(evidence_ref)
        if available_at is None:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_FRESH_REF_AVAILABILITY_MISSING"
            )
        if available_at > current_as_of:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_FRESH_REF_FUTURE_FORBIDDEN"
            )
        if (
            evidence_ref not in previous_availability
            and available_at > freshness_cutoff
        ):
            fresh.add(evidence_ref)
    return fresh


def _has_two_nonoverlapping_dependency_refs(
    refs: set[str],
    *,
    evidence_dependency_closure: Mapping[str, frozenset[str]],
) -> bool:
    """Require two materially distinct observables, not two provenance aliases.

    The complete dependency closure remains authoritative and unchanged.  Only
    venue and projection lineage are provenance-only for this independence
    decision.  Every other present or future group stays material by default.
    In particular, distinct candle requests still share the explicit
    ``OBSERVABLE_FAMILY:PRICE_ACTION`` group and therefore cannot create
    a false dual-source HIGH promotion.
    """

    def prefix(group: str) -> str:
        return group.partition(":")[0]

    def material(groups: frozenset[str]) -> frozenset[str]:
        return frozenset(
            group
            for group in groups
            if prefix(group) not in _PROVENANCE_ONLY_DEPENDENCY_PREFIXES
        )

    def typed(groups: frozenset[str], expected_prefix: str) -> frozenset[str]:
        return frozenset(
            group for group in groups if prefix(group) == expected_prefix
        )

    ordered = sorted(refs)
    for index, left in enumerate(ordered):
        left_groups = evidence_dependency_closure.get(left)
        if not left_groups:
            continue
        left_material = material(left_groups)
        left_requests = typed(left_groups, _REQUEST_DEPENDENCY_PREFIX)
        left_families = typed(
            left_groups, _OBSERVABLE_FAMILY_DEPENDENCY_PREFIX
        )
        for right in ordered[index + 1 :]:
            right_groups = evidence_dependency_closure.get(right)
            if not right_groups:
                continue
            right_material = material(right_groups)
            right_requests = typed(right_groups, _REQUEST_DEPENDENCY_PREFIX)
            right_families = typed(
                right_groups, _OBSERVABLE_FAMILY_DEPENDENCY_PREFIX
            )
            if (
                left_requests
                and right_requests
                and left_families
                and right_families
                and left_families.issubset(
                    _DIRECTIONAL_ADMISSIBLE_OBSERVABLE_FAMILY_GROUPS
                )
                and right_families.issubset(
                    _DIRECTIONAL_ADMISSIBLE_OBSERVABLE_FAMILY_GROUPS
                )
                and left_requests.isdisjoint(right_requests)
                and left_families.isdisjoint(right_families)
                and left_material.isdisjoint(right_material)
            ):
                return True
    return False


def _has_directional_counter_evidence(
    refs: set[str],
    *,
    current_availability: Mapping[str, datetime],
    current_as_of: datetime,
    high_directional_evidence_refs: frozenset[str],
) -> bool:
    """Require one currently available counter-ref from a directional family."""

    for evidence_ref in refs:
        available_at = current_availability.get(evidence_ref)
        if (
            evidence_ref in high_directional_evidence_refs
            and available_at is not None
            and available_at <= current_as_of
        ):
            return True
    return False


def _high_directional_evidence_refs(
    analysis_bundle: Mapping[str, Any],
    *,
    evidence_dependency_closure: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    """Admit only observed/derived PIT datums from directional families."""

    admitted: set[str] = set()
    for row in analysis_bundle["datums"]:
        if row.get("status") not in {"OBSERVED", "DERIVED"}:
            continue
        evidence_ref = str(row.get(_PIT_DATUM_DIGEST_FIELD))
        groups = evidence_dependency_closure.get(evidence_ref, frozenset())
        families = frozenset(
            group
            for group in groups
            if group.partition(":")[0]
            == _OBSERVABLE_FAMILY_DEPENDENCY_PREFIX
        )
        if (
            families
            and families.issubset(
                _DIRECTIONAL_ADMISSIBLE_OBSERVABLE_FAMILY_GROUPS
            )
        ):
            admitted.add(evidence_ref)
    return frozenset(admitted)


def _verify_high_tier_evidence_gates(
    *,
    current_state: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None,
    current_as_of: datetime,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
    evidence_dependency_closure: Mapping[str, frozenset[str]],
    high_directional_evidence_refs: frozenset[str],
) -> set[str]:
    """Ground initial HIGH and LOW-to-HIGH in dual fresh independent evidence."""

    current = _hypotheses_by_id(current_state)
    previous = {} if previous_state is None else _hypotheses_by_id(previous_state)
    fresh_used: set[str] = set()
    for hypothesis_id, row in current.items():
        if (
            row.get("subjective_plausibility_tier") != "HIGH"
            or row.get("direction") not in {"LONG", "SHORT"}
        ):
            continue
        predecessor: Mapping[str, Any] | None = previous.get(hypothesis_id)
        if predecessor is None and row.get("predecessor_id") is not None:
            predecessor = previous.get(str(row.get("predecessor_id")))
        initial_high = predecessor is None
        low_to_high = (
            predecessor is not None
            and predecessor.get("subjective_plausibility_tier") == "LOW"
        )
        if not (initial_high or low_to_high):
            continue
        opposing_refs = set(row.get("opposing_refs", ()))
        if not opposing_refs:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_HIGH_TIER_COUNTER_EVIDENCE_REQUIRED"
            )
        support_identity_refs = _refs(
            row, ("source_refs", "supporting_refs", "tier_update_refs")
        )
        if not _has_directional_counter_evidence(
            opposing_refs - support_identity_refs,
            current_availability=current_availability,
            current_as_of=current_as_of,
            high_directional_evidence_refs=high_directional_evidence_refs,
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_HIGH_TIER_DIRECTIONAL_COUNTER_EVIDENCE_REQUIRED"
            )
        refs = (
            set(row.get("tier_update_refs", ()))
            if low_to_high
            else _refs(row, ("source_refs", "supporting_refs"))
        )
        if previous_state is None:
            # Genesis evidence is fresh by construction once it is present in
            # the verified current PIT availability registry.
            fresh = {
                ref
                for ref in refs
                if ref in current_availability
                and current_availability[ref] <= current_as_of
            }
        else:
            fresh = _postdating_fresh_refs(
                refs,
                current_availability=current_availability,
                previous_availability=previous_availability,
                freshness_cutoff=freshness_cutoff,
                current_as_of=current_as_of,
            )
        directional_fresh = fresh & set(high_directional_evidence_refs)
        if (
            len(directional_fresh) < 2
            or not _has_two_nonoverlapping_dependency_refs(
                directional_fresh,
                evidence_dependency_closure=evidence_dependency_closure,
            )
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED"
            )
        fresh_used.update(directional_fresh)
    return fresh_used


def _lineage_is_genesis(row: Mapping[str, Any], object_id: str) -> bool:
    return (
        row.get("lineage_id") == object_id
        and row.get("lineage_revision") == 1
        and row.get("predecessor_id") is None
        and row.get("predecessor_fingerprint") is None
    )


def _lineage_is_successor(
    row: Mapping[str, Any], predecessor: Mapping[str, Any]
) -> bool:
    return (
        row.get("predecessor_id")
        in {
            predecessor.get("hypothesis_id"),
            predecessor.get("zone_id"),
            predecessor.get("modifier_id"),
        }
        and row.get("lineage_id") == predecessor.get("lineage_id")
        and row.get("lineage_revision")
        == predecessor.get("lineage_revision", 0) + 1
        and row.get("predecessor_fingerprint")
        == predecessor.get("semantic_fingerprint")
        and row.get("semantic_fingerprint")
        == predecessor.get("semantic_fingerprint")
    )


def _verify_hypothesis_continuity(
    *,
    current_state: Mapping[str, Any],
    previous_state: Mapping[str, Any],
    previous_digest: str,
    current_as_of: datetime,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
) -> tuple[list[str], list[str], list[str], list[str], set[str]]:
    current = _hypotheses_by_id(current_state)
    previous = _hypotheses_by_id(previous_state)
    missing_ids = sorted(set(previous) - set(current))
    if missing_ids:
        # Terminal IDs remain as tombstones.  Retaining them is what makes a
        # later same-ID revival detectable with one durable predecessor.
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_HYPOTHESIS_DISAPPEARED"
        )

    continued_ids = sorted(set(previous) & set(current))
    new_ids = sorted(set(current) - set(previous))
    renewed_ids: list[str] = []
    retired_ids: list[str] = []
    fresh_refs: set[str] = set()
    for hypothesis_id in continued_ids:
        old = previous[hypothesis_id]
        new = current[hypothesis_id]
        if (
            new.get("parent_revision_digest") != previous_digest
            or new.get("previous_subjective_plausibility_tier")
            != old.get("subjective_plausibility_tier")
            or new.get("previous_expires_at") != old.get("expires_at")
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_DURABLE_PRIOR_CLAIM_MISMATCH"
            )
        if not _same_fields(new, old, _HYPOTHESIS_IDENTITY_FIELDS):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_HYPOTHESIS_IDENTITY_MUTATED"
            )
        tier_refs = set(new.get("tier_update_refs", ()))
        tier_changed = (
            new.get("subjective_plausibility_tier")
            != old.get("subjective_plausibility_tier")
        )
        if tier_changed:
            fresh = _postdating_fresh_refs(
                tier_refs,
                current_availability=current_availability,
                previous_availability=previous_availability,
                freshness_cutoff=freshness_cutoff,
                current_as_of=current_as_of,
            )
            if not tier_refs or fresh != tier_refs:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_TIER_CHANGE_FRESH_PIT_REQUIRED"
                )
            fresh_refs.update(fresh)
        elif tier_refs:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_FALSE_TIER_CHANGE_EVIDENCE"
            )
        if new.get("expires_at") != old.get("expires_at"):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_HYPOTHESIS_IN_PLACE_RENEWAL_FORBIDDEN"
            )
        old_status = old.get("status")
        new_status = new.get("status")
        if old_status == "FALSIFIED" and new_status != "FALSIFIED":
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_FALSIFIED_HYPOTHESIS_REVIVAL_FORBIDDEN"
            )
        if old_status == "EXPIRED" and new_status != "EXPIRED":
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_RETIRED_HYPOTHESIS_REVIVAL_FORBIDDEN"
            )
        due = _time(
            old.get("expires_at"), "V32_CONTINUITY_HYPOTHESIS_EXPIRY_INVALID"
        ) <= current_as_of
        if due and old_status != "FALSIFIED" and new_status not in {
            "EXPIRED",
            "FALSIFIED",
        }:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_DUE_HYPOTHESIS_NOT_RETIRED"
            )
        if old_status not in {"FALSIFIED", "EXPIRED"} and new_status in {
            "FALSIFIED",
            "EXPIRED",
        }:
            retired_ids.append(hypothesis_id)

    renewed_predecessors: set[str] = set()
    previous_lineages = {str(row["lineage_id"]) for row in previous.values()}
    previous_fingerprints = {
        str(row["semantic_fingerprint"]) for row in previous.values()
    }
    for hypothesis_id in new_ids:
        row = current[hypothesis_id]
        predecessor_id = row.get("predecessor_id")
        renewal_claimed = predecessor_id is not None
        if renewal_claimed:
            renewal_refs = set(row.get("renewal_evidence_refs", ()))
            predecessor = previous.get(str(predecessor_id))
            if (
                predecessor is None
                or not _lineage_is_successor(row, predecessor)
                or row.get("parent_revision_digest") != previous_digest
                or row.get("previous_subjective_plausibility_tier")
                != predecessor.get("subjective_plausibility_tier")
                or row.get("previous_expires_at") != predecessor.get("expires_at")
                or not renewal_refs
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_HYPOTHESIS_RENEWAL_PREDECESSOR_INVALID"
                )
            if (
                predecessor_id in renewed_predecessors
                or predecessor.get("status") == "FALSIFIED"
                or _time(
                    predecessor.get("expires_at"),
                    "V32_CONTINUITY_HYPOTHESIS_EXPIRY_INVALID",
                )
                > current_as_of
                or current[predecessor_id].get("status") != "EXPIRED"
                or _time(
                    row.get("expires_at"),
                    "V32_CONTINUITY_HYPOTHESIS_EXPIRY_INVALID",
                )
                <= _time(
                    predecessor.get("expires_at"),
                    "V32_CONTINUITY_HYPOTHESIS_EXPIRY_INVALID",
                )
                or row.get("status") not in {"ACTIVE", "WEAKENED", "UNKNOWN"}
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_HYPOTHESIS_RENEWAL_TRANSITION_INVALID"
                )
            fresh = _postdating_fresh_refs(
                renewal_refs,
                current_availability=current_availability,
                previous_availability=previous_availability,
                freshness_cutoff=freshness_cutoff,
                current_as_of=current_as_of,
            )
            if fresh != renewal_refs:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_HYPOTHESIS_RENEWAL_FRESH_PIT_REQUIRED"
                )
            renewed_predecessors.add(str(predecessor_id))
            renewed_ids.append(hypothesis_id)
            fresh_refs.update(fresh)
            tier_refs = set(row.get("tier_update_refs", ()))
            tier_changed = (
                row.get("subjective_plausibility_tier")
                != predecessor.get("subjective_plausibility_tier")
            )
            if tier_changed:
                tier_fresh = _postdating_fresh_refs(
                    tier_refs,
                    current_availability=current_availability,
                    previous_availability=previous_availability,
                    freshness_cutoff=freshness_cutoff,
                    current_as_of=current_as_of,
                )
                if not tier_refs or tier_fresh != tier_refs:
                    raise V32DynamicStateContinuityError(
                        "V32_CONTINUITY_TIER_CHANGE_FRESH_PIT_REQUIRED"
                    )
                fresh_refs.update(tier_fresh)
            elif tier_refs:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_FALSE_TIER_CHANGE_EVIDENCE"
                )
        else:
            if (
                not _lineage_is_genesis(row, hypothesis_id)
                or row.get("lineage_id") in previous_lineages
                or row.get("semantic_fingerprint") in previous_fingerprints
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_HYPOTHESIS_RENEWAL_IDENTITY_REQUIRED"
                )
            if (
                row.get("parent_revision_digest") is not None
                or row.get("previous_subjective_plausibility_tier") is not None
                or row.get("previous_expires_at") is not None
                or row.get("tier_update_refs")
                or row.get("renewal_evidence_refs")
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_NEW_HYPOTHESIS_FALSE_PARENT"
                )
            fresh = _postdating_fresh_refs(
                _refs(row, ("source_refs", "supporting_refs")),
                current_availability=current_availability,
                previous_availability=previous_availability,
                freshness_cutoff=freshness_cutoff,
                current_as_of=current_as_of,
            )
            if not fresh:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_NEW_HYPOTHESIS_FRESH_PIT_REQUIRED"
                )
            fresh_refs.update(fresh)
    return continued_ids, new_ids, sorted(renewed_ids), sorted(retired_ids), fresh_refs


def _verify_zone_continuity(
    *,
    current_state: Mapping[str, Any],
    previous_state: Mapping[str, Any],
    current_as_of: datetime,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
) -> tuple[list[str], list[str], list[str], list[str], set[str]]:
    current = _rows_by_id(current_state, collection="zones", key="zone_id")
    previous = _rows_by_id(previous_state, collection="zones", key="zone_id")
    if set(previous) - set(current):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_ZONE_DISAPPEARED"
        )
    continued = sorted(set(previous) & set(current))
    new_ids = sorted(set(current) - set(previous))
    renewed_ids: list[str] = []
    retired: list[str] = []
    fresh_refs: set[str] = set()
    previous_as_of = _time(
        previous_state["as_of"], "V32_CONTINUITY_PREVIOUS_TIME_INVALID"
    )
    for zone_id in continued:
        old = previous[zone_id]
        new = current[zone_id]
        if new.get("expires_at") != old.get("expires_at"):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_ZONE_IN_PLACE_RENEWAL_FORBIDDEN"
            )
        if not _same_fields(new, old, _ZONE_IDENTITY_FIELDS):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_ZONE_IDENTITY_MUTATED"
            )
        expiry = _time(
            old.get("expires_at"), "V32_CONTINUITY_ZONE_EXPIRY_INVALID"
        )
        if previous_as_of < expiry <= current_as_of:
            retired.append(zone_id)
    for zone_id in new_ids:
        row = current[zone_id]
        predecessor_id = row.get("predecessor_id")
        if predecessor_id is None:
            if (
                not _lineage_is_genesis(row, zone_id)
                or row.get("lineage_id")
                in {old.get("lineage_id") for old in previous.values()}
                or row.get("semantic_fingerprint")
                in {old.get("semantic_fingerprint") for old in previous.values()}
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_ZONE_RENEWAL_IDENTITY_REQUIRED"
                )
        else:
            predecessor = previous.get(str(predecessor_id))
            if (
                predecessor is None
                or not _lineage_is_successor(row, predecessor)
                or str(predecessor_id) in {
                    str(current[item].get("predecessor_id"))
                    for item in new_ids
                    if item != zone_id
                }
                or _time(
                    predecessor.get("expires_at"),
                    "V32_CONTINUITY_ZONE_EXPIRY_INVALID",
                )
                > current_as_of
                or _time(
                    row.get("expires_at"),
                    "V32_CONTINUITY_ZONE_TIME_INVALID",
                )
                <= current_as_of
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_ZONE_RENEWAL_PREDECESSOR_INVALID"
                )
            renewed_ids.append(zone_id)
        fresh = _postdating_fresh_refs(
            _refs(row, _ZONE_PIT_FIELDS),
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
            current_as_of=current_as_of,
        )
        if (
            _time(row.get("available_at"), "V32_CONTINUITY_ZONE_TIME_INVALID")
            <= freshness_cutoff
            or _time(row.get("expires_at"), "V32_CONTINUITY_ZONE_TIME_INVALID")
            <= current_as_of
            or not fresh
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_NEW_ZONE_FRESH_PIT_REQUIRED"
            )
        fresh_refs.update(fresh)
    return continued, new_ids, sorted(renewed_ids), sorted(retired), fresh_refs


def _verify_path_modifier_continuity(
    *,
    current_state: Mapping[str, Any],
    previous_state: Mapping[str, Any],
    current_as_of: datetime,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
) -> tuple[list[str], list[str], list[str], list[str], set[str]]:
    current = _rows_by_id(
        current_state, collection="path_modifiers", key="modifier_id"
    )
    previous = _rows_by_id(
        previous_state, collection="path_modifiers", key="modifier_id"
    )
    if set(previous) - set(current):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PREVIOUS_PATH_MODIFIER_DISAPPEARED"
        )
    continued = sorted(set(previous) & set(current))
    new_ids = sorted(set(current) - set(previous))
    renewed_ids: list[str] = []
    retired: list[str] = []
    fresh_refs: set[str] = set()
    for modifier_id in continued:
        old = previous[modifier_id]
        new = current[modifier_id]
        if new.get("expires_at") != old.get("expires_at"):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PATH_MODIFIER_IN_PLACE_RENEWAL_FORBIDDEN"
            )
        if not _same_fields(new, old, _MODIFIER_IDENTITY_FIELDS):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PATH_MODIFIER_IDENTITY_MUTATED"
            )
        old_status = old.get("status")
        new_status = new.get("status")
        if old_status in {"FALSIFIED", "EXPIRED"} and new_status != old_status:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_RETIRED_PATH_MODIFIER_REVIVAL_FORBIDDEN"
            )
        due = _time(
            old.get("expires_at"), "V32_CONTINUITY_PATH_MODIFIER_EXPIRY_INVALID"
        ) <= current_as_of
        if due and old_status != "FALSIFIED" and new_status not in {
            "EXPIRED",
            "FALSIFIED",
        }:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_DUE_PATH_MODIFIER_NOT_RETIRED"
            )
        if old_status not in {"FALSIFIED", "EXPIRED"} and new_status in {
            "FALSIFIED",
            "EXPIRED",
        }:
            retired.append(modifier_id)
    for modifier_id in new_ids:
        row = current[modifier_id]
        predecessor_id = row.get("predecessor_id")
        if predecessor_id is None:
            if (
                not _lineage_is_genesis(row, modifier_id)
                or row.get("lineage_id")
                in {old.get("lineage_id") for old in previous.values()}
                or row.get("semantic_fingerprint")
                in {old.get("semantic_fingerprint") for old in previous.values()}
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_PATH_MODIFIER_RENEWAL_IDENTITY_REQUIRED"
                )
        else:
            predecessor = previous.get(str(predecessor_id))
            if (
                predecessor is None
                or not _lineage_is_successor(row, predecessor)
                or str(predecessor_id) in {
                    str(current[item].get("predecessor_id"))
                    for item in new_ids
                    if item != modifier_id
                }
                or predecessor.get("status") == "FALSIFIED"
                or current[str(predecessor_id)].get("status") != "EXPIRED"
                or _time(
                    predecessor.get("expires_at"),
                    "V32_CONTINUITY_PATH_MODIFIER_EXPIRY_INVALID",
                )
                > current_as_of
            ):
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_PATH_MODIFIER_RENEWAL_PREDECESSOR_INVALID"
                )
            renewed_ids.append(modifier_id)
        fresh = _postdating_fresh_refs(
            set(str(item) for item in row["source_refs"]),
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
            current_as_of=current_as_of,
        )
        if (
            _time(
                row.get("available_at"), "V32_CONTINUITY_PATH_MODIFIER_TIME_INVALID"
            )
            <= freshness_cutoff
            or _time(
                row.get("expires_at"), "V32_CONTINUITY_PATH_MODIFIER_TIME_INVALID"
            )
            <= current_as_of
            or row.get("status") not in {"ACTIVE", "UNKNOWN"}
            or not fresh
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_NEW_PATH_MODIFIER_FRESH_PIT_REQUIRED"
            )
        fresh_refs.update(fresh)
    return continued, new_ids, sorted(renewed_ids), sorted(retired), fresh_refs


def _verify_modifier_registries(
    *,
    state: Mapping[str, Any],
    pit_members: frozenset[str],
    graph_members: frozenset[str],
) -> list[str]:
    modifiers = {
        str(row["modifier_id"]): row for row in state["path_modifiers"]
    }
    hypotheses = _hypotheses_by_id(state)
    modifier_edges = {
        (modifier_id, str(hypothesis_id))
        for modifier_id, modifier in modifiers.items()
        for hypothesis_id in modifier["affected_hypothesis_ids"]
    }
    hypothesis_edges = {
        (str(modifier_id), hypothesis_id)
        for hypothesis_id, hypothesis in hypotheses.items()
        for modifier_id in hypothesis["path_modifier_ids"]
    }
    if modifier_edges != hypothesis_edges:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_MODIFIER_AFFECTED_IDS_NOT_BIDIRECTIONAL"
        )
    for modifier_id, modifier in modifiers.items():
        if not set(modifier["source_refs"]).issubset(pit_members):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_MODIFIER_SOURCE_NOT_CURRENT_PIT"
            )
        if not set(modifier["dependency_groups"]).issubset(graph_members):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_MODIFIER_DEPENDENCY_NOT_CURRENT_GRAPH"
            )
        if any(
            hypothesis_id not in hypotheses
            for hypothesis_id in modifier["affected_hypothesis_ids"]
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_MODIFIER_AFFECTED_ID_MISSING"
            )
    return sorted(modifiers)


def _verify_complete_state_registry_coverage(
    *,
    state: Mapping[str, Any],
    pit_members: frozenset[str],
    graph_members: frozenset[str],
    evidence_dependency_closure: Mapping[str, frozenset[str]],
) -> None:
    """Reject evidence/dependency strings that are not in verified registries."""

    pit_refs: set[str] = set()
    graph_refs: set[str] = set()
    closure_objects: list[tuple[set[str], set[str]]] = []
    regime = state["market_regime_state"]
    pit_refs.update(regime["evidence_refs"])
    pit_refs.update(regime["counter_evidence_refs"])
    pit_refs.update(regime["transition_evidence_refs"])
    for assessment in regime["regime_feature_assessments"]:
        pit_refs.update(assessment["evidence_refs"])
    for unknown in state["unknowns"]:
        graph_refs.update(unknown["dependency_refs"])
    for zone in state["zones"]:
        zone_refs: set[str] = set()
        for field in _ZONE_PIT_FIELDS:
            pit_refs.update(zone[field])
            zone_refs.update(zone[field])
        graph_refs.update(zone["dependency_groups"])
        closure_objects.append((zone_refs, set(zone["dependency_groups"])))
    for hypothesis in state["hypotheses"]:
        hypothesis_refs: set[str] = set()
        for field in _HYPOTHESIS_PIT_FIELDS:
            pit_refs.update(hypothesis[field])
            hypothesis_refs.update(hypothesis[field])
        graph_refs.update(hypothesis["dependency_groups"])
        closure_objects.append(
            (hypothesis_refs, set(hypothesis["dependency_groups"]))
        )
    for modifier in state["path_modifiers"]:
        pit_refs.update(modifier["source_refs"])
        graph_refs.update(modifier["dependency_groups"])
        closure_objects.append(
            (set(modifier["source_refs"]), set(modifier["dependency_groups"]))
        )
    for cluster in state["dependency_clusters"]:
        graph_refs.update(cluster["shared_dependency_groups"])
    if not pit_refs.issubset(pit_members):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_STATE_EVIDENCE_NOT_CURRENT_PIT"
        )
    if not graph_refs.issubset(graph_members):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_STATE_DEPENDENCY_NOT_CURRENT_GRAPH"
        )
    for evidence_refs, declared_dependencies in closure_objects:
        required_dependencies: set[str] = set()
        for evidence_ref in evidence_refs:
            closure = evidence_dependency_closure.get(evidence_ref)
            if closure is None:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_EVIDENCE_DEPENDENCY_CLOSURE_MISSING"
                )
            required_dependencies.update(closure)
        if not required_dependencies.issubset(declared_dependencies):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_EVIDENCE_DEPENDENCY_CLOSURE_INCOMPLETE"
            )


def _verify_regime_feature_assessment_evidence(
    *,
    state: Mapping[str, Any],
    pit_members: frozenset[str],
    evidence_dependency_closure: Mapping[str, frozenset[str]],
) -> None:
    """Bind typed regime features to current PIT observable families.

    The Agent may classify a feature, but it may not use one decorative or
    unrelated reference to manufacture CHOPPY or directionless volatility.
    Each feature must cite a compatible typed observable family, and the two
    guarded regimes require at least two refs spanning at least two families.
    """

    regime = state["market_regime_state"]
    assessments = regime["regime_feature_assessments"]
    all_refs: set[str] = set()
    all_qualifying_families: set[str] = set()
    for assessment in assessments:
        feature_type = assessment["feature_type"]
        refs = set(assessment["evidence_refs"])
        if not refs.issubset(pit_members):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_REGIME_FEATURE_EVIDENCE_NOT_CURRENT_PIT"
            )
        required_families = REGIME_FEATURE_REQUIRED_OBSERVABLE_FAMILIES[
            feature_type
        ]
        qualifying_families: set[str] = set()
        for evidence_ref in refs:
            groups = evidence_dependency_closure.get(evidence_ref)
            if not groups:
                raise V32DynamicStateContinuityError(
                    "V32_CONTINUITY_REGIME_FEATURE_EVIDENCE_CLOSURE_MISSING"
                )
            qualifying_families.update(
                group.partition(":")[2]
                for group in groups
                if group.startswith("OBSERVABLE_FAMILY:")
                and group.partition(":")[2] in required_families
            )
        if not qualifying_families:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_REGIME_FEATURE_OBSERVABLE_FAMILY_INVALID"
            )
        all_refs.update(refs)
        all_qualifying_families.update(qualifying_families)
    if (
        regime["regime"] in REGIME_FEATURE_REQUIRED_COMBINATIONS
        and (len(all_refs) < 2 or len(all_qualifying_families) < 2)
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_REGIME_FEATURE_DIVERSITY_INVALID"
        )


def _verify_market_regime_continuity(
    *,
    current_state: Mapping[str, Any],
    previous_state: Mapping[str, Any],
    current_as_of: datetime,
    current_availability: Mapping[str, datetime],
    previous_availability: Mapping[str, datetime],
    freshness_cutoff: datetime,
    evidence_dependency_closure: Mapping[str, frozenset[str]],
    verified_public_market_analysis_bundle: Mapping[str, Any],
) -> set[str]:
    current = current_state["market_regime_state"]
    previous = previous_state["market_regime_state"]
    previous_regime = previous["regime"]
    current_regime = current["regime"]
    transition_refs = set(current["transition_evidence_refs"])
    if current["previous_regime"] != previous_regime:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_MARKET_REGIME_PRIOR_MISMATCH"
        )
    if current_regime == previous_regime:
        if transition_refs:
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_FALSE_MARKET_REGIME_TRANSITION"
            )
        return set()
    fresh = _postdating_fresh_refs(
        transition_refs,
        current_availability=current_availability,
        previous_availability=previous_availability,
        freshness_cutoff=freshness_cutoff,
        current_as_of=current_as_of,
    )
    if not transition_refs or fresh != transition_refs:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_MARKET_REGIME_TRANSITION_FRESH_PIT_REQUIRED"
        )
    if (
        previous_regime in CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES
        and current_regime not in CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES
        and not _has_two_nonoverlapping_dependency_refs(
            fresh,
            evidence_dependency_closure=evidence_dependency_closure,
        )
        and not _two_closed_15m_bars_support_regime(
            verified_public_market_analysis_bundle, current_regime
        )
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_NONDIRECTIONAL_TO_DIRECTIONAL_EVIDENCE_GATE_INVALID"
        )
    return fresh


def _two_closed_15m_bars_support_regime(
    analysis_bundle: Mapping[str, Any], regime: str
) -> bool:
    """Machine-check the narrow two-closed-bar directional alternative."""

    series = analysis_bundle.get("closed_bar_series")
    if not isinstance(series, Mapping):
        return False
    bars = series.get("15M")
    if not isinstance(bars, list) or len(bars) < 2:
        return False
    left, right = bars[-2], bars[-1]
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    try:
        left_open_ms = int(left.get("open_time_ms"))
        left_close_ms = int(left.get("close_time_ms"))
        right_open_ms = int(right.get("open_time_ms"))
        right_close_ms = int(right.get("close_time_ms"))
        left_open = Decimal(str(left.get("open")))
        left_close = Decimal(str(left.get("close")))
        right_open = Decimal(str(right.get("open")))
        right_close = Decimal(str(right.get("close")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if (
        left.get("confirmed_closed") is not True
        or right.get("confirmed_closed") is not True
        or left_close_ms - left_open_ms != 900_000
        or right_close_ms - right_open_ms != 900_000
        or right_open_ms != left_close_ms
    ):
        return False
    if regime == "TREND_UP":
        return left_close > left_open and right_close > right_open and right_close > left_close
    if regime == "TREND_DOWN":
        return left_close < left_open and right_close < right_open and right_close < left_close
    return False


def compose_v32_dynamic_state_continuity_v1(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    current_state: Mapping[str, Any],
    durable_previous_state: Mapping[str, Any] | None,
    durable_previous_state_digest: str | None,
    verified_pit_evidence_registry: Mapping[str, Any],
    verified_pit_evidence_registry_digest: str,
    verified_public_market_analysis_bundle: Mapping[str, Any],
    verified_pit_evidence_availability_registry: Mapping[str, Any],
    verified_pit_evidence_availability_registry_digest: str,
    durable_previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    durable_previous_pit_evidence_availability_registry_digest: str | None,
    verified_graph_dependency_registry: Mapping[str, Any],
    verified_graph_dependency_registry_digest: str,
) -> dict[str, Any]:
    """Verify one current state against durable state and current registries.

    ``durable_previous_state_digest`` is a controller/checkpoint binding, not a
    value copied from ``current_state``.  Requiring it separately prevents the
    current Agent payload from manufacturing both a predecessor and its link.
    """

    try:
        current_digest = verify_v32_dynamic_research_state_v1(current_state)
    except V32DynamicResearchError as exc:
        raise V32DynamicStateContinuityError(
            f"V32_CONTINUITY_CURRENT_STATE_INVALID:{exc}"
        ) from exc
    run_id = str(current_state["run_id"])
    cycle_index = current_state["cycle_index"]
    as_of = str(current_state["as_of"])
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int):
        raise V32DynamicStateContinuityError("V32_CONTINUITY_CYCLE_INVALID")

    previous_digest: str | None = None
    continued_ids: list[str] = []
    new_ids = sorted(_hypotheses_by_id(current_state))
    renewed_ids: list[str] = []
    retired_hypothesis_ids: list[str] = []
    continued_zone_ids: list[str] = []
    new_zone_ids = sorted(
        _rows_by_id(current_state, collection="zones", key="zone_id")
    )
    retired_zone_ids: list[str] = []
    renewed_zone_ids: list[str] = []
    continued_modifier_ids: list[str] = []
    new_modifier_ids = sorted(
        _rows_by_id(
            current_state, collection="path_modifiers", key="modifier_id"
        )
    )
    retired_modifier_ids: list[str] = []
    renewed_modifier_ids: list[str] = []
    fresh_lifecycle_refs: set[str] = set()
    if cycle_index == 1:
        if (
            durable_previous_state is not None
            or durable_previous_state_digest is not None
            or current_state.get("previous_state_digest") is not None
            or durable_previous_pit_evidence_availability_registry is not None
            or durable_previous_pit_evidence_availability_registry_digest is not None
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_GENESIS_PREVIOUS_STATE_FORBIDDEN"
            )
    else:
        if (
            durable_previous_state is None
            or durable_previous_state_digest is None
            or durable_previous_pit_evidence_availability_registry is None
            or durable_previous_pit_evidence_availability_registry_digest is None
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_DURABLE_PREVIOUS_STATE_REQUIRED"
            )
        expected_digest = _digest(
            durable_previous_state_digest,
            "V32_CONTINUITY_DURABLE_PREVIOUS_DIGEST_INVALID",
        )
        try:
            previous_digest = verify_v32_dynamic_research_state_v1(
                durable_previous_state
            )
        except V32DynamicResearchError as exc:
            raise V32DynamicStateContinuityError(
                f"V32_CONTINUITY_DURABLE_PREVIOUS_STATE_INVALID:{exc}"
            ) from exc
        if (
            previous_digest != expected_digest
            or current_state.get("previous_state_digest") != expected_digest
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PREVIOUS_DIGEST_BINDING_MISMATCH"
            )
        if (
            durable_previous_state.get("run_id") != run_id
            or durable_previous_state.get("cycle_index") != cycle_index - 1
            or _time(
                durable_previous_state.get("as_of"),
                "V32_CONTINUITY_PREVIOUS_TIME_INVALID",
            )
            >= _time(as_of, "V32_CONTINUITY_CURRENT_TIME_INVALID")
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_PREVIOUS_IDENTITY_INVALID"
            )
    pit_digest, pit_members = _verify_current_cycle_registry(
        verified_pit_evidence_registry,
        schema_id=PIT_REGISTRY_SCHEMA_ID,
        digest_field=PIT_REGISTRY_DIGEST_FIELD,
        run_id=run_id,
        cycle_index=cycle_index,
        as_of=as_of,
        code_prefix="V32_CONTINUITY_PIT_REGISTRY",
        allow_as_of_not_after=True,
    )
    if pit_digest != _digest(
        verified_pit_evidence_registry_digest,
        "V32_CONTINUITY_PIT_REGISTRY_DURABLE_DIGEST_INVALID",
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_PIT_REGISTRY_DURABLE_BINDING_MISMATCH"
        )
    availability_digest = (
        verify_v32_verified_pit_evidence_availability_registry_v1(
            verified_pit_evidence_availability_registry,
            public_evidence_verifier=public_evidence_verifier,
            public_market_analysis_bundle=verified_public_market_analysis_bundle,
            pit_evidence_registry=verified_pit_evidence_registry,
        )
    )
    if availability_digest != _digest(
        verified_pit_evidence_availability_registry_digest,
        "V32_CONTINUITY_AVAILABILITY_REGISTRY_DURABLE_DIGEST_INVALID",
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_AVAILABILITY_REGISTRY_DURABLE_BINDING_MISMATCH"
        )
    current_availability = {
        str(row["evidence_ref"]): _time(
            row["available_at"], "V32_CONTINUITY_AVAILABILITY_TIME_INVALID"
        )
        for row in verified_pit_evidence_availability_registry["entries"]
    }
    analysis_bundle_digest = _digest(
        verified_pit_evidence_availability_registry[
            "public_market_analysis_bundle_digest"
        ],
        "V32_CONTINUITY_AVAILABILITY_SOURCE_BINDING_INVALID",
    )
    previous_availability: dict[str, datetime] = {}
    previous_availability_digest: str | None = None
    freshness_cutoff = _time(as_of, "V32_CONTINUITY_CURRENT_TIME_INVALID")
    if durable_previous_state is not None:
        assert durable_previous_pit_evidence_availability_registry is not None
        assert durable_previous_pit_evidence_availability_registry_digest is not None
        previous_availability_digest, previous_availability = (
            _verify_durable_availability_registry(
                durable_previous_pit_evidence_availability_registry,
                expected_digest=(
                    durable_previous_pit_evidence_availability_registry_digest
                ),
                run_id=run_id,
                cycle_index=cycle_index - 1,
                as_of=str(durable_previous_state["as_of"]),
            )
        )
        freshness_cutoff = max(
            _time(
                durable_previous_state["as_of"],
                "V32_CONTINUITY_PREVIOUS_TIME_INVALID",
            ),
            _time(
                durable_previous_pit_evidence_availability_registry["as_of"],
                "V32_CONTINUITY_PREVIOUS_AVAILABILITY_TIME_INVALID",
            ),
        )
        if any(
            current_availability[evidence_ref] != available_at
            for evidence_ref, available_at in previous_availability.items()
            if evidence_ref in current_availability
        ):
            raise V32DynamicStateContinuityError(
                "V32_CONTINUITY_AVAILABILITY_HISTORY_MUTATED"
            )

    graph_digest, graph_members, evidence_dependency_closure = _verify_graph_registry(
        verified_graph_dependency_registry,
        run_id=run_id,
        cycle_index=cycle_index,
        as_of=as_of,
    )
    if graph_digest != _digest(
        verified_graph_dependency_registry_digest,
        "V32_CONTINUITY_GRAPH_REGISTRY_DURABLE_DIGEST_INVALID",
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_GRAPH_REGISTRY_DURABLE_BINDING_MISMATCH"
        )
    modifier_ids = _verify_modifier_registries(
        state=current_state,
        pit_members=pit_members,
        graph_members=graph_members,
    )
    _verify_complete_state_registry_coverage(
        state=current_state,
        pit_members=pit_members,
        graph_members=graph_members,
        evidence_dependency_closure=evidence_dependency_closure,
    )
    _verify_regime_feature_assessment_evidence(
        state=current_state,
        pit_members=pit_members,
        evidence_dependency_closure=evidence_dependency_closure,
    )
    high_directional_refs = _high_directional_evidence_refs(
        verified_public_market_analysis_bundle,
        evidence_dependency_closure=evidence_dependency_closure,
    )
    high_tier_fresh_refs = _verify_high_tier_evidence_gates(
        current_state=current_state,
        previous_state=durable_previous_state,
        current_as_of=_time(as_of, "V32_CONTINUITY_CURRENT_TIME_INVALID"),
        current_availability=current_availability,
        previous_availability=previous_availability,
        freshness_cutoff=freshness_cutoff,
        evidence_dependency_closure=evidence_dependency_closure,
        high_directional_evidence_refs=high_directional_refs,
    )
    fresh_lifecycle_refs.update(high_tier_fresh_refs)
    if durable_previous_state is not None:
        assert previous_digest is not None
        current_as_of = _time(as_of, "V32_CONTINUITY_CURRENT_TIME_INVALID")
        (
            continued_ids,
            new_ids,
            renewed_ids,
            retired_hypothesis_ids,
            hypothesis_fresh_refs,
        ) = _verify_hypothesis_continuity(
            current_state=current_state,
            previous_state=durable_previous_state,
            previous_digest=previous_digest,
            current_as_of=current_as_of,
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
        )
        (
            continued_zone_ids,
            new_zone_ids,
            renewed_zone_ids,
            retired_zone_ids,
            zone_fresh_refs,
        ) = _verify_zone_continuity(
            current_state=current_state,
            previous_state=durable_previous_state,
            current_as_of=current_as_of,
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
        )
        (
            continued_modifier_ids,
            new_modifier_ids,
            renewed_modifier_ids,
            retired_modifier_ids,
            modifier_fresh_refs,
        ) = _verify_path_modifier_continuity(
            current_state=current_state,
            previous_state=durable_previous_state,
            current_as_of=current_as_of,
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
        )
        regime_fresh_refs = _verify_market_regime_continuity(
            current_state=current_state,
            previous_state=durable_previous_state,
            current_as_of=current_as_of,
            current_availability=current_availability,
            previous_availability=previous_availability,
            freshness_cutoff=freshness_cutoff,
            evidence_dependency_closure=evidence_dependency_closure,
            verified_public_market_analysis_bundle=(
                verified_public_market_analysis_bundle
            ),
        )
        fresh_lifecycle_refs.update(hypothesis_fresh_refs)
        fresh_lifecycle_refs.update(zone_fresh_refs)
        fresh_lifecycle_refs.update(modifier_fresh_refs)
        fresh_lifecycle_refs.update(regime_fresh_refs)

    current_hypotheses = _hypotheses_by_id(current_state)
    current_modifiers = _rows_by_id(
        current_state, collection="path_modifiers", key="modifier_id"
    )
    reanalysis_reasons: list[str] = []
    if any(
        current_hypotheses[item]["status"] == "EXPIRED"
        for item in retired_hypothesis_ids
    ):
        reanalysis_reasons.append("HYPOTHESIS_EXPIRY_RETIREMENT")
    if any(
        current_hypotheses[item]["status"] == "FALSIFIED"
        for item in retired_hypothesis_ids
    ):
        reanalysis_reasons.append("HYPOTHESIS_FALSIFICATION_RETIREMENT")
    if retired_zone_ids:
        reanalysis_reasons.append("ZONE_EXPIRY_RETIREMENT")
    if any(
        current_modifiers[item]["status"] == "EXPIRED"
        for item in retired_modifier_ids
    ):
        reanalysis_reasons.append("PATH_MODIFIER_EXPIRY_RETIREMENT")
    if any(
        current_modifiers[item]["status"] == "FALSIFIED"
        for item in retired_modifier_ids
    ):
        reanalysis_reasons.append("PATH_MODIFIER_FALSIFICATION_RETIREMENT")
    reanalysis_reasons = sorted(reanalysis_reasons)

    receipt = {
        "schema_id": RECEIPT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "as_of": as_of,
        "current_state_digest": current_digest,
        "durable_previous_state_digest": previous_digest,
        "pit_evidence_registry_digest": pit_digest,
        "pit_evidence_availability_registry_digest": availability_digest,
        "durable_previous_pit_evidence_availability_registry_digest": (
            previous_availability_digest
        ),
        "public_market_analysis_bundle_digest": analysis_bundle_digest,
        "graph_dependency_registry_digest": graph_digest,
        "continued_hypothesis_ids": continued_ids,
        "new_hypothesis_ids": new_ids,
        "renewed_hypothesis_ids": renewed_ids,
        "retired_hypothesis_ids": retired_hypothesis_ids,
        "continued_zone_ids": continued_zone_ids,
        "new_zone_ids": new_zone_ids,
        "renewed_zone_ids": renewed_zone_ids,
        "retired_zone_ids": retired_zone_ids,
        "continued_path_modifier_ids": continued_modifier_ids,
        "new_path_modifier_ids": new_modifier_ids,
        "renewed_path_modifier_ids": renewed_modifier_ids,
        "retired_path_modifier_ids": retired_modifier_ids,
        "fresh_lifecycle_evidence_refs": sorted(fresh_lifecycle_refs),
        "lifecycle_reanalysis_required": bool(reanalysis_reasons),
        "lifecycle_reanalysis_reasons": reanalysis_reasons,
        "verified_path_modifier_ids": modifier_ids,
        "continuity_policy": (
            "DURABLE_PRIOR_ONLY_TERMINAL_TOMBSTONES_NO_SILENT_DISAPPEARANCE"
        ),
        "renewal_policy": (
            "STABLE_LINEAGE_MONOTONIC_REVISION_EXACT_PREDECESSOR_FINGERPRINT_"
            "NO_IN_PLACE_EXPIRY_EXTENSION_NEW_ID_AND_POSTDATING_FRESH_PIT_REQUIRED"
        ),
        "retirement_policy": (
            "DUE_OBJECT_TERMINAL_ZERO_ACTION_SUPPORT_AND_REANALYSIS_REQUIRED"
        ),
        "modifier_registry_policy": (
            "CURRENT_CYCLE_PIT_AND_GRAPH_MEMBERSHIP_BIDIRECTIONAL_AFFECTED_IDS"
        ),
        "evidence_dependency_closure_policy": (
            "FULL_UNION_PER_EVIDENCE_DIGEST_NO_CALLER_SUBSETS_OR_SPLIT_IDENTITY"
        ),
        "freshness_policy": (
            "DETERMINISTIC_SOURCE_BUNDLE_AVAILABILITY_GREATER_THAN_DURABLE_"
            "PREVIOUS_STATE_AND_PIT_CUTOFF_NOT_PREVIOUS_STATE_USAGE"
        ),
        "complete_registry_policy": (
            "ALL_REGIME_FEATURE_ZONE_HYPOTHESIS_MODIFIER_EVIDENCE_IN_PIT_"
            "TYPED_REGIME_FEATURE_OBSERVABLE_FAMILY_BINDING_AND_ALL_UNKNOWN_"
            "ZONE_HYPOTHESIS_MODIFIER_CLUSTER_DEPENDENCIES_IN_GRAPH"
        ),
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(receipt, RECEIPT_DIGEST_FIELD)


def verify_v32_dynamic_state_continuity_v1(
    document: Mapping[str, Any],
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    current_state: Mapping[str, Any],
    durable_previous_state: Mapping[str, Any] | None,
    durable_previous_state_digest: str | None,
    verified_pit_evidence_registry: Mapping[str, Any],
    verified_pit_evidence_registry_digest: str,
    verified_public_market_analysis_bundle: Mapping[str, Any],
    verified_pit_evidence_availability_registry: Mapping[str, Any],
    verified_pit_evidence_availability_registry_digest: str,
    durable_previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    durable_previous_pit_evidence_availability_registry_digest: str | None,
    verified_graph_dependency_registry: Mapping[str, Any],
    verified_graph_dependency_registry_digest: str,
) -> str:
    """Replay every continuity check and require exact receipt reconstruction."""

    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, RECEIPT_DIGEST_FIELD)
        rebuilt = compose_v32_dynamic_state_continuity_v1(
            public_evidence_verifier=public_evidence_verifier,
            current_state=current_state,
            durable_previous_state=durable_previous_state,
            durable_previous_state_digest=durable_previous_state_digest,
            verified_pit_evidence_registry=verified_pit_evidence_registry,
            verified_pit_evidence_registry_digest=(
                verified_pit_evidence_registry_digest
            ),
            verified_public_market_analysis_bundle=(
                verified_public_market_analysis_bundle
            ),
            verified_pit_evidence_availability_registry=(
                verified_pit_evidence_availability_registry
            ),
            verified_pit_evidence_availability_registry_digest=(
                verified_pit_evidence_availability_registry_digest
            ),
            durable_previous_pit_evidence_availability_registry=(
                durable_previous_pit_evidence_availability_registry
            ),
            durable_previous_pit_evidence_availability_registry_digest=(
                durable_previous_pit_evidence_availability_registry_digest
            ),
            verified_graph_dependency_registry=(
                verified_graph_dependency_registry
            ),
            verified_graph_dependency_registry_digest=(
                verified_graph_dependency_registry_digest
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DynamicStateContinuityError):
            raise
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_RECEIPT_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[RECEIPT_DIGEST_FIELD]
    ):
        raise V32DynamicStateContinuityError(
            "V32_CONTINUITY_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "GRAPH_REGISTRY_DIGEST_FIELD",
    "GRAPH_REGISTRY_SCHEMA_ID",
    "PIT_REGISTRY_DIGEST_FIELD",
    "PIT_REGISTRY_SCHEMA_ID",
    "PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD",
    "PIT_AVAILABILITY_REGISTRY_SCHEMA_ID",
    "RECEIPT_DIGEST_FIELD",
    "RECEIPT_SCHEMA_ID",
    "V32DynamicStateContinuityError",
    "build_v32_verified_pit_evidence_availability_registry_v1",
    "compose_v32_dynamic_state_continuity_v1",
    "verify_v32_verified_pit_evidence_availability_registry_v1",
    "verify_v32_dynamic_state_continuity_v1",
]
