"""Fail-closed data-gap escalation and future-only manual public evidence."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .contracts.canonical import canonical_bytes, self_digest, verify_self_digest
from .v32_authorized_revision_common import (
    SCHEMA_VERSION,
    V32AuthorizedRevisionContractError,
    binding,
    boundary,
    digest,
    integer,
    moment,
    text,
    time,
    verify_boundary,
)


ESCALATION_SCHEMA_ID = "theory_paper_v32_data_gap_escalation_v1"
ESCALATION_DIGEST_FIELD = "data_gap_escalation_digest"
MANUAL_REVISION_SCHEMA_ID = "theory_paper_v32_manual_public_evidence_revision_v1"
MANUAL_REVISION_DIGEST_FIELD = "manual_public_evidence_revision_digest"
POLICY_SCHEMA_ID = "theory_paper_v32_data_gap_manual_policy_v1"
POLICY_DIGEST_FIELD = "data_gap_manual_policy_digest"
OFFICIAL_SOURCE_KINDS = frozenset(
    {
        "OFFICIAL_REGULATOR",
        "OFFICIAL_CENTRAL_BANK",
        "OFFICIAL_EXCHANGE_PUBLIC",
        "OFFICIAL_ISSUER",
        "OFFICIAL_PUBLIC_STATISTICS",
    }
)
MANUAL_CAPTURE_STEPS = (
    "OPEN_ALLOWLISTED_OFFICIAL_PUBLIC_SOURCE",
    "CAPTURE_SCREENSHOT_OR_OFFICIAL_EXPORT",
    "SAVE_UNMODIFIED_ORIGINAL_RAW_BYTES",
    "RECORD_OBSERVED_AVAILABLE_AND_CAPTURE_TIMES",
    "COMPUTE_SEMANTIC_AND_PHYSICAL_SHA256",
    "VERIFY_INSTRUMENT_FIELD_UNIT_AND_TIME",
    "SUBMIT_AS_NEW_FUTURE_CYCLE_REVISION",
)


class V32DataGapEscalationError(ValueError):
    """A data gap was hidden, backfilled, or sourced outside the allowlist."""


def build_v32_data_gap_manual_policy_v1(
    *, policy_id: str, run_scope_id: str, frozen_at: str
) -> dict[str, Any]:
    """Freeze fail-closed escalation and future-only manual readmission."""

    try:
        document = {
            "schema_id": POLICY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "policy_id": text(policy_id, "V32_DATA_GAP_POLICY_ID_INVALID"),
            "run_scope_id": text(
                run_scope_id, "V32_DATA_GAP_POLICY_RUN_SCOPE_INVALID"
            ),
            "frozen_at": time(frozen_at, "V32_DATA_GAP_POLICY_TIME_INVALID"),
            "official_source_kinds": sorted(OFFICIAL_SOURCE_KINDS),
            "manual_capture_steps": list(MANUAL_CAPTURE_STEPS),
            "automatic_request_method": "GET",
            "same_attempt_retry_allowed": False,
            "failure_value_status": "UNKNOWN",
            "zero_imputation_allowed": False,
            "manual_source_type": "MANUAL_PUBLIC_EVIDENCE",
            "https_official_allowlist_required": True,
            "raw_and_capture_bindings_required": True,
            "semantic_and_physical_digests_required": True,
            "observed_available_capture_verify_time_order_required": True,
            "future_cycle_readmission_required": True,
            "historical_backfill_allowed": False,
            "sealed_pit_history_mutation_allowed": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        raise V32DataGapEscalationError(
            "V32_DATA_GAP_POLICY_INPUT_INVALID"
        ) from exc
    return self_digest(document, POLICY_DIGEST_FIELD)


def verify_v32_data_gap_manual_policy_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, POLICY_DIGEST_FIELD)
        verify_boundary(document, "V32_DATA_GAP_POLICY_BOUNDARY_INVALID")
        rebuilt = build_v32_data_gap_manual_policy_v1(
            policy_id=document["policy_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DataGapEscalationError):
            raise
        raise V32DataGapEscalationError("V32_DATA_GAP_POLICY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[POLICY_DIGEST_FIELD]:
        raise V32DataGapEscalationError("V32_DATA_GAP_POLICY_REPLAY_MISMATCH")
    return supplied


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _official_sources(value: Any) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32DataGapEscalationError("V32_DATA_GAP_SOURCE_SET_INVALID")
    if not value or len(value) > 16:
        raise V32DataGapEscalationError("V32_DATA_GAP_SOURCE_SET_INVALID")
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "source_id",
            "source_kind",
            "url",
        }:
            raise V32DataGapEscalationError("V32_DATA_GAP_SOURCE_INVALID")
        source_kind = text(item["source_kind"], "V32_DATA_GAP_SOURCE_INVALID")
        url = text(item["url"], "V32_DATA_GAP_SOURCE_INVALID")
        parsed = urlparse(url)
        if (
            source_kind not in OFFICIAL_SOURCE_KINDS
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise V32DataGapEscalationError("V32_DATA_GAP_SOURCE_INVALID")
        rows.append(
            {
                "source_id": text(
                    item["source_id"], "V32_DATA_GAP_SOURCE_INVALID"
                ),
                "source_kind": source_kind,
                "url": url,
            }
        )
    rows.sort(key=lambda row: row["source_id"])
    if len({row["source_id"] for row in rows}) != len(rows):
        raise V32DataGapEscalationError("V32_DATA_GAP_SOURCE_DUPLICATE")
    return rows


def _request(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "request_id",
        "source_id",
        "method",
        "endpoint",
        "field_path",
    }:
        raise V32DataGapEscalationError("V32_DATA_GAP_REQUEST_INVALID")
    method = text(value["method"], "V32_DATA_GAP_REQUEST_INVALID")
    if method != "GET":
        raise V32DataGapEscalationError("V32_DATA_GAP_REQUEST_INVALID")
    return {
        key: text(value[key], "V32_DATA_GAP_REQUEST_INVALID")
        for key in ("request_id", "source_id", "method", "endpoint", "field_path")
    }


def build_v32_data_gap_escalation_v1(
    *,
    gap_id: str,
    run_id: str,
    cycle_index: int,
    request: Mapping[str, Any],
    requested_at: str,
    failed_at: str,
    error_code: str,
    error_message_digest: str,
    impact: str,
    claim_ceiling: str,
    allowed_official_public_sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        requested = time(requested_at, "V32_DATA_GAP_TIME_INVALID")
        failed = time(failed_at, "V32_DATA_GAP_TIME_INVALID")
        if moment(failed, "V32_DATA_GAP_TIME_INVALID") < moment(
            requested, "V32_DATA_GAP_TIME_INVALID"
        ):
            raise V32DataGapEscalationError("V32_DATA_GAP_TIME_INVALID")
        normalized_request = _request(request)
        sources = _official_sources(allowed_official_public_sources)
        document = {
            "schema_id": ESCALATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "gap_id": text(gap_id, "V32_DATA_GAP_ID_INVALID"),
            "run_id": text(run_id, "V32_DATA_GAP_RUN_INVALID"),
            "cycle_index": integer(
                cycle_index,
                "V32_DATA_GAP_CYCLE_INVALID",
                minimum=1,
                maximum=16,
            ),
            "request": normalized_request,
            "requested_at": requested,
            "failed_at": failed,
            "attempt_count": 1,
            "retry_allowed_for_same_attempt": False,
            "error_code": text(error_code, "V32_DATA_GAP_ERROR_INVALID"),
            "error_message_digest": digest(
                error_message_digest, "V32_DATA_GAP_ERROR_INVALID"
            ),
            "objective_status": "UNKNOWN",
            "objective_value": None,
            "zero_imputed": False,
            "impact": text(impact, "V32_DATA_GAP_IMPACT_INVALID"),
            "claim_ceiling": text(
                claim_ceiling, "V32_DATA_GAP_CLAIM_CEILING_INVALID"
            ),
            "allowed_official_public_sources": sources,
            "manual_capture_steps": list(MANUAL_CAPTURE_STEPS),
            "manual_plan_status": "OPEN_MANUAL_PUBLIC_EVIDENCE_PLAN",
            "manual_source_type_required": "MANUAL_PUBLIC_EVIDENCE",
            "semantic_and_physical_digest_required": True,
            "time_verification_required": True,
            "future_cycle_readmission_required": True,
            "historical_cycle_backfill_forbidden": True,
            "original_pit_history_mutation_forbidden": True,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DataGapEscalationError):
            raise
        raise V32DataGapEscalationError("V32_DATA_GAP_INPUT_INVALID") from exc
    return self_digest(document, ESCALATION_DIGEST_FIELD)


def verify_v32_data_gap_escalation_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, ESCALATION_DIGEST_FIELD)
        verify_boundary(document, "V32_DATA_GAP_BOUNDARY_INVALID")
        rebuilt = build_v32_data_gap_escalation_v1(
            gap_id=document["gap_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            request=document["request"],
            requested_at=document["requested_at"],
            failed_at=document["failed_at"],
            error_code=document["error_code"],
            error_message_digest=document["error_message_digest"],
            impact=document["impact"],
            claim_ceiling=document["claim_ceiling"],
            allowed_official_public_sources=document[
                "allowed_official_public_sources"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DataGapEscalationError):
            raise
        raise V32DataGapEscalationError("V32_DATA_GAP_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[ESCALATION_DIGEST_FIELD]:
        raise V32DataGapEscalationError("V32_DATA_GAP_REPLAY_MISMATCH")
    return supplied


def build_v32_manual_public_evidence_revision_v1(
    *,
    revision_id: str,
    escalation: Mapping[str, Any],
    escalation_binding: Mapping[str, Any],
    future_cycle_index: int,
    future_cycle_decision_time: str,
    official_source_id: str,
    raw_evidence_binding: Mapping[str, Any],
    capture_evidence_binding: Mapping[str, Any],
    observed_at: str,
    available_at: str,
    captured_at: str,
    verified_at: str,
) -> dict[str, Any]:
    escalation_digest = verify_v32_data_gap_escalation_v1(escalation)
    try:
        escalation_ref = binding(
            escalation_binding, "V32_MANUAL_EVIDENCE_ESCALATION_BINDING_INVALID"
        )
        if (
            escalation_ref["schema_id"] != ESCALATION_SCHEMA_ID
            or escalation_ref["digest_field"] != ESCALATION_DIGEST_FIELD
            or escalation_ref["semantic_digest"] != escalation_digest
            or escalation_ref["physical_sha256"] != _physical(escalation)
        ):
            raise V32DataGapEscalationError(
                "V32_MANUAL_EVIDENCE_ESCALATION_BINDING_INVALID"
            )
        future_cycle = integer(
            future_cycle_index,
            "V32_MANUAL_EVIDENCE_CYCLE_INVALID",
            minimum=1,
            maximum=16,
        )
        if future_cycle <= escalation["cycle_index"]:
            raise V32DataGapEscalationError(
                "V32_MANUAL_EVIDENCE_HISTORICAL_BACKFILL_FORBIDDEN"
            )
        allowed = {
            row["source_id"] for row in escalation["allowed_official_public_sources"]
        }
        source_id = text(
            official_source_id, "V32_MANUAL_EVIDENCE_SOURCE_INVALID"
        )
        if source_id not in allowed:
            raise V32DataGapEscalationError("V32_MANUAL_EVIDENCE_SOURCE_INVALID")
        raw_ref = binding(
            raw_evidence_binding, "V32_MANUAL_EVIDENCE_RAW_BINDING_INVALID"
        )
        capture_ref = binding(
            capture_evidence_binding,
            "V32_MANUAL_EVIDENCE_CAPTURE_BINDING_INVALID",
        )
        observed = time(observed_at, "V32_MANUAL_EVIDENCE_TIME_INVALID")
        available = time(available_at, "V32_MANUAL_EVIDENCE_TIME_INVALID")
        captured = time(captured_at, "V32_MANUAL_EVIDENCE_TIME_INVALID")
        verified = time(verified_at, "V32_MANUAL_EVIDENCE_TIME_INVALID")
        decision = time(
            future_cycle_decision_time, "V32_MANUAL_EVIDENCE_TIME_INVALID"
        )
        if not (
            moment(observed, "V32_MANUAL_EVIDENCE_TIME_INVALID")
            <= moment(available, "V32_MANUAL_EVIDENCE_TIME_INVALID")
            <= moment(captured, "V32_MANUAL_EVIDENCE_TIME_INVALID")
            <= moment(verified, "V32_MANUAL_EVIDENCE_TIME_INVALID")
            <= moment(decision, "V32_MANUAL_EVIDENCE_TIME_INVALID")
        ):
            raise V32DataGapEscalationError("V32_MANUAL_EVIDENCE_TIME_INVALID")
        document = {
            "schema_id": MANUAL_REVISION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "revision_id": text(
                revision_id, "V32_MANUAL_EVIDENCE_REVISION_ID_INVALID"
            ),
            "run_id": escalation["run_id"],
            "source_cycle_index": escalation["cycle_index"],
            "future_cycle_index": future_cycle,
            "future_cycle_decision_time": decision,
            "escalation_binding": escalation_ref,
            "official_source_id": source_id,
            "source_type": "MANUAL_PUBLIC_EVIDENCE",
            "raw_evidence_binding": raw_ref,
            "capture_evidence_binding": capture_ref,
            "observed_at": observed,
            "available_at": available,
            "captured_at": captured,
            "verified_at": verified,
            "raw_semantic_digest": raw_ref["semantic_digest"],
            "raw_physical_sha256": raw_ref["physical_sha256"],
            "admission_status": "VERIFIED_FOR_FUTURE_CYCLE_ONLY",
            "objective_history_rewritten": False,
            "historical_backfill_performed": False,
            "automatic_collection_claim": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DataGapEscalationError):
            raise
        raise V32DataGapEscalationError(
            "V32_MANUAL_EVIDENCE_INPUT_INVALID"
        ) from exc
    return self_digest(document, MANUAL_REVISION_DIGEST_FIELD)


def verify_v32_manual_public_evidence_revision_v1(
    document: Mapping[str, Any], *, escalation: Mapping[str, Any]
) -> str:
    try:
        supplied = verify_self_digest(document, MANUAL_REVISION_DIGEST_FIELD)
        verify_boundary(document, "V32_MANUAL_EVIDENCE_BOUNDARY_INVALID")
        rebuilt = build_v32_manual_public_evidence_revision_v1(
            revision_id=document["revision_id"],
            escalation=escalation,
            escalation_binding=document["escalation_binding"],
            future_cycle_index=document["future_cycle_index"],
            future_cycle_decision_time=document["future_cycle_decision_time"],
            official_source_id=document["official_source_id"],
            raw_evidence_binding=document["raw_evidence_binding"],
            capture_evidence_binding=document["capture_evidence_binding"],
            observed_at=document["observed_at"],
            available_at=document["available_at"],
            captured_at=document["captured_at"],
            verified_at=document["verified_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32DataGapEscalationError):
            raise
        raise V32DataGapEscalationError("V32_MANUAL_EVIDENCE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[MANUAL_REVISION_DIGEST_FIELD]:
        raise V32DataGapEscalationError("V32_MANUAL_EVIDENCE_REPLAY_MISMATCH")
    return supplied


__all__ = [
    "ESCALATION_DIGEST_FIELD",
    "ESCALATION_SCHEMA_ID",
    "MANUAL_CAPTURE_STEPS",
    "MANUAL_REVISION_DIGEST_FIELD",
    "MANUAL_REVISION_SCHEMA_ID",
    "OFFICIAL_SOURCE_KINDS",
    "POLICY_DIGEST_FIELD",
    "POLICY_SCHEMA_ID",
    "V32DataGapEscalationError",
    "build_v32_data_gap_escalation_v1",
    "build_v32_data_gap_manual_policy_v1",
    "build_v32_manual_public_evidence_revision_v1",
    "verify_v32_data_gap_escalation_v1",
    "verify_v32_data_gap_manual_policy_v1",
    "verify_v32_manual_public_evidence_revision_v1",
]
