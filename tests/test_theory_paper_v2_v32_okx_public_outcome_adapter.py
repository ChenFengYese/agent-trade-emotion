from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
import io
import unittest
import urllib.error

from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    V32PublicTransportUnavailableError,
    build_v32_outcome_tick_attempt,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
    V32OkxPublicMarkCaptureAdapter,
    V32OkxPublicOutcomeAdapterError,
    _V32OpenApiPublicHttpTransport,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_https_route import (
    V32PublicHttpsRouteError,
)


@dataclass
class _Transport:
    response: HttpCapture | None = None
    error: Exception | None = None
    calls: int = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.calls += 1
        if url != OKX_V32_MARK_PRICE_URL or timeout != 15.0:
            raise AssertionError("unexpected public request")
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _attempt() -> dict[str, object]:
    return build_v32_outcome_tick_attempt(
        run_id="v32-target-test",
        tick_index=1,
        planned_tick_at="2026-08-07T10:15:00Z",
        reserved_at="2026-08-07T10:15:01Z",
    )


def _response(
    *,
    status: int = 200,
    final_url: str = OKX_V32_MARK_PRICE_URL,
    raw: bytes | None = None,
) -> HttpCapture:
    return HttpCapture(
        status=status,
        headers={"content-type": "application/json"},
        body=(
            b'{"code":"0","data":[{"instType":"SWAP","instId":"BTC-USDT-SWAP","markPx":"65000","ts":"1786097701000"}]}'
            if raw is None
            else raw
        ),
        received_at=datetime(2026, 8, 7, 10, 15, 2, tzinfo=UTC),
        final_url=final_url,
    )


class V32OkxPublicOutcomeAdapterTests(unittest.TestCase):
    def test_v32_default_transport_preserves_http_error_and_redirect_bodies(self) -> None:
        raw = b'{"code":"500","msg":"provider","data":[]}'
        headers = Message()
        headers["Content-Type"] = "application/json"
        http_error = urllib.error.HTTPError(
            OKX_V32_MARK_PRICE_URL,
            503,
            "unavailable",
            headers,
            io.BytesIO(raw),
        )

        class ErrorOpener:
            def open(self, request, timeout):
                raise http_error

        captured = _V32OpenApiPublicHttpTransport(
            clock=lambda: datetime(2026, 8, 7, 10, 15, 2, tzinfo=UTC),
            opener=ErrorOpener(),
            max_response_bytes=1024 * 1024,
        ).get(OKX_V32_MARK_PRICE_URL, 15.0)
        self.assertEqual(503, captured.status)
        self.assertEqual(raw, captured.body)

        response_headers = headers

        class RedirectResponse:
            status = 200
            headers = response_headers

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def geturl(self):
                return "https://openapi.okx.com/api/v5/public/time"

            def read(self, amount=-1):
                return raw if amount < 0 else raw[:amount]

        class RedirectOpener:
            def open(self, request, timeout):
                return RedirectResponse()

        redirected = _V32OpenApiPublicHttpTransport(
            clock=lambda: datetime(2026, 8, 7, 10, 15, 2, tzinfo=UTC),
            opener=RedirectOpener(),
            max_response_bytes=1024 * 1024,
        ).get(OKX_V32_MARK_PRICE_URL, 15.0)
        self.assertEqual(raw, redirected.body)
        self.assertEqual(
            "https://openapi.okx.com/api/v5/public/time", redirected.final_url
        )

    def test_one_exact_public_get_returns_unparsed_raw_bytes(self) -> None:
        transport = _Transport(response=_response())
        adapter = V32OkxPublicMarkCaptureAdapter(transport=transport)
        result = adapter.capture_public_mark(
            attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
        )
        self.assertEqual(transport.calls, 1)
        self.assertEqual(result["transport_status"], "RESPONSE_CAPTURED")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["final_url"], OKX_V32_MARK_PRICE_URL)
        self.assertEqual(result["received_at"], "2026-08-07T10:15:02Z")
        self.assertIsInstance(result["raw_payload"], bytes)
        self.assertNotIn("value", result)
        self.assertNotIn("fill", result)

    def test_non_200_response_is_returned_raw_for_durable_classification(self) -> None:
        transport = _Transport(response=_response(status=503))
        result = V32OkxPublicMarkCaptureAdapter(
            transport=transport
        ).capture_public_mark(
            attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
        )
        self.assertEqual(transport.calls, 1)
        self.assertEqual(result["transport_status"], "RESPONSE_CAPTURED")
        self.assertEqual(result["http_status"], 503)
        self.assertIsInstance(result["raw_payload"], bytes)

    def test_zero_byte_response_is_returned_for_durable_classification(self) -> None:
        transport = _Transport(response=_response(raw=b""))
        result = V32OkxPublicMarkCaptureAdapter(
            transport=transport
        ).capture_public_mark(
            attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
        )
        self.assertEqual(1, transport.calls)
        self.assertEqual("RESPONSE_CAPTURED", result["transport_status"])
        self.assertEqual(200, result["http_status"])
        self.assertEqual(b"", result["raw_payload"])

    def test_transport_exception_is_not_retried_or_fallback_routed(self) -> None:
        transport = _Transport(error=TimeoutError("bounded public timeout"))
        adapter = V32OkxPublicMarkCaptureAdapter(transport=transport)
        with self.assertRaisesRegex(
            V32PublicTransportUnavailableError, "PUBLIC_TRANSPORT_UNAVAILABLE"
        ):
            adapter.capture_public_mark(
                attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
            )
        self.assertEqual(transport.calls, 1)

    def test_default_transport_wrapper_separates_route_defect_from_physical_failure(self) -> None:
        route = _Transport(
            error=V32PublicHttpsRouteError(
                "V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_UNAVAILABLE"
            ),
        )
        with self.assertRaisesRegex(
            V32OkxPublicOutcomeAdapterError,
            "ROUTE_OR_IDENTITY_INVALID:V32_PUBLIC_HTTPS_ROUTE_CONFIGURATION_UNAVAILABLE",
        ):
            V32OkxPublicMarkCaptureAdapter(
                transport=route
            ).capture_public_mark(
                attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
            )
        self.assertEqual(1, route.calls)

        physical = _Transport(error=TimeoutError())
        failure_time = datetime(2026, 8, 7, 10, 15, 3, tzinfo=UTC)
        with self.assertRaises(V32PublicTransportUnavailableError) as raised:
            V32OkxPublicMarkCaptureAdapter(
                transport=physical,
                clock=lambda: failure_time,
            ).capture_public_mark(
                attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
            )
        self.assertEqual("PUBLIC_TIMEOUT", raised.exception.coverage_failure_code)
        self.assertEqual("2026-08-07T10:15:03Z", raised.exception.failure_at)
        self.assertEqual(1, physical.calls)

        wrapped_404 = _Transport(
            error=urllib.error.HTTPError(
                OKX_V32_MARK_PRICE_URL, 404, "sanitized", {}, None
            ),
        )
        with self.assertRaisesRegex(
            V32OkxPublicOutcomeAdapterError,
            "ROUTE_OR_IDENTITY_INVALID:PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
        ):
            V32OkxPublicMarkCaptureAdapter(
                transport=wrapped_404,
                clock=lambda: failure_time,
            ).capture_public_mark(
                attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
            )
        self.assertEqual(1, wrapped_404.calls)

    def test_wrong_attempt_time_redirect_and_tamper_fail_closed(self) -> None:
        adapter = V32OkxPublicMarkCaptureAdapter(
            transport=_Transport(response=_response())
        )
        with self.assertRaisesRegex(
            V32OkxPublicOutcomeAdapterError, "ATTEMPT_TIME_MISMATCH"
        ):
            adapter.capture_public_mark(
                attempt=_attempt(), requested_at="2026-08-07T10:15:02Z"
            )
        redirected = V32OkxPublicMarkCaptureAdapter(
            transport=_Transport(
                response=_response(
                    final_url="https://openapi.okx.com/api/v5/public/time"
                )
            )
        )
        redirected_result = redirected.capture_public_mark(
            attempt=_attempt(), requested_at="2026-08-07T10:15:01Z"
        )
        self.assertEqual(
            "https://openapi.okx.com/api/v5/public/time",
            redirected_result["final_url"],
        )
        self.assertIsInstance(redirected_result["raw_payload"], bytes)
        tampered = _attempt()
        tampered["source_request_id"] = "different"
        with self.assertRaisesRegex(
            V32OkxPublicOutcomeAdapterError, "ATTEMPT_INVALID"
        ):
            adapter.capture_public_mark(
                attempt=tampered, requested_at="2026-08-07T10:15:01Z"
            )


if __name__ == "__main__":
    unittest.main()
