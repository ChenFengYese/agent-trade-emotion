"""V3.1 adapters from legacy market snapshots to one Domain contract.

The two public entry points differ only at their source boundary.  Both return
the same ``PointInTimeDatum`` and ``InformationEvent`` objects, preserve raw
bindings when they exist, and materialize absent categories as explicit
UNKNOWN values.  This module performs no IO and makes no network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    verify_self_digest,
)
from ..domain.data_model import (
    ConflictState,
    DataModelError,
    DataQuality,
    DatumEpistemicType,
    DatumValueType,
    Missingness,
    PointInTimeDatum,
    ProxyLevel,
    QualityLevel,
    UncertaintyKind,
    UncertaintyRepresentation,
    admit_point_in_time_dataset,
    verify_point_in_time_dataset,
)
from ..domain.dynamic_research import MARKET_CATEGORIES
from ..domain.financial_evaluation import build_market_economics_snapshot
from ..domain.information_model import (
    ActorKind,
    ActorRole,
    ActorRoleAssignment,
    AudienceKind,
    AudienceSegment,
    CommitmentLevel,
    InformationActor,
    InformationChannel,
    InformationEvent,
    InformationForm,
    InformationModelError,
    InformationNovelty,
    InformationScope,
    InstitutionalStatus,
    ObservedFactKind,
    ObservedInformationFact,
    PropagationClass,
    Reversibility,
    RoleAssignmentBasis,
    SourceArtifactRef,
    SourceAcquisitionMethod,
    SourceAcquisitionReceipt,
    SourceCoverage,
    SourceEvidenceBoundary,
    SourceQuality,
    SourceType,
    admit_information_event,
    information_event_digest,
)


class V31MarketAdapterError(ValueError):
    """A legacy snapshot could not be mapped without inventing information."""


@dataclass(frozen=True, slots=True)
class V31MarketAdaptation:
    adapter_id: str
    run_id: str
    cycle_index: int
    source_snapshot_digest: str
    data: tuple[PointInTimeDatum, ...]
    information_events: tuple[InformationEvent, ...]
    dataset_document: Mapping[str, Any]
    revision_semantics: str = "GENESIS_PER_IMMUTABLE_SNAPSHOT"

    def __post_init__(self) -> None:
        if (
            not self.adapter_id
            or not self.run_id
            or self.cycle_index < 1
            or not re.fullmatch(r"[0-9a-f]{64}", self.source_snapshot_digest)
            or not self.data
            or not self.information_events
            or self.revision_semantics != "GENESIS_PER_IMMUTABLE_SNAPSHOT"
            or any(
                event.revision != 1
                or event.previous_revision_digest is not None
                or event.revised_at is not None
                or event.novelty is not InformationNovelty.NEW
                for event in self.information_events
            )
        ):
            raise V31MarketAdapterError("V31_MARKET_ADAPTATION_INVALID")


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_NATIVE_CONTRACT_SPECIFICATION_FIELDS = frozenset(
    {
        "instrument_id",
        "contract_multiplier",
        "contract_multiplier_unit",
        "contract_multiplier_source_field",
        "okx_ct_val",
        "okx_ct_mult",
        "contract_value_currency",
        "contract_type",
        "settlement_currency",
        "quantity_step_contracts",
        "minimum_quantity_contracts",
        "price_tick_usdt",
        "source_request_id",
        "source_raw_body_sha256",
        "available_at",
    }
)
_PUBLIC_CAPTURE_FIELDS = frozenset(
    {
        "request_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "response_received_at",
        "final_url",
        "http_status",
        "selected_response_headers",
        "response_headers_digest",
        "raw_body_sha256",
        "raw_body_byte_length",
        "request_identity_digest",
        "record_digest",
    }
)


def _time(value: Any, code: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise V31MarketAdapterError(code) from exc
    else:
        raise V31MarketAdapterError(code)
    if parsed.tzinfo is None:
        raise V31MarketAdapterError(code)
    return parsed.astimezone(UTC)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31MarketAdapterError(code)
    return value.strip()


def _positive_canonical_decimal(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise V31MarketAdapterError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise V31MarketAdapterError(code) from exc
    if (
        not parsed.is_finite()
        or parsed <= 0
        or canonical_decimal(parsed) != value
    ):
        raise V31MarketAdapterError(code)
    return value


def _verified_native_contract_specification(
    snapshot: Mapping[str, Any],
    *,
    information: Mapping[str, Any],
    captures: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Bind ``ctVal`` to the exact public-instrument capture and PIT fact."""

    specification = snapshot.get("contract_specification")
    if (
        not isinstance(specification, Mapping)
        or set(specification) != _NATIVE_CONTRACT_SPECIFICATION_FIELDS
    ):
        raise V31MarketAdapterError("V31_NATIVE_CONTRACT_SPECIFICATION_INVALID")
    numeric_fields = {
        field: _positive_canonical_decimal(
            specification.get(field),
            "V31_NATIVE_CONTRACT_SPECIFICATION_NUMERIC_INVALID",
        )
        for field in (
            "contract_multiplier",
            "okx_ct_val",
            "okx_ct_mult",
            "quantity_step_contracts",
            "minimum_quantity_contracts",
            "price_tick_usdt",
        )
    }
    multiplier = numeric_fields["contract_multiplier"]
    if (
        specification.get("instrument_id") != snapshot.get("instrument_id")
        or specification.get("contract_multiplier_unit") != "BTC_PER_CONTRACT"
        or specification.get("contract_multiplier_source_field") != "ctVal"
        or specification.get("okx_ct_val") != multiplier
        or specification.get("contract_value_currency") != "BTC"
        or specification.get("contract_type") != "linear"
        or specification.get("settlement_currency") != "USDT"
        or specification.get("source_request_id") != "okx-native-instrument"
        or not isinstance(specification.get("source_raw_body_sha256"), str)
        or _HEX_64.fullmatch(str(specification["source_raw_body_sha256"])) is None
    ):
        raise V31MarketAdapterError("V31_NATIVE_CONTRACT_SPECIFICATION_INVALID")
    if (
        Decimal(numeric_fields["minimum_quantity_contracts"])
        % Decimal(numeric_fields["quantity_step_contracts"])
        != 0
    ):
        raise V31MarketAdapterError(
            "V31_NATIVE_CONTRACT_QUANTITY_CONSTRAINTS_INVALID"
        )
    available_at = _time(
        specification.get("available_at"),
        "V31_NATIVE_CONTRACT_SPECIFICATION_TIME_INVALID",
    )
    capture_rows = [
        row
        for row in captures
        if isinstance(row, Mapping)
        and row.get("request_id") == specification.get("source_request_id")
    ]
    if len(capture_rows) != 1:
        raise V31MarketAdapterError("V31_NATIVE_CONTRACT_SOURCE_BINDING_INVALID")
    capture = capture_rows[0]
    if (
        capture.get("raw_body_sha256")
        != specification.get("source_raw_body_sha256")
        or _time(
            capture.get("response_received_at"),
            "V31_NATIVE_CONTRACT_SPECIFICATION_TIME_INVALID",
        )
        != available_at
    ):
        raise V31MarketAdapterError("V31_NATIVE_CONTRACT_SOURCE_BINDING_INVALID")
    facts = information.get("facts")
    fact_specs = {
        "instrument-contract-multiplier": (
            numeric_fields["contract_multiplier"],
            "BTC_PER_CONTRACT",
        ),
        "instrument-okx-ct-mult": (
            numeric_fields["okx_ct_mult"],
            "OKX_CT_MULT",
        ),
        "instrument-quantity-step-contracts": (
            numeric_fields["quantity_step_contracts"],
            "CONTRACTS",
        ),
        "instrument-minimum-quantity-contracts": (
            numeric_fields["minimum_quantity_contracts"],
            "CONTRACTS",
        ),
        "instrument-price-tick-usdt": (
            numeric_fields["price_tick_usdt"],
            "USDT_PER_BTC",
        ),
    }
    if not isinstance(facts, list):
        raise V31MarketAdapterError("V31_NATIVE_CONTRACT_FACT_MISSING")
    for fact_id, (expected_value, expected_unit) in fact_specs.items():
        rows = [
            row
            for row in facts
            if isinstance(row, Mapping) and row.get("fact_id") == fact_id
        ]
        if len(rows) != 1:
            raise V31MarketAdapterError("V31_NATIVE_CONTRACT_FACT_MISSING")
        fact = rows[0]
        if (
            fact.get("kind") != "RAW_FACT"
            or fact.get("metric") != fact_id
            or fact.get("value") != expected_value
            or fact.get("unit") != expected_unit
            or fact.get("source_ref") != specification.get("source_request_id")
            or fact.get("raw_sha256")
            != specification.get("source_raw_body_sha256")
            or _time(
                fact.get("available_at"),
                "V31_NATIVE_CONTRACT_SPECIFICATION_TIME_INVALID",
            )
            != available_at
            or fact.get("missing_reason") is not None
        ):
            raise V31MarketAdapterError(
                "V31_NATIVE_CONTRACT_FACT_BINDING_INVALID"
            )
    return dict(specification)


def _validate_public_capture(
    capture: Mapping[str, Any], *, cutoff: datetime
) -> Mapping[str, Any]:
    if not isinstance(capture, Mapping) or set(capture) != _PUBLIC_CAPTURE_FIELDS:
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_SCHEMA_INVALID")
    request_id = _text(capture.get("request_id"), "V31_SOURCE_CAPTURE_ID_INVALID")
    query = capture.get("query")
    headers = capture.get("selected_response_headers")
    if (
        capture.get("method") != "GET"
        or capture.get("base_url") != "https://www.okx.com"
        or not isinstance(capture.get("path"), str)
        or not str(capture["path"]).startswith("/")
        or not isinstance(query, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "value"}
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("value"), str)
            for row in query
        )
        or query != sorted(query, key=lambda row: str(row["name"]))
        or len({str(row["name"]) for row in query}) != len(query)
        or not isinstance(headers, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "value"}
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("value"), str)
            for row in headers
        )
        or headers != sorted(headers, key=lambda row: str(row["name"]))
        or len({str(row["name"]) for row in headers}) != len(headers)
        or capture.get("http_status") != 200
        or not isinstance(capture.get("raw_body_byte_length"), int)
        or isinstance(capture.get("raw_body_byte_length"), bool)
        or capture["raw_body_byte_length"] < 0
        or not isinstance(capture.get("final_url"), str)
        or not str(capture["final_url"]).startswith(
            f"{capture.get('base_url')}{capture.get('path')}"
        )
    ):
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_SEMANTICS_INVALID")
    started = _time(capture["request_started_at"], "V31_SOURCE_CAPTURE_TIME_INVALID")
    received = _time(capture["response_received_at"], "V31_SOURCE_CAPTURE_TIME_INVALID")
    if started > received or received > cutoff:
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_NOT_POINT_IN_TIME")
    for field in (
        "response_headers_digest",
        "raw_body_sha256",
        "request_identity_digest",
        "record_digest",
    ):
        if not isinstance(capture.get(field), str) or _HEX_64.fullmatch(capture[field]) is None:
            raise V31MarketAdapterError("V31_SOURCE_CAPTURE_DIGEST_INVALID")
    if canonical_digest(headers) != capture["response_headers_digest"]:
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_HEADER_DIGEST_INVALID")
    if canonical_digest(
        {
            "method": "GET",
            "base_url": capture["base_url"],
            "path": capture["path"],
            "query": query,
        }
    ) != capture["request_identity_digest"]:
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_REQUEST_DIGEST_INVALID")
    record_payload = dict(capture)
    record_payload.pop("record_digest")
    if canonical_digest(record_payload) != capture["record_digest"]:
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_RECORD_DIGEST_INVALID")
    return {**dict(capture), "request_id": request_id}


def _source_evidence(
    *,
    source_kind: str,
    locator: str,
    snapshot_digest: str,
    available_at: datetime,
    source_captures: Sequence[Mapping[str, Any]],
    required_request_ids: Sequence[str],
) -> tuple[SourceEvidenceBoundary, SourceAcquisitionReceipt, SourceQuality]:
    if source_kind == "SYNTHETIC":
        return (
            SourceEvidenceBoundary.LOCAL_SYNTHETIC,
            SourceAcquisitionReceipt(
                receipt_id=f"acquisition:{snapshot_digest}",
                evidence_boundary=SourceEvidenceBoundary.LOCAL_SYNTHETIC,
                acquisition_method=SourceAcquisitionMethod.LOCAL_SYNTHETIC_FIXTURE,
                source_locator=locator,
                acquired_at=available_at,
                content_sha256=snapshot_digest,
                request_ids=(),
                request_identity_digests=(),
                response_headers_digests=(),
                raw_body_sha256s=(),
                capture_record_digests=(),
                external_verifier_refs=(),
                external_verification_digests=(),
                limitations=(
                    "Local synthetic acquisition proves fixture replay only, not market validity.",
                ),
            ),
            SourceQuality.PARTIAL,
        )
    capture_rows = tuple(source_captures)
    required_ids = tuple(required_request_ids)
    if not capture_rows and not required_ids:
        return (
            SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED,
            SourceAcquisitionReceipt(
                receipt_id=f"acquisition:{snapshot_digest}",
                evidence_boundary=SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED,
                acquisition_method=SourceAcquisitionMethod.LOCAL_SNAPSHOT_IMPORT,
                source_locator=locator,
                acquired_at=available_at,
                content_sha256=snapshot_digest,
                request_ids=(),
                request_identity_digests=(),
                response_headers_digests=(),
                raw_body_sha256s=(),
                capture_record_digests=(),
                external_verifier_refs=(),
                external_verification_digests=(),
                limitations=(
                    "The self-digested local snapshot has no replayable transport acquisition evidence.",
                ),
            ),
            SourceQuality.UNVERIFIED,
        )
    if (
        not capture_rows
        or not required_ids
        or any(not isinstance(request_id, str) or not request_id for request_id in required_ids)
        or len(required_ids) != len(set(required_ids))
    ):
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_REQUIRED_SET_INVALID")
    validated = tuple(
        _validate_public_capture(row, cutoff=available_at) for row in capture_rows
    )
    by_id = {str(row["request_id"]): row for row in validated}
    if len(by_id) != len(validated) or not set(required_ids).issubset(by_id):
        raise V31MarketAdapterError("V31_SOURCE_CAPTURE_REQUIRED_SET_INCOMPLETE")
    ordered = tuple(by_id[key] for key in sorted(by_id))
    return (
        SourceEvidenceBoundary.SOURCE_ATTESTED,
        SourceAcquisitionReceipt(
            receipt_id=f"acquisition:{snapshot_digest}",
            evidence_boundary=SourceEvidenceBoundary.SOURCE_ATTESTED,
            acquisition_method=SourceAcquisitionMethod.PUBLIC_HTTP_CAPTURE,
            source_locator=locator,
            acquired_at=max(
                _time(row["response_received_at"], "V31_SOURCE_CAPTURE_TIME_INVALID")
                for row in ordered
            ),
            content_sha256=snapshot_digest,
            request_ids=tuple(str(row["request_id"]) for row in ordered),
            request_identity_digests=tuple(str(row["request_identity_digest"]) for row in ordered),
            response_headers_digests=tuple(str(row["response_headers_digest"]) for row in ordered),
            raw_body_sha256s=tuple(str(row["raw_body_sha256"]) for row in ordered),
            capture_record_digests=tuple(str(row["record_digest"]) for row in ordered),
            external_verifier_refs=(),
            external_verification_digests=(),
            limitations=(
                "Transport captures are replayable; no independent external verifier attests the normalized interpretation.",
            ),
        ),
        SourceQuality.VERIFIED_SECONDARY,
    )


def _facts(value: Any) -> list[Mapping[str, Any]]:
    if (
        not isinstance(value, (list, tuple))
        or not value
        or any(not isinstance(row, Mapping) for row in value)
    ):
        raise V31MarketAdapterError("V31_MARKET_FACTS_INVALID")
    rows = list(value)
    fact_ids = tuple(row.get("fact_id") for row in rows)
    if (
        any(not isinstance(fact_id, str) or not fact_id for fact_id in fact_ids)
        or len(fact_ids) != len(set(fact_ids))
    ):
        raise V31MarketAdapterError("V31_MARKET_FACT_IDS_INVALID")
    return rows


def _quality(
    *, legacy_quality: str, source_kind: str, missing: bool
) -> DataQuality:
    if missing:
        unknown = QualityLevel.UNKNOWN
        return DataQuality(
            source_reliability=unknown,
            completeness=QualityLevel.UNUSABLE,
            timeliness=unknown,
            semantic_fidelity=unknown,
            measurement_error=unknown,
            revision_risk=unknown,
            cross_source_consistency=unknown,
            lineage_integrity=unknown,
            dependency_independence=unknown,
            regime_applicability=unknown,
            limitations=(
                "The missingness observation is usable; the absent market value is not.",
            ),
        )

    base = {
        "GOOD": QualityLevel.HIGH,
        "DEGRADED": QualityLevel.MEDIUM,
        "STALE": QualityLevel.LOW,
    }.get(legacy_quality, QualityLevel.UNKNOWN)
    timeliness = QualityLevel.LOW if legacy_quality == "STALE" else base
    semantic = QualityLevel.LOW if source_kind == "SYNTHETIC" else base
    regime = QualityLevel.UNUSABLE if source_kind == "SYNTHETIC" else QualityLevel.UNKNOWN
    return DataQuality(
        source_reliability=base,
        completeness=base,
        timeliness=timeliness,
        semantic_fidelity=semantic,
        measurement_error=QualityLevel.UNKNOWN,
        revision_risk=QualityLevel.UNKNOWN,
        cross_source_consistency=QualityLevel.UNKNOWN,
        lineage_integrity=base,
        dependency_independence=QualityLevel.UNKNOWN,
        regime_applicability=regime,
        limitations=(
            "Synthetic chronology has no market-validity claim."
            if source_kind == "SYNTHETIC"
            else "A single public source does not establish cross-source consistency.",
        ),
    )


def _missingness(reason: str | None) -> Missingness:
    normalized = (reason or "").upper()
    if "NOT_AUTHORIZED" in normalized:
        return Missingness.NOT_AUTHORIZED
    if "FIRST_CYCLE" in normalized or "NOT_APPLICABLE" in normalized:
        return Missingness.NOT_APPLICABLE
    if "COVERAGE" in normalized:
        return Missingness.COVERAGE_INSUFFICIENT
    if "CONFLICT" in normalized:
        return Missingness.CONFLICTED
    if "UNAVAILABLE" in normalized or "NO_SOURCE" in normalized or "NOT_PRESENT" in normalized:
        return Missingness.SOURCE_UNAVAILABLE
    return Missingness.UNKNOWN


def _currency(unit: str) -> str | None:
    normalized = unit.upper()
    if "USDT" in normalized:
        return "USDT"
    if normalized in {"BTC", "ETH", "USD", "EUR", "CNY"}:
        return normalized
    return None


def _missing_category_fact(
    *, category: str, symbol: str, as_of: datetime
) -> dict[str, Any]:
    timestamp = as_of.isoformat().replace("+00:00", "Z")
    slug = category.lower()
    return {
        "fact_id": f"v31-adapter-unknown:{slug}",
        "kind": "RAW_FACT",
        "category": category,
        "metric": f"unavailable_{slug}",
        "value": None,
        "unit": "UNAVAILABLE",
        "symbol": symbol,
        "timeframe": "SNAPSHOT",
        "window": "CURRENT_CAPTURE",
        "source_ref": "NO_AUTHORIZED_SOURCE",
        "raw_ref": None,
        "raw_sha256": None,
        "observed_at": timestamp,
        "available_at": timestamp,
        "quality": "UNKNOWN",
        "coverage": "0",
        "dependency_group": f"V31_MISSING_{category}",
        "lineage": [],
        "transform": None,
        "limitations": "The source snapshot contained no fact for this required category.",
        "missing_reason": "CATEGORY_NOT_PRESENT_IN_SOURCE_SNAPSHOT",
    }


def _complete_categories(
    rows: Sequence[Mapping[str, Any]], *, symbol: str, as_of: datetime
) -> list[Mapping[str, Any]]:
    completed = list(rows)
    present = {str(row.get("category") or "") for row in completed}
    completed.extend(
        _missing_category_fact(category=category, symbol=symbol, as_of=as_of)
        for category in MARKET_CATEGORIES
        if category not in present
    )
    return completed


def _capture_event(
    *,
    source_kind: str,
    run_id: str,
    cycle_index: int,
    symbol: str,
    available_at: datetime,
    snapshot_digest: str,
    decision_at: datetime,
    source_captures: Sequence[Mapping[str, Any]],
    required_request_ids: Sequence[str],
) -> InformationEvent:
    synthetic = source_kind == "SYNTHETIC"
    actor_id = (
        "actor:v31:synthetic-fixture-collector"
        if synthetic
        else "actor:v31:okx-public-market-source"
    )
    identity_digest = snapshot_digest
    source_id = (
        f"source:v31:{source_kind.lower()}:{run_id}:{cycle_index}:{identity_digest}"
    )
    event_id = (
        "information-event:v31:capture-genesis:"
        f"{source_kind.lower()}:{run_id}:{cycle_index}:{identity_digest}"
    )
    locator = (
        f"snapshot://{source_kind.lower()}/{run_id}/{cycle_index}/{snapshot_digest}"
    )
    evidence_boundary, acquisition_receipt, source_quality = _source_evidence(
        source_kind=source_kind,
        locator=locator,
        snapshot_digest=snapshot_digest,
        available_at=available_at,
        source_captures=source_captures,
        required_request_ids=required_request_ids,
    )
    audience_id = "audience:v31:research-runtime"
    actor = InformationActor(
        actor_id=actor_id,
        display_name=(
            "Synthetic Fixture Collector" if synthetic else "OKX Public Market Source"
        ),
        actor_kind=ActorKind.ORGANIZATION,
        jurisdictions=(() if synthetic else ("PUBLIC_MARKET_SOURCE",)),
        provenance_refs=(source_id,),
        limitations=(
            "This actor exists only inside a synthetic contract fixture."
            if synthetic
            else "The venue is a source and intermediary; this label does not infer trader identity.",
        ),
    )
    source = SourceArtifactRef(
        artifact_id=source_id,
        publisher_actor_id=actor_id,
        locator=locator,
        source_type=(
            SourceType.DERIVED_SUMMARY if synthetic else SourceType.PRIMARY_MARKET_DATA
        ),
        channel=InformationChannel.DATA_FEED,
        propagation_class=PropagationClass.PRIMARY,
        quality=source_quality,
        coverage=SourceCoverage.FULL_TEXT,
        content_sha256=snapshot_digest,
        language="machine-readable-json",
        published_at=available_at,
        observed_at=available_at,
        available_at=available_at,
        provenance_refs=(f"snapshot-digest:{snapshot_digest}",),
        limitations=(
            "The digest binds a synthetic snapshot and carries no empirical market validity."
            if synthetic
            else "The digest binds the normalized snapshot, not an independent second source.",
        ),
        evidence_boundary=evidence_boundary,
        acquisition_receipt=acquisition_receipt,
    )
    role = ActorRoleAssignment(
        assignment_id=f"role:v31:capture:{source_kind.lower()}",
        actor_id=actor_id,
        role=(
            ActorRole.RULE_AND_SYSTEM_AUTHORITY
            if synthetic
            else ActorRole.LIQUIDITY_AND_INTERMEDIATION
        ),
        basis=(
            RoleAssignmentBasis.RESEARCH_CLASSIFICATION
            if synthetic
            else RoleAssignmentBasis.OBSERVED_MARKET_FUNCTION
        ),
        authority_scope=("SYNTHETIC_FIXTURE_ONLY" if synthetic else "PUBLIC_VENUE_DATA",),
        valid_from=available_at,
        valid_to=None,
        evidence_refs=(source_id,),
        limitations=(
            "Fixture authority is not market authority."
            if synthetic
            else "The role classification does not imply knowledge of venue intent.",
        ),
    )
    audience = AudienceSegment(
        segment_id=audience_id,
        label="Non-executable V3.1 research runtime",
        audience_kinds=(AudienceKind.PASSIVE_AND_RULE_BASED,),
        market_scopes=(symbol,),
        constraints=("point-in-time only", "no account or execution authority"),
        provenance_refs=("theory/history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md",),
        limitations=("This is a system audience, not a claim about market participants.",),
    )
    observed = ObservedInformationFact(
        fact_id=(
            f"fact:v31:capture-genesis:{source_kind.lower()}:{run_id}:"
            f"{cycle_index}:{identity_digest}"
        ),
        fact_kind=ObservedFactKind.OBSERVABLE_ACTION,
        statement=f"A {source_kind.lower()} snapshot for {symbol} became available.",
        source_artifact_ids=(source_id,),
        observed_at=available_at,
        limitations=("Capture availability is observed; market direction is not inferred.",),
    )
    event = InformationEvent(
        event_id=event_id,
        revision=1,
        previous_revision_digest=None,
        primary_actor_id=actor_id,
        actors=(actor,),
        actor_role_assignments=(role,),
        scopes=(InformationScope.INSTRUMENT,),
        information_form=InformationForm.DISCLOSURE,
        institutional_status=InstitutionalStatus.UNKNOWN,
        channel=InformationChannel.DATA_FEED,
        audiences=(audience,),
        observable_message_or_action=observed.statement,
        novelty=InformationNovelty.NEW,
        commitment=CommitmentLevel.NON_BINDING,
        reversibility=Reversibility.UNKNOWN,
        propagation_class=PropagationClass.PRIMARY,
        published_at=available_at,
        observed_at=available_at,
        available_at=available_at,
        effective_at=available_at,
        revised_at=None,
        source_artifacts=(source,),
        observed_facts=(observed,),
        intent_hypotheses=(),
        behavior_response_hypotheses=(),
        limitations=(
            "This is a content-addressed genesis capture, not an update or revision of an earlier event.",
            "This technical capture event provides lineage only and is not a directional market event.",
        ),
    )
    admit_information_event(event, decision_at=decision_at)
    return event


def _to_datum(
    row: Mapping[str, Any],
    *,
    source_kind: str,
    run_id: str,
    cycle_index: int,
    as_of: datetime,
    symbol: str,
    venue_id: str | None,
    event: InformationEvent,
    input_bindings: Mapping[str, PointInTimeDatum],
) -> PointInTimeDatum:
    capture_identity = event.event_id.rsplit(":", 1)[-1]
    fact_id = _text(row.get("fact_id"), "V31_MARKET_FACT_ID_INVALID")
    kind = str(row.get("kind") or "")
    if kind not in {"RAW_FACT", "DERIVED_FEATURE"}:
        raise V31MarketAdapterError("V31_MARKET_FACT_KIND_INVALID")
    category = _text(row.get("category"), "V31_MARKET_CATEGORY_INVALID")
    if category not in MARKET_CATEGORIES:
        raise V31MarketAdapterError("V31_MARKET_CATEGORY_INVALID")
    metric = _text(row.get("metric"), "V31_MARKET_METRIC_INVALID")
    value = row.get("value")
    if value is not None and not isinstance(value, str):
        raise V31MarketAdapterError("V31_MARKET_VALUE_INVALID")
    missing = value is None
    reason = row.get("missing_reason")
    if missing and (not isinstance(reason, str) or not reason.strip()):
        raise V31MarketAdapterError("V31_MARKET_MISSING_REASON_REQUIRED")
    if not missing and reason is not None:
        raise V31MarketAdapterError("V31_MARKET_OBSERVED_REASON_FORBIDDEN")
    observed_at = _time(row.get("observed_at"), "V31_MARKET_OBSERVED_TIME_INVALID")
    available_at = _time(row.get("available_at"), "V31_MARKET_AVAILABLE_TIME_INVALID")
    if observed_at > available_at or available_at > as_of:
        raise V31MarketAdapterError("V31_MARKET_FACT_PIT_INVALID")

    raw_ref_value = row.get("raw_ref")
    raw_sha_value = row.get("raw_sha256")
    raw_ref = (
        raw_ref_value
        if isinstance(raw_ref_value, str)
        and raw_ref_value.strip()
        and raw_ref_value != "UNAVAILABLE"
        and isinstance(raw_sha_value, str)
        and _HEX_64.fullmatch(raw_sha_value)
        else None
    )
    raw_sha = raw_sha_value if raw_ref is not None else None
    if not missing and (raw_ref is None or raw_sha is None):
        raise V31MarketAdapterError("V31_MARKET_OBSERVED_RAW_BINDING_INVALID")
    unbound_raw_limitation = (
        (f"Legacy unbound raw reference was not admitted: {raw_ref_value}",)
        if raw_ref is None and isinstance(raw_ref_value, str) and raw_ref_value != "UNAVAILABLE"
        else ()
    )

    legacy_lineage = row.get("lineage")
    if not isinstance(legacy_lineage, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in legacy_lineage
    ):
        raise V31MarketAdapterError("V31_MARKET_LINEAGE_INVALID")
    legacy_input_refs = tuple(legacy_lineage) if kind == "DERIVED_FEATURE" else ()
    transform = row.get("transform")
    if kind == "DERIVED_FEATURE" and (
        not legacy_input_refs or not isinstance(transform, str) or not transform.strip()
    ):
        raise V31MarketAdapterError("V31_MARKET_DERIVED_LINEAGE_INVALID")
    if kind == "RAW_FACT" and (legacy_lineage or transform is not None):
        raise V31MarketAdapterError("V31_MARKET_RAW_DERIVATION_FORBIDDEN")

    source_ref = _text(row.get("source_ref"), "V31_MARKET_SOURCE_REF_INVALID")
    source_type = (
        "NO_AUTHORIZED_SOURCE"
        if missing and raw_ref is None
        else "SYNTHETIC_FIXTURE"
        if source_kind == "SYNTHETIC"
        else "OKX_OFFICIAL_PUBLIC"
    )
    quality_name = str(row.get("quality") or "UNKNOWN")
    limitations_value = row.get("limitations")
    limitations = (
        (limitations_value.strip(),)
        if isinstance(limitations_value, str) and limitations_value.strip()
        else ()
    )
    if not limitations:
        raise V31MarketAdapterError("V31_MARKET_LIMITATIONS_REQUIRED")
    limitations += unbound_raw_limitation
    limitations += (
        "Adapted from a legacy snapshot without adding directional interpretation.",
        "This datum is a content-addressed genesis observation; revision 1 does not claim an update to an earlier datum.",
    )
    dependency_group = _text(
        row.get("dependency_group"), "V31_MARKET_DEPENDENCY_GROUP_INVALID"
    )
    timeframe = _text(row.get("timeframe"), "V31_MARKET_TIMEFRAME_INVALID")
    unit_value = _text(row.get("unit"), "V31_MARKET_UNIT_INVALID")
    if kind == "DERIVED_FEATURE":
        if not set(legacy_input_refs).issubset(input_bindings):
            raise V31MarketAdapterError("V31_MARKET_DERIVED_INPUT_UNKNOWN")
        input_refs = tuple(input_bindings[item].datum_id for item in legacy_input_refs)
        input_digests = tuple(
            input_bindings[item].to_document()["datum_digest"]
            for item in legacy_input_refs
        )
    else:
        input_refs = ()
        input_digests = ()
    if unit_value == "SHA256":
        value_type = DatumValueType.DIGEST
    elif unit_value == "BOOLEAN":
        value_type = DatumValueType.BOOLEAN
    else:
        value_type = DatumValueType.NUMERIC

    return PointInTimeDatum(
        datum_id=(
            f"datum:v31:genesis:{source_kind.lower()}:{run_id}:{cycle_index}:"
            f"{capture_identity}:{fact_id}"
        ),
        epistemic_type=(
            DatumEpistemicType.OBSERVED_FACT
            if kind == "RAW_FACT"
            else DatumEpistemicType.DERIVED_MEASURE
        ),
        data_kind="MARKET_FACT" if kind == "RAW_FACT" else "MARKET_DERIVED_MEASURE",
        category=category,
        metric=metric,
        value=value,
        value_type=value_type,
        unit=unit_value,
        currency=_currency(unit_value),
        frequency=timeframe,
        timeframe=timeframe,
        window=_text(row.get("window"), "V31_MARKET_WINDOW_INVALID"),
        instrument_id=symbol,
        asset_class=("SYNTHETIC" if source_kind == "SYNTHETIC" else "CRYPTO_DERIVATIVE"),
        venue_id=venue_id,
        entity_ids=(),
        actor_ids=(event.primary_actor_id,),
        audience_ids=(),
        event_ids=(event.event_id,),
        source_id=f"source:v31:{source_kind.lower()}:{source_ref}",
        source_type=source_type,
        source_ref=source_ref,
        raw_ref=raw_ref,
        raw_sha256=raw_sha,
        # ``as_of`` on a datum is the economic/reference time of that
        # observation, not the later snapshot capture cutoff.  Closed candles
        # and other lagged public facts are normally observed before the final
        # response arrives; using the capture cutoff here reverses the Domain
        # invariant ``as_of <= observed_at <= available_at``.
        as_of=observed_at,
        observed_at=observed_at,
        published_at=None,
        available_at=available_at,
        effective_at=observed_at,
        revised_at=None,
        vintage_id=(
            f"vintage:genesis:{source_kind.lower()}:{run_id}:{cycle_index}:"
            f"{capture_identity}"
        ),
        revision=1,
        revision_of_digest=None,
        formula_version=(transform.strip() if kind == "DERIVED_FEATURE" else None),
        input_refs=input_refs,
        input_digests=input_digests,
        quality=_quality(
            legacy_quality=quality_name, source_kind=source_kind, missing=missing
        ),
        coverage=row.get("coverage"),
        missingness=(Missingness.OBSERVED if not missing else _missingness(reason)),
        missing_reason=(None if not missing else reason.strip()),
        staleness=("STALE" if quality_name == "STALE" else "CURRENT_AT_CAPTURE"),
        conflict_state=(ConflictState.NONE if not missing else ConflictState.UNKNOWN),
        proxy_level=(ProxyLevel.DIRECT if kind == "RAW_FACT" else ProxyLevel.MODEL_DERIVED),
        uncertainty=UncertaintyRepresentation(
            kind=(
                UncertaintyKind.NONE_DECLARED
                if not missing and kind == "RAW_FACT"
                else UncertaintyKind.UNKNOWN
            ),
            assumptions=(
                "No numerical uncertainty was supplied by the legacy source."
                if not missing
                else "The value is unavailable and has not been imputed.",
            ),
        ),
        regime_ref=None,
        dependency_group=dependency_group,
        lineage=tuple(legacy_lineage),
        limitations=limitations,
    )


def _adapt(
    *,
    source_kind: str,
    adapter_id: str,
    run_id: str,
    cycle_index: int,
    symbol: str,
    as_of: datetime,
    decision_at: datetime,
    source_snapshot_digest: str,
    facts: Sequence[Mapping[str, Any]],
    venue_id: str | None,
    source_captures: Sequence[Mapping[str, Any]] = (),
    required_request_ids: Sequence[str] = (),
) -> V31MarketAdaptation:
    if not run_id or cycle_index < 1 or not symbol:
        raise V31MarketAdapterError("V31_MARKET_IDENTITY_INVALID")
    cutoff = _time(decision_at, "V31_MARKET_DECISION_TIME_INVALID")
    try:
        event = _capture_event(
            source_kind=source_kind,
            run_id=run_id,
            cycle_index=cycle_index,
            symbol=symbol,
            available_at=as_of,
            snapshot_digest=source_snapshot_digest,
            decision_at=cutoff,
            source_captures=source_captures,
            required_request_ids=required_request_ids,
        )
        source = event.source_artifacts[0]
        if source.evidence_boundary is SourceEvidenceBoundary.SOURCE_ATTESTED:
            receipt = source.acquisition_receipt
            if receipt is None:  # pragma: no cover - enforced by Domain contract
                raise V31MarketAdapterError("V31_SOURCE_ATTESTATION_MISSING")
            admitted_raw_digests = set(receipt.raw_body_sha256s)
            fact_raw_digests = {
                str(row["raw_sha256"])
                for row in facts
                if row.get("value") is not None
                and isinstance(row.get("raw_sha256"), str)
            }
            if not fact_raw_digests or not fact_raw_digests.issubset(
                admitted_raw_digests
            ):
                raise V31MarketAdapterError(
                    "V31_SOURCE_ATTESTATION_FACT_BINDING_INVALID"
                )
        completed = _complete_categories(facts, symbol=symbol, as_of=as_of)
        legacy_ids = [str(row.get("fact_id") or "") for row in completed]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise V31MarketAdapterError("V31_MARKET_FACT_ID_DUPLICATE")
        bound_by_legacy_id: dict[str, PointInTimeDatum] = {}
        pending = list(completed)
        while pending:
            progress = False
            for row in tuple(pending):
                kind = str(row.get("kind") or "")
                lineage = tuple(row.get("lineage") or ())
                if kind == "DERIVED_FEATURE" and not set(lineage).issubset(
                    bound_by_legacy_id
                ):
                    continue
                datum = _to_datum(
                    row,
                    source_kind=source_kind,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    as_of=as_of,
                    symbol=symbol,
                    venue_id=venue_id,
                    event=event,
                    input_bindings=bound_by_legacy_id,
                )
                bound_by_legacy_id[str(row["fact_id"])] = datum
                pending.remove(row)
                progress = True
            if not progress:
                raise V31MarketAdapterError(
                    "V31_MARKET_DERIVED_INPUT_UNKNOWN_OR_CYCLIC"
                )
        data = tuple(bound_by_legacy_id[fact_id] for fact_id in legacy_ids)
        dataset = admit_point_in_time_dataset(
            dataset_id=(
                f"dataset:v31:genesis:{source_kind.lower()}:{run_id}:"
                f"{cycle_index}:{source_snapshot_digest}"
            ),
            decision_at=cutoff,
            data=data,
        )
    except V31MarketAdapterError:
        raise
    except (DataModelError, InformationModelError) as exc:
        raise V31MarketAdapterError(f"V31_MARKET_DOMAIN_REJECTED:{exc}") from exc
    return V31MarketAdaptation(
        adapter_id=adapter_id,
        run_id=run_id,
        cycle_index=cycle_index,
        source_snapshot_digest=source_snapshot_digest,
        data=data,
        information_events=(event,),
        dataset_document=dataset,
    )


def adapt_synthetic_fixture_snapshot(
    snapshot: Mapping[str, Any],
    *,
    run_id: str,
    cycle_index: int,
    as_of: datetime | str,
    decision_at: datetime | str,
) -> V31MarketAdaptation:
    """Map a ``SyntheticMarketDataCollector`` result to the V3.1 contracts."""

    if not isinstance(snapshot, Mapping):
        raise V31MarketAdapterError("V31_SYNTHETIC_SNAPSHOT_INVALID")
    as_of_time = _time(as_of, "V31_SYNTHETIC_AS_OF_INVALID")
    cutoff = _time(decision_at, "V31_MARKET_DECISION_TIME_INVALID")
    rows = _facts(snapshot.get("facts"))
    symbol_values = {str(row.get("symbol") or "") for row in rows}
    if len(symbol_values) != 1 or "" in symbol_values:
        raise V31MarketAdapterError("V31_SYNTHETIC_SYMBOL_INVALID")
    symbol = next(iter(symbol_values))
    if "market_information_snapshot_digest" in snapshot:
        try:
            digest = verify_self_digest(
                snapshot, "market_information_snapshot_digest"
            )
        except ValueError as exc:
            raise V31MarketAdapterError(
                "V31_SYNTHETIC_SNAPSHOT_DIGEST_INVALID"
            ) from exc
        if (
            snapshot.get("run_id") != run_id
            or snapshot.get("cycle_index") != cycle_index
            or snapshot.get("symbol") != symbol
            or _time(snapshot.get("as_of"), "V31_SYNTHETIC_SNAPSHOT_TIME_INVALID")
            != as_of_time
            or snapshot.get("missing_values_are_zero") is not False
        ):
            raise V31MarketAdapterError("V31_SYNTHETIC_SNAPSHOT_IDENTITY_INVALID")
    else:
        digest = canonical_digest(dict(snapshot))
    return _adapt(
        source_kind="SYNTHETIC",
        adapter_id="V31_SYNTHETIC_FIXTURE_ADAPTER_V1",
        run_id=run_id,
        cycle_index=cycle_index,
        symbol=symbol,
        as_of=as_of_time,
        decision_at=cutoff,
        source_snapshot_digest=digest,
        facts=rows,
        venue_id=None,
    )


def adapt_native_public_snapshot(
    snapshot: Mapping[str, Any],
    *,
    decision_at: datetime | str,
) -> V31MarketAdaptation:
    """Map a verified native/public snapshot to the same V3.1 contracts."""

    if not isinstance(snapshot, Mapping):
        raise V31MarketAdapterError("V31_NATIVE_SNAPSHOT_INVALID")
    try:
        snapshot_digest = verify_self_digest(
            snapshot, "native_market_snapshot_digest"
        )
    except ValueError as exc:
        raise V31MarketAdapterError("V31_NATIVE_SNAPSHOT_DIGEST_INVALID") from exc
    information = snapshot.get("market_information_snapshot")
    if not isinstance(information, Mapping):
        raise V31MarketAdapterError("V31_NATIVE_INFORMATION_SNAPSHOT_MISSING")
    try:
        verify_self_digest(information, "market_information_snapshot_digest")
    except ValueError as exc:
        raise V31MarketAdapterError("V31_NATIVE_INFORMATION_DIGEST_INVALID") from exc
    if snapshot.get("point_in_time") is not True or snapshot.get("missing_is_zero") is not False:
        raise V31MarketAdapterError("V31_NATIVE_PIT_SEMANTICS_INVALID")
    schema_version = snapshot.get("schema_version")
    if (
        snapshot.get("schema_id") != "native_btc_public_market_snapshot"
        or schema_version not in {"1.0.0", "1.1.0"}
    ):
        raise V31MarketAdapterError("V31_NATIVE_SNAPSHOT_SCHEMA_INVALID")
    run_id = _text(snapshot.get("run_id"), "V31_NATIVE_RUN_ID_INVALID")
    cycle_index = snapshot.get("cycle_index")
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise V31MarketAdapterError("V31_NATIVE_CYCLE_INVALID")
    symbol = _text(snapshot.get("instrument_id"), "V31_NATIVE_INSTRUMENT_INVALID")
    if (
        information.get("run_id") != run_id
        or information.get("cycle_index") != cycle_index
        or information.get("symbol") != symbol
        or information.get("missing_values_are_zero") is not False
    ):
        raise V31MarketAdapterError("V31_NATIVE_INFORMATION_IDENTITY_INVALID")
    captured = _time(snapshot.get("captured_through"), "V31_NATIVE_CAPTURE_TIME_INVALID")
    if _time(information.get("as_of"), "V31_NATIVE_AS_OF_INVALID") != captured:
        raise V31MarketAdapterError("V31_NATIVE_CAPTURE_TIME_MISMATCH")
    source_captures = snapshot.get("source_captures")
    required_request_ids = snapshot.get("required_request_ids")
    if not isinstance(source_captures, list) or not isinstance(
        required_request_ids, list
    ):
        raise V31MarketAdapterError("V31_NATIVE_SOURCE_EVIDENCE_SCHEMA_INVALID")
    if schema_version == "1.1.0":
        _verified_native_contract_specification(
            snapshot,
            information=information,
            captures=source_captures,
        )
    return _adapt(
        source_kind="NATIVE_PUBLIC",
        adapter_id="V31_NATIVE_PUBLIC_ADAPTER_V1",
        run_id=run_id,
        cycle_index=cycle_index,
        symbol=symbol,
        as_of=captured,
        decision_at=_time(decision_at, "V31_MARKET_DECISION_TIME_INVALID"),
        source_snapshot_digest=snapshot_digest,
        facts=_facts(information.get("facts")),
        venue_id="OKX",
        source_captures=source_captures,
        required_request_ids=required_request_ids,
    )


def native_financial_market_economics_input(
    *,
    snapshot: Mapping[str, Any],
    adaptation: V31MarketAdaptation,
    long_protective_stop_price: str,
    short_protective_stop_price: str,
) -> dict[str, str]:
    """Build a formal financial-evaluation input from one V1.1 public capture.

    The two protective stops remain preregistered policy inputs.  The symbol,
    PIT mark, contract multiplier, and availability time must instead agree
    across the raw-bound snapshot, information layer, and admitted PIT dataset.
    Legacy V1.0 snapshots remain readable for audit but cannot enter this formal
    financial path because they did not persist ``ctVal``.
    """

    if not isinstance(snapshot, Mapping) or not isinstance(
        adaptation, V31MarketAdaptation
    ):
        raise V31MarketAdapterError("V31_NATIVE_FINANCIAL_INPUT_INVALID")
    try:
        snapshot_digest = verify_self_digest(
            snapshot, "native_market_snapshot_digest"
        )
        verified_dataset_rows = verify_point_in_time_dataset(
            adaptation.dataset_document
        )
    except (DataModelError, ValueError) as exc:
        raise V31MarketAdapterError(
            "V31_NATIVE_FINANCIAL_INPUT_DIGEST_INVALID"
        ) from exc
    if snapshot.get("schema_version") != "1.1.0":
        raise V31MarketAdapterError(
            "V31_NATIVE_FINANCIAL_CONTRACT_SPECIFICATION_REQUIRED"
        )
    information = snapshot.get("market_information_snapshot")
    captures = snapshot.get("source_captures")
    if not isinstance(information, Mapping) or not isinstance(captures, list):
        raise V31MarketAdapterError("V31_NATIVE_FINANCIAL_INPUT_INVALID")
    specification = _verified_native_contract_specification(
        snapshot,
        information=information,
        captures=captures,
    )
    if (
        adaptation.adapter_id != "V31_NATIVE_PUBLIC_ADAPTER_V1"
        or adaptation.source_snapshot_digest != snapshot_digest
        or adaptation.run_id != snapshot.get("run_id")
        or adaptation.cycle_index != snapshot.get("cycle_index")
        or tuple(adaptation.data) != tuple(verified_dataset_rows)
        or adaptation.dataset_document.get("data")
        != [row.to_document() for row in adaptation.data]
    ):
        raise V31MarketAdapterError(
            "V31_NATIVE_FINANCIAL_ADAPTATION_BINDING_INVALID"
        )
    by_metric: dict[str, list[PointInTimeDatum]] = {}
    for datum in adaptation.data:
        by_metric.setdefault(datum.metric, []).append(datum)
    mark_rows = by_metric.get("mark-price", [])
    contract_metric_specs = {
        "instrument-contract-multiplier": (
            "contract_multiplier",
            "BTC_PER_CONTRACT",
        ),
        "instrument-okx-ct-mult": ("okx_ct_mult", "OKX_CT_MULT"),
        "instrument-quantity-step-contracts": (
            "quantity_step_contracts",
            "CONTRACTS",
        ),
        "instrument-minimum-quantity-contracts": (
            "minimum_quantity_contracts",
            "CONTRACTS",
        ),
        "instrument-price-tick-usdt": (
            "price_tick_usdt",
            "USDT_PER_BTC",
        ),
    }
    contract_rows = {
        metric: by_metric.get(metric, [])
        for metric in contract_metric_specs
    }
    if len(mark_rows) != 1 or any(
        len(rows) != 1 for rows in contract_rows.values()
    ):
        raise V31MarketAdapterError("V31_NATIVE_FINANCIAL_DATUM_MISSING")
    mark = mark_rows[0]
    if (
        mark.value != snapshot.get("mark_price")
        or mark.value_type is not DatumValueType.NUMERIC
        or mark.missingness is not Missingness.OBSERVED
        or mark.raw_sha256 is None
    ):
        raise V31MarketAdapterError(
            "V31_NATIVE_FINANCIAL_DATUM_BINDING_INVALID"
        )
    for metric, (specification_field, expected_unit) in (
        contract_metric_specs.items()
    ):
        datum = contract_rows[metric][0]
        if (
            datum.value != specification[specification_field]
            or datum.unit != expected_unit
            or datum.value_type is not DatumValueType.NUMERIC
            or datum.missingness is not Missingness.OBSERVED
            or datum.raw_sha256 != specification["source_raw_body_sha256"]
            or datum.raw_ref is None
        ):
            raise V31MarketAdapterError(
                "V31_NATIVE_FINANCIAL_DATUM_BINDING_INVALID"
            )
    available_at = max(
        mark.available_at,
        *(rows[0].available_at for rows in contract_rows.values()),
    )
    multiplier = contract_rows["instrument-contract-multiplier"][0]
    raw_input = {
        "symbol": str(snapshot["instrument_id"]),
        "available_at": available_at.isoformat().replace("+00:00", "Z"),
        "mark_price": _positive_canonical_decimal(
            mark.value, "V31_NATIVE_FINANCIAL_MARK_INVALID"
        ),
        "contract_multiplier": _positive_canonical_decimal(
            multiplier.value,
            "V31_NATIVE_FINANCIAL_CONTRACT_MULTIPLIER_INVALID",
        ),
        "contract_size_multiplier": _positive_canonical_decimal(
            specification["okx_ct_mult"],
            "V31_NATIVE_FINANCIAL_CONTRACT_SIZE_MULTIPLIER_INVALID",
        ),
        "quantity_step_contracts": _positive_canonical_decimal(
            specification["quantity_step_contracts"],
            "V31_NATIVE_FINANCIAL_QUANTITY_STEP_INVALID",
        ),
        "minimum_quantity_contracts": _positive_canonical_decimal(
            specification["minimum_quantity_contracts"],
            "V31_NATIVE_FINANCIAL_MINIMUM_QUANTITY_INVALID",
        ),
        "price_tick_usdt": _positive_canonical_decimal(
            specification["price_tick_usdt"],
            "V31_NATIVE_FINANCIAL_PRICE_TICK_INVALID",
        ),
        "long_protective_stop_price": long_protective_stop_price,
        "short_protective_stop_price": short_protective_stop_price,
    }
    try:
        normalized = build_market_economics_snapshot(
            decision_at=str(adaptation.dataset_document["decision_at"]),
            market_economics=raw_input,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31MarketAdapterError(
            "V31_NATIVE_FINANCIAL_MARKET_ECONOMICS_INVALID"
        ) from exc
    return {
        field: str(normalized[field])
        for field in (
            "symbol",
            "available_at",
            "mark_price",
            "contract_multiplier",
            "contract_size_multiplier",
            "quantity_step_contracts",
            "minimum_quantity_contracts",
            "price_tick_usdt",
            "long_protective_stop_price",
            "short_protective_stop_price",
        )
    }


__all__ = [
    "V31MarketAdaptation",
    "V31MarketAdapterError",
    "adapt_native_public_snapshot",
    "adapt_synthetic_fixture_snapshot",
    "native_financial_market_economics_input",
]
