"""Application composition for a full V3.2 durable source replay receipt.

The composition performs no collection and has no transport.  It reopens the
exact source-qualification artifacts and the exact admitted run artifacts,
replays their semantic verifiers, checks every physical SHA-256, reconstructs
the analysis bundle from sealed raw bytes, and writes one canonical receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    CAPTURE_SCHEMA_ID,
    FULL_LOADER_DIGEST_FIELD,
    FULL_LOADER_SCHEMA_ID,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    QUALIFICATION_DIGEST_FIELD,
    QUALIFICATION_SCHEMA_ID,
    SNAPSHOT_DIGEST_FIELD,
    SNAPSHOT_SCHEMA_ID,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    qualification_ref,
    verify_v32_active_authority_projection,
    verify_v32_cycle_source_admission,
    verify_v32_cycle_source_full_loader_receipt,
    verify_v32_formal_source_qualification,
    verify_v32_pit_evidence_registry,
    verify_v32_public_market_snapshot,
    verify_v32_public_source_capture,
)
from .v32_public_evidence_port import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    INFORMATION_EVENT_DIGEST_FIELD,
    OKX_PUBLIC_BASE_URL,
    RAW_BUNDLE_SCHEMA_ID,
    RAW_BUNDLE_SCHEMA_VERSION,
    SOURCE_ATTEMPT_DIGEST_FIELD as ATTEMPT_DIGEST_FIELD,
    SOURCE_ATTEMPT_SCHEMA_ID as ATTEMPT_SCHEMA_ID,
    V32PublicEvidenceVerificationError,
    V32PublicEvidenceVerifierPort,
)
from .v32_cycle_source_admission import (
    V32CycleSourceAdmissionWorkflowError,
    verify_durable_v32_cycle_source_admission,
)
from .v32_cycle_source_store_port import (
    V32CycleSourcePersistenceError,
    V32CycleSourceStorePort,
)


class V32DurableSourceReplayError(ValueError):
    """The durable replay did not prove one exact source transaction."""


RECEIPT_SCHEMA_ID = "theory_paper_v32_durable_source_replay_receipt_v1"
RECEIPT_DIGEST_FIELD = "durable_source_replay_receipt_digest"
# 1.3.0 binds replay rows to the openapi.okx.com raw-bundle generation.
# No successful www generation produced a replay receipt; the failed V1/www
# qualification is handled only by its exact sealed failure verifiers.
SCHEMA_VERSION = "1.3.0"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_COMPONENT_ORDER = (
    "SERVER_TIME",
    "INSTRUMENT",
    "TICKER",
    "MARK_PRICE",
    "CLOSED_CANDLES_15M",
    "CLOSED_CANDLES_1H",
    "CLOSED_CANDLES_4H",
    "CLOSED_CANDLES_1D",
    "OPEN_INTEREST",
    "FUNDING_RATE",
    "ORDER_BOOK",
    "RECENT_TRADES",
)
_COMPONENT_PATHS = {
    "SERVER_TIME": "/api/v5/public/time",
    "INSTRUMENT": "/api/v5/public/instruments",
    "TICKER": "/api/v5/market/ticker",
    "MARK_PRICE": "/api/v5/public/mark-price",
    "CLOSED_CANDLES_15M": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_1H": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_4H": "/api/v5/market/history-candles",
    "CLOSED_CANDLES_1D": "/api/v5/market/history-candles",
    "OPEN_INTEREST": "/api/v5/public/open-interest",
    "FUNDING_RATE": "/api/v5/public/funding-rate",
    "ORDER_BOOK": "/api/v5/market/books",
    "RECENT_TRADES": "/api/v5/market/trades",
}
_OPTIONAL_COMPONENTS = frozenset(
    {"OPEN_INTEREST", "FUNDING_RATE", "ORDER_BOOK", "RECENT_TRADES"}
)
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, *range(500, 600)})
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_:\-.]{0,159}$")
_TYPED_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_RAW_BINDING_FIELDS = frozenset(
    {"relative_ref", "semantic_digest", "physical_sha256"}
)
_REQUEST_REPLAY_FIELDS = frozenset(
    {
        "component_id",
        "request_id",
        "method",
        "base_url",
        "path",
        "query",
        "status",
        "http_status",
        "error_code",
        "attempt_number",
        "retry_allowed",
        "request_started_at",
        "response_received_at",
        "raw_binding",
        "failure_evidence_binding",
        "event_semantic_digest",
        "event_carrier_binding",
    }
)
_RUN_COPY_FIELDS = frozenset(
    {
        "artifact_role",
        "source_binding",
        "target_binding",
        "exact_bytes_copied",
        "readback_verified",
    }
)
_TRANSACTION_PROOF_FIELDS = frozenset(
    {
        "attempt_id",
        "capture_digest",
        "qualification_digest",
        "snapshot_digest",
        "pit_registry_digest",
        "full_loader_digest",
        "source_admission_digest",
        "single_source_collection_transaction",
        "attempt_count",
        "request_count",
        "each_request_attempt_count",
        "retry_allowed",
        "request_ids",
    }
)
_RAW_BEFORE_DERIVED_FIELDS = frozenset(
    {
        "method",
        "attempt_started_at",
        "sealed_raw_bindings",
        "verified_no_response_failure_bindings",
        "derived_typed_bindings",
        "analysis_reconstructed_from_sealed_raw",
        "all_response_raws_read_before_receipt",
        "derived_documents_exact_canonical_bytes",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "qualification_id",
        "replayed_at",
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        GOVERNING_AUTHORITY_DIGEST_FIELD,
        "experiment_contract_digest",
        "attempt_reservation_binding",
        "aggregate_raw_binding",
        "request_replays",
        "market_analysis_bundle_binding",
        "source_capture_binding",
        "source_snapshot_binding",
        "source_pit_registry_binding",
        "source_qualification_binding",
        "run_copy_replays",
        "full_loader_receipt_binding",
        "cycle_source_admission_binding",
        "transaction_proof",
        "raw_before_derived_proof",
        "physical_replay_verified",
        "semantic_replay_verified",
        "point_in_time_verified",
        "analysis_bundle_digest_is_pit_member",
        "replay_network_calls",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        RECEIPT_DIGEST_FIELD,
    }
)


def durable_source_replay_receipt_ref(cycle_index: int) -> str:
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_CYCLE_INVALID"
        )
    return (
        f"cycles/{cycle_index:04d}/market/v32-source-replay/"
        "durable-source-replay-receipt.json"
    )


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32DurableSourceReplayError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DurableSourceReplayError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32DurableSourceReplayError(code)
    return parsed.astimezone(UTC)


def _safe_relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise V32DurableSourceReplayError(code)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32DurableSourceReplayError(code)
    return value


def _typed_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _TYPED_BINDING_FIELDS:
        raise V32DurableSourceReplayError(code)
    result = {
        "relative_ref": _safe_relative(value.get("relative_ref"), code),
        "schema_id": str(value.get("schema_id") or ""),
        "digest_field": str(value.get("digest_field") or ""),
        "semantic_digest": str(value.get("semantic_digest") or ""),
        "physical_sha256": str(value.get("physical_sha256") or ""),
    }
    if (
        not result["schema_id"]
        or not result["digest_field"]
        or _HEX_64.fullmatch(result["semantic_digest"]) is None
        or _HEX_64.fullmatch(result["physical_sha256"]) is None
    ):
        raise V32DurableSourceReplayError(code)
    return result


def _expected_typed_binding(
    value: Any,
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, str]:
    binding = _typed_binding(value, code)
    if (
        binding["schema_id"] != schema_id
        or binding["digest_field"] != digest_field
    ):
        raise V32DurableSourceReplayError(code)
    return binding


def _raw_binding(value: Any, code: str) -> dict[str, str]:
    result = _evidence_binding(value, code)
    if result["semantic_digest"] != result["physical_sha256"]:
        raise V32DurableSourceReplayError(code)
    return result


def _evidence_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RAW_BINDING_FIELDS:
        raise V32DurableSourceReplayError(code)
    result = {
        "relative_ref": _safe_relative(value.get("relative_ref"), code),
        "semantic_digest": str(value.get("semantic_digest") or ""),
        "physical_sha256": str(value.get("physical_sha256") or ""),
    }
    if (
        _HEX_64.fullmatch(result["semantic_digest"]) is None
        or _HEX_64.fullmatch(result["physical_sha256"]) is None
    ):
        raise V32DurableSourceReplayError(code)
    return result


def _query(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise V32DurableSourceReplayError(code)
    query: dict[str, str] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(item, str)
            or not item
        ):
            raise V32DurableSourceReplayError(code)
        query[key] = item
    if list(query) != sorted(query):
        raise V32DurableSourceReplayError(code)
    return query


def _qualification_base(qualification_id: str) -> str:
    return qualification_ref(qualification_id).rsplit("/", 1)[0]


def _attempt_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/attempt-reservation.json"


def _component_slug(component_id: str) -> str:
    return component_id.lower().replace("_", "-")


def _component_raw_ref(qualification_id: str, component_id: str) -> str:
    return (
        f"{_qualification_base(qualification_id)}/raw/requests/"
        f"{_component_slug(component_id)}.body"
    )


def _component_failure_ref(qualification_id: str, component_id: str) -> str:
    return (
        f"{_qualification_base(qualification_id)}/component-failures/"
        f"{_component_slug(component_id)}.json"
    )


def _typed_binding_from_store(
    *,
    store: V32CycleSourceStorePort,
    relative_ref: str,
    digest_field: str,
    expected_semantic_digest: str,
) -> dict[str, str]:
    binding = store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=expected_semantic_digest,
    )
    return _typed_binding(binding, "V32_DURABLE_SOURCE_TYPED_BINDING_INVALID")


def _raw_binding_from_store(
    *, store: V32CycleSourceStorePort, relative_ref: str
) -> dict[str, str]:
    raw = store.read_raw(relative_ref=relative_ref)
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "relative_ref": relative_ref,
        "semantic_digest": digest,
        "physical_sha256": digest,
    }


def _read_attempt_binding(
    *,
    source_store: V32CycleSourceStorePort,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    authority_projection_digest: str,
    governing_authority_digest: str,
    contract_digest: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    relative_ref = _attempt_ref(qualification_id)
    raw = source_store.read_raw(relative_ref=relative_ref)
    attempt = loads_json_strict(raw)
    semantic = verify_self_digest(attempt, ATTEMPT_DIGEST_FIELD)
    if (
        attempt.get("schema_id") != ATTEMPT_SCHEMA_ID
        or attempt.get("qualification_id") != qualification_id
        or attempt.get("run_id") != run_id
        or attempt.get("cycle_index") != cycle_index
        or attempt.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != authority_projection_digest
        or attempt.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != governing_authority_digest
        or attempt.get("experiment_contract_digest") != contract_digest
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
        or attempt.get("single_source_collection_transaction") is not True
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_ATTEMPT_INVALID"
        )
    canonical = canonical_bytes(attempt) + b"\n"
    if raw != canonical:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_ATTEMPT_NONCANONICAL"
        )
    return attempt, {
        "relative_ref": relative_ref,
        "schema_id": ATTEMPT_SCHEMA_ID,
        "digest_field": ATTEMPT_DIGEST_FIELD,
        "semantic_digest": semantic,
        "physical_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _replay_typed_source_artifact(
    *,
    store: V32CycleSourceStorePort,
    binding: Mapping[str, Any],
    verifier: Any,
) -> dict[str, str]:
    normalized = _typed_binding(
        binding, "V32_DURABLE_SOURCE_TYPED_BINDING_INVALID"
    )
    document = store.read_document(
        relative_ref=normalized["relative_ref"],
        digest_field=normalized["digest_field"],
        expected_semantic_digest=normalized["semantic_digest"],
        expected_physical_sha256=normalized["physical_sha256"],
    )
    if (
        document.get("schema_id") != normalized["schema_id"]
        or verifier(document) != normalized["semantic_digest"]
        or store.read_raw(
            relative_ref=normalized["relative_ref"],
            expected_sha256=normalized["physical_sha256"],
        )
        != canonical_bytes(document) + b"\n"
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_TYPED_REPLAY_INVALID"
        )
    return normalized


def _run_copy_replays(
    *,
    run_store: V32CycleSourceStorePort,
    full_loader: Mapping[str, Any],
    source_bindings_by_role: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_source_refs: set[str] = set()
    seen_target_refs: set[str] = set()
    for copy_row in full_loader["artifact_copies"]:
        role = str(copy_row["artifact_role"])
        source = source_bindings_by_role.get(role)
        if source is None:
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_COPY_ROLE_INVALID"
            )
        if role == "RAW_RESPONSE":
            source_binding = _raw_binding(
                source, "V32_DURABLE_SOURCE_COPY_SOURCE_INVALID"
            )
            target_binding = _raw_binding_from_store(
                store=run_store,
                relative_ref=str(copy_row["target_relative_ref"]),
            )
        else:
            source_binding = _typed_binding(
                source, "V32_DURABLE_SOURCE_COPY_SOURCE_INVALID"
            )
            target_binding = _typed_binding_from_store(
                store=run_store,
                relative_ref=str(copy_row["target_relative_ref"]),
                digest_field=str(copy_row["digest_field"]),
                expected_semantic_digest=str(copy_row["semantic_digest"]),
            )
        if (
            source_binding["relative_ref"] != copy_row["source_relative_ref"]
            or source_binding["semantic_digest"] != copy_row["semantic_digest"]
            or source_binding["physical_sha256"]
            != copy_row["source_physical_sha256"]
            or target_binding["relative_ref"] != copy_row["target_relative_ref"]
            or target_binding["semantic_digest"] != copy_row["semantic_digest"]
            or target_binding["physical_sha256"]
            != copy_row["target_physical_sha256"]
            or source_binding["physical_sha256"]
            != target_binding["physical_sha256"]
            or copy_row.get("exact_bytes_copied") is not True
            or copy_row.get("readback_verified") is not True
            or source_binding["relative_ref"] in seen_source_refs
            or target_binding["relative_ref"] in seen_target_refs
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_COPY_REPLAY_INVALID"
            )
        seen_source_refs.add(source_binding["relative_ref"])
        seen_target_refs.add(target_binding["relative_ref"])
        rows.append(
            {
                "artifact_role": role,
                "source_binding": source_binding,
                "target_binding": target_binding,
                "exact_bytes_copied": True,
                "readback_verified": True,
            }
        )
    rows.sort(key=lambda row: row["artifact_role"])
    if [row["artifact_role"] for row in rows] != sorted(
        [
            "MARKET_SNAPSHOT",
            "PIT_REGISTRY",
            "RAW_RESPONSE",
            "SOURCE_CAPTURE",
            "SOURCE_QUALIFICATION",
        ]
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_COPY_SET_INVALID"
        )
    return rows


def _build_replay_receipt(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    source_store: V32CycleSourceStorePort,
    run_store: V32CycleSourceStorePort,
    active_authority: Mapping[str, Any],
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    replayed_at: str,
) -> dict[str, Any]:
    authority_projection_digest = verify_v32_active_authority_projection(
        active_authority
    )
    governing_authority_digest = str(
        active_authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
    )
    contract_digest = str(active_authority["experiment_contract_digest"])
    if active_authority.get("authorized_run_id") != run_id:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_AUTHORITY_RUN_MISMATCH"
        )
    replay_time = _time(replayed_at, "V32_DURABLE_SOURCE_REPLAY_TIME_INVALID")

    source_replay = public_evidence_verifier.replay_durable_public_source_qualification(
        store=source_store,
        qualification_id=qualification_id,
        active_authority=active_authority,
    )
    admission_replay = verify_durable_v32_cycle_source_admission(
        run_store=run_store,
        run_id=run_id,
        cycle_index=cycle_index,
        expected_authority_projection_digest=authority_projection_digest,
        expected_governing_authority_digest=governing_authority_digest,
        expected_experiment_contract_digest=contract_digest,
    )
    qualification = source_replay.formal_qualification
    analysis = source_replay.public_market_analysis_bundle
    capture = source_replay.source_capture
    snapshot = source_replay.market_snapshot
    pit = source_replay.pit_registry
    admission = admission_replay["cycle_source_admission"]
    full_loader = admission_replay["full_loader_receipt"]
    if (
        source_replay.run_id != run_id
        or source_replay.cycle_index != cycle_index
        or qualification.get("qualification_id") != qualification_id
        or qualification.get("decision_time") != admission.get("decision_time")
        or replay_time
        < _time(admission["decision_time"], "V32_DURABLE_SOURCE_REPLAY_TIME_INVALID")
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_TRANSACTION_IDENTITY_INVALID"
        )

    attempt, attempt_binding = _read_attempt_binding(
        source_store=source_store,
        qualification_id=qualification_id,
        run_id=run_id,
        cycle_index=cycle_index,
        authority_projection_digest=authority_projection_digest,
        governing_authority_digest=governing_authority_digest,
        contract_digest=contract_digest,
    )
    aggregate_raw_binding = _raw_binding(
        source_replay.raw_binding,
        "V32_DURABLE_SOURCE_AGGREGATE_RAW_INVALID",
    )
    aggregate_raw = source_store.read_raw(
        relative_ref=aggregate_raw_binding["relative_ref"],
        expected_sha256=aggregate_raw_binding["physical_sha256"],
    )
    if hashlib.sha256(aggregate_raw).hexdigest() != aggregate_raw_binding[
        "semantic_digest"
    ]:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_AGGREGATE_RAW_INVALID"
        )
    aggregate_document = loads_json_strict(aggregate_raw)
    if (
        not isinstance(aggregate_document, Mapping)
        or aggregate_document.get("schema_id") != RAW_BUNDLE_SCHEMA_ID
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_RAW_SCHEMA_ID_INVALID"
        )
    if aggregate_document.get("schema_version") != RAW_BUNDLE_SCHEMA_VERSION:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_RAW_SCHEMA_VERSION_UNSUPPORTED"
        )
    aggregate_components = aggregate_document.get("components")
    if (
        not isinstance(aggregate_components, list)
        or any(not isinstance(row, Mapping) for row in aggregate_components)
        or [row.get("component_id") for row in aggregate_components]
        != list(_COMPONENT_ORDER)
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_AGGREGATE_COMPONENT_SET_INVALID"
        )
    aggregate_by_component = {
        row["component_id"]: row for row in aggregate_components
    }

    analysis_binding = _replay_typed_source_artifact(
        store=source_store,
        binding=source_replay.public_market_analysis_bundle_binding,
        verifier=public_evidence_verifier.verify_public_market_analysis_bundle,
    )
    capture_binding = _replay_typed_source_artifact(
        store=source_store,
        binding=source_replay.source_capture_binding,
        verifier=verify_v32_public_source_capture,
    )
    snapshot_binding = _replay_typed_source_artifact(
        store=source_store,
        binding=source_replay.market_snapshot_binding,
        verifier=verify_v32_public_market_snapshot,
    )
    pit_binding = _replay_typed_source_artifact(
        store=source_store,
        binding=source_replay.pit_registry_binding,
        verifier=verify_v32_pit_evidence_registry,
    )
    qualification_binding = _replay_typed_source_artifact(
        store=source_store,
        binding=source_replay.formal_qualification_binding,
        verifier=verify_v32_formal_source_qualification,
    )
    full_loader_binding = _replay_typed_source_artifact(
        store=run_store,
        binding=admission_replay["full_loader_receipt_binding"],
        verifier=verify_v32_cycle_source_full_loader_receipt,
    )
    admission_binding = _replay_typed_source_artifact(
        store=run_store,
        binding=admission_replay["cycle_source_admission_binding"],
        verifier=verify_v32_cycle_source_admission,
    )

    request_rows = analysis["request_raw_bindings"]
    event_by_component = {
        row["component_id"]: row for row in analysis["information_events"]
    }
    if (
        len(request_rows) != len(event_by_component)
        or [row.get("component_id") for row in request_rows]
        != list(_COMPONENT_ORDER)
        or len({row["request_id"] for row in request_rows}) != len(request_rows)
        or any(
            row.get("attempt_number") != 1
            or row.get("retry_allowed") is not False
            for row in request_rows
        )
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REQUEST_SET_INVALID"
        )
    request_replays: list[dict[str, Any]] = []
    replayed_raw_refs: set[str] = set()
    verified_no_response_failure_bindings: list[dict[str, str]] = []
    replay_no_response_failure = (
        public_evidence_verifier.replay_durable_component_no_response_failure
    )
    for row in request_rows:
        component_id = str(row["component_id"])
        event = event_by_component.get(component_id)
        aggregate_component = aggregate_by_component.get(component_id)
        query = _query(
            row.get("query"), "V32_DURABLE_SOURCE_REQUEST_QUERY_INVALID"
        )
        if (
            event is None
            or row.get("method") != "GET"
            or row.get("base_url") != OKX_PUBLIC_BASE_URL
            or row.get("path") != _COMPONENT_PATHS.get(component_id)
            or row.get("status") not in {"OBSERVED", "UNKNOWN"}
            or (
                row.get("status") == "UNKNOWN"
                and component_id not in _OPTIONAL_COMPONENTS
            )
            or (
                row.get("status") == "OBSERVED"
                and (
                    row.get("raw_binding") is None
                    or row.get("failure_evidence_binding") is not None
                    or row.get("error_code") is not None
                )
            )
            or (
                row.get("status") == "UNKNOWN"
                and (
                    row.get("failure_evidence_binding") is None
                    or not isinstance(row.get("error_code"), str)
                    or _REASON_CODE.fullmatch(row["error_code"]) is None
                )
            )
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_EVENT_SET_INVALID"
            )
        verify_self_digest(event, INFORMATION_EVENT_DIGEST_FIELD)
        raw_binding: dict[str, str] | None = None
        failure_binding: dict[str, str] | None = None
        failure_receipt: Mapping[str, Any] | None = None
        if row["raw_binding"] is not None:
            raw_binding = _raw_binding(
                row["raw_binding"],
                "V32_DURABLE_SOURCE_REQUEST_RAW_INVALID",
            )
            raw = source_store.read_raw(
                relative_ref=raw_binding["relative_ref"],
                expected_sha256=raw_binding["physical_sha256"],
            )
            if (
                hashlib.sha256(raw).hexdigest()
                != raw_binding["semantic_digest"]
                or raw_binding["relative_ref"] in replayed_raw_refs
                or raw_binding["relative_ref"]
                != _component_raw_ref(qualification_id, component_id)
            ):
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REQUEST_RAW_INVALID"
                )
            replayed_raw_refs.add(raw_binding["relative_ref"])
        if row["status"] == "OBSERVED":
            if row["failure_evidence_binding"] is not None:
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REQUEST_FAILURE_BINDING_INVALID"
                )
        elif raw_binding is not None:
            failure_binding = _raw_binding(
                row["failure_evidence_binding"],
                "V32_DURABLE_SOURCE_REQUEST_FAILURE_BINDING_INVALID",
            )
            if failure_binding != raw_binding:
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REQUEST_FAILURE_BINDING_INVALID"
                )
        else:
            failure_binding = _evidence_binding(
                row["failure_evidence_binding"],
                "V32_DURABLE_SOURCE_REQUEST_FAILURE_BINDING_INVALID",
            )
            if failure_binding["relative_ref"] != _component_failure_ref(
                qualification_id, component_id
            ):
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REQUEST_FAILURE_BINDING_INVALID"
                )
            failure_receipt = (
                replay_no_response_failure(
                    store=source_store,
                    qualification_id=qualification_id,
                    component_id=component_id,
                    binding=failure_binding,
                )
            )
            verified_no_response_failure_bindings.append(failure_binding)
        if (
            not isinstance(aggregate_component, Mapping)
            or aggregate_component.get("method") != row.get("method")
            or aggregate_component.get("path") != row.get("path")
            or aggregate_component.get("query") != row.get("query")
            or aggregate_component.get("status") != row.get("status")
            or (
                row.get("status") == "OBSERVED"
                and aggregate_component.get("http_status") != 200
            )
            or (
                row.get("status") == "UNKNOWN"
                and (
                    (
                        raw_binding is not None
                        and aggregate_component.get("http_status")
                        not in _TRANSIENT_HTTP_STATUS_CODES
                    )
                    or (
                        raw_binding is None
                        and aggregate_component.get("http_status") is not None
                    )
                )
            )
            or aggregate_component.get("error_code") != row.get("error_code")
            or aggregate_component.get("request_started_at")
            != row.get("request_started_at")
            or aggregate_component.get("response_received_at")
            != row.get("response_received_at")
            or aggregate_component.get("raw_binding") != row.get("raw_binding")
            or aggregate_component.get("failure_evidence_binding")
            != row.get("failure_evidence_binding")
            or event.get("raw_binding") != row.get("raw_binding")
            or event.get("failure_evidence_binding")
            != row.get("failure_evidence_binding")
            or event.get("status") != row.get("status")
            or event.get("available_at") != row.get("response_received_at")
            or event.get("request_path") != row.get("path")
            or event.get("request_query") != row.get("query")
            or event.get("reason_code") != row.get("error_code")
            or (
                failure_receipt is not None
                and (
                    failure_receipt.get("method") != row.get("method")
                    or failure_receipt.get("base_url") != row.get("base_url")
                    or failure_receipt.get("path") != row.get("path")
                    or failure_receipt.get("query") != row.get("query")
                    or failure_receipt.get("request_started_at")
                    != row.get("request_started_at")
                    or failure_receipt.get("failure_at")
                    != row.get("response_received_at")
                    or failure_receipt.get("failure_codes", [None])[-1]
                    != row.get("error_code")
                )
            )
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_EVENT_REQUEST_MISMATCH"
            )
        request_replays.append(
            {
                "component_id": component_id,
                "request_id": row["request_id"],
                "method": row["method"],
                "base_url": row["base_url"],
                "path": row["path"],
                "query": query,
                "status": row["status"],
                "http_status": aggregate_component["http_status"],
                "error_code": row["error_code"],
                "attempt_number": 1,
                "retry_allowed": False,
                "request_started_at": row["request_started_at"],
                "response_received_at": row["response_received_at"],
                "raw_binding": raw_binding,
                "failure_evidence_binding": failure_binding,
                "event_semantic_digest": event[INFORMATION_EVENT_DIGEST_FIELD],
                "event_carrier_binding": analysis_binding,
            }
        )

    source_bindings_by_role = {
        "SOURCE_QUALIFICATION": qualification_binding,
        "SOURCE_CAPTURE": capture_binding,
        "MARKET_SNAPSHOT": snapshot_binding,
        "PIT_REGISTRY": pit_binding,
        "RAW_RESPONSE": aggregate_raw_binding,
    }
    run_copy_replays = _run_copy_replays(
        run_store=run_store,
        full_loader=full_loader,
        source_bindings_by_role=source_bindings_by_role,
    )
    copied_by_role = {
        row["artifact_role"]: row["target_binding"]
        for row in run_copy_replays
    }
    if (
        copied_by_role["SOURCE_QUALIFICATION"]
        != admission["qualification_binding"]
        or copied_by_role["SOURCE_CAPTURE"] != admission["capture_binding"]
        or copied_by_role["MARKET_SNAPSHOT"]
        != admission["current_snapshot_binding"]
        or copied_by_role["PIT_REGISTRY"] != admission["pit_registry_binding"]
        or analysis_binding["semantic_digest"] not in pit["members"]
        or analysis_binding["semantic_digest"]
        not in run_store.read_document(
            relative_ref=copied_by_role["PIT_REGISTRY"]["relative_ref"],
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
            expected_semantic_digest=copied_by_role["PIT_REGISTRY"][
                "semantic_digest"
            ],
            expected_physical_sha256=copied_by_role["PIT_REGISTRY"][
                "physical_sha256"
            ],
        )["members"]
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_ANALYSIS_PIT_BINDING_INVALID"
        )

    sealed_raw_bindings = [
        aggregate_raw_binding,
        *[
            row["raw_binding"]
            for row in request_replays
            if row["raw_binding"] is not None
        ],
    ]
    return self_digest(
        {
            "schema_id": RECEIPT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "qualification_id": qualification_id,
            "replayed_at": replayed_at,
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: (
                authority_projection_digest
            ),
            GOVERNING_AUTHORITY_DIGEST_FIELD: governing_authority_digest,
            "experiment_contract_digest": contract_digest,
            "attempt_reservation_binding": attempt_binding,
            "aggregate_raw_binding": aggregate_raw_binding,
            "request_replays": request_replays,
            "market_analysis_bundle_binding": analysis_binding,
            "source_capture_binding": capture_binding,
            "source_snapshot_binding": snapshot_binding,
            "source_pit_registry_binding": pit_binding,
            "source_qualification_binding": qualification_binding,
            "run_copy_replays": run_copy_replays,
            "full_loader_receipt_binding": full_loader_binding,
            "cycle_source_admission_binding": admission_binding,
            "transaction_proof": {
                "attempt_id": capture["attempt_id"],
                "capture_digest": capture[CAPTURE_DIGEST_FIELD],
                "qualification_digest": qualification[
                    QUALIFICATION_DIGEST_FIELD
                ],
                "snapshot_digest": snapshot[SNAPSHOT_DIGEST_FIELD],
                "pit_registry_digest": pit[PIT_REGISTRY_DIGEST_FIELD],
                "full_loader_digest": full_loader[FULL_LOADER_DIGEST_FIELD],
                "source_admission_digest": admission[
                    SOURCE_ADMISSION_DIGEST_FIELD
                ],
                "single_source_collection_transaction": True,
                "attempt_count": 1,
                "request_count": len(request_replays),
                "each_request_attempt_count": 1,
                "retry_allowed": False,
                "request_ids": [row["request_id"] for row in request_replays],
            },
            "raw_before_derived_proof": {
                "method": "EXACT_RAW_RECONSTRUCTION_AND_DERIVED_BYTE_MATCH",
                "attempt_started_at": attempt["started_at"],
                "sealed_raw_bindings": sealed_raw_bindings,
                "verified_no_response_failure_bindings": (
                    verified_no_response_failure_bindings
                ),
                "derived_typed_bindings": [
                    analysis_binding,
                    capture_binding,
                    snapshot_binding,
                    pit_binding,
                    qualification_binding,
                    full_loader_binding,
                    admission_binding,
                ],
                "analysis_reconstructed_from_sealed_raw": True,
                "all_response_raws_read_before_receipt": True,
                "derived_documents_exact_canonical_bytes": True,
            },
            "physical_replay_verified": True,
            "semantic_replay_verified": True,
            "point_in_time_verified": True,
            "analysis_bundle_digest_is_pit_member": True,
            "replay_network_calls": 0,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
        },
        RECEIPT_DIGEST_FIELD,
    )


def verify_v32_durable_source_replay_receipt(
    document: Mapping[str, Any],
) -> str:
    if (
        isinstance(document, Mapping)
        and document.get("schema_id") == RECEIPT_SCHEMA_ID
        and document.get("schema_version") != SCHEMA_VERSION
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_SCHEMA_VERSION_UNSUPPORTED"
        )
    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, RECEIPT_DIGEST_FIELD)
    except ValueError as exc:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        ) from exc
    requests = document.get("request_replays")
    copies = document.get("run_copy_replays")
    transaction = document.get("transaction_proof")
    raw_proof = document.get("raw_before_derived_proof")
    if (
        document.get("schema_id") != RECEIPT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or not isinstance(document.get("run_id"), str)
        or not document["run_id"]
        or isinstance(document.get("cycle_index"), bool)
        or not isinstance(document.get("cycle_index"), int)
        or not 1 <= document["cycle_index"] <= 16
        or not isinstance(document.get("qualification_id"), str)
        or not document["qualification_id"]
        or _HEX_64.fullmatch(
            str(document.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD))
        )
        is None
        or _HEX_64.fullmatch(
            str(document.get(GOVERNING_AUTHORITY_DIGEST_FIELD))
        )
        is None
        or _HEX_64.fullmatch(str(document.get("experiment_contract_digest")))
        is None
        or document.get("physical_replay_verified") is not True
        or document.get("semantic_replay_verified") is not True
        or document.get("point_in_time_verified") is not True
        or document.get("analysis_bundle_digest_is_pit_member") is not True
        or document.get("replay_network_calls") != 0
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("account_data_accessed") is not False
        or document.get("order_data_accessed") is not False
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    replayed_at = _time(
        document["replayed_at"],
        "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
    )
    attempt_binding = _expected_typed_binding(
        document["attempt_reservation_binding"],
        schema_id=ATTEMPT_SCHEMA_ID,
        digest_field=ATTEMPT_DIGEST_FIELD,
        code="V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
    )
    aggregate_binding = _raw_binding(
        document["aggregate_raw_binding"],
        "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
    )
    typed_specs = {
        "market_analysis_bundle_binding": (
            ANALYSIS_BUNDLE_SCHEMA_ID,
            ANALYSIS_BUNDLE_DIGEST_FIELD,
        ),
        "source_capture_binding": (CAPTURE_SCHEMA_ID, CAPTURE_DIGEST_FIELD),
        "source_snapshot_binding": (
            SNAPSHOT_SCHEMA_ID,
            SNAPSHOT_DIGEST_FIELD,
        ),
        "source_pit_registry_binding": (
            PIT_REGISTRY_SCHEMA_ID,
            PIT_REGISTRY_DIGEST_FIELD,
        ),
        "source_qualification_binding": (
            QUALIFICATION_SCHEMA_ID,
            QUALIFICATION_DIGEST_FIELD,
        ),
        "full_loader_receipt_binding": (
            FULL_LOADER_SCHEMA_ID,
            FULL_LOADER_DIGEST_FIELD,
        ),
        "cycle_source_admission_binding": (
            SOURCE_ADMISSION_SCHEMA_ID,
            SOURCE_ADMISSION_DIGEST_FIELD,
        ),
    }
    typed_bindings = {
        key: _expected_typed_binding(
            document[key],
            schema_id=schema_id,
            digest_field=digest_field,
            code="V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
        )
        for key, (schema_id, digest_field) in typed_specs.items()
    }

    if not isinstance(requests, list) or len(requests) != len(_COMPONENT_ORDER):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    request_ids: list[str] = []
    replayed_raw_bindings: list[dict[str, str]] = []
    replayed_raw_refs: set[str] = set()
    no_response_failure_bindings: list[dict[str, str]] = []
    no_response_failure_refs: set[str] = set()
    request_started_times: list[datetime] = []
    for index, row in enumerate(requests):
        component_id = _COMPONENT_ORDER[index]
        if (
            not isinstance(row, Mapping)
            or set(row) != _REQUEST_REPLAY_FIELDS
            or row.get("component_id") != component_id
            or not isinstance(row.get("request_id"), str)
            or not row["request_id"]
            or row.get("method") != "GET"
            or row.get("base_url") != OKX_PUBLIC_BASE_URL
            or row.get("path") != _COMPONENT_PATHS[component_id]
            or row.get("attempt_number") != 1
            or row.get("retry_allowed") is not False
            or _HEX_64.fullmatch(str(row.get("event_semantic_digest")))
            is None
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        _query(
            row["query"], "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
        request_started = _time(
            row["request_started_at"],
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
        )
        response_received = _time(
            row["response_received_at"],
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
        )
        if request_started > response_received or response_received > replayed_at:
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        event_carrier = _expected_typed_binding(
            row["event_carrier_binding"],
            schema_id=ANALYSIS_BUNDLE_SCHEMA_ID,
            digest_field=ANALYSIS_BUNDLE_DIGEST_FIELD,
            code="V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
        )
        if event_carrier != typed_bindings["market_analysis_bundle_binding"]:
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        if row["status"] == "OBSERVED":
            raw_binding = _raw_binding(
                row["raw_binding"],
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
            if (
                row["failure_evidence_binding"] is not None
                or row.get("http_status") != 200
                or row.get("error_code") is not None
                or raw_binding["relative_ref"]
                != _component_raw_ref(document["qualification_id"], component_id)
                or raw_binding["relative_ref"] in replayed_raw_refs
            ):
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
                )
            replayed_raw_refs.add(raw_binding["relative_ref"])
            replayed_raw_bindings.append(raw_binding)
        elif row["status"] == "UNKNOWN":
            if (
                component_id not in _OPTIONAL_COMPONENTS
                or not isinstance(row.get("error_code"), str)
                or _REASON_CODE.fullmatch(row["error_code"]) is None
            ):
                raise V32DurableSourceReplayError(
                    "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
                )
            if row["raw_binding"] is not None:
                raw_binding = _raw_binding(
                    row["raw_binding"],
                    "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
                )
                failure_binding = _raw_binding(
                    row["failure_evidence_binding"],
                    "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
                )
                if (
                    failure_binding != raw_binding
                    or row.get("http_status")
                    not in _TRANSIENT_HTTP_STATUS_CODES
                    or raw_binding["relative_ref"]
                    != _component_raw_ref(
                        document["qualification_id"], component_id
                    )
                    or raw_binding["relative_ref"] in replayed_raw_refs
                ):
                    raise V32DurableSourceReplayError(
                        "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
                    )
                replayed_raw_refs.add(raw_binding["relative_ref"])
                replayed_raw_bindings.append(raw_binding)
            else:
                failure_binding = _evidence_binding(
                    row["failure_evidence_binding"],
                    "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
                )
                if (
                    row.get("http_status") is not None
                    or failure_binding["relative_ref"]
                    != _component_failure_ref(
                        document["qualification_id"], component_id
                    )
                    or failure_binding["relative_ref"]
                    in no_response_failure_refs
                ):
                    raise V32DurableSourceReplayError(
                        "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
                    )
                no_response_failure_refs.add(failure_binding["relative_ref"])
                no_response_failure_bindings.append(failure_binding)
        else:
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        request_ids.append(row["request_id"])
        request_started_times.append(request_started)
    if len(set(request_ids)) != len(request_ids):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )

    expected_sources: dict[str, Mapping[str, Any]] = {
        "MARKET_SNAPSHOT": typed_bindings["source_snapshot_binding"],
        "PIT_REGISTRY": typed_bindings["source_pit_registry_binding"],
        "RAW_RESPONSE": aggregate_binding,
        "SOURCE_CAPTURE": typed_bindings["source_capture_binding"],
        "SOURCE_QUALIFICATION": typed_bindings[
            "source_qualification_binding"
        ],
    }
    expected_roles = sorted(expected_sources)
    if not isinstance(copies, list) or len(copies) != len(expected_roles):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    source_refs: set[str] = set()
    target_refs: set[str] = set()
    for index, row in enumerate(copies):
        if (
            not isinstance(row, Mapping)
            or set(row) != _RUN_COPY_FIELDS
            or row.get("artifact_role") != expected_roles[index]
            or row.get("exact_bytes_copied") is not True
            or row.get("readback_verified") is not True
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        role = row["artifact_role"]
        if role == "RAW_RESPONSE":
            source_binding = _raw_binding(
                row["source_binding"],
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
            target_binding = _raw_binding(
                row["target_binding"],
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
        else:
            expected_source = _typed_binding(
                expected_sources[role],
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
            source_binding = _expected_typed_binding(
                row["source_binding"],
                schema_id=expected_source["schema_id"],
                digest_field=expected_source["digest_field"],
                code="V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
            target_binding = _expected_typed_binding(
                row["target_binding"],
                schema_id=expected_source["schema_id"],
                digest_field=expected_source["digest_field"],
                code="V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
            )
        if (
            source_binding != expected_sources[role]
            or source_binding["semantic_digest"]
            != target_binding["semantic_digest"]
            or source_binding["physical_sha256"]
            != target_binding["physical_sha256"]
            or source_binding["relative_ref"] in source_refs
            or target_binding["relative_ref"] in target_refs
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
            )
        source_refs.add(source_binding["relative_ref"])
        target_refs.add(target_binding["relative_ref"])

    if (
        not isinstance(transaction, Mapping)
        or set(transaction) != _TRANSACTION_PROOF_FIELDS
        or not isinstance(transaction.get("attempt_id"), str)
        or not transaction["attempt_id"]
        or transaction.get("capture_digest")
        != typed_bindings["source_capture_binding"]["semantic_digest"]
        or transaction.get("qualification_digest")
        != typed_bindings["source_qualification_binding"]["semantic_digest"]
        or transaction.get("snapshot_digest")
        != typed_bindings["source_snapshot_binding"]["semantic_digest"]
        or transaction.get("pit_registry_digest")
        != typed_bindings["source_pit_registry_binding"]["semantic_digest"]
        or transaction.get("full_loader_digest")
        != typed_bindings["full_loader_receipt_binding"]["semantic_digest"]
        or transaction.get("source_admission_digest")
        != typed_bindings["cycle_source_admission_binding"]["semantic_digest"]
        or transaction.get("single_source_collection_transaction") is not True
        or transaction.get("attempt_count") != 1
        or transaction.get("request_count") != len(requests)
        or transaction.get("each_request_attempt_count") != 1
        or transaction.get("retry_allowed") is not False
        or transaction.get("request_ids") != request_ids
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )

    expected_derived = [
        typed_bindings["market_analysis_bundle_binding"],
        typed_bindings["source_capture_binding"],
        typed_bindings["source_snapshot_binding"],
        typed_bindings["source_pit_registry_binding"],
        typed_bindings["source_qualification_binding"],
        typed_bindings["full_loader_receipt_binding"],
        typed_bindings["cycle_source_admission_binding"],
    ]
    if (
        not isinstance(raw_proof, Mapping)
        or set(raw_proof) != _RAW_BEFORE_DERIVED_FIELDS
        or raw_proof.get("method")
        != "EXACT_RAW_RECONSTRUCTION_AND_DERIVED_BYTE_MATCH"
        or raw_proof.get("sealed_raw_bindings")
        != [aggregate_binding, *replayed_raw_bindings]
        or raw_proof.get("verified_no_response_failure_bindings")
        != no_response_failure_bindings
        or raw_proof.get("derived_typed_bindings") != expected_derived
        or raw_proof.get("analysis_reconstructed_from_sealed_raw") is not True
        or raw_proof.get("all_response_raws_read_before_receipt")
        is not True
        or raw_proof.get("derived_documents_exact_canonical_bytes") is not True
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    attempt_started_at = _time(
        raw_proof["attempt_started_at"],
        "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID",
    )
    if (
        attempt_started_at > min(request_started_times)
        or attempt_started_at > replayed_at
        or attempt_binding["relative_ref"] in source_refs
    ):
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_RECEIPT_INVALID"
        )
    return supplied


def compose_and_persist_v32_durable_source_replay_receipt(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    source_store: V32CycleSourceStorePort,
    run_store: V32CycleSourceStorePort,
    active_authority: Mapping[str, Any],
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    replayed_at: str,
) -> dict[str, Any]:
    """Replay the source chain, write one receipt, and return acceptance inputs."""

    try:
        receipt = _build_replay_receipt(
            public_evidence_verifier=public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=active_authority,
            qualification_id=qualification_id,
            run_id=run_id,
            cycle_index=cycle_index,
            replayed_at=replayed_at,
        )
        verify_v32_durable_source_replay_receipt(receipt)
        relative_ref = durable_source_replay_receipt_ref(cycle_index)
        binding = run_store.write_document(
            relative_ref=relative_ref,
            document=receipt,
            digest_field=RECEIPT_DIGEST_FIELD,
        )
        durable = run_store.read_document(
            relative_ref=relative_ref,
            digest_field=RECEIPT_DIGEST_FIELD,
            expected_semantic_digest=receipt[RECEIPT_DIGEST_FIELD],
            expected_physical_sha256=binding["physical_sha256"],
        )
        raw = run_store.read_raw(
            relative_ref=relative_ref,
            expected_sha256=binding["physical_sha256"],
        )
        if (
            durable != receipt
            or raw != canonical_bytes(receipt) + b"\n"
            or verify_v32_durable_source_replay_receipt(durable)
            != receipt[RECEIPT_DIGEST_FIELD]
        ):
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_READBACK_INVALID"
            )
        return {
            "durable_source_replay_receipt": receipt,
            "durable_source_replay_receipt_binding": binding,
            "acceptance_inputs": {
                "durable_source_replay_receipt_binding": binding,
                "public_market_analysis_bundle_binding": receipt[
                    "market_analysis_bundle_binding"
                ],
                "cycle_source_admission_binding": receipt[
                    "cycle_source_admission_binding"
                ],
                "pit_registry_binding": receipt[
                    "source_pit_registry_binding"
                ],
            },
        }
    except V32DurableSourceReplayError:
        raise
    except (
        V32CycleSourcePersistenceError,
        V32PublicEvidenceVerificationError,
        V32CycleSourceAdmissionWorkflowError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_FAILED"
        ) from exc


def verify_durable_v32_source_replay_receipt(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    source_store: V32CycleSourceStorePort,
    run_store: V32CycleSourceStorePort,
    active_authority: Mapping[str, Any],
    qualification_id: str,
    run_id: str,
    cycle_index: int,
) -> dict[str, Any]:
    """Recompose a stored receipt and reject semantic or physical alternatives."""

    try:
        relative_ref = durable_source_replay_receipt_ref(cycle_index)
        receipt = run_store.read_document(
            relative_ref=relative_ref,
            digest_field=RECEIPT_DIGEST_FIELD,
        )
        verify_v32_durable_source_replay_receipt(receipt)
        raw = run_store.read_raw(relative_ref=relative_ref)
        if raw != canonical_bytes(receipt) + b"\n":
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_NONCANONICAL"
            )
        expected = _build_replay_receipt(
            public_evidence_verifier=public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=active_authority,
            qualification_id=qualification_id,
            run_id=run_id,
            cycle_index=cycle_index,
            replayed_at=receipt["replayed_at"],
        )
        if receipt != expected:
            raise V32DurableSourceReplayError(
                "V32_DURABLE_SOURCE_REPLAY_RECEIPT_MISMATCH"
            )
        binding = _typed_binding_from_store(
            store=run_store,
            relative_ref=relative_ref,
            digest_field=RECEIPT_DIGEST_FIELD,
            expected_semantic_digest=receipt[RECEIPT_DIGEST_FIELD],
        )
        return {
            "durable_source_replay_receipt": receipt,
            "durable_source_replay_receipt_binding": binding,
            "acceptance_inputs": {
                "durable_source_replay_receipt_binding": binding,
                "public_market_analysis_bundle_binding": receipt[
                    "market_analysis_bundle_binding"
                ],
                "cycle_source_admission_binding": receipt[
                    "cycle_source_admission_binding"
                ],
                "pit_registry_binding": receipt[
                    "source_pit_registry_binding"
                ],
            },
        }
    except V32DurableSourceReplayError:
        raise
    except (
        V32CycleSourcePersistenceError,
        V32PublicEvidenceVerificationError,
        V32CycleSourceAdmissionWorkflowError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32DurableSourceReplayError(
            "V32_DURABLE_SOURCE_REPLAY_FAILED"
        ) from exc


__all__ = [
    "RECEIPT_DIGEST_FIELD",
    "RECEIPT_SCHEMA_ID",
    "V32DurableSourceReplayError",
    "compose_and_persist_v32_durable_source_replay_receipt",
    "durable_source_replay_receipt_ref",
    "verify_durable_v32_source_replay_receipt",
    "verify_v32_durable_source_replay_receipt",
]
