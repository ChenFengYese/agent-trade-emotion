from __future__ import annotations

from unittest.mock import patch
import traceback
import unittest
import urllib.error
import urllib.request

from trade_system.theory_paper_v2.infrastructure.v32_public_https_route import (
    V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
    V32_PUBLIC_REQUEST_HEADERS_DIGEST,
    V32PublicHttpsRouteError,
    V32SystemPublicHttpsOpener,
    _FrozenHttpsProxyHandler,
    build_v32_public_get_request_v1,
    classify_v32_public_https_failure_v1,
)


URL = "https://openapi.okx.com/api/v5/public/time"


class _Underlying:
    def __init__(self) -> None:
        self.calls = 0
        self.requests = []

    def open(self, request, timeout):
        self.calls += 1
        self.requests.append(request)
        return object()


class V32PublicHttpsRouteTests(unittest.TestCase):
    def request(self, *, url: str = URL, headers=None):
        return urllib.request.Request(
            url,
            method="GET",
            headers=headers or {
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-v3.2-public-research/1.0",
            },
        )

    def test_direct_and_noncredential_system_proxy_are_single_frozen_routes(self):
        self.assertEqual(
            "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3",
            V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
        )
        cases = (
            ({}, "DIRECT_NO_SYSTEM_HTTPS_PROXY"),
            (
                {"https": "http://127.0.0.1:8080"},
                "SYSTEM_HTTPS_PROXY_NON_CREDENTIAL",
            ),
        )
        for proxies, expected_mode in cases:
            with self.subTest(expected_mode=expected_mode):
                underlying = _Underlying()
                with patch(
                    "urllib.request.build_opener", return_value=underlying
                ) as build:
                    route = V32SystemPublicHttpsOpener(
                        proxy_supplier=lambda value=proxies: value,
                        bypass_checker=lambda _host: False,
                    )
                    route.open(self.request(), timeout=10)
                    self.assertEqual(expected_mode, route.route_mode)
                    self.assertEqual(1, underlying.calls)
                    self.assertEqual(1, build.call_count)
                    self.assertEqual(
                        V32_PUBLIC_HTTPS_ROUTE_POLICY_ID,
                        route.route_policy_id,
                    )
                    handlers = build.call_args.args
                    if proxies:
                        self.assertIsInstance(
                            handlers[0], _FrozenHttpsProxyHandler
                        )
                        chained = self.request()
                        handlers[0].https_open(chained)
                        self.assertEqual("openapi.okx.com", chained._tunnel_host)
                        self.assertEqual("127.0.0.1:8080", chained.host)
                    else:
                        self.assertIsInstance(
                            handlers[0], urllib.request.ProxyHandler
                        )

    def test_proxy_route_does_not_recheck_global_bypass_after_resolution(self):
        underlying = _Underlying()
        with patch(
            "urllib.request.build_opener", return_value=underlying
        ) as build, patch(
            "urllib.request.proxy_bypass",
            side_effect=AssertionError("global bypass must not be consulted"),
        ):
            route = V32SystemPublicHttpsOpener(
                proxy_supplier=lambda: {"https": "http://127.0.0.1:8080"},
                bypass_checker=lambda _host: False,
            )
            route.open(self.request(), timeout=10)
        self.assertEqual(1, underlying.calls)
        handler = build.call_args.args[0]
        chained = self.request()
        handler.https_open(chained)
        self.assertEqual("openapi.okx.com", chained._tunnel_host)

    def test_fixed_headers_and_caller_injection_fail_before_network(self):
        request = build_v32_public_get_request_v1(URL)
        self.assertEqual(
            {
                "accept": "application/json",
                "user-agent": "agent-trade-emotion-v3.2-public-research/1.0",
            },
            {name.casefold(): value for name, value in request.header_items()},
        )
        self.assertEqual(
            "V32_FIXED_PUBLIC_RESEARCH_JSON_REQUEST_HEADERS_V1",
            V32_PUBLIC_REQUEST_HEADER_POLICY_ID,
        )
        self.assertRegex(V32_PUBLIC_REQUEST_HEADERS_DIGEST, r"^[0-9a-f]{64}$")
        invalid_headers = (
            {"Accept": "application/json"},
            {
                "Accept": "application/json",
                "User-Agent": "rotating-identity/9.9",
            },
            {
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-v3.2-public-research/1.0",
                "Cookie": "forbidden",
            },
            {
                "Accept": "application/json",
                "User-Agent": "agent-trade-emotion-v3.2-public-research/1.0",
                "OK-ACCESS-KEY": "forbidden",
            },
        )
        for headers in invalid_headers:
            with self.subTest(headers=tuple(headers)), patch(
                "urllib.request.build_opener"
            ) as build:
                route = V32SystemPublicHttpsOpener(
                    proxy_supplier=lambda: {},
                    bypass_checker=lambda _host: False,
                )
                with self.assertRaisesRegex(
                    V32PublicHttpsRouteError, "TARGET_INVALID"
                ):
                    route.open(self.request(headers=headers), timeout=10)
                self.assertEqual(0, build.call_count)

    def test_plain_and_percent_encoded_proxy_userinfo_fail_before_network(self):
        secrets = (
            "http://alice:topsecret@127.0.0.1:8080",
            "http://alice%3Atopsecret@127.0.0.1:8080",
        )
        for proxy in secrets:
            with self.subTest(proxy_kind="encoded" if "%" in proxy else "plain"):
                with patch("urllib.request.build_opener") as build:
                    route = V32SystemPublicHttpsOpener(
                        proxy_supplier=lambda value=proxy: {"https": value},
                        bypass_checker=lambda _host: False,
                    )
                    with self.assertRaisesRegex(
                        V32PublicHttpsRouteError,
                        "PROXY_CREDENTIALS_FORBIDDEN",
                    ) as raised:
                        route.open(self.request(), timeout=10)
                    self.assertEqual(0, build.call_count)
                    self.assertNotIn("topsecret", str(raised.exception))
                    self.assertNotIn("alice", repr(raised.exception))

    def test_no_proxy_bypass_redirect_surface_and_sensitive_headers_are_rejected(self):
        with patch("urllib.request.build_opener") as build:
            bypass = V32SystemPublicHttpsOpener(
                proxy_supplier=lambda: {"https": "http://127.0.0.1:8080"},
                bypass_checker=lambda _host: True,
            )
            with self.assertRaisesRegex(
                V32PublicHttpsRouteError, "PROXY_BYPASS_FORBIDDEN"
            ):
                bypass.open(self.request(), timeout=10)
            self.assertEqual(0, build.call_count)

        invalid_requests = (
            self.request(url="https://www.okx.com/api/v5/public/time"),
            self.request(url="https://openapi.okx.com/api/v5/trade/order"),
            self.request(headers={"Authorization": "forbidden"}),
            urllib.request.Request(URL, method="POST"),
        )
        for request in invalid_requests:
            with self.subTest(url=request.full_url, method=request.get_method()):
                with patch("urllib.request.build_opener") as build:
                    route = V32SystemPublicHttpsOpener(
                        proxy_supplier=lambda: {},
                        bypass_checker=lambda _host: False,
                    )
                    with self.assertRaisesRegex(
                        V32PublicHttpsRouteError, "TARGET_INVALID"
                    ):
                        route.open(request, timeout=10)
                    self.assertEqual(0, build.call_count)

    def test_proxy_supplier_and_bypass_prose_never_leak_through_traceback(self):
        secret = "alice:topsecret@private-proxy.example"

        def supplier_failure():
            raise RuntimeError(secret)

        def bypass_failure(_host):
            raise RuntimeError(secret)

        routes = (
            V32SystemPublicHttpsOpener(
                proxy_supplier=supplier_failure,
                bypass_checker=lambda _host: False,
            ),
            V32SystemPublicHttpsOpener(
                proxy_supplier=lambda: {"https": "http://127.0.0.1:8080"},
                bypass_checker=bypass_failure,
            ),
        )
        for route in routes:
            with self.subTest(route=route), self.assertRaises(
                V32PublicHttpsRouteError
            ) as raised:
                route.open(self.request(), timeout=10)
            rendered = "".join(traceback.format_exception(raised.exception))
            self.assertNotIn(secret, rendered)
            self.assertIsNone(raised.exception.__cause__)
            self.assertTrue(raised.exception.__suppress_context__)

    def test_http_status_classification_never_launders_4xx_as_coverage(self):
        expected = {
            301: "PUBLIC_REDIRECT_FORBIDDEN",
            400: "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
            401: "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
            403: "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
            404: "PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE",
            429: "PUBLIC_PROVIDER_UNAVAILABLE",
            500: "PUBLIC_PROVIDER_UNAVAILABLE",
            503: "PUBLIC_PROVIDER_UNAVAILABLE",
        }
        for status, failure_code in expected.items():
            with self.subTest(status=status):
                error = urllib.error.HTTPError(
                    URL, status, "sanitized", {}, None
                )
                self.assertEqual(
                    failure_code,
                    classify_v32_public_https_failure_v1(error),
                )


if __name__ == "__main__":
    unittest.main()
