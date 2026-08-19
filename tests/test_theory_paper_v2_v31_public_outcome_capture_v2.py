from __future__ import annotations

import copy
from datetime import UTC, datetime
from email.message import Message
import io
import unittest
import urllib.error

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    build_minimal_experiment_contract,
    build_typed_path_monitor_plan,
)
from trade_system.theory_paper_v2.domain.v31_monitor_runtime import (
    build_monitor_resolution_attempt,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    verify_public_outcome_capture,
    verify_public_outcome_transport_failure,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.v31_public_outcome_capture_v2 import (
    OkxRawResponseHttpTransportV2,
    OkxPublicOutcomeCaptureAdapterV2,
    V31PublicOutcomeCaptureV2Error,
)


REQUESTED_AT = "2026-08-06T11:00:00Z"


class _Sequence:
    def __init__(self, *values) -> None:
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("test sequence exhausted")
        return self.values.pop(0)


class _ResponseTransport:
    def __init__(self, *, raw: bytes) -> None:
        self.raw = raw
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.calls += 1
        if url != OKX_MARK_PRICE_URL or timeout != 15.0:
            raise AssertionError("unexpected public request")
        return HttpCapture(
            status=503,
            headers={"Content-Type": "application/octet-stream"},
            body=self.raw,
            received_at=datetime(2026, 8, 6, 11, 0, 0, 5_000, tzinfo=UTC),
            final_url=OKX_MARK_PRICE_URL,
        )


class _TimeoutTransport:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.calls += 1
        if url != OKX_MARK_PRICE_URL or timeout != 15.0:
            raise AssertionError("unexpected public request")
        raise TimeoutError("provider-specific detail must not enter evidence")


def _plan_and_attempt() -> tuple[dict, dict]:
    contract = build_minimal_experiment_contract(
        contract_id="contract:v31:capture-adapter-v2",
        run_id="run:v31:capture-adapter-v2",
        frozen_at="2026-08-06T09:00:00Z",
    )
    origins = {
        "accepted_state": {
            "ref": "cycles/0001/accepted-research-state.json",
            "digest": "a" * 64,
        },
        "path_set": {"ref": "path-set:1", "digest": "b" * 64},
        "path": {"ref": "path:lead:1", "digest": "c" * 64},
        "hypothesis_revision": {"ref": "hypothesis:lead:r1", "digest": "d" * 64},
        "expectation_revision": {"ref": "expectation:lead:r1", "digest": "e" * 64},
    }
    observable = "metric:mark-price-usdt"
    rules = (
        FrozenMonitorRule(
            rule_id="confirmation",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=observable,
            operator=MonitorOperator.GT,
            expected="65000",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="contradiction",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=observable,
            operator=MonitorOperator.LT,
            expected="64000",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="falsifier",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=observable,
            operator=MonitorOperator.LTE,
            expected="63000",
            unit="USDT_PER_BTC",
        ),
    )
    plan = build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id="monitor:1",
        cycle_id="cycle:1",
        cycle_index=1,
        origin_bindings=origins,
        decision_at="2026-08-06T10:00:00Z",
        observable_ref=observable,
        source_request_id="okx-public-mark-price:1",
        rules=rules,
    )
    attempt = build_monitor_resolution_attempt(
        run_id=plan["run_id"],
        cycle_index=1,
        monitor_plan_digest=plan["monitor_plan_digest"],
        requested_at=REQUESTED_AT,
        previous_outcome_receipt_digest=None,
    )
    return plan, attempt


class V31PublicOutcomeCaptureAdapterV2Tests(unittest.TestCase):
    def test_default_transport_preserves_http_error_response_bytes(self) -> None:
        raw = b"\xffprovider-503-body\x00"
        headers = Message()
        headers["Content-Type"] = "application/octet-stream"
        response = urllib.error.HTTPError(
            OKX_MARK_PRICE_URL,
            503,
            "unavailable",
            headers,
            io.BytesIO(raw),
        )

        class _ErrorOpener:
            def open(self, request, timeout):
                raise response

        transport = OkxRawResponseHttpTransportV2(
            clock=lambda: datetime(2026, 8, 6, 11, 0, 0, tzinfo=UTC)
        )
        transport._opener = _ErrorOpener()

        captured = transport.get(OKX_MARK_PRICE_URL, 15.0)

        self.assertEqual(503, captured.status)
        self.assertEqual(raw, captured.body)
        self.assertEqual(OKX_MARK_PRICE_URL, captured.final_url)

    def test_response_bytes_and_metadata_are_captured_without_interpretation(self) -> None:
        raw = b"\xffnot-json\x00provider-body\r\n"
        transport = _ResponseTransport(raw=raw)
        adapter = OkxPublicOutcomeCaptureAdapterV2(
            transport=transport,
            clock=_Sequence(
                datetime(2026, 8, 6, 11, 0, 0, 1_000, tzinfo=UTC)
            ),
            monotonic_ns=_Sequence(1_000_000_000, 1_004_000_000),
        )
        plan, attempt = _plan_and_attempt()

        envelope = adapter.capture_public_outcome(
            monitor_plan=plan,
            attempt=attempt,
            requested_at=REQUESTED_AT,
        )

        self.assertEqual(1, transport.calls)
        self.assertEqual("RESPONSE_CAPTURED", envelope["transport_status"])
        self.assertEqual(raw, envelope["raw_payload"])
        self.assertIsNone(envelope["transport_failure"])
        captured = envelope["capture"]
        self.assertEqual(503, captured["status_code"])
        self.assertEqual("application/octet-stream", captured["content_type"])
        self.assertEqual(4, captured["monotonic_elapsed_ms"])
        self.assertEqual(
            captured["capture_digest"],
            verify_public_outcome_capture(captured, raw_payload=raw),
        )

    def test_timeout_becomes_typed_no_response_without_exception_text(self) -> None:
        transport = _TimeoutTransport()
        adapter = OkxPublicOutcomeCaptureAdapterV2(
            transport=transport,
            clock=_Sequence(
                datetime(2026, 8, 6, 11, 0, 0, 1_000, tzinfo=UTC),
                datetime(2026, 8, 6, 11, 0, 0, 8_000, tzinfo=UTC),
            ),
            monotonic_ns=_Sequence(2_000_000_000, 2_007_000_000),
        )
        plan, attempt = _plan_and_attempt()

        envelope = adapter.capture_public_outcome(
            monitor_plan=plan,
            attempt=attempt,
            requested_at=REQUESTED_AT,
        )

        self.assertEqual(1, transport.calls)
        self.assertEqual("NO_RESPONSE", envelope["transport_status"])
        self.assertIsNone(envelope["capture"])
        self.assertIsNone(envelope["raw_payload"])
        failure = envelope["transport_failure"]
        self.assertEqual("PUBLIC_TIMEOUT", failure["failure_code"])
        self.assertEqual(7, failure["monotonic_elapsed_ms"])
        self.assertEqual(
            failure["transport_failure_digest"],
            verify_public_outcome_transport_failure(failure),
        )
        self.assertNotIn("exception", failure)
        self.assertNotIn("failure_summary", failure)
        self.assertNotIn("provider-specific detail", str(failure))

    def test_invalid_scope_fails_before_clock_or_get(self) -> None:
        plan, _ = _plan_and_attempt()
        invalid = copy.deepcopy(plan)
        invalid.pop("monitor_plan_digest")
        invalid["observable"]["source_endpoint"] = (
            "https://www.okx.com/api/v5/account/balance"
        )
        invalid = self_digest(invalid, "monitor_plan_digest")
        attempt = build_monitor_resolution_attempt(
            run_id=invalid["run_id"],
            cycle_index=1,
            monitor_plan_digest=invalid["monitor_plan_digest"],
            requested_at=REQUESTED_AT,
            previous_outcome_receipt_digest=None,
        )
        transport = _ResponseTransport(raw=b"must-not-be-requested")
        adapter = OkxPublicOutcomeCaptureAdapterV2(
            transport=transport,
            clock=_Sequence(),
            monotonic_ns=_Sequence(),
        )

        with self.assertRaisesRegex(
            V31PublicOutcomeCaptureV2Error, "V31_CAPTURE_SCOPE_INVALID"
        ):
            adapter.capture_public_outcome(
                monitor_plan=invalid,
                attempt=attempt,
                requested_at=REQUESTED_AT,
            )
        self.assertEqual(0, transport.calls)


if __name__ == "__main__":
    unittest.main()
