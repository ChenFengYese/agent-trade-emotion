"""Deterministic baseline association and change estimation for V3.1.

This module intentionally implements only a pre-registered Pearson baseline
over explicitly paired, point-in-time observations.  It gives the system a
real numeric association path without pretending to implement DCC, Granger,
tail dependence, or structural causality.  More advanced estimators must emit
their own versioned receipts through the same association contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any, Mapping, Sequence

from .association_model import (
    INTERPRETATION_BOUNDARIES,
    build_association_revision,
)
from .contracts.canonical import canonical_decimal, self_digest, verify_self_digest


class AssociationEstimationError(ValueError):
    """A numeric association estimate or comparison failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_Z_975 = Decimal("1.959963984540054")
_CORRELATION_CLAMP = Decimal("0.999999999999999999999999")


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AssociationEstimationError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssociationEstimationError(code) from exc
    if result.tzinfo is None:
        raise AssociationEstimationError(code)
    return result.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | str, code: str) -> Decimal:
    if isinstance(value, float) or isinstance(value, bool):
        raise AssociationEstimationError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AssociationEstimationError(code) from exc
    if not result.is_finite():
        raise AssociationEstimationError(code)
    return result


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssociationEstimationError(code)
    return value.strip()


def _strings(values: Sequence[str], code: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise AssociationEstimationError(code)
    result = list(values)
    if (
        (not allow_empty and not result)
        or any(not isinstance(item, str) or not item.strip() for item in result)
        or len(result) != len(set(result))
    ):
        raise AssociationEstimationError(code)
    return sorted(item.strip() for item in result)


@dataclass(frozen=True, slots=True)
class PairedNumericObservation:
    pair_id: str
    as_of: str
    available_at: str
    source_value: Decimal | str
    target_value: Decimal | str
    source_datum_digest: str
    target_datum_digest: str

    def __post_init__(self) -> None:
        _text(self.pair_id, "ASSOCIATION_PAIR_ID_INVALID")
        as_of = _time(self.as_of, "ASSOCIATION_PAIR_TIME_INVALID")
        available = _time(self.available_at, "ASSOCIATION_PAIR_TIME_INVALID")
        if as_of > available:
            raise AssociationEstimationError("ASSOCIATION_PAIR_NOT_POINT_IN_TIME")
        object.__setattr__(
            self,
            "source_value",
            _decimal(self.source_value, "ASSOCIATION_PAIR_VALUE_INVALID"),
        )
        object.__setattr__(
            self,
            "target_value",
            _decimal(self.target_value, "ASSOCIATION_PAIR_VALUE_INVALID"),
        )
        for value in (self.source_datum_digest, self.target_datum_digest):
            if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
                raise AssociationEstimationError("ASSOCIATION_PAIR_DIGEST_INVALID")

    def to_document(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "as_of": _time_text(_time(self.as_of, "ASSOCIATION_PAIR_TIME_INVALID")),
            "available_at": _time_text(
                _time(self.available_at, "ASSOCIATION_PAIR_TIME_INVALID")
            ),
            "source_value": canonical_decimal(self.source_value),
            "target_value": canonical_decimal(self.target_value),
            "source_datum_digest": self.source_datum_digest,
            "target_datum_digest": self.target_datum_digest,
        }


def _pearson(rows: Sequence[PairedNumericObservation]) -> Decimal:
    count = Decimal(len(rows))
    source_mean = sum((row.source_value for row in rows), Decimal(0)) / count
    target_mean = sum((row.target_value for row in rows), Decimal(0)) / count
    source_ss = sum(
        ((row.source_value - source_mean) ** 2 for row in rows), Decimal(0)
    )
    target_ss = sum(
        ((row.target_value - target_mean) ** 2 for row in rows), Decimal(0)
    )
    if source_ss == 0 or target_ss == 0:
        raise AssociationEstimationError("ASSOCIATION_ZERO_VARIANCE")
    cross = sum(
        (
            (row.source_value - source_mean) * (row.target_value - target_mean)
            for row in rows
        ),
        Decimal(0),
    )
    with localcontext() as context:
        context.prec = 50
        result = cross / (source_ss * target_ss).sqrt()
    return max(Decimal(-1), min(Decimal(1), result))


def _fisher_interval(correlation: Decimal, sample_count: int) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 50
        bounded = max(-_CORRELATION_CLAMP, min(_CORRELATION_CLAMP, correlation))
        fisher_z = ((Decimal(1) + bounded) / (Decimal(1) - bounded)).ln() / 2
        standard_error = Decimal(1) / Decimal(sample_count - 3).sqrt()
        lower_z = fisher_z - _Z_975 * standard_error
        upper_z = fisher_z + _Z_975 * standard_error

        def tanh(value: Decimal) -> Decimal:
            doubled = (value * 2).exp()
            return (doubled - 1) / (doubled + 1)

        lower = max(Decimal(-1), tanh(lower_z))
        upper = min(Decimal(1), tanh(upper_z))
        return min(lower, correlation), max(upper, correlation)


def estimate_pearson_association(
    *,
    association_id: str,
    source_node_id: str,
    target_node_id: str,
    decision_at: str,
    timeframe: str,
    observations: Sequence[PairedNumericObservation],
    multiple_testing_control: str,
    limitations: Sequence[str],
) -> dict[str, Any]:
    """Compute a receipt-bound Pearson estimate from at least four PIT pairs."""

    cutoff = _time(decision_at, "ASSOCIATION_ESTIMATION_DECISION_TIME_INVALID")
    identity = (
        _text(association_id, "ASSOCIATION_ESTIMATION_ID_INVALID"),
        _text(source_node_id, "ASSOCIATION_ESTIMATION_SOURCE_INVALID"),
        _text(target_node_id, "ASSOCIATION_ESTIMATION_TARGET_INVALID"),
    )
    if identity[1] == identity[2]:
        raise AssociationEstimationError("ASSOCIATION_SELF_PAIR_FORBIDDEN")
    rows = tuple(observations)
    if len(rows) < 4 or any(not isinstance(row, PairedNumericObservation) for row in rows):
        raise AssociationEstimationError("ASSOCIATION_SAMPLE_INSUFFICIENT")
    pair_ids = [row.pair_id for row in rows]
    as_of_values = [_time(row.as_of, "ASSOCIATION_PAIR_TIME_INVALID") for row in rows]
    if len(pair_ids) != len(set(pair_ids)) or len(as_of_values) != len(set(as_of_values)):
        raise AssociationEstimationError("ASSOCIATION_PAIR_DUPLICATE")
    if any(
        _time(row.available_at, "ASSOCIATION_PAIR_TIME_INVALID") > cutoff
        for row in rows
    ):
        raise AssociationEstimationError("ASSOCIATION_FUTURE_PAIR_FORBIDDEN")
    rows = tuple(sorted(rows, key=lambda row: _time(row.as_of, "ASSOCIATION_PAIR_TIME_INVALID")))
    point = _pearson(rows)
    lower, upper = _fisher_interval(point, len(rows))
    document = {
        "schema_id": "theory_paper_v2_v31_association_estimation_receipt",
        "schema_version": "1.0.0",
        "association_id": identity[0],
        "source_node_id": identity[1],
        "target_node_id": identity[2],
        "decision_at": _time_text(cutoff),
        "available_at": _time_text(
            max(_time(row.available_at, "ASSOCIATION_PAIR_TIME_INVALID") for row in rows)
        ),
        "method": "PEARSON_PAIRWISE_COMPLETE_FISHER_Z_95_V1",
        "model_version": "V3_1_PEARSON_BASELINE_1_0_0",
        "timeframe": _text(timeframe, "ASSOCIATION_ESTIMATION_TIMEFRAME_INVALID"),
        "window_start": _time_text(min(as_of_values)),
        "window_end": _time_text(max(as_of_values)),
        "sample_count": len(rows),
        "paired_observations": [row.to_document() for row in rows],
        "estimate": {
            "lower": canonical_decimal(lower),
            "point": canonical_decimal(point),
            "upper": canonical_decimal(upper),
            "scale": "CORRELATION",
            "interval_kind": "ESTIMATION_INTERVAL",
            "confidence_level": "0.95",
        },
        "multiple_testing_control": _text(
            multiple_testing_control,
            "ASSOCIATION_MULTIPLE_TESTING_CONTROL_REQUIRED",
        ),
        "interpretation_boundary": "ASSOCIATIONAL_NOT_CAUSAL",
        "limitations": _strings(limitations, "ASSOCIATION_LIMITATIONS_REQUIRED"),
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "association_estimation_receipt_digest")


def verify_pearson_association_receipt(receipt: Mapping[str, Any]) -> str:
    if not isinstance(receipt, Mapping):
        raise AssociationEstimationError("ASSOCIATION_RECEIPT_INVALID")
    try:
        rows = tuple(
            PairedNumericObservation(
                pair_id=row["pair_id"],
                as_of=row["as_of"],
                available_at=row["available_at"],
                source_value=row["source_value"],
                target_value=row["target_value"],
                source_datum_digest=row["source_datum_digest"],
                target_datum_digest=row["target_datum_digest"],
            )
            for row in receipt["paired_observations"]
        )
        rebuilt = estimate_pearson_association(
            association_id=receipt["association_id"],
            source_node_id=receipt["source_node_id"],
            target_node_id=receipt["target_node_id"],
            decision_at=receipt["decision_at"],
            timeframe=receipt["timeframe"],
            observations=rows,
            multiple_testing_control=receipt["multiple_testing_control"],
            limitations=receipt["limitations"],
        )
        supplied = verify_self_digest(
            receipt, "association_estimation_receipt_digest"
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, AssociationEstimationError):
            raise
        raise AssociationEstimationError("ASSOCIATION_RECEIPT_INVALID") from exc
    if rebuilt != dict(receipt) or supplied != rebuilt["association_estimation_receipt_digest"]:
        raise AssociationEstimationError("ASSOCIATION_RECEIPT_RECONSTRUCTION_MISMATCH")
    return supplied


def build_association_revision_from_estimate(
    *,
    receipt: Mapping[str, Any],
    dependency_group_ids: Sequence[str],
    regime_ids: Sequence[str],
    condition_refs: Sequence[str],
    limitations: Sequence[str],
) -> dict[str, Any]:
    """Translate the verified numeric receipt into the common graph edge contract."""

    receipt_digest = verify_pearson_association_receipt(receipt)
    estimate = receipt["estimate"]
    return build_association_revision(
        {
            "schema_version": "V3_1_ASSOCIATION_REVISION",
            "association_id": receipt["association_id"],
            "revision": 1,
            "predecessor_digest": None,
            "source_node_id": receipt["source_node_id"],
            "target_node_id": receipt["target_node_id"],
            "relation": "ASSOCIATED_WITH",
            "association_type": "OBSERVED_ASSOCIATION",
            "method": receipt["method"],
            "interpretation_boundary": INTERPRETATION_BOUNDARIES[
                "OBSERVED_ASSOCIATION"
            ],
            "estimate_interval": {
                "lower": estimate["lower"],
                "point": estimate["point"],
                "upper": estimate["upper"],
                "scale": "CORRELATION",
                "unit": "INDEX",
                "interval_kind": "ESTIMATION_INTERVAL",
            },
            "window": {
                "start_at": receipt["window_start"],
                "end_at": receipt["window_end"],
                "timeframe": receipt["timeframe"],
                "sample_count": receipt["sample_count"],
            },
            "lag": {"value": 0, "unit": receipt["timeframe"], "direction": "SYNCHRONOUS"},
            "regime": {
                "regime_ids": list(regime_ids),
                "condition_refs": list(condition_refs),
            },
            "coverage": {"ratio": "1", "status": "COMPLETE", "limitations": []},
            "stability": {
                "assessment": "UNKNOWN",
                "evidence_window_count": 1,
                "break_refs": [],
            },
            "dependency_group_ids": list(dependency_group_ids),
            "provenance": [
                {
                    "source_ref": f"association-estimate:{receipt['association_id']}",
                    "source_digest": receipt_digest,
                    "observed_at": receipt["window_end"],
                    "available_at": receipt["available_at"],
                    "revision_ref": "V3_1_PEARSON_BASELINE_1_0_0",
                }
            ],
            "validity": {"valid_from": receipt["decision_at"], "valid_until": None},
            "identification_contract": None,
            "status": "ACTIVE",
            "created_at": receipt["available_at"],
            "available_at": receipt["decision_at"],
            "limitations": list(limitations),
        },
        decision_at=receipt["decision_at"],
    )


def compare_disjoint_association_windows(
    *, prior_receipt: Mapping[str, Any], current_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two disjoint, otherwise identical Pearson windows conservatively."""

    prior_digest = verify_pearson_association_receipt(prior_receipt)
    current_digest = verify_pearson_association_receipt(current_receipt)
    if any(
        prior_receipt[field] != current_receipt[field]
        for field in ("association_id", "source_node_id", "target_node_id", "method", "timeframe")
    ):
        raise AssociationEstimationError("ASSOCIATION_CHANGE_NOT_COMPARABLE")
    if _time(current_receipt["window_start"], "ASSOCIATION_WINDOW_INVALID") <= _time(
        prior_receipt["window_end"], "ASSOCIATION_WINDOW_INVALID"
    ):
        raise AssociationEstimationError(
            "ASSOCIATION_OVERLAPPING_WINDOWS_REQUIRE_JOINT_ESTIMATOR"
        )
    prior = prior_receipt["estimate"]
    current = current_receipt["estimate"]
    lower = _decimal(current["lower"], "ASSOCIATION_CHANGE_INVALID") - _decimal(
        prior["upper"], "ASSOCIATION_CHANGE_INVALID"
    )
    point = _decimal(current["point"], "ASSOCIATION_CHANGE_INVALID") - _decimal(
        prior["point"], "ASSOCIATION_CHANGE_INVALID"
    )
    upper = _decimal(current["upper"], "ASSOCIATION_CHANGE_INVALID") - _decimal(
        prior["lower"], "ASSOCIATION_CHANGE_INVALID"
    )
    direction = (
        "INCREASE_DISTINGUISHED"
        if lower > 0
        else "DECREASE_DISTINGUISHED"
        if upper < 0
        else "CHANGE_NOT_DISTINGUISHED"
    )
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_association_change_receipt",
            "schema_version": "1.0.0",
            "association_id": current_receipt["association_id"],
            "prior_estimation_receipt_digest": prior_digest,
            "current_estimation_receipt_digest": current_digest,
            "prior_window": [prior_receipt["window_start"], prior_receipt["window_end"]],
            "current_window": [current_receipt["window_start"], current_receipt["window_end"]],
            "comparison_method": "DISJOINT_FISHER_INTERVAL_DIFFERENCE_V1",
            "change_interval": {
                "lower": canonical_decimal(lower),
                "point": canonical_decimal(point),
                "upper": canonical_decimal(upper),
            },
            "direction_claim": direction,
            "interpretation_boundary": "ASSOCIATION_CHANGE_NOT_CAUSAL",
            "limitations": [
                "The interval comparison is conservative and valid only for the declared disjoint windows.",
                "A change in correlation does not identify a transmission mechanism or structural cause.",
            ],
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "association_change_receipt_digest",
    )


__all__ = [
    "AssociationEstimationError",
    "PairedNumericObservation",
    "build_association_revision_from_estimate",
    "compare_disjoint_association_windows",
    "estimate_pearson_association",
    "verify_pearson_association_receipt",
]
