from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import copy
import http.client
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    loads_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    build_v32_active_authority_projection,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADERS_DIGEST,
)
from trade_system.theory_paper_v2.domain.v31_sentiment_native_projection_v2 import (
    build_v31_native_sentiment_source_registry,
    verify_v31_native_sentiment_source_registry,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_public_source_collector as collector_module,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_bundle_transport import (
    V32OkxPublicBundleTransport,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    ANALYSIS_BUNDLE_SCHEMA_VERSION,
    AXIS_EVIDENCE_DIGEST_FIELD,
    AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD,
    COMPONENT_CAPTURE_DIGEST_FIELD,
    COMPONENT_CAPTURE_SCHEMA_VERSION,
    COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
    COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID,
    COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_VERSION,
    RAW_BUNDLE_SCHEMA_ID,
    RAW_BUNDLE_SCHEMA_VERSION,
    TRANSPORT_FAILURE_DIGEST_FIELD,
    TRANSPORT_FAILURE_SCHEMA_VERSION,
    PIT_DATUM_DIGEST_FIELD,
    PIT_DATUM_SCHEMA_VERSION,
    VALIDATION_FAILURE_DIGEST_FIELD,
    V32PublicSourceCollectorError,
    V32RawFirstOkxPublicBundleCollector,
    assess_current_v32_public_source_validation_failure_reproduction_v1,
    recover_durable_v32_public_source_failure_v1,
    verify_durable_v32_public_source_qualification,
    verify_durable_v32_public_source_validation_failure_v1,
    verify_durable_v32_public_source_transport_failure_v1,
    verify_v32_public_component_capture_v1,
    verify_v32_public_component_no_response_failure_v1,
    verify_v32_public_market_analysis_bundle,
    verify_v32_public_source_transport_failure_v1,
    verify_v32_public_source_validation_failure_v1,
)


RUN_ID = "run:v32:public-source-collector-unit"
CONTRACT_DIGEST = "c" * 64
BASE = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
SERVER_MS = int((BASE + timedelta(seconds=3)).timestamp() * 1000)


def ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def okx_body(data: list[object]) -> str:
    return canonical_bytes({"code": "0", "msg": "", "data": data}).decode()


def candle_rows(interval_ms: int) -> list[list[str]]:
    bucket = (SERVER_MS // interval_ms) * interval_ms
    rows: list[list[str]] = []
    for index in range(20):
        opened = bucket - ((20 - index) * interval_ms)
        close = 60_000 + index
        rows.append(
            [
                str(opened),
                str(close - 1),
                str(close + 3),
                str(close - 4),
                str(close),
                str(100 + index),
                str(100 + index),
                str((100 + index) * close),
                "1",
            ]
        )
    return rows


def component(
    component_id: str,
    path: str,
    query: dict[str, str],
    body: str | None,
    *,
    error_code: str | None = None,
) -> dict:
    observed = body is not None
    return {
        "component_id": component_id,
        "method": "GET",
        "path": path,
        "query": query,
        "status": "OBSERVED" if observed else "UNKNOWN",
        "http_status": 200 if observed else None,
        "body_utf8": body,
        "error_code": None if observed else error_code,
        "request_started_at": ts(BASE + timedelta(seconds=2)),
        "response_received_at": ts(BASE + timedelta(seconds=3)),
        "attempt_number": 1,
        "retry_allowed": False,
        "raw_binding": None,
        "failure_evidence_binding": None,
    }


def raw_bundle(*, unknown_optional: bool = False) -> dict:
    bucket = {
        label: (SERVER_MS // interval) * interval
        for label, interval in {
            "15M": 900_000,
            "1H": 3_600_000,
            "4H": 14_400_000,
            "1D": 86_400_000,
        }.items()
    }
    optional = None if unknown_optional else "OBSERVED"
    components = [
        component(
            "SERVER_TIME",
            "/api/v5/public/time",
            {},
            okx_body([{"ts": str(SERVER_MS)}]),
        ),
        component(
            "INSTRUMENT",
            "/api/v5/public/instruments",
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
            okx_body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "state": "live",
                        "ctVal": "0.01",
                        "ctValCcy": "BTC",
                        "ctMult": "1",
                        "lotSz": "0.01",
                        "minSz": "0.01",
                        "tickSz": "0.1",
                        "ctType": "linear",
                        "settleCcy": "USDT",
                    }
                ]
            ),
        ),
        component(
            "TICKER",
            "/api/v5/market/ticker",
            {"instId": "BTC-USDT-SWAP"},
            okx_body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "last": "60000",
                        "bidPx": "59999",
                        "askPx": "60001",
                        "vol24h": "1000",
                        "volCcy24h": "200",
                        "ts": str(SERVER_MS - 1000),
                    }
                ]
            ),
        ),
        component(
            "MARK_PRICE",
            "/api/v5/public/mark-price",
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
            okx_body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "markPx": "60000",
                        "ts": str(SERVER_MS - 1000),
                    }
                ]
            ),
        ),
        component(
            "CLOSED_CANDLES_15M",
            "/api/v5/market/history-candles",
            {
                "after": str(bucket["15M"]),
                "bar": "15m",
                "instId": "BTC-USDT-SWAP",
                "limit": "96",
            },
            okx_body(candle_rows(900_000)),
        ),
        component(
            "CLOSED_CANDLES_1H",
            "/api/v5/market/history-candles",
            {
                "after": str(bucket["1H"]),
                "bar": "1H",
                "instId": "BTC-USDT-SWAP",
                "limit": "168",
            },
            okx_body(candle_rows(3_600_000)),
        ),
        component(
            "CLOSED_CANDLES_4H",
            "/api/v5/market/history-candles",
            {
                "after": str(bucket["4H"]),
                "bar": "4H",
                "instId": "BTC-USDT-SWAP",
                "limit": "90",
            },
            okx_body(candle_rows(14_400_000)),
        ),
        component(
            "CLOSED_CANDLES_1D",
            "/api/v5/market/history-candles",
            {
                "after": str(bucket["1D"]),
                "bar": "1Dutc",
                "instId": "BTC-USDT-SWAP",
                "limit": "60",
            },
            okx_body(candle_rows(86_400_000)),
        ),
        component(
            "OPEN_INTEREST",
            "/api/v5/public/open-interest",
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
            (
                okx_body(
                    [
                        {
                            "instId": "BTC-USDT-SWAP",
                            "oiCcy": "25000",
                            "ts": str(SERVER_MS - 1000),
                        }
                    ]
                )
                if optional
                else None
            ),
            error_code=None if optional else "PUBLIC_TRANSPORT_IO_FAILURE",
        ),
        component(
            "FUNDING_RATE",
            "/api/v5/public/funding-rate",
            {"instId": "BTC-USDT-SWAP"},
            (
                okx_body(
                    [
                        {
                            "instId": "BTC-USDT-SWAP",
                            "fundingRate": "-0.0001",
                            "prevFundingTime": str(SERVER_MS - 3_600_000),
                            "fundingTime": str(SERVER_MS + 3_600_000),
                            "nextFundingTime": str(SERVER_MS + 7_200_000),
                            "ts": str(SERVER_MS - 1000),
                        }
                    ]
                )
                if optional
                else None
            ),
            error_code=None if optional else "PUBLIC_TRANSPORT_IO_FAILURE",
        ),
        component(
            "ORDER_BOOK",
            "/api/v5/market/books",
            {"instId": "BTC-USDT-SWAP", "sz": "50"},
            (
                okx_body(
                    [
                        {
                            "bids": [
                                ["59999", "10", "0", "1"],
                                ["59998", "9", "0", "1"],
                                ["59997", "8", "0", "1"],
                                ["59996", "7", "0", "1"],
                                ["59995", "6", "0", "1"],
                            ],
                            "asks": [
                                ["60001", "8", "0", "1"],
                                ["60002", "9", "0", "1"],
                                ["60003", "10", "0", "1"],
                                ["60004", "11", "0", "1"],
                                ["60005", "12", "0", "1"],
                            ],
                            "ts": str(SERVER_MS - 1000),
                        }
                    ]
                )
                if optional
                else None
            ),
            error_code=None if optional else "PUBLIC_TRANSPORT_IO_FAILURE",
        ),
        component(
            "RECENT_TRADES",
            "/api/v5/market/trades",
            {"instId": "BTC-USDT-SWAP", "limit": "100"},
            (
                okx_body(
                    [
                        {
                            "instId": "BTC-USDT-SWAP",
                            "tradeId": "fixture-trade-1",
                            "px": "60000",
                            "side": "buy",
                            "sz": "2",
                            "ts": str(SERVER_MS - 1000),
                        },
                        {
                            "instId": "BTC-USDT-SWAP",
                            "tradeId": "fixture-trade-2",
                            "px": "60001",
                            "side": "sell",
                            "sz": "1",
                            "ts": str(SERVER_MS - 1000),
                        },
                    ]
                )
                if optional
                else None
            ),
            error_code=None if optional else "PUBLIC_TRANSPORT_IO_FAILURE",
        ),
    ]
    return {
        "schema_id": RAW_BUNDLE_SCHEMA_ID,
        "schema_version": RAW_BUNDLE_SCHEMA_VERSION,
        "base_url": "https://openapi.okx.com",
        "venue": "OKX",
        "instrument_id": "BTC-USDT-SWAP",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "components": components,
    }


def resign_analysis(document: dict) -> dict:
    document["pit_member_digests"] = sorted(
        [row[PIT_DATUM_DIGEST_FIELD] for row in document["datums"]]
        + [
            row["public_source_event_digest"]
            for row in document["information_events"]
        ]
        + [
            row[AXIS_EVIDENCE_DIGEST_FIELD]
            for row in document["axis_source_evidence"]
        ]
    )
    return self_digest(document, ANALYSIS_BUNDLE_DIGEST_FIELD)


class SequenceClock:
    def __init__(self) -> None:
        self.values = iter(
            [
                ts(BASE + timedelta(seconds=1)),
                ts(BASE + timedelta(seconds=2)),
                ts(BASE + timedelta(seconds=4)),
                ts(BASE + timedelta(seconds=5)),
                ts(BASE + timedelta(seconds=6)),
            ]
        )

    def __call__(self) -> str:
        return next(self.values)


class DeadAfterFirstClock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls == 1:
            return ts(BASE + timedelta(seconds=1))
        raise OSError("injected permanent clock failure")


class BundleTransport:
    def __init__(self, bundle: dict | None, *, fail: bool = False) -> None:
        self.bundle = bundle
        self.fail = fail
        self.calls = 0

    def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
        self.calls += 1
        if instrument_id != "BTC-USDT-SWAP":
            raise AssertionError("instrument drift")
        if self.fail:
            raise TimeoutError("fixture transport failure")
        assert self.bundle is not None
        bundle = copy.deepcopy(self.bundle)
        for component in bundle["components"]:
            if component["body_utf8"] is None:
                component["raw_binding"] = None
                component["failure_evidence_binding"] = dict(
                    raw_body_sink.seal_component_no_response_failure(
                        component_id=component["component_id"],
                        method=component["method"],
                        path=component["path"],
                        query=component["query"],
                        request_started_at=component["request_started_at"],
                        failure_at=component["response_received_at"],
                        response_present=False,
                        body_present=False,
                        http_status=None,
                        response_final_url=None,
                        failure_codes=[
                            f"V32_OKX_TRANSPORT_{component['component_id']}_FAILED",
                            component["error_code"],
                        ],
                        route_policy_id=(
                            "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
                        ),
                        attempt_number=1,
                        retry_allowed=False,
                    )
                )
                continue
            component["raw_binding"] = dict(
                raw_body_sink.seal_component_capture(
                    component_id=component["component_id"],
                    payload=component["body_utf8"].encode("utf-8"),
                    method=component["method"],
                    path=component["path"],
                    query=component["query"],
                    http_status=component["http_status"],
                    final_url=component_final_url(component),
                    request_started_at=component["request_started_at"],
                    response_received_at=component["response_received_at"],
                    capture_completed_at=component["response_received_at"],
                    route_policy_id=(
                        "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
                    ),
                )
            )
            component["failure_evidence_binding"] = None
        return canonical_bytes(bundle)


class TypedBodyFailureTransport:
    def __init__(self, failure_body: bytes = b'{"code":"500","msg":"unavailable"}') -> None:
        self.calls = 0
        self.failure_body = failure_body

    def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
        self.calls += 1
        failure_body = self.failure_body
        failure_binding = raw_body_sink.seal_component_capture(
            component_id="SERVER_TIME",
            payload=failure_body,
            method="GET",
            path="/api/v5/public/time",
            query={},
            http_status=503,
            final_url="https://openapi.okx.com/api/v5/public/time",
            request_started_at=ts(BASE + timedelta(seconds=2)),
            response_received_at=ts(BASE + timedelta(seconds=3)),
            capture_completed_at=ts(BASE + timedelta(seconds=3)),
            route_policy_id=(
                "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
            ),
        )
        error = OSError("V32_OKX_TRANSPORT_SERVER_TIME_RESPONSE_INVALID")
        error.failure_code = "V32_OKX_TRANSPORT_SERVER_TIME_RESPONSE_INVALID"
        error.failure_context = {
            "component_id": "SERVER_TIME",
            "method": "GET",
            "path": "/api/v5/public/time",
            "query": {},
            "request_started_at": ts(BASE + timedelta(seconds=2)),
            "failure_at": ts(BASE + timedelta(seconds=3)),
            "response_received_at": ts(BASE + timedelta(seconds=3)),
            "capture_completed_at": ts(BASE + timedelta(seconds=3)),
            "final_url": "https://openapi.okx.com/api/v5/public/time",
            "request_dispatched": True,
            "response_present": True,
            "body_present": True,
            "http_status": 503,
            "route_policy_id": (
                "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
            ),
            "failure_codes": [
                "V32_OKX_TRANSPORT_SERVER_TIME_RESPONSE_INVALID",
                "PUBLIC_PROVIDER_UNAVAILABLE",
            ],
            "attempt_number": 1,
            "retry_allowed": False,
        }
        error.failure_response_body = failure_body
        error.failure_raw_binding = failure_binding
        raise error


def component_final_url(component: dict) -> str:
    encoded = urllib.parse.urlencode(sorted(component["query"].items()))
    base = "https://openapi.okx.com" + component["path"]
    return base if not encoded else f"{base}?{encoded}"


def component_capture_ref(qualification_id: str, component_id: str) -> str:
    slug = component_id.lower().replace("_", "-")
    return f"qualifications/{qualification_id}/component-captures/{slug}.json"


def component_failure_ref(qualification_id: str, component_id: str) -> str:
    slug = component_id.lower().replace("_", "-")
    return f"qualifications/{qualification_id}/component-failures/{slug}.json"


class RecordingStore(LocalV32CycleSourceAdmissionStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.writes: list[str] = []

    def write_raw(self, *, relative_ref: str, payload: bytes) -> dict[str, str]:
        self.writes.append(relative_ref)
        return super().write_raw(relative_ref=relative_ref, payload=payload)


class FailingComponentCaptureStore(RecordingStore):
    def write_document(self, *, relative_ref, document, digest_field):
        if "/component-captures/" in relative_ref:
            raise OSError("injected capture publish crash")
        return super().write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )


class FailingComponentFailureStore(RecordingStore):
    def write_document(self, *, relative_ref, document, digest_field):
        if "/component-failures/" in relative_ref:
            raise OSError("injected no-response receipt publish crash")
        return super().write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )


class CrashAfterCaptureStore(RecordingStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.crashed = False

    def write_document(self, *, relative_ref, document, digest_field):
        if (
            not self.crashed
            and relative_ref.endswith("/public-market-analysis-bundle.json")
        ):
            self.crashed = True
            raise KeyboardInterrupt("injected crash after aggregate capture")
        return super().write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )


class ReadFailureResponse:
    status = 200

    def __init__(
        self, final_url: str, error: BaseException | None = None
    ) -> None:
        self.final_url = final_url
        self.error = error or OSError("injected response body read failure")

    def read(self, amount: int = -1) -> bytes:
        raise self.error

    def geturl(self) -> str:
        return self.final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class BodyResponse(ReadFailureResponse):
    def __init__(self, final_url: str, payload: bytes) -> None:
        super().__init__(final_url)
        self.payload = payload

    def read(self, amount: int = -1) -> bytes:
        return self.payload if amount < 0 else self.payload[:amount]


class RaisingReader:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error or OSError("injected HTTPError body read failure")

    def read(self, amount: int = -1) -> bytes:
        raise self.error

    def close(self) -> None:
        return None


class OneOutcomeOpener:
    route_policy_id = (
        "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
    )

    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class ComponentFailureClock:
    def __init__(self) -> None:
        self.tick = 0

    def __call__(self) -> str:
        self.tick += 1
        return ts(BASE + timedelta(seconds=2, microseconds=self.tick))


def authority() -> dict:
    return build_v32_active_authority_projection(
        run_id=RUN_ID,
        recorded_at=ts(BASE),
        experiment_contract_digest=CONTRACT_DIGEST,
        governing_authority_binding={
            "relative_ref": "config/v32/governing-authority.json",
            "schema_id": "theory_paper_v32_current_research_authority_v1",
            "digest_field": "authority_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        },
    )


class V32PublicSourceCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_current_failure_reproduction_assessment_is_publicly_exported(self) -> None:
        self.assertIn(
            "assess_current_v32_public_source_validation_failure_reproduction_v1",
            collector_module.__all__,
        )

    def test_attempt_only_crash_is_sealed_locally_without_transport_retry(self) -> None:
        qid = "q-attempt-prefix-crash"
        store = RecordingStore(self.root / qid)

        class CrashTransport:
            def __init__(self) -> None:
                self.calls = 0

            def fetch_once(self, *, instrument_id, raw_body_sink):
                del instrument_id, raw_body_sink
                self.calls += 1
                raise KeyboardInterrupt("injected transport process crash")

        transport = CrashTransport()
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaises(KeyboardInterrupt):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        first = collector.seal_interrupted_attempt_failure(
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        second = collector.seal_interrupted_attempt_failure(
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        self.assertEqual(first, second)
        self.assertEqual(1, transport.calls)
        recovered = recover_durable_v32_public_source_failure_v1(
            store=store,
            qualification_id=qid,
            active_authority=authority(),
            expected_run_id=RUN_ID,
            expected_cycle_index=1,
        )
        self.assertEqual(
            "V32_PUBLIC_SOURCE_LOCAL_CRASH_PREFIX_FAILED_CLOSED",
            recovered["failure"]["failure_code"],
        )
        self.assertEqual(
            "PRE_AGGREGATE_RAW_VALIDATION",
            recovered["failure"]["failure_phase"],
        )

    def test_post_capture_crash_is_sealed_from_durable_bytes_without_retry(self) -> None:
        qid = "q-capture-prefix-crash"
        store = CrashAfterCaptureStore(self.root / qid)
        transport = BundleTransport(raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaises(KeyboardInterrupt):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        binding = collector.seal_interrupted_attempt_failure(
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        self.assertEqual(1, transport.calls)
        recovered = recover_durable_v32_public_source_failure_v1(
            store=store,
            qualification_id=qid,
            active_authority=authority(),
            expected_run_id=RUN_ID,
            expected_cycle_index=1,
        )
        self.assertEqual(binding, recovered["failure_evidence_binding"])
        self.assertEqual(
            "POST_CAPTURE_FORMALIZATION",
            recovered["failure"]["failure_phase"],
        )

    def execute(
        self, *, bundle: dict | None = None, qid: str = "q-v32-public-source"
    ):
        store = RecordingStore(self.root / qid)
        transport = BundleTransport(bundle or raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        result = collector.collect_and_qualify(
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        return store, transport, collector, result

    def test_single_transaction_raw_first_builds_complete_typed_analysis_bundle(self) -> None:
        store, transport, _, result = self.execute()
        self.assertEqual(1, transport.calls)
        analysis = result.public_market_analysis_bundle
        self.assertEqual(ANALYSIS_BUNDLE_SCHEMA_ID, analysis["schema_id"])
        self.assertEqual(
            ANALYSIS_BUNDLE_SCHEMA_VERSION, analysis["schema_version"]
        )
        self.assertEqual(
            analysis[ANALYSIS_BUNDLE_DIGEST_FIELD],
            verify_v32_public_market_analysis_bundle(analysis),
        )
        self.assertEqual(12, len(analysis["request_raw_bindings"]))
        self.assertTrue(
            all(row["attempt_number"] == 1 for row in analysis["request_raw_bindings"])
        )
        self.assertGreaterEqual(len(analysis["datums"]), 500)
        self.assertTrue(
            all(
                row["available_at"] == analysis["available_at"]
                for row in analysis["datums"]
                if row["status"] == "DERIVED"
            )
        )
        self.assertEqual({"15M", "1H", "4H", "1D"}, set(analysis["closed_bar_series"]))
        self.assertTrue(all(len(rows) == 20 for rows in analysis["closed_bar_series"].values()))
        datums = {row["datum_id"]: row for row in analysis["datums"]}
        funding = datums["funding-rate"]
        next_funding = datums["next-funding-settlement-time-ms"]
        self.assertEqual(PIT_DATUM_SCHEMA_VERSION, funding["schema_version"])
        self.assertEqual(
            ts(BASE + timedelta(seconds=2)), funding["observed_at"]
        )
        self.assertEqual(funding["observed_at"], funding["provider_observed_at"])
        self.assertEqual(
            ts(datetime.fromtimestamp((SERVER_MS + 3_600_000) / 1000, tz=UTC)),
            funding["effective_at"],
        )
        self.assertEqual(
            str(SERVER_MS + 7_200_000), next_funding["value"]
        )
        self.assertGreater(next_funding["effective_at"], analysis["available_at"])
        self.assertLessEqual(analysis["as_of"], analysis["available_at"])
        self.assertNotEqual(funding["effective_at"], analysis["as_of"])
        instrument = datums["contract-value"]
        self.assertIsNone(instrument["provider_observed_at"])
        self.assertEqual(
            "LOCAL_CAPTURE_NO_PROVIDER_CLOCK",
            instrument["clock_uncertainty_status"],
        )
        self.assertEqual(instrument["observed_at"], instrument["available_at"])
        self.assertEqual(
            [
                "PRICE_DIRECTIONAL_PRESSURE",
                "STRUCTURE_PERSISTENCE",
                "PARTICIPATION_AND_ACTIVE_FLOW",
                "CROWDING_DIRECTION",
                "LEVERAGE_CHANGE",
                "FORCED_DELEVERAGING_PRESSURE",
                "LIQUIDITY_RESILIENCE",
                "VOLATILITY_AND_TAIL_STRESS",
                "EVENT_AND_NARRATIVE_REACTION",
                "ATTENTION_AND_AUDIENCE_RESPONSE",
                "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
                "TIMEFRAME_COHERENCE",
                "OTHER",
            ],
            [row["axis_id"] for row in analysis["axis_source_evidence"]],
        )
        raw_index = store.writes.index(
            "qualifications/q-v32-public-source/raw/public-market-bundle.body"
        )
        capture_index = store.writes.index(
            "qualifications/q-v32-public-source/capture.json"
        )
        request_raw_indices = [
            index
            for index, ref in enumerate(store.writes)
            if "/raw/requests/" in ref and ref.endswith(".body")
        ]
        component_capture_refs = [
            ref for ref in store.writes if "/component-captures/" in ref
        ]
        self.assertEqual(12, len(request_raw_indices))
        self.assertEqual(12, len(component_capture_refs))
        self.assertLess(max(request_raw_indices), raw_index)
        for index, component in enumerate(raw_bundle()["components"]):
            slug = component["component_id"].lower().replace("_", "-")
            body_ref = (
                "qualifications/q-v32-public-source/raw/requests/"
                f"{slug}.body"
            )
            capture_ref = (
                "qualifications/q-v32-public-source/component-captures/"
                f"{slug}.json"
            )
            self.assertLess(store.writes.index(body_ref), store.writes.index(capture_ref))
            if index + 1 < 12:
                next_slug = (
                    raw_bundle()["components"][index + 1]["component_id"]
                    .lower()
                    .replace("_", "-")
                )
                next_body_ref = (
                    "qualifications/q-v32-public-source/raw/requests/"
                    f"{next_slug}.body"
                )
                self.assertLess(
                    store.writes.index(capture_ref), store.writes.index(next_body_ref)
                )
            sealed_capture = store.read_document(
                relative_ref=capture_ref,
                digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
            )
            self.assertEqual(
                sealed_capture[COMPONENT_CAPTURE_DIGEST_FIELD],
                verify_v32_public_component_capture_v1(sealed_capture),
            )
            self.assertEqual(component["component_id"], sealed_capture["component_id"])
            self.assertEqual(
                COMPONENT_CAPTURE_SCHEMA_VERSION,
                sealed_capture["schema_version"],
            )
            self.assertEqual(component_final_url(component), sealed_capture["final_url"])
            self.assertEqual(1, sealed_capture["attempt_number"])
            self.assertFalse(sealed_capture["retry_allowed"])
            self.assertFalse(sealed_capture["executable"])
            self.assertEqual(
                V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
                sealed_capture["request_header_policy_id"],
            )
            self.assertEqual(
                V32_PUBLIC_REQUEST_HEADERS_DIGEST,
                sealed_capture["request_headers_digest"],
            )
        self.assertLess(raw_index, capture_index)
        replay = verify_durable_v32_public_source_qualification(
            store=store,
            qualification_id="q-v32-public-source",
            active_authority=authority(),
        )
        self.assertEqual(
            result.public_market_analysis_bundle_binding,
            replay.public_market_analysis_bundle_binding,
        )

    def test_optional_sources_remain_unknown_not_zero_and_other_is_retained(self) -> None:
        store, transport, _, result = self.execute(
            bundle=raw_bundle(unknown_optional=True), qid="q-unknown-optional"
        )
        analysis = result.public_market_analysis_bundle
        by_id = {row["datum_id"]: row for row in analysis["datums"]}
        for datum_id in (
            "open-interest-btc",
            "funding-rate",
            "book-best-bid",
            "recent-trade-count",
        ):
            self.assertEqual("UNKNOWN", by_id[datum_id]["status"])
            self.assertIsNone(by_id[datum_id]["value"])
            self.assertFalse(by_id[datum_id]["missing_is_zero"])
        self.assertEqual("UNKNOWN", result.market_snapshot["open_interest_status"])
        self.assertFalse(result.market_snapshot["open_interest_zero_imputed"])
        axes = {row["axis_id"]: row for row in analysis["axis_source_evidence"]}
        self.assertEqual(
            "SOURCE_COMPONENT_UNKNOWN:OPEN_INTEREST",
            axes["LEVERAGE_CHANGE"]["reason_code"],
        )
        self.assertEqual(
            "SOURCE_COMPONENT_UNKNOWN:ORDER_BOOK",
            axes["LIQUIDITY_RESILIENCE"]["reason_code"],
        )
        self.assertEqual(
            "UNKNOWN",
            axes["LIQUIDITY_RESILIENCE"]["source_assessments"][0][
                "admission_status"
            ],
        )
        other = analysis["axis_source_evidence"][-1]
        self.assertEqual("OTHER", other["status"])
        self.assertTrue(other["other_retained"])
        request_by_component = {
            row["component_id"]: row
            for row in analysis["request_raw_bindings"]
        }
        for component_id in (
            "OPEN_INTEREST",
            "FUNDING_RATE",
            "ORDER_BOOK",
            "RECENT_TRADES",
        ):
            binding = request_by_component[component_id][
                "failure_evidence_binding"
            ]
            self.assertEqual(
                component_failure_ref("q-unknown-optional", component_id),
                binding["relative_ref"],
            )
            receipt = store.read_document(
                relative_ref=binding["relative_ref"],
                digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
                expected_semantic_digest=binding["semantic_digest"],
                expected_physical_sha256=binding["physical_sha256"],
            )
            self.assertEqual(
                receipt[COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD],
                verify_v32_public_component_no_response_failure_v1(receipt),
            )
            self.assertEqual(
                COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_VERSION,
                receipt["schema_version"],
            )
            self.assertFalse(receipt["response_present"])
            self.assertFalse(receipt["body_present"])
            self.assertIsNone(receipt["http_status"])
            self.assertIsNone(receipt["response_final_url"])
            self.assertEqual(
                V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
                receipt["request_header_policy_id"],
            )
            self.assertEqual(
                V32_PUBLIC_REQUEST_HEADERS_DIGEST,
                receipt["request_headers_digest"],
            )
        verify_durable_v32_public_source_qualification(
            store=store,
            qualification_id="q-unknown-optional",
            active_authority=authority(),
        )
        self.assertEqual(1, transport.calls)

    def test_missing_tampered_or_swapped_no_response_receipt_fails_replay(self) -> None:
        for case in ("missing", "tampered", "swapped"):
            with self.subTest(case=case):
                qid = f"q-no-response-{case}"
                store, transport, _, _ = self.execute(
                    bundle=raw_bundle(unknown_optional=True), qid=qid
                )
                oi_path = store.root / component_failure_ref(
                    qid, "OPEN_INTEREST"
                )
                funding_path = store.root / component_failure_ref(
                    qid, "FUNDING_RATE"
                )
                if case == "missing":
                    oi_path.unlink()
                elif case == "tampered":
                    receipt = store.read_document(
                        relative_ref=component_failure_ref(
                            qid, "OPEN_INTEREST"
                        ),
                        digest_field=COMPONENT_NO_RESPONSE_FAILURE_DIGEST_FIELD,
                    )
                    receipt["failure_at"] = ts(
                        BASE + timedelta(seconds=4)
                    )
                    oi_path.write_bytes(canonical_bytes(receipt) + b"\n")
                else:
                    oi_bytes = oi_path.read_bytes()
                    funding_bytes = funding_path.read_bytes()
                    oi_path.write_bytes(funding_bytes)
                    funding_path.write_bytes(oi_bytes)
                with self.assertRaisesRegex(
                    V32PublicSourceCollectorError,
                    "NO_RESPONSE|DURABLE_REPLAY_FAILED",
                ):
                    verify_durable_v32_public_source_qualification(
                        store=store,
                        qualification_id=qid,
                        active_authority=authority(),
                    )
                self.assertEqual(1, transport.calls)

    def test_no_response_receipt_sink_failure_stops_before_aggregate(self) -> None:
        qid = "q-no-response-sink-failure"
        store = FailingComponentFailureStore(self.root / qid)
        transport = BundleTransport(raw_bundle(unknown_optional=True))
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "QUALIFICATION_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/raw/public-market-bundle.body"
            )
        )
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/qualification.json"
            )
        )

    def test_axis_rows_bind_exact_frozen_source_roles_and_claim_ceilings(self) -> None:
        _, _, _, result = self.execute(qid="q-axis-source-roles")
        analysis = result.public_market_analysis_bundle
        registry = build_v31_native_sentiment_source_registry()
        registry_digest = verify_v31_native_sentiment_source_registry(registry)
        self.assertEqual(registry_digest, analysis["axis_source_registry_digest"])
        axes = {row["axis_id"]: row for row in analysis["axis_source_evidence"]}

        liquidity = axes["LIQUIDITY_RESILIENCE"]
        self.assertEqual("UNKNOWN", liquidity["status"])
        self.assertEqual("UNKNOWN", liquidity["admission_status"])
        self.assertFalse(liquidity["native_external_direct_admitted"])
        self.assertEqual(
            {
                "source_kind": "PUBLIC_ORDER_BOOK_SNAPSHOT",
                "evidence_role": "UNKNOWN",
                "admission_status": "REJECTED",
                "claim_ceiling": "SINGLE_BOOK_STATE_NOT_RESILIENCE",
            },
            {
                key: liquidity["source_assessments"][0][key]
                for key in (
                    "source_kind",
                    "evidence_role",
                    "admission_status",
                    "claim_ceiling",
                )
            },
        )

        leverage = axes["LEVERAGE_CHANGE"]
        self.assertEqual("UNKNOWN", leverage["status"])
        self.assertEqual("UNKNOWN", leverage["admission_status"])
        self.assertEqual(
            ("DIRECT", "ADMITTED", "OPEN_INTEREST_LEVEL_ONLY"),
            tuple(
                leverage["source_assessments"][0][key]
                for key in (
                    "evidence_role",
                    "admission_status",
                    "claim_ceiling",
                )
            ),
        )

        coherence = axes["TIMEFRAME_COHERENCE"]
        self.assertEqual("UNKNOWN", coherence["status"])
        self.assertEqual("DERIVED", coherence["source_assessments"][0]["evidence_role"])
        self.assertEqual("UNKNOWN", coherence["source_assessments"][0]["admission_status"])
        self.assertEqual(
            "DERIVED_MEASURE_NOT_MATERIALIZED",
            coherence["source_assessments"][0]["reason_code"],
        )

    def test_self_resigned_book_snapshot_cannot_be_promoted_to_direct_resilience(self) -> None:
        _, _, _, result = self.execute(qid="q-book-promotion-forgery")
        forged = deepcopy(result.public_market_analysis_bundle)
        liquidity = next(
            row
            for row in forged["axis_source_evidence"]
            if row["axis_id"] == "LIQUIDITY_RESILIENCE"
        )
        assessment = liquidity["source_assessments"][0]
        assessment.update(
            {
                "evidence_role": "DIRECT",
                "admission_status": "ADMITTED",
                "reason_code": None,
            }
        )
        assessment.update(
            self_digest(assessment, AXIS_SOURCE_ASSESSMENT_DIGEST_FIELD)
        )
        liquidity.update(
            {
                "status": "OBSERVED",
                "admission_status": "ADMITTED",
                "native_external_direct_admitted": True,
                "observed_at": forged["as_of"],
                "claim_ceiling": "ADMITTED_SOURCE_COVERAGE_NOT_DIRECTIONAL_STATE",
                "reason_code": None,
            }
        )
        liquidity.update(self_digest(liquidity, AXIS_EVIDENCE_DIGEST_FIELD))
        forged["pit_member_digests"] = sorted(
            [row[PIT_DATUM_DIGEST_FIELD] for row in forged["datums"]]
            + [row["public_source_event_digest"] for row in forged["information_events"]]
            + [row[AXIS_EVIDENCE_DIGEST_FIELD] for row in forged["axis_source_evidence"]]
        )
        forged = self_digest(forged, ANALYSIS_BUNDLE_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "AXIS_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_public_market_analysis_bundle(forged)

    def test_self_resigned_oi_level_cannot_be_promoted_to_leverage_change(self) -> None:
        _, _, _, result = self.execute(qid="q-oi-change-forgery")
        forged = deepcopy(result.public_market_analysis_bundle)
        leverage = next(
            row
            for row in forged["axis_source_evidence"]
            if row["axis_id"] == "LEVERAGE_CHANGE"
        )
        leverage.update(
            {
                "status": "OBSERVED",
                "admission_status": "ADMITTED",
                "native_external_direct_admitted": True,
                "observed_at": forged["as_of"],
                "claim_ceiling": "ADMITTED_SOURCE_COVERAGE_NOT_DIRECTIONAL_STATE",
                "reason_code": None,
            }
        )
        leverage.update(self_digest(leverage, AXIS_EVIDENCE_DIGEST_FIELD))
        forged["pit_member_digests"] = sorted(
            [row[PIT_DATUM_DIGEST_FIELD] for row in forged["datums"]]
            + [row["public_source_event_digest"] for row in forged["information_events"]]
            + [row[AXIS_EVIDENCE_DIGEST_FIELD] for row in forged["axis_source_evidence"]]
        )
        forged = self_digest(forged, ANALYSIS_BUNDLE_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "AXIS_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_public_market_analysis_bundle(forged)

    def test_provider_time_travel_seals_all_raw_then_fails_and_cannot_retry(self) -> None:
        bundle = raw_bundle()
        mark = next(row for row in bundle["components"] if row["component_id"] == "MARK_PRICE")
        mark["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "60000",
                    "ts": str(int((BASE + timedelta(seconds=9)).timestamp() * 1000)),
                }
            ]
        )
        store = RecordingStore(self.root / "time-travel")
        transport = BundleTransport(bundle)
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport, clock=SequenceClock(), store=store
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "PROVIDER_TIME_TRAVEL"
        ) as raised:
            collector.collect_and_qualify(
                qualification_id="q-time-travel",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        self.assertTrue(
            store.artifact_exists(
                relative_ref="qualifications/q-time-travel/raw/public-market-bundle.body"
            )
        )
        self.assertEqual(12, len([ref for ref in store.writes if "/raw/requests/" in ref]))
        receipt = store.read_document(
            relative_ref="qualifications/q-time-travel/validation-failure.json",
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
        )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            verify_v32_public_source_validation_failure_v1(receipt),
        )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_validation_failure_v1(
                receipt, store=store
            ),
        )
        forged = deepcopy(receipt)
        forged["failed_at"] = ts(BASE + timedelta(seconds=99))
        forged = self_digest(forged, VALIDATION_FAILURE_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "REPLAY_INVALID"
        ):
            verify_durable_v32_public_source_validation_failure_v1(
                forged, store=store
            )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            raised.exception.failure_evidence_binding["semantic_digest"],
        )
        self.assertEqual(12, len(receipt["component_evidence_bindings"]))
        with self.assertRaisesRegex(V32PublicSourceCollectorError, "ATTEMPT_ALREADY_CONSUMED"):
            collector.collect_and_qualify(
                qualification_id="q-time-travel",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)

    def test_validation_failure_replays_optional_no_response_evidence(self) -> None:
        bundle = raw_bundle(unknown_optional=True)
        mark = next(
            row
            for row in bundle["components"]
            if row["component_id"] == "MARK_PRICE"
        )
        mark["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "60000",
                    "ts": str(
                        int(
                            (BASE + timedelta(seconds=9)).timestamp()
                            * 1000
                        )
                    ),
                }
            ]
        )
        store = RecordingStore(self.root / "mixed-validation-failure")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(bundle),
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "PROVIDER_TIME_TRAVEL"
        ):
            collector.collect_and_qualify(
                qualification_id="q-mixed-validation-failure",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        receipt = store.read_document(
            relative_ref=(
                "qualifications/q-mixed-validation-failure/"
                "validation-failure.json"
            ),
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
        )
        for component_id in (
            "OPEN_INTEREST",
            "FUNDING_RATE",
            "ORDER_BOOK",
            "RECENT_TRADES",
        ):
            self.assertEqual(
                COMPONENT_NO_RESPONSE_FAILURE_SCHEMA_ID,
                receipt["component_evidence_bindings"][component_id][
                    "schema_id"
                ],
            )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_validation_failure_v1(
                receipt, store=store
            ),
        )

    def test_validation_failure_replay_binds_actual_document_bytes(self) -> None:
        bundle = raw_bundle()
        mark = next(
            row
            for row in bundle["components"]
            if row["component_id"] == "MARK_PRICE"
        )
        mark["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "60000",
                    "ts": str(
                        int(
                            (BASE + timedelta(seconds=9)).timestamp()
                            * 1000
                        )
                    ),
                }
            ]
        )
        store = RecordingStore(self.root / "physical-binding")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(bundle),
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaises(V32PublicSourceCollectorError):
            collector.collect_and_qualify(
                qualification_id="q-physical-binding",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        receipt = store.read_document(
            relative_ref=(
                "qualifications/q-physical-binding/validation-failure.json"
            ),
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
        )
        capture_path = store.root / (
            "qualifications/q-physical-binding/capture.json"
        )
        capture_path.write_bytes(b" " + capture_path.read_bytes())
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_durable_v32_public_source_validation_failure_v1(
                receipt, store=store
            )

    def test_staleness_is_measured_at_aggregate_availability(self) -> None:
        values = iter(
            [
                ts(BASE + timedelta(seconds=1)),
                ts(BASE + timedelta(seconds=2)),
                ts(BASE + timedelta(seconds=200)),
                ts(BASE + timedelta(seconds=201)),
            ]
        )
        store = RecordingStore(self.root / "slow-aggregate")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(raw_bundle()),
            clock=values.__next__,
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "COMPONENT_STALE"
        ):
            collector.collect_and_qualify(
                qualification_id="q-slow-aggregate",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )

    def test_late_formalization_failure_is_durable_and_recoverable(self) -> None:
        values = iter(
            [
                ts(BASE + timedelta(seconds=1)),
                ts(BASE + timedelta(seconds=2)),
                ts(BASE + timedelta(seconds=4)),
                ts(BASE + timedelta(seconds=1001)),
                ts(BASE + timedelta(seconds=1002)),
                ts(BASE + timedelta(seconds=1003)),
            ]
        )
        qid = "q-late-formalization"
        store = RecordingStore(self.root / qid)
        transport = BundleTransport(raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=values.__next__,
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "FRESHNESS_INVALID"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        recovered = recover_durable_v32_public_source_failure_v1(
            store=store,
            qualification_id=qid,
            active_authority=authority(),
            expected_run_id=RUN_ID,
            expected_cycle_index=1,
        )
        self.assertEqual(
            "POST_CAPTURE_FORMALIZATION",
            recovered["failure"]["failure_phase"],
        )
        self.assertEqual(
            "V32_PUBLIC_SOURCE_FRESHNESS_INVALID",
            recovered["failure"]["failure_code"],
        )
        self.assertEqual(1, transport.calls)

    def test_microsecond_provider_ahead_preserves_knowledge_safe_as_of(self) -> None:
        bundle = raw_bundle()
        mark = next(
            row
            for row in bundle["components"]
            if row["component_id"] == "MARK_PRICE"
        )
        mark["response_received_at"] = ts(
            BASE + timedelta(seconds=3, microseconds=500_500)
        )
        mark["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "60000",
                    "ts": str(
                        int(
                            (
                                BASE
                                + timedelta(seconds=3, microseconds=501_000)
                            ).timestamp()
                            * 1000
                        )
                    ),
                }
            ]
        )
        _, _, _, result = self.execute(
            bundle=bundle, qid="q-microsecond-as-of"
        )
        analysis = result.public_market_analysis_bundle
        self.assertEqual(mark["response_received_at"], analysis["as_of"])
        self.assertTrue(
            all(
                row["observed_at"] is None
                or row["source_component_id"]
                in {"SERVER_TIME", "INSTRUMENT"}
                or row["observed_at"] <= analysis["as_of"]
                for row in analysis["datums"]
            )
        )

    def test_derived_provider_ahead_uses_source_clock_but_aggregate_availability(self) -> None:
        bundle = raw_bundle()
        trades = next(
            row
            for row in bundle["components"]
            if row["component_id"] == "RECENT_TRADES"
        )
        trades["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": "ahead-trade-1",
                    "px": "60000",
                    "side": "buy",
                    "sz": "1",
                    "ts": str(
                        int(
                            (
                                BASE
                                + timedelta(seconds=3, milliseconds=500)
                            ).timestamp()
                            * 1000
                        )
                    ),
                }
            ]
        )
        _, _, _, result = self.execute(
            bundle=bundle, qid="q-derived-provider-ahead"
        )
        count = next(
            row
            for row in result.public_market_analysis_bundle["datums"]
            if row["datum_id"] == "recent-trade-count"
        )
        self.assertEqual(ts(BASE + timedelta(seconds=3)), count["observed_at"])
        self.assertEqual(
            ts(BASE + timedelta(seconds=4)), count["available_at"]
        )
        self.assertEqual(500, count["provider_clock_ahead_milliseconds"])
        self.assertEqual(
            "WITHIN_BOUND_PROVIDER_AHEAD_NORMALIZED_TO_SOURCE_CLOCK",
            count["clock_uncertainty_status"],
        )

    def test_static_bundle_rejects_resigned_as_of_bar_gap_and_funding_time(self) -> None:
        _, _, _, result = self.execute(qid="q-static-time-forgery")
        original = result.public_market_analysis_bundle

        forged_as_of = deepcopy(original)
        forged_as_of["as_of"] = ts(BASE - timedelta(days=2))
        forged_as_of = self_digest(
            forged_as_of, ANALYSIS_BUNDLE_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "AS_OF_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_public_market_analysis_bundle(forged_as_of)

        forged_gap = deepcopy(original)
        forged_gap["closed_bar_series"]["15M"][10]["open_time_ms"] += 1
        forged_gap["closed_bar_series"]["15M"][10]["close_time_ms"] += 1
        forged_gap = self_digest(forged_gap, ANALYSIS_BUNDLE_DIGEST_FIELD)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged_gap)

        forged_funding = deepcopy(original)
        funding = next(
            row
            for row in forged_funding["datums"]
            if row["datum_id"] == "funding-rate"
        )
        funding["effective_at"] = ts(BASE + timedelta(days=99))
        funding.update(self_digest(funding, PIT_DATUM_DIGEST_FIELD))
        forged_funding["pit_member_digests"] = sorted(
            [row[PIT_DATUM_DIGEST_FIELD] for row in forged_funding["datums"]]
            + [
                row["public_source_event_digest"]
                for row in forged_funding["information_events"]
            ]
            + [
                row[AXIS_EVIDENCE_DIGEST_FIELD]
                for row in forged_funding["axis_source_evidence"]
            ]
        )
        forged_funding = self_digest(
            forged_funding, ANALYSIS_BUNDLE_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "FUNDING_TIME_INVALID"
        ):
            verify_v32_public_market_analysis_bundle(forged_funding)

    def test_raw_candles_and_trade_sample_reject_malformed_or_over_limit_rows(self) -> None:
        malformed = raw_bundle()
        candles = next(
            row
            for row in malformed["components"]
            if row["component_id"] == "CLOSED_CANDLES_15M"
        )
        candle_body = loads_json_strict(candles["body_utf8"])
        candle_body["data"].append(["malformed"])
        candles["body_utf8"] = okx_body(candle_body["data"])
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "CLOSED_BAR_INVALID"
        ):
            self.execute(bundle=malformed, qid="q-malformed-candle-row")

        oversized = raw_bundle()
        trades = next(
            row
            for row in oversized["components"]
            if row["component_id"] == "RECENT_TRADES"
        )
        trades["body_utf8"] = okx_body(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": f"over-limit-{index}",
                    "px": "60000",
                    "side": "buy" if index % 2 == 0 else "sell",
                    "sz": "1",
                    "ts": str(SERVER_MS - 1000),
                }
                for index in range(101)
            ]
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "RECENT_TRADES_INVALID"
        ):
            self.execute(bundle=oversized, qid="q-over-limit-trades")

        duplicated = raw_bundle()
        trades = next(
            row
            for row in duplicated["components"]
            if row["component_id"] == "RECENT_TRADES"
        )
        body = loads_json_strict(trades["body_utf8"])
        body["data"][1]["tradeId"] = body["data"][0]["tradeId"]
        trades["body_utf8"] = okx_body(body["data"])
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "RECENT_TRADES_INVALID"
        ):
            self.execute(bundle=duplicated, qid="q-duplicate-trade-id")

    def test_static_bundle_rejects_ohlc_effective_time_and_trade_metadata_forgery(self) -> None:
        _, _, _, result = self.execute(qid="q-static-role-forgery")
        original = result.public_market_analysis_bundle

        forged_bar = deepcopy(original)
        forged_bar["closed_bar_series"]["15M"][0]["high"] = "1"
        forged_bar = self_digest(
            forged_bar, ANALYSIS_BUNDLE_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "BAR_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_public_market_analysis_bundle(forged_bar)

        forged_effective = deepcopy(original)
        mark = next(
            row
            for row in forged_effective["datums"]
            if row["datum_id"] == "mark-price"
        )
        mark["effective_at"] = ts(BASE + timedelta(days=99))
        mark.update(self_digest(mark, PIT_DATUM_DIGEST_FIELD))
        forged_effective = resign_analysis(forged_effective)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged_effective)

        forged_count = deepcopy(original)
        count = next(
            row
            for row in forged_count["datums"]
            if row["datum_id"] == "recent-trade-count"
        )
        count["value"] = "999"
        count.update(self_digest(count, PIT_DATUM_DIGEST_FIELD))
        forged_count = resign_analysis(forged_count)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRADE_SAMPLE_INVALID"
        ):
            verify_v32_public_market_analysis_bundle(forged_count)

    def test_datum_contract_rejects_resigned_value_unit_metric_source_and_derivation(self) -> None:
        _, _, _, result = self.execute(qid="q-datum-contract")
        original = result.public_market_analysis_bundle
        ticker_event_id = next(
            row["event_id"]
            for row in original["information_events"]
            if row["component_id"] == "TICKER"
        )
        mutations = (
            {"value": "not-a-number"},
            {"unit": "BTC"},
            {"metric_kind": "PUBLIC_MAGIC_PRICE"},
            {
                "source_component_id": "TICKER",
                "source_event_id": ticker_event_id,
            },
            {"derivation": "DERIVED_BY_ASSERTION"},
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                forged = deepcopy(original)
                mark = next(
                    row
                    for row in forged["datums"]
                    if row["datum_id"] == "mark-price"
                )
                mark.update(mutation)
                mark.update(self_digest(mark, PIT_DATUM_DIGEST_FIELD))
                forged = resign_analysis(forged)
                with self.assertRaises(V32PublicSourceCollectorError):
                    verify_v32_public_market_analysis_bundle(forged)

    def test_event_and_axis_schema_versions_are_exact(self) -> None:
        _, _, _, result = self.execute(qid="q-member-schema-version")
        original = result.public_market_analysis_bundle

        forged_event = deepcopy(original)
        event = forged_event["information_events"][0]
        event["schema_version"] = "9.9.9"
        event.update(
            self_digest(event, "public_source_event_digest")
        )
        forged_event = resign_analysis(forged_event)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged_event)

        forged_axis = deepcopy(original)
        axis = forged_axis["axis_source_evidence"][0]
        axis["schema_version"] = "9.9.9"
        axis.update(self_digest(axis, AXIS_EVIDENCE_DIGEST_FIELD))
        forged_axis = resign_analysis(forged_axis)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged_axis)

    def test_order_book_requires_five_sorted_non_crossed_levels(self) -> None:
        cases = []
        too_shallow = raw_bundle()
        book = next(
            row
            for row in too_shallow["components"]
            if row["component_id"] == "ORDER_BOOK"
        )
        body = loads_json_strict(book["body_utf8"])
        body["data"][0]["bids"] = body["data"][0]["bids"][:4]
        book["body_utf8"] = okx_body(body["data"])
        cases.append(("shallow", too_shallow))

        unsorted = raw_bundle()
        book = next(
            row
            for row in unsorted["components"]
            if row["component_id"] == "ORDER_BOOK"
        )
        body = loads_json_strict(book["body_utf8"])
        body["data"][0]["bids"][1][0] = "60000"
        book["body_utf8"] = okx_body(body["data"])
        cases.append(("unsorted", unsorted))

        crossed = raw_bundle()
        book = next(
            row
            for row in crossed["components"]
            if row["component_id"] == "ORDER_BOOK"
        )
        body = loads_json_strict(book["body_utf8"])
        body["data"][0]["asks"][0][0] = "59998"
        book["body_utf8"] = okx_body(body["data"])
        cases.append(("crossed", crossed))

        for label, bundle in cases:
            with self.subTest(label=label), self.assertRaisesRegex(
                V32PublicSourceCollectorError, "ORDER_BOOK_INVALID"
            ):
                self.execute(bundle=bundle, qid=f"q-book-{label}")

    def test_static_book_group_recomputes_spread_and_declares_raw_replay_dependency(self) -> None:
        _, _, _, result = self.execute(qid="q-book-static")
        original = result.public_market_analysis_bundle
        imbalance = next(
            row
            for row in original["datums"]
            if row["datum_id"] == "book-top5-imbalance"
        )
        self.assertIn(
            "VERIFICATION:DURABLE_RAW_REPLAY_REQUIRED_FOR_BOOK_TOP5_IMBALANCE",
            imbalance["dependency_group_ids"],
        )

        forged_spread = deepcopy(original)
        spread = next(
            row
            for row in forged_spread["datums"]
            if row["datum_id"] == "book-spread-bps"
        )
        spread["value"] = "999999"
        spread.update(self_digest(spread, PIT_DATUM_DIGEST_FIELD))
        forged_spread = resign_analysis(forged_spread)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "BOOK_INVALID"
        ):
            verify_v32_public_market_analysis_bundle(forged_spread)

        forged_dependency = deepcopy(original)
        imbalance = next(
            row
            for row in forged_dependency["datums"]
            if row["datum_id"] == "book-top5-imbalance"
        )
        imbalance["dependency_group_ids"].remove(
            "VERIFICATION:DURABLE_RAW_REPLAY_REQUIRED_FOR_BOOK_TOP5_IMBALANCE"
        )
        imbalance.update(self_digest(imbalance, PIT_DATUM_DIGEST_FIELD))
        forged_dependency = resign_analysis(forged_dependency)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged_dependency)

    def test_permanent_clock_failure_seals_uncertain_terminal_receipt(self) -> None:
        qid = "q-permanent-clock-failure"
        store = RecordingStore(self.root / qid)
        transport = BundleTransport(raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=DeadAfterFirstClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "CLOCK_FAILED"
        ) as raised:
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(0, transport.calls)
        receipt = store.read_document(
            relative_ref=f"qualifications/{qid}/validation-failure.json",
            digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
        )
        self.assertEqual("PRE_AGGREGATE_RAW_VALIDATION", receipt["failure_phase"])
        self.assertEqual(
            "ATTEMPT_STARTED_AT_LAST_KNOWN_UNCERTAIN",
            receipt["failure_time_source"],
        )
        self.assertTrue(receipt["failure_time_uncertain"])
        self.assertEqual(ts(BASE + timedelta(seconds=1)), receipt["failed_at"])
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_validation_failure_v1(
                receipt, store=store
            ),
        )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            raised.exception.failure_evidence_binding["semantic_digest"],
        )
        recovered = recover_durable_v32_public_source_failure_v1(
            store=store,
            qualification_id=qid,
            active_authority=authority(),
            expected_run_id=RUN_ID,
            expected_cycle_index=1,
        )
        self.assertEqual(
            "ATTEMPT_STARTED_AT_LAST_KNOWN_UNCERTAIN",
            recovered["failure"]["failure_time_source"],
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "ATTEMPT_ALREADY_CONSUMED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(0, transport.calls)

    def test_funding_schedule_cannot_predate_provider_observation(self) -> None:
        bundle = raw_bundle()
        funding = next(
            row
            for row in bundle["components"]
            if row["component_id"] == "FUNDING_RATE"
        )
        body = loads_json_strict(funding["body_utf8"])
        body["data"][0]["fundingTime"] = str(SERVER_MS - 3_600_000)
        funding["body_utf8"] = okx_body(body["data"])
        store = RecordingStore(self.root / "funding-before-observation")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(bundle),
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "FUNDING_RATE_INVALID"
        ):
            collector.collect_and_qualify(
                qualification_id="q-funding-before-observation",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )

    def test_build_or_verifier_failure_is_sealed_and_replayable(self) -> None:
        store = RecordingStore(self.root / "analysis-build-failure")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(raw_bundle()),
            clock=SequenceClock(),
            store=store,
        )
        with patch.object(
            collector_module,
            "verify_v32_public_market_analysis_bundle",
            side_effect=TypeError("private implementation detail"),
        ):
            with self.assertRaisesRegex(
                V32PublicSourceCollectorError,
                "ANALYSIS_BUILD_OR_VERIFY_FAILED",
            ):
                collector.collect_and_qualify(
                    qualification_id="q-analysis-build-failure",
                    run_id=RUN_ID,
                    cycle_index=1,
                    active_authority=authority(),
                )
            receipt = store.read_document(
                relative_ref=(
                    "qualifications/q-analysis-build-failure/"
                    "validation-failure.json"
                ),
                digest_field=VALIDATION_FAILURE_DIGEST_FIELD,
            )
            self.assertEqual(
                "REPRODUCED_EXACT_FAILURE",
                assess_current_v32_public_source_validation_failure_reproduction_v1(
                    receipt, store=store
                ),
            )
        self.assertEqual(
            receipt[VALIDATION_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_validation_failure_v1(
                receipt, store=store
            ),
        )
        self.assertEqual(
            "NO_LONGER_REPRODUCES_AFTER_CODE_CHANGE",
            assess_current_v32_public_source_validation_failure_reproduction_v1(
                receipt, store=store
            ),
        )
        recovered = recover_durable_v32_public_source_failure_v1(
            store=store,
            qualification_id="q-analysis-build-failure",
            active_authority=authority(),
            expected_run_id=RUN_ID,
            expected_cycle_index=1,
        )
        self.assertEqual(
            "NO_LONGER_REPRODUCES_AFTER_CODE_CHANGE",
            recovered["current_reproduction_status"],
        )

    def test_missing_or_wrong_source_fails_after_aggregate_raw_is_sealed(self) -> None:
        cases = []
        missing = raw_bundle()
        missing["components"] = [
            row for row in missing["components"] if row["component_id"] != "TICKER"
        ]
        cases.append(("missing", missing, "COMPONENT_SET_INVALID"))
        wrong = raw_bundle()
        wrong["venue"] = "BINANCE"
        cases.append(("wrong", wrong, "IDENTITY_INVALID"))
        for label, bundle, code in cases:
            store = RecordingStore(self.root / label)
            transport = BundleTransport(bundle)
            collector = V32RawFirstOkxPublicBundleCollector(
                transport=transport, clock=SequenceClock(), store=store
            )
            with self.assertRaisesRegex(V32PublicSourceCollectorError, code):
                collector.collect_and_qualify(
                    qualification_id=f"q-{label}",
                    run_id=RUN_ID,
                    cycle_index=1,
                    active_authority=authority(),
                )
            recovered = recover_durable_v32_public_source_failure_v1(
                store=store,
                qualification_id=f"q-{label}",
                active_authority=authority(),
                expected_run_id=RUN_ID,
                expected_cycle_index=1,
            )
            self.assertEqual(
                "PRE_CAPTURE_AGGREGATE_VALIDATION",
                recovered["failure"]["failure_phase"],
            )
            self.assertTrue(
                recovered["failure"]["failure_code"].endswith(code)
            )
            self.assertEqual(1, transport.calls)
            self.assertEqual(1, transport.calls)
            self.assertTrue(
                store.artifact_exists(
                    relative_ref=f"qualifications/q-{label}/raw/public-market-bundle.body"
                )
            )

    def test_legacy_raw_bundle_schema_stops_at_explicit_compatibility_boundary(
        self,
    ) -> None:
        bundle = raw_bundle()
        bundle["schema_version"] = "1.2.0"
        bundle["base_url"] = "https://www.okx.com"
        store = RecordingStore(self.root / "legacy-raw-schema")
        transport = BundleTransport(bundle)
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )

        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "V32_PUBLIC_SOURCE_RAW_BUNDLE_SCHEMA_VERSION_UNSUPPORTED",
        ):
            collector.collect_and_qualify(
                qualification_id="q-legacy-raw-schema",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)

    def test_sealed_failed_www_v1_capture_and_failure_are_read_only(self) -> None:
        project = Path(__file__).resolve().parents[1]
        qualification_run_id = (
            "v32-qualification-btcusdt-20260808t220933z"
        )
        qualification_id = f"{qualification_run_id}:public-source"
        source_root = (
            project
            / ".runtime/v32/qualifications"
            / qualification_run_id
            / "public-source"
        )
        base = source_root / "qualifications" / qualification_id
        capture_path = base / "component-captures/server-time.json"
        failure_path = base / "transport-failure.json"
        if not capture_path.is_file() or not failure_path.is_file():
            self.skipTest("sealed failed qualification is not present")
        capture = load_json_strict(capture_path)
        failure = load_json_strict(failure_path)
        self.assertEqual(
            capture[COMPONENT_CAPTURE_DIGEST_FIELD],
            verify_v32_public_component_capture_v1(capture),
        )
        store = LocalV32CycleSourceAdmissionStore(source_root)
        self.assertEqual(
            failure[TRANSPORT_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_transport_failure_v1(
                failure, store=store
            ),
        )
        forged = deepcopy(failure)
        forged["qualification_id"] = "v32-forged:public-source"
        forged = self_digest(forged, TRANSPORT_FAILURE_DIGEST_FIELD)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_source_transport_failure_v1(forged)

    def test_transport_failure_consumes_attempt_without_retry(self) -> None:
        store = RecordingStore(self.root / "transport-failure")
        transport = BundleTransport(None, fail=True)
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport, clock=SequenceClock(), store=store
        )
        with self.assertRaisesRegex(V32PublicSourceCollectorError, "TRANSPORT_FAILED"):
            collector.collect_and_qualify(
                qualification_id="q-transport-failure",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        with self.assertRaisesRegex(V32PublicSourceCollectorError, "ATTEMPT_ALREADY_CONSUMED"):
            collector.collect_and_qualify(
                qualification_id="q-transport-failure",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        receipt_ref = (
            "qualifications/q-transport-failure/transport-failure.json"
        )
        receipt = store.read_document(
            relative_ref=receipt_ref,
            digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
        )
        verify_v32_public_source_transport_failure_v1(receipt)
        self.assertEqual(
            TRANSPORT_FAILURE_SCHEMA_VERSION, receipt["schema_version"]
        )
        self.assertEqual(
            ["V32_PUBLIC_SOURCE_TRANSPORT_FAILED", "PUBLIC_TIMEOUT"],
            receipt["failure_codes"],
        )
        self.assertEqual("AGGREGATE_PUBLIC_BUNDLE", receipt["component_id"])
        self.assertTrue(receipt["request_dispatched"])
        self.assertFalse(receipt["response_present"])
        self.assertFalse(receipt["body_present"])
        self.assertIsNone(receipt["failure_raw_binding"])
        self.assertIsNone(receipt["response_final_url"])
        self.assertFalse(receipt["credential_data_accessed"])
        self.assertEqual(
            V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
            receipt["request_header_policy_id"],
        )
        self.assertEqual(
            V32_PUBLIC_REQUEST_HEADERS_DIGEST,
            receipt["request_headers_digest"],
        )
        for field, forged_value in (
            ("request_header_policy_id", "V32_FORGED_HEADER_POLICY"),
            ("request_headers_digest", "f" * 64),
        ):
            forged = deepcopy(receipt)
            forged[field] = forged_value
            forged = self_digest(forged, TRANSPORT_FAILURE_DIGEST_FIELD)
            with self.subTest(field=field), self.assertRaises(
                V32PublicSourceCollectorError
            ):
                verify_v32_public_source_transport_failure_v1(forged)
        self.assertLess(
            store.writes.index(
                "qualifications/q-transport-failure/attempt-reservation.json"
            ),
            store.writes.index(receipt_ref),
        )

    def test_durable_transport_failure_requires_owning_receipt_and_attempt(self) -> None:
        qid = "q-durable-transport-owner"
        store = RecordingStore(self.root / qid)
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(None, fail=True),
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRANSPORT_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        receipt = store.read_document(
            relative_ref=f"qualifications/{qid}/transport-failure.json",
            digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
        )

        empty_store = RecordingStore(self.root / "empty-transport-owner")
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "DURABLE_OWNER_INVALID"
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                receipt, store=empty_store
            )

        unsealed = deepcopy(receipt)
        unsealed["failure_at"] = ts(BASE + timedelta(seconds=99))
        unsealed = self_digest(
            unsealed, TRANSPORT_FAILURE_DIGEST_FIELD
        )
        self.assertEqual(
            unsealed[TRANSPORT_FAILURE_DIGEST_FIELD],
            verify_v32_public_source_transport_failure_v1(unsealed),
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "DURABLE_OWNER_INVALID"
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                unsealed, store=store
            )

        swapped_qid = "q-durable-transport-owner-swapped"
        swapped_store = RecordingStore(self.root / swapped_qid)
        swapped_collector = V32RawFirstOkxPublicBundleCollector(
            transport=BundleTransport(None, fail=True),
            clock=SequenceClock(),
            store=swapped_store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRANSPORT_FAILED"
        ):
            swapped_collector.collect_and_qualify(
                qualification_id=swapped_qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        attempt_ref = f"qualifications/{qid}/attempt-reservation.json"
        swapped_attempt_ref = (
            f"qualifications/{swapped_qid}/attempt-reservation.json"
        )
        (store.root / attempt_ref).write_bytes(
            (swapped_store.root / swapped_attempt_ref).read_bytes()
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "ATTEMPT_INVALID"
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                receipt, store=store
            )

    def test_body_read_failures_bind_real_final_url_without_forging_empty_body(self) -> None:
        expected_url = "https://openapi.okx.com/api/v5/public/time"
        cases = (
            (
                "http-error-read",
                urllib.error.HTTPError(
                    expected_url,
                    503,
                    "unavailable",
                    hdrs=None,
                    fp=RaisingReader(),
                ),
                True,
                503,
                expected_url,
            ),
            (
                "success-read",
                ReadFailureResponse(expected_url),
                True,
                200,
                expected_url,
            ),
            (
                "success-value-read",
                ReadFailureResponse(
                    expected_url, ValueError("closed response stream")
                ),
                True,
                200,
                expected_url,
            ),
            (
                "success-incomplete-read",
                ReadFailureResponse(
                    expected_url,
                    http.client.IncompleteRead(b"partial", 10),
                ),
                True,
                200,
                expected_url,
            ),
            (
                "http-error-incomplete-read",
                urllib.error.HTTPError(
                    expected_url,
                    503,
                    "unavailable",
                    hdrs=None,
                    fp=RaisingReader(
                        http.client.IncompleteRead(b"partial", 10)
                    ),
                ),
                True,
                503,
                expected_url,
            ),
            ("no-response", TimeoutError("timeout"), False, None, None),
        )
        for label, outcome, response_present, status, final_url in cases:
            with self.subTest(label=label):
                qid = f"q-{label}"
                store = RecordingStore(self.root / qid)
                opener = OneOutcomeOpener(outcome)
                transport = V32OkxPublicBundleTransport(
                    clock=ComponentFailureClock(), opener=opener
                )
                collector = V32RawFirstOkxPublicBundleCollector(
                    transport=transport,
                    clock=SequenceClock(),
                    store=store,
                )
                with self.assertRaisesRegex(
                    V32PublicSourceCollectorError, "TRANSPORT_FAILED"
                ):
                    collector.collect_and_qualify(
                        qualification_id=qid,
                        run_id=RUN_ID,
                        cycle_index=1,
                        active_authority=authority(),
                    )
                receipt = store.read_document(
                    relative_ref=f"qualifications/{qid}/transport-failure.json",
                    digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
                )
                self.assertEqual(response_present, receipt["response_present"])
                self.assertEqual(status, receipt["http_status"])
                self.assertEqual(final_url, receipt["response_final_url"])
                self.assertFalse(receipt["body_present"])
                self.assertIsNone(receipt["failure_raw_binding"])
                self.assertEqual(
                    receipt[TRANSPORT_FAILURE_DIGEST_FIELD],
                    verify_durable_v32_public_source_transport_failure_v1(
                        receipt, store=store
                    ),
                )
                self.assertFalse(
                    store.artifact_exists(
                        relative_ref=(
                            f"qualifications/{qid}/raw/requests/server-time.body"
                        )
                    )
                )
                self.assertEqual(1, opener.calls)

    def test_post_capture_server_time_parse_failure_binds_final_url_durably(self) -> None:
        qid = "q-server-time-post-capture-parse-failure"
        expected_url = "https://openapi.okx.com/api/v5/public/time"
        response_body = canonical_bytes(
            {"code": "0", "msg": "", "data": [{"ts": "invalid"}]}
        )
        store = RecordingStore(self.root / qid)
        opener = OneOutcomeOpener(BodyResponse(expected_url, response_body))
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=V32OkxPublicBundleTransport(
                clock=ComponentFailureClock(), opener=opener
            ),
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRANSPORT_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        receipt = store.read_document(
            relative_ref=f"qualifications/{qid}/transport-failure.json",
            digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
        )
        self.assertEqual(expected_url, receipt["response_final_url"])
        self.assertTrue(receipt["response_present"])
        self.assertTrue(receipt["body_present"])
        self.assertEqual(200, receipt["http_status"])
        self.assertEqual(
            receipt[TRANSPORT_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_transport_failure_v1(
                receipt, store=store
            ),
        )
        capture = store.read_document(
            relative_ref=component_capture_ref(qid, "SERVER_TIME"),
            digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
        )
        self.assertEqual(expected_url, capture["final_url"])
        self.assertEqual(len(response_body), capture["body_length_bytes"])
        self.assertEqual(1, opener.calls)

    def test_failure_response_body_is_sealed_before_typed_failure_receipt(self) -> None:
        store = RecordingStore(self.root / "transport-body-failure")
        transport = TypedBodyFailureTransport()
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport, clock=SequenceClock(), store=store
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRANSPORT_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id="q-transport-body-failure",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        raw_ref = (
            "qualifications/q-transport-body-failure/raw/requests/server-time.body"
        )
        receipt_ref = (
            "qualifications/q-transport-body-failure/transport-failure.json"
        )
        receipt = store.read_document(
            relative_ref=receipt_ref,
            digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
        )
        verify_v32_public_source_transport_failure_v1(receipt)
        verify_durable_v32_public_source_transport_failure_v1(
            receipt, store=store
        )
        self.assertEqual(1, transport.calls)
        self.assertTrue(receipt["response_present"])
        self.assertTrue(receipt["body_present"])
        self.assertEqual(503, receipt["http_status"])
        self.assertEqual(
            "https://openapi.okx.com/api/v5/public/time",
            receipt["response_final_url"],
        )
        self.assertEqual(ts(BASE + timedelta(seconds=3)), receipt["failure_at"])
        self.assertEqual(
            [
                "V32_PUBLIC_SOURCE_TRANSPORT_FAILED",
                "V32_OKX_TRANSPORT_SERVER_TIME_RESPONSE_INVALID",
                "PUBLIC_PROVIDER_UNAVAILABLE",
            ],
            receipt["failure_codes"],
        )
        self.assertEqual(
            b'{"code":"500","msg":"unavailable"}',
            store.read_raw(
                relative_ref=raw_ref,
                expected_sha256=receipt["failure_raw_binding"]["physical_sha256"],
            ),
        )
        self.assertLess(store.writes.index(raw_ref), store.writes.index(receipt_ref))
        tampered = copy.deepcopy(receipt)
        tampered["failure_raw_binding"]["relative_ref"] = (
            "qualifications/q-transport-body-failure/raw/requests/ticker.body"
        )
        tampered = self_digest(tampered, TRANSPORT_FAILURE_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "TRANSPORT_FAILURE_INVALID",
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                tampered, store=store
            )

    def test_zero_byte_failure_replays_from_capture_and_mismatch_fails_closed(self) -> None:
        qid = "q-zero-byte-failure-capture"
        store = RecordingStore(self.root / qid)
        transport = TypedBodyFailureTransport(b"")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "TRANSPORT_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        receipt = store.read_document(
            relative_ref=f"qualifications/{qid}/transport-failure.json",
            digest_field=TRANSPORT_FAILURE_DIGEST_FIELD,
        )
        self.assertEqual(
            receipt[TRANSPORT_FAILURE_DIGEST_FIELD],
            verify_durable_v32_public_source_transport_failure_v1(
                receipt, store=store
            ),
        )
        capture = store.read_document(
            relative_ref=component_capture_ref(qid, "SERVER_TIME"),
            digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
        )
        self.assertEqual(0, capture["body_length_bytes"])
        self.assertEqual(503, capture["http_status"])
        self.assertEqual(
            b"",
            store.read_raw(
                relative_ref=capture["body_binding"]["relative_ref"],
                expected_sha256=capture["body_binding"]["physical_sha256"],
            ),
        )
        forged = copy.deepcopy(receipt)
        forged["http_status"] = 429
        forged = self_digest(forged, TRANSPORT_FAILURE_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "TRANSPORT_FAILURE_CAPTURE_MISMATCH",
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                forged, store=store
            )
        (store.root / component_capture_ref(qid, "SERVER_TIME")).unlink()
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "COMPONENT_CAPTURE_REPLAY_FAILED",
        ):
            verify_durable_v32_public_source_transport_failure_v1(
                receipt, store=store
            )
        self.assertEqual(1, transport.calls)

    def test_adapter_programming_defect_is_not_relabelled_as_transport(self) -> None:
        class DefectiveTransport:
            def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
                del raw_body_sink
                raise ValueError("adapter schema defect")

        store = RecordingStore(self.root / "adapter-defect")
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=DefectiveTransport(), clock=SequenceClock(), store=store
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "QUALIFICATION_FAILED",
        ) as raised:
            collector.collect_and_qualify(
                qualification_id="q-adapter-defect",
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertNotIn("TRANSPORT_FAILED", str(raised.exception))
        self.assertTrue(
            store.artifact_exists(
                relative_ref=(
                    "qualifications/q-adapter-defect/attempt-reservation.json"
                )
            )
        )

    def test_component_raw_tamper_breaks_durable_derivation_binding(self) -> None:
        store, _, _, _ = self.execute(qid="q-tamper")
        component_path = (
            store.root
            / "qualifications/q-tamper/raw/requests/mark-price.body"
        )
        component_path.write_bytes(b"{}")
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "COMPONENT_RAW_REPLAY_MISMATCH|COMPONENT_CAPTURE_REPLAY_FAILED|DURABLE_REPLAY_FAILED",
        ):
            verify_durable_v32_public_source_qualification(
                store=store,
                qualification_id="q-tamper",
                active_authority=authority(),
            )

    def test_missing_tampered_or_swapped_capture_bundle_fails_durable_replay(self) -> None:
        for case in ("missing", "tampered", "swapped"):
            with self.subTest(case=case):
                qid = f"q-capture-{case}"
                store, transport, _, _ = self.execute(qid=qid)
                server_path = store.root / component_capture_ref(qid, "SERVER_TIME")
                ticker_path = store.root / component_capture_ref(qid, "TICKER")
                if case == "missing":
                    server_path.unlink()
                elif case == "tampered":
                    document = store.read_document(
                        relative_ref=component_capture_ref(qid, "SERVER_TIME"),
                        digest_field=COMPONENT_CAPTURE_DIGEST_FIELD,
                    )
                    document["http_status"] = 201
                    server_path.write_bytes(canonical_bytes(document) + b"\n")
                else:
                    server_bytes = server_path.read_bytes()
                    ticker_bytes = ticker_path.read_bytes()
                    server_path.write_bytes(ticker_bytes)
                    ticker_path.write_bytes(server_bytes)
                with self.assertRaisesRegex(
                    V32PublicSourceCollectorError,
                    "COMPONENT_CAPTURE|DURABLE_REPLAY_FAILED",
                ):
                    verify_durable_v32_public_source_qualification(
                        store=store,
                        qualification_id=qid,
                        active_authority=authority(),
                    )
                self.assertEqual(1, transport.calls)

    def test_capture_publish_crash_leaves_raw_tail_and_never_qualifies(self) -> None:
        qid = "q-capture-publish-crash"
        store = FailingComponentCaptureStore(self.root / qid)
        transport = BundleTransport(raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "QUALIFICATION_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        self.assertTrue(
            store.artifact_exists(
                relative_ref=(
                    f"qualifications/{qid}/raw/requests/server-time.body"
                )
            )
        )
        self.assertFalse(
            store.artifact_exists(
                relative_ref=component_capture_ref(qid, "SERVER_TIME")
            )
        )
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/qualification.json"
            )
        )

    def test_real_adapter_capture_crash_is_not_laundered_as_transport(self) -> None:
        qid = "q-real-adapter-capture-publish-crash"
        raw_ref = f"qualifications/{qid}/raw/requests/server-time.body"
        store = FailingComponentCaptureStore(self.root / qid)
        opener = OneOutcomeOpener(
            BodyResponse(
                "https://openapi.okx.com/api/v5/public/time",
                okx_body([{"ts": str(SERVER_MS)}]).encode("utf-8"),
            )
        )
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=V32OkxPublicBundleTransport(
                clock=ComponentFailureClock(), opener=opener
            ),
            clock=SequenceClock(),
            store=store,
        )

        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "QUALIFICATION_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )

        self.assertEqual(1, opener.calls)
        self.assertEqual(1, store.writes.count(raw_ref))
        self.assertTrue(store.artifact_exists(relative_ref=raw_ref))
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/transport-failure.json"
            )
        )
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/qualification.json"
            )
        )

    def test_capture_clock_rollback_fails_after_raw_without_qualification(self) -> None:
        class RollbackTransport:
            calls = 0

            def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
                self.calls += 1
                raw_body_sink.seal_component_capture(
                    component_id="SERVER_TIME",
                    payload=b"",
                    method="GET",
                    path="/api/v5/public/time",
                    query={},
                    http_status=200,
                    final_url="https://openapi.okx.com/api/v5/public/time",
                    request_started_at=ts(BASE + timedelta(seconds=2)),
                    response_received_at=ts(BASE + timedelta(seconds=3)),
                    capture_completed_at=ts(BASE + timedelta(seconds=2)),
                    route_policy_id=(
                        "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
                    ),
                )
                raise AssertionError("unreachable")

        qid = "q-capture-clock-rollback"
        store = RecordingStore(self.root / qid)
        transport = RollbackTransport()
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError, "QUALIFICATION_FAILED"
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        self.assertEqual(
            b"",
            store.read_raw(
                relative_ref=f"qualifications/{qid}/raw/requests/server-time.body"
            ),
        )
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/qualification.json"
            )
        )

    def test_aggregate_metadata_mismatch_rejects_captured_response(self) -> None:
        class MismatchTransport(BundleTransport):
            def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
                raw = super().fetch_once(
                    instrument_id=instrument_id,
                    raw_body_sink=raw_body_sink,
                )
                document = loads_json_strict(raw)
                document["components"][2]["request_started_at"] = ts(
                    BASE + timedelta(seconds=2, microseconds=1)
                )
                return canonical_bytes(document)

        qid = "q-capture-aggregate-mismatch"
        store = RecordingStore(self.root / qid)
        transport = MismatchTransport(raw_bundle())
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=store,
        )
        with self.assertRaisesRegex(
            V32PublicSourceCollectorError,
            "COMPONENT_CAPTURE_AGGREGATE_MISMATCH",
        ):
            collector.collect_and_qualify(
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                active_authority=authority(),
            )
        self.assertEqual(1, transport.calls)
        self.assertFalse(
            store.artifact_exists(
                relative_ref=f"qualifications/{qid}/qualification.json"
            )
        )

    def test_self_resigned_analysis_datum_cannot_drop_its_raw_binding(self) -> None:
        _, _, _, result = self.execute(qid="q-analysis-resign")
        forged = deepcopy(result.public_market_analysis_bundle)
        forged["datums"] = [dict(row) for row in forged["datums"]]
        observed = next(row for row in forged["datums"] if row["status"] == "OBSERVED")
        observed["raw_binding"] = None
        observed.update(self_digest(observed, PIT_DATUM_DIGEST_FIELD))
        forged["pit_member_digests"] = sorted(
            [
                row[PIT_DATUM_DIGEST_FIELD] for row in forged["datums"]
            ]
            + [
                row["public_source_event_digest"]
                for row in forged["information_events"]
            ]
            + [
                row["axis_source_evidence_digest"]
                for row in forged["axis_source_evidence"]
            ]
        )
        forged = self_digest(forged, ANALYSIS_BUNDLE_DIGEST_FIELD)
        with self.assertRaises(V32PublicSourceCollectorError):
            verify_v32_public_market_analysis_bundle(forged)


if __name__ == "__main__":
    unittest.main()
