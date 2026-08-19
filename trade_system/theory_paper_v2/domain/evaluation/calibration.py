"""Future-compatible calibration lineage with E0 fail-closed permissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common import (
    EXTERNAL_EXECUTION_AUTHORITY,
    SYSTEM_MODE,
    DomainError,
    DomainResult,
    ReducerStatus,
)
from ..contracts.canonical import canonical_digest
from .model import ProbabilityStatus, ProbabilityUse, require_aware


class ForecastOutcomeStatus(StrEnum):
    RESOLVED = "RESOLVED"
    PENDING = "PENDING"
    CENSORED = "CENSORED"
    CONFLICTED = "CONFLICTED"


class CoherenceVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ForecastIssuanceReceipt:
    forecast_issuance_id: str
    forecaster_ref: str
    event_definition_ref: str
    instrument_or_universe_scope_ref: str
    forecast_horizon_ref: str
    issued_at: datetime
    available_at: datetime
    probability_vector_ref: str
    probability_status_at_issuance: ProbabilityStatus
    calibration_record_ref: str | None
    source_input_manifest_ref: str
    source_input_digest: str
    outcome_due_at: datetime

    def __post_init__(self) -> None:
        for value in (self.issued_at, self.available_at, self.outcome_due_at):
            require_aware(value)
        if self.available_at < self.issued_at:
            raise ValueError("FORECAST_AVAILABLE_BEFORE_ISSUANCE")
        if (
            self.probability_status_at_issuance
            is ProbabilityStatus.CALIBRATED_OOS
        ) != (self.calibration_record_ref is not None):
            raise ValueError("FORECAST_CALIBRATION_LINEAGE_MISMATCH")


@dataclass(frozen=True, slots=True)
class OutcomeResolutionReceipt:
    outcome_resolution_id: str
    forecast_issuance_ref: str
    event_definition_ref: str
    label_resolver_ref: str
    outcome_status: ForecastOutcomeStatus
    resolved_label_ref: str | None
    observation_window_start: datetime
    observation_window_end: datetime
    label_available_at: datetime | None
    source_receipt_refs: tuple[str, ...]
    overlapping_horizon_group_ref: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.observation_window_start)
        require_aware(self.observation_window_end)
        require_aware(self.label_available_at)
        if self.observation_window_end < self.observation_window_start:
            raise ValueError("OUTCOME_WINDOW_REVERSED")
        if self.outcome_status is ForecastOutcomeStatus.RESOLVED and (
            self.resolved_label_ref is None or self.label_available_at is None
        ):
            raise ValueError("RESOLVED_OUTCOME_LABEL_MISSING")
        if self.outcome_status is not ForecastOutcomeStatus.RESOLVED and (
            self.resolved_label_ref is not None
        ):
            raise ValueError("UNRESOLVED_OUTCOME_HAS_LABEL")


@dataclass(frozen=True, slots=True)
class CalibrationDatasetManifest:
    manifest_id: str
    dataset_version: str
    forecast_issuance_refs: tuple[str, ...]
    outcome_resolution_refs: tuple[str, ...]
    training_cutoff: datetime
    evaluation_cutoff: datetime
    pending_count: int
    censored_count: int
    resolved_count: int
    overlap_handling_policy_ref: str
    cohort_and_regime_policy_ref: str
    label_leakage_check_ref: str
    dataset_type: str
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class CalibrationRegistry:
    registry_id: str
    registry_version: str
    calibration_record_refs: tuple[str, ...]
    registry_status: str
    valid_from: datetime
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False

    def __post_init__(self) -> None:
        require_aware(self.valid_from)
        if not self.registry_id or not self.registry_version:
            raise ValueError("CALIBRATION_REGISTRY_IDENTITY_MISSING")


@dataclass(frozen=True, slots=True)
class ProbabilityUseAuthorization:
    authorization_id: str
    calibration_record_ref: str
    coherence_receipt_ref: str
    allowed_uses: frozenset[str]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        require_aware(self.valid_from)
        require_aware(self.valid_until)
        if (
            self.valid_until <= self.valid_from
            or not self.allowed_uses
            or not self.allowed_uses.issubset(
                {"DISPLAY_ONLY", "PATH_RANKING", "EXPECTED_VALUE", "POSITION_SIZING"}
            )
        ):
            raise ValueError("PROBABILITY_USE_AUTHORIZATION_INVALID")


@dataclass(frozen=True, slots=True)
class ForecastCoherenceReceipt:
    receipt_id: str
    probability_status: ProbabilityStatus
    status: CoherenceVerdict
    other_path_present: bool | None
    violation_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.receipt_id
            or not isinstance(self.probability_status, ProbabilityStatus)
            or not isinstance(self.status, CoherenceVerdict)
        ):
            raise ValueError("FORECAST_COHERENCE_RECEIPT_INVALID")


def _error(code: str, message: str) -> DomainResult:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="CALIBRATION",
            retryability="NEVER",
            message=message,
        ),
    )


def create_empty_e0_calibration_registry(
    *, registry_id: str, registry_version: str, valid_from: datetime
) -> CalibrationRegistry:
    require_aware(valid_from)
    return CalibrationRegistry(
        registry_id=registry_id,
        registry_version=registry_version,
        calibration_record_refs=(),
        registry_status="EMPTY_E0",
        valid_from=valid_from,
    )


def validate_e0_calibration_registry(
    registry: CalibrationRegistry,
) -> DomainResult[CalibrationRegistry]:
    if (
        registry.system_mode != SYSTEM_MODE
        or registry.external_execution_authority != EXTERNAL_EXECUTION_AUTHORITY
        or registry.executable
        or registry.registry_status != "EMPTY_E0"
        or registry.calibration_record_refs
    ):
        return _error(
            "CALIBRATION_REGISTRY_NONEMPTY_E0",
            "E0 accepts exactly an empty calibration registry",
        )
    return DomainResult(status=ReducerStatus.APPLIED, value=registry)


def build_calibration_dataset_manifest(
    *,
    manifest_id: str,
    dataset_version: str,
    issuances: tuple[ForecastIssuanceReceipt, ...],
    outcomes: tuple[OutcomeResolutionReceipt, ...],
    training_cutoff: datetime,
    evaluation_cutoff: datetime,
    overlap_handling_policy_ref: str,
    cohort_and_regime_policy_ref: str,
    label_leakage_check_ref: str,
) -> DomainResult[CalibrationDatasetManifest]:
    """Freeze one-to-one, point-in-time-clean forecast/outcome lineage."""

    require_aware(training_cutoff)
    require_aware(evaluation_cutoff)
    if evaluation_cutoff < training_cutoff or not issuances or not outcomes:
        return _error(
            "CALIBRATION_LINEAGE_COMPLETE",
            "dataset cutoffs or lineage cardinality are invalid",
        )
    issuance_by_id = {item.forecast_issuance_id: item for item in issuances}
    outcome_by_forecast = {item.forecast_issuance_ref: item for item in outcomes}
    if (
        len(issuance_by_id) != len(issuances)
        or len(outcome_by_forecast) != len(outcomes)
        or set(issuance_by_id) != set(outcome_by_forecast)
    ):
        return _error(
            "CALIBRATION_LINEAGE_COMPLETE",
            "issuance and outcome lineage must be one-to-one",
        )
    for issuance_id, issuance in issuance_by_id.items():
        outcome = outcome_by_forecast[issuance_id]
        if outcome.event_definition_ref != issuance.event_definition_ref:
            return _error(
                "CALIBRATION_EVENT_DEFINITION_MISMATCH",
                "outcome event differs from forecast event",
            )
        if (
            issuance.available_at > evaluation_cutoff
            or (
                outcome.label_available_at is not None
                and outcome.label_available_at > evaluation_cutoff
            )
        ):
            return _error(
                "CALIBRATION_LABEL_LEAKAGE",
                "forecast or label was unavailable at evaluation cutoff",
            )
    pending = sum(
        item.outcome_status is ForecastOutcomeStatus.PENDING for item in outcomes
    )
    censored = sum(
        item.outcome_status is ForecastOutcomeStatus.CENSORED for item in outcomes
    )
    resolved = sum(
        item.outcome_status is ForecastOutcomeStatus.RESOLVED for item in outcomes
    )
    digest = canonical_digest(
        {
            "manifest_id": manifest_id,
            "dataset_version": dataset_version,
            "issuance_refs": tuple(sorted(issuance_by_id)),
            "outcome_refs": tuple(
                sorted(item.outcome_resolution_id for item in outcomes)
            ),
            "training_cutoff": training_cutoff.isoformat(),
            "evaluation_cutoff": evaluation_cutoff.isoformat(),
            "counts": (pending, censored, resolved),
            "overlap_handling_policy_ref": overlap_handling_policy_ref,
            "cohort_and_regime_policy_ref": cohort_and_regime_policy_ref,
            "label_leakage_check_ref": label_leakage_check_ref,
            "dataset_type": "INDEPENDENT_FROZEN_EVALUATION",
        }
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=CalibrationDatasetManifest(
            manifest_id=manifest_id,
            dataset_version=dataset_version,
            forecast_issuance_refs=tuple(sorted(issuance_by_id)),
            outcome_resolution_refs=tuple(
                sorted(item.outcome_resolution_id for item in outcomes)
            ),
            training_cutoff=training_cutoff,
            evaluation_cutoff=evaluation_cutoff,
            pending_count=pending,
            censored_count=censored,
            resolved_count=resolved,
            overlap_handling_policy_ref=overlap_handling_policy_ref,
            cohort_and_regime_policy_ref=cohort_and_regime_policy_ref,
            label_leakage_check_ref=label_leakage_check_ref,
            dataset_type="INDEPENDENT_FROZEN_EVALUATION",
            manifest_digest=digest,
        ),
    )


def authorize_probability_use(
    *,
    probability_status: ProbabilityStatus,
    requested_use: ProbabilityUse,
    registry: CalibrationRegistry,
    authorization: ProbabilityUseAuthorization | None,
    coherence_receipt: ForecastCoherenceReceipt | None,
    decision_cutoff: datetime,
) -> DomainResult[bool]:
    """Apply the E0 probability-use matrix without implicit promotion."""

    registry_result = validate_e0_calibration_registry(registry)
    if registry_result.status is not ReducerStatus.APPLIED:
        return registry_result
    require_aware(decision_cutoff)
    if authorization is not None:
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "E0 accepts zero probability-use authorization instances",
        )
    if probability_status is ProbabilityStatus.CALIBRATED_OOS:
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "coherence or Agent agreement cannot create calibration",
        )
    if requested_use in {
        ProbabilityUse.NUMERIC_DISPLAY,
        ProbabilityUse.EXPECTED_VALUE,
        ProbabilityUse.KELLY,
        ProbabilityUse.POSITION_SIZING,
    }:
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "numeric probability use is forbidden for ordinal/unknown states",
        )
    if probability_status is ProbabilityStatus.UNKNOWN and (
        requested_use is ProbabilityUse.ORDINAL_PATH_RANKING
    ):
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "UNKNOWN cannot be promoted to ordinal ranking",
        )
    if (
        coherence_receipt is not None
        and coherence_receipt.probability_status is ProbabilityStatus.CALIBRATED_OOS
    ):
        return _error(
            "PROBABILITY_USE_UNAUTHORIZED_E0",
            "coherence receipt claimed unreachable E0 calibration",
        )
    return DomainResult(status=ReducerStatus.APPLIED, value=True)
