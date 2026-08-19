"""Domain contract for admitting qualified public data into one V3.1 cycle.

Source qualification deliberately has no experiment-start authority.  This
receipt is the explicit bridge between that isolated evidence store and the
sole authorized, non-executable V3.1 research run.  It binds both sides of
every exact-byte copy and never advances a research checkpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest


SOURCE_ADMISSION_SCHEMA_ID = "theory_paper_v31_cycle_source_admission"
SOURCE_ADMISSION_SCHEMA_VERSION = "1.0.0"
SOURCE_ADMISSION_DIGEST_FIELD = "cycle_source_admission_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EXACT_INSTRUMENT = {
    "venue": "OKX",
    "instrument_id": "BTC-USDT-SWAP",
    "market_type": "PERPETUAL_SWAP",
    "underlying_symbol": "BTC-USDT",
}
_ARTIFACT_COPY_FIELDS = frozenset(
    {
        "artifact_role",
        "artifact_id",
        "source_relative_ref",
        "target_relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "source_physical_sha256",
        "target_physical_sha256",
        "exact_bytes_copied",
    }
)
_DOCUMENT_ROLES = frozenset(
    {
        "QUALIFICATION_PLAN",
        "QUALIFICATION_RESERVATION",
        "QUALIFICATION_CHECKPOINT",
        "QUALIFICATION_COMPLETION",
        "MARKET_SNAPSHOT",
        "PIT_DATASET",
        "INFORMATION_EVENT",
    }
)
_SINGLETON_ROLES = frozenset(_DOCUMENT_ROLES - {"INFORMATION_EVENT"})
_ARTIFACT_ROLES = _DOCUMENT_ROLES | {"RAW_RESPONSE"}
_PREVIOUS_CONTEXT_FIELDS = frozenset(
    {
        "status",
        "previous_cycle_source_admission_binding",
        "prior_snapshot_binding",
        "prior_open_interest_datum_digest",
        "prior_open_interest_status",
        "prior_open_interest_zero_imputed",
        "previous_decision_at",
        "previous_admitted_at",
        "previous_closed_1h_as_of",
    }
)
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "admitted_at",
        "decision_at",
        "closed_1h_as_of",
        "symbol",
        "instrument",
        "data_scope",
        "active_authority_digest",
        "active_authority_recorded_at",
        "experiment_contract_digest",
        "source_qualification_id",
        "source_qualification_internal_cycle_index",
        "source_qualification_plan_digest",
        "source_qualification_checkpoint_digest",
        "source_qualification_completion_digest",
        "source_qualification_decision_at",
        "native_market_snapshot_digest",
        "pit_dataset_digest",
        "information_event_digests",
        "information_event_record_digests",
        "source_capture_record_digests",
        "source_capture_records_embedded_in_copied_snapshot",
        "raw_physical_sha256_by_request_id",
        "earliest_capture_started_at",
        "latest_capture_received_at",
        "artifact_copies",
        "previous_source_context",
        "source_evidence_boundary",
        "source_quality_ceiling",
        "source_qualification_is_start_authority",
        "cycle_source_admitted",
        "exact_source_bytes_copied_and_read_back",
        "missing_is_zero",
        "public_only",
        "account_access",
        "account_data_accessed",
        "paper_trading",
        "live_trading",
        "order_submission",
        "order_data_accessed",
        "credential_access",
        "credentials_accessed",
        "funds_access",
        "portfolio_mutation",
        "external_execution_authority",
        "executable",
        SOURCE_ADMISSION_DIGEST_FIELD,
    }
)


class V31CycleSourceAdmissionError(ValueError):
    """A formal-cycle source admission contract failed closed."""


def cycle_source_admission_ref(cycle_index: int) -> str:
    cycle = _cycle(cycle_index)
    return (
        f"cycles/{cycle:04d}/market/source-admission/"
        "cycle-source-admission.json"
    )


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31CycleSourceAdmissionError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31CycleSourceAdmissionError(code)
    return value


def _cycle(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 8
    ):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ADMISSION_CYCLE_INVALID"
        )
    return value


def _timestamp(value: Any, code: str) -> datetime:
    text = _text(value, code)
    if not text.endswith("Z"):
        raise V31CycleSourceAdmissionError(code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31CycleSourceAdmissionError(code) from exc
    if parsed.tzinfo is None:
        raise V31CycleSourceAdmissionError(code)
    normalized = parsed.astimezone(UTC)
    admitted_forms = {
        normalized.isoformat(timespec="seconds").replace("+00:00", "Z"),
        normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        normalized.isoformat(timespec="microseconds").replace("+00:00", "Z"),
    }
    if text not in admitted_forms:
        raise V31CycleSourceAdmissionError(code)
    return normalized


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.as_posix() != text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31CycleSourceAdmissionError(code)
    return text


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V31CycleSourceAdmissionError(code)
    return {
        "relative_ref": _relative_ref(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _previous_context(value: Any, *, cycle_index: int) -> dict[str, Any]:
    code = "V31_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID"
    if not isinstance(value, Mapping) or set(value) != _PREVIOUS_CONTEXT_FIELDS:
        raise V31CycleSourceAdmissionError(code)
    if cycle_index == 1:
        expected = {
            "status": "GENESIS_NO_PRIOR_SOURCE_CONTEXT",
            "previous_cycle_source_admission_binding": None,
            "prior_snapshot_binding": None,
            "prior_open_interest_datum_digest": None,
            "prior_open_interest_status": "NOT_APPLICABLE_GENESIS",
            "prior_open_interest_zero_imputed": False,
            "previous_decision_at": None,
            "previous_admitted_at": None,
            "previous_closed_1h_as_of": None,
        }
        if dict(value) != expected:
            raise V31CycleSourceAdmissionError(code)
        return expected
    if value.get("status") != "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE":
        raise V31CycleSourceAdmissionError(code)
    previous_admission = _binding(
        value.get("previous_cycle_source_admission_binding"), code
    )
    prior_snapshot = _binding(value.get("prior_snapshot_binding"), code)
    if (
        previous_admission["schema_id"] != SOURCE_ADMISSION_SCHEMA_ID
        or previous_admission["digest_field"] != SOURCE_ADMISSION_DIGEST_FIELD
        or prior_snapshot["schema_id"] != "native_btc_public_market_snapshot"
        or prior_snapshot["digest_field"] != "native_market_snapshot_digest"
    ):
        raise V31CycleSourceAdmissionError(code)
    prior_status = value.get("prior_open_interest_status")
    if prior_status not in {"OBSERVED", "UNKNOWN"}:
        raise V31CycleSourceAdmissionError(code)
    if value.get("prior_open_interest_zero_imputed") is not False:
        raise V31CycleSourceAdmissionError(code)
    previous_decision_at = _text(value.get("previous_decision_at"), code)
    previous_admitted_at = _text(value.get("previous_admitted_at"), code)
    previous_closed = _text(value.get("previous_closed_1h_as_of"), code)
    _timestamp(previous_decision_at, code)
    _timestamp(previous_admitted_at, code)
    _timestamp(previous_closed, code)
    return {
        "status": "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE",
        "previous_cycle_source_admission_binding": previous_admission,
        "prior_snapshot_binding": prior_snapshot,
        "prior_open_interest_datum_digest": _digest(
            value.get("prior_open_interest_datum_digest"), code
        ),
        "prior_open_interest_status": prior_status,
        "prior_open_interest_zero_imputed": False,
        "previous_decision_at": previous_decision_at,
        "previous_admitted_at": previous_admitted_at,
        "previous_closed_1h_as_of": previous_closed,
    }


def _artifact_copy(value: Any, *, cycle_index: int) -> dict[str, Any]:
    code = "V31_CYCLE_SOURCE_ARTIFACT_COPY_INVALID"
    if not isinstance(value, Mapping) or set(value) != _ARTIFACT_COPY_FIELDS:
        raise V31CycleSourceAdmissionError(code)
    role = _text(value.get("artifact_role"), code)
    if role not in _ARTIFACT_ROLES:
        raise V31CycleSourceAdmissionError(code)
    artifact_id = _text(value.get("artifact_id"), code)
    source_ref = _relative_ref(value.get("source_relative_ref"), code)
    target_ref = _relative_ref(value.get("target_relative_ref"), code)
    target_prefix = f"cycles/{cycle_index:04d}/market/source-admission/"
    if not target_ref.startswith(target_prefix):
        raise V31CycleSourceAdmissionError(code)
    semantic = _digest(value.get("semantic_digest"), code)
    source_physical = _digest(value.get("source_physical_sha256"), code)
    target_physical = _digest(value.get("target_physical_sha256"), code)
    if source_physical != target_physical or value.get("exact_bytes_copied") is not True:
        raise V31CycleSourceAdmissionError(code)
    schema_id = value.get("schema_id")
    digest_field = value.get("digest_field")
    if role == "RAW_RESPONSE":
        if schema_id is not None or digest_field is not None or semantic != source_physical:
            raise V31CycleSourceAdmissionError(code)
    else:
        schema_id = _text(schema_id, code)
        digest_field = _text(digest_field, code)
    return {
        "artifact_role": role,
        "artifact_id": artifact_id,
        "source_relative_ref": source_ref,
        "target_relative_ref": target_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "source_physical_sha256": source_physical,
        "target_physical_sha256": target_physical,
        "exact_bytes_copied": True,
    }


def _copy_rows(
    values: Sequence[Mapping[str, Any]], *, cycle_index: int
) -> list[dict[str, Any]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ARTIFACT_SET_INVALID"
        )
    rows = [_artifact_copy(row, cycle_index=cycle_index) for row in values]
    if not rows:
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ARTIFACT_SET_INVALID"
        )
    expected_order = sorted(
        rows, key=lambda row: (row["artifact_role"], row["artifact_id"])
    )
    identities = {(row["artifact_role"], row["artifact_id"]) for row in rows}
    if (
        rows != expected_order
        or len(identities) != len(rows)
        or len({row["source_relative_ref"] for row in rows}) != len(rows)
        or len({row["target_relative_ref"] for row in rows}) != len(rows)
    ):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ARTIFACT_SET_INVALID"
        )
    by_role = {
        role: [row for row in rows if row["artifact_role"] == role]
        for role in _ARTIFACT_ROLES
    }
    if (
        any(len(by_role[role]) != 1 for role in _SINGLETON_ROLES)
        or not by_role["INFORMATION_EVENT"]
        or not by_role["RAW_RESPONSE"]
    ):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ARTIFACT_SET_INVALID"
        )
    return rows


def _string_digest_map(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise V31CycleSourceAdmissionError(code)
    result: dict[str, str] = {}
    for key in sorted(value):
        result[_text(key, code)] = _digest(value[key], code)
    if list(value) != list(result) or len(result) != len(value):
        raise V31CycleSourceAdmissionError(code)
    return result


def _digest_list(value: Any, code: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V31CycleSourceAdmissionError(code)
    rows = [_digest(item, code) for item in value]
    if not rows or len(rows) != len(set(rows)):
        raise V31CycleSourceAdmissionError(code)
    return rows


def seal_v31_cycle_source_admission(
    *,
    run_id: str,
    cycle_index: int,
    admitted_at: str,
    decision_at: str,
    closed_1h_as_of: str,
    active_authority_digest: str,
    active_authority_recorded_at: str,
    experiment_contract_digest: str,
    source_qualification_id: str,
    source_qualification_plan_digest: str,
    source_qualification_checkpoint_digest: str,
    source_qualification_completion_digest: str,
    source_qualification_decision_at: str,
    native_market_snapshot_digest: str,
    pit_dataset_digest: str,
    information_event_digests: Sequence[str],
    information_event_record_digests: Sequence[str],
    source_capture_record_digests: Mapping[str, str],
    raw_physical_sha256_by_request_id: Mapping[str, str],
    earliest_capture_started_at: str,
    latest_capture_received_at: str,
    artifact_copies: Sequence[Mapping[str, Any]],
    previous_source_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal one exact-byte public-source admission; never grant start authority."""

    cycle = _cycle(cycle_index)
    authority_time = _timestamp(
        active_authority_recorded_at,
        "V31_CYCLE_SOURCE_AUTHORITY_TIME_INVALID",
    )
    earliest = _timestamp(
        earliest_capture_started_at,
        "V31_CYCLE_SOURCE_CAPTURE_TIME_INVALID",
    )
    latest = _timestamp(
        latest_capture_received_at,
        "V31_CYCLE_SOURCE_CAPTURE_TIME_INVALID",
    )
    source_decision = _timestamp(
        source_qualification_decision_at,
        "V31_CYCLE_SOURCE_DECISION_TIME_INVALID",
    )
    target_decision = _timestamp(
        decision_at, "V31_CYCLE_SOURCE_DECISION_TIME_INVALID"
    )
    current_closed = _timestamp(
        closed_1h_as_of, "V31_CYCLE_SOURCE_CLOSED_1H_TIME_INVALID"
    )
    admitted = _timestamp(
        admitted_at, "V31_CYCLE_SOURCE_ADMITTED_TIME_INVALID"
    )
    if (
        earliest <= authority_time
        or latest < earliest
        or source_decision < latest
        or target_decision != source_decision
        or admitted < target_decision
    ):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_CHRONOLOGY_INVALID"
        )

    rows = _copy_rows(artifact_copies, cycle_index=cycle)
    event_digests = _digest_list(
        information_event_digests,
        "V31_CYCLE_SOURCE_INFORMATION_DIGESTS_INVALID",
    )
    event_record_digests = _digest_list(
        information_event_record_digests,
        "V31_CYCLE_SOURCE_INFORMATION_RECORD_DIGESTS_INVALID",
    )
    capture_digests = _string_digest_map(
        source_capture_record_digests,
        "V31_CYCLE_SOURCE_CAPTURE_DIGESTS_INVALID",
    )
    raw_digests = _string_digest_map(
        raw_physical_sha256_by_request_id,
        "V31_CYCLE_SOURCE_RAW_DIGESTS_INVALID",
    )
    raw_rows = [row for row in rows if row["artifact_role"] == "RAW_RESPONSE"]
    event_rows = [row for row in rows if row["artifact_role"] == "INFORMATION_EVENT"]
    singleton = {
        role: next(row for row in rows if row["artifact_role"] == role)
        for role in _SINGLETON_ROLES
    }
    if (
        set(capture_digests) != set(raw_digests)
        or {row["artifact_id"] for row in raw_rows} != set(raw_digests)
        or any(
            row["semantic_digest"] != raw_digests[row["artifact_id"]]
            for row in raw_rows
        )
        or [row["semantic_digest"] for row in event_rows]
        != event_record_digests
        or len(event_digests) != len(event_record_digests)
        or singleton["QUALIFICATION_PLAN"]["semantic_digest"]
        != source_qualification_plan_digest
        or singleton["QUALIFICATION_CHECKPOINT"]["semantic_digest"]
        != source_qualification_checkpoint_digest
        or singleton["QUALIFICATION_COMPLETION"]["semantic_digest"]
        != source_qualification_completion_digest
        or singleton["MARKET_SNAPSHOT"]["semantic_digest"]
        != native_market_snapshot_digest
        or singleton["PIT_DATASET"]["semantic_digest"] != pit_dataset_digest
    ):
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ARTIFACT_BINDING_MISMATCH"
        )

    previous_context = _previous_context(
        previous_source_context, cycle_index=cycle
    )
    if cycle > 1:
        previous_decision = _timestamp(
            previous_context["previous_decision_at"],
            "V31_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID",
        )
        previous_closed = _timestamp(
            previous_context["previous_closed_1h_as_of"],
            "V31_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID",
        )
        previous_admitted = _timestamp(
            previous_context["previous_admitted_at"],
            "V31_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID",
        )
        if (
            target_decision <= previous_decision
            or earliest <= previous_admitted
            or admitted <= previous_admitted
            or current_closed != previous_closed + timedelta(hours=1)
        ):
            raise V31CycleSourceAdmissionError(
                "V31_CYCLE_SOURCE_CROSS_CYCLE_CHRONOLOGY_INVALID"
            )

    return self_digest(
        {
            "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
            "schema_version": SOURCE_ADMISSION_SCHEMA_VERSION,
            "run_id": _text(run_id, "V31_CYCLE_SOURCE_RUN_ID_INVALID"),
            "cycle_index": cycle,
            "admitted_at": admitted_at,
            "decision_at": decision_at,
            "closed_1h_as_of": closed_1h_as_of,
            "symbol": "BTC-USDT-SWAP",
            "instrument": dict(_EXACT_INSTRUMENT),
            "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "active_authority_digest": _digest(
                active_authority_digest,
                "V31_CYCLE_SOURCE_AUTHORITY_DIGEST_INVALID",
            ),
            "active_authority_recorded_at": active_authority_recorded_at,
            "experiment_contract_digest": _digest(
                experiment_contract_digest,
                "V31_CYCLE_SOURCE_CONTRACT_DIGEST_INVALID",
            ),
            "source_qualification_id": _text(
                source_qualification_id,
                "V31_CYCLE_SOURCE_QUALIFICATION_ID_INVALID",
            ),
            "source_qualification_internal_cycle_index": 1,
            "source_qualification_plan_digest": _digest(
                source_qualification_plan_digest,
                "V31_CYCLE_SOURCE_QUALIFICATION_DIGEST_INVALID",
            ),
            "source_qualification_checkpoint_digest": _digest(
                source_qualification_checkpoint_digest,
                "V31_CYCLE_SOURCE_QUALIFICATION_DIGEST_INVALID",
            ),
            "source_qualification_completion_digest": _digest(
                source_qualification_completion_digest,
                "V31_CYCLE_SOURCE_QUALIFICATION_DIGEST_INVALID",
            ),
            "source_qualification_decision_at": source_qualification_decision_at,
            "native_market_snapshot_digest": _digest(
                native_market_snapshot_digest,
                "V31_CYCLE_SOURCE_SNAPSHOT_DIGEST_INVALID",
            ),
            "pit_dataset_digest": _digest(
                pit_dataset_digest,
                "V31_CYCLE_SOURCE_DATASET_DIGEST_INVALID",
            ),
            "information_event_digests": event_digests,
            "information_event_record_digests": event_record_digests,
            "source_capture_record_digests": capture_digests,
            "source_capture_records_embedded_in_copied_snapshot": True,
            "raw_physical_sha256_by_request_id": raw_digests,
            "earliest_capture_started_at": earliest_capture_started_at,
            "latest_capture_received_at": latest_capture_received_at,
            "artifact_copies": rows,
            "previous_source_context": previous_context,
            "source_evidence_boundary": "SOURCE_ATTESTED",
            "source_quality_ceiling": "VERIFIED_SECONDARY",
            "source_qualification_is_start_authority": False,
            "cycle_source_admitted": True,
            "exact_source_bytes_copied_and_read_back": True,
            "missing_is_zero": False,
            "public_only": True,
            "account_access": False,
            "account_data_accessed": False,
            "paper_trading": False,
            "live_trading": False,
            "order_submission": False,
            "order_data_accessed": False,
            "credential_access": False,
            "credentials_accessed": False,
            "funds_access": False,
            "portfolio_mutation": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        SOURCE_ADMISSION_DIGEST_FIELD,
    )


def verify_v31_cycle_source_admission(document: Mapping[str, Any]) -> str:
    """Reconstruct the strict receipt and reject any semantic extension."""

    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ADMISSION_SCHEMA_INVALID"
        )
    try:
        supplied = verify_self_digest(document, SOURCE_ADMISSION_DIGEST_FIELD)
        rebuilt = seal_v31_cycle_source_admission(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            admitted_at=document["admitted_at"],
            decision_at=document["decision_at"],
            closed_1h_as_of=document["closed_1h_as_of"],
            active_authority_digest=document["active_authority_digest"],
            active_authority_recorded_at=document[
                "active_authority_recorded_at"
            ],
            experiment_contract_digest=document["experiment_contract_digest"],
            source_qualification_id=document["source_qualification_id"],
            source_qualification_plan_digest=document[
                "source_qualification_plan_digest"
            ],
            source_qualification_checkpoint_digest=document[
                "source_qualification_checkpoint_digest"
            ],
            source_qualification_completion_digest=document[
                "source_qualification_completion_digest"
            ],
            source_qualification_decision_at=document[
                "source_qualification_decision_at"
            ],
            native_market_snapshot_digest=document[
                "native_market_snapshot_digest"
            ],
            pit_dataset_digest=document["pit_dataset_digest"],
            information_event_digests=document["information_event_digests"],
            information_event_record_digests=document[
                "information_event_record_digests"
            ],
            source_capture_record_digests=document[
                "source_capture_record_digests"
            ],
            raw_physical_sha256_by_request_id=document[
                "raw_physical_sha256_by_request_id"
            ],
            earliest_capture_started_at=document[
                "earliest_capture_started_at"
            ],
            latest_capture_received_at=document["latest_capture_received_at"],
            artifact_copies=document["artifact_copies"],
            previous_source_context=document["previous_source_context"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31CycleSourceAdmissionError):
            raise
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ADMISSION_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[SOURCE_ADMISSION_DIGEST_FIELD]:
        raise V31CycleSourceAdmissionError(
            "V31_CYCLE_SOURCE_ADMISSION_NOT_CANONICAL"
        )
    return supplied


def admitted_authoring_source_bindings(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Project copied artifacts for the later authoring-packet composition.

    The returned values do not by themselves prove authorized admission.  The
    authoring packet must additionally bind the admission receipt and replay it.
    """

    verify_v31_cycle_source_admission(receipt)
    rows = receipt["artifact_copies"]

    def projected(row: Mapping[str, Any]) -> dict[str, str]:
        if row["schema_id"] is None or row["digest_field"] is None:
            raise V31CycleSourceAdmissionError(
                "V31_CYCLE_SOURCE_AUTHORING_BINDING_INVALID"
            )
        return {
            "relative_ref": row["target_relative_ref"],
            "schema_id": row["schema_id"],
            "digest_field": row["digest_field"],
            "semantic_digest": row["semantic_digest"],
            "physical_sha256": row["target_physical_sha256"],
        }

    completion = next(
        row for row in rows if row["artifact_role"] == "QUALIFICATION_COMPLETION"
    )
    snapshot = next(
        row for row in rows if row["artifact_role"] == "MARKET_SNAPSHOT"
    )
    dataset = next(row for row in rows if row["artifact_role"] == "PIT_DATASET")
    events = [row for row in rows if row["artifact_role"] == "INFORMATION_EVENT"]
    return {
        "source_qualification_completion_binding": projected(completion),
        "market_snapshot_binding": projected(snapshot),
        "information_event_bindings": [projected(row) for row in events],
        "pit_dataset_binding": projected(dataset),
    }


__all__ = [
    "SOURCE_ADMISSION_DIGEST_FIELD",
    "SOURCE_ADMISSION_SCHEMA_ID",
    "SOURCE_ADMISSION_SCHEMA_VERSION",
    "V31CycleSourceAdmissionError",
    "admitted_authoring_source_bindings",
    "cycle_source_admission_ref",
    "seal_v31_cycle_source_admission",
    "verify_v31_cycle_source_admission",
]
