"""Raw-first, one-attempt V3.2 OKX public bundle collection.

The adapter deliberately has no default network transport.  A caller must
inject one transport whose single ``fetch_once`` call returns an aggregate of
exact UTF-8 bodies from the frozen OKX public endpoint set.  The aggregate is
sealed before any payload parsing or typed derivation occurs.

This module creates qualification evidence only.  It does not create an
authority or research run, access an account, submit an order, or execute a
trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import http.client
import re
from typing import Any, Callable, Mapping, Protocol, Sequence
import urllib.parse

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..application.v32_public_evidence_port import (
    OKX_PUBLIC_BASE_URL,
    RAW_BUNDLE_SCHEMA_ID,
    RAW_BUNDLE_SCHEMA_VERSION,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    V31_NATIVE_SENTIMENT_AXES,
    build_v31_native_sentiment_source_registry,
    verify_v31_native_sentiment_source_registry,
)
from ..domain.v32_runtime_support_contracts import (
    MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS,
    V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADERS_DIGEST,
)
from ..domain.governance.v32_qualification_identity import (
    FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    CAPTURE_SCHEMA_ID,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    QUALIFICATION_DIGEST_FIELD,
    SNAPSHOT_DIGEST_FIELD,
    SOURCE_SCOPE,
    build_v32_formal_source_qualification,
    build_v32_pit_evidence_registry,
    build_v32_public_market_snapshot,
    build_v32_public_source_capture,
    qualification_ref,
    verify_v32_active_authority_projection,
    verify_v32_formal_source_qualification,
    verify_v32_pit_evidence_registry,
    verify_v32_public_market_snapshot,
    verify_v32_public_source_capture,
)
from .v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
    V32CycleSourceAdmissionStoreError,
)
from .v32_public_https_route import V32_PUBLIC_HTTPS_ROUTE_POLICY_ID


class V32PublicSourceCollectorError(ValueError):
    """One public-source attempt failed closed and cannot be retried."""

    def __init__(
        self,
        failure_code: str,
        *,
        failure_context: Mapping[str, Any] | None = None,
        failure_evidence_binding: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.failure_context = (
            None if failure_context is None else dict(failure_context)
        )
        self.failure_evidence_binding = (
            None
            if failure_evidence_binding is None
            else dict(failure_evidence_binding)
        )


class V32PublicComponentRawSinkError(ValueError):
    """A component body could not be sealed before interpretation."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


class V32PublicComponentRawSink(Protocol):
    """Seal one bounded response and its capture metadata before parsing."""

    def seal_component_capture(
        self,
        *,
        component_id: str,
        payload: bytes,
        method: str,
        path: str,
        query: Mapping[str, str],
        http_status: int,
        final_url: str,
        request_started_at: str,
        response_received_at: str,
        capture_completed_at: str,
        route_policy_id: str,
    ) -> Mapping[str, str]: ...

    def seal_component_no_response_failure(
        self,
        *,
        component_id: str,
        method: str,
        path: str,
        query: Mapping[str, str],
        request_started_at: str,
        failure_at: str,
        response_present: bool,
        body_present: bool,
        http_status: None,
        response_final_url: None,
        failure_codes: Sequence[str],
        route_policy_id: str,
        attempt_number: int,
        retry_allowed: bool,
    ) -> Mapping[str, str]: ...


class V32PublicMarketBundleTransport(Protocol):
    """Injected public-only aggregate transport; it is called exactly once."""

    def fetch_once(
        self,
        *,
        instrument_id: str,
        raw_body_sink: V32PublicComponentRawSink,
    ) -> bytes: ...


Clock = Callable[[], str]

ATTEMPT_SCHEMA_ID = "theory_paper_v32_public_source_attempt_reservation_v1"
ATTEMPT_DIGEST_FIELD = "source_attempt_reservation_digest"
AXIS_EVIDENCE_SCHEMA_ID = "theory_paper_v32_axis_source_evidence_v1"
AXIS_EVIDENCE_DIGEST_FIELD = "axis_source_evidence_digest"
AXIS_EVIDENCE_SCHEMA_VERSION = "1.0.0"
AXIS_SOURCE_ASSESSMENT_SCHEMA_ID = (
    "theory_paper_v32_axis_source_assessment_v1"
)
AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD = "axis_source_assessment_digest"
AXIS_SOURCE_ASSESSMENT_SCHEMA_VERSION = "1.0.0"
PIT_DATUM_SCHEMA_ID = "theory_paper_v32_minimal_pit_datum_v1"
PIT_DATUM_DIGEST_FIELD = "pit_datum_digest"
PIT_DATUM_SCHEMA_VERSION = "1.1.0"
ANALYSIS_BUNDLE_SCHEMA_ID = (
    "theory_paper_v32_public_market_analysis_bundle_v1"
)
ANALYSIS_BUNDLE_DIGEST_FIELD = "public_market_analysis_bundle_digest"
ANALYSIS_BUNDLE_SCHEMA_VERSION = "1.1.0"
INFORMATION_EVENT_SCHEMA_ID = "theory_paper_v32_public_source_event_v1"
INFORMATION_EVENT_DIGEST_FIELD = "public_source_event_digest"
INFORMATION_EVENT_SCHEMA_VERSION = "1.0.0"
TRANSPORT_FAILURE_SCHEMA_ID = (
    "theory_paper_v32_public_source_transport_failure_v1"
)
TRANSPORT_FAILURE_DIGEST_FIELD = "public_source_transport_failure_digest"
TRANSPORT_FAILURE_SCHEMA_VERSION = "1.2.0"
VALIDATION_FAILURE_SCHEMA_ID = (
    "theory_paper_v32_public_source_validation_failure_v1"
)
VALIDATION_FAILURE_DIGEST_FIELD = "public_source_validation_failure_digest"
VALIDATION_FAILURE_SCHEMA_VERSION = "1.2.0"
_FAILURE_TIME_ACTIVE_CLOCK = "ACTIVE_CLOCK_OBSERVATION"
_FAILURE_TIME_ATTEMPT_FALLBACK = (
    "ATTEMPT_STARTED_AT_LAST_KNOWN_UNCERTAIN"
)
_FAILURE_TIME_CAPTURE_FALLBACK = (
    "CAPTURE_RESPONSE_RECEIVED_AT_LAST_KNOWN_UNCERTAIN"
)
COMPONENT_CAPTURE_SCHEMA_ID = (
    "theory_paper_v32_public_component_capture_v1"
)
COMPONENT_CAPTURE_DIGEST_FIELD = "public_component_capture_digest"
COMPONENT_CAPTURE_SCHEMA_VERSION = "1.2.0"
COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID = (
    "theory_paper_v32_public_component_no_response_failure_v1"
)
COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD = (
    "public_component_no_response_failure_digest"
)
COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_VERSION = "1.2.0"

# The only www/V1 evidence that remains readable was sealed by the permanently
# failed 2026-08-08 public-source qualification.  Active builders never emit
# these identities, and verifiers accept no other legacy digest.
_LEGACY_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID = (
    f"{FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID}:public-source"
)
_LEGACY_OKX_PUBLIC_BASE_URL = "https://www.okx.com"
_LEGACY_ROUTE_POLICY_ID = (
    "V32_SYSTEM_PUBLIC_HTTPS_NON_CREDENTIAL_NO_REDIRECT_V1"
)
_LEGACY_COMPONENT_CAPTURE_DIGEST = (
    "41e51f51df0c9a1e106bf126a4ee42a57e4fb7f9aa659729b8107140ad9308cd"
)
_LEGACY_TRANSPORT_FAILURE_DIGEST = (
    "9e5ec7cd1902f9d7e51b29556c984144deb0367260ff04ba6ae1475374a7a304"
)
_LEGACY_OPENAPI_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID = (
    f"{FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID}:public-source"
)
_LEGACY_OPENAPI_ROUTE_POLICY_ID = (
    "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_NON_CREDENTIAL_NO_REDIRECT_V2"
)
_LEGACY_OPENAPI_COMPONENT_CAPTURE_DIGEST = (
    "1f9579b30e0083f11f3825d8bf613f63e4013330cfe1c9a7e9fd5d82e71ae6b8"
)
_LEGACY_OPENAPI_TRANSPORT_FAILURE_DIGEST = (
    "20a937621f1c32c0f941cdcb2aec16e652e6bdd14259ba615cb5c7fd0fbc6175"
)

OKX_INSTRUMENT_ID = "BTC-USDT-SWAP"
MAX_RAW_BUNDLE_BYTES = 10 * 1024 * 1024
MAX_PUBLIC_COMPONENT_CAPTURE_BYTES = (2 * 1024 * 1024) + 1
MAX_SOURCE_AGE_SECONDS = 900
MAX_CLOSED_BAR_AGE_SECONDS = 1800
MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS = 120_000
MAX_FUNDING_COMPONENT_STALENESS_MILLISECONDS = 900_000
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_:\-.]{0,159}$")

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
_TIMEFRAME_INTERVAL_MS = {
    "15M": 900_000,
    "1H": 3_600_000,
    "4H": 14_400_000,
    "1D": 86_400_000,
}
_TIMEFRAME_COMPONENT = {
    "15M": "CLOSED_CANDLES_15M",
    "1H": "CLOSED_CANDLES_1H",
    "4H": "CLOSED_CANDLES_4H",
    "1D": "CLOSED_CANDLES_1D",
}
_BOOK_TOP5_IMBALANCE_REPLAY_DEPENDENCY = (
    "VERIFICATION:DURABLE_RAW_REPLAY_REQUIRED_FOR_BOOK_TOP5_IMBALANCE"
)

# Exact semantic roles for every non-bar datum.  The tuple is:
# metric_kind, materialized status, unit, source component, derivation,
# value kind, permits effective_at.  Optional public sources may replace the
# materialized status with UNKNOWN, but may not change the datum identity.
_FIXED_DATUM_CONTRACTS: Mapping[
    str, tuple[str, str, str, str, str, str, bool]
] = {
    "book-best-ask": (
        "BOOK_BEST_ASK",
        "OBSERVED",
        "USDT_PER_BTC",
        "ORDER_BOOK",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "book-best-bid": (
        "BOOK_BEST_BID",
        "OBSERVED",
        "USDT_PER_BTC",
        "ORDER_BOOK",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "book-spread-bps": (
        "BOOK_SPREAD_BPS",
        "DERIVED",
        "BASIS_POINTS",
        "ORDER_BOOK",
        "DERIVED_FROM_SINGLE_BOOK_SNAPSHOT",
        "NONNEGATIVE_DECIMAL",
        False,
    ),
    "book-top5-imbalance": (
        "BOOK_TOP5_IMBALANCE",
        "DERIVED",
        "RATIO_NEG1_TO_1",
        "ORDER_BOOK",
        "DERIVED_FROM_SINGLE_BOOK_SNAPSHOT",
        "RATIO_NEG1_TO_1",
        False,
    ),
    "contract-multiplier": (
        "INSTRUMENT_CTMULT",
        "OBSERVED",
        "OKX_CT_MULT",
        "INSTRUMENT",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "contract-value": (
        "INSTRUMENT_CTVAL",
        "OBSERVED",
        "BTC_PER_CONTRACT",
        "INSTRUMENT",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "funding-rate": (
        "PUBLIC_FUNDING_RATE",
        "OBSERVED",
        "RATE",
        "FUNDING_RATE",
        "DIRECT_PUBLIC_FIELD",
        "FINITE_DECIMAL",
        True,
    ),
    "mark-price": (
        "PUBLIC_MARK_PRICE",
        "OBSERVED",
        "USDT_PER_BTC",
        "MARK_PRICE",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "minimum-quantity": (
        "INSTRUMENT_MINSZ",
        "OBSERVED",
        "CONTRACTS",
        "INSTRUMENT",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "next-funding-settlement-time-ms": (
        "PUBLIC_NEXT_FUNDING_SETTLEMENT_SCHEDULE",
        "OBSERVED",
        "UNIX_MS",
        "FUNDING_RATE",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_INTEGER",
        True,
    ),
    "okx-server-time-ms": (
        "PROVIDER_SERVER_TIME",
        "OBSERVED",
        "UNIX_MS",
        "SERVER_TIME",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_INTEGER",
        False,
    ),
    "open-interest-btc": (
        "PUBLIC_OPEN_INTEREST_LEVEL",
        "OBSERVED",
        "BTC",
        "OPEN_INTEREST",
        "DIRECT_PUBLIC_FIELD",
        "NONNEGATIVE_DECIMAL",
        False,
    ),
    "price-tick": (
        "INSTRUMENT_TICKSZ",
        "OBSERVED",
        "USDT_PER_BTC",
        "INSTRUMENT",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "quantity-step": (
        "INSTRUMENT_LOTSZ",
        "OBSERVED",
        "CONTRACTS",
        "INSTRUMENT",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "recent-trade-count": (
        "RECENT_TRADE_COUNT",
        "DERIVED",
        "COUNT",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE",
        "POSITIVE_INTEGER",
        False,
    ),
    "recent-trade-sample-end-ms": (
        "RECENT_TRADE_SAMPLE_END_TIME",
        "DERIVED",
        "UNIX_MS",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE_METADATA",
        "POSITIVE_INTEGER",
        False,
    ),
    "recent-trade-sample-request-limit": (
        "RECENT_TRADE_SAMPLE_REQUEST_LIMIT",
        "DERIVED",
        "COUNT",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE_METADATA",
        "POSITIVE_INTEGER",
        False,
    ),
    "recent-trade-sample-start-ms": (
        "RECENT_TRADE_SAMPLE_START_TIME",
        "DERIVED",
        "UNIX_MS",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE_METADATA",
        "POSITIVE_INTEGER",
        False,
    ),
    "recent-trade-sample-truncation-status": (
        "RECENT_TRADE_SAMPLE_TRUNCATION_STATUS",
        "DERIVED",
        "ORDINAL_STATUS",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE_METADATA",
        "TRADE_TRUNCATION_STATUS",
        False,
    ),
    "recent-trade-side-imbalance": (
        "RECENT_TRADE_SIDE_IMBALANCE",
        "DERIVED",
        "RATIO_NEG1_TO_1",
        "RECENT_TRADES",
        "DERIVED_FROM_PUBLIC_TRADE_SAMPLE",
        "RATIO_NEG1_TO_1",
        False,
    ),
    "ticker-best-ask": (
        "TICKER_ASKPX",
        "OBSERVED",
        "USDT_PER_BTC",
        "TICKER",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "ticker-best-bid": (
        "TICKER_BIDPX",
        "OBSERVED",
        "USDT_PER_BTC",
        "TICKER",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "ticker-last": (
        "TICKER_LAST",
        "OBSERVED",
        "USDT_PER_BTC",
        "TICKER",
        "DIRECT_PUBLIC_FIELD",
        "POSITIVE_DECIMAL",
        False,
    ),
    "ticker-volume-24h-btc": (
        "TICKER_VOLCCY24H",
        "OBSERVED",
        "BTC",
        "TICKER",
        "DIRECT_PUBLIC_FIELD",
        "NONNEGATIVE_DECIMAL",
        False,
    ),
    "ticker-volume-24h-contracts": (
        "TICKER_VOL24H",
        "OBSERVED",
        "CONTRACTS",
        "TICKER",
        "DIRECT_PUBLIC_FIELD",
        "NONNEGATIVE_DECIMAL",
        False,
    ),
    **{
        f"rsi14-{timeframe.lower()}": (
            "SIMPLE_RSI14_CLOSED_BARS",
            "DERIVED",
            "INDEX_0_100",
            component_id,
            "DERIVED_SIMPLE_RSI14_NOT_PREDICTION",
            "INDEX_0_100",
            False,
        )
        for timeframe, component_id in _TIMEFRAME_COMPONENT.items()
    },
}
_RAW_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "base_url",
        "venue",
        "instrument_id",
        "source_scope",
        "components",
    }
)
_COMPONENT_FIELDS = frozenset(
    {
        "component_id",
        "method",
        "path",
        "query",
        "status",
        "http_status",
        "body_utf8",
        "error_code",
        "request_started_at",
        "response_received_at",
        "attempt_number",
        "retry_allowed",
        "raw_binding",
        "failure_evidence_binding",
    }
)
_RAW_BINDING_FIELDS = frozenset(
    {"relative_ref", "semantic_digest", "physical_sha256"}
)
_EVIDENCE_BINDING_FIELDS = _RAW_BINDING_FIELDS
_DOCUMENT_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_REQUEST_BINDING_FIELDS = frozenset(
    {
        "component_id",
        "request_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "response_received_at",
        "status",
        "attempt_number",
        "retry_allowed",
        "raw_binding",
        "failure_evidence_binding",
        "error_code",
    }
)
_EVENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "event_id",
        "venue",
        "instrument_id",
        "source_type",
        "component_id",
        "request_path",
        "request_query",
        "request_started_at",
        "available_at",
        "status",
        "raw_binding",
        "failure_evidence_binding",
        "reason_code",
        "attempt_number",
        "retry_allowed",
        "dependency_group_ids",
        "claim_ceiling",
        "account_data_accessed",
        "order_data_accessed",
        "external_execution_authority",
        "executable",
        INFORMATION_EVENT_DIGEST_FIELD,
    }
)
_DATUM_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "datum_id",
        "instrument_id",
        "metric_kind",
        "status",
        "value",
        "unit",
        "observed_at",
        "provider_observed_at",
        "effective_at",
        "provider_clock_ahead_milliseconds",
        "clock_uncertainty_status",
        "available_at",
        "source_component_id",
        "source_event_id",
        "raw_binding",
        "dependency_group_ids",
        "reason_code",
        "derivation",
        "point_in_time",
        "missing_is_zero",
        PIT_DATUM_DIGEST_FIELD,
    }
)
_AXIS_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "axis_id",
        "status",
        "admission_status",
        "source_component_ids",
        "source_registry_digest",
        "source_assessments",
        "native_external_direct_admitted",
        "observed_at",
        "available_at",
        "raw_bundle_sha256",
        "claim_ceiling",
        "reason_code",
        "directional_state_computed",
        "missing_is_zero",
        "other_retained",
        AXIS_EVIDENCE_DIGEST_FIELD,
    }
)
_AXIS_SOURCE_ASSESSMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "axis_id",
        "source_kind",
        "evidence_role",
        "source_component_ids",
        "admission_status",
        "native_external",
        "claim_ceiling",
        "reason_code",
        "missing_is_zero",
        AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD,
    }
)
_BAR_FIELDS = frozenset(
    {
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume_contracts",
        "confirmed_closed",
    }
)
_ANALYSIS_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "instrument",
        "as_of",
        "available_at",
        "capture_digest",
        "aggregate_raw_binding",
        "request_raw_bindings",
        "information_events",
        "datums",
        "closed_bar_series",
        "axis_source_evidence",
        "axis_source_registry_digest",
        "pit_member_digests",
        "point_in_time",
        "missing_is_zero",
        "other_unknown_policy",
        "single_source_collection_transaction",
        "each_request_attempt_count",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        ANALYSIS_BUNDLE_DIGEST_FIELD,
    }
)
_TRANSPORT_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "attempt_reservation_digest",
        "component_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "failure_at",
        "request_dispatched",
        "response_present",
        "body_present",
        "http_status",
        "response_final_url",
        "failure_codes",
        "route_policy_id",
        "request_header_policy_id",
        "request_headers_digest",
        "failure_raw_binding",
        "attempt_number",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        "credential_data_accessed",
        TRANSPORT_FAILURE_DIGEST_FIELD,
    }
)
_VALIDATION_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "run_id",
        "cycle_index",
        "attempt_reservation_digest",
        "failure_phase",
        "failure_code",
        "failed_at",
        "failure_time_source",
        "failure_time_uncertain",
        "aggregate_raw_binding",
        "aggregate_capture_binding",
        "component_evidence_bindings",
        "attempt_number",
        "retry_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        "credential_data_accessed",
        VALIDATION_FAILURE_DIGEST_FIELD,
    }
)
_COMPONENT_CAPTURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "component_id",
        "method",
        "base_url",
        "path",
        "query",
        "http_status",
        "final_url",
        "request_started_at",
        "response_received_at",
        "capture_completed_at",
        "body_binding",
        "body_length_bytes",
        "attempt_number",
        "retry_allowed",
        "route_policy_id",
        "request_header_policy_id",
        "request_headers_digest",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        "credential_data_accessed",
        COMPONENT_CAPTURE_DIGEST_FIELD,
    }
)
_COMPONENT_NO_RESPONSE_FAILURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "qualification_id",
        "component_id",
        "method",
        "base_url",
        "path",
        "query",
        "request_started_at",
        "failure_at",
        "request_dispatched",
        "response_present",
        "body_present",
        "http_status",
        "response_final_url",
        "failure_codes",
        "attempt_number",
        "retry_allowed",
        "route_policy_id",
        "request_header_policy_id",
        "request_headers_digest",
        "source_scope",
        "transport_locality",
        "public_data_only",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        "credential_data_accessed",
        COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
    }
)


@dataclass(frozen=True, slots=True)
class V32PublicSourceQualification:
    qualification_id: str
    run_id: str
    cycle_index: int
    raw_binding: Mapping[str, str]
    source_capture: Mapping[str, Any]
    source_capture_binding: Mapping[str, str]
    market_snapshot: Mapping[str, Any]
    market_snapshot_binding: Mapping[str, str]
    pit_registry: Mapping[str, Any]
    pit_registry_binding: Mapping[str, str]
    formal_qualification: Mapping[str, Any]
    formal_qualification_binding: Mapping[str, str]
    public_market_analysis_bundle: Mapping[str, Any]
    public_market_analysis_bundle_binding: Mapping[str, str]
    axis_source_evidence: tuple[Mapping[str, Any], ...]
    open_interest_datum: Mapping[str, Any]
    single_source_collection_transaction: bool = True
    attempt_count: int = 1
    retry_allowed: bool = False
    external_execution_authority: str = "NONE_LOCAL_SIMULATION"
    executable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualification_id": self.qualification_id,
            "run_id": self.run_id,
            "cycle_index": self.cycle_index,
            "raw_binding": dict(self.raw_binding),
            "source_capture": dict(self.source_capture),
            "source_capture_binding": dict(self.source_capture_binding),
            "market_snapshot": dict(self.market_snapshot),
            "market_snapshot_binding": dict(self.market_snapshot_binding),
            "pit_registry": dict(self.pit_registry),
            "pit_registry_binding": dict(self.pit_registry_binding),
            "formal_qualification": dict(self.formal_qualification),
            "formal_qualification_binding": dict(
                self.formal_qualification_binding
            ),
            "public_market_analysis_bundle": dict(
                self.public_market_analysis_bundle
            ),
            "public_market_analysis_bundle_binding": dict(
                self.public_market_analysis_bundle_binding
            ),
            "axis_source_evidence": [
                dict(row) for row in self.axis_source_evidence
            ],
            "open_interest_datum": dict(self.open_interest_datum),
            "single_source_collection_transaction": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }


def _qualification_base(qualification_id: str) -> str:
    return qualification_ref(qualification_id).rsplit("/", 1)[0]


def _attempt_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/attempt-reservation.json"


def _raw_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/raw/public-market-bundle.body"


def _transport_failure_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/transport-failure.json"


def _validation_failure_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/validation-failure.json"


def _transport_failure_raw_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/raw/transport-failure.body"


def _capture_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/capture.json"


def _snapshot_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/snapshot.json"


def _pit_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/pit-registry.json"


def _analysis_bundle_ref(qualification_id: str) -> str:
    return f"{_qualification_base(qualification_id)}/public-market-analysis-bundle.json"


def _component_raw_ref(qualification_id: str, component_id: str) -> str:
    slug = component_id.lower().replace("_", "-")
    return f"{_qualification_base(qualification_id)}/raw/requests/{slug}.body"


def _component_capture_ref(qualification_id: str, component_id: str) -> str:
    slug = component_id.lower().replace("_", "-")
    return f"{_qualification_base(qualification_id)}/component-captures/{slug}.json"


def _component_no_response_failure_ref(
    qualification_id: str, component_id: str
) -> str:
    slug = component_id.lower().replace("_", "-")
    return f"{_qualification_base(qualification_id)}/component-failures/{slug}.json"


class _WriteOnceComponentRawSink:
    """Collector-owned write-once body plus metadata capture capability."""

    def __init__(
        self,
        *,
        qualification_id: str,
        store: LocalV32CycleSourceAdmissionStore,
    ) -> None:
        self._qualification_id = qualification_id
        self._store = store
        self._sealed: dict[str, dict[str, str]] = {}

    def seal_component_capture(
        self,
        *,
        component_id: str,
        payload: bytes,
        method: str,
        path: str,
        query: Mapping[str, str],
        http_status: int,
        final_url: str,
        request_started_at: str,
        response_received_at: str,
        capture_completed_at: str,
        route_policy_id: str,
    ) -> Mapping[str, str]:
        if component_id not in _COMPONENT_ORDER or not isinstance(payload, bytes):
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_INPUT_INVALID"
            )
        if len(payload) > MAX_PUBLIC_COMPONENT_CAPTURE_BYTES:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_BODY_TOO_LARGE"
            )
        if component_id in self._sealed:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_DUPLICATE"
            )
        relative_ref = _component_raw_ref(self._qualification_id, component_id)
        try:
            physical = self._store.write_raw(
                relative_ref=relative_ref, payload=payload
            )["physical_sha256"]
            readback = self._store.read_raw(
                relative_ref=relative_ref, expected_sha256=physical
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_WRITE_FAILED"
            ) from None
        if readback != payload:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_READBACK_FAILED"
            )
        binding = {
            "relative_ref": relative_ref,
            "semantic_digest": physical,
            "physical_sha256": physical,
        }
        try:
            capture = build_v32_public_component_capture_v1(
                qualification_id=self._qualification_id,
                component_id=component_id,
                method=method,
                path=path,
                query=query,
                http_status=http_status,
                final_url=final_url,
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                capture_completed_at=capture_completed_at,
                route_policy_id=route_policy_id,
                body_binding=binding,
                body_length_bytes=len(payload),
            )
            capture_binding = self._store.write_document(
                relative_ref=_component_capture_ref(
                    self._qualification_id, component_id
                ),
                document=capture,
                digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
            )
            readback_capture = self._store.read_document(
                relative_ref=capture_binding["relative_ref"],
                digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
                expected_semantic_digest=capture_binding["semantic_digest"],
                expected_physical_sha256=capture_binding["physical_sha256"],
            )
            verify_v32_public_component_capture_v1(readback_capture)
            durable_body = self._store.read_raw(
                relative_ref=relative_ref,
                expected_sha256=physical,
            )
        except (KeyError, OSError, TypeError, ValueError):
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_CAPTURE_WRITE_FAILED"
            ) from None
        if readback_capture != capture or durable_body != payload:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_CAPTURE_READBACK_FAILED"
            )
        self._sealed[component_id] = {
            **binding,
            "capture_semantic_digest": capture[
                COMPONENT_CAPTURE_DIGEST_FIELD
            ],
        }
        return dict(binding)

    def seal_component_no_response_failure(
        self,
        *,
        component_id: str,
        method: str,
        path: str,
        query: Mapping[str, str],
        request_started_at: str,
        failure_at: str,
        response_present: bool,
        body_present: bool,
        http_status: None,
        response_final_url: None,
        failure_codes: Sequence[str],
        route_policy_id: str,
        attempt_number: int,
        retry_allowed: bool,
    ) -> Mapping[str, str]:
        if component_id in self._sealed:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_FAILURE_SINK_DUPLICATE"
            )
        try:
            receipt = build_v32_public_component_no_response_failure_v1(
                qualification_id=self._qualification_id,
                component_id=component_id,
                method=method,
                path=path,
                query=query,
                request_started_at=request_started_at,
                failure_at=failure_at,
                response_present=response_present,
                body_present=body_present,
                http_status=http_status,
                response_final_url=response_final_url,
                failure_codes=failure_codes,
                route_policy_id=route_policy_id,
                attempt_number=attempt_number,
                retry_allowed=retry_allowed,
            )
            stored = self._store.write_document(
                relative_ref=_component_no_response_failure_ref(
                    self._qualification_id, component_id
                ),
                document=receipt,
                digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
            )
            readback = self._store.read_document(
                relative_ref=stored["relative_ref"],
                digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
                expected_semantic_digest=stored["semantic_digest"],
                expected_physical_sha256=stored["physical_sha256"],
            )
            verify_v32_public_component_no_response_failure_v1(readback)
        except (KeyError, OSError, TypeError, ValueError):
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_FAILURE_SINK_WRITE_FAILED"
            ) from None
        if readback != receipt:
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_FAILURE_SINK_READBACK_FAILED"
            )
        binding = {
            "relative_ref": stored["relative_ref"],
            "semantic_digest": stored["semantic_digest"],
            "physical_sha256": stored["physical_sha256"],
        }
        self._sealed[component_id] = {
            **binding,
            "no_response_failure": "SEALED",
        }
        return dict(binding)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32PublicSourceCollectorError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32PublicSourceCollectorError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32PublicSourceCollectorError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _milliseconds(value: Any, code: str) -> int:
    if not isinstance(value, str) or not value.isdigit():
        raise V32PublicSourceCollectorError(code)
    result = int(value)
    if result <= 0:
        raise V32PublicSourceCollectorError(code)
    return result


def _decimal(
    value: Any,
    code: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> str:
    if not isinstance(value, str):
        raise V32PublicSourceCollectorError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise V32PublicSourceCollectorError(code) from exc
    if (
        not parsed.is_finite()
        or (positive and parsed <= 0)
        or (nonnegative and parsed < 0)
    ):
        raise V32PublicSourceCollectorError(code)
    return canonical_decimal(parsed)


def _okx_rows(body_utf8: str, code: str) -> list[Mapping[str, Any]]:
    try:
        root = loads_json_strict(body_utf8)
    except ValueError as exc:
        raise V32PublicSourceCollectorError(code) from exc
    if (
        set(root) != {"code", "msg", "data"}
        or root.get("code") != "0"
        or root.get("msg") not in {"", None}
        or not isinstance(root.get("data"), list)
        or any(not isinstance(row, Mapping) for row in root["data"])
    ):
        raise V32PublicSourceCollectorError(code)
    return list(root["data"])


def _query(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(item, str)
        or not item
        for key, item in value.items()
    ):
        raise V32PublicSourceCollectorError(code)
    return {key: value[key] for key in sorted(value)}


def _raw_body_binding(
    value: Any,
    code: str,
    *,
    expected_ref: str | None = None,
) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _RAW_BINDING_FIELDS
        or not isinstance(value.get("relative_ref"), str)
        or not value["relative_ref"]
        or (
            expected_ref is not None
            and value.get("relative_ref") != expected_ref
        )
        or not isinstance(value.get("semantic_digest"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["semantic_digest"])
        is None
        or value.get("semantic_digest") != value.get("physical_sha256")
    ):
        raise V32PublicSourceCollectorError(code)
    return {
        "relative_ref": str(value["relative_ref"]),
        "semantic_digest": str(value["semantic_digest"]),
        "physical_sha256": str(value["physical_sha256"]),
    }


def _evidence_binding(
    value: Any,
    code: str,
    *,
    expected_ref: str | None = None,
) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _EVIDENCE_BINDING_FIELDS
        or not isinstance(value.get("relative_ref"), str)
        or not value["relative_ref"]
        or (
            expected_ref is not None
            and value.get("relative_ref") != expected_ref
        )
        or not isinstance(value.get("semantic_digest"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["semantic_digest"])
        is None
        or not isinstance(value.get("physical_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["physical_sha256"])
        is None
    ):
        raise V32PublicSourceCollectorError(code)
    return {
        "relative_ref": str(value["relative_ref"]),
        "semantic_digest": str(value["semantic_digest"]),
        "physical_sha256": str(value["physical_sha256"]),
    }


def _document_binding(
    value: Any,
    code: str,
    *,
    expected_ref: str | None = None,
    expected_schema_id: str | None = None,
    expected_digest_field: str | None = None,
) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _DOCUMENT_BINDING_FIELDS
        or not isinstance(value.get("relative_ref"), str)
        or not value["relative_ref"]
        or (expected_ref is not None and value["relative_ref"] != expected_ref)
        or not isinstance(value.get("schema_id"), str)
        or not value["schema_id"]
        or (
            expected_schema_id is not None
            and value["schema_id"] != expected_schema_id
        )
        or not isinstance(value.get("digest_field"), str)
        or not value["digest_field"]
        or (
            expected_digest_field is not None
            and value["digest_field"] != expected_digest_field
        )
        or not isinstance(value.get("semantic_digest"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["semantic_digest"]) is None
        or not isinstance(value.get("physical_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["physical_sha256"]) is None
    ):
        raise V32PublicSourceCollectorError(code)
    return {key: str(value[key]) for key in _DOCUMENT_BINDING_FIELDS}


def _read_document_binding(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    document = store.read_document(
        relative_ref=relative_ref,
        digest_field=digest_field,
    )
    if document.get("schema_id") != schema_id:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DOCUMENT_BINDING_INVALID"
        )
    binding = store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=str(document[digest_field]),
    )
    if (
        binding.get("schema_id") != schema_id
        or binding.get("digest_field") != digest_field
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DOCUMENT_BINDING_INVALID"
        )
    return document, dict(binding)


def _canonical_component_url(path: str, query: Mapping[str, str]) -> str:
    encoded = urllib.parse.urlencode(sorted(query.items()))
    base = OKX_PUBLIC_BASE_URL + path
    return base if not encoded else f"{base}?{encoded}"


def build_v32_public_component_capture_v1(
    *,
    qualification_id: str,
    component_id: str,
    method: str,
    path: str,
    query: Mapping[str, str],
    http_status: int,
    final_url: str,
    request_started_at: str,
    response_received_at: str,
    capture_completed_at: str,
    route_policy_id: str,
    body_binding: Mapping[str, str],
    body_length_bytes: int,
) -> dict[str, Any]:
    """Build the immutable per-response body and metadata capture bundle."""

    if (
        not isinstance(qualification_id, str)
        or not qualification_id
        or not isinstance(component_id, str)
        or component_id not in _COMPONENT_ORDER
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_INVALID"
        )
    canonical_query = _query(
        query, "V32_PUBLIC_COMPONENT_CAPTURE_QUERY_INVALID"
    )
    binding = _raw_body_binding(
        body_binding,
        "V32_PUBLIC_COMPONENT_CAPTURE_BODY_BINDING_INVALID",
        expected_ref=_component_raw_ref(qualification_id, component_id),
    )
    started = _time(
        request_started_at, "V32_PUBLIC_COMPONENT_CAPTURE_TIME_INVALID"
    )
    received = _time(
        response_received_at, "V32_PUBLIC_COMPONENT_CAPTURE_TIME_INVALID"
    )
    completed = _time(
        capture_completed_at, "V32_PUBLIC_COMPONENT_CAPTURE_TIME_INVALID"
    )
    parsed_final = (
        urllib.parse.urlsplit(final_url)
        if isinstance(final_url, str)
        else None
    )
    if (
        method != "GET"
        or path != _COMPONENT_PATHS.get(component_id)
        or isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
        or not isinstance(final_url, str)
        or not final_url
        or len(final_url) > 4096
        or parsed_final is None
        or parsed_final.scheme != "https"
        or not parsed_final.hostname
        or parsed_final.username is not None
        or parsed_final.password is not None
        or parsed_final.fragment
        or any(ord(character) < 32 for character in final_url)
        or final_url != _canonical_component_url(path, canonical_query)
        or received < started
        or completed < received
        or route_policy_id != V32_PUBLIC_HTTPS_ROUTE_POLICY_ID
        or isinstance(body_length_bytes, bool)
        or not isinstance(body_length_bytes, int)
        or not 0 <= body_length_bytes <= MAX_PUBLIC_COMPONENT_CAPTURE_BYTES
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_INVALID"
        )
    return self_digest(
        {
            "schema_id": COMPONENT_CAPTURE_SCHEMA_ID,
            "schema_version": COMPONENT_CAPTURE_SCHEMA_VERSION,
            "qualification_id": qualification_id,
            "component_id": component_id,
            "method": "GET",
            "base_url": OKX_PUBLIC_BASE_URL,
            "path": path,
            "query": canonical_query,
            "http_status": http_status,
            "final_url": final_url,
            "request_started_at": request_started_at,
            "response_received_at": response_received_at,
            "capture_completed_at": capture_completed_at,
            "body_binding": binding,
            "body_length_bytes": body_length_bytes,
            "attempt_number": 1,
            "retry_allowed": False,
            "route_policy_id": route_policy_id,
            "request_header_policy_id": V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
            "request_headers_digest": V32_PUBLIC_REQUEST_HEADERS_DIGEST,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "credential_data_accessed": False,
        },
        COMPONENT_CAPTURE_DIGEST_FIELD,
    )


def verify_v32_public_component_capture_v1(
    document: Mapping[str, Any],
) -> str:
    if isinstance(document, Mapping):
        try:
            historical = verify_self_digest(
                document, COMPONENT_CAPTURE_DIGEST_FIELD
            )
        except (TypeError, ValueError):
            historical = None
        if historical in {
            _LEGACY_COMPONENT_CAPTURE_DIGEST,
            _LEGACY_OPENAPI_COMPONENT_CAPTURE_DIGEST,
        }:
            if (
                document.get("qualification_id")
                == _LEGACY_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID
                and document.get("schema_version") == "1.0.0"
                and document.get("base_url") == _LEGACY_OKX_PUBLIC_BASE_URL
                and document.get("route_policy_id") == _LEGACY_ROUTE_POLICY_ID
                and historical == _LEGACY_COMPONENT_CAPTURE_DIGEST
            ) or (
                document.get("qualification_id")
                == _LEGACY_OPENAPI_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID
                and document.get("schema_version") == "1.1.0"
                and document.get("base_url") == OKX_PUBLIC_BASE_URL
                and document.get("route_policy_id")
                == _LEGACY_OPENAPI_ROUTE_POLICY_ID
                and historical == _LEGACY_OPENAPI_COMPONENT_CAPTURE_DIGEST
            ):
                return historical
    if not isinstance(document, Mapping) or set(document) != _COMPONENT_CAPTURE_FIELDS:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, COMPONENT_CAPTURE_DIGEST_FIELD
        )
        rebuilt = build_v32_public_component_capture_v1(
            qualification_id=document["qualification_id"],
            component_id=document["component_id"],
            method=document["method"],
            path=document["path"],
            query=document["query"],
            http_status=document["http_status"],
            final_url=document["final_url"],
            request_started_at=document["request_started_at"],
            response_received_at=document["response_received_at"],
            capture_completed_at=document["capture_completed_at"],
            route_policy_id=document["route_policy_id"],
            body_binding=document["body_binding"],
            body_length_bytes=document["body_length_bytes"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicSourceCollectorError):
            raise
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[COMPONENT_CAPTURE_DIGEST_FIELD]:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_INVALID"
        )
    return supplied


def build_v32_public_component_no_response_failure_v1(
    *,
    qualification_id: str,
    component_id: str,
    method: str,
    path: str,
    query: Mapping[str, str],
    request_started_at: str,
    failure_at: str,
    response_present: bool,
    body_present: bool,
    http_status: None,
    response_final_url: None,
    failure_codes: Sequence[str],
    route_policy_id: str,
    attempt_number: int,
    retry_allowed: bool,
) -> dict[str, Any]:
    if (
        not isinstance(qualification_id, str)
        or not qualification_id
        or component_id not in _OPTIONAL_COMPONENTS
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_INVALID"
        )
    canonical_query = _query(
        query, "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_QUERY_INVALID"
    )
    started = _time(
        request_started_at,
        "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
    )
    failed = _time(
        failure_at,
        "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
    )
    codes = list(failure_codes)
    if (
        method != "GET"
        or path != _COMPONENT_PATHS[component_id]
        or failed < started
        or response_present is not False
        or body_present is not False
        or http_status is not None
        or response_final_url is not None
        or len(codes) != 2
        or codes[0] != f"V32_OKX_TRANSPORT_{component_id}_FAILED"
        or codes[1]
        not in {
            "PUBLIC_CONNECTION_FAILURE",
            "PUBLIC_DNS_UNAVAILABLE",
            "PUBLIC_TIMEOUT",
            "PUBLIC_TLS_FAILURE",
            "PUBLIC_TRANSPORT_IO_FAILURE",
        }
        or any(
            not isinstance(code, str) or _REASON_CODE.fullmatch(code) is None
            for code in codes
        )
        or route_policy_id != V32_PUBLIC_HTTPS_ROUTE_POLICY_ID
        or attempt_number != 1
        or isinstance(attempt_number, bool)
        or retry_allowed is not False
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_INVALID"
        )
    return self_digest(
        {
            "schema_id": COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID,
            "schema_version": COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_VERSION,
            "qualification_id": qualification_id,
            "component_id": component_id,
            "method": "GET",
            "base_url": OKX_PUBLIC_BASE_URL,
            "path": path,
            "query": canonical_query,
            "request_started_at": request_started_at,
            "failure_at": failure_at,
            "request_dispatched": True,
            "response_present": False,
            "body_present": False,
            "http_status": None,
            "response_final_url": None,
            "failure_codes": codes,
            "attempt_number": 1,
            "retry_allowed": False,
            "route_policy_id": route_policy_id,
            "request_header_policy_id": V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
            "request_headers_digest": V32_PUBLIC_REQUEST_HEADERS_DIGEST,
            "source_scope": SOURCE_SCOPE,
            "transport_locality": "LOCAL_PUBLIC_HTTPS_TRANSPORT",
            "public_data_only": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "credential_data_accessed": False,
        },
        COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
    )


def verify_v32_public_component_no_response_failure_v1(
    document: Mapping[str, Any],
) -> str:
    if (
        not isinstance(document, Mapping)
        or set(document) != _COMPONENT_NO_RESPONSE_FAILURE_FIELDS
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD
        )
        rebuilt = build_v32_public_component_no_response_failure_v1(
            qualification_id=document["qualification_id"],
            component_id=document["component_id"],
            method=document["method"],
            path=document["path"],
            query=document["query"],
            request_started_at=document["request_started_at"],
            failure_at=document["failure_at"],
            response_present=document["response_present"],
            body_present=document["body_present"],
            http_status=document["http_status"],
            response_final_url=document["response_final_url"],
            failure_codes=document["failure_codes"],
            route_policy_id=document["route_policy_id"],
            attempt_number=document["attempt_number"],
            retry_allowed=document["retry_allowed"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicSourceCollectorError):
            raise
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied
        != rebuilt[COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD]
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_INVALID"
        )
    return supplied


def _read_durable_component_no_response_failure(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    component_id: str,
    binding: Mapping[str, str],
) -> dict[str, Any]:
    expected_ref = _component_no_response_failure_ref(
        qualification_id, component_id
    )
    verified_binding = _evidence_binding(
        binding,
        "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_BINDING_INVALID",
        expected_ref=expected_ref,
    )
    try:
        receipt = store.read_document(
            relative_ref=expected_ref,
            digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
            expected_semantic_digest=verified_binding["semantic_digest"],
            expected_physical_sha256=verified_binding["physical_sha256"],
        )
        verify_v32_public_component_no_response_failure_v1(receipt)
    except V32PublicSourceCollectorError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_REPLAY_FAILED"
        ) from exc
    if (
        receipt.get("qualification_id") != qualification_id
        or receipt.get("component_id") != component_id
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_IDENTITY_MISMATCH"
        )
    return receipt


def verify_durable_v32_public_component_no_response_failure_v1(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    component_id: str,
    binding: Mapping[str, str],
) -> dict[str, Any]:
    """Replay one fixed-path no-response receipt through its owning contract."""

    return _read_durable_component_no_response_failure(
        store=store,
        qualification_id=qualification_id,
        component_id=component_id,
        binding=binding,
    )


def _read_durable_component_capture(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    component_id: str,
) -> tuple[dict[str, Any], dict[str, str], bytes]:
    capture_ref = _component_capture_ref(qualification_id, component_id)
    try:
        capture = store.read_document(
            relative_ref=capture_ref,
            digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
        )
        verify_v32_public_component_capture_v1(capture)
        if (
            capture.get("qualification_id") != qualification_id
            or capture.get("component_id") != component_id
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_COMPONENT_CAPTURE_IDENTITY_MISMATCH"
            )
        body_binding = _raw_body_binding(
            capture["body_binding"],
            "V32_PUBLIC_COMPONENT_CAPTURE_BODY_BINDING_INVALID",
            expected_ref=_component_raw_ref(qualification_id, component_id),
        )
        raw = store.read_raw(
            relative_ref=body_binding["relative_ref"],
            expected_sha256=body_binding["physical_sha256"],
        )
    except V32PublicSourceCollectorError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_REPLAY_FAILED"
        ) from exc
    if (
        hashlib.sha256(raw).hexdigest() != body_binding["semantic_digest"]
        or len(raw) != capture["body_length_bytes"]
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_BODY_REPLAY_MISMATCH"
        )
    return capture, body_binding, raw


def _verify_component_capture_against_aggregate_row(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    component: Mapping[str, Any],
    transaction_started_at: str,
    transaction_received_at: str,
) -> Mapping[str, str] | None:
    component_id = str(component["component_id"])
    capture_ref = _component_capture_ref(qualification_id, component_id)
    has_capture = store.artifact_exists(relative_ref=capture_ref)
    failure_ref = _component_no_response_failure_ref(
        qualification_id, component_id
    )
    has_no_response_failure = store.artifact_exists(
        relative_ref=failure_ref
    )
    aggregate_binding = component.get("raw_binding")
    if aggregate_binding is None:
        if has_capture:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_COMPONENT_CAPTURE_UNEXPECTED"
            )
        if (
            component.get("status") != "UNKNOWN"
            or component.get("http_status") is not None
            or not has_no_response_failure
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_MISSING"
            )
        receipt = _read_durable_component_no_response_failure(
            store=store,
            qualification_id=qualification_id,
            component_id=component_id,
            binding=component["failure_evidence_binding"],
        )
        if (
            receipt["method"] != component["method"]
            or receipt["path"] != component["path"]
            or receipt["query"] != component["query"]
            or receipt["request_started_at"]
            != component["request_started_at"]
            or receipt["failure_at"]
            != component["response_received_at"]
            or receipt["failure_codes"][-1] != component["error_code"]
            or _time(
                receipt["request_started_at"],
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
            )
            < _time(
                transaction_started_at,
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
            )
            or _time(
                receipt["failure_at"],
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
            )
            > _time(
                transaction_received_at,
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_TIME_INVALID",
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_AGGREGATE_MISMATCH"
            )
        return None
    if has_no_response_failure:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_NO_RESPONSE_FAILURE_UNEXPECTED"
        )
    if not has_capture:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_MISSING"
        )
    capture, body_binding, raw = _read_durable_component_capture(
        store=store,
        qualification_id=qualification_id,
        component_id=component_id,
    )
    supplied_binding = _raw_body_binding(
        aggregate_binding,
        "V32_PUBLIC_SOURCE_COMPONENT_RAW_BINDING_INVALID",
        expected_ref=_component_raw_ref(qualification_id, component_id),
    )
    transaction_started = _time(
        transaction_started_at,
        "V32_PUBLIC_COMPONENT_CAPTURE_TRANSACTION_TIME_INVALID",
    )
    transaction_received = _time(
        transaction_received_at,
        "V32_PUBLIC_COMPONENT_CAPTURE_TRANSACTION_TIME_INVALID",
    )
    if (
        body_binding != supplied_binding
        or capture["method"] != component["method"]
        or capture["path"] != component["path"]
        or capture["query"] != component["query"]
        or capture["http_status"] != component["http_status"]
        or capture["final_url"]
        != _canonical_component_url(
            str(component["path"]), component["query"]
        )
        or capture["request_started_at"]
        != component["request_started_at"]
        or capture["response_received_at"]
        != component["response_received_at"]
        or _time(
            capture["request_started_at"],
            "V32_PUBLIC_COMPONENT_CAPTURE_TRANSACTION_TIME_INVALID",
        )
        < transaction_started
        or _time(
            capture["capture_completed_at"],
            "V32_PUBLIC_COMPONENT_CAPTURE_TRANSACTION_TIME_INVALID",
        )
        > transaction_received
        or (
            component["status"] == "OBSERVED"
            and raw != str(component["body_utf8"]).encode("utf-8")
        )
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_COMPONENT_CAPTURE_AGGREGATE_MISMATCH"
        )
    return body_binding


def build_v32_public_source_transport_failure_v1(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    attempt_reservation_digest: str,
    component_id: str,
    method: str,
    path: str,
    query: Mapping[str, str],
    request_started_at: str,
    failure_at: str,
    request_dispatched: bool,
    response_present: bool,
    body_present: bool,
    http_status: int | None,
    response_final_url: str | None,
    failure_codes: Sequence[str],
    route_policy_id: str,
    failure_raw_binding: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Build the sanitized, write-once receipt for one failed public attempt."""

    started = _time(
        request_started_at, "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID"
    )
    failed = _time(failure_at, "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID")
    codes = list(failure_codes)
    parsed_final = (
        urllib.parse.urlsplit(response_final_url)
        if isinstance(response_final_url, str)
        else None
    )
    binding = None if failure_raw_binding is None else dict(failure_raw_binding)
    if binding is not None:
        expected_failure_raw_ref = (
            _transport_failure_raw_ref(qualification_id)
            if component_id == "AGGREGATE_PUBLIC_BUNDLE"
            else _component_raw_ref(qualification_id, component_id)
        )
        binding = _raw_body_binding(
            binding,
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_INVALID",
            expected_ref=expected_failure_raw_ref,
        )
    if (
        not isinstance(qualification_id, str)
        or not qualification_id
        or not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
        or not isinstance(attempt_reservation_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", attempt_reservation_digest) is None
        or component_id not in {*_COMPONENT_ORDER, "AGGREGATE_PUBLIC_BUNDLE"}
        or method != "GET"
        or not isinstance(path, str)
        or not path.startswith("/api/v5/")
        or not isinstance(request_dispatched, bool)
        or not isinstance(response_present, bool)
        or not isinstance(body_present, bool)
        or failed < started
        or not isinstance(route_policy_id, str)
        or _REASON_CODE.fullmatch(route_policy_id) is None
        or (
            route_policy_id != V32_PUBLIC_HTTPS_ROUTE_POLICY_ID
            and not (
                component_id == "AGGREGATE_PUBLIC_BUNDLE"
                and response_present is False
                and route_policy_id
                == "INJECTED_PUBLIC_TRANSPORT_NO_ROUTE_CLAIM"
            )
        )
        or not 2 <= len(codes) <= 8
        or codes[0] != "V32_PUBLIC_SOURCE_TRANSPORT_FAILED"
        or any(
            not isinstance(code, str) or _REASON_CODE.fullmatch(code) is None
            for code in codes
        )
        or len(set(codes)) != len(codes)
        or (not request_dispatched and response_present)
        or (body_present and not response_present)
        or body_present != (binding is not None)
        or (
            response_present
            and (
                isinstance(http_status, bool)
                or not isinstance(http_status, int)
                or not 100 <= http_status <= 599
            )
        )
        or (not response_present and http_status is not None)
        or (
            response_present
            and (
                not isinstance(response_final_url, str)
                or not response_final_url
                or len(response_final_url) > 4096
                or parsed_final is None
                or parsed_final.scheme != "https"
                or not parsed_final.hostname
                or parsed_final.username is not None
                or parsed_final.password is not None
                or parsed_final.fragment
                or any(ord(character) < 32 for character in response_final_url)
                or (
                    "PUBLIC_REDIRECT_FORBIDDEN" not in codes
                    and response_final_url
                    != _canonical_component_url(path, query)
                )
                or (
                    "PUBLIC_REDIRECT_FORBIDDEN" in codes
                    and not (300 <= http_status < 400)
                    and response_final_url
                    == _canonical_component_url(path, query)
                )
            )
        )
        or (not response_present and response_final_url is not None)
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_INVALID"
        )
    return self_digest(
        {
            "schema_id": TRANSPORT_FAILURE_SCHEMA_ID,
            "schema_version": TRANSPORT_FAILURE_SCHEMA_VERSION,
            "qualification_id": qualification_id,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "attempt_reservation_digest": attempt_reservation_digest,
            "component_id": component_id,
            "method": "GET",
            "base_url": OKX_PUBLIC_BASE_URL,
            "path": path,
            "query": _query(query, "V32_PUBLIC_SOURCE_FAILURE_QUERY_INVALID"),
            "request_started_at": request_started_at,
            "failure_at": failure_at,
            "request_dispatched": request_dispatched,
            "response_present": response_present,
            "body_present": body_present,
            "http_status": http_status,
            "response_final_url": response_final_url,
            "failure_codes": codes,
            "route_policy_id": route_policy_id,
            "request_header_policy_id": V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
            "request_headers_digest": V32_PUBLIC_REQUEST_HEADERS_DIGEST,
            "failure_raw_binding": binding,
            "attempt_number": 1,
            "retry_allowed": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "credential_data_accessed": False,
        },
        TRANSPORT_FAILURE_DIGEST_FIELD,
    )


def verify_v32_public_source_transport_failure_v1(
    document: Mapping[str, Any],
) -> str:
    if isinstance(document, Mapping):
        try:
            historical = verify_self_digest(
                document, TRANSPORT_FAILURE_DIGEST_FIELD
            )
        except (TypeError, ValueError):
            historical = None
        if historical in {
            _LEGACY_TRANSPORT_FAILURE_DIGEST,
            _LEGACY_OPENAPI_TRANSPORT_FAILURE_DIGEST,
        }:
            if (
                document.get("qualification_id")
                == _LEGACY_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID
                and document.get("run_id")
                == FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID
                and document.get("schema_version") == "1.0.0"
                and document.get("base_url") == _LEGACY_OKX_PUBLIC_BASE_URL
                and document.get("route_policy_id") == _LEGACY_ROUTE_POLICY_ID
                and historical == _LEGACY_TRANSPORT_FAILURE_DIGEST
            ) or (
                document.get("qualification_id")
                == _LEGACY_OPENAPI_FAILED_PUBLIC_SOURCE_QUALIFICATION_ID
                and document.get("run_id")
                == FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID
                and document.get("schema_version") == "1.1.0"
                and document.get("base_url") == OKX_PUBLIC_BASE_URL
                and document.get("route_policy_id")
                == _LEGACY_OPENAPI_ROUTE_POLICY_ID
                and historical == _LEGACY_OPENAPI_TRANSPORT_FAILURE_DIGEST
            ):
                return historical
    if not isinstance(document, Mapping) or set(document) != _TRANSPORT_FAILURE_FIELDS:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_INVALID"
        )
    try:
        supplied = verify_self_digest(document, TRANSPORT_FAILURE_DIGEST_FIELD)
        rebuilt = build_v32_public_source_transport_failure_v1(
            qualification_id=document["qualification_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            attempt_reservation_digest=document["attempt_reservation_digest"],
            component_id=document["component_id"],
            method=document["method"],
            path=document["path"],
            query=document["query"],
            request_started_at=document["request_started_at"],
            failure_at=document["failure_at"],
            request_dispatched=document["request_dispatched"],
            response_present=document["response_present"],
            body_present=document["body_present"],
            http_status=document["http_status"],
            response_final_url=document["response_final_url"],
            failure_codes=document["failure_codes"],
            route_policy_id=document["route_policy_id"],
            failure_raw_binding=document["failure_raw_binding"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicSourceCollectorError):
            raise
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[TRANSPORT_FAILURE_DIGEST_FIELD]:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_INVALID"
        )
    return supplied


def verify_durable_v32_public_source_transport_failure_v1(
    document: Mapping[str, Any],
    *,
    store: LocalV32CycleSourceAdmissionStore,
) -> str:
    """Verify the receipt and replay its exact raw body binding, if present."""

    supplied = verify_v32_public_source_transport_failure_v1(document)

    def verify_receipt_owner_and_attempt() -> None:
        qualification_id = str(document["qualification_id"])
        try:
            sealed_receipt = store.read_document(
                relative_ref=_transport_failure_ref(qualification_id),
                digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
                expected_semantic_digest=supplied,
            )
            attempt = loads_json_strict(
                store.read_raw(
                    relative_ref=_attempt_ref(qualification_id)
                )
            )
            attempt_digest = verify_self_digest(
                attempt, ATTEMPT_DIGEST_FIELD
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_DURABLE_OWNER_INVALID"
            ) from exc
        if sealed_receipt != dict(document):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_DURABLE_OWNER_INVALID"
            )
        if (
            attempt.get("schema_id") != ATTEMPT_SCHEMA_ID
            or attempt.get("schema_version") != "1.0.0"
            or attempt.get("qualification_id") != qualification_id
            or attempt.get("run_id") != document["run_id"]
            or attempt.get("cycle_index") != document["cycle_index"]
            or attempt_digest != document["attempt_reservation_digest"]
            or attempt.get(ATTEMPT_DIGEST_FIELD)
            != document["attempt_reservation_digest"]
            or attempt.get("attempt_number") != 1
            or attempt.get("retry_allowed") is not False
            or attempt.get("single_source_collection_transaction") is not True
            or attempt.get("source_scope") != SOURCE_SCOPE
            or attempt.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or attempt.get("executable") is not False
            or attempt.get("account_data_accessed") is not False
            or attempt.get("order_data_accessed") is not False
            or _time(
                attempt.get("started_at"),
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_ATTEMPT_INVALID",
            )
            > _time(
                document["request_started_at"],
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_ATTEMPT_INVALID",
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_ATTEMPT_INVALID"
            )

    binding = document["failure_raw_binding"]
    if binding is None:
        if document["component_id"] in _COMPONENT_ORDER and store.artifact_exists(
            relative_ref=_component_capture_ref(
                str(document["qualification_id"]),
                str(document["component_id"]),
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_CAPTURE_UNEXPECTED"
            )
        verify_receipt_owner_and_attempt()
        return supplied
    expected_ref = (
        _transport_failure_raw_ref(str(document["qualification_id"]))
        if document["component_id"] == "AGGREGATE_PUBLIC_BUNDLE"
        else _component_raw_ref(
            str(document["qualification_id"]), str(document["component_id"])
        )
    )
    verified = _raw_body_binding(
        binding,
        "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_BINDING_INVALID",
        expected_ref=expected_ref,
    )
    try:
        raw = store.read_raw(
            relative_ref=verified["relative_ref"],
            expected_sha256=verified["physical_sha256"],
        )
    except (OSError, TypeError, ValueError):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_REPLAY_FAILED"
        ) from None
    if hashlib.sha256(raw).hexdigest() != verified["semantic_digest"]:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_REPLAY_FAILED"
        )
    if document["component_id"] in _COMPONENT_ORDER:
        capture, capture_body_binding, capture_raw = (
            _read_durable_component_capture(
                store=store,
                qualification_id=str(document["qualification_id"]),
                component_id=str(document["component_id"]),
            )
        )
        if (
            capture_body_binding != verified
            or capture_raw != raw
            or capture["method"] != document["method"]
            or capture["path"] != document["path"]
            or capture["query"] != document["query"]
            or capture["http_status"] != document["http_status"]
            or capture["final_url"] != document["response_final_url"]
            or capture["request_started_at"]
            != document["request_started_at"]
            or capture["route_policy_id"] != document["route_policy_id"]
            or capture.get("request_header_policy_id")
            != document.get("request_header_policy_id")
            or capture.get("request_headers_digest")
            != document.get("request_headers_digest")
            or _time(
                capture["capture_completed_at"],
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_CAPTURE_TIME_INVALID",
            )
            > _time(
                document["failure_at"],
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_CAPTURE_TIME_INVALID",
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_CAPTURE_MISMATCH"
            )
    verify_receipt_owner_and_attempt()
    return supplied


def build_v32_public_source_validation_failure_v1(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    attempt_reservation_digest: str,
    failure_phase: str,
    failure_code: str,
    failed_at: str,
    failure_time_source: str,
    failure_time_uncertain: bool,
    aggregate_raw_binding: Mapping[str, str] | None,
    aggregate_capture_binding: Mapping[str, str] | None,
    component_evidence_bindings: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Bind one post-capture local semantic failure to all sealed evidence."""

    raw_binding = (
        None
        if aggregate_raw_binding is None
        else _raw_body_binding(
            aggregate_raw_binding,
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID",
            expected_ref=_raw_ref(qualification_id),
        )
    )
    if failure_phase not in {
        "PRE_AGGREGATE_RAW_VALIDATION",
        "PRE_CAPTURE_AGGREGATE_VALIDATION",
        "POST_CAPTURE_ANALYSIS_VALIDATION",
        "POST_CAPTURE_FORMALIZATION",
    }:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        )
    capture_binding = (
        None
        if aggregate_capture_binding is None
        else _document_binding(
            aggregate_capture_binding,
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID",
            expected_ref=_capture_ref(qualification_id),
            expected_schema_id=CAPTURE_SCHEMA_ID,
            expected_digest_field=CAPTURE_DIGEST_FIELD,
        )
    )
    pre_raw = failure_phase == "PRE_AGGREGATE_RAW_VALIDATION"
    pre_capture = failure_phase == "PRE_CAPTURE_AGGREGATE_VALIDATION"
    post_capture = failure_phase in {
        "POST_CAPTURE_ANALYSIS_VALIDATION",
        "POST_CAPTURE_FORMALIZATION",
    }
    if (
        not isinstance(component_evidence_bindings, Mapping)
        or (
            pre_raw
            and (
                raw_binding is not None
                or capture_binding is not None
                or component_evidence_bindings
            )
        )
        or (
            pre_capture
            and (
                raw_binding is None
                or capture_binding is not None
                or component_evidence_bindings
            )
        )
        or (
            post_capture
            and (
                raw_binding is None
                or capture_binding is None
                or set(component_evidence_bindings)
                != set(_COMPONENT_ORDER)
            )
        )
        or (
            failure_time_source == _FAILURE_TIME_ACTIVE_CLOCK
            and failure_time_uncertain is not False
        )
        or (
            failure_time_source == _FAILURE_TIME_ATTEMPT_FALLBACK
            and (
                failure_time_uncertain is not True
                or capture_binding is not None
            )
        )
        or (
            failure_time_source == _FAILURE_TIME_CAPTURE_FALLBACK
            and (
                failure_time_uncertain is not True
                or capture_binding is None
                or not post_capture
            )
        )
        or failure_time_source
        not in {
            _FAILURE_TIME_ACTIVE_CLOCK,
            _FAILURE_TIME_ATTEMPT_FALLBACK,
            _FAILURE_TIME_CAPTURE_FALLBACK,
        }
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        )
    component_bindings: dict[str, dict[str, str]] = {}
    for component_id in (
        _COMPONENT_ORDER if capture_binding is not None else ()
    ):
        candidate = component_evidence_bindings[component_id]
        schema_id = candidate.get("schema_id") if isinstance(candidate, Mapping) else None
        if schema_id == COMPONENT_CAPTURE_SCHEMA_ID:
            component_bindings[component_id] = _document_binding(
                candidate,
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID",
                expected_ref=_component_capture_ref(
                    qualification_id, component_id
                ),
                expected_schema_id=COMPONENT_CAPTURE_SCHEMA_ID,
                expected_digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
            )
        elif schema_id == COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID:
            component_bindings[component_id] = _document_binding(
                candidate,
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID",
                expected_ref=_component_no_response_failure_ref(
                    qualification_id, component_id
                ),
                expected_schema_id=COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID,
                expected_digest_field=(
                    COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD
                ),
            )
        else:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
            )
    if (
        not isinstance(qualification_id, str)
        or not qualification_id
        or not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
        or not isinstance(attempt_reservation_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", attempt_reservation_digest) is None
        or not isinstance(failure_code, str)
        or _REASON_CODE.fullmatch(failure_code) is None
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        )
    _time(failed_at, "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID")
    return self_digest(
        {
            "schema_id": VALIDATION_FAILURE_SCHEMA_ID,
            "schema_version": VALIDATION_FAILURE_SCHEMA_VERSION,
            "qualification_id": qualification_id,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "attempt_reservation_digest": attempt_reservation_digest,
            "failure_phase": failure_phase,
            "failure_code": failure_code,
            "failed_at": failed_at,
            "failure_time_source": failure_time_source,
            "failure_time_uncertain": failure_time_uncertain,
            "aggregate_raw_binding": raw_binding,
            "aggregate_capture_binding": capture_binding,
            "component_evidence_bindings": component_bindings,
            "attempt_number": 1,
            "retry_allowed": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "credential_data_accessed": False,
        },
        VALIDATION_FAILURE_DIGEST_FIELD,
    )


def verify_v32_public_source_validation_failure_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _VALIDATION_FAILURE_FIELDS:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        )
    try:
        supplied = verify_self_digest(document, VALIDATION_FAILURE_DIGEST_FIELD)
        rebuilt = build_v32_public_source_validation_failure_v1(
            qualification_id=document["qualification_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            attempt_reservation_digest=document["attempt_reservation_digest"],
            failure_phase=document["failure_phase"],
            failure_code=document["failure_code"],
            failed_at=document["failed_at"],
            failure_time_source=document["failure_time_source"],
            failure_time_uncertain=document["failure_time_uncertain"],
            aggregate_raw_binding=document["aggregate_raw_binding"],
            aggregate_capture_binding=document["aggregate_capture_binding"],
            component_evidence_bindings=document["component_evidence_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicSourceCollectorError):
            raise
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[VALIDATION_FAILURE_DIGEST_FIELD]
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_INVALID"
        )
    return supplied


def verify_durable_v32_public_source_validation_failure_v1(
    document: Mapping[str, Any],
    *,
    store: LocalV32CycleSourceAdmissionStore,
) -> str:
    """Verify the sealed historical failure fact and every physical input."""

    supplied = verify_v32_public_source_validation_failure_v1(document)
    qualification_id = str(document["qualification_id"])
    try:
        sealed_receipt = store.read_document(
            relative_ref=_validation_failure_ref(qualification_id),
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
            expected_semantic_digest=supplied,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
        ) from exc
    if sealed_receipt != dict(document):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
        )
    attempt = loads_json_strict(
        store.read_raw(relative_ref=_attempt_ref(qualification_id))
    )
    verify_self_digest(attempt, ATTEMPT_DIGEST_FIELD)
    if (
        attempt.get(ATTEMPT_DIGEST_FIELD)
        != document["attempt_reservation_digest"]
        or attempt.get("run_id") != document["run_id"]
        or attempt.get("cycle_index") != document["cycle_index"]
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_allowed") is not False
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
        )

    def verify_failure_time(
        *, fallback_at: Any, fallback_source: str
    ) -> None:
        failed = _time(
            document["failed_at"],
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID",
        )
        fallback = _time(
            fallback_at,
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID",
        )
        time_source = document["failure_time_source"]
        uncertain = document["failure_time_uncertain"]
        if time_source == _FAILURE_TIME_ACTIVE_CLOCK:
            valid = uncertain is False and failed >= fallback
        else:
            valid = (
                time_source == fallback_source
                and uncertain is True
                and failed == fallback
            )
        if not valid:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
            )

    if document["failure_phase"] == "PRE_AGGREGATE_RAW_VALIDATION":
        verify_failure_time(
            fallback_at=attempt.get("started_at"),
            fallback_source=_FAILURE_TIME_ATTEMPT_FALLBACK,
        )
        if (
            document["aggregate_raw_binding"] is not None
            or document["aggregate_capture_binding"] is not None
            or document["component_evidence_bindings"]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
            )
        return supplied
    raw_binding = _raw_body_binding(
        document["aggregate_raw_binding"],
        "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID",
        expected_ref=_raw_ref(qualification_id),
    )
    raw = store.read_raw(
        relative_ref=raw_binding["relative_ref"],
        expected_sha256=raw_binding["physical_sha256"],
    )
    if document["failure_phase"] == "PRE_CAPTURE_AGGREGATE_VALIDATION":
        verify_failure_time(
            fallback_at=attempt.get("started_at"),
            fallback_source=_FAILURE_TIME_ATTEMPT_FALLBACK,
        )
        if (
            document["aggregate_capture_binding"] is not None
            or document["component_evidence_bindings"]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
            )
        return supplied
    capture, capture_binding = _read_document_binding(
        store=store,
        relative_ref=_capture_ref(qualification_id),
        schema_id=CAPTURE_SCHEMA_ID,
        digest_field=CAPTURE_DIGEST_FIELD,
    )
    if (
        capture_binding != document["aggregate_capture_binding"]
        or capture.get("qualification_id") != qualification_id
        or capture.get("run_id") != document["run_id"]
        or capture.get("cycle_index") != document["cycle_index"]
        or capture.get("raw_response_binding") != raw_binding
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
        )
    verify_failure_time(
        fallback_at=capture.get("response_received_at"),
        fallback_source=_FAILURE_TIME_CAPTURE_FALLBACK,
    )
    for component_id in _COMPONENT_ORDER:
        expected_binding = document["component_evidence_bindings"][
            component_id
        ]
        schema_id = expected_binding.get("schema_id")
        if schema_id == COMPONENT_CAPTURE_SCHEMA_ID:
            component_document, component_binding = _read_document_binding(
                store=store,
                relative_ref=_component_capture_ref(
                    qualification_id, component_id
                ),
                schema_id=COMPONENT_CAPTURE_SCHEMA_ID,
                digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
            )
            body_binding = _raw_body_binding(
                component_document.get("body_binding"),
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID",
                expected_ref=_component_raw_ref(
                    qualification_id, component_id
                ),
            )
            body = store.read_raw(
                relative_ref=body_binding["relative_ref"],
                expected_sha256=body_binding["physical_sha256"],
            )
            if (
                component_document.get("qualification_id")
                != qualification_id
                or component_document.get("component_id") != component_id
                or component_document.get("attempt_number") != 1
                or component_document.get("retry_allowed") is not False
                or component_document.get("body_length_bytes") != len(body)
                or hashlib.sha256(body).hexdigest()
                != body_binding["semantic_digest"]
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
                )
        elif schema_id == COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID:
            component_document, component_binding = _read_document_binding(
                store=store,
                relative_ref=_component_no_response_failure_ref(
                    qualification_id, component_id
                ),
                schema_id=COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID,
                digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
            )
            if (
                component_document.get("qualification_id")
                != qualification_id
                or component_document.get("component_id") != component_id
                or component_document.get("attempt_number") != 1
                or component_document.get("retry_allowed") is not False
                or component_document.get("response_present") is not False
                or component_document.get("body_present") is not False
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
                )
        else:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
            )
        if component_binding != expected_binding:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID"
            )
    return supplied


def assess_current_v32_public_source_validation_failure_reproduction_v1(
    document: Mapping[str, Any],
    *,
    store: LocalV32CycleSourceAdmissionStore,
) -> str:
    """Compare a sealed failure with current code without rewriting history.

    A later fix can legitimately make a historical implementation failure no
    longer reproduce.  That result is diagnostic only: the physical receipt,
    attempt, aggregate response, and component evidence remain the authority
    for whether the earlier failure was actually sealed.
    """

    verify_durable_v32_public_source_validation_failure_v1(
        document, store=store
    )
    if document["failure_phase"] != "POST_CAPTURE_ANALYSIS_VALIDATION":
        return "CURRENT_REPLAY_SCOPE_NOT_MATERIALIZED"
    try:
        qualification_id = str(document["qualification_id"])
        raw_binding = _raw_body_binding(
            document["aggregate_raw_binding"],
            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_REPLAY_INVALID",
            expected_ref=_raw_ref(qualification_id),
        )
        raw = store.read_raw(
            relative_ref=raw_binding["relative_ref"],
            expected_sha256=raw_binding["physical_sha256"],
        )
        capture, _ = _read_document_binding(
            store=store,
            relative_ref=_capture_ref(qualification_id),
            schema_id=CAPTURE_SCHEMA_ID,
            digest_field=CAPTURE_DIGEST_FIELD,
        )
        components, _ = _component_rows(raw)
        component_raw_bindings: dict[
            str, Mapping[str, str] | None
        ] = {}
        for component_id in _COMPONENT_ORDER:
            component_raw_bindings[component_id] = (
                _verify_component_capture_against_aggregate_row(
                    store=store,
                    qualification_id=qualification_id,
                    component=components[component_id],
                    transaction_started_at=capture["request_started_at"],
                    transaction_received_at=capture["response_received_at"],
                )
            )
        derived = _derive_bundle(
            raw=raw,
            available_at=str(capture["response_received_at"]),
            aggregate_raw_binding=raw_binding,
            component_raw_bindings=component_raw_bindings,
        )
        analysis_bundle = build_v32_public_market_analysis_bundle(
            qualification_id=qualification_id,
            run_id=str(document["run_id"]),
            cycle_index=int(document["cycle_index"]),
            capture_digest=str(capture[CAPTURE_DIGEST_FIELD]),
            aggregate_raw_binding=raw_binding,
            component_raw_bindings=component_raw_bindings,
            derived=derived,
        )
        verify_v32_public_market_analysis_bundle(analysis_bundle)
    except (KeyError, TypeError, ValueError) as caught:
        exc = (
            caught
            if isinstance(caught, V32PublicSourceCollectorError)
            else V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_ANALYSIS_BUILD_OR_VERIFY_FAILED"
            )
        )
        if exc.failure_code == document["failure_code"]:
            return "REPRODUCED_EXACT_FAILURE"
        return "DIFFERENT_FAILURE_UNDER_CURRENT_CODE"
    except Exception:
        return "CURRENT_CODE_REPLAY_UNAVAILABLE"
    return "NO_LONGER_REPRODUCES_AFTER_CODE_CHANGE"


def recover_durable_v32_public_source_failure_v1(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    active_authority: Mapping[str, Any],
    expected_run_id: str | None = None,
    expected_cycle_index: int | None = None,
) -> dict[str, Any]:
    """Recover the sole sealed aggregate source failure without I/O retry."""

    authority_projection_digest = verify_v32_active_authority_projection(
        active_authority
    )
    governing_authority_digest = str(
        active_authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
    )
    experiment_contract_digest = str(
        active_authority["experiment_contract_digest"]
    )
    attempt = loads_json_strict(
        store.read_raw(relative_ref=_attempt_ref(qualification_id))
    )
    verify_self_digest(attempt, ATTEMPT_DIGEST_FIELD)
    if (
        attempt.get("qualification_id") != qualification_id
        or attempt.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != authority_projection_digest
        or attempt.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != governing_authority_digest
        or attempt.get("experiment_contract_digest")
        != experiment_contract_digest
        or attempt.get("run_id")
        != active_authority.get("authorized_run_id")
        or (
            expected_run_id is not None
            and attempt.get("run_id") != expected_run_id
        )
        or (
            expected_cycle_index is not None
            and attempt.get("cycle_index") != expected_cycle_index
        )
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DURABLE_FAILURE_AUTHORITY_INVALID"
        )

    candidates = (
        (
            _validation_failure_ref(qualification_id),
            VALIDATION_FAILURE_SCHEMA_ID,
            VALIDATION_FAILURE_DIGEST_FIELD,
            verify_durable_v32_public_source_validation_failure_v1,
        ),
        (
            _transport_failure_ref(qualification_id),
            TRANSPORT_FAILURE_SCHEMA_ID,
            TRANSPORT_FAILURE_DIGEST_FIELD,
            verify_durable_v32_public_source_transport_failure_v1,
        ),
    )
    present = [
        candidate
        for candidate in candidates
        if store.artifact_exists(relative_ref=candidate[0])
    ]
    if len(present) != 1:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DURABLE_FAILURE_SET_INVALID"
        )
    relative_ref, schema_id, digest_field, verifier = present[0]
    document, binding = _read_document_binding(
        store=store,
        relative_ref=relative_ref,
        schema_id=schema_id,
        digest_field=digest_field,
    )
    if schema_id == VALIDATION_FAILURE_SCHEMA_ID:
        reproduction_status = (
            assess_current_v32_public_source_validation_failure_reproduction_v1(
                document, store=store
            )
        )
    else:
        verifier(document, store=store)
        reproduction_status = "NOT_APPLICABLE_TRANSPORT_FAILURE"
    if (
        document.get("qualification_id") != qualification_id
        or (
            expected_run_id is not None
            and document.get("run_id") != expected_run_id
        )
        or (
            expected_cycle_index is not None
            and document.get("cycle_index") != expected_cycle_index
        )
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DURABLE_FAILURE_IDENTITY_INVALID"
        )
    return {
        "failure": document,
        "failure_evidence_binding": binding,
        "current_reproduction_status": reproduction_status,
    }


def _component_rows(raw: bytes) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        document = loads_json_strict(raw)
    except ValueError as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_RAW_BUNDLE_INVALID"
        ) from exc
    if (
        isinstance(document, Mapping)
        and document.get("schema_id") == RAW_BUNDLE_SCHEMA_ID
        and document.get("schema_version") != RAW_BUNDLE_SCHEMA_VERSION
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_RAW_BUNDLE_SCHEMA_VERSION_UNSUPPORTED"
        )
    if (
        not isinstance(document, Mapping)
        or set(document) != _RAW_FIELDS
        or document.get("schema_id") != RAW_BUNDLE_SCHEMA_ID
        or document.get("schema_version") != RAW_BUNDLE_SCHEMA_VERSION
        or document.get("base_url") != OKX_PUBLIC_BASE_URL
        or document.get("venue") != "OKX"
        or document.get("instrument_id") != OKX_INSTRUMENT_ID
        or document.get("source_scope") != SOURCE_SCOPE
        or not isinstance(document.get("components"), list)
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_RAW_BUNDLE_IDENTITY_INVALID"
        )
    rows: dict[str, dict[str, Any]] = {}
    supplied_order: list[str] = []
    for candidate in document["components"]:
        if not isinstance(candidate, Mapping) or set(candidate) != _COMPONENT_FIELDS:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_COMPONENT_INVALID"
            )
        component_id = candidate.get("component_id")
        if component_id not in _COMPONENT_ORDER or component_id in rows:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_COMPONENT_SET_INVALID"
            )
        supplied_order.append(str(component_id))
        query = _query(
            candidate.get("query"), "V32_PUBLIC_SOURCE_COMPONENT_QUERY_INVALID"
        )
        status = candidate.get("status")
        observed = status == "OBSERVED"
        unknown_optional = component_id in _OPTIONAL_COMPONENTS and status == "UNKNOWN"
        raw_binding_value = candidate.get("raw_binding")
        raw_binding = (
            None
            if raw_binding_value is None
            else _raw_body_binding(
                raw_binding_value,
                "V32_PUBLIC_SOURCE_COMPONENT_RAW_BINDING_INVALID",
            )
        )
        failure_evidence_value = candidate.get("failure_evidence_binding")
        failure_evidence_binding = (
            None
            if failure_evidence_value is None
            else _evidence_binding(
                failure_evidence_value,
                "V32_PUBLIC_SOURCE_COMPONENT_FAILURE_EVIDENCE_INVALID",
            )
        )
        http_status = candidate.get("http_status")
        request_started_at = candidate.get("request_started_at")
        response_received_at = candidate.get("response_received_at")
        request_started = _time(
            request_started_at, "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID"
        )
        response_received = _time(
            response_received_at, "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID"
        )
        if (
            candidate.get("method") != "GET"
            or candidate.get("path") != _COMPONENT_PATHS[component_id]
            or not (observed or unknown_optional)
            or response_received < request_started
            or candidate.get("attempt_number") != 1
            or candidate.get("retry_allowed") is not False
            or (
                observed
                and (
                    http_status != 200
                    or not isinstance(candidate.get("body_utf8"), str)
                    or not candidate["body_utf8"]
                    or candidate.get("error_code") is not None
                    or raw_binding is None
                    or failure_evidence_binding is not None
                )
            )
            or (
                unknown_optional
                and (
                    candidate.get("body_utf8") is not None
                    or not isinstance(candidate.get("error_code"), str)
                    or _REASON_CODE.fullmatch(candidate["error_code"]) is None
                    or failure_evidence_binding is None
                    or (
                        http_status is None
                        and raw_binding is not None
                    )
                    or (
                        http_status is not None
                        and (
                            http_status not in _TRANSIENT_HTTP_STATUS_CODES
                            or raw_binding is None
                            or failure_evidence_binding != raw_binding
                        )
                    )
                )
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_COMPONENT_STATUS_INVALID"
            )
        rows[str(component_id)] = {
            **dict(candidate),
            "query": query,
            "raw_binding": raw_binding,
            "failure_evidence_binding": failure_evidence_binding,
        }
    if supplied_order != list(_COMPONENT_ORDER):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_COMPONENT_SET_INVALID"
        )
    return rows, hashlib.sha256(raw).hexdigest()


def _require_queries(
    components: Mapping[str, Mapping[str, Any]], *, server_time_ms: int
) -> None:
    buckets = {
        timeframe: (server_time_ms // interval) * interval
        for timeframe, interval in _TIMEFRAME_INTERVAL_MS.items()
    }
    expected = {
        "SERVER_TIME": {},
        "INSTRUMENT": {"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
        "TICKER": {"instId": OKX_INSTRUMENT_ID},
        "MARK_PRICE": {"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
        "CLOSED_CANDLES_15M": {
            "after": str(buckets["15M"]),
            "bar": "15m",
            "instId": OKX_INSTRUMENT_ID,
            "limit": "96",
        },
        "CLOSED_CANDLES_1H": {
            "after": str(buckets["1H"]),
            "bar": "1H",
            "instId": OKX_INSTRUMENT_ID,
            "limit": "168",
        },
        "CLOSED_CANDLES_4H": {
            "after": str(buckets["4H"]),
            "bar": "4H",
            "instId": OKX_INSTRUMENT_ID,
            "limit": "90",
        },
        "CLOSED_CANDLES_1D": {
            "after": str(buckets["1D"]),
            "bar": "1Dutc",
            "instId": OKX_INSTRUMENT_ID,
            "limit": "60",
        },
        "OPEN_INTEREST": {
            "instId": OKX_INSTRUMENT_ID,
            "instType": "SWAP",
        },
        "FUNDING_RATE": {"instId": OKX_INSTRUMENT_ID},
        "ORDER_BOOK": {"instId": OKX_INSTRUMENT_ID, "sz": "50"},
        "RECENT_TRADES": {"instId": OKX_INSTRUMENT_ID, "limit": "100"},
    }
    if any(dict(components[key]["query"]) != value for key, value in expected.items()):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_COMPONENT_QUERY_INVALID"
        )


_AXIS_SOURCE_PLANS: dict[str, tuple[dict[str, Any], ...]] = {
    "PRICE_DIRECTIONAL_PRESSURE": (
        {
            "source_kind": "PUBLIC_MARK_OR_INDEX_PRICE",
            "evidence_role": "DIRECT",
            "source_component_ids": ("MARK_PRICE", "TICKER"),
            "mode": "ADMIT_IF_OBSERVED",
        },
        {
            "source_kind": "PUBLIC_CLOSED_CANDLE_SERIES",
            "evidence_role": "DIRECT",
            "source_component_ids": ("CLOSED_CANDLES_15M",),
            "mode": "ADMIT_IF_OBSERVED",
        },
    ),
    "STRUCTURE_PERSISTENCE": (
        {
            "source_kind": "PUBLIC_CLOSED_CANDLE_SERIES",
            "evidence_role": "PROXY",
            "source_component_ids": tuple(_TIMEFRAME_COMPONENT.values()),
            "mode": "ADMIT_IF_OBSERVED",
        },
    ),
    "PARTICIPATION_AND_ACTIVE_FLOW": (
        {
            "source_kind": "PUBLIC_CLOSED_CANDLE_VOLUME",
            "evidence_role": "DIRECT",
            "source_component_ids": ("CLOSED_CANDLES_15M",),
            "mode": "ADMIT_IF_OBSERVED",
        },
        {
            "source_kind": "PUBLIC_AGGRESSOR_TRADE_SAMPLE",
            "evidence_role": "DIRECT",
            "source_component_ids": ("RECENT_TRADES",),
            "mode": "ADMIT_IF_OBSERVED",
        },
    ),
    "CROWDING_DIRECTION": (
        {
            "source_kind": "PUBLIC_FUNDING_RATE",
            "evidence_role": "DIRECT",
            "source_component_ids": ("FUNDING_RATE",),
            "mode": "ADMIT_IF_OBSERVED",
        },
    ),
    "LEVERAGE_CHANGE": (
        {
            "source_kind": "PUBLIC_OPEN_INTEREST",
            "evidence_role": "DIRECT",
            "source_component_ids": ("OPEN_INTEREST",),
            # A point-in-time OI level is a legal native observation, but it
            # is not the cross-capture change required by the axis label.
            "mode": "ADMIT_SOURCE_AXIS_UNKNOWN",
        },
    ),
    "FORCED_DELEVERAGING_PRESSURE": (),
    "LIQUIDITY_RESILIENCE": (
        {
            "source_kind": "PUBLIC_ORDER_BOOK_SNAPSHOT",
            # The frozen V3.1 matrix explicitly forbids one snapshot as a
            # direct/proxy/derived resilience source.
            "evidence_role": "UNKNOWN",
            "source_component_ids": ("ORDER_BOOK",),
            "mode": "REJECT_IF_OBSERVED",
        },
    ),
    "VOLATILITY_AND_TAIL_STRESS": (
        {
            "source_kind": "PUBLIC_CLOSED_CANDLE_SERIES",
            "evidence_role": "DIRECT",
            "source_component_ids": tuple(_TIMEFRAME_COMPONENT.values()),
            "mode": "ADMIT_IF_OBSERVED",
        },
    ),
    "EVENT_AND_NARRATIVE_REACTION": (),
    "ATTENTION_AND_AUDIENCE_RESPONSE": (),
    "CROSS_MARKET_RISK_APPETITE_AND_REGIME": (),
    "TIMEFRAME_COHERENCE": (
        {
            "source_kind": "CLOSED_MULTI_TIMEFRAME_COHERENCE",
            "evidence_role": "DERIVED",
            "source_component_ids": tuple(_TIMEFRAME_COMPONENT.values()),
            # Inputs exist, but this collector has not materialized the
            # registered four-return coherence transform.
            "mode": "DERIVATION_NOT_MATERIALIZED",
        },
    ),
}

_AXIS_NO_SOURCE_REASONS = {
    "FORCED_DELEVERAGING_PRESSURE": "NO_ADMITTED_LIQUIDATION_SOURCE",
    "EVENT_AND_NARRATIVE_REACTION": "NO_ADMITTED_EVENT_SOURCE",
    "ATTENTION_AND_AUDIENCE_RESPONSE": "NO_ADMITTED_ATTENTION_SOURCE",
    "CROSS_MARKET_RISK_APPETITE_AND_REGIME": (
        "NO_ADMITTED_CROSS_MARKET_SOURCE"
    ),
}


def _native_axis_registry_material() -> tuple[
    str, dict[str, Mapping[str, Any]], Mapping[str, Mapping[str, Any]]
]:
    registry = build_v31_native_sentiment_source_registry()
    try:
        registry_digest = verify_v31_native_sentiment_source_registry(registry)
    except ValueError as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_REGISTRY_INVALID"
        ) from exc
    axes = {row["axis_id"]: row for row in registry["axes"]}
    if set(axes) != set(V31_NATIVE_SENTIMENT_AXES):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_REGISTRY_INVALID"
        )
    return registry_digest, axes, registry["source_kind_rules"]


def _axis_source_assessment(
    *,
    axis_id: str,
    source_kind: str,
    evidence_role: str,
    source_component_ids: Sequence[str],
    mode: str,
    component_statuses: Mapping[str, str],
    axis_policy: Mapping[str, Any],
    source_rules: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if source_kind not in source_rules:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_SOURCE_KIND_INVALID"
        )
    role_field = {
        "DIRECT": "direct_source_kinds",
        "PROXY": "proxy_source_kinds",
        "DERIVED": "derived_source_kinds",
    }.get(evidence_role)
    if role_field is None:
        if evidence_role != "UNKNOWN" or any(
            source_kind in axis_policy[field]
            for field in (
                "direct_source_kinds",
                "proxy_source_kinds",
                "derived_source_kinds",
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_AXIS_ROLE_INVALID"
            )
    elif source_kind not in axis_policy[role_field]:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_ROLE_INVALID"
        )
    components = sorted(set(source_component_ids))
    if not components or any(row not in component_statuses for row in components):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_COMPONENT_INVALID"
        )
    unavailable = [
        row for row in components if component_statuses[row] != "OBSERVED"
    ]
    if unavailable:
        admission_status = "UNKNOWN"
        reason_code = f"SOURCE_COMPONENT_UNKNOWN:{unavailable[0]}"
    elif mode in {"ADMIT_IF_OBSERVED", "ADMIT_SOURCE_AXIS_UNKNOWN"}:
        admission_status = "ADMITTED"
        reason_code = None
    elif mode == "REJECT_IF_OBSERVED":
        admission_status = "REJECTED"
        reason_code = "SOURCE_KIND_FORBIDDEN_FOR_AXIS_ROLE"
    elif mode == "DERIVATION_NOT_MATERIALIZED":
        admission_status = "UNKNOWN"
        reason_code = "DERIVED_MEASURE_NOT_MATERIALIZED"
    else:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AXIS_MODE_INVALID"
        )
    rule = source_rules[source_kind]
    return self_digest(
        {
            "schema_id": AXIS_SOURCE_ASSESSMENT_SCHEMA_ID,
            "schema_version": AXIS_SOURCE_ASSESSMENT_SCHEMA_VERSION,
            "axis_id": axis_id,
            "source_kind": source_kind,
            "evidence_role": evidence_role,
            "source_component_ids": components,
            "admission_status": admission_status,
            "native_external": rule["native_external"],
            "claim_ceiling": rule["claim_ceiling"],
            "reason_code": reason_code,
            "missing_is_zero": False,
        },
        AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD,
    )


def _axis_row(
    *,
    axis_id: str,
    status: str,
    admission_status: str,
    source_component_ids: Sequence[str],
    source_registry_digest: str,
    source_assessments: Sequence[Mapping[str, Any]],
    native_external_direct_admitted: bool,
    observed_at: str | None,
    available_at: str,
    raw_sha256: str,
    claim_ceiling: str,
    reason_code: str | None,
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": AXIS_EVIDENCE_SCHEMA_ID,
            "schema_version": AXIS_EVIDENCE_SCHEMA_VERSION,
            "axis_id": axis_id,
            "status": status,
            "admission_status": admission_status,
            "source_component_ids": sorted(set(source_component_ids)),
            "source_registry_digest": source_registry_digest,
            "source_assessments": [dict(row) for row in source_assessments],
            "native_external_direct_admitted": (
                native_external_direct_admitted
            ),
            "observed_at": observed_at,
            "available_at": available_at,
            "raw_bundle_sha256": raw_sha256,
            "claim_ceiling": claim_ceiling,
            "reason_code": reason_code,
            "directional_state_computed": False,
            "missing_is_zero": False,
            "other_retained": axis_id == "OTHER",
        },
        AXIS_EVIDENCE_DIGEST_FIELD,
    )


def _build_axis_rows(
    *,
    component_statuses: Mapping[str, str],
    component_observed_at: Mapping[str, str],
    available_at: str,
    raw_sha256: str,
) -> tuple[list[dict[str, Any]], str]:
    registry_digest, axis_policies, source_rules = _native_axis_registry_material()
    rows: list[dict[str, Any]] = []
    for axis_id in V31_NATIVE_SENTIMENT_AXES:
        assessments = [
            _axis_source_assessment(
                axis_id=axis_id,
                component_statuses=component_statuses,
                axis_policy=axis_policies[axis_id],
                source_rules=source_rules,
                **spec,
            )
            for spec in _AXIS_SOURCE_PLANS[axis_id]
        ]
        modes = [spec["mode"] for spec in _AXIS_SOURCE_PLANS[axis_id]]
        source_components = sorted(
            {
                component_id
                for assessment in assessments
                for component_id in assessment["source_component_ids"]
            }
        )
        all_admitted = bool(assessments) and all(
            row["admission_status"] == "ADMITTED" for row in assessments
        )
        axis_admitted = all_admitted and not any(
            mode
            in {
                "ADMIT_SOURCE_AXIS_UNKNOWN",
                "REJECT_IF_OBSERVED",
                "DERIVATION_NOT_MATERIALIZED",
            }
            for mode in modes
        )
        if axis_admitted:
            status = "OBSERVED"
            admission_status = "ADMITTED"
            if any(
                component_id not in component_observed_at
                for component_id in source_components
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_AXIS_COMPONENT_TIME_MISSING"
                )
            axis_observed_at = _time_text(
                max(
                    _time(
                        component_observed_at[component_id],
                        "V32_PUBLIC_SOURCE_AXIS_COMPONENT_TIME_INVALID",
                    )
                    for component_id in source_components
                )
            )
            claim_ceiling = "ADMITTED_SOURCE_COVERAGE_NOT_DIRECTIONAL_STATE"
            reason_code = None
        else:
            status = "UNKNOWN"
            admission_status = "UNKNOWN"
            axis_observed_at = None
            unavailable = next(
                (
                    row["reason_code"]
                    for row in assessments
                    if isinstance(row["reason_code"], str)
                    and row["reason_code"].startswith(
                        "SOURCE_COMPONENT_UNKNOWN:"
                    )
                ),
                None,
            )
            if unavailable is not None:
                claim_ceiling = "UNKNOWN_REQUIRED_SOURCE_UNAVAILABLE"
                reason_code = unavailable
            elif axis_id == "LEVERAGE_CHANGE":
                claim_ceiling = "OPEN_INTEREST_LEVEL_ONLY"
                reason_code = "OPEN_INTEREST_LEVEL_NO_CROSS_CAPTURE_CHANGE"
            elif axis_id == "LIQUIDITY_RESILIENCE":
                claim_ceiling = "SINGLE_BOOK_STATE_NOT_RESILIENCE"
                reason_code = "SINGLE_ORDER_BOOK_SNAPSHOT_FORBIDDEN"
            elif axis_id == "TIMEFRAME_COHERENCE":
                claim_ceiling = "DERIVED_CLOSED_MULTI_TIMEFRAME_RELATION_ONLY"
                reason_code = "COHERENCE_DERIVATION_NOT_MATERIALIZED"
            elif not assessments:
                claim_ceiling = "UNKNOWN_NO_ADMITTED_AXIS_SOURCE"
                reason_code = _AXIS_NO_SOURCE_REASONS[axis_id]
            else:
                claim_ceiling = "UNKNOWN_REQUIRED_SOURCE_UNAVAILABLE"
                reason_code = "NO_ADMITTED_AXIS_SOURCE"
        native_direct = axis_admitted and any(
            row["admission_status"] == "ADMITTED"
            and row["evidence_role"] == "DIRECT"
            and row["native_external"] is True
            for row in assessments
        )
        rows.append(
            _axis_row(
                axis_id=axis_id,
                status=status,
                admission_status=admission_status,
                source_component_ids=source_components,
                source_registry_digest=registry_digest,
                source_assessments=assessments,
                native_external_direct_admitted=native_direct,
                observed_at=axis_observed_at,
                available_at=available_at,
                raw_sha256=raw_sha256,
                claim_ceiling=claim_ceiling,
                reason_code=reason_code,
            )
        )
    rows.append(
        _axis_row(
            axis_id="OTHER",
            status="OTHER",
            admission_status="NOT_APPLICABLE",
            source_component_ids=[],
            source_registry_digest=registry_digest,
            source_assessments=[],
            native_external_direct_admitted=False,
            observed_at=None,
            available_at=available_at,
            raw_sha256=raw_sha256,
            claim_ceiling="UNCLASSIFIED_PUBLIC_INFORMATION_RETAINED",
            reason_code="OTHER_RESIDUAL_RETAINED_NOT_ZERO",
        )
    )
    return rows, registry_digest


_BAR_DATUM_ID = re.compile(
    r"^bar-(15m|1h|4h|1d)-([1-9][0-9]*)-"
    r"(open|high|low|close|volume|range-pct|return-pct)$"
)


def _datum_contract(
    datum_id: Any,
) -> tuple[str, str, str, str, str, str, bool]:
    if not isinstance(datum_id, str):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
        )
    fixed = _FIXED_DATUM_CONTRACTS.get(datum_id)
    if fixed is not None:
        return fixed
    matched = _BAR_DATUM_ID.fullmatch(datum_id)
    if matched is None:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
        )
    timeframe, _, suffix = matched.groups()
    component_id = _TIMEFRAME_COMPONENT[timeframe.upper()]
    if suffix in {"open", "high", "low", "close"}:
        return (
            f"CLOSED_BAR_{suffix.upper()}",
            "OBSERVED",
            "USDT_PER_BTC",
            component_id,
            "DIRECT_PUBLIC_FIELD",
            "POSITIVE_DECIMAL",
            False,
        )
    if suffix == "volume":
        return (
            "CLOSED_BAR_VOLUME",
            "OBSERVED",
            "CONTRACTS",
            component_id,
            "DIRECT_PUBLIC_FIELD",
            "NONNEGATIVE_DECIMAL",
            False,
        )
    if suffix == "range-pct":
        return (
            "CLOSED_BAR_RANGE_PCT",
            "DERIVED",
            "PERCENT",
            component_id,
            "DERIVED_FROM_SAME_CLOSED_BAR",
            "NONNEGATIVE_DECIMAL",
            False,
        )
    return (
        "CLOSED_BAR_RETURN_PCT",
        "DERIVED",
        "PERCENT",
        component_id,
        "DERIVED_FROM_TWO_CLOSED_BARS",
        "FINITE_DECIMAL",
        False,
    )


def _validate_datum_semantic_contract(
    *,
    datum_id: Any,
    metric_kind: Any,
    status: Any,
    value: Any,
    unit: Any,
    source_component_id: Any,
    source_event_id: Any,
    derivation: Any,
    effective_at: Any,
    dependency_group_ids: Any,
) -> None:
    (
        expected_metric,
        materialized_status,
        expected_unit,
        expected_component,
        expected_derivation,
        value_kind,
        permits_effective_at,
    ) = _datum_contract(datum_id)
    invalid = (
        metric_kind != expected_metric
        or source_component_id != expected_component
        or source_event_id
        != f"okx-public-request:{expected_component.lower()}"
        or not isinstance(dependency_group_ids, Sequence)
        or isinstance(dependency_group_ids, (str, bytes))
        or "VENUE:OKX" not in dependency_group_ids
        or f"REQUEST:{expected_component}" not in dependency_group_ids
    )
    if status == "UNKNOWN":
        invalid = invalid or (
            expected_component not in _OPTIONAL_COMPONENTS
            or value is not None
            or unit is not None
            or derivation != "NOT_DERIVED_SOURCE_UNKNOWN"
            or effective_at is not None
            or f"UNIT_HINT:{expected_unit}" not in dependency_group_ids
        )
    else:
        invalid = invalid or (
            status != materialized_status
            or unit != expected_unit
            or derivation != expected_derivation
            or isinstance(effective_at, str) != permits_effective_at
            or not isinstance(value, str)
            or not value
        )
    if invalid:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
        )
    if status == "UNKNOWN":
        return
    try:
        if value_kind == "POSITIVE_INTEGER":
            normalized = str(
                _milliseconds(
                    value, "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
                )
            )
        elif value_kind == "TRADE_TRUNCATION_STATUS":
            if value not in {
                "POSSIBLY_TRUNCATED_AT_REQUEST_LIMIT",
                "NOT_REQUEST_LIMIT_SATURATED",
            }:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
                )
            normalized = value
        else:
            normalized = _decimal(
                value,
                "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID",
                positive=value_kind == "POSITIVE_DECIMAL",
                nonnegative=value_kind == "NONNEGATIVE_DECIMAL",
            )
            parsed = Decimal(normalized)
            if (
                value_kind == "RATIO_NEG1_TO_1"
                and not Decimal("-1") <= parsed <= Decimal("1")
            ) or (
                value_kind == "INDEX_0_100"
                and not Decimal("0") <= parsed <= Decimal("100")
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
                )
        if normalized != value:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
            )
    except (InvalidOperation, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicSourceCollectorError):
            raise
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
        ) from exc
    if (
        datum_id == "book-top5-imbalance"
        and _BOOK_TOP5_IMBALANCE_REPLAY_DEPENDENCY
        not in dependency_group_ids
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_CONTRACT_INVALID"
        )


def _datum(
    *,
    datum_id: str,
    metric_kind: str,
    status: str,
    value: str | None,
    unit: str | None,
    observed_at: str | None,
    available_at: str,
    source_component_id: str,
    source_event_id: str,
    raw_binding: Mapping[str, str] | None,
    dependency_group_ids: Sequence[str],
    reason_code: str | None,
    derivation: str,
    provider_observed_at: str | None,
    provider_clock_reference_at: str | None,
    effective_at: str | None = None,
) -> dict[str, Any]:
    _validate_datum_semantic_contract(
        datum_id=datum_id,
        metric_kind=metric_kind,
        status=status,
        value=value,
        unit=unit,
        source_component_id=source_component_id,
        source_event_id=source_event_id,
        derivation=derivation,
        effective_at=effective_at,
        dependency_group_ids=dependency_group_ids,
    )
    available = _time(available_at, "V32_PUBLIC_SOURCE_DATUM_INVALID")
    observed = (
        None
        if observed_at is None
        else _time(observed_at, "V32_PUBLIC_SOURCE_DATUM_INVALID")
    )
    provider = (
        None
        if provider_observed_at is None
        else _time(
            provider_observed_at, "V32_PUBLIC_SOURCE_DATUM_INVALID"
        )
    )
    clock_reference = (
        None
        if provider_clock_reference_at is None
        else _time(
            provider_clock_reference_at,
            "V32_PUBLIC_SOURCE_DATUM_INVALID",
        )
    )
    if effective_at is not None:
        _time(effective_at, "V32_PUBLIC_SOURCE_DATUM_INVALID")
    provider_ahead_ms: int | None
    clock_status: str
    if status == "UNKNOWN":
        provider_ahead_ms = None
        clock_status = "UNKNOWN"
    elif provider is None:
        provider_ahead_ms = None
        clock_status = "LOCAL_CAPTURE_NO_PROVIDER_CLOCK"
    else:
        if clock_reference is None:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_DATUM_INVALID"
            )
        ahead = provider - clock_reference
        ahead_microseconds = max(0, ahead // timedelta(microseconds=1))
        provider_ahead_ms = (ahead_microseconds + 999) // 1000
        clock_status = (
            "WITHIN_BOUND_PROVIDER_AHEAD_NORMALIZED_TO_SOURCE_CLOCK"
            if provider_ahead_ms > 0
            else "PROVIDER_NOT_AHEAD"
        )
    if (
        status not in {"OBSERVED", "DERIVED", "UNKNOWN"}
        or (status == "UNKNOWN") != (value is None)
        or (status == "UNKNOWN") != (unit is None)
        or (status == "UNKNOWN") != (reason_code is not None)
        or (status == "UNKNOWN") != (observed_at is None)
        or (
            status == "UNKNOWN"
            and (
                provider_observed_at is not None
                or provider_clock_reference_at is not None
                or effective_at is not None
            )
        )
        or (
            status != "UNKNOWN"
            and (
                observed is None
                or observed > available
                or (
                    provider is None
                    and (
                        clock_reference is not None
                        or observed != available
                    )
                )
                or (
                    provider is not None
                    and (
                        clock_reference is None
                        or clock_reference > available
                        or provider_ahead_ms is None
                        or provider_ahead_ms
                        > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS
                        or observed != min(provider, clock_reference)
                    )
                )
            )
        )
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DATUM_INVALID"
        )
    return self_digest(
        {
            "schema_id": PIT_DATUM_SCHEMA_ID,
            "schema_version": PIT_DATUM_SCHEMA_VERSION,
            "datum_id": datum_id,
            "instrument_id": OKX_INSTRUMENT_ID,
            "metric_kind": metric_kind,
            "status": status,
            "value": value,
            "unit": unit,
            "observed_at": observed_at,
            "provider_observed_at": provider_observed_at,
            "effective_at": effective_at,
            "provider_clock_ahead_milliseconds": provider_ahead_ms,
            "clock_uncertainty_status": clock_status,
            "available_at": available_at,
            "source_component_id": source_component_id,
            "source_event_id": source_event_id,
            "raw_binding": dict(raw_binding) if raw_binding is not None else None,
            "dependency_group_ids": sorted(set(dependency_group_ids)),
            "reason_code": reason_code,
            "derivation": derivation,
            "point_in_time": True,
            "missing_is_zero": False,
        },
        PIT_DATUM_DIGEST_FIELD,
    )


def _event(
    *,
    component: Mapping[str, Any],
    raw_binding: Mapping[str, str] | None,
    aggregate_raw_binding: Mapping[str, str],
) -> dict[str, Any]:
    component_id = str(component["component_id"])
    observed = component["status"] == "OBSERVED"
    return self_digest(
        {
            "schema_id": INFORMATION_EVENT_SCHEMA_ID,
            "schema_version": INFORMATION_EVENT_SCHEMA_VERSION,
            "event_id": f"okx-public-request:{component_id.lower()}",
            "venue": "OKX",
            "instrument_id": OKX_INSTRUMENT_ID,
            "source_type": "OFFICIAL_EXCHANGE_PUBLIC_ENDPOINT",
            "component_id": component_id,
            "request_path": component["path"],
            "request_query": dict(component["query"]),
            "request_started_at": component["request_started_at"],
            "available_at": component["response_received_at"],
            "status": "OBSERVED" if observed else "UNKNOWN",
            "raw_binding": dict(raw_binding) if raw_binding is not None else None,
            "failure_evidence_binding": (
                None
                if observed
                else dict(component["failure_evidence_binding"])
            ),
            "reason_code": None if observed else component["error_code"],
            "attempt_number": 1,
            "retry_allowed": False,
            "dependency_group_ids": [
                "VENUE:OKX",
                f"REQUEST:{component_id}",
            ],
            "claim_ceiling": "PUBLISHED_PUBLIC_RESPONSE_ONLY",
            "account_data_accessed": False,
            "order_data_accessed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        INFORMATION_EVENT_DIGEST_FIELD,
    )


def _parse_candles(
    *,
    component: Mapping[str, Any],
    timeframe: str,
    server_time_ms: int,
) -> list[tuple[int, str, str, str, str, str]]:
    try:
        root = loads_json_strict(str(component["body_utf8"]))
    except ValueError as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
        ) from exc
    if (
        set(root) != {"code", "msg", "data"}
        or root.get("code") != "0"
        or root.get("msg") not in {"", None}
        or not isinstance(root.get("data"), list)
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
        )
    query_limit = component.get("query", {}).get("limit")
    if (
        not isinstance(query_limit, str)
        or not query_limit.isdigit()
        or int(query_limit) <= 0
        or len(root["data"]) > int(query_limit)
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
        )
    interval = _TIMEFRAME_INTERVAL_MS[timeframe]
    output: list[tuple[int, str, str, str, str, str]] = []
    for row in root["data"]:
        if (
            not isinstance(row, list)
            or len(row) < 9
            or any(not isinstance(value, str) for value in row[:9])
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
            )
        if row[8] not in {"0", "1"}:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
            )
        if row[8] == "0":
            continue
        opened = _milliseconds(row[0], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID")
        opened_price = _decimal(
            row[1], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID", positive=True
        )
        high = _decimal(
            row[2], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID", positive=True
        )
        low = _decimal(
            row[3], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID", positive=True
        )
        close = _decimal(
            row[4], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID", positive=True
        )
        volume = _decimal(
            row[5], "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID", nonnegative=True
        )
        if (
            opened % interval != 0
            or opened + interval > server_time_ms
            or Decimal(high) < Decimal(low)
            or Decimal(high) < max(Decimal(opened_price), Decimal(close))
            or Decimal(low) > min(Decimal(opened_price), Decimal(close))
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_CLOSED_BAR_INVALID"
            )
        output.append((opened, opened_price, high, low, close, volume))
    output.sort(key=lambda item: item[0])
    if (
        len(output) < 20
        or len({row[0] for row in output}) != len(output)
        or any(
            current[0] - previous[0] != interval
            for previous, current in zip(output, output[1:])
        )
        or output[-1][0] + interval
        != (server_time_ms // interval) * interval
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_CLOSED_BAR_COVERAGE_INVALID"
        )
    return output


def _simple_rsi14(closes: Sequence[str]) -> str:
    if len(closes) < 15:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_RSI_INPUT_INVALID"
        )
    values = [Decimal(value) for value in closes[-15:]]
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for previous, current in zip(values, values[1:]):
        delta = current - previous
        gains.append(max(delta, Decimal("0")))
        losses.append(max(-delta, Decimal("0")))
    average_gain = sum(gains, Decimal("0")) / Decimal("14")
    average_loss = sum(losses, Decimal("0")) / Decimal("14")
    if average_loss == 0:
        return "100" if average_gain > 0 else "50"
    relative_strength = average_gain / average_loss
    return canonical_decimal(
        Decimal("100") - Decimal("100") / (Decimal("1") + relative_strength)
    )


def _derive_bundle(
    *,
    raw: bytes,
    available_at: str,
    aggregate_raw_binding: Mapping[str, str],
    component_raw_bindings: Mapping[str, Mapping[str, str] | None],
) -> dict[str, Any]:
    components, raw_sha = _component_rows(raw)
    outer_available = _time(
        available_at, "V32_PUBLIC_SOURCE_AVAILABLE_TIME_INVALID"
    )
    if any(
        _time(row["response_received_at"], "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID")
        > outer_available
        for row in components.values()
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_COMPONENT_TIME_TRAVEL"
        )

    events = [
        _event(
            component=components[component_id],
            raw_binding=component_raw_bindings[component_id],
            aggregate_raw_binding=aggregate_raw_binding,
        )
        for component_id in _COMPONENT_ORDER
    ]
    event_by_component = {row["component_id"]: row for row in events}
    datums: list[dict[str, Any]] = []

    def provider_time_fields(
        *,
        component_id: str,
        provider_ms: int,
        stale_after_ms: int | None,
    ) -> tuple[str, str, datetime]:
        received = _time(
            components[component_id]["response_received_at"],
            "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID",
        )
        provider = datetime.fromtimestamp(provider_ms / 1000, tz=UTC)
        ahead = provider - received
        ahead_microseconds = max(0, ahead // timedelta(microseconds=1))
        ahead_ms = (ahead_microseconds + 999) // 1000
        if ahead_ms > MAX_PROVIDER_CLOCK_AHEAD_MILLISECONDS:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_PROVIDER_TIME_TRAVEL"
            )
        normalized = min(provider, received)
        if (
            stale_after_ms is not None
            and outer_available - normalized
            > timedelta(milliseconds=stale_after_ms)
        ):
            raise V32PublicSourceCollectorError(
                f"V32_PUBLIC_SOURCE_COMPONENT_STALE:{component_id}"
            )
        provider_text = _time_text(provider)
        normalized_text = (
            components[component_id]["response_received_at"]
            if provider > received
            else provider_text
        )
        return normalized_text, provider_text, normalized

    def observed_datum(
        *,
        datum_id: str,
        metric_kind: str,
        value: str,
        unit: str,
        observed_at: str,
        component_id: str,
        dependencies: Sequence[str] = (),
        derivation: str = "DIRECT_PUBLIC_FIELD",
        provider_observed_at: str | None = None,
        effective_at: str | None = None,
        local_capture_clock: bool = False,
    ) -> None:
        event = event_by_component[component_id]
        provider_time = (
            None
            if local_capture_clock
            else (
                observed_at
                if provider_observed_at is None
                else provider_observed_at
            )
        )
        datum_available_at = (
            event["available_at"]
            if derivation == "DIRECT_PUBLIC_FIELD"
            else available_at
        )
        datums.append(
            _datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                status="DERIVED" if derivation != "DIRECT_PUBLIC_FIELD" else "OBSERVED",
                value=value,
                unit=unit,
                observed_at=observed_at,
                available_at=datum_available_at,
                source_component_id=component_id,
                source_event_id=event["event_id"],
                raw_binding=component_raw_bindings[component_id],
                dependency_group_ids=[
                    "VENUE:OKX",
                    f"REQUEST:{component_id}",
                    *dependencies,
                ],
                reason_code=None,
                derivation=derivation,
                provider_observed_at=provider_time,
                provider_clock_reference_at=(
                    None if provider_time is None else event["available_at"]
                ),
                effective_at=effective_at,
            )
        )

    def unknown_datum(
        *, datum_id: str, metric_kind: str, unit_hint: str, component_id: str
    ) -> None:
        event = event_by_component[component_id]
        datums.append(
            _datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                status="UNKNOWN",
                value=None,
                unit=None,
                observed_at=None,
                available_at=event["available_at"],
                source_component_id=component_id,
                source_event_id=event["event_id"],
                raw_binding=None,
                dependency_group_ids=[
                    "VENUE:OKX",
                    f"REQUEST:{component_id}",
                    f"UNIT_HINT:{unit_hint}",
                ],
                reason_code=str(components[component_id]["error_code"]),
                derivation="NOT_DERIVED_SOURCE_UNKNOWN",
                provider_observed_at=None,
                provider_clock_reference_at=None,
                effective_at=None,
            )
        )

    server_rows = _okx_rows(
        str(components["SERVER_TIME"]["body_utf8"]),
        "V32_PUBLIC_SOURCE_SERVER_TIME_INVALID",
    )
    if len(server_rows) != 1:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_SERVER_TIME_INVALID"
        )
    server_time_ms = _milliseconds(
        server_rows[0].get("ts"), "V32_PUBLIC_SOURCE_SERVER_TIME_INVALID"
    )
    server_observed_at, server_provider_at, _ = provider_time_fields(
        component_id="SERVER_TIME",
        provider_ms=server_time_ms,
        stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
    )
    _require_queries(components, server_time_ms=server_time_ms)
    server_time = server_provider_at
    observed_datum(
        datum_id="okx-server-time-ms",
        metric_kind="PROVIDER_SERVER_TIME",
        value=str(server_time_ms),
        unit="UNIX_MS",
        observed_at=server_observed_at,
        provider_observed_at=server_provider_at,
        component_id="SERVER_TIME",
    )

    instrument_rows = _okx_rows(
        str(components["INSTRUMENT"]["body_utf8"]),
        "V32_PUBLIC_SOURCE_INSTRUMENT_INVALID",
    )
    if len(instrument_rows) != 1:
        raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_INSTRUMENT_INVALID")
    instrument = instrument_rows[0]
    if (
        instrument.get("instId") != OKX_INSTRUMENT_ID
        or instrument.get("state") != "live"
        or instrument.get("ctValCcy") != "BTC"
        or instrument.get("ctType") != "linear"
        or instrument.get("settleCcy") != "USDT"
    ):
        raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_INSTRUMENT_INVALID")
    for field, datum_id, unit in (
        ("ctVal", "contract-value", "BTC_PER_CONTRACT"),
        ("ctMult", "contract-multiplier", "OKX_CT_MULT"),
        ("lotSz", "quantity-step", "CONTRACTS"),
        ("minSz", "minimum-quantity", "CONTRACTS"),
        ("tickSz", "price-tick", "USDT_PER_BTC"),
    ):
        observed_datum(
            datum_id=datum_id,
            metric_kind=f"INSTRUMENT_{field.upper()}",
            value=_decimal(
                instrument.get(field),
                "V32_PUBLIC_SOURCE_INSTRUMENT_INVALID",
                positive=True,
            ),
            unit=unit,
            observed_at=str(components["INSTRUMENT"]["response_received_at"]),
            component_id="INSTRUMENT",
            local_capture_clock=True,
            dependencies=["CLOCK:LOCAL_CAPTURE_NO_PROVIDER_SNAPSHOT_TIME"],
        )

    ticker_rows = _okx_rows(
        str(components["TICKER"]["body_utf8"]),
        "V32_PUBLIC_SOURCE_TICKER_INVALID",
    )
    if len(ticker_rows) != 1 or ticker_rows[0].get("instId") != OKX_INSTRUMENT_ID:
        raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_TICKER_INVALID")
    ticker = ticker_rows[0]
    ticker_time_ms = _milliseconds(
        ticker.get("ts"), "V32_PUBLIC_SOURCE_TICKER_INVALID"
    )
    ticker_time, ticker_provider_time, _ = provider_time_fields(
        component_id="TICKER",
        provider_ms=ticker_time_ms,
        stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
    )
    for field, datum_id, unit, positive in (
        ("last", "ticker-last", "USDT_PER_BTC", True),
        ("bidPx", "ticker-best-bid", "USDT_PER_BTC", True),
        ("askPx", "ticker-best-ask", "USDT_PER_BTC", True),
        ("vol24h", "ticker-volume-24h-contracts", "CONTRACTS", False),
        ("volCcy24h", "ticker-volume-24h-btc", "BTC", False),
    ):
        observed_datum(
            datum_id=datum_id,
            metric_kind=f"TICKER_{field.upper()}",
            value=_decimal(
                ticker.get(field),
                "V32_PUBLIC_SOURCE_TICKER_INVALID",
                positive=positive,
                nonnegative=not positive,
            ),
            unit=unit,
            observed_at=ticker_time,
            provider_observed_at=ticker_provider_time,
            component_id="TICKER",
        )

    mark_rows = _okx_rows(
        str(components["MARK_PRICE"]["body_utf8"]),
        "V32_PUBLIC_SOURCE_MARK_PRICE_INVALID",
    )
    if len(mark_rows) != 1 or mark_rows[0].get("instId") != OKX_INSTRUMENT_ID:
        raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_MARK_PRICE_INVALID")
    mark_price = _decimal(
        mark_rows[0].get("markPx"),
        "V32_PUBLIC_SOURCE_MARK_PRICE_INVALID",
        positive=True,
    )
    mark_time_ms = _milliseconds(
        mark_rows[0].get("ts"), "V32_PUBLIC_SOURCE_MARK_PRICE_INVALID"
    )
    mark_time, mark_provider_time, _ = provider_time_fields(
        component_id="MARK_PRICE",
        provider_ms=mark_time_ms,
        stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
    )
    observed_datum(
        datum_id="mark-price",
        metric_kind="PUBLIC_MARK_PRICE",
        value=mark_price,
        unit="USDT_PER_BTC",
        observed_at=mark_time,
        provider_observed_at=mark_provider_time,
        component_id="MARK_PRICE",
    )

    bar_series: dict[str, list[dict[str, Any]]] = {}
    latest_close_ms: dict[str, int] = {}
    latest_close_observed_at: dict[str, str] = {}
    latest_close_provider_at: dict[str, str] = {}
    for timeframe, component_id in _TIMEFRAME_COMPONENT.items():
        bars = _parse_candles(
            component=components[component_id],
            timeframe=timeframe,
            server_time_ms=server_time_ms,
        )
        interval = _TIMEFRAME_INTERVAL_MS[timeframe]
        series: list[dict[str, Any]] = []
        for index, (opened, open_value, high, low, close, volume) in enumerate(bars):
            close_ms = opened + interval
            observed_at, provider_observed_at, _ = provider_time_fields(
                component_id=component_id,
                provider_ms=close_ms,
                stale_after_ms=None,
            )
            bar_dependency = f"BAR:{timeframe}:{opened}"
            for metric, value, unit in (
                ("OPEN", open_value, "USDT_PER_BTC"),
                ("HIGH", high, "USDT_PER_BTC"),
                ("LOW", low, "USDT_PER_BTC"),
                ("CLOSE", close, "USDT_PER_BTC"),
                ("VOLUME", volume, "CONTRACTS"),
            ):
                observed_datum(
                    datum_id=f"bar-{timeframe.lower()}-{opened}-{metric.lower()}",
                    metric_kind=f"CLOSED_BAR_{metric}",
                    value=value,
                    unit=unit,
                    observed_at=observed_at,
                    provider_observed_at=provider_observed_at,
                    component_id=component_id,
                    dependencies=[f"TIMEFRAME:{timeframe}", bar_dependency],
                )
            range_pct = (
                (Decimal(high) - Decimal(low)) / Decimal(close) * Decimal("100")
            )
            observed_datum(
                datum_id=f"bar-{timeframe.lower()}-{opened}-range-pct",
                metric_kind="CLOSED_BAR_RANGE_PCT",
                value=canonical_decimal(range_pct),
                unit="PERCENT",
                observed_at=observed_at,
                provider_observed_at=provider_observed_at,
                component_id=component_id,
                dependencies=[f"TIMEFRAME:{timeframe}", bar_dependency],
                derivation="DERIVED_FROM_SAME_CLOSED_BAR",
            )
            if index > 0:
                previous_close = Decimal(bars[index - 1][4])
                return_pct = (
                    Decimal(close) / previous_close - Decimal("1")
                ) * Decimal("100")
                observed_datum(
                    datum_id=f"bar-{timeframe.lower()}-{opened}-return-pct",
                    metric_kind="CLOSED_BAR_RETURN_PCT",
                    value=canonical_decimal(return_pct),
                    unit="PERCENT",
                    observed_at=observed_at,
                    provider_observed_at=provider_observed_at,
                    component_id=component_id,
                    dependencies=[
                        f"TIMEFRAME:{timeframe}",
                        bar_dependency,
                        f"BAR:{timeframe}:{bars[index - 1][0]}",
                    ],
                    derivation="DERIVED_FROM_TWO_CLOSED_BARS",
                )
            series.append(
                {
                    "open_time_ms": opened,
                    "close_time_ms": close_ms,
                    "open": open_value,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume_contracts": volume,
                    "confirmed_closed": True,
                }
            )
            if index == len(bars) - 1:
                latest_close_observed_at[timeframe] = observed_at
                latest_close_provider_at[timeframe] = provider_observed_at
        latest_close_ms[timeframe] = series[-1]["close_time_ms"]
        observed_datum(
            datum_id=f"rsi14-{timeframe.lower()}",
            metric_kind="SIMPLE_RSI14_CLOSED_BARS",
            value=_simple_rsi14([row["close"] for row in series]),
            unit="INDEX_0_100",
            observed_at=latest_close_observed_at[timeframe],
            provider_observed_at=latest_close_provider_at[timeframe],
            component_id=component_id,
            dependencies=[f"TIMEFRAME:{timeframe}", "WINDOW:CLOSED_BARS_15"],
            derivation="DERIVED_SIMPLE_RSI14_NOT_PREDICTION",
        )
        bar_series[timeframe] = series

    open_interest_component = components["OPEN_INTEREST"]
    if open_interest_component["status"] == "UNKNOWN":
        unknown_datum(
            datum_id="open-interest-btc",
            metric_kind="PUBLIC_OPEN_INTEREST_LEVEL",
            unit_hint="BTC",
            component_id="OPEN_INTEREST",
        )
    else:
        open_interest_rows = _okx_rows(
            str(open_interest_component["body_utf8"]),
            "V32_PUBLIC_SOURCE_OPEN_INTEREST_INVALID",
        )
        if (
            len(open_interest_rows) != 1
            or open_interest_rows[0].get("instId") != OKX_INSTRUMENT_ID
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_OPEN_INTEREST_INVALID"
            )
        open_interest_value = _decimal(
            open_interest_rows[0].get("oiCcy"),
            "V32_PUBLIC_SOURCE_OPEN_INTEREST_INVALID",
            nonnegative=True,
        )
        open_interest_ms = _milliseconds(
            open_interest_rows[0].get("ts"),
            "V32_PUBLIC_SOURCE_OPEN_INTEREST_INVALID",
        )
        (
            open_interest_time,
            open_interest_provider_time,
            _,
        ) = provider_time_fields(
            component_id="OPEN_INTEREST",
            provider_ms=open_interest_ms,
            stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
        )
        observed_datum(
            datum_id="open-interest-btc",
            metric_kind="PUBLIC_OPEN_INTEREST_LEVEL",
            value=open_interest_value,
            unit="BTC",
            observed_at=open_interest_time,
            provider_observed_at=open_interest_provider_time,
            component_id="OPEN_INTEREST",
        )

    funding_component = components["FUNDING_RATE"]
    if funding_component["status"] == "UNKNOWN":
        for datum_id, metric_kind, unit_hint in (
            ("funding-rate", "PUBLIC_FUNDING_RATE", "RATE"),
            (
                "next-funding-settlement-time-ms",
                "PUBLIC_NEXT_FUNDING_SETTLEMENT_SCHEDULE",
                "UNIX_MS",
            ),
        ):
            unknown_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                unit_hint=unit_hint,
                component_id="FUNDING_RATE",
            )
    else:
        funding_rows = _okx_rows(
            str(funding_component["body_utf8"]),
            "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID",
        )
        if (
            len(funding_rows) != 1
            or funding_rows[0].get("instId") != OKX_INSTRUMENT_ID
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID"
            )
        funding_row = funding_rows[0]
        funding_value = _decimal(
            funding_row.get("fundingRate"),
            "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID",
        )
        funding_observed_ms = _milliseconds(
            funding_row.get("ts"),
            "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID",
        )
        funding_effective_ms = _milliseconds(
            funding_row.get("fundingTime"),
            "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID",
        )
        next_funding_effective_ms = _milliseconds(
            funding_row.get("nextFundingTime"),
            "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID",
        )
        if not (
            funding_observed_ms
            <= funding_effective_ms
            < next_funding_effective_ms
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_FUNDING_RATE_INVALID"
            )
        (
            funding_observed_at,
            funding_provider_observed_at,
            _,
        ) = provider_time_fields(
            component_id="FUNDING_RATE",
            provider_ms=funding_observed_ms,
            stale_after_ms=MAX_FUNDING_COMPONENT_STALENESS_MILLISECONDS,
        )
        funding_effective_at = _time_text(
            datetime.fromtimestamp(funding_effective_ms / 1000, tz=UTC)
        )
        next_funding_effective_at = _time_text(
            datetime.fromtimestamp(next_funding_effective_ms / 1000, tz=UTC)
        )
        observed_datum(
            datum_id="funding-rate",
            metric_kind="PUBLIC_FUNDING_RATE",
            value=funding_value,
            unit="RATE",
            observed_at=funding_observed_at,
            provider_observed_at=funding_provider_observed_at,
            effective_at=funding_effective_at,
            component_id="FUNDING_RATE",
            dependencies=[
                "SEMANTICS:CURRENT_PERIOD_INDICATIVE_NOT_REALIZED_SETTLEMENT",
                "TIME_ROLE:FUNDING_TIME_IS_EFFECTIVE_NOT_OBSERVED",
            ],
        )
        observed_datum(
            datum_id="next-funding-settlement-time-ms",
            metric_kind="PUBLIC_NEXT_FUNDING_SETTLEMENT_SCHEDULE",
            value=str(next_funding_effective_ms),
            unit="UNIX_MS",
            observed_at=funding_observed_at,
            provider_observed_at=funding_provider_observed_at,
            effective_at=next_funding_effective_at,
            component_id="FUNDING_RATE",
            dependencies=["TIME_ROLE:FUTURE_SCHEDULE_NOT_OBSERVATION_TIME"],
        )

    book_component = components["ORDER_BOOK"]
    if book_component["status"] == "UNKNOWN":
        for datum_id, metric_kind, unit in (
            ("book-best-bid", "BOOK_BEST_BID", "USDT_PER_BTC"),
            ("book-best-ask", "BOOK_BEST_ASK", "USDT_PER_BTC"),
            ("book-spread-bps", "BOOK_SPREAD_BPS", "BASIS_POINTS"),
            ("book-top5-imbalance", "BOOK_TOP5_IMBALANCE", "RATIO_NEG1_TO_1"),
        ):
            unknown_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                unit_hint=unit,
                component_id="ORDER_BOOK",
            )
    else:
        book_rows = _okx_rows(
            str(book_component["body_utf8"]), "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID"
        )
        if len(book_rows) != 1:
            raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID")
        book = book_rows[0]
        bids, asks = book.get("bids"), book.get("asks")
        if (
            not isinstance(bids, list)
            or not isinstance(asks, list)
            or not 5 <= len(bids) <= 50
            or not 5 <= len(asks) <= 50
            or any(
                not isinstance(row, list) or len(row) < 2
                for row in [*bids, *asks]
            )
        ):
            raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID")
        try:
            all_bid_rows = [
                (
                    _decimal(row[0], "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID", positive=True),
                    _decimal(row[1], "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID", nonnegative=True),
                )
                for row in bids
            ]
            all_ask_rows = [
                (
                    _decimal(row[0], "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID", positive=True),
                    _decimal(row[1], "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID", nonnegative=True),
                )
                for row in asks
            ]
        except (IndexError, TypeError) as exc:
            raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID") from exc
        if any(
            Decimal(previous[0]) <= Decimal(current[0])
            for previous, current in zip(all_bid_rows, all_bid_rows[1:])
        ) or any(
            Decimal(previous[0]) >= Decimal(current[0])
            for previous, current in zip(all_ask_rows, all_ask_rows[1:])
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID"
            )
        bid_rows = all_bid_rows[:5]
        ask_rows = all_ask_rows[:5]
        book_time_ms = _milliseconds(book.get("ts"), "V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID")
        book_time, book_provider_time, _ = provider_time_fields(
            component_id="ORDER_BOOK",
            provider_ms=book_time_ms,
            stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
        )
        bid = Decimal(bid_rows[0][0])
        ask = Decimal(ask_rows[0][0])
        if ask <= bid:
            raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_ORDER_BOOK_INVALID")
        bid_size = sum((Decimal(row[1]) for row in bid_rows), Decimal("0"))
        ask_size = sum((Decimal(row[1]) for row in ask_rows), Decimal("0"))
        total = bid_size + ask_size
        values = (
            ("book-best-bid", "BOOK_BEST_BID", canonical_decimal(bid), "USDT_PER_BTC"),
            ("book-best-ask", "BOOK_BEST_ASK", canonical_decimal(ask), "USDT_PER_BTC"),
            (
                "book-spread-bps",
                "BOOK_SPREAD_BPS",
                canonical_decimal((ask - bid) / ((ask + bid) / Decimal("2")) * Decimal("10000")),
                "BASIS_POINTS",
            ),
            (
                "book-top5-imbalance",
                "BOOK_TOP5_IMBALANCE",
                canonical_decimal((bid_size - ask_size) / total) if total > 0 else "0",
                "RATIO_NEG1_TO_1",
            ),
        )
        for datum_id, metric_kind, value, unit in values:
            observed_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                value=value,
                unit=unit,
                observed_at=book_time,
                provider_observed_at=book_provider_time,
                component_id="ORDER_BOOK",
                dependencies=(
                    [_BOOK_TOP5_IMBALANCE_REPLAY_DEPENDENCY]
                    if datum_id == "book-top5-imbalance"
                    else []
                ),
                derivation=(
                    "DIRECT_PUBLIC_FIELD"
                    if datum_id in {"book-best-bid", "book-best-ask"}
                    else "DERIVED_FROM_SINGLE_BOOK_SNAPSHOT"
                ),
            )

    trades_component = components["RECENT_TRADES"]
    if trades_component["status"] == "UNKNOWN":
        for datum_id, metric_kind, unit in (
            ("recent-trade-count", "RECENT_TRADE_COUNT", "COUNT"),
            ("recent-trade-side-imbalance", "RECENT_TRADE_SIDE_IMBALANCE", "RATIO_NEG1_TO_1"),
            (
                "recent-trade-sample-start-ms",
                "RECENT_TRADE_SAMPLE_START_TIME",
                "UNIX_MS",
            ),
            (
                "recent-trade-sample-end-ms",
                "RECENT_TRADE_SAMPLE_END_TIME",
                "UNIX_MS",
            ),
            (
                "recent-trade-sample-request-limit",
                "RECENT_TRADE_SAMPLE_REQUEST_LIMIT",
                "COUNT",
            ),
            (
                "recent-trade-sample-truncation-status",
                "RECENT_TRADE_SAMPLE_TRUNCATION_STATUS",
                "ORDINAL_STATUS",
            ),
        ):
            unknown_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                unit_hint=unit,
                component_id="RECENT_TRADES",
            )
    else:
        trade_rows = _okx_rows(
            str(trades_component["body_utf8"]), "V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID"
        )
        if not trade_rows or len(trade_rows) > 100:
            raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID")
        buy = Decimal("0")
        sell = Decimal("0")
        trade_times: list[int] = []
        trade_ids: set[str] = set()
        for row in trade_rows:
            trade_id = row.get("tradeId")
            if (
                row.get("instId") != OKX_INSTRUMENT_ID
                or row.get("side") not in {"buy", "sell"}
                or not isinstance(trade_id, str)
                or not trade_id
                or trade_id in trade_ids
            ):
                raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID")
            trade_ids.add(trade_id)
            _decimal(
                row.get("px"),
                "V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID",
                positive=True,
            )
            size = Decimal(
                _decimal(row.get("sz"), "V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID", nonnegative=True)
            )
            trade_times.append(_milliseconds(row.get("ts"), "V32_PUBLIC_SOURCE_RECENT_TRADES_INVALID"))
            if row["side"] == "buy":
                buy += size
            else:
                sell += size
        latest_trade_ms = max(trade_times)
        earliest_trade_ms = min(trade_times)
        trade_time, trade_provider_time, _ = provider_time_fields(
            component_id="RECENT_TRADES",
            provider_ms=latest_trade_ms,
            stale_after_ms=MAX_REALTIME_COMPONENT_STALENESS_MILLISECONDS,
        )
        total = buy + sell
        for datum_id, metric_kind, value, unit, derivation in (
            ("recent-trade-count", "RECENT_TRADE_COUNT", str(len(trade_rows)), "COUNT", "DERIVED_FROM_PUBLIC_TRADE_SAMPLE"),
            (
                "recent-trade-side-imbalance",
                "RECENT_TRADE_SIDE_IMBALANCE",
                canonical_decimal((buy - sell) / total) if total > 0 else "0",
                "RATIO_NEG1_TO_1",
                "DERIVED_FROM_PUBLIC_TRADE_SAMPLE",
            ),
        ):
            observed_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                value=value,
                unit=unit,
                observed_at=trade_time,
                provider_observed_at=trade_provider_time,
                component_id="RECENT_TRADES",
                derivation=derivation,
            )
        for datum_id, metric_kind, value, unit in (
            (
                "recent-trade-sample-start-ms",
                "RECENT_TRADE_SAMPLE_START_TIME",
                str(earliest_trade_ms),
                "UNIX_MS",
            ),
            (
                "recent-trade-sample-end-ms",
                "RECENT_TRADE_SAMPLE_END_TIME",
                str(latest_trade_ms),
                "UNIX_MS",
            ),
            (
                "recent-trade-sample-request-limit",
                "RECENT_TRADE_SAMPLE_REQUEST_LIMIT",
                "100",
                "COUNT",
            ),
            (
                "recent-trade-sample-truncation-status",
                "RECENT_TRADE_SAMPLE_TRUNCATION_STATUS",
                (
                    "POSSIBLY_TRUNCATED_AT_REQUEST_LIMIT"
                    if len(trade_rows) == 100
                    else "NOT_REQUEST_LIMIT_SATURATED"
                ),
                "ORDINAL_STATUS",
            ),
        ):
            observed_datum(
                datum_id=datum_id,
                metric_kind=metric_kind,
                value=value,
                unit=unit,
                observed_at=trade_time,
                provider_observed_at=trade_provider_time,
                component_id="RECENT_TRADES",
                dependencies=[
                    "SAMPLE:FIXED_COUNT_NOT_FIXED_TIME_WINDOW",
                    "REQUEST_LIMIT:100",
                ],
                derivation="DERIVED_FROM_PUBLIC_TRADE_SAMPLE_METADATA",
            )

    market_observed_times = [
        _time(row["observed_at"], "V32_PUBLIC_SOURCE_AS_OF_INVALID")
        for row in datums
        if row["status"] in {"OBSERVED", "DERIVED"}
        and row["source_component_id"]
        not in {"SERVER_TIME", "INSTRUMENT"}
    ]
    if not market_observed_times:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_AS_OF_INVALID"
        )
    as_of = _time_text(max(market_observed_times))
    closed_bar_as_of = _time_text(
        datetime.fromtimestamp(latest_close_ms["15M"] / 1000, tz=UTC)
    )

    component_observed_at = {
        "TICKER": ticker_time,
        "MARK_PRICE": mark_time,
        **{
            component_id: latest_close_observed_at[timeframe]
            for timeframe, component_id in _TIMEFRAME_COMPONENT.items()
        },
    }
    if open_interest_component["status"] == "OBSERVED":
        component_observed_at["OPEN_INTEREST"] = open_interest_time
    if funding_component["status"] == "OBSERVED":
        component_observed_at["FUNDING_RATE"] = funding_observed_at
    if book_component["status"] == "OBSERVED":
        component_observed_at["ORDER_BOOK"] = book_time
    if trades_component["status"] == "OBSERVED":
        component_observed_at["RECENT_TRADES"] = trade_time

    axis_rows, axis_source_registry_digest = _build_axis_rows(
        component_statuses={
            component_id: row["status"]
            for component_id, row in components.items()
        },
        component_observed_at=component_observed_at,
        available_at=available_at,
        raw_sha256=raw_sha,
    )
    datums.sort(key=lambda row: row["datum_id"])
    if len({row["datum_id"] for row in datums}) != len(datums):
        raise V32PublicSourceCollectorError("V32_PUBLIC_SOURCE_DATUM_DUPLICATE")
    oi_datum = next(row for row in datums if row["datum_id"] == "open-interest-btc")
    return {
        "components": components,
        "raw_sha256": raw_sha,
        "as_of": as_of,
        "derived_available_at": available_at,
        "closed_bar_as_of": closed_bar_as_of,
        "mark_price": mark_price,
        "bar_series": bar_series,
        "information_events": events,
        "datums": datums,
        "open_interest_datum": oi_datum,
        "axis_source_evidence": axis_rows,
        "axis_source_registry_digest": axis_source_registry_digest,
        "pit_member_digests": sorted(
            [
                *[row[PIT_DATUM_DIGEST_FIELD] for row in datums],
                *[row[INFORMATION_EVENT_DIGEST_FIELD] for row in events],
                *[row[AXIS_EVIDENCE_DIGEST_FIELD] for row in axis_rows],
            ]
        ),
    }


def build_v32_public_market_analysis_bundle(
    *,
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    capture_digest: str,
    aggregate_raw_binding: Mapping[str, str],
    component_raw_bindings: Mapping[str, Mapping[str, str] | None],
    derived: Mapping[str, Any],
) -> dict[str, Any]:
    request_bindings = []
    components = derived["components"]
    for component_id in _COMPONENT_ORDER:
        component = components[component_id]
        request_bindings.append(
            {
                "component_id": component_id,
                "request_id": f"okx-public:{component_id.lower()}",
                "method": "GET",
                "base_url": OKX_PUBLIC_BASE_URL,
                "path": component["path"],
                "query": dict(component["query"]),
                "request_started_at": component["request_started_at"],
                "response_received_at": component["response_received_at"],
                "status": component["status"],
                "attempt_number": 1,
                "retry_allowed": False,
                "raw_binding": (
                    dict(component_raw_bindings[component_id])
                    if component_raw_bindings[component_id] is not None
                    else None
                ),
                "failure_evidence_binding": (
                    None
                    if component["status"] == "OBSERVED"
                    else dict(component["failure_evidence_binding"])
                ),
                "error_code": component["error_code"],
            }
        )
    return self_digest(
        {
            "schema_id": ANALYSIS_BUNDLE_SCHEMA_ID,
            "schema_version": ANALYSIS_BUNDLE_SCHEMA_VERSION,
            "qualification_id": qualification_id,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "instrument": {
                "venue": "OKX",
                "instrument_id": OKX_INSTRUMENT_ID,
                "market_type": "PERPETUAL_SWAP",
                "underlying_symbol": "BTC-USDT",
            },
            "as_of": derived["as_of"],
            # The typed axes are derived only after the aggregate response is
            # available.  The bundle knowledge time therefore cannot be
            # backdated to the latest inner component response.
            "available_at": derived["derived_available_at"],
            "capture_digest": capture_digest,
            "aggregate_raw_binding": dict(aggregate_raw_binding),
            "request_raw_bindings": request_bindings,
            "information_events": list(derived["information_events"]),
            "datums": list(derived["datums"]),
            "closed_bar_series": dict(derived["bar_series"]),
            "axis_source_evidence": list(derived["axis_source_evidence"]),
            "axis_source_registry_digest": derived[
                "axis_source_registry_digest"
            ],
            "pit_member_digests": list(derived["pit_member_digests"]),
            "point_in_time": True,
            "missing_is_zero": False,
            "other_unknown_policy": {
                "unknown_retained": True,
                "other_retained": True,
                "unknown_not_probability": True,
                "axis_direction_not_precomputed": True,
            },
            "single_source_collection_transaction": True,
            "each_request_attempt_count": 1,
            "retry_allowed": False,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
        },
        ANALYSIS_BUNDLE_DIGEST_FIELD,
    )


def verify_v32_public_market_analysis_bundle(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, ANALYSIS_BUNDLE_DIGEST_FIELD)
    except ValueError as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        ) from exc
    axes = document.get("axis_source_evidence")
    datums = document.get("datums")
    events = document.get("information_events")
    requests = document.get("request_raw_bindings")
    expected_axis_registry_digest, _, _ = _native_axis_registry_material()
    if (
        not isinstance(document, Mapping)
        or set(document) != _ANALYSIS_BUNDLE_FIELDS
        or document.get("schema_id") != ANALYSIS_BUNDLE_SCHEMA_ID
        or document.get("schema_version") != ANALYSIS_BUNDLE_SCHEMA_VERSION
        or document.get("point_in_time") is not True
        or document.get("missing_is_zero") is not False
        or document.get("single_source_collection_transaction") is not True
        or document.get("each_request_attempt_count") != 1
        or document.get("retry_allowed") is not False
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("account_data_accessed") is not False
        or document.get("order_data_accessed") is not False
        or document.get("axis_source_registry_digest")
        != expected_axis_registry_digest
        or not isinstance(axes, list)
        or [row.get("axis_id") for row in axes]
        != [*V31_NATIVE_SENTIMENT_AXES, "OTHER"]
        or not isinstance(datums, list)
        or not datums
        or len({row.get("datum_id") for row in datums}) != len(datums)
        or not isinstance(events, list)
        or len(events) != len(_COMPONENT_ORDER)
        or not isinstance(requests, list)
        or [row.get("component_id") for row in requests]
        != list(_COMPONENT_ORDER)
        or any(
            not isinstance(row, Mapping)
            or set(row) != _REQUEST_BINDING_FIELDS
            or row.get("attempt_number") != 1
            or row.get("retry_allowed") is not False
            for row in requests
        )
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    available = _time(
        document["available_at"], "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
    )
    if (
        _time(document["as_of"], "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID")
        > available
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    request_by_component = {row["component_id"]: row for row in requests}

    def valid_evidence_binding(value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and set(value) == _EVIDENCE_BINDING_FIELDS
            and isinstance(value.get("relative_ref"), str)
            and bool(value["relative_ref"])
            and isinstance(value.get("semantic_digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["semantic_digest"])
            is not None
            and isinstance(value.get("physical_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["physical_sha256"])
            is not None
        )

    def valid_raw_binding(value: Any) -> bool:
        return valid_evidence_binding(value) and value.get(
            "semantic_digest"
        ) == value.get("physical_sha256")

    if not valid_raw_binding(document.get("aggregate_raw_binding")):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    for row in requests:
        component_id = row["component_id"]
        status = row.get("status")
        request_started = _time(
            row.get("request_started_at"),
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        )
        response_received = _time(
            row.get("response_received_at"),
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        )
        if (
            component_id not in _COMPONENT_ORDER
            or row.get("method") != "GET"
            or row.get("base_url") != OKX_PUBLIC_BASE_URL
            or row.get("path") != _COMPONENT_PATHS[component_id]
            or request_started > response_received
            or response_received > available
            or status not in {"OBSERVED", "UNKNOWN"}
            or (
                status == "OBSERVED"
                and (
                    not valid_raw_binding(row.get("raw_binding"))
                    or row.get("failure_evidence_binding") is not None
                    or row.get("error_code") is not None
                )
            )
            or (
                status == "UNKNOWN"
                and (
                    component_id not in _OPTIONAL_COMPONENTS
                    or (
                        row.get("raw_binding") is not None
                        and not valid_raw_binding(row.get("raw_binding"))
                    )
                    or not valid_evidence_binding(
                        row.get("failure_evidence_binding")
                    )
                    or (
                        row.get("raw_binding") is not None
                        and row.get("failure_evidence_binding")
                        != row.get("raw_binding")
                    )
                    or (
                        row.get("raw_binding") is None
                        and row.get("failure_evidence_binding", {}).get(
                            "relative_ref"
                        )
                        != _component_no_response_failure_ref(
                            str(document["qualification_id"]), component_id
                        )
                    )
                    or not isinstance(row.get("error_code"), str)
                )
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
    event_by_id: dict[str, Mapping[str, Any]] = {}
    for row in events:
        if (
            not isinstance(row, Mapping)
            or set(row) != _EVENT_FIELDS
            or row.get("schema_id") != INFORMATION_EVENT_SCHEMA_ID
            or row.get("schema_version")
            != INFORMATION_EVENT_SCHEMA_VERSION
            or row.get("component_id") not in request_by_component
            or row.get("attempt_number") != 1
            or row.get("retry_allowed") is not False
            or row.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or row.get("executable") is not False
            or row.get("account_data_accessed") is not False
            or row.get("order_data_accessed") is not False
            or row.get("event_id") in event_by_id
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        verify_self_digest(row, INFORMATION_EVENT_DIGEST_FIELD)
        request = request_by_component[row["component_id"]]
        if (
            row.get("status") != request["status"]
            or row.get("raw_binding") != request["raw_binding"]
            or row.get("failure_evidence_binding")
            != request["failure_evidence_binding"]
            or row.get("reason_code") != request["error_code"]
            or row.get("available_at") != request["response_received_at"]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        event_by_id[str(row["event_id"])] = row
    for row in datums:
        if (
            not isinstance(row, Mapping)
            or set(row) != _DATUM_FIELDS
            or row.get("schema_id") != PIT_DATUM_SCHEMA_ID
            or row.get("schema_version") != PIT_DATUM_SCHEMA_VERSION
            or row.get("point_in_time") is not True
            or row.get("missing_is_zero") is not False
            or row.get("source_component_id") not in request_by_component
            or row.get("source_event_id") not in event_by_id
            or event_by_id.get(row.get("source_event_id"), {}).get(
                "component_id"
            )
            != row.get("source_component_id")
            or not isinstance(row.get("dependency_group_ids"), list)
            or row["dependency_group_ids"]
            != sorted(set(row["dependency_group_ids"]))
            or _time(
                row.get("available_at"),
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
            )
            > available
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        verify_self_digest(row, PIT_DATUM_DIGEST_FIELD)
        try:
            rebuilt_datum = _datum(
                datum_id=row["datum_id"],
                metric_kind=row["metric_kind"],
                status=row["status"],
                value=row["value"],
                unit=row["unit"],
                observed_at=row["observed_at"],
                available_at=row["available_at"],
                source_component_id=row["source_component_id"],
                source_event_id=row["source_event_id"],
                raw_binding=row["raw_binding"],
                dependency_group_ids=row["dependency_group_ids"],
                reason_code=row["reason_code"],
                derivation=row["derivation"],
                provider_observed_at=row["provider_observed_at"],
                provider_clock_reference_at=(
                    None
                    if row["provider_observed_at"] is None
                    else event_by_id[row["source_event_id"]]["available_at"]
                ),
                effective_at=row["effective_at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            ) from exc
        if dict(row) != rebuilt_datum:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        request = request_by_component[row["source_component_id"]]
        if row.get("status") == "UNKNOWN":
            if (
                row.get("value") is not None
                or row.get("unit") is not None
                or row.get("observed_at") is not None
                or row.get("raw_binding") is not None
                or not isinstance(row.get("reason_code"), str)
                or request["status"] != "UNKNOWN"
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
                )
        elif row.get("status") in {"OBSERVED", "DERIVED"}:
            if (
                not isinstance(row.get("value"), str)
                or not row["value"]
                or not isinstance(row.get("unit"), str)
                or not row["unit"]
                or row.get("reason_code") is not None
                or row.get("raw_binding") != request["raw_binding"]
                or request["status"] != "OBSERVED"
                or (
                    row.get("status") == "DERIVED"
                    and row.get("available_at") != document["available_at"]
                )
                or (
                    row.get("source_component_id") == "INSTRUMENT"
                    and row.get("provider_observed_at") is not None
                )
                or (
                    row.get("source_component_id") != "INSTRUMENT"
                    and not isinstance(
                        row.get("provider_observed_at"), str
                    )
                )
                or (
                    row.get("datum_id")
                    in {
                        "funding-rate",
                        "next-funding-settlement-time-ms",
                    }
                )
                != isinstance(row.get("effective_at"), str)
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
                )
            _time(
                row.get("observed_at"),
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
            )
        else:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
    datum_by_id = {str(row["datum_id"]): row for row in datums}
    if not set(_FIXED_DATUM_CONTRACTS).issubset(datum_by_id):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_DATUM_SET_INVALID"
        )
    book_ids = (
        "book-best-bid",
        "book-best-ask",
        "book-spread-bps",
        "book-top5-imbalance",
    )
    book_datums = [datum_by_id[datum_id] for datum_id in book_ids]
    book_request = request_by_component["ORDER_BOOK"]
    if (
        book_request["status"] == "UNKNOWN"
        and any(row["status"] != "UNKNOWN" for row in book_datums)
    ) or (
        book_request["status"] == "OBSERVED"
        and [row["status"] for row in book_datums]
        != ["OBSERVED", "OBSERVED", "DERIVED", "DERIVED"]
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BOOK_INVALID"
        )
    if book_request["status"] == "OBSERVED":
        try:
            bid = Decimal(datum_by_id["book-best-bid"]["value"])
            ask = Decimal(datum_by_id["book-best-ask"]["value"])
            spread = Decimal(datum_by_id["book-spread-bps"]["value"])
            imbalance = Decimal(
                datum_by_id["book-top5-imbalance"]["value"]
            )
            expected_spread = canonical_decimal(
                (ask - bid)
                / ((ask + bid) / Decimal("2"))
                * Decimal("10000")
            )
        except (KeyError, TypeError, InvalidOperation, ZeroDivisionError) as exc:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BOOK_INVALID"
            ) from exc
        common_fields = (
            "observed_at",
            "provider_observed_at",
            "provider_clock_ahead_milliseconds",
            "clock_uncertainty_status",
            "source_component_id",
            "source_event_id",
            "raw_binding",
        )
        book_reference = datum_by_id["book-best-bid"]
        if (
            book_request.get("query", {}).get("sz") != "50"
            or bid <= 0
            or ask <= bid
            or spread < 0
            or datum_by_id["book-spread-bps"]["value"]
            != expected_spread
            or not Decimal("-1") <= imbalance <= Decimal("1")
            or any(
                row[field] != book_reference[field]
                for row in book_datums
                for field in common_fields
            )
            or _BOOK_TOP5_IMBALANCE_REPLAY_DEPENDENCY
            not in datum_by_id["book-top5-imbalance"][
                "dependency_group_ids"
            ]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BOOK_INVALID"
            )
    market_observations = [
        _time(
            row["observed_at"],
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        )
        for row in datums
        if row["status"] in {"OBSERVED", "DERIVED"}
        and row["source_component_id"]
        not in {"SERVER_TIME", "INSTRUMENT"}
    ]
    if (
        not market_observations
        or document["as_of"] != _time_text(max(market_observations))
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_AS_OF_RECONSTRUCTION_MISMATCH"
        )
    funding = datum_by_id.get("funding-rate")
    next_funding = datum_by_id.get("next-funding-settlement-time-ms")
    if funding is None or next_funding is None or (
        funding["status"] == "UNKNOWN"
    ) != (next_funding["status"] == "UNKNOWN"):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID"
        )
    if funding["status"] != "UNKNOWN":
        try:
            funding_provider = _time(
                funding["provider_observed_at"],
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID",
            )
            funding_effective = _time(
                funding["effective_at"],
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID",
            )
            next_effective = _time(
                next_funding["effective_at"],
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID",
            )
            next_value_ms = _milliseconds(
                next_funding["value"],
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID",
            )
            next_value_time = datetime.fromtimestamp(
                next_value_ms / 1000, tz=UTC
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, V32PublicSourceCollectorError):
                raise
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID"
            ) from exc
        if (
            not funding_provider <= funding_effective < next_effective
            or next_effective != next_value_time
            or funding["observed_at"] != next_funding["observed_at"]
            or funding["provider_observed_at"]
            != next_funding["provider_observed_at"]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_FUNDING_TIME_INVALID"
            )
    trade_ids = (
        "recent-trade-count",
        "recent-trade-side-imbalance",
        "recent-trade-sample-start-ms",
        "recent-trade-sample-end-ms",
        "recent-trade-sample-request-limit",
        "recent-trade-sample-truncation-status",
    )
    trade_datums = [datum_by_id.get(datum_id) for datum_id in trade_ids]
    trades_request = request_by_component["RECENT_TRADES"]
    if any(row is None for row in trade_datums) or (
        trades_request["status"] == "OBSERVED"
        and any(
            row.get("status") not in {"OBSERVED", "DERIVED"}
            for row in trade_datums
        )
    ) or (
        trades_request["status"] == "UNKNOWN"
        and any(row.get("status") != "UNKNOWN" for row in trade_datums)
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_TRADE_SAMPLE_INVALID"
        )
    if trades_request["status"] == "OBSERVED":
        try:
            count = int(datum_by_id["recent-trade-count"]["value"])
            start_ms = int(
                datum_by_id["recent-trade-sample-start-ms"]["value"]
            )
            end_ms = int(
                datum_by_id["recent-trade-sample-end-ms"]["value"]
            )
            limit = int(
                datum_by_id["recent-trade-sample-request-limit"]["value"]
            )
            imbalance = Decimal(
                datum_by_id["recent-trade-side-imbalance"]["value"]
            )
            provider_end = _time(
                datum_by_id["recent-trade-count"]["provider_observed_at"],
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_TRADE_SAMPLE_INVALID",
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_TRADE_SAMPLE_INVALID"
            ) from exc
        expected_truncation = (
            "POSSIBLY_TRUNCATED_AT_REQUEST_LIMIT"
            if count == limit
            else "NOT_REQUEST_LIMIT_SATURATED"
        )
        if (
            str(count) != datum_by_id["recent-trade-count"]["value"]
            or str(start_ms)
            != datum_by_id["recent-trade-sample-start-ms"]["value"]
            or str(end_ms)
            != datum_by_id["recent-trade-sample-end-ms"]["value"]
            or str(limit)
            != datum_by_id["recent-trade-sample-request-limit"]["value"]
            or trades_request.get("query", {}).get("limit") != "100"
            or limit != 100
            or not 1 <= count <= limit
            or not 0 <= start_ms <= end_ms
            or not Decimal("-1") <= imbalance <= Decimal("1")
            or datum_by_id["recent-trade-sample-truncation-status"][
                "value"
            ]
            != expected_truncation
            or any(
                row["observed_at"]
                != datum_by_id["recent-trade-count"]["observed_at"]
                or row["provider_observed_at"]
                != datum_by_id["recent-trade-count"][
                    "provider_observed_at"
                ]
                for row in trade_datums
            )
            or provider_end
            != datetime.fromtimestamp(end_ms / 1000, tz=UTC)
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_TRADE_SAMPLE_INVALID"
            )
    for row in axes:
        assessments = row.get("source_assessments") if isinstance(row, Mapping) else None
        if (
            not isinstance(row, Mapping)
            or set(row) != _AXIS_FIELDS
            or row.get("schema_id") != AXIS_EVIDENCE_SCHEMA_ID
            or row.get("schema_version") != AXIS_EVIDENCE_SCHEMA_VERSION
            or row.get("directional_state_computed") is not False
            or row.get("missing_is_zero") is not False
            or row.get("other_retained") != (row.get("axis_id") == "OTHER")
            or row.get("status") not in {"OBSERVED", "UNKNOWN", "OTHER"}
            or row.get("admission_status")
            not in {"ADMITTED", "REJECTED", "UNKNOWN", "NOT_APPLICABLE"}
            or row.get("source_registry_digest")
            != expected_axis_registry_digest
            or not isinstance(assessments, list)
            or not isinstance(row.get("native_external_direct_admitted"), bool)
            or (
                row.get("axis_id") == "OTHER"
                and (
                    row.get("status") != "OTHER"
                    or row.get("admission_status") != "NOT_APPLICABLE"
                    or assessments
                )
            )
            or (
                row.get("axis_id") != "OTHER"
                and row.get("admission_status") == "NOT_APPLICABLE"
            )
            or _time(
                row.get("available_at"),
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
            )
            > available
            or (
                row.get("observed_at") is not None
                and _time(
                    row.get("observed_at"),
                    "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
                )
                > _time(
                    row.get("available_at"),
                    "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
                )
            )
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        try:
            verify_self_digest(row, AXIS_EVIDENCE_DIGEST_FIELD)
            for assessment in assessments:
                if (
                    not isinstance(assessment, Mapping)
                    or set(assessment) != _AXIS_SOURCE_ASSESSMENT_FIELDS
                    or assessment.get("schema_id")
                    != AXIS_SOURCE_ASSESSMENT_SCHEMA_ID
                    or assessment.get("schema_version")
                    != AXIS_SOURCE_ASSESSMENT_SCHEMA_VERSION
                    or assessment.get("axis_id") != row.get("axis_id")
                    or assessment.get("evidence_role")
                    not in {"DIRECT", "PROXY", "DERIVED", "UNKNOWN"}
                    or assessment.get("admission_status")
                    not in {"ADMITTED", "REJECTED", "UNKNOWN"}
                    or not isinstance(assessment.get("native_external"), bool)
                    or assessment.get("missing_is_zero") is not False
                ):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
                    )
                verify_self_digest(
                    assessment, AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD
                )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, V32PublicSourceCollectorError):
                raise
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            ) from exc
    reconstructed_component_observed_at: dict[str, str] = {}
    for row in datums:
        if row["status"] not in {"OBSERVED", "DERIVED"}:
            continue
        component_id = str(row["source_component_id"])
        observed = _time(
            row["observed_at"],
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        )
        previous = reconstructed_component_observed_at.get(component_id)
        if previous is None or observed > _time(
            previous,
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        ):
            reconstructed_component_observed_at[component_id] = _time_text(
                observed
            )
    expected_axes, rebuilt_axis_registry_digest = _build_axis_rows(
        component_statuses={
            component_id: row["status"]
            for component_id, row in request_by_component.items()
        },
        component_observed_at=reconstructed_component_observed_at,
        available_at=document["available_at"],
        raw_sha256=document["aggregate_raw_binding"]["semantic_digest"],
    )
    if (
        rebuilt_axis_registry_digest != expected_axis_registry_digest
        or axes != expected_axes
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_AXIS_RECONSTRUCTION_MISMATCH"
        )
    series = document.get("closed_bar_series")
    if not isinstance(series, Mapping) or set(series) != set(_TIMEFRAME_INTERVAL_MS):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    server_time_datum = datum_by_id.get("okx-server-time-ms")
    if (
        server_time_datum is None
        or server_time_datum.get("status") != "OBSERVED"
    ):
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    server_time_ms = _milliseconds(
        server_time_datum["value"],
        "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
    )
    expected_datum_ids = set(_FIXED_DATUM_CONTRACTS)
    for timeframe, rows in series.items():
        interval = _TIMEFRAME_INTERVAL_MS[timeframe]
        component_id = _TIMEFRAME_COMPONENT[timeframe]
        series_limit = request_by_component[component_id].get(
            "query", {}
        ).get("limit")
        if (
            not isinstance(series_limit, str)
            or not series_limit.isdigit()
            or int(series_limit) <= 0
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        if (
            not isinstance(rows, list)
            or len(rows) < 20
            or len(rows) > int(series_limit)
            or any(
                not isinstance(row, Mapping)
                or set(row) != _BAR_FIELDS
                or row.get("confirmed_closed") is not True
                or row.get("close_time_ms") - row.get("open_time_ms")
                != interval
                or row.get("open_time_ms") % interval != 0
                for row in rows
            )
            or any(
                current["open_time_ms"] - previous["open_time_ms"]
                != interval
                for previous, current in zip(rows, rows[1:])
            )
            or rows[-1]["close_time_ms"]
            != (server_time_ms // interval) * interval
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
            )
        try:
            for bar in rows:
                opened_price = Decimal(bar["open"])
                high = Decimal(bar["high"])
                low = Decimal(bar["low"])
                close = Decimal(bar["close"])
                volume = Decimal(bar["volume_contracts"])
                if (
                    min(opened_price, high, low, close) <= 0
                    or volume < 0
                    or high < low
                    or high < max(opened_price, close)
                    or low > min(opened_price, close)
                ):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
                    )
        except (KeyError, TypeError, InvalidOperation) as exc:
            if isinstance(exc, V32PublicSourceCollectorError):
                raise
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
            ) from exc
        component_received = _time(
            request_by_component[component_id]["response_received_at"],
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID",
        )
        for index, bar in enumerate(rows):
            opened = int(bar["open_time_ms"])
            expected_datum_ids.update(
                f"bar-{timeframe.lower()}-{opened}-{suffix}"
                for suffix in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "range-pct",
                )
            )
            if index > 0:
                expected_datum_ids.add(
                    f"bar-{timeframe.lower()}-{opened}-return-pct"
                )
            provider_close = datetime.fromtimestamp(
                int(bar["close_time_ms"]) / 1000, tz=UTC
            )
            expected_observed_at = _time_text(
                min(provider_close, component_received)
            )
            for suffix, field in (
                ("open", "open"),
                ("high", "high"),
                ("low", "low"),
                ("close", "close"),
                ("volume", "volume_contracts"),
            ):
                datum = datum_by_id.get(
                    f"bar-{timeframe.lower()}-{opened}-{suffix}"
                )
                if (
                    datum is None
                    or datum.get("value") != bar[field]
                    or datum.get("source_component_id") != component_id
                    or datum.get("provider_observed_at")
                    != _time_text(provider_close)
                    or datum.get("observed_at") != expected_observed_at
                ):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
                    )
            range_datum = datum_by_id.get(
                f"bar-{timeframe.lower()}-{opened}-range-pct"
            )
            expected_range = canonical_decimal(
                (Decimal(bar["high"]) - Decimal(bar["low"]))
                / Decimal(bar["close"])
                * Decimal("100")
            )
            if range_datum is None or range_datum.get("value") != expected_range:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
                )
            if index > 0:
                return_datum = datum_by_id.get(
                    f"bar-{timeframe.lower()}-{opened}-return-pct"
                )
                expected_return = canonical_decimal(
                    (
                        Decimal(bar["close"])
                        / Decimal(rows[index - 1]["close"])
                        - Decimal("1")
                    )
                    * Decimal("100")
                )
                if (
                    return_datum is None
                    or return_datum.get("value") != expected_return
                ):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
                    )
        rsi = datum_by_id.get(f"rsi14-{timeframe.lower()}")
        if rsi is None or rsi.get("value") != _simple_rsi14(
            [str(row["close"]) for row in rows]
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_BAR_RECONSTRUCTION_MISMATCH"
            )
    if set(datum_by_id) != expected_datum_ids:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_DATUM_SET_INVALID"
        )
    expected_members = sorted(
        [
            *[row[PIT_DATUM_DIGEST_FIELD] for row in datums],
            *[row[INFORMATION_EVENT_DIGEST_FIELD] for row in events],
            *[row[AXIS_EVIDENCE_DIGEST_FIELD] for row in axes],
        ]
    )
    if document.get("pit_member_digests") != expected_members:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_MARKET_ANALYSIS_BUNDLE_INVALID"
        )
    return supplied


def _transport_failure_details(
    exc: BaseException, *, request_started_at: str, failure_at: str
) -> tuple[dict[str, Any], bytes | None, Mapping[str, str] | None]:
    context = getattr(exc, "failure_context", None)
    context = context if isinstance(context, Mapping) else {}
    component_id = context.get("component_id")
    if component_id not in {*_COMPONENT_ORDER, "AGGREGATE_PUBLIC_BUNDLE"}:
        component_id = "AGGREGATE_PUBLIC_BUNDLE"
    path = context.get("path")
    if not isinstance(path, str) or not path.startswith("/api/v5/"):
        path = "/api/v5/public/time"
    query = context.get("query")
    try:
        query = _query(query if isinstance(query, Mapping) else {}, "INVALID")
    except V32PublicSourceCollectorError:
        query = {}
    component_started = context.get("request_started_at")
    try:
        if (
            _time(component_started, "INVALID")
            < _time(request_started_at, "INVALID")
        ):
            component_started = request_started_at
    except V32PublicSourceCollectorError:
        component_started = request_started_at
    effective_failure_at = failure_at
    context_failure_at = context.get("failure_at")
    if context_failure_at is not None:
        try:
            context_failed = _time(
                context_failure_at, "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID"
            )
            if not (
                _time(
                    component_started,
                    "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID",
                )
                <= context_failed
                <= _time(
                    failure_at, "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID"
                )
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_FAILURE_TIME_INVALID"
                )
            effective_failure_at = str(context_failure_at)
        except V32PublicSourceCollectorError:
            raise
    supplied_raw_binding = getattr(exc, "failure_raw_binding", None)
    if supplied_raw_binding is not None and not isinstance(
        supplied_raw_binding, Mapping
    ):
        supplied_raw_binding = None
    response_body = getattr(exc, "failure_response_body", None)
    if not isinstance(response_body, bytes):
        response_body = None
    response_present = context.get("response_present") is True or response_body is not None
    request_dispatched = context.get("request_dispatched") is not False
    if not request_dispatched:
        response_present = False
        response_body = None
    http_status = context.get("http_status")
    if (
        not response_present
        or isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
    ):
        http_status = None
    route_policy_id = context.get("route_policy_id")
    if (
        not isinstance(route_policy_id, str)
        or _REASON_CODE.fullmatch(route_policy_id) is None
    ):
        route_policy_id = "INJECTED_PUBLIC_TRANSPORT_NO_ROUTE_CLAIM"
    response_final_url = (
        context.get("final_url") if response_present else None
    )
    supplied_codes = context.get("failure_codes")
    codes: list[str] = ["V32_PUBLIC_SOURCE_TRANSPORT_FAILED"]
    if isinstance(supplied_codes, Sequence) and not isinstance(
        supplied_codes, (str, bytes)
    ):
        for code in supplied_codes:
            if (
                isinstance(code, str)
                and _REASON_CODE.fullmatch(code) is not None
                and code not in codes
            ):
                codes.append(code)
    if len(codes) == 1:
        if isinstance(exc, (TimeoutError,)):
            leaf = "PUBLIC_TIMEOUT"
        elif isinstance(exc, ConnectionError):
            leaf = "PUBLIC_CONNECTION_FAILURE"
        elif isinstance(exc, OSError):
            leaf = "PUBLIC_TRANSPORT_IO_FAILURE"
        else:
            leaf = "UNCLASSIFIED_STRUCTURAL_FAILURE"
        codes.append(leaf)
    return (
        {
            "component_id": component_id,
            "method": "GET",
            "path": path,
            "query": query,
            "request_started_at": component_started,
            "failure_at": effective_failure_at,
            "request_dispatched": request_dispatched,
            "response_present": response_present,
            "body_present": (
                response_body is not None or supplied_raw_binding is not None
            ),
            "http_status": http_status,
            "response_final_url": response_final_url,
            "failure_codes": codes[:8],
            "route_policy_id": route_policy_id,
        },
        response_body,
        supplied_raw_binding,
    )


class V32RawFirstOkxPublicBundleCollector:
    """Perform one durable public bundle attempt with no retry path."""

    def __init__(
        self,
        *,
        transport: V32PublicMarketBundleTransport,
        clock: Clock,
        store: LocalV32CycleSourceAdmissionStore,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._store = store

    def _clock_time(self) -> str:
        try:
            value = self._clock()
        except Exception as exc:  # clock is an injected external boundary
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_CLOCK_FAILED"
            ) from exc
        _time(value, "V32_PUBLIC_SOURCE_CLOCK_INVALID")
        return value

    def _validation_failure_time(
        self,
        *,
        attempt: Mapping[str, Any],
        capture_binding: Mapping[str, str] | None,
    ) -> tuple[str, str, bool]:
        if capture_binding is None:
            fallback_at = str(attempt["started_at"])
            fallback_source = _FAILURE_TIME_ATTEMPT_FALLBACK
        else:
            capture = self._store.read_document(
                relative_ref=str(capture_binding["relative_ref"]),
                digest_field=CAPTURE_DIGEST_FIELD,
                expected_semantic_digest=str(
                    capture_binding["semantic_digest"]
                ),
                expected_physical_sha256=str(
                    capture_binding["physical_sha256"]
                ),
            )
            verify_v32_public_source_capture(capture)
            fallback_at = str(capture["response_received_at"])
            fallback_source = _FAILURE_TIME_CAPTURE_FALLBACK
        fallback = _time(
            fallback_at, "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_TIME_INVALID"
        )
        try:
            active_at = self._clock_time()
        except V32PublicSourceCollectorError:
            return fallback_at, fallback_source, True
        if _time(
            active_at, "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_TIME_INVALID"
        ) < fallback:
            return fallback_at, fallback_source, True
        return active_at, _FAILURE_TIME_ACTIVE_CLOCK, False

    def _seal_local_validation_failure(
        self,
        *,
        qualification_id: str,
        run_id: str,
        cycle_index: int,
        attempt: Mapping[str, Any],
        failure_phase: str,
        failure_code: str,
        raw_binding: Mapping[str, str] | None,
        capture_binding: Mapping[str, str] | None,
    ) -> Mapping[str, str]:
        component_evidence_bindings: dict[str, Mapping[str, str]] = {}
        if capture_binding is not None:
            if raw_binding is None:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_WRITE_FAILED"
                )
            raw = self._store.read_raw(
                relative_ref=str(raw_binding["relative_ref"]),
                expected_sha256=str(raw_binding["physical_sha256"]),
            )
            components, _ = _component_rows(raw)
            for component_id in _COMPONENT_ORDER:
                component = components[component_id]
                if component["raw_binding"] is None:
                    relative_ref = _component_no_response_failure_ref(
                        qualification_id, component_id
                    )
                    schema_id = COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID
                    digest_field = (
                        COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD
                    )
                else:
                    relative_ref = _component_capture_ref(
                        qualification_id, component_id
                    )
                    schema_id = COMPONENT_CAPTURE_SCHEMA_ID
                    digest_field = COMPONENT_CAPTURE_DIGEST_FIELD
                _, evidence_binding = _read_document_binding(
                    store=self._store,
                    relative_ref=relative_ref,
                    schema_id=schema_id,
                    digest_field=digest_field,
                )
                component_evidence_bindings[component_id] = evidence_binding
        failed_at, failure_time_source, failure_time_uncertain = (
            self._validation_failure_time(
                attempt=attempt,
                capture_binding=capture_binding,
            )
        )
        failure = build_v32_public_source_validation_failure_v1(
            qualification_id=qualification_id,
            run_id=run_id,
            cycle_index=cycle_index,
            attempt_reservation_digest=str(
                attempt[ATTEMPT_DIGEST_FIELD]
            ),
            failure_phase=failure_phase,
            failure_code=failure_code,
            failed_at=failed_at,
            failure_time_source=failure_time_source,
            failure_time_uncertain=failure_time_uncertain,
            aggregate_raw_binding=raw_binding,
            aggregate_capture_binding=capture_binding,
            component_evidence_bindings=component_evidence_bindings,
        )
        binding = self._store.write_document(
            relative_ref=_validation_failure_ref(qualification_id),
            document=failure,
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
        )
        verify_durable_v32_public_source_validation_failure_v1(
            failure, store=self._store
        )
        return binding

    def seal_interrupted_attempt_failure(
        self,
        *,
        qualification_id: str,
        run_id: str,
        cycle_index: int,
        active_authority: Mapping[str, Any],
    ) -> Mapping[str, str]:
        """Seal a local crash prefix without repeating the public request."""

        authority_projection_digest = verify_v32_active_authority_projection(
            active_authority
        )
        attempt = loads_json_strict(
            self._store.read_raw(relative_ref=_attempt_ref(qualification_id))
        )
        try:
            verify_self_digest(attempt, ATTEMPT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_INTERRUPTED_ATTEMPT_INVALID"
            ) from exc
        if (
            attempt.get("qualification_id") != qualification_id
            or attempt.get("run_id") != run_id
            or attempt.get("cycle_index") != cycle_index
            or attempt.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
            != authority_projection_digest
            or attempt.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
            != active_authority.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
            or attempt.get("experiment_contract_digest")
            != active_authority.get("experiment_contract_digest")
            or attempt.get("attempt_number") != 1
            or attempt.get("retry_allowed") is not False
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_INTERRUPTED_ATTEMPT_INVALID"
            )
        if self._store.artifact_exists(
            relative_ref=qualification_ref(qualification_id)
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_INTERRUPTED_ATTEMPT_ALREADY_COMPLETE"
            )
        try:
            recovered = recover_durable_v32_public_source_failure_v1(
                store=self._store,
                qualification_id=qualification_id,
                active_authority=active_authority,
                expected_run_id=run_id,
                expected_cycle_index=cycle_index,
            )
        except V32PublicSourceCollectorError as exc:
            if exc.failure_code != "V32_PUBLIC_SOURCE_DURABLE_FAILURE_SET_INVALID":
                raise
        else:
            return dict(recovered["failure_evidence_binding"])

        raw_binding: Mapping[str, str] | None = None
        capture_binding: Mapping[str, str] | None = None
        raw_ref = _raw_ref(qualification_id)
        if self._store.artifact_exists(relative_ref=raw_ref):
            raw = self._store.read_raw(relative_ref=raw_ref)
            raw_digest = hashlib.sha256(raw).hexdigest()
            raw_binding = {
                "relative_ref": raw_ref,
                "semantic_digest": raw_digest,
                "physical_sha256": raw_digest,
            }
        capture_ref = _capture_ref(qualification_id)
        if self._store.artifact_exists(relative_ref=capture_ref):
            _, capture_binding = _read_document_binding(
                store=self._store,
                relative_ref=capture_ref,
                schema_id=CAPTURE_SCHEMA_ID,
                digest_field=CAPTURE_DIGEST_FIELD,
            )
            if raw_binding is None:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_INTERRUPTED_ATTEMPT_INVALID"
                )
        failure_phase = (
            "PRE_AGGREGATE_RAW_VALIDATION"
            if raw_binding is None
            else (
                "PRE_CAPTURE_AGGREGATE_VALIDATION"
                if capture_binding is None
                else "POST_CAPTURE_FORMALIZATION"
            )
        )
        return self._seal_local_validation_failure(
            qualification_id=qualification_id,
            run_id=run_id,
            cycle_index=cycle_index,
            attempt=attempt,
            failure_phase=failure_phase,
            failure_code=(
                "V32_PUBLIC_SOURCE_LOCAL_CRASH_PREFIX_FAILED_CLOSED"
            ),
            raw_binding=raw_binding,
            capture_binding=capture_binding,
        )

    def collect_and_qualify(
        self,
        *,
        qualification_id: str,
        run_id: str,
        cycle_index: int,
        active_authority: Mapping[str, Any],
    ) -> V32PublicSourceQualification:
        """Reserve, fetch once, seal raw, then derive the formal bundle."""

        attempt: Mapping[str, Any] | None = None
        raw_binding: Mapping[str, str] | None = None
        capture_binding: Mapping[str, str] | None = None
        try:
            authority_projection_digest = verify_v32_active_authority_projection(
                active_authority
            )
            governing_authority_digest = str(
                active_authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
            )
            if active_authority.get("authorized_run_id") != run_id:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_AUTHORITY_RUN_MISMATCH"
                )
            if (
                isinstance(cycle_index, bool)
                or not isinstance(cycle_index, int)
                or not 1 <= cycle_index <= 16
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_CYCLE_INVALID"
                )
            attempt_ref = _attempt_ref(qualification_id)
            if self._store.artifact_exists(relative_ref=attempt_ref):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_ATTEMPT_ALREADY_CONSUMED"
                )
            started_at = self._clock_time()
            attempt = self_digest(
                {
                    "schema_id": ATTEMPT_SCHEMA_ID,
                    "schema_version": "1.0.0",
                    "qualification_id": qualification_id,
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "started_at": started_at,
                    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: (
                        authority_projection_digest
                    ),
                    GOVERNING_AUTHORITY_DIGEST_FIELD: (
                        governing_authority_digest
                    ),
                    "experiment_contract_digest": active_authority[
                        "experiment_contract_digest"
                    ],
                    "attempt_number": 1,
                    "retry_allowed": False,
                    "single_source_collection_transaction": True,
                    "source_scope": SOURCE_SCOPE,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                    "account_data_accessed": False,
                    "order_data_accessed": False,
                },
                ATTEMPT_DIGEST_FIELD,
            )
            self._store.write_raw(
                relative_ref=attempt_ref,
                payload=canonical_bytes(attempt) + b"\n",
            )
            request_started_at = self._clock_time()
            if _time(request_started_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID") < _time(
                started_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"
                )
            try:
                raw_body_sink = _WriteOnceComponentRawSink(
                    qualification_id=qualification_id,
                    store=self._store,
                )
                raw = self._transport.fetch_once(
                    instrument_id=OKX_INSTRUMENT_ID,
                    raw_body_sink=raw_body_sink,
                )
            except (
                TimeoutError,
                ConnectionError,
                http.client.HTTPException,
                OSError,
            ) as exc:
                # Only physical I/O failures are transport failures.  Adapter
                # contract bugs and programming errors remain structural and
                # must not be laundered into ordinary coverage loss.
                failure_context = getattr(exc, "failure_context", None)
                failure_codes = (
                    failure_context.get("failure_codes")
                    if isinstance(failure_context, Mapping)
                    else None
                )
                if (
                    isinstance(failure_codes, Sequence)
                    and not isinstance(failure_codes, (str, bytes))
                    and "PUBLIC_RAW_SINK_STRUCTURAL_FAILURE" in failure_codes
                ):
                    # The raw body may already be durably sealed.  Reclassifying
                    # a subsequent capture-publication defect as a network
                    # failure would try to write the same write-once body again
                    # and hide the original local structural failure.
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_SOURCE_QUALIFICATION_FAILED"
                    ) from exc
                failure_at = self._clock_time()
                details, failure_body, supplied_failure_binding = (
                    _transport_failure_details(
                    exc,
                    request_started_at=request_started_at,
                    failure_at=failure_at,
                    )
                )
                failure_raw_binding = (
                    None
                    if supplied_failure_binding is None
                    else _raw_body_binding(
                        supplied_failure_binding,
                        "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_BINDING_INVALID",
                        expected_ref=(
                            _transport_failure_raw_ref(qualification_id)
                            if details["component_id"] == "AGGREGATE_PUBLIC_BUNDLE"
                            else _component_raw_ref(
                                qualification_id, details["component_id"]
                            )
                        ),
                    )
                )
                try:
                    if failure_raw_binding is not None:
                        durable_failure_body = self._store.read_raw(
                            relative_ref=failure_raw_binding["relative_ref"],
                            expected_sha256=failure_raw_binding["physical_sha256"],
                        )
                        if (
                            failure_body is not None
                            and durable_failure_body != failure_body
                        ):
                            raise V32PublicSourceCollectorError(
                                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_READBACK_FAILED"
                            )
                    elif failure_body is not None:
                        failure_raw_ref = (
                            _transport_failure_raw_ref(qualification_id)
                            if details["component_id"]
                            == "AGGREGATE_PUBLIC_BUNDLE"
                            else _component_raw_ref(
                                qualification_id, details["component_id"]
                            )
                        )
                        failure_sha = self._store.write_raw(
                            relative_ref=failure_raw_ref,
                            payload=failure_body,
                        )["physical_sha256"]
                        if (
                            self._store.read_raw(
                                relative_ref=failure_raw_ref,
                                expected_sha256=failure_sha,
                            )
                            != failure_body
                        ):
                            raise V32PublicSourceCollectorError(
                                "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_RAW_READBACK_FAILED"
                            )
                        failure_raw_binding = {
                            "relative_ref": failure_raw_ref,
                            "semantic_digest": failure_sha,
                            "physical_sha256": failure_sha,
                        }
                    failure = build_v32_public_source_transport_failure_v1(
                        qualification_id=qualification_id,
                        run_id=run_id,
                        cycle_index=cycle_index,
                        attempt_reservation_digest=attempt[
                            ATTEMPT_DIGEST_FIELD
                        ],
                        failure_raw_binding=failure_raw_binding,
                        **details,
                    )
                    verify_v32_public_source_transport_failure_v1(failure)
                    failure_receipt_binding = self._store.write_document(
                        relative_ref=_transport_failure_ref(qualification_id),
                        document=failure,
                        digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
                    )
                    verify_durable_v32_public_source_transport_failure_v1(
                        failure, store=self._store
                    )
                except (OSError, TypeError, ValueError):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_SOURCE_TRANSPORT_FAILURE_WRITE_FAILED"
                    ) from None
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_TRANSPORT_FAILED",
                    failure_context={
                        "failure_codes": details["failure_codes"]
                    },
                    failure_evidence_binding=failure_receipt_binding,
                ) from None
            if not isinstance(raw, bytes) or not raw:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_TRANSPORT_BYTES_INVALID"
                )
            raw_ref = _raw_ref(qualification_id)
            raw_physical = self._store.write_raw(
                relative_ref=raw_ref, payload=raw
            )["physical_sha256"]
            readback = self._store.read_raw(
                relative_ref=raw_ref, expected_sha256=raw_physical
            )
            if readback != raw:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_RAW_READBACK_FAILED"
                )
            raw_binding = {
                "relative_ref": raw_ref,
                "semantic_digest": raw_physical,
                "physical_sha256": raw_physical,
            }
            response_received_at = self._clock_time()
            if len(raw) > MAX_RAW_BUNDLE_BYTES:
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_RAW_BUNDLE_TOO_LARGE"
                )
            components, _ = _component_rows(raw)
            outer_started = _time(
                request_started_at, "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID"
            )
            outer_received = _time(
                response_received_at, "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID"
            )
            if any(
                _time(
                    row["request_started_at"],
                    "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID",
                )
                < outer_started
                or _time(
                    row["response_received_at"],
                    "V32_PUBLIC_SOURCE_COMPONENT_TIME_INVALID",
                )
                > outer_received
                for row in components.values()
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_COMPONENT_OUTSIDE_TRANSACTION"
                )
            component_raw_bindings: dict[
                str, Mapping[str, str] | None
            ] = {}
            for component_id in _COMPONENT_ORDER:
                component = components[component_id]
                component_raw_bindings[component_id] = (
                    _verify_component_capture_against_aggregate_row(
                        store=self._store,
                        qualification_id=qualification_id,
                        component=component,
                        transaction_started_at=request_started_at,
                        transaction_received_at=response_received_at,
                    )
                )
            capture = build_v32_public_source_capture(
                qualification_id=qualification_id,
                run_id=run_id,
                cycle_index=cycle_index,
                attempt_id=f"{qualification_id}:attempt:1",
                request_id=f"{qualification_id}:public-market-bundle",
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                raw_response_binding=raw_binding,
            )
            capture_binding = self._store.write_document(
                relative_ref=_capture_ref(qualification_id),
                document=capture,
                digest_field=CAPTURE_DIGEST_FIELD,
            )
            try:
                derived = _derive_bundle(
                    raw=raw,
                    available_at=response_received_at,
                    aggregate_raw_binding=raw_binding,
                    component_raw_bindings=component_raw_bindings,
                )
                analysis_bundle = build_v32_public_market_analysis_bundle(
                    qualification_id=qualification_id,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    capture_digest=capture[CAPTURE_DIGEST_FIELD],
                    aggregate_raw_binding=raw_binding,
                    component_raw_bindings=component_raw_bindings,
                    derived=derived,
                )
                verify_v32_public_market_analysis_bundle(analysis_bundle)
            except (KeyError, TypeError, ValueError) as caught:
                exc = (
                    caught
                    if isinstance(caught, V32PublicSourceCollectorError)
                    else V32PublicSourceCollectorError(
                        "V32_PUBLIC_SOURCE_ANALYSIS_BUILD_OR_VERIFY_FAILED"
                    )
                )
                try:
                    (
                        failed_at,
                        failure_time_source,
                        failure_time_uncertain,
                    ) = self._validation_failure_time(
                        attempt=attempt,
                        capture_binding=capture_binding,
                    )
                    component_evidence_bindings = {}
                    for component_id in _COMPONENT_ORDER:
                        component = components[component_id]
                        if component["raw_binding"] is None:
                            relative_ref = (
                                _component_no_response_failure_ref(
                                    qualification_id, component_id
                                )
                            )
                            schema_id = (
                                COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID
                            )
                            digest_field = (
                                COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD
                            )
                        else:
                            relative_ref = _component_capture_ref(
                                qualification_id, component_id
                            )
                            schema_id = COMPONENT_CAPTURE_SCHEMA_ID
                            digest_field = COMPONENT_CAPTURE_DIGEST_FIELD
                        _, component_evidence_binding = (
                            _read_document_binding(
                                store=self._store,
                                relative_ref=relative_ref,
                                schema_id=schema_id,
                                digest_field=digest_field,
                            )
                        )
                        component_evidence_bindings[component_id] = (
                            component_evidence_binding
                        )
                    validation_failure = (
                        build_v32_public_source_validation_failure_v1(
                            qualification_id=qualification_id,
                            run_id=run_id,
                            cycle_index=cycle_index,
                            attempt_reservation_digest=attempt[
                                ATTEMPT_DIGEST_FIELD
                            ],
                            failure_phase=(
                                "POST_CAPTURE_ANALYSIS_VALIDATION"
                            ),
                            failure_code=exc.failure_code,
                            failed_at=failed_at,
                            failure_time_source=failure_time_source,
                            failure_time_uncertain=(
                                failure_time_uncertain
                            ),
                            aggregate_raw_binding=raw_binding,
                            aggregate_capture_binding=capture_binding,
                            component_evidence_bindings=(
                                component_evidence_bindings
                            ),
                        )
                    )
                    validation_failure_binding = self._store.write_document(
                        relative_ref=_validation_failure_ref(
                            qualification_id
                        ),
                        document=validation_failure,
                        digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
                    )
                    if (
                        assess_current_v32_public_source_validation_failure_reproduction_v1(
                            validation_failure,
                            store=self._store,
                        )
                        != "REPRODUCED_EXACT_FAILURE"
                    ):
                        raise V32PublicSourceCollectorError(
                            "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_WRITE_FAILED"
                        )
                except (OSError, TypeError, ValueError):
                    raise V32PublicSourceCollectorError(
                        "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_WRITE_FAILED",
                        failure_evidence_binding=capture_binding,
                    ) from None
                raise V32PublicSourceCollectorError(
                    exc.failure_code,
                    failure_context={
                        "failure_phase": (
                            "POST_CAPTURE_LOCAL_SEMANTIC_VALIDATION"
                        )
                    },
                    failure_evidence_binding=validation_failure_binding,
                ) from None
            analysis_bundle_binding = self._store.write_document(
                relative_ref=_analysis_bundle_ref(qualification_id),
                document=analysis_bundle,
                digest_field=ANALYSIS_BUNDLE_DIGEST_FIELD,
            )
            snapshot = build_v32_public_market_snapshot(
                qualification_id=qualification_id,
                run_id=run_id,
                cycle_index=cycle_index,
                capture_attempt_digest=capture[CAPTURE_DIGEST_FIELD],
                as_of=derived["as_of"],
                available_at=response_received_at,
                closed_bar_as_of=derived["closed_bar_as_of"],
                open_interest_datum_digest=derived["open_interest_datum"][
                    PIT_DATUM_DIGEST_FIELD
                ],
                open_interest_status=derived["open_interest_datum"]["status"],
            )
            snapshot_binding = self._store.write_document(
                relative_ref=_snapshot_ref(qualification_id),
                document=snapshot,
                digest_field=SNAPSHOT_DIGEST_FIELD,
            )
            pit = build_v32_pit_evidence_registry(
                run_id=run_id,
                cycle_index=cycle_index,
                as_of=response_received_at,
                members=sorted(
                    [
                        *derived["pit_member_digests"],
                        analysis_bundle[ANALYSIS_BUNDLE_DIGEST_FIELD],
                    ]
                ),
                upstream_snapshot_digest=snapshot[SNAPSHOT_DIGEST_FIELD],
                capture_digest=capture[CAPTURE_DIGEST_FIELD],
            )
            pit_binding = self._store.write_document(
                relative_ref=_pit_ref(qualification_id),
                document=pit,
                digest_field=PIT_REGISTRY_DIGEST_FIELD,
            )
            completed_at = self._clock_time()
            decision_time = self._clock_time()
            chronology = [
                _time(active_authority["recorded_at"], "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
                _time(started_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
                _time(request_started_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
                _time(response_received_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
                _time(completed_at, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
                _time(decision_time, "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"),
            ]
            if not (
                chronology[0] < chronology[1]
                and chronology[1] <= chronology[2] <= chronology[3]
                and chronology[3] <= chronology[4] <= chronology[5]
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_CHRONOLOGY_INVALID"
                )
            if (
                chronology[5] - chronology[3]
                > timedelta(seconds=MAX_SOURCE_AGE_SECONDS)
                or chronology[5]
                - _time(
                    derived["closed_bar_as_of"],
                    "V32_PUBLIC_SOURCE_CLOSED_BAR_TIME_INVALID",
                )
                > timedelta(seconds=MAX_CLOSED_BAR_AGE_SECONDS)
            ):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_FRESHNESS_INVALID"
                )
            qualification = build_v32_formal_source_qualification(
                qualification_id=qualification_id,
                run_id=run_id,
                cycle_index=cycle_index,
                started_at=started_at,
                completed_at=completed_at,
                decision_time=decision_time,
                active_authority_projection_digest=(
                    authority_projection_digest
                ),
                governing_authority_digest=governing_authority_digest,
                active_authority_recorded_at=active_authority["recorded_at"],
                experiment_contract_digest=active_authority[
                    "experiment_contract_digest"
                ],
                capture_binding=capture_binding,
                snapshot_binding=snapshot_binding,
                pit_registry_binding=pit_binding,
            )
            qualification_binding = self._store.write_document(
                relative_ref=qualification_ref(qualification_id),
                document=qualification,
                digest_field=QUALIFICATION_DIGEST_FIELD,
            )
            return V32PublicSourceQualification(
                qualification_id=qualification_id,
                run_id=run_id,
                cycle_index=cycle_index,
                raw_binding=raw_binding,
                source_capture=capture,
                source_capture_binding=capture_binding,
                market_snapshot=snapshot,
                market_snapshot_binding=snapshot_binding,
                pit_registry=pit,
                pit_registry_binding=pit_binding,
                formal_qualification=qualification,
                formal_qualification_binding=qualification_binding,
                public_market_analysis_bundle=analysis_bundle,
                public_market_analysis_bundle_binding=analysis_bundle_binding,
                axis_source_evidence=tuple(derived["axis_source_evidence"]),
                open_interest_datum=derived["open_interest_datum"],
            )
        except V32PublicSourceCollectorError as exc:
            if (
                (
                    exc.failure_evidence_binding is not None
                    and exc.failure_evidence_binding.get("schema_id")
                    != CAPTURE_SCHEMA_ID
                )
                or attempt is None
            ):
                raise
            failure_phase = (
                "PRE_AGGREGATE_RAW_VALIDATION"
                if raw_binding is None
                else (
                    "PRE_CAPTURE_AGGREGATE_VALIDATION"
                    if capture_binding is None
                    else "POST_CAPTURE_FORMALIZATION"
                )
            )
            try:
                terminal_binding = self._seal_local_validation_failure(
                    qualification_id=qualification_id,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    attempt=attempt,
                    failure_phase=failure_phase,
                    failure_code=exc.failure_code,
                    raw_binding=raw_binding,
                    capture_binding=capture_binding,
                )
            except (OSError, TypeError, ValueError):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_WRITE_FAILED"
                ) from None
            raise V32PublicSourceCollectorError(
                exc.failure_code,
                failure_context={"failure_phase": failure_phase},
                failure_evidence_binding=terminal_binding,
            ) from None
        except (KeyError, TypeError, ValueError) as caught:
            exc = V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_QUALIFICATION_FAILED"
            )
            if attempt is None:
                raise exc from caught
            failure_phase = (
                "PRE_AGGREGATE_RAW_VALIDATION"
                if raw_binding is None
                else (
                    "PRE_CAPTURE_AGGREGATE_VALIDATION"
                    if capture_binding is None
                    else "POST_CAPTURE_FORMALIZATION"
                )
            )
            try:
                terminal_binding = self._seal_local_validation_failure(
                    qualification_id=qualification_id,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    attempt=attempt,
                    failure_phase=failure_phase,
                    failure_code=exc.failure_code,
                    raw_binding=raw_binding,
                    capture_binding=capture_binding,
                )
            except (OSError, TypeError, ValueError):
                raise V32PublicSourceCollectorError(
                    "V32_PUBLIC_SOURCE_VALIDATION_FAILURE_WRITE_FAILED"
                ) from None
            raise V32PublicSourceCollectorError(
                exc.failure_code,
                failure_context={"failure_phase": failure_phase},
                failure_evidence_binding=terminal_binding,
            ) from None


def verify_durable_v32_public_source_qualification(
    *,
    store: LocalV32CycleSourceAdmissionStore,
    qualification_id: str,
    active_authority: Mapping[str, Any],
) -> V32PublicSourceQualification:
    """Replay raw bytes and reconstruct every derived typed artifact."""

    try:
        authority_projection_digest = verify_v32_active_authority_projection(
            active_authority
        )
        governing_authority_digest = str(
            active_authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
        )
        attempt_raw = store.read_raw(relative_ref=_attempt_ref(qualification_id))
        attempt = loads_json_strict(attempt_raw)
        verify_self_digest(attempt, ATTEMPT_DIGEST_FIELD)
        if (
            attempt.get("schema_id") != ATTEMPT_SCHEMA_ID
            or attempt.get("qualification_id") != qualification_id
            or attempt.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
            != authority_projection_digest
            or attempt.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
            != governing_authority_digest
            or attempt.get("attempt_number") != 1
            or attempt.get("retry_allowed") is not False
            or attempt.get("single_source_collection_transaction") is not True
            or attempt.get("source_scope") != SOURCE_SCOPE
            or attempt.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or attempt.get("executable") is not False
            or attempt.get("account_data_accessed") is not False
            or attempt.get("order_data_accessed") is not False
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_ATTEMPT_REPLAY_INVALID"
            )
        qualification = store.read_document(
            relative_ref=qualification_ref(qualification_id),
            digest_field=QUALIFICATION_DIGEST_FIELD,
        )
        verify_v32_formal_source_qualification(qualification)
        if (
            qualification.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
            != authority_projection_digest
            or qualification.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
            != governing_authority_digest
            or qualification.get("run_id") != active_authority.get("authorized_run_id")
            or qualification.get("qualification_id") != qualification_id
            or qualification.get("attempt_count") != 1
            or qualification.get("retry_allowed") is not False
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_QUALIFICATION_REPLAY_INVALID"
            )
        capture_binding = dict(qualification["capture_binding"])
        capture = store.read_document(
            relative_ref=capture_binding["relative_ref"],
            digest_field=CAPTURE_DIGEST_FIELD,
            expected_semantic_digest=capture_binding["semantic_digest"],
            expected_physical_sha256=capture_binding["physical_sha256"],
        )
        verify_v32_public_source_capture(capture)
        snapshot_binding = dict(qualification["snapshot_binding"])
        snapshot = store.read_document(
            relative_ref=snapshot_binding["relative_ref"],
            digest_field=SNAPSHOT_DIGEST_FIELD,
            expected_semantic_digest=snapshot_binding["semantic_digest"],
            expected_physical_sha256=snapshot_binding["physical_sha256"],
        )
        verify_v32_public_market_snapshot(snapshot)
        pit_binding = dict(qualification["pit_registry_binding"])
        pit = store.read_document(
            relative_ref=pit_binding["relative_ref"],
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
            expected_semantic_digest=pit_binding["semantic_digest"],
            expected_physical_sha256=pit_binding["physical_sha256"],
        )
        verify_v32_pit_evidence_registry(pit)
        raw_binding = dict(capture["raw_response_binding"])
        raw = store.read_raw(
            relative_ref=raw_binding["relative_ref"],
            expected_sha256=raw_binding["physical_sha256"],
        )
        components, _ = _component_rows(raw)
        component_raw_bindings: dict[
            str, Mapping[str, str] | None
        ] = {}
        for component_id in _COMPONENT_ORDER:
            component = components[component_id]
            component_raw_bindings[component_id] = (
                _verify_component_capture_against_aggregate_row(
                    store=store,
                    qualification_id=qualification_id,
                    component=component,
                    transaction_started_at=capture["request_started_at"],
                    transaction_received_at=capture[
                        "response_received_at"
                    ],
                )
            )
        analysis_bundle = store.read_document(
            relative_ref=_analysis_bundle_ref(qualification_id),
            digest_field=ANALYSIS_BUNDLE_DIGEST_FIELD,
        )
        verify_v32_public_market_analysis_bundle(analysis_bundle)
        analysis_bundle_binding = store.artifact_binding(
            relative_ref=_analysis_bundle_ref(qualification_id),
            digest_field=ANALYSIS_BUNDLE_DIGEST_FIELD,
            expected_semantic_digest=analysis_bundle[
                ANALYSIS_BUNDLE_DIGEST_FIELD
            ],
        )
        if (
            hashlib.sha256(raw).hexdigest() != raw_binding["semantic_digest"]
            or capture.get("qualification_id") != qualification_id
            or capture.get("run_id") != qualification.get("run_id")
            or capture.get("cycle_index") != qualification.get("cycle_index")
            or snapshot.get("capture_attempt_digest")
            != capture.get(CAPTURE_DIGEST_FIELD)
            or pit.get("upstream_semantic_digest")
            != snapshot.get(SNAPSHOT_DIGEST_FIELD)
            or pit.get("full_verification_receipt_digest")
            != capture.get(CAPTURE_DIGEST_FIELD)
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_REPLAY_BINDING_INVALID"
            )
        derived = _derive_bundle(
            raw=raw,
            available_at=capture["response_received_at"],
            aggregate_raw_binding=raw_binding,
            component_raw_bindings=component_raw_bindings,
        )
        rebuilt_analysis_bundle = build_v32_public_market_analysis_bundle(
            qualification_id=qualification_id,
            run_id=qualification["run_id"],
            cycle_index=qualification["cycle_index"],
            capture_digest=capture[CAPTURE_DIGEST_FIELD],
            aggregate_raw_binding=raw_binding,
            component_raw_bindings=component_raw_bindings,
            derived=derived,
        )
        rebuilt_snapshot = build_v32_public_market_snapshot(
            qualification_id=qualification_id,
            run_id=qualification["run_id"],
            cycle_index=qualification["cycle_index"],
            capture_attempt_digest=capture[CAPTURE_DIGEST_FIELD],
            as_of=derived["as_of"],
            available_at=capture["response_received_at"],
            closed_bar_as_of=derived["closed_bar_as_of"],
            open_interest_datum_digest=derived["open_interest_datum"][
                PIT_DATUM_DIGEST_FIELD
            ],
            open_interest_status=derived["open_interest_datum"]["status"],
        )
        rebuilt_pit = build_v32_pit_evidence_registry(
            run_id=qualification["run_id"],
            cycle_index=qualification["cycle_index"],
            as_of=capture["response_received_at"],
            members=sorted(
                [
                    *derived["pit_member_digests"],
                    analysis_bundle[ANALYSIS_BUNDLE_DIGEST_FIELD],
                ]
            ),
            upstream_snapshot_digest=snapshot[SNAPSHOT_DIGEST_FIELD],
            capture_digest=capture[CAPTURE_DIGEST_FIELD],
        )
        if (
            snapshot != rebuilt_snapshot
            or analysis_bundle != rebuilt_analysis_bundle
            or pit != rebuilt_pit
        ):
            raise V32PublicSourceCollectorError(
                "V32_PUBLIC_SOURCE_DERIVATION_REPLAY_MISMATCH"
            )
        qualification_binding = store.artifact_binding(
            relative_ref=qualification_ref(qualification_id),
            digest_field=QUALIFICATION_DIGEST_FIELD,
            expected_semantic_digest=qualification[QUALIFICATION_DIGEST_FIELD],
        )
        return V32PublicSourceQualification(
            qualification_id=qualification_id,
            run_id=str(qualification["run_id"]),
            cycle_index=int(qualification["cycle_index"]),
            raw_binding=raw_binding,
            source_capture=capture,
            source_capture_binding=capture_binding,
            market_snapshot=snapshot,
            market_snapshot_binding=snapshot_binding,
            pit_registry=pit,
            pit_registry_binding=pit_binding,
            formal_qualification=qualification,
            formal_qualification_binding=qualification_binding,
            public_market_analysis_bundle=analysis_bundle,
            public_market_analysis_bundle_binding=analysis_bundle_binding,
            axis_source_evidence=tuple(derived["axis_source_evidence"]),
            open_interest_datum=derived["open_interest_datum"],
        )
    except V32PublicSourceCollectorError:
        raise
    except (V32CycleSourceAdmissionStoreError, KeyError, TypeError, ValueError) as exc:
        raise V32PublicSourceCollectorError(
            "V32_PUBLIC_SOURCE_DURABLE_REPLAY_FAILED"
        ) from exc


__all__ = [
    "ANALYSIS_BUNDLE_DIGEST_FIELD",
    "ANALYSIS_BUNDLE_SCHEMA_ID",
    "ANALYSIS_BUNDLE_SCHEMA_VERSION",
    "AXIS_EVIDENCE_DIGEST_FIELD",
    "ATTEMPT_DIGEST_FIELD",
    "COMPONENT_CAPTURE_DIGEST_FIELD",
    "COMPONENT_CAPTURE_SCHEMA_ID",
    "COMPONENT_CAPTURE_SCHEMA_VERSION",
    "COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD",
    "COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID",
    "COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_VERSION",
    "MAX_PUBLIC_COMPONENT_CAPTURE_BYTES",
    "OKX_INSTRUMENT_ID",
    "PIT_DATUM_DIGEST_FIELD",
    "PIT_DATUM_SCHEMA_VERSION",
    "RAW_BUNDLE_SCHEMA_ID",
    "TRANSPORT_FAILURE_DIGEST_FIELD",
    "TRANSPORT_FAILURE_SCHEMA_ID",
    "TRANSPORT_FAILURE_SCHEMA_VERSION",
    "VALIDATION_FAILURE_DIGEST_FIELD",
    "VALIDATION_FAILURE_SCHEMA_ID",
    "VALIDATION_FAILURE_SCHEMA_VERSION",
    "V32PublicComponentRawSink",
    "V32PublicComponentRawSinkError",
    "V32PublicMarketBundleTransport",
    "V32PublicSourceCollectorError",
    "V32PublicSourceQualification",
    "V32RawFirstOkxPublicBundleCollector",
    "assess_current_v32_public_source_validation_failure_reproduction_v1",
    "build_v32_public_market_analysis_bundle",
    "build_v32_public_component_capture_v1",
    "build_v32_public_component_no_response_failure_v1",
    "build_v32_public_source_transport_failure_v1",
    "build_v32_public_source_validation_failure_v1",
    "recover_durable_v32_public_source_failure_v1",
    "verify_durable_v32_public_source_transport_failure_v1",
    "verify_durable_v32_public_component_no_response_failure_v1",
    "verify_durable_v32_public_source_qualification",
    "verify_durable_v32_public_source_validation_failure_v1",
    "verify_v32_public_market_analysis_bundle",
    "verify_v32_public_component_capture_v1",
    "verify_v32_public_component_no_response_failure_v1",
    "verify_v32_public_source_transport_failure_v1",
    "verify_v32_public_source_validation_failure_v1",
]
