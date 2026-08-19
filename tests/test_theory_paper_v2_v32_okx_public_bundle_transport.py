from __future__ import annotations

from collections import deque
import hashlib
import http.client
import io
import json
import unittest
import urllib.error
import urllib.parse

from trade_system.theory_paper_v2.domain.contracts.canonical import loads_json_strict
from trade_system.theory_paper_v2.application.v32_public_evidence_port import (
    RAW_BUNDLE_SCHEMA_VERSION,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_bundle_transport import (
    V32OkxPublicBundleTransport,
    V32OkxPublicBundleTransportError,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    V32PublicComponentRawSinkError,
)


class Response:
    def __init__(
        self, body: str, status: int = 200, *, final_url: str | None = None
    ) -> None:
        self.status = status
        self.body = body.encode()
        self.final_url = final_url

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]

    def geturl(self) -> str:
        assert self.final_url is not None
        return self.final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class ResponseReadFailure(Response):
    def __init__(self, body: str, error: BaseException | None = None) -> None:
        super().__init__(body)
        self.error = error or OSError("injected body read failure")

    def read(self, amount: int = -1) -> bytes:
        raise self.error


class GeturlValueErrorResponse(Response):
    def geturl(self) -> str:
        raise ValueError("invalid final URL accessor")


class StatusValueErrorResponse(Response):
    @property
    def status(self):
        raise ValueError("invalid response status")

    @status.setter
    def status(self, value):
        return None


class RaisingReader:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error or OSError("injected HTTPError body read failure")

    def read(self, amount: int = -1) -> bytes:
        raise self.error

    def close(self) -> None:
        return None


class Opener:
    def __init__(self, outcomes) -> None:
        self.outcomes = deque(outcomes)
        self.urls: list[str] = []
        self.requests = []
        self.timeouts: list[float] = []

    def open(self, request, timeout):
        self.urls.append(request.full_url)
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome.final_url is None:
            outcome.final_url = request.full_url
        return outcome


class RawSink:
    def __init__(self) -> None:
        self.payloads = {}
        self.captures = {}
        self.failures = {}

    def seal_component_capture(self, *, component_id, payload, **metadata):
        if component_id in self.payloads:
            raise AssertionError("duplicate component body")
        self.payloads[component_id] = payload
        self.captures[component_id] = dict(metadata)
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "relative_ref": (
                "qualifications/q-test/raw/requests/"
                f"{component_id.lower().replace('_', '-')}.body"
            ),
            "semantic_digest": digest,
            "physical_sha256": digest,
        }

    def seal_component_no_response_failure(self, *, component_id, **metadata):
        if component_id in self.payloads or component_id in self.failures:
            raise AssertionError("duplicate component evidence")
        self.failures[component_id] = dict(metadata)
        digest = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "relative_ref": (
                "qualifications/q-test/component-failures/"
                f"{component_id.lower().replace('_', '-')}.json"
            ),
            "semantic_digest": digest,
            "physical_sha256": digest,
        }


class FailingOptionalRawSink(RawSink):
    def seal_component_capture(self, *, component_id, payload, **metadata):
        if component_id == "OPEN_INTEREST":
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_RAW_SINK_WRITE_FAILED"
            )
        return super().seal_component_capture(
            component_id=component_id, payload=payload, **metadata
        )


class FailingNoResponseSink(RawSink):
    def seal_component_no_response_failure(self, *, component_id, **metadata):
        if component_id == "OPEN_INTEREST":
            raise V32PublicComponentRawSinkError(
                "V32_PUBLIC_COMPONENT_FAILURE_SINK_WRITE_FAILED"
            )
        return super().seal_component_no_response_failure(
            component_id=component_id, **metadata
        )


class CaptureBeforeNextRequestOpener(Opener):
    def __init__(self, outcomes, sink: RawSink) -> None:
        super().__init__(outcomes)
        self.sink = sink

    def open(self, request, timeout):
        if self.urls:
            if len(self.sink.captures) + len(self.sink.failures) != len(
                self.urls
            ):
                raise AssertionError("next request opened before prior capture")
        return super().open(request, timeout)


def body(data) -> str:
    return json.dumps({"code": "0", "msg": "", "data": data}, separators=(",", ":"))


class V32OkxPublicBundleTransportTests(unittest.TestCase):
    def clock(self):
        self.tick += 1
        return f"2026-08-08T00:00:{self.tick:02d}Z"

    def setUp(self) -> None:
        self.tick = 0
        self.sink = RawSink()
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(11))
        self.opener = Opener(outcomes)

    def test_exact_twelve_public_requests_and_frozen_queries(self) -> None:
        transport = V32OkxPublicBundleTransport(
            clock=self.clock, opener=self.opener
        )
        raw = transport.fetch_once(
            instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
        )
        document = loads_json_strict(raw)
        self.assertEqual("1.3.0", RAW_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(RAW_BUNDLE_SCHEMA_VERSION, document["schema_version"])
        self.assertEqual("https://openapi.okx.com", document["base_url"])
        self.assertEqual(12, len(document["components"]))
        self.assertEqual(12, len(self.opener.urls))
        self.assertEqual(12, len(self.sink.captures))
        server_capture = self.sink.captures["SERVER_TIME"]
        self.assertEqual("GET", server_capture["method"])
        self.assertEqual("/api/v5/public/time", server_capture["path"])
        self.assertEqual({}, server_capture["query"])
        self.assertEqual(200, server_capture["http_status"])
        self.assertEqual(self.opener.urls[0], server_capture["final_url"])
        self.assertLessEqual(
            server_capture["request_started_at"],
            server_capture["response_received_at"],
        )
        self.assertLessEqual(
            server_capture["response_received_at"],
            server_capture["capture_completed_at"],
        )
        self.assertEqual(
            "INJECTED_PUBLIC_OPENER_NO_ROUTE_CLAIM",
            server_capture["route_policy_id"],
        )
        self.assertTrue(
            all(
                url.startswith("https://openapi.okx.com/api/v5/")
                for url in self.opener.urls
            )
        )
        self.assertTrue(all(request.method == "GET" for request in self.opener.requests))
        self.assertTrue(all(timeout == 10.0 for timeout in self.opener.timeouts))
        for request in self.opener.requests:
            header_names = {name.casefold() for name, _ in request.header_items()}
            self.assertEqual({"accept", "user-agent"}, header_names)
            self.assertFalse(
                header_names
                & {
                    "authorization",
                    "cookie",
                    "ok-access-key",
                    "ok-access-passphrase",
                    "ok-access-sign",
                }
            )
            query_names = {
                name.casefold()
                for name in urllib.parse.parse_qs(
                    urllib.parse.urlsplit(request.full_url).query
                )
            }
            self.assertFalse(
                query_names
                & {"apikey", "api_key", "key", "passphrase", "secret", "sign"}
            )
        candle = document["components"][4]
        self.assertEqual("15m", candle["query"]["bar"])
        self.assertEqual("96", candle["query"]["limit"])
        self.assertFalse(any("apiKey" in url or "orders" in url for url in self.opener.urls))
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "ATTEMPT_ALREADY_CONSUMED",
        ):
            transport.fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(12, len(self.opener.urls))

    def test_each_capture_finishes_before_the_next_request_is_opened(self) -> None:
        sink = RawSink()
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(11))
        opener = CaptureBeforeNextRequestOpener(outcomes, sink)
        V32OkxPublicBundleTransport(clock=self.clock, opener=opener).fetch_once(
            instrument_id="BTC-USDT-SWAP", raw_body_sink=sink
        )
        self.assertEqual(12, len(opener.urls))
        self.assertEqual(12, len(sink.captures))

    def test_optional_failure_becomes_unknown_without_retry(self) -> None:
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(urllib.error.URLError("unavailable"))
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        raw = V32OkxPublicBundleTransport(
            clock=self.clock, opener=opener
        ).fetch_once(
            instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
        )
        document = loads_json_strict(raw)
        oi = document["components"][8]
        self.assertEqual("UNKNOWN", oi["status"])
        self.assertEqual("PUBLIC_TRANSPORT_IO_FAILURE", oi["error_code"])
        self.assertIsNone(oi["raw_binding"])
        self.assertIsNotNone(oi["failure_evidence_binding"])
        self.assertIn("OPEN_INTEREST", self.sink.failures)
        self.assertEqual(12, len(opener.urls))

    def test_optional_no_response_receipt_finishes_before_next_request(self) -> None:
        sink = RawSink()
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(urllib.error.URLError("unavailable"))
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = CaptureBeforeNextRequestOpener(outcomes, sink)
        document = loads_json_strict(
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=sink
            )
        )
        self.assertEqual(12, len(opener.urls))
        self.assertIn("OPEN_INTEREST", sink.failures)
        failure = sink.failures["OPEN_INTEREST"]
        self.assertFalse(failure["response_present"])
        self.assertFalse(failure["body_present"])
        self.assertIsNone(failure["http_status"])
        self.assertIsNone(failure["response_final_url"])
        self.assertEqual(1, failure["attempt_number"])
        self.assertFalse(failure["retry_allowed"])
        self.assertIsNotNone(
            document["components"][8]["failure_evidence_binding"]
        )

    def test_optional_no_response_sink_failure_stops_before_next_request(self) -> None:
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(urllib.error.URLError("unavailable"))
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP",
                raw_body_sink=FailingNoResponseSink(),
            )
        self.assertEqual(9, len(opener.urls))
        self.assertEqual(
            "V32_PUBLIC_COMPONENT_FAILURE_SINK_WRITE_FAILED",
            raised.exception.failure_code,
        )

    def test_required_failure_aborts_and_is_not_retried(self) -> None:
        opener = Opener([urllib.error.URLError("down")])
        transport = V32OkxPublicBundleTransport(
            clock=self.clock, opener=opener
        )
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            transport.fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        failure = raised.exception
        self.assertEqual(
            "V32_OKX_TRANSPORT_SERVER_TIME_FAILED", failure.failure_code
        )
        self.assertEqual(
            [
                "V32_OKX_TRANSPORT_SERVER_TIME_FAILED",
                "PUBLIC_TRANSPORT_IO_FAILURE",
            ],
            failure.failure_context["failure_codes"],
        )
        self.assertEqual("SERVER_TIME", failure.failure_context["component_id"])
        self.assertTrue(failure.failure_context["request_dispatched"])
        self.assertFalse(failure.failure_context["response_present"])
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "ATTEMPT_ALREADY_CONSUMED",
        ):
            transport.fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))

    def test_required_redirect_is_rejected_without_follow_or_retry(self) -> None:
        opener = Opener(
            [
                Response(
                    body([{"ts": "1786147200000"}]),
                    final_url="https://openapi.okx.com/api/v5/public/time?redirected=1",
                )
            ]
        )
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "SERVER_TIME_REDIRECT_FORBIDDEN",
        ):
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))
        self.assertEqual(
            "https://openapi.okx.com/api/v5/public/time?redirected=1",
            self.sink.captures["SERVER_TIME"]["final_url"],
        )

    def test_optional_redirect_is_structural_after_raw_seal_and_stops(self) -> None:
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(
            Response(
                body([{"ok": "1"}]),
                final_url=(
                    "https://openapi.okx.com/api/v5/public/open-interest?redirected=1"
                ),
            )
        )
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "OPEN_INTEREST_REDIRECT_FORBIDDEN",
        ) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(9, len(opener.urls))
        self.assertIn("OPEN_INTEREST", self.sink.payloads)
        self.assertEqual(
            "PUBLIC_REDIRECT_FORBIDDEN",
            raised.exception.failure_context["failure_codes"][-1],
        )
        self.assertIsNotNone(raised.exception.failure_raw_binding)

    def test_optional_http_400_bad_json_and_bad_envelope_are_structural(self) -> None:
        cases = (
            ("http-400", Response(body([{"error": "bad request"}]), status=400)),
            ("bad-json", Response("{")),
            ("bad-envelope", Response('{"code":"0","msg":"","data":{}}')),
        )
        for label, optional_response in cases:
            with self.subTest(label=label):
                self.tick = 0
                self.sink = RawSink()
                outcomes = [Response(body([{"ts": "1786147200000"}]))]
                outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
                outcomes.append(optional_response)
                outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
                opener = Opener(outcomes)
                with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
                    V32OkxPublicBundleTransport(
                        clock=self.clock, opener=opener
                    ).fetch_once(
                        instrument_id="BTC-USDT-SWAP",
                        raw_body_sink=self.sink,
                    )
                self.assertEqual(9, len(opener.urls))
                self.assertIn("OPEN_INTEREST", self.sink.payloads)
                self.assertIsNotNone(raised.exception.failure_raw_binding)
                self.assertIn(
                    raised.exception.failure_context["failure_codes"][-1],
                    {
                        "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
                        "PUBLIC_RESPONSE_STRUCTURAL_FAILURE",
                    },
                )

    def test_zero_byte_response_is_sealed_before_structural_failure(self) -> None:
        opener = Opener([Response("")])
        transport = V32OkxPublicBundleTransport(
            clock=self.clock, opener=opener
        )
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            transport.fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))
        self.assertIn("SERVER_TIME", self.sink.payloads)
        self.assertEqual(b"", self.sink.payloads["SERVER_TIME"])
        self.assertEqual(200, self.sink.captures["SERVER_TIME"]["http_status"])
        self.assertTrue(raised.exception.failure_context["response_present"])
        self.assertTrue(raised.exception.failure_context["body_present"])
        self.assertEqual(b"", raised.exception.failure_response_body)
        self.assertIsNotNone(raised.exception.failure_raw_binding)
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError, "ATTEMPT_ALREADY_CONSUMED"
        ):
            transport.fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))

    def test_server_time_semantic_failure_retains_capture_metadata(self) -> None:
        opener = Opener([Response(body([{"ts": "not-a-timestamp"}]))])
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "SERVER_TIME_INVALID",
        ) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        failure = raised.exception
        self.assertEqual(1, len(opener.urls))
        self.assertIn("SERVER_TIME", self.sink.captures)
        self.assertEqual(opener.urls[0], failure.failure_context["final_url"])
        self.assertEqual(
            self.sink.captures["SERVER_TIME"]["response_received_at"],
            failure.failure_context["response_received_at"],
        )
        self.assertEqual(
            self.sink.captures["SERVER_TIME"]["capture_completed_at"],
            failure.failure_context["capture_completed_at"],
        )

    def test_http_error_body_and_status_are_captured_before_classification(self) -> None:
        url = (
            "https://openapi.okx.com/api/v5/public/open-interest?"
            "instId=BTC-USDT-SWAP&instType=SWAP"
        )
        error_body = body([{"error": "temporarily unavailable"}]).encode()
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(
            urllib.error.HTTPError(
                url,
                503,
                "unavailable",
                hdrs=None,
                fp=io.BytesIO(error_body),
            )
        )
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        document = loads_json_strict(
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        )
        self.assertEqual("UNKNOWN", document["components"][8]["status"])
        self.assertEqual(error_body, self.sink.payloads["OPEN_INTEREST"])
        capture = self.sink.captures["OPEN_INTEREST"]
        self.assertEqual(503, capture["http_status"])
        self.assertEqual(url, capture["final_url"])

    def test_http_error_body_read_failure_is_not_forged_as_zero_bytes(self) -> None:
        url = (
            "https://openapi.okx.com/api/v5/public/open-interest?"
            "instId=BTC-USDT-SWAP&instType=SWAP"
        )
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(
            urllib.error.HTTPError(
                url,
                503,
                "unavailable",
                hdrs=None,
                fp=RaisingReader(),
            )
        )
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(9, len(opener.urls))
        self.assertNotIn("OPEN_INTEREST", self.sink.payloads)
        self.assertIsNone(raised.exception.failure_response_body)
        self.assertIsNone(raised.exception.failure_raw_binding)
        self.assertTrue(raised.exception.failure_context["response_present"])
        self.assertFalse(raised.exception.failure_context["body_present"])
        self.assertEqual(503, raised.exception.failure_context["http_status"])
        self.assertEqual(
            "PUBLIC_RESPONSE_BODY_READ_FAILED",
            raised.exception.failure_context["failure_codes"][-1],
        )

    def test_success_response_body_read_failure_is_not_zero_byte_capture(self) -> None:
        opener = Opener(
            [ResponseReadFailure(body([{"ts": "1786147200000"}]))]
        )
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))
        self.assertNotIn("SERVER_TIME", self.sink.payloads)
        self.assertIsNone(raised.exception.failure_response_body)
        self.assertFalse(raised.exception.failure_context["body_present"])
        self.assertEqual(
            "PUBLIC_RESPONSE_BODY_READ_FAILED",
            raised.exception.failure_context["failure_codes"][-1],
        )

    def test_success_response_value_and_http_read_failures_are_typed(self) -> None:
        cases = (
            ValueError("closed response stream"),
            http.client.IncompleteRead(b"partial", 10),
        )
        for error in cases:
            with self.subTest(error=type(error).__name__):
                self.tick = 0
                self.sink = RawSink()
                opener = Opener(
                    [ResponseReadFailure(body([{"ts": "1786147200000"}]), error)]
                )
                with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
                    V32OkxPublicBundleTransport(
                        clock=self.clock, opener=opener
                    ).fetch_once(
                        instrument_id="BTC-USDT-SWAP",
                        raw_body_sink=self.sink,
                    )
                self.assertEqual(1, len(opener.urls))
                self.assertNotIn("SERVER_TIME", self.sink.payloads)
                self.assertTrue(raised.exception.failure_context["response_present"])
                self.assertFalse(raised.exception.failure_context["body_present"])
                self.assertEqual(
                    "PUBLIC_RESPONSE_BODY_READ_FAILED",
                    raised.exception.failure_context["failure_codes"][-1],
                )

    def test_status_and_geturl_value_errors_are_not_body_read_failures(self) -> None:
        for response in (
            GeturlValueErrorResponse(body([{"ts": "1786147200000"}])),
            StatusValueErrorResponse(body([{"ts": "1786147200000"}])),
        ):
            with self.subTest(response=type(response).__name__):
                self.tick = 0
                self.sink = RawSink()
                opener = Opener([response])
                with self.assertRaises(ValueError) as raised:
                    V32OkxPublicBundleTransport(
                        clock=self.clock, opener=opener
                    ).fetch_once(
                        instrument_id="BTC-USDT-SWAP",
                        raw_body_sink=self.sink,
                    )
                self.assertNotIn(
                    "BODY_READ_FAILED", str(raised.exception)
                )
                self.assertEqual(1, len(opener.urls))
                self.assertEqual({}, self.sink.payloads)

    def test_http_error_incomplete_read_is_typed_without_empty_capture(self) -> None:
        url = "https://openapi.okx.com/api/v5/public/time"
        opener = Opener(
            [
                urllib.error.HTTPError(
                    url,
                    503,
                    "unavailable",
                    hdrs=None,
                    fp=RaisingReader(
                        http.client.IncompleteRead(b"partial", 10)
                    ),
                )
            ]
        )
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual(1, len(opener.urls))
        self.assertNotIn("SERVER_TIME", self.sink.payloads)
        self.assertTrue(raised.exception.failure_context["response_present"])
        self.assertFalse(raised.exception.failure_context["body_present"])
        self.assertEqual(
            "PUBLIC_RESPONSE_BODY_READ_FAILED",
            raised.exception.failure_context["failure_codes"][-1],
        )

    def test_optional_429_and_503_are_raw_bound_unknown_coverage(self) -> None:
        for status in (429, 503):
            with self.subTest(status=status):
                self.tick = 0
                self.sink = RawSink()
                outcomes = [Response(body([{"ts": "1786147200000"}]))]
                outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
                outcomes.append(
                    Response(body([{"error": "temporarily unavailable"}]), status=status)
                )
                outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
                opener = Opener(outcomes)
                document = loads_json_strict(
                    V32OkxPublicBundleTransport(
                        clock=self.clock, opener=opener
                    ).fetch_once(
                        instrument_id="BTC-USDT-SWAP",
                        raw_body_sink=self.sink,
                    )
                )
                optional = document["components"][8]
                self.assertEqual("UNKNOWN", optional["status"])
                self.assertEqual(status, optional["http_status"])
                self.assertEqual(
                    "PUBLIC_PROVIDER_UNAVAILABLE", optional["error_code"]
                )
                self.assertIsNotNone(optional["raw_binding"])
                self.assertEqual(12, len(opener.urls))

    def test_optional_raw_sink_failure_is_structural_not_unknown(self) -> None:
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(11))
        opener = Opener(outcomes)
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP",
                raw_body_sink=FailingOptionalRawSink(),
            )
        self.assertEqual(9, len(opener.urls))
        self.assertEqual(
            "V32_PUBLIC_COMPONENT_RAW_SINK_WRITE_FAILED",
            raised.exception.failure_code,
        )
        self.assertEqual(
            "PUBLIC_RAW_SINK_STRUCTURAL_FAILURE",
            raised.exception.failure_context["failure_codes"][-1],
        )

    def test_optional_503_capture_failure_aborts_before_next_request(self) -> None:
        outcomes = [Response(body([{"ts": "1786147200000"}]))]
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(7))
        outcomes.append(
            Response(body([{"error": "temporarily unavailable"}]), status=503)
        )
        outcomes.extend(Response(body([{"ok": "1"}])) for _ in range(3))
        opener = Opener(outcomes)
        with self.assertRaises(V32OkxPublicBundleTransportError) as raised:
            V32OkxPublicBundleTransport(
                clock=self.clock, opener=opener
            ).fetch_once(
                instrument_id="BTC-USDT-SWAP",
                raw_body_sink=FailingOptionalRawSink(),
            )
        self.assertEqual(9, len(opener.urls))
        self.assertEqual(
            "V32_PUBLIC_COMPONENT_RAW_SINK_WRITE_FAILED",
            raised.exception.failure_code,
        )
        self.assertEqual(
            "PUBLIC_RAW_SINK_STRUCTURAL_FAILURE",
            raised.exception.failure_context["failure_codes"][-1],
        )

    def test_wrong_instrument_never_opens_a_request(self) -> None:
        transport = V32OkxPublicBundleTransport(
            clock=self.clock, opener=self.opener
        )
        with self.assertRaisesRegex(
            V32OkxPublicBundleTransportError,
            "INSTRUMENT_INVALID",
        ):
            transport.fetch_once(
                instrument_id="ETH-USDT-SWAP", raw_body_sink=self.sink
            )
        self.assertEqual([], self.opener.urls)


if __name__ == "__main__":
    unittest.main()
