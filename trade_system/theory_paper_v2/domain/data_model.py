"""Unified point-in-time data ontology for V3.1.

The legacy fact contract remains readable, while this module defines the
successor schema shared by synthetic and public-market adapters.  It keeps
source time, observation time, availability, effective time, vintage and
revision separate, and it never converts missing values into zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_decimal, canonical_digest


class DataModelError(ValueError):
    """A data object violated PIT, lineage, quality, or revision semantics."""


class DatumEpistemicType(StrEnum):
    OBSERVED_FACT = "OBSERVED_FACT"
    DERIVED_MEASURE = "DERIVED_MEASURE"
    ASSOCIATION_ESTIMATE = "ASSOCIATION_ESTIMATE"
    LATENT_FACTOR_ESTIMATE = "LATENT_FACTOR_ESTIMATE"
    REGIME_ESTIMATE = "REGIME_ESTIMATE"


class DatumValueType(StrEnum):
    NUMERIC = "NUMERIC"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    CATEGORY = "CATEGORY"
    DIGEST = "DIGEST"


class Missingness(StrEnum):
    OBSERVED = "OBSERVED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class ConflictState(StrEnum):
    NONE = "NONE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    SEMANTIC_CONFLICT = "SEMANTIC_CONFLICT"
    UNKNOWN = "UNKNOWN"


class ProxyLevel(StrEnum):
    DIRECT = "DIRECT"
    FIRST_ORDER_PROXY = "FIRST_ORDER_PROXY"
    SECOND_ORDER_PROXY = "SECOND_ORDER_PROXY"
    MODEL_DERIVED = "MODEL_DERIVED"
    UNKNOWN = "UNKNOWN"


class UncertaintyKind(StrEnum):
    NONE_DECLARED = "NONE_DECLARED"
    ORDINAL = "ORDINAL"
    INTERVAL = "INTERVAL"
    DISTRIBUTION_REF = "DISTRIBUTION_REF"
    MODEL_ENSEMBLE = "MODEL_ENSEMBLE"
    UNKNOWN = "UNKNOWN"


class QualityLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNUSABLE = "UNUSABLE"
    UNKNOWN = "UNKNOWN"


_DATUM_DOCUMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "datum_id",
        "epistemic_type",
        "data_kind",
        "category",
        "metric",
        "value",
        "value_type",
        "unit",
        "currency",
        "frequency",
        "timeframe",
        "window",
        "instrument_id",
        "asset_class",
        "venue_id",
        "entity_ids",
        "actor_ids",
        "audience_ids",
        "event_ids",
        "source_id",
        "source_type",
        "source_ref",
        "raw_ref",
        "raw_sha256",
        "as_of",
        "observed_at",
        "published_at",
        "available_at",
        "effective_at",
        "revised_at",
        "vintage_id",
        "revision",
        "revision_of_digest",
        "formula_version",
        "input_refs",
        "input_digests",
        "quality",
        "coverage",
        "missingness",
        "missing_reason",
        "staleness",
        "conflict_state",
        "proxy_level",
        "uncertainty",
        "regime_ref",
        "dependency_group",
        "lineage",
        "limitations",
        "hypothesis_admissible",
        "inference_admissible",
        "claim_ceiling",
        "missing_is_zero",
        "executable",
        "datum_digest",
    }
)

_DATASET_DOCUMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "dataset_id",
        "decision_at",
        "data",
        "observed_count",
        "unknown_count",
        "hypothesis_admissible_count",
        "inference_admissible_count",
        "hypothesis_only_datum_ids",
        "quarantined_datum_ids",
        "missing_is_zero",
        "point_in_time",
        "executable",
        "dataset_digest",
    }
)


def _aware(value: datetime, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DataModelError(code)
    return value.astimezone(UTC)


def _time(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    )


def _strings(
    value: Sequence[str], code: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise DataModelError(code)
    result = tuple(value)
    if (not allow_empty and not result) or any(
        not isinstance(item, str) or not item.strip() for item in result
    ) or len(result) != len(set(result)):
        raise DataModelError(code)
    return result


def _coverage(value: Decimal | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise DataModelError("DATA_BINARY_FLOAT_FORBIDDEN")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DataModelError("DATA_COVERAGE_INVALID") from exc
    if not result.is_finite() or result < 0 or result > 1:
        raise DataModelError("DATA_COVERAGE_INVALID")
    return result


@dataclass(frozen=True, slots=True)
class DataQuality:
    source_reliability: QualityLevel
    completeness: QualityLevel
    timeliness: QualityLevel
    semantic_fidelity: QualityLevel
    measurement_error: QualityLevel
    revision_risk: QualityLevel
    cross_source_consistency: QualityLevel
    lineage_integrity: QualityLevel
    dependency_independence: QualityLevel
    regime_applicability: QualityLevel
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "source_reliability",
            "completeness",
            "timeliness",
            "semantic_fidelity",
            "measurement_error",
            "revision_risk",
            "cross_source_consistency",
            "lineage_integrity",
            "dependency_independence",
            "regime_applicability",
        ):
            if not isinstance(getattr(self, field_name), QualityLevel):
                raise DataModelError("DATA_QUALITY_LEVEL_INVALID")
        object.__setattr__(
            self,
            "limitations",
            _strings(self.limitations, "DATA_QUALITY_LIMITATIONS_INVALID", allow_empty=True),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name).value
            for field_name in (
                "source_reliability",
                "completeness",
                "timeliness",
                "semantic_fidelity",
                "measurement_error",
                "revision_risk",
                "cross_source_consistency",
                "lineage_integrity",
                "dependency_independence",
                "regime_applicability",
            )
        } | {"limitations": list(self.limitations)}


@dataclass(frozen=True, slots=True)
class UncertaintyRepresentation:
    kind: UncertaintyKind
    lower: str | None = None
    upper: str | None = None
    distribution_ref: str | None = None
    ordinal_level: str | None = None
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, UncertaintyKind):
            raise DataModelError("DATA_UNCERTAINTY_KIND_INVALID")
        object.__setattr__(
            self,
            "assumptions",
            _strings(self.assumptions, "DATA_UNCERTAINTY_ASSUMPTIONS_INVALID", allow_empty=True),
        )
        if self.kind is UncertaintyKind.INTERVAL:
            if self.lower is None or self.upper is None:
                raise DataModelError("DATA_UNCERTAINTY_INTERVAL_REQUIRED")
            try:
                lower = Decimal(self.lower)
                upper = Decimal(self.upper)
                if not lower.is_finite() or not upper.is_finite() or lower > upper:
                    raise DataModelError("DATA_UNCERTAINTY_INTERVAL_INVALID")
            except InvalidOperation as exc:
                raise DataModelError("DATA_UNCERTAINTY_INTERVAL_INVALID") from exc
            object.__setattr__(self, "lower", canonical_decimal(lower))
            object.__setattr__(self, "upper", canonical_decimal(upper))
        elif self.lower is not None or self.upper is not None:
            raise DataModelError("DATA_UNCERTAINTY_INTERVAL_FORBIDDEN")
        if self.kind in {
            UncertaintyKind.DISTRIBUTION_REF,
            UncertaintyKind.MODEL_ENSEMBLE,
        }:
            if not isinstance(self.distribution_ref, str) or not self.distribution_ref:
                raise DataModelError("DATA_UNCERTAINTY_DISTRIBUTION_REF_REQUIRED")
        elif self.distribution_ref is not None:
            raise DataModelError("DATA_UNCERTAINTY_DISTRIBUTION_REF_FORBIDDEN")
        if self.kind is UncertaintyKind.ORDINAL:
            if not isinstance(self.ordinal_level, str) or not self.ordinal_level.strip():
                raise DataModelError("DATA_UNCERTAINTY_ORDINAL_LEVEL_REQUIRED")
        elif self.ordinal_level is not None:
            raise DataModelError("DATA_UNCERTAINTY_ORDINAL_LEVEL_FORBIDDEN")

    def to_document(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "lower": self.lower,
            "upper": self.upper,
            "distribution_ref": self.distribution_ref,
            "ordinal_level": self.ordinal_level,
            "assumptions": list(self.assumptions),
        }


@dataclass(frozen=True, slots=True)
class PointInTimeDatum:
    datum_id: str
    epistemic_type: DatumEpistemicType
    data_kind: str
    category: str
    metric: str
    value: str | None
    value_type: DatumValueType
    unit: str
    currency: str | None
    frequency: str
    timeframe: str
    window: str
    instrument_id: str | None
    asset_class: str | None
    venue_id: str | None
    entity_ids: tuple[str, ...]
    actor_ids: tuple[str, ...]
    audience_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    source_id: str
    source_type: str
    source_ref: str
    raw_ref: str | None
    raw_sha256: str | None
    as_of: datetime
    observed_at: datetime
    published_at: datetime | None
    available_at: datetime
    effective_at: datetime | None
    revised_at: datetime | None
    vintage_id: str
    revision: int
    revision_of_digest: str | None
    formula_version: str | None
    input_refs: tuple[str, ...]
    input_digests: tuple[str, ...]
    quality: DataQuality
    coverage: Decimal | str | None
    missingness: Missingness
    missing_reason: str | None
    staleness: str
    conflict_state: ConflictState
    proxy_level: ProxyLevel
    uncertainty: UncertaintyRepresentation
    regime_ref: str | None
    dependency_group: str
    lineage: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "datum_id",
            "data_kind",
            "category",
            "metric",
            "unit",
            "frequency",
            "timeframe",
            "window",
            "source_id",
            "source_type",
            "source_ref",
            "vintage_id",
            "staleness",
            "dependency_group",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DataModelError("DATA_REQUIRED_TEXT_INVALID")
        for field_name in (
            "currency",
            "instrument_id",
            "asset_class",
            "venue_id",
            "raw_ref",
            "raw_sha256",
            "revision_of_digest",
            "formula_version",
            "missing_reason",
            "regime_ref",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise DataModelError("DATA_OPTIONAL_TEXT_INVALID")
        if not isinstance(self.epistemic_type, DatumEpistemicType):
            raise DataModelError("DATA_EPISTEMIC_TYPE_INVALID")
        if not isinstance(self.value_type, DatumValueType):
            raise DataModelError("DATA_VALUE_TYPE_INVALID")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise DataModelError("DATA_REVISION_INVALID")
        for field_name in (
            "entity_ids",
            "actor_ids",
            "audience_ids",
            "event_ids",
            "input_refs",
            "input_digests",
            "lineage",
            "limitations",
        ):
            object.__setattr__(
                self,
                field_name,
                _strings(getattr(self, field_name), "DATA_REFS_INVALID", allow_empty=True),
            )
        for field_name in ("as_of", "observed_at", "available_at"):
            object.__setattr__(
                self,
                field_name,
                _aware(getattr(self, field_name), "DATA_TIME_INVALID"),
            )
        for field_name in ("published_at", "effective_at", "revised_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _aware(value, "DATA_TIME_INVALID"))
        if self.published_at is not None and self.available_at < self.published_at:
            raise DataModelError("DATA_AVAILABLE_PRECEDES_PUBLICATION")
        if self.as_of > self.observed_at:
            raise DataModelError("DATA_AS_OF_AFTER_OBSERVATION")
        if self.observed_at > self.available_at:
            raise DataModelError("DATA_AVAILABLE_PRECEDES_OBSERVATION")
        if self.revised_at is not None and not (
            self.as_of <= self.revised_at <= self.observed_at
        ):
            raise DataModelError("DATA_REVISION_TIME_INVALID")
        if not isinstance(self.quality, DataQuality):
            raise DataModelError("DATA_QUALITY_INVALID")
        if not isinstance(self.uncertainty, UncertaintyRepresentation):
            raise DataModelError("DATA_UNCERTAINTY_INVALID")
        if not isinstance(self.missingness, Missingness) or not isinstance(
            self.conflict_state, ConflictState
        ) or not isinstance(self.proxy_level, ProxyLevel):
            raise DataModelError("DATA_STATUS_ENUM_INVALID")
        object.__setattr__(self, "coverage", _coverage(self.coverage))
        if self.value is None:
            if self.missingness is Missingness.OBSERVED or not (
                isinstance(self.missing_reason, str) and self.missing_reason.strip()
            ):
                raise DataModelError("DATA_MISSINGNESS_CONTRACT_INVALID")
        elif (
            not isinstance(self.value, str)
            or self.missingness is not Missingness.OBSERVED
            or self.missing_reason is not None
        ):
            raise DataModelError("DATA_OBSERVED_VALUE_CONTRACT_INVALID")
        if self.value is not None:
            if self.value_type is DatumValueType.NUMERIC:
                try:
                    numeric_value = Decimal(self.value)
                except InvalidOperation as exc:
                    raise DataModelError("DATA_NUMERIC_VALUE_INVALID") from exc
                if not numeric_value.is_finite():
                    raise DataModelError("DATA_NUMERIC_VALUE_INVALID")
            elif self.value_type is DatumValueType.BOOLEAN and self.value not in {
                "true",
                "false",
            }:
                raise DataModelError("DATA_BOOLEAN_VALUE_INVALID")
            elif self.value_type is DatumValueType.DIGEST and re.fullmatch(
                r"[0-9a-f]{64}", self.value
            ) is None:
                raise DataModelError("DATA_DIGEST_VALUE_INVALID")
            elif self.value_type in {DatumValueType.TEXT, DatumValueType.CATEGORY} and not self.value.strip():
                raise DataModelError("DATA_TEXT_VALUE_INVALID")
        derived = self.epistemic_type is not DatumEpistemicType.OBSERVED_FACT
        if derived and (
            not self.formula_version
            or not self.input_refs
            or len(self.input_refs) != len(self.input_digests)
            or any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in self.input_digests)
        ):
            raise DataModelError("DATA_DERIVED_LINEAGE_REQUIRED")
        if not derived and (
            self.formula_version is not None or self.input_refs or self.input_digests
        ):
            raise DataModelError("DATA_OBSERVED_FACT_DERIVATION_FORBIDDEN")
        if self.revision == 1 and self.revision_of_digest is not None:
            raise DataModelError("DATA_GENESIS_REVISION_DIGEST_FORBIDDEN")
        if self.revision == 1 and self.revised_at is not None:
            raise DataModelError("DATA_GENESIS_REVISION_TIME_FORBIDDEN")
        if self.revision > 1 and (
            not isinstance(self.revision_of_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.revision_of_digest) is None
        ):
            raise DataModelError("DATA_PRIOR_REVISION_DIGEST_REQUIRED")
        if self.revision > 1 and self.revised_at is None:
            raise DataModelError("DATA_REVISION_TIME_REQUIRED")
        if self.raw_ref is None and self.raw_sha256 is not None:
            raise DataModelError("DATA_RAW_BINDING_INVALID")
        if self.raw_ref is not None and (
            not isinstance(self.raw_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is None
        ):
            raise DataModelError("DATA_RAW_BINDING_INVALID")

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_id": "theory_paper_v2_v31_point_in_time_datum",
            "schema_version": "1.0.0",
            "datum_id": self.datum_id,
            "epistemic_type": self.epistemic_type.value,
            "data_kind": self.data_kind,
            "category": self.category,
            "metric": self.metric,
            "value": self.value,
            "value_type": self.value_type.value,
            "unit": self.unit,
            "currency": self.currency,
            "frequency": self.frequency,
            "timeframe": self.timeframe,
            "window": self.window,
            "instrument_id": self.instrument_id,
            "asset_class": self.asset_class,
            "venue_id": self.venue_id,
            "entity_ids": list(self.entity_ids),
            "actor_ids": list(self.actor_ids),
            "audience_ids": list(self.audience_ids),
            "event_ids": list(self.event_ids),
            "source_id": self.source_id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "raw_ref": self.raw_ref,
            "raw_sha256": self.raw_sha256,
            "as_of": _time(self.as_of),
            "observed_at": _time(self.observed_at),
            "published_at": _time(self.published_at),
            "available_at": _time(self.available_at),
            "effective_at": _time(self.effective_at),
            "revised_at": _time(self.revised_at),
            "vintage_id": self.vintage_id,
            "revision": self.revision,
            "revision_of_digest": self.revision_of_digest,
            "formula_version": self.formula_version,
            "input_refs": list(self.input_refs),
            "input_digests": list(self.input_digests),
            "quality": self.quality.to_document(),
            "coverage": (
                canonical_decimal(self.coverage) if self.coverage is not None else None
            ),
            "missingness": self.missingness.value,
            "missing_reason": self.missing_reason,
            "staleness": self.staleness,
            "conflict_state": self.conflict_state.value,
            "proxy_level": self.proxy_level.value,
            "uncertainty": self.uncertainty.to_document(),
            "regime_ref": self.regime_ref,
            "dependency_group": self.dependency_group,
            "lineage": list(self.lineage),
            "limitations": list(self.limitations),
            "hypothesis_admissible": _hypothesis_admissible(self),
            "inference_admissible": _inference_admissible(self),
            "claim_ceiling": _claim_ceiling(self),
            "missing_is_zero": False,
            "executable": False,
        }
        document["datum_digest"] = canonical_digest(document)
        return document


def _document_time(value: Any, code: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise DataModelError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataModelError(code) from exc
    if parsed.tzinfo is None:
        raise DataModelError(code)
    parsed = parsed.astimezone(UTC)
    if _time(parsed) != value:
        raise DataModelError(code)
    return parsed


def _document_string_tuple(value: Any, code: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DataModelError(code)
    return _strings(value, code, allow_empty=True)


def point_in_time_datum_from_document(
    document: Mapping[str, Any],
) -> PointInTimeDatum:
    """Reconstruct and fully revalidate one canonical PIT datum document.

    A public hash only proves byte identity.  This function deliberately
    rebuilds the typed domain object and then requires an exact canonical
    round trip, so a caller cannot alter an enum, revision, quality result, or
    computed admission flag and merely sign the edited mapping again.
    """

    if (
        not isinstance(document, Mapping)
        or set(document) != _DATUM_DOCUMENT_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_v31_point_in_time_datum"
        or document.get("schema_version") != "1.0.0"
    ):
        raise DataModelError("DATA_DOCUMENT_SCHEMA_INVALID")
    supplied_digest = document.get("datum_digest")
    payload = dict(document)
    payload.pop("datum_digest", None)
    if (
        not isinstance(supplied_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", supplied_digest) is None
        or canonical_digest(payload) != supplied_digest
    ):
        raise DataModelError("DATA_DOCUMENT_DIGEST_INVALID")
    quality = document.get("quality")
    uncertainty = document.get("uncertainty")
    if not isinstance(quality, Mapping) or set(quality) != {
        "source_reliability",
        "completeness",
        "timeliness",
        "semantic_fidelity",
        "measurement_error",
        "revision_risk",
        "cross_source_consistency",
        "lineage_integrity",
        "dependency_independence",
        "regime_applicability",
        "limitations",
    }:
        raise DataModelError("DATA_DOCUMENT_QUALITY_SCHEMA_INVALID")
    if not isinstance(uncertainty, Mapping) or set(uncertainty) != {
        "kind",
        "lower",
        "upper",
        "distribution_ref",
        "ordinal_level",
        "assumptions",
    }:
        raise DataModelError("DATA_DOCUMENT_UNCERTAINTY_SCHEMA_INVALID")
    try:
        rebuilt = PointInTimeDatum(
            datum_id=document["datum_id"],
            epistemic_type=DatumEpistemicType(document["epistemic_type"]),
            data_kind=document["data_kind"],
            category=document["category"],
            metric=document["metric"],
            value=document["value"],
            value_type=DatumValueType(document["value_type"]),
            unit=document["unit"],
            currency=document["currency"],
            frequency=document["frequency"],
            timeframe=document["timeframe"],
            window=document["window"],
            instrument_id=document["instrument_id"],
            asset_class=document["asset_class"],
            venue_id=document["venue_id"],
            entity_ids=_document_string_tuple(
                document["entity_ids"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            actor_ids=_document_string_tuple(
                document["actor_ids"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            audience_ids=_document_string_tuple(
                document["audience_ids"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            event_ids=_document_string_tuple(
                document["event_ids"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            source_id=document["source_id"],
            source_type=document["source_type"],
            source_ref=document["source_ref"],
            raw_ref=document["raw_ref"],
            raw_sha256=document["raw_sha256"],
            as_of=_document_time(document["as_of"], "DATA_DOCUMENT_TIME_INVALID"),
            observed_at=_document_time(
                document["observed_at"], "DATA_DOCUMENT_TIME_INVALID"
            ),
            published_at=_document_time(
                document["published_at"],
                "DATA_DOCUMENT_TIME_INVALID",
                optional=True,
            ),
            available_at=_document_time(
                document["available_at"], "DATA_DOCUMENT_TIME_INVALID"
            ),
            effective_at=_document_time(
                document["effective_at"],
                "DATA_DOCUMENT_TIME_INVALID",
                optional=True,
            ),
            revised_at=_document_time(
                document["revised_at"],
                "DATA_DOCUMENT_TIME_INVALID",
                optional=True,
            ),
            vintage_id=document["vintage_id"],
            revision=document["revision"],
            revision_of_digest=document["revision_of_digest"],
            formula_version=document["formula_version"],
            input_refs=_document_string_tuple(
                document["input_refs"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            input_digests=_document_string_tuple(
                document["input_digests"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            quality=DataQuality(
                source_reliability=QualityLevel(quality["source_reliability"]),
                completeness=QualityLevel(quality["completeness"]),
                timeliness=QualityLevel(quality["timeliness"]),
                semantic_fidelity=QualityLevel(quality["semantic_fidelity"]),
                measurement_error=QualityLevel(quality["measurement_error"]),
                revision_risk=QualityLevel(quality["revision_risk"]),
                cross_source_consistency=QualityLevel(
                    quality["cross_source_consistency"]
                ),
                lineage_integrity=QualityLevel(quality["lineage_integrity"]),
                dependency_independence=QualityLevel(
                    quality["dependency_independence"]
                ),
                regime_applicability=QualityLevel(
                    quality["regime_applicability"]
                ),
                limitations=_document_string_tuple(
                    quality["limitations"], "DATA_DOCUMENT_QUALITY_INVALID"
                ),
            ),
            coverage=document["coverage"],
            missingness=Missingness(document["missingness"]),
            missing_reason=document["missing_reason"],
            staleness=document["staleness"],
            conflict_state=ConflictState(document["conflict_state"]),
            proxy_level=ProxyLevel(document["proxy_level"]),
            uncertainty=UncertaintyRepresentation(
                kind=UncertaintyKind(uncertainty["kind"]),
                lower=uncertainty["lower"],
                upper=uncertainty["upper"],
                distribution_ref=uncertainty["distribution_ref"],
                ordinal_level=uncertainty["ordinal_level"],
                assumptions=_document_string_tuple(
                    uncertainty["assumptions"],
                    "DATA_DOCUMENT_UNCERTAINTY_INVALID",
                ),
            ),
            regime_ref=document["regime_ref"],
            dependency_group=document["dependency_group"],
            lineage=_document_string_tuple(
                document["lineage"], "DATA_DOCUMENT_REFS_INVALID"
            ),
            limitations=_document_string_tuple(
                document["limitations"], "DATA_DOCUMENT_REFS_INVALID"
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DataModelError):
            raise
        raise DataModelError("DATA_DOCUMENT_SEMANTICS_INVALID") from exc
    if rebuilt.to_document() != dict(document):
        raise DataModelError("DATA_DOCUMENT_CANONICAL_ROUNDTRIP_MISMATCH")
    return rebuilt


def point_in_time_dataset_rows_from_document(
    document: Mapping[str, Any],
) -> tuple[PointInTimeDatum, ...]:
    """Validate a dataset envelope and reconstruct every contained datum.

    Revision continuity is intentionally checked by
    :func:`verify_point_in_time_dataset`, because that check may require the
    prior cycle's exact rows.  All computed counts and quarantine fields are
    nevertheless recomputed here.
    """

    if (
        not isinstance(document, Mapping)
        or set(document) != _DATASET_DOCUMENT_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_v31_point_in_time_dataset"
        or document.get("schema_version") != "1.0.0"
        or document.get("point_in_time") is not True
        or document.get("missing_is_zero") is not False
        or document.get("executable") is not False
        or not isinstance(document.get("dataset_id"), str)
        or not str(document["dataset_id"]).strip()
    ):
        raise DataModelError("DATASET_DOCUMENT_SCHEMA_INVALID")
    supplied_digest = document.get("dataset_digest")
    payload = dict(document)
    payload.pop("dataset_digest", None)
    if (
        not isinstance(supplied_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", supplied_digest) is None
        or canonical_digest(payload) != supplied_digest
    ):
        raise DataModelError("DATASET_DOCUMENT_DIGEST_INVALID")
    _document_time(document.get("decision_at"), "DATASET_DOCUMENT_TIME_INVALID")
    raw_rows = document.get("data")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise DataModelError("DATASET_DOCUMENT_ROWS_INVALID")
    rows = tuple(point_in_time_datum_from_document(row) for row in raw_rows)
    if len({row.datum_id for row in rows}) != len(rows):
        raise DataModelError("DATASET_DATUM_IDS_INVALID")
    expected_hypothesis_only = [
        row.datum_id
        for row in rows
        if _hypothesis_admissible(row) and not _inference_admissible(row)
    ]
    expected_quarantine = [
        row.datum_id for row in rows if not _inference_admissible(row)
    ]
    for field in (
        "observed_count",
        "unknown_count",
        "hypothesis_admissible_count",
        "inference_admissible_count",
    ):
        value = document.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise DataModelError("DATASET_DOCUMENT_COUNTS_INVALID")
    if (
        document["observed_count"] != sum(row.value is not None for row in rows)
        or document["unknown_count"] != sum(row.value is None for row in rows)
        or document["hypothesis_admissible_count"]
        != sum(_hypothesis_admissible(row) for row in rows)
        or document["inference_admissible_count"]
        != sum(_inference_admissible(row) for row in rows)
        or document.get("hypothesis_only_datum_ids")
        != expected_hypothesis_only
        or document.get("quarantined_datum_ids") != expected_quarantine
    ):
        raise DataModelError("DATASET_DOCUMENT_COMPUTED_FIELDS_INVALID")
    return rows


def verify_point_in_time_dataset(
    document: Mapping[str, Any],
    *,
    prior_revisions: Mapping[str, PointInTimeDatum] | None = None,
    external_inputs: Mapping[str, PointInTimeDatum] | None = None,
) -> tuple[PointInTimeDatum, ...]:
    """Rebuild a PIT dataset and require exact equality with domain output."""

    rows = point_in_time_dataset_rows_from_document(document)
    decision_at = _document_time(
        document["decision_at"], "DATASET_DOCUMENT_TIME_INVALID"
    )
    rebuilt = admit_point_in_time_dataset(
        dataset_id=str(document["dataset_id"]),
        decision_at=decision_at,
        data=rows,
        prior_revisions=prior_revisions,
        external_inputs=external_inputs,
    )
    if rebuilt != dict(document):
        raise DataModelError("DATASET_DOCUMENT_CANONICAL_ROUNDTRIP_MISMATCH")
    return rows


def admit_point_in_time_dataset(
    *,
    dataset_id: str,
    decision_at: datetime,
    data: Sequence[PointInTimeDatum],
    prior_revisions: Mapping[str, PointInTimeDatum] | None = None,
    external_inputs: Mapping[str, PointInTimeDatum] | None = None,
) -> dict[str, Any]:
    """Admit a finite dataset and verify PIT plus append-only revisions."""

    cutoff = _aware(decision_at, "DATA_DECISION_TIME_INVALID")
    rows = tuple(data)
    if not isinstance(dataset_id, str) or not dataset_id.strip() or not rows:
        raise DataModelError("DATASET_INVALID")
    ids = tuple(row.datum_id for row in rows if isinstance(row, PointInTimeDatum))
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        raise DataModelError("DATASET_DATUM_IDS_INVALID")
    priors = dict(prior_revisions or {})
    external = dict(external_inputs or {})
    if any(
        key != value.datum_id or not isinstance(value, PointInTimeDatum)
        for key, value in external.items()
    ):
        raise DataModelError("DATASET_EXTERNAL_INPUTS_INVALID")
    catalog = {**external, **{row.datum_id: row for row in rows}}
    for row in rows:
        if row.available_at > cutoff:
            raise DataModelError("DATASET_FUTURE_INFORMATION_FORBIDDEN")
        prior = priors.get(row.datum_id)
        if row.revision == 1:
            if prior is not None:
                raise DataModelError("DATASET_GENESIS_PRIOR_CONFLICT")
            continue
        if prior is None or row.revision != prior.revision + 1:
            raise DataModelError("DATASET_REVISION_SEQUENCE_INVALID")
        if row.revision_of_digest != prior.to_document()["datum_digest"]:
            raise DataModelError("DATASET_REVISION_DIGEST_MISMATCH")
        if row.available_at <= prior.available_at:
            raise DataModelError("DATASET_REVISION_AVAILABILITY_INVALID")
        if _revision_identity(row) != _revision_identity(prior):
            raise DataModelError("DATASET_REVISION_IDENTITY_CHANGED")
    for row in rows:
        if row.epistemic_type is DatumEpistemicType.OBSERVED_FACT:
            continue
        for input_ref, input_digest in zip(row.input_refs, row.input_digests):
            source = catalog.get(input_ref)
            if source is None:
                raise DataModelError("DATASET_DERIVED_INPUT_MISSING")
            if source.to_document()["datum_digest"] != input_digest:
                raise DataModelError("DATASET_DERIVED_INPUT_DIGEST_MISMATCH")
            if source.available_at > row.available_at or source.available_at > cutoff:
                raise DataModelError("DATASET_DERIVED_INPUT_NOT_PIT")
    _assert_derived_graph_acyclic(rows)
    document = {
        "schema_id": "theory_paper_v2_v31_point_in_time_dataset",
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "decision_at": _time(cutoff),
        "data": [row.to_document() for row in rows],
        "observed_count": sum(row.value is not None for row in rows),
        "unknown_count": sum(row.value is None for row in rows),
        "hypothesis_admissible_count": sum(
            _hypothesis_admissible(row) for row in rows
        ),
        "inference_admissible_count": sum(_inference_admissible(row) for row in rows),
        "hypothesis_only_datum_ids": [
            row.datum_id
            for row in rows
            if _hypothesis_admissible(row) and not _inference_admissible(row)
        ],
        "quarantined_datum_ids": [
            row.datum_id for row in rows if not _inference_admissible(row)
        ],
        "missing_is_zero": False,
        "point_in_time": True,
        "executable": False,
    }
    document["dataset_digest"] = canonical_digest(document)
    return document


def _revision_identity(row: PointInTimeDatum) -> tuple[Any, ...]:
    """Fields whose semantic change requires a new datum id, not a revision."""

    return (
        row.epistemic_type,
        row.data_kind,
        row.category,
        row.metric,
        row.value_type,
        row.unit,
        row.currency,
        row.frequency,
        row.timeframe,
        row.window,
        row.instrument_id,
        row.asset_class,
        row.venue_id,
        row.entity_ids,
        row.actor_ids,
        row.audience_ids,
        row.event_ids,
        row.source_id,
        row.source_type,
        row.source_ref,
        row.formula_version,
        row.input_refs,
        row.dependency_group,
    )


def _assert_derived_graph_acyclic(rows: Sequence[PointInTimeDatum]) -> None:
    graph = {
        row.datum_id: tuple(
            ref for ref in row.input_refs if ref in {item.datum_id for item in rows}
        )
        for row in rows
        if row.epistemic_type is not DatumEpistemicType.OBSERVED_FACT
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise DataModelError("DATASET_DERIVED_INPUT_CYCLE")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, ()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _inference_admissible(row: PointInTimeDatum) -> bool:
    return _claim_ceiling(row) == "ASSOCIATION_OR_HYPOTHESIS_ONLY"


def _hypothesis_admissible(row: PointInTimeDatum) -> bool:
    return _claim_ceiling(row) != "NO_INFERENCE"


def _claim_ceiling(row: PointInTimeDatum) -> str:
    """Return the strongest epistemic use justified by the quality vector.

    The ceiling is deliberately ordinal.  It does not average heterogeneous
    quality dimensions into a score and it never upgrades a conflicted,
    missing, zero-coverage, or explicitly unusable value into inference input.
    Partial coverage and weak provenance may still be described or used to
    form a visibly limited hypothesis, but they cannot support a stronger
    association/model claim.
    """

    critical_levels = (
        row.quality.source_reliability,
        row.quality.completeness,
        row.quality.timeliness,
        row.quality.semantic_fidelity,
        row.quality.lineage_integrity,
    )
    all_levels = critical_levels + (
        row.quality.measurement_error,
        row.quality.revision_risk,
        row.quality.cross_source_consistency,
        row.quality.dependency_independence,
        row.quality.regime_applicability,
    )
    if (
        row.value is None
        or row.missingness is not Missingness.OBSERVED
        or row.coverage is None
        or row.coverage == 0
        or row.conflict_state is not ConflictState.NONE
        or QualityLevel.UNUSABLE in all_levels
    ):
        return "NO_INFERENCE"
    if (
        any(level in {QualityLevel.LOW, QualityLevel.UNKNOWN} for level in critical_levels)
        or row.coverage < 1
        or row.proxy_level
        in {ProxyLevel.SECOND_ORDER_PROXY, ProxyLevel.UNKNOWN}
    ):
        return "DESCRIPTIVE_OR_HYPOTHESIS_ONLY"
    return "ASSOCIATION_OR_HYPOTHESIS_ONLY"


_DATUM_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "previous_registry_digest",
        "known_datum_ids",
        "latest_revisions",
        "current_cycle_datum_digests",
        "current_inference_active_datum_ids",
        "history_retention",
        "external_execution_authority",
        "executable",
        "datum_revision_registry_digest",
    }
)


def _verify_datum_registry(
    registry: Mapping[str, Any], *, expected_run_id: str | None = None
) -> str:
    if (
        not isinstance(registry, Mapping)
        or set(registry) != _DATUM_REGISTRY_FIELDS
        or registry.get("schema_id")
        != "theory_paper_v2_v31_datum_revision_registry"
        or registry.get("schema_version") != "1.0.0"
        or registry.get("history_retention") != "ALL_KNOWN_IDS_LATEST_REVISION_ONLY"
        or registry.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or registry.get("executable") is not False
        or not isinstance(registry.get("run_id"), str)
        or not registry["run_id"]
        or (
            expected_run_id is not None
            and registry.get("run_id") != expected_run_id
        )
        or isinstance(registry.get("cycle_index"), bool)
        or not isinstance(registry.get("cycle_index"), int)
        or registry["cycle_index"] < 1
    ):
        raise DataModelError("DATUM_REGISTRY_SCHEMA_INVALID")
    decision = _document_time(
        registry.get("decision_at"), "DATUM_REGISTRY_TIME_INVALID"
    )
    supplied = registry.get("datum_revision_registry_digest")
    payload = dict(registry)
    payload.pop("datum_revision_registry_digest", None)
    if (
        not isinstance(supplied, str)
        or re.fullmatch(r"[0-9a-f]{64}", supplied) is None
        or canonical_digest(payload) != supplied
    ):
        raise DataModelError("DATUM_REGISTRY_DIGEST_INVALID")
    known = registry.get("known_datum_ids")
    latest = registry.get("latest_revisions")
    current_digests = registry.get("current_cycle_datum_digests")
    active_ids = registry.get("current_inference_active_datum_ids")
    if (
        not isinstance(known, list)
        or known != sorted(known)
        or len(known) != len(set(known))
        or any(not isinstance(value, str) or not value for value in known)
        or not isinstance(latest, list)
        or not isinstance(current_digests, list)
        or len(current_digests) != len(set(current_digests))
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in current_digests
        )
        or not isinstance(active_ids, list)
        or active_ids != sorted(active_ids)
        or len(active_ids) != len(set(active_ids))
    ):
        raise DataModelError("DATUM_REGISTRY_CONTENT_INVALID")
    latest_rows = tuple(point_in_time_datum_from_document(row) for row in latest)
    latest_ids = [row.datum_id for row in latest_rows]
    if latest_ids != sorted(latest_ids) or latest_ids != known:
        raise DataModelError("DATUM_REGISTRY_KNOWN_IDS_NOT_RETAINED")
    if any(row.available_at > decision for row in latest_rows):
        raise DataModelError("DATUM_REGISTRY_FUTURE_REVISION")
    if not set(active_ids).issubset(set(known)):
        raise DataModelError("DATUM_REGISTRY_ACTIVE_IDS_INVALID")
    previous_digest = registry.get("previous_registry_digest")
    if registry["cycle_index"] == 1:
        if previous_digest is not None:
            raise DataModelError("DATUM_REGISTRY_GENESIS_INVALID")
    elif (
        not isinstance(previous_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", previous_digest) is None
    ):
        raise DataModelError("DATUM_REGISTRY_PREDECESSOR_INVALID")
    return supplied


def build_point_in_time_datum_revision_registry(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: datetime,
    dataset: Mapping[str, Any],
    previous_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Retain all datum identities and reject revision-one resurrection."""

    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
    ):
        raise DataModelError("DATUM_REGISTRY_IDENTITY_INVALID")
    cutoff = _aware(decision_at, "DATUM_REGISTRY_TIME_INVALID")
    latest: dict[str, PointInTimeDatum] = {}
    previous_digest: str | None = None
    if previous_registry is None:
        if cycle_index != 1:
            raise DataModelError("DATUM_REGISTRY_PREDECESSOR_REQUIRED")
    else:
        previous_digest = _verify_datum_registry(
            previous_registry, expected_run_id=run_id
        )
        previous_decision = _document_time(
            previous_registry["decision_at"], "DATUM_REGISTRY_TIME_INVALID"
        )
        if (
            cycle_index != previous_registry["cycle_index"] + 1
            or previous_decision >= cutoff
        ):
            raise DataModelError("DATUM_REGISTRY_PREDECESSOR_INVALID")
        latest = {
            row.datum_id: row
            for row in (
                point_in_time_datum_from_document(document)
                for document in previous_registry["latest_revisions"]
            )
        }
    if (
        not isinstance(dataset, Mapping)
        or _document_time(dataset.get("decision_at"), "DATUM_REGISTRY_TIME_INVALID")
        != cutoff
    ):
        raise DataModelError("DATUM_REGISTRY_DATASET_TIME_INVALID")
    rows = verify_point_in_time_dataset(
        dataset,
        prior_revisions=latest,
        external_inputs=latest,
    )
    for row in rows:
        latest[row.datum_id] = row
    current_documents = [row.to_document() for row in rows]
    document = {
        "schema_id": "theory_paper_v2_v31_datum_revision_registry",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "decision_at": _time(cutoff),
        "previous_registry_digest": previous_digest,
        "known_datum_ids": sorted(latest),
        "latest_revisions": [
            latest[datum_id].to_document() for datum_id in sorted(latest)
        ],
        "current_cycle_datum_digests": sorted(
            row["datum_digest"] for row in current_documents
        ),
        "current_inference_active_datum_ids": sorted(
            row["datum_id"]
            for row in current_documents
            if row["inference_admissible"] is True
        ),
        "history_retention": "ALL_KNOWN_IDS_LATEST_REVISION_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    document["datum_revision_registry_digest"] = canonical_digest(document)
    _verify_datum_registry(document, expected_run_id=run_id)
    return document


__all__ = [
    "ConflictState",
    "DataModelError",
    "DataQuality",
    "DatumEpistemicType",
    "DatumValueType",
    "Missingness",
    "PointInTimeDatum",
    "ProxyLevel",
    "QualityLevel",
    "UncertaintyKind",
    "UncertaintyRepresentation",
    "admit_point_in_time_dataset",
    "build_point_in_time_datum_revision_registry",
    "point_in_time_datum_from_document",
    "point_in_time_dataset_rows_from_document",
    "verify_point_in_time_dataset",
]
