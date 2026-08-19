"""Exact clock/tick and public-adapter support contracts for V3.2.

These documents freeze the two operational policies referenced by the V3.2
experiment contract.  They are intentionally closed-shape documents rather
than generic wrappers around caller supplied payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .governance.v32_qualification_identity import (
    FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
    FAILED_V32_TARGET_RUN_ID,
)


SCHEMA_VERSION = "1.0.0"
CLOCK_SCHEMA_ID = "theory_paper_v32_clock_and_tick_policy_v1"
CLOCK_DIGEST_FIELD = "clock_policy_digest"
OUTCOME_ADAPTER_SCHEMA_ID = "theory_paper_v32_public_outcome_adapter_contract_v1"
OUTCOME_ADAPTER_DIGEST_FIELD = "outcome_adapter_contract_digest"
OUTCOME_ADAPTER_ID = "V32_OKX_PUBLIC_MARK_RAW_CAPTURE_OPENAPI_V3"
_LEGACY_OUTCOME_ADAPTER_ID = "V32_OKX_PUBLIC_MARK_RAW_CAPTURE_V1"
_LEGACY_OPENAPI_OUTCOME_ADAPTER_ID = "V32_OKX_PUBLIC_MARK_RAW_CAPTURE_OPENAPI_V2"
_LEGACY_FAILED_OUTCOME_ADAPTER_DIGESTS = {
    FAILED_V32_TARGET_RUN_ID: (
        "02901f1890e9a0d767dee0c2e617e6e043141a3c395d74461ea8dc8281850280"
    ),
    FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID: (
        "263617002199443eaa02a2f3ea744c121a4df0423c8fd086a5c2f8e701db81e1"
    ),
}
_LEGACY_FAILED_OPENAPI_OUTCOME_ADAPTER_DIGESTS = {
    FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID: (
        "5043c16dcc9bd6147aaa35fd60579b5fe80069120f22e8f9358d10ac848657e5"
    ),
}
V32_PUBLIC_HTTPS_ROUTE_POLICY_ID = (
    "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
)
V32_PUBLIC_REQUEST_HEADER_POLICY_ID = (
    "V32_FIXED_PUBLIC_RESEARCH_JSON_REQUEST_HEADERS_V1"
)
V32_PUBLIC_REQUEST_HEADERS = (
    ("accept", "application/json"),
    ("user-agent", "agent-trade-emotion-v3.2-public-research/1.0"),
)
V32_PUBLIC_REQUEST_HEADERS_DIGEST = canonical_digest(
    {
        "schema_id": "theory_paper_v32_public_request_headers_v1",
        "headers": [list(row) for row in V32_PUBLIC_REQUEST_HEADERS],
    }
)
MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS = 5000
ANALYSIS_INTERVAL_SECONDS = 900
MAX_ANALYSIS_SUBSTAGES_PER_WAKE = 64
PRE_PROPOSAL_PHASE_BUDGET_SECONDS = 120
PROPOSAL_PHASE_BUDGET_SECONDS = 180
MIDDLE_PHASE_BUDGET_SECONDS = 90
SELECTION_PHASE_BUDGET_SECONDS = 180
FINALIZE_PHASE_BUDGET_SECONDS = 90
TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS = 660
EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS = 240

if (
    PRE_PROPOSAL_PHASE_BUDGET_SECONDS
    + PROPOSAL_PHASE_BUDGET_SECONDS
    + MIDDLE_PHASE_BUDGET_SECONDS
    + SELECTION_PHASE_BUDGET_SECONDS
    + FINALIZE_PHASE_BUDGET_SECONDS
    != TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS
    or TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS
    + EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS
    != ANALYSIS_INTERVAL_SECONDS
):
    raise RuntimeError("V32_ANALYSIS_PHASE_BUDGET_CONSTANT_DRIFT")


class V32RuntimeSupportContractError(ValueError):
    """A closed V3.2 runtime-support policy drifted."""


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32RuntimeSupportContractError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32RuntimeSupportContractError(code) from exc
    if parsed.tzinfo is None:
        raise V32RuntimeSupportContractError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32RuntimeSupportContractError(code)
    return text


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
        "fill_claim": False,
        "pnl_claim": False,
        "executable": False,
    }


def build_v32_clock_and_tick_policy_v1(
    *, run_scope_id: str, frozen_at: str
) -> dict[str, Any]:
    """Freeze independent 15-minute analysis and delayed outcome clocks."""

    return self_digest(
        {
            "schema_id": CLOCK_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_scope_id": _text(run_scope_id, "V32_CLOCK_SCOPE_INVALID"),
            "frozen_at": _time(frozen_at, "V32_CLOCK_TIME_INVALID"),
            "analysis_clock": {
                "analysis_cycles": 16,
                "minimum_decision_spacing_seconds": ANALYSIS_INTERVAL_SECONDS,
                "cycle_1_mode": "FULL_CONTEXT",
                "cycle_2_to_16_mode": "DELTA_UPDATE",
                "future_outcomes_readable": False,
                "future_outcomes_block_analysis": False,
                "mature_unresolved_outcome_blocks_analysis": True,
                "phase_budgets_seconds": {
                    "pre_proposal": PRE_PROPOSAL_PHASE_BUDGET_SECONDS,
                    "proposal": PROPOSAL_PHASE_BUDGET_SECONDS,
                    "middle": MIDDLE_PHASE_BUDGET_SECONDS,
                    "selection": SELECTION_PHASE_BUDGET_SECONDS,
                    "finalize": FINALIZE_PHASE_BUDGET_SECONDS,
                },
                "total_phase_budget_seconds": (
                    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS
                ),
                "earliest_outcome_grace_reserve_seconds": (
                    EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS
                ),
                "budget_plus_reserve_equals_decision_spacing": True,
            },
            "outcome_clock": {
                "horizon_seconds": [900, 3600, 14400],
                "grace_seconds": 900,
                "tick_alignment_utc_minutes": [0, 15, 30, 45],
                "one_tick_may_resolve_multiple_schedules": True,
                "attempts_per_tick": 1,
                "retry_allowed": False,
                "raw_before_parse": True,
                "outcome_only_tail_required": True,
                "terminal_schedule_count": 48,
            },
            "recovery_policy": {
                "reserved_without_raw": "FAILED_CLOSED_NO_SECOND_REQUEST",
                "raw_present": "DETERMINISTIC_LOCAL_TAIL_ONLY",
                "partial_batch": "DETERMINISTIC_LOCAL_TAIL_ONLY",
                "parse_failure": "KEEP_RAW_AND_FAIL_CLOSED",
                "coverage_loss": "TERMINAL_UNKNOWN_NOT_ZERO",
            },
            "wake_boundary_policy": {
                "maximum_supervisor_permits_or_high_level_lane_boundaries": 1,
                "active_analysis_permit_append_only_substages_allowed": True,
                "maximum_append_only_analysis_substages": (
                    MAX_ANALYSIS_SUBSTAGES_PER_WAKE
                ),
                "append_only_substage_is_high_level_boundary": False,
                "outcome_lane_substage_burst_allowed": False,
            },
            "mid_run_change_forbidden": True,
            **_boundary(),
        },
        CLOCK_DIGEST_FIELD,
    )


def verify_v32_clock_and_tick_policy_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V32RuntimeSupportContractError("V32_CLOCK_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, CLOCK_DIGEST_FIELD)
        rebuilt = build_v32_clock_and_tick_policy_v1(
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RuntimeSupportContractError):
            raise
        raise V32RuntimeSupportContractError(
            "V32_CLOCK_DOCUMENT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[CLOCK_DIGEST_FIELD]:
        raise V32RuntimeSupportContractError("V32_CLOCK_RECONSTRUCTION_MISMATCH")
    return supplied


def build_v32_public_outcome_adapter_contract_v1(
    *, run_scope_id: str, frozen_at: str
) -> dict[str, Any]:
    """Freeze the sole public OKX mark capture boundary."""

    return self_digest(
        {
            "schema_id": OUTCOME_ADAPTER_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_scope_id": _text(run_scope_id, "V32_ADAPTER_SCOPE_INVALID"),
            "frozen_at": _time(frozen_at, "V32_ADAPTER_TIME_INVALID"),
            "adapter_id": OUTCOME_ADAPTER_ID,
            "request": {
                "method": "GET",
                "scheme": "https",
                "host": "openapi.okx.com",
                "path": "/api/v5/public/mark-price",
                "query": {
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                },
                "exact_url": (
                    "https://openapi.okx.com/api/v5/public/mark-price"
                    "?instType=SWAP&instId=BTC-USDT-SWAP"
                ),
                "requests_per_tick": 1,
                "retry_count": 0,
                "redirect_allowed": False,
                "alternate_host_or_venue_fallback": False,
                "timeout_seconds": 15,
                "route_policy_id": V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
                "header_policy_id": V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
                "normalized_headers": {
                    key: value for key, value in V32_PUBLIC_REQUEST_HEADERS
                },
                "normalized_headers_digest": (
                    V32_PUBLIC_REQUEST_HEADERS_DIGEST
                ),
                "caller_header_injection_allowed": False,
                "proxy_identity_rotation_allowed": False,
            },
            "response": {
                "maximum_bytes": 1048576,
                "raw_bytes_must_be_durable_before_parse": True,
                "parser_input_must_equal_durable_bytes": True,
                "accepted_instrument_id": "BTC-USDT-SWAP",
                "accepted_instrument_type": "SWAP",
                "observable_ref": "metric:okx-public-mark-price-usdt",
                "mark_must_be_positive_canonical_decimal": True,
                "provider_clock_ahead_tolerance_milliseconds": (
                    MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS
                ),
                "provider_time_original_preserved": True,
                "within_bound_provider_ahead_quality": "MEDIUM_CLOCK_UNCERTAINTY",
                "beyond_clock_ahead_bound": "FAILED_CLOSED",
                "empty_or_provider_unavailable": "UNKNOWN_COVERAGE_LOSS",
                "schema_or_semantic_conflict": "FAILED_CLOSED",
            },
            "semantic_boundary": {
                "stop_trigger_is_fill": False,
                "price_touch_is_order": False,
                "price_touch_is_position": False,
                "price_touch_is_pnl": False,
            },
            "mid_run_change_forbidden": True,
            **_boundary(),
        },
        OUTCOME_ADAPTER_DIGEST_FIELD,
    )


def verify_v32_public_outcome_adapter_contract_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V32RuntimeSupportContractError("V32_ADAPTER_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, OUTCOME_ADAPTER_DIGEST_FIELD)
        if document.get("adapter_id") in {
            _LEGACY_OUTCOME_ADAPTER_ID,
            _LEGACY_OPENAPI_OUTCOME_ADAPTER_ID,
        }:
            request = document.get("request")
            legacy_openapi = (
                document.get("adapter_id")
                == _LEGACY_OPENAPI_OUTCOME_ADAPTER_ID
            )
            expected_digest = (
                _LEGACY_FAILED_OPENAPI_OUTCOME_ADAPTER_DIGESTS
                if legacy_openapi
                else _LEGACY_FAILED_OUTCOME_ADAPTER_DIGESTS
            ).get(document.get("run_scope_id"))
            if (
                document.get("schema_id") != OUTCOME_ADAPTER_SCHEMA_ID
                or document.get("schema_version") != SCHEMA_VERSION
                or expected_digest is None
                or not isinstance(request, Mapping)
                or request.get("host")
                != ("openapi.okx.com" if legacy_openapi else "www.okx.com")
                or supplied != expected_digest
            ):
                raise V32RuntimeSupportContractError(
                    "V32_ADAPTER_RECONSTRUCTION_MISMATCH"
                )
            return supplied
        rebuilt = build_v32_public_outcome_adapter_contract_v1(
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32RuntimeSupportContractError):
            raise
        raise V32RuntimeSupportContractError(
            "V32_ADAPTER_DOCUMENT_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[OUTCOME_ADAPTER_DIGEST_FIELD]
    ):
        raise V32RuntimeSupportContractError(
            "V32_ADAPTER_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "ANALYSIS_INTERVAL_SECONDS",
    "CLOCK_DIGEST_FIELD",
    "CLOCK_SCHEMA_ID",
    "EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS",
    "FINALIZE_PHASE_BUDGET_SECONDS",
    "MAX_ANALYSIS_SUBSTAGES_PER_WAKE",
    "OUTCOME_ADAPTER_DIGEST_FIELD",
    "OUTCOME_ADAPTER_ID",
    "OUTCOME_ADAPTER_SCHEMA_ID",
    "V32_PUBLIC_HTTPS_ROUTE_POLICY_ID",
    "V32_PUBLIC_REQUEST_HEADER_POLICY_ID",
    "V32_PUBLIC_REQUEST_HEADERS",
    "V32_PUBLIC_REQUEST_HEADERS_DIGEST",
    "MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS",
    "MIDDLE_PHASE_BUDGET_SECONDS",
    "PRE_PROPOSAL_PHASE_BUDGET_SECONDS",
    "PROPOSAL_PHASE_BUDGET_SECONDS",
    "SCHEMA_VERSION",
    "SELECTION_PHASE_BUDGET_SECONDS",
    "TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS",
    "V32RuntimeSupportContractError",
    "build_v32_clock_and_tick_policy_v1",
    "build_v32_public_outcome_adapter_contract_v1",
    "verify_v32_clock_and_tick_policy_v1",
    "verify_v32_public_outcome_adapter_contract_v1",
]
