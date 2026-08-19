"""Successor-only adapter from admitted V3.1 PIT data to twelve-axis evidence.

The Domain source registry deliberately does not know how the current V3.1
market adapter names OKX datums.  This application boundary performs that
small, explicit translation.  It accepts only an already admitted public
cycle, binds every projected observation to the exact PIT datum, information
revision, availability time and dependency group, and leaves every
unsupported axis UNKNOWN.

No ordinal axis direction is inferred here.  In particular, a one-frame book
snapshot is never promoted to liquidity resilience; price/volume do not stand
in for liquidation, attention, news or cross-market evidence; and the
multi-timeframe evidence object is emitted only for the exact closed
15m/1h/4h/1d return set.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.data_model import (
    DataModelError,
    PointInTimeDatum,
    verify_point_in_time_dataset,
)
from ..domain.v31_cycle_source_admission import (
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    V31CycleSourceAdmissionError,
    cycle_source_admission_ref,
    verify_v31_cycle_source_admission,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    V31SentimentNativeProjectionError,
    build_v31_native_sentiment_projection,
    build_v31_native_sentiment_source_registry,
    verify_v31_native_sentiment_projection,
    verify_v31_native_sentiment_source_registry,
)


class V31SentimentProjectionAdapterV2Error(ValueError):
    """The successor application projection could not be proved exactly."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CANDLE_METRIC = re.compile(
    r"^candle-(15m|1h|4h|1d)-(close|return-pct|range-pct|"
    r"volume-vs-20bar-median)$"
)
_CLOSED_TIMEFRAMES = ("15m", "1h", "4h", "1d")
_INFORMATION_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "previous_registry_digest",
        "known_event_ids",
        "latest_revisions",
        "current_cycle_event_digests",
        "history_retention",
        "external_execution_authority",
        "executable",
        "information_revision_registry_digest",
    }
)
_INFORMATION_LATEST_FIELDS = frozenset(
    {"event_id", "revision", "event_digest", "available_at"}
)
_CRITICAL_QUALITY_FIELDS = (
    "source_reliability",
    "completeness",
    "timeliness",
    "semantic_fidelity",
    "lineage_integrity",
)
_OI_CONTINUITY_FIELDS = (
    "value",
    "unit",
    "instrument_id",
    "venue_id",
    "source_type",
    "source_ref",
    "raw_ref",
    "raw_sha256",
    "as_of",
    "observed_at",
    "available_at",
    "coverage",
    "missingness",
)
_EXPLICIT_UNSUPPORTED_METRICS = frozenset(
    {
        "liquidation-stress",
        "news-cross-market",
        "cross-market-risk-appetite",
        "crowding-positioning",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "adapter_id",
        "projection_id",
        "run_id",
        "cycle_index",
        "instrument_id",
        "decision_at",
        "cycle_source_admission_binding",
        "pit_dataset_binding",
        "information_revision_registry_binding",
        "previous_context_verification",
        "native_source_registry",
        "native_source_registry_digest",
        "information_datum_binding_materials",
        "derived_evidence_materials",
        "excluded_candidates",
        "projection",
        "projection_digest",
        "source_observation_count",
        "axis_count",
        "missing_is_zero",
        "public_data_only",
        "external_execution_authority",
        "executable",
        "claim_boundaries",
        "projection_receipt_digest",
    }
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31SentimentProjectionAdapterV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SentimentProjectionAdapterV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SentimentProjectionAdapterV2Error(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SentimentProjectionAdapterV2Error(code)
    return value


def _verify_information_registry(
    document: Mapping[str, Any],
) -> tuple[str, dict[str, dict[str, Any]]]:
    code = "V31_SENTIMENT_ADAPTER_INFORMATION_REGISTRY_INVALID"
    if (
        not isinstance(document, Mapping)
        or set(document) != _INFORMATION_REGISTRY_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_v31_information_revision_registry"
        or document.get("schema_version") != "1.0.0"
        or document.get("history_retention")
        != "ALL_KNOWN_IDS_LATEST_REVISION_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or not isinstance(document.get("run_id"), str)
        or not document["run_id"]
        or isinstance(document.get("cycle_index"), bool)
        or not isinstance(document.get("cycle_index"), int)
        or document["cycle_index"] < 1
    ):
        raise V31SentimentProjectionAdapterV2Error(code)
    supplied = _digest(
        document.get("information_revision_registry_digest"), code
    )
    payload = dict(document)
    payload.pop("information_revision_registry_digest")
    if canonical_digest(payload) != supplied:
        raise V31SentimentProjectionAdapterV2Error(code)
    decision = _time(document.get("decision_at"), code)
    known = document.get("known_event_ids")
    latest = document.get("latest_revisions")
    current = document.get("current_cycle_event_digests")
    if (
        not isinstance(known, list)
        or known != sorted(known)
        or len(known) != len(set(known))
        or any(not isinstance(item, str) or not item for item in known)
        or not isinstance(latest, list)
        or not isinstance(current, list)
        or len(current) != len(set(current))
        or any(not isinstance(item, str) or _HEX_64.fullmatch(item) is None for item in current)
    ):
        raise V31SentimentProjectionAdapterV2Error(code)
    by_id: dict[str, dict[str, Any]] = {}
    for row in latest:
        if (
            not isinstance(row, Mapping)
            or set(row) != _INFORMATION_LATEST_FIELDS
            or not isinstance(row.get("event_id"), str)
            or not row["event_id"]
            or isinstance(row.get("revision"), bool)
            or not isinstance(row.get("revision"), int)
            or row["revision"] < 1
            or _HEX_64.fullmatch(str(row.get("event_digest") or "")) is None
            or _time(row.get("available_at"), code) > decision
            or row["event_id"] in by_id
        ):
            raise V31SentimentProjectionAdapterV2Error(code)
        by_id[str(row["event_id"])] = dict(row)
    if sorted(by_id) != known or [row["event_id"] for row in latest] != known:
        raise V31SentimentProjectionAdapterV2Error(code)
    previous = document.get("previous_registry_digest")
    if document["cycle_index"] == 1:
        if previous is not None:
            raise V31SentimentProjectionAdapterV2Error(code)
    else:
        _digest(previous, code)
    return supplied, by_id


def _dataset_rows(document: Mapping[str, Any]) -> tuple[PointInTimeDatum, ...]:
    try:
        return verify_point_in_time_dataset(document)
    except DataModelError as exc:
        raise V31SentimentProjectionAdapterV2Error(
            f"V31_SENTIMENT_ADAPTER_PIT_DATASET_INVALID:{exc}"
        ) from exc


def _quality_status(document: Mapping[str, Any]) -> str:
    quality = document["quality"]
    levels = [str(quality[field]) for field in _CRITICAL_QUALITY_FIELDS]
    if "UNUSABLE" in levels:
        return "UNUSABLE"
    if "LOW" in levels:
        return "LOW"
    if "UNKNOWN" in levels:
        return "UNKNOWN"
    if all(level == "HIGH" for level in levels):
        return "HIGH"
    if all(level in {"HIGH", "MEDIUM"} for level in levels):
        return "MEDIUM"
    return "UNKNOWN"


def _closed_candle_parts(document: Mapping[str, Any]) -> tuple[str, str] | None:
    match = _CANDLE_METRIC.fullmatch(str(document.get("metric") or ""))
    if match is None:
        return None
    timeframe, measure = match.groups()
    if (
        document.get("timeframe") != timeframe
        or document.get("window") != "LATEST_CLOSED_AND_20_BAR_CONTEXT"
    ):
        return None
    return timeframe, measure


def _mapping_for(document: Mapping[str, Any]) -> dict[str, Any] | None:
    metric = str(document.get("metric") or "")
    candle = _closed_candle_parts(document)
    if metric == "mark-price":
        return {
            "source_kind": "PUBLIC_MARK_OR_INDEX_PRICE",
            "axis_bindings": [
                {
                    "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
                    "evidence_role": "DIRECT",
                }
            ],
            "is_closed": None,
            "timeframes": [],
        }
    if candle is not None:
        timeframe, measure = candle
        if measure in {"close", "return-pct"}:
            axes = [
                {
                    "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
                    "evidence_role": "DIRECT",
                }
            ]
            if measure == "return-pct":
                axes.extend(
                    [
                        {
                            "axis_id": "STRUCTURE_PERSISTENCE",
                            "evidence_role": "PROXY",
                        },
                        {
                            "axis_id": "VOLATILITY_AND_TAIL_STRESS",
                            "evidence_role": "DIRECT",
                        },
                    ]
                )
            source_kind = "PUBLIC_CLOSED_CANDLE_SERIES"
        elif measure == "range-pct":
            axes = [
                {
                    "axis_id": "VOLATILITY_AND_TAIL_STRESS",
                    "evidence_role": "DIRECT",
                }
            ]
            source_kind = "PUBLIC_CLOSED_CANDLE_SERIES"
        else:
            axes = [
                {
                    "axis_id": "PARTICIPATION_AND_ACTIVE_FLOW",
                    "evidence_role": "DIRECT",
                }
            ]
            source_kind = "PUBLIC_CLOSED_CANDLE_VOLUME"
        return {
            "source_kind": source_kind,
            "axis_bindings": axes,
            "is_closed": True,
            "timeframes": [timeframe],
        }
    if metric == "recent-trade-side-imbalance":
        return {
            "source_kind": "PUBLIC_AGGRESSOR_TRADE_SAMPLE",
            "axis_bindings": [
                {
                    "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
                    "evidence_role": "PROXY",
                },
                {
                    "axis_id": "PARTICIPATION_AND_ACTIVE_FLOW",
                    "evidence_role": "DIRECT",
                },
            ],
            "is_closed": None,
            "timeframes": [],
        }
    if metric == "book-top5-imbalance":
        return {
            "source_kind": "PUBLIC_ORDER_BOOK_SNAPSHOT",
            "axis_bindings": [
                {
                    "axis_id": "PRICE_DIRECTIONAL_PRESSURE",
                    "evidence_role": "PROXY",
                }
            ],
            "is_closed": None,
            "timeframes": [],
        }
    if metric == "funding-rate":
        return {
            "source_kind": "PUBLIC_FUNDING_RATE",
            "axis_bindings": [
                {
                    "axis_id": "CROWDING_DIRECTION",
                    "evidence_role": "DIRECT",
                },
                {
                    "axis_id": "LEVERAGE_CHANGE",
                    "evidence_role": "PROXY",
                },
            ],
            "is_closed": None,
            "timeframes": [],
        }
    if metric == "open-interest-btc":
        return {
            "source_kind": "PUBLIC_OPEN_INTEREST",
            "axis_bindings": [
                {
                    "axis_id": "CROWDING_DIRECTION",
                    "evidence_role": "PROXY",
                },
                {
                    "axis_id": "LEVERAGE_CHANGE",
                    "evidence_role": "DIRECT",
                },
            ],
            "is_closed": None,
            "timeframes": [],
        }
    return None


def _information_bindings(
    document: Mapping[str, Any],
    *,
    latest_information: Mapping[str, Mapping[str, Any]],
    admitted_event_digests: set[str],
    binding_purpose: str,
) -> tuple[list[dict[str, str]], datetime, list[dict[str, Any]]]:
    event_ids = document.get("event_ids")
    if not isinstance(event_ids, list) or not event_ids:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_DATUM_INFORMATION_BINDING_MISSING"
        )
    bindings: list[dict[str, str]] = []
    materials: list[dict[str, Any]] = []
    available = _time(
        document.get("available_at"),
        "V31_SENTIMENT_ADAPTER_DATUM_TIME_INVALID",
    )
    for event_id in sorted(event_ids):
        row = latest_information.get(str(event_id))
        if row is None or row["event_digest"] not in admitted_event_digests:
            raise V31SentimentProjectionAdapterV2Error(
                "V31_SENTIMENT_ADAPTER_INFORMATION_NOT_SOURCE_ADMITTED"
            )
        material = self_digest(
            {
                "schema_id": "theory_paper_v2_v31_information_datum_binding_material",
                "schema_version": "2.0.0",
                "binding_purpose": binding_purpose,
                "information_revision_ref": str(event_id),
                "information_revision_digest": str(row["event_digest"]),
                "information_revision_available_at": str(row["available_at"]),
                "datum_ref": str(document["datum_id"]),
                "datum_digest": str(document["datum_digest"]),
                "datum_available_at": str(document["available_at"]),
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "material_digest",
        )
        material_ref = f"v31-information-datum-binding:{material['material_digest']}"
        bindings.append(
            {
                "information_ref": material_ref,
                "information_digest": str(material["material_digest"]),
            }
        )
        materials.append(
            {
                "material_ref": material_ref,
                "material_digest": material["material_digest"],
                "material": material,
            }
        )
        available = max(
            available,
            _time(
                row["available_at"],
                "V31_SENTIMENT_ADAPTER_INFORMATION_TIME_INVALID",
            ),
        )
    return bindings, available, materials


def _base_observation(
    document: Mapping[str, Any],
    *,
    mapping: Mapping[str, Any],
    latest_information: Mapping[str, Mapping[str, Any]],
    admitted_event_digests: set[str],
    admitted_raw_digests_by_request_id: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bindings, available, information_materials = _information_bindings(
        document,
        latest_information=latest_information,
        admitted_event_digests=admitted_event_digests,
        binding_purpose="BASE_NATIVE_SOURCE_OBSERVATION",
    )
    observed = _time(
        document.get("observed_at"),
        "V31_SENTIMENT_ADAPTER_DATUM_TIME_INVALID",
    )
    coverage = document.get("coverage")
    observed_value = (
        document.get("value") is not None
        and document.get("missingness") == "OBSERVED"
    )
    admitted = (
        observed_value
        and document.get("hypothesis_admissible") is True
        and document.get("source_type") == "OKX_OFFICIAL_PUBLIC"
        and isinstance(document.get("raw_ref"), str)
        and _HEX_64.fullmatch(str(document.get("raw_sha256") or ""))
        is not None
        and admitted_raw_digests_by_request_id.get(str(document.get("source_ref")))
        == document.get("raw_sha256")
    )
    observation = {
        "evidence_id": f"v31-native-source:{document['datum_digest']}",
        "source_kind": mapping["source_kind"],
        "axis_bindings": list(mapping["axis_bindings"]),
        "information_bindings": bindings,
        "datum_ref": document["datum_id"],
        "datum_digest": document["datum_digest"],
        "input_datum_bindings": [],
        "dependency_group_id": document["dependency_group"],
        "observed_at": _time_text(observed),
        "available_at": _time_text(available),
        "admission_status": "ADMITTED" if admitted else "REJECTED",
        "clock_status": "VALID" if observed <= available else "INVALID",
        "quality_status": _quality_status(document),
        "coverage_status": "SUFFICIENT" if coverage == "1" else "INSUFFICIENT",
        "source_observation_status": "OBSERVED" if observed_value else "UNKNOWN",
        "is_closed": mapping["is_closed"],
        "timeframes": list(mapping["timeframes"]),
        "limitations": sorted(
            set(
                list(document.get("limitations") or [])
                + [
                    "This application mapping preserves the PIT datum claim ceiling.",
                    "Source availability does not determine an ordinal axis state.",
                ]
            )
        ),
    }
    return observation, information_materials


def _previous_context(
    *,
    cycle_source_admission: Mapping[str, Any],
    previous_pit_dataset: Mapping[str, Any] | None,
    previous_cycle_source_admission: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cycle = int(cycle_source_admission["cycle_index"])
    context = cycle_source_admission["previous_source_context"]
    if cycle == 1:
        if previous_pit_dataset is not None or previous_cycle_source_admission is not None:
            raise V31SentimentProjectionAdapterV2Error(
                "V31_SENTIMENT_ADAPTER_GENESIS_PREVIOUS_INPUT_FORBIDDEN"
            )
        return {"status": "NOT_APPLICABLE_GENESIS"}, None
    if previous_pit_dataset is None and previous_cycle_source_admission is None:
        return {"status": "NOT_SUPPLIED_OI_CHANGE_EXCLUDED"}, None
    if previous_pit_dataset is None or previous_cycle_source_admission is None:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_PREVIOUS_INPUT_PAIR_REQUIRED"
        )
    try:
        previous_admission_digest = verify_v31_cycle_source_admission(
            previous_cycle_source_admission
        )
    except V31CycleSourceAdmissionError as exc:
        raise V31SentimentProjectionAdapterV2Error(
            f"V31_SENTIMENT_ADAPTER_PREVIOUS_ADMISSION_INVALID:{exc}"
        ) from exc
    expected_binding = context["previous_cycle_source_admission_binding"]
    if (
        previous_cycle_source_admission.get("run_id")
        != cycle_source_admission.get("run_id")
        or previous_cycle_source_admission.get("cycle_index") != cycle - 1
        or expected_binding.get("relative_ref")
        != cycle_source_admission_ref(cycle - 1)
        or expected_binding.get("schema_id") != SOURCE_ADMISSION_SCHEMA_ID
        or expected_binding.get("digest_field")
        != SOURCE_ADMISSION_DIGEST_FIELD
        or expected_binding.get("semantic_digest") != previous_admission_digest
        or context.get("previous_decision_at")
        != previous_cycle_source_admission.get("decision_at")
        or context.get("previous_admitted_at")
        != previous_cycle_source_admission.get("admitted_at")
        or context.get("previous_closed_1h_as_of")
        != previous_cycle_source_admission.get("closed_1h_as_of")
        or context.get("prior_snapshot_binding", {}).get("semantic_digest")
        != previous_cycle_source_admission.get("native_market_snapshot_digest")
    ):
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_PREVIOUS_ADMISSION_BINDING_INVALID"
        )
    previous_rows = _dataset_rows(previous_pit_dataset)
    if (
        previous_pit_dataset.get("dataset_digest")
        != previous_cycle_source_admission.get("pit_dataset_digest")
    ):
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_PREVIOUS_DATASET_BINDING_INVALID"
        )
    oi_rows = [row.to_document() for row in previous_rows if row.metric == "open-interest-btc"]
    if len(oi_rows) != 1:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_PREVIOUS_OI_NOT_UNIQUE"
        )
    prior = oi_rows[0]
    if prior["datum_digest"] != context["prior_open_interest_datum_digest"]:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_PREVIOUS_OI_DIGEST_INVALID"
        )
    verified = {
        "status": "VERIFIED_EXACT_PREVIOUS_OI_BINDING",
        "previous_cycle_source_admission_ref": cycle_source_admission_ref(
            cycle - 1
        ),
        "previous_cycle_source_admission_digest": previous_admission_digest,
        "previous_pit_dataset_ref": previous_pit_dataset["dataset_id"],
        "previous_pit_dataset_digest": previous_pit_dataset["dataset_digest"],
        "previous_open_interest_datum_ref": prior["datum_id"],
        "previous_open_interest_datum_digest": prior["datum_digest"],
    }
    if (
        context.get("prior_open_interest_status") != "OBSERVED"
        or prior.get("value") is None
        or prior.get("missingness") != "OBSERVED"
        or prior.get("coverage") != "1"
    ):
        return (
            {
                **verified,
                "status": "VERIFIED_PREVIOUS_OI_UNKNOWN_CHANGE_EXCLUDED",
            },
            None,
        )
    return verified, prior


def _oi_change_observation(
    *,
    documents_by_id: Mapping[str, Mapping[str, Any]],
    metric_documents: Mapping[str, list[Mapping[str, Any]]],
    previous_oi: Mapping[str, Any] | None,
    latest_information: Mapping[str, Mapping[str, Any]],
    admitted_event_digests: set[str],
    admitted_raw_digests_by_request_id: Mapping[str, str],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    rows = metric_documents.get("open-interest-change-pct", [])
    if not rows:
        return None, [], "OPEN_INTEREST_CHANGE_DATUM_ABSENT"
    if len(rows) != 1:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_OI_CHANGE_NOT_UNIQUE"
        )
    change = rows[0]
    if change.get("value") is None:
        return None, [], "OPEN_INTEREST_CHANGE_UNKNOWN"
    if previous_oi is None:
        return None, [], "PREVIOUS_EXACT_OI_BINDING_NOT_VERIFIED"
    if (
        admitted_raw_digests_by_request_id.get(str(change.get("source_ref")))
        != change.get("raw_sha256")
    ):
        return None, [], "CURRENT_OI_CHANGE_RAW_NOT_SOURCE_ADMITTED"
    input_rows = []
    for ref, digest in zip(change.get("input_refs", []), change.get("input_digests", [])):
        row = documents_by_id.get(str(ref))
        if row is None or row.get("datum_digest") != digest:
            raise V31SentimentProjectionAdapterV2Error(
                "V31_SENTIMENT_ADAPTER_OI_CHANGE_INPUT_BINDING_INVALID"
            )
        input_rows.append(row)
    current = [row for row in input_rows if row.get("metric") == "open-interest-btc"]
    prior_copies = [
        row
        for row in input_rows
        if row.get("metric") == "prior-cycle-open-interest-btc"
    ]
    if len(input_rows) != 2 or len(current) != 1 or len(prior_copies) != 1:
        return None, [], "OI_CHANGE_EXACT_CURRENT_AND_PRIOR_INPUT_SET_MISSING"
    if (
        admitted_raw_digests_by_request_id.get(str(current[0].get("source_ref")))
        != current[0].get("raw_sha256")
    ):
        return None, [], "CURRENT_OPEN_INTEREST_RAW_NOT_SOURCE_ADMITTED"
    prior_copy = prior_copies[0]
    if any(prior_copy.get(field) != previous_oi.get(field) for field in _OI_CONTINUITY_FIELDS):
        return None, [], "PRIOR_OI_COPY_DOES_NOT_MATCH_PREVIOUS_ACCEPTED_DATUM"
    info_bindings, available, information_materials = _information_bindings(
        change,
        latest_information=latest_information,
        admitted_event_digests=admitted_event_digests,
        binding_purpose="CROSS_CAPTURE_OPEN_INTEREST_CHANGE",
    )
    observed = _time(
        change["observed_at"], "V31_SENTIMENT_ADAPTER_OI_CHANGE_TIME_INVALID"
    )
    input_bindings = [
        {
            "datum_ref": row["datum_id"],
            "datum_digest": row["datum_digest"],
            "metric_kind": "OPEN_INTEREST_LEVEL",
            "timeframe": row["timeframe"],
            "is_closed": None,
        }
        for row in input_rows
    ]
    return (
        {
            "evidence_id": f"v31-native-source:{change['datum_digest']}",
            "source_kind": "CROSS_CAPTURE_OPEN_INTEREST_CHANGE",
            "axis_bindings": [
                {"axis_id": "LEVERAGE_CHANGE", "evidence_role": "DERIVED"}
            ],
            "information_bindings": info_bindings,
            "datum_ref": change["datum_id"],
            "datum_digest": change["datum_digest"],
            "input_datum_bindings": input_bindings,
            "dependency_group_id": change["dependency_group"],
            "observed_at": _time_text(observed),
            "available_at": _time_text(available),
            "admission_status": (
                "ADMITTED" if change.get("hypothesis_admissible") is True else "REJECTED"
            ),
            "clock_status": "VALID" if observed <= available else "INVALID",
            "quality_status": _quality_status(change),
            "coverage_status": (
                "SUFFICIENT" if change.get("coverage") == "1" else "INSUFFICIENT"
            ),
            "source_observation_status": "OBSERVED",
            "is_closed": None,
            "timeframes": [],
            "limitations": sorted(
                set(
                    list(change.get("limitations") or [])
                    + [
                        (
                            "The change binds the exact previous accepted OI "
                            "datum and current OI datum."
                        ),
                        "Open-interest change has no directional sign by itself.",
                    ]
                )
            ),
        },
        information_materials,
        None,
    )


def _coherence_material(
    *,
    metric_documents: Mapping[str, list[Mapping[str, Any]]],
    latest_information: Mapping[str, Mapping[str, Any]],
    admitted_event_digests: set[str],
    admitted_raw_digests_by_request_id: Mapping[str, str],
    dataset_digest: str,
    information_registry_digest: str,
    instrument_id: str,
    decision_at: str,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    str | None,
]:
    inputs: list[Mapping[str, Any]] = []
    for timeframe in _CLOSED_TIMEFRAMES:
        rows = metric_documents.get(f"candle-{timeframe}-return-pct", [])
        exact = [row for row in rows if _closed_candle_parts(row) == (timeframe, "return-pct")]
        if len(exact) != 1 or exact[0].get("value") is None:
            return (
                None,
                None,
                None,
                "CLOSED_15M_1H_4H_1D_RETURN_SET_INCOMPLETE",
            )
        if (
            admitted_raw_digests_by_request_id.get(
                str(exact[0].get("source_ref"))
            )
            != exact[0].get("raw_sha256")
        ):
            return (
                None,
                None,
                None,
                "CLOSED_MULTITIMEFRAME_RAW_NOT_SOURCE_ADMITTED",
            )
        inputs.append(exact[0])
    input_bindings = [
        {
            "datum_ref": row["datum_id"],
            "datum_digest": row["datum_digest"],
            "metric_kind": "CLOSED_CANDLE_RETURN",
            "timeframe": row["timeframe"],
            "is_closed": True,
        }
        for row in inputs
    ]
    source_information: dict[str, str] = {}
    available_times: list[datetime] = []
    observed_times: list[datetime] = []
    dependencies = []
    for row in inputs:
        _, available, materials = _information_bindings(
            row,
            latest_information=latest_information,
            admitted_event_digests=admitted_event_digests,
            binding_purpose="CLOSED_MULTITIMEFRAME_INPUT",
        )
        for item in materials:
            material = item["material"]
            source_information[material["information_revision_ref"]] = material[
                "information_revision_digest"
            ]
        available_times.append(available)
        observed_times.append(
            _time(
                row["observed_at"],
                "V31_SENTIMENT_ADAPTER_COHERENCE_TIME_INVALID",
            )
        )
        dependencies.append(
            {
                "datum_ref": row["datum_id"],
                "datum_digest": row["datum_digest"],
                "dependency_group_id": row["dependency_group"],
            }
        )
    material = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_closed_multitimeframe_evidence_material",
            "schema_version": "2.0.0",
            "instrument_id": instrument_id,
            "decision_at": decision_at,
            "pit_dataset_digest": dataset_digest,
            "information_revision_registry_digest": information_registry_digest,
            "input_datum_bindings": input_bindings,
            "input_dependency_bindings": sorted(
                dependencies, key=lambda row: row["datum_ref"]
            ),
            "formula_id": "EXACT_CLOSED_INPUT_SET_NO_DIRECTIONAL_STATE_V1",
            "ordinal_axis_state_computed": False,
            "missing_is_zero": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "limitations": [
                "This material proves only that the four exact closed return inputs are available.",
                "It does not compute direction, probability or an action.",
            ],
        },
        "material_digest",
    )
    material_ref = f"v31-closed-multitimeframe-material:{material['material_digest']}"
    dependency_group = f"V31_CLOSED_MULTITIMEFRAME:{canonical_digest(dependencies)}"
    information_material = self_digest(
        {
            "schema_id": "theory_paper_v2_v31_coherence_information_binding_material",
            "schema_version": "2.0.0",
            "coherence_material_ref": material_ref,
            "coherence_material_digest": material["material_digest"],
            "information_revision_bindings": [
                {
                    "information_revision_ref": ref,
                    "information_revision_digest": digest,
                }
                for ref, digest in sorted(source_information.items())
            ],
            "available_at": _time_text(max(available_times)),
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "material_digest",
    )
    information_material_ref = (
        "v31-coherence-information-binding:"
        f"{information_material['material_digest']}"
    )
    observation = {
        "evidence_id": f"v31-native-source:{material['material_digest']}",
        "source_kind": "CLOSED_MULTI_TIMEFRAME_COHERENCE",
        "axis_bindings": [
            {"axis_id": "TIMEFRAME_COHERENCE", "evidence_role": "DERIVED"}
        ],
        "information_bindings": [
            {
                "information_ref": information_material_ref,
                "information_digest": information_material["material_digest"],
            }
        ],
        "datum_ref": material_ref,
        "datum_digest": material["material_digest"],
        "input_datum_bindings": input_bindings,
        "dependency_group_id": dependency_group,
        "observed_at": _time_text(max(observed_times)),
        "available_at": _time_text(max(available_times)),
        "admission_status": "ADMITTED",
        "clock_status": "VALID",
        "quality_status": max(
            (_quality_status(row) for row in inputs),
            key=("HIGH", "MEDIUM", "LOW", "UNUSABLE", "UNKNOWN").index,
        ),
        "coverage_status": (
            "SUFFICIENT" if all(row.get("coverage") == "1" for row in inputs) else "INSUFFICIENT"
        ),
        "source_observation_status": "OBSERVED",
        "is_closed": True,
        "timeframes": list(_CLOSED_TIMEFRAMES),
        "limitations": list(material["limitations"]),
    }
    binding = {
        "material_ref": material_ref,
        "material_digest": material["material_digest"],
        "material": material,
    }
    information_binding = {
        "material_ref": information_material_ref,
        "material_digest": information_material["material_digest"],
        "material": information_material,
    }
    return observation, binding, information_binding, None


def build_v31_sentiment_native_projection_receipt_v2(
    *,
    projection_id: str,
    pit_dataset: Mapping[str, Any],
    information_revision_registry: Mapping[str, Any],
    cycle_source_admission: Mapping[str, Any],
    previous_pit_dataset: Mapping[str, Any] | None = None,
    previous_cycle_source_admission: Mapping[str, Any] | None = None,
    axis_state_bindings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one replayable registry-plus-projection application receipt."""

    try:
        source_admission_digest = verify_v31_cycle_source_admission(
            cycle_source_admission
        )
    except V31CycleSourceAdmissionError as exc:
        raise V31SentimentProjectionAdapterV2Error(
            f"V31_SENTIMENT_ADAPTER_SOURCE_ADMISSION_INVALID:{exc}"
        ) from exc
    rows = _dataset_rows(pit_dataset)
    info_digest, latest_information = _verify_information_registry(
        information_revision_registry
    )
    run_id = str(cycle_source_admission["run_id"])
    cycle_index = int(cycle_source_admission["cycle_index"])
    instrument_id = str(cycle_source_admission["symbol"])
    decision_at = str(cycle_source_admission["decision_at"])
    if (
        pit_dataset.get("dataset_digest")
        != cycle_source_admission.get("pit_dataset_digest")
        or pit_dataset.get("decision_at") != decision_at
        or information_revision_registry.get("run_id") != run_id
        or information_revision_registry.get("cycle_index") != cycle_index
        or information_revision_registry.get("decision_at") != decision_at
        or set(information_revision_registry["current_cycle_event_digests"])
        != set(cycle_source_admission["information_event_digests"])
        or any(
            row.instrument_id != instrument_id
            for row in rows
            if row.value is not None
        )
    ):
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_SOURCE_INPUT_BINDING_INVALID"
        )
    admitted_event_digests = set(cycle_source_admission["information_event_digests"])
    admitted_raw_digests_by_request_id = dict(
        cycle_source_admission["raw_physical_sha256_by_request_id"]
    )
    documents = [row.to_document() for row in rows]
    documents_by_id = {row["datum_id"]: row for row in documents}
    metric_documents: dict[str, list[Mapping[str, Any]]] = {}
    for row in documents:
        metric_documents.setdefault(str(row["metric"]), []).append(row)

    previous_context, previous_oi = _previous_context(
        cycle_source_admission=cycle_source_admission,
        previous_pit_dataset=previous_pit_dataset,
        previous_cycle_source_admission=previous_cycle_source_admission,
    )
    source_observations: list[dict[str, Any]] = []
    information_binding_materials: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in sorted(documents, key=lambda item: item["datum_id"]):
        mapping = _mapping_for(row)
        if mapping is None:
            if row["metric"] in _EXPLICIT_UNSUPPORTED_METRICS:
                excluded.append(
                    {
                        "datum_ref": row["datum_id"],
                        "datum_digest": row["datum_digest"],
                        "metric": row["metric"],
                        "reason": "NO_OBSERVED_QUALIFIED_REGISTERED_SOURCE",
                    }
                )
            continue
        observation, materials = _base_observation(
            row,
            mapping=mapping,
            latest_information=latest_information,
            admitted_event_digests=admitted_event_digests,
            admitted_raw_digests_by_request_id=admitted_raw_digests_by_request_id,
        )
        source_observations.append(observation)
        information_binding_materials.extend(materials)

    oi_observation, oi_information_materials, oi_exclusion = _oi_change_observation(
        documents_by_id=documents_by_id,
        metric_documents=metric_documents,
        previous_oi=previous_oi,
        latest_information=latest_information,
        admitted_event_digests=admitted_event_digests,
        admitted_raw_digests_by_request_id=admitted_raw_digests_by_request_id,
    )
    if oi_observation is not None:
        source_observations.append(oi_observation)
        information_binding_materials.extend(oi_information_materials)
    elif oi_exclusion is not None:
        rows_for_change = metric_documents.get("open-interest-change-pct", [])
        excluded.append(
            {
                "datum_ref": (
                    rows_for_change[0]["datum_id"] if len(rows_for_change) == 1 else None
                ),
                "datum_digest": (
                    rows_for_change[0]["datum_digest"] if len(rows_for_change) == 1 else None
                ),
                "metric": "open-interest-change-pct",
                "reason": oi_exclusion,
            }
        )

    (
        coherence_observation,
        coherence_binding,
        coherence_information_binding,
        coherence_exclusion,
    ) = _coherence_material(
        metric_documents=metric_documents,
        latest_information=latest_information,
        admitted_event_digests=admitted_event_digests,
        admitted_raw_digests_by_request_id=admitted_raw_digests_by_request_id,
        dataset_digest=str(pit_dataset["dataset_digest"]),
        information_registry_digest=info_digest,
        instrument_id=instrument_id,
        decision_at=decision_at,
    )
    derived_materials: list[dict[str, Any]] = []
    if coherence_observation is not None and coherence_binding is not None:
        source_observations.append(coherence_observation)
        derived_materials.append(coherence_binding)
        if coherence_information_binding is None:
            raise V31SentimentProjectionAdapterV2Error(
                "V31_SENTIMENT_ADAPTER_COHERENCE_INFORMATION_BINDING_MISSING"
            )
        information_binding_materials.append(coherence_information_binding)
    elif coherence_exclusion is not None:
        excluded.append(
            {
                "datum_ref": None,
                "datum_digest": None,
                "metric": "closed-multitimeframe-coherence",
                "reason": coherence_exclusion,
            }
        )

    registry = build_v31_native_sentiment_source_registry()
    registry_digest = verify_v31_native_sentiment_source_registry(registry)
    try:
        projection = build_v31_native_sentiment_projection(
            projection_id=projection_id,
            instrument_id=instrument_id,
            decision_at=decision_at,
            source_observations=source_observations,
            axis_state_bindings=axis_state_bindings,
            registry=registry,
        )
        projection_digest = verify_v31_native_sentiment_projection(
            projection, registry=registry
        )
    except V31SentimentNativeProjectionError as exc:
        raise V31SentimentProjectionAdapterV2Error(
            f"V31_SENTIMENT_ADAPTER_DOMAIN_PROJECTION_REJECTED:{exc}"
        ) from exc
    receipt = {
        "schema_id": "theory_paper_v2_v31_sentiment_native_projection_receipt",
        "schema_version": "2.0.0",
        "adapter_id": "V31_SUCCESSOR_PIT_TO_NATIVE_SENTIMENT_PROJECTION_V2",
        "projection_id": projection["projection_id"],
        "run_id": run_id,
        "cycle_index": cycle_index,
        "instrument_id": instrument_id,
        "decision_at": decision_at,
        "cycle_source_admission_binding": {
            "relative_ref": cycle_source_admission_ref(cycle_index),
            "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
            "digest_field": SOURCE_ADMISSION_DIGEST_FIELD,
            "semantic_digest": source_admission_digest,
        },
        "pit_dataset_binding": {
            "dataset_ref": pit_dataset["dataset_id"],
            "dataset_digest": pit_dataset["dataset_digest"],
        },
        "information_revision_registry_binding": {
            "registry_ref": f"information-revision-registry:{run_id}:{cycle_index}",
            "registry_digest": info_digest,
        },
        "previous_context_verification": previous_context,
        "native_source_registry": registry,
        "native_source_registry_digest": registry_digest,
        "information_datum_binding_materials": sorted(
            information_binding_materials,
            key=lambda row: row["material_ref"],
        ),
        "derived_evidence_materials": derived_materials,
        "excluded_candidates": sorted(
            excluded,
            key=lambda row: (
                str(row["metric"]),
                str(row["datum_ref"] or ""),
                str(row["reason"]),
            ),
        ),
        "projection": projection,
        "projection_digest": projection_digest,
        "source_observation_count": len(projection["source_observations"]),
        "axis_count": len(projection["axis_projections"]),
        "missing_is_zero": False,
        "public_data_only": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "claim_boundaries": [
            "NO_AXIS_DIRECTION_INFERRED_BY_ADAPTER",
            "NO_CALIBRATED_PROBABILITY",
            "NO_EXPECTED_VALUE",
            "NO_TRADING_OR_EXECUTION_AUTHORITY",
        ],
    }
    return self_digest(receipt, "projection_receipt_digest")


def verify_v31_sentiment_native_projection_receipt_v2(
    document: Mapping[str, Any],
    *,
    pit_dataset: Mapping[str, Any],
    information_revision_registry: Mapping[str, Any],
    cycle_source_admission: Mapping[str, Any],
    previous_pit_dataset: Mapping[str, Any] | None = None,
    previous_cycle_source_admission: Mapping[str, Any] | None = None,
) -> str:
    """Replay all external inputs and require exact canonical equivalence."""

    if (
        not isinstance(document, Mapping)
        or set(document) != _RECEIPT_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_v31_sentiment_native_projection_receipt"
        or document.get("schema_version") != "2.0.0"
        or not isinstance(document.get("projection"), Mapping)
    ):
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, "projection_receipt_digest")
    except ValueError as exc:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_RECEIPT_DIGEST_INVALID"
        ) from exc
    rebuilt = build_v31_sentiment_native_projection_receipt_v2(
        projection_id=document.get("projection_id"),
        pit_dataset=pit_dataset,
        information_revision_registry=information_revision_registry,
        cycle_source_admission=cycle_source_admission,
        previous_pit_dataset=previous_pit_dataset,
        previous_cycle_source_admission=previous_cycle_source_admission,
        axis_state_bindings=document["projection"].get("axis_state_bindings", ()),
    )
    if dict(document) != rebuilt:
        raise V31SentimentProjectionAdapterV2Error(
            "V31_SENTIMENT_ADAPTER_RECEIPT_CANONICAL_FORM_INVALID"
        )
    return supplied


__all__ = [
    "V31SentimentProjectionAdapterV2Error",
    "build_v31_sentiment_native_projection_receipt_v2",
    "verify_v31_sentiment_native_projection_receipt_v2",
]
