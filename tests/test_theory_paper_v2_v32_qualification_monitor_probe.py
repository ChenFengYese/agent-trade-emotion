from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_digest
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    V32_QUALIFICATION_CONTEXT_PROFILE,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    V32PublicTransportUnavailableError,
)
from trade_system.theory_paper_v2.domain.v32_qualification_monitor_probe import (
    build_v32_qualification_monitor_probe_attempt_v1,
    build_v32_qualification_monitor_probe_capture_v1,
    build_v32_qualification_monitor_probe_v1,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
    V32OkxPublicMarkCaptureAdapter,
    V32OkxPublicOutcomeAdapterError,
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MutableClock:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class RecordingCapture:
    def __init__(
        self,
        *,
        received_at: str,
        no_response: bool = False,
        captured_at: str | None = None,
        http_status: int = 200,
        final_url: str = OKX_V32_MARK_PRICE_URL,
        raw_payload: bytes | None = None,
        failure_code: str = "PUBLIC_TIMEOUT",
    ) -> None:
        self.received_at = received_at
        self.no_response = no_response
        self.captured_at = captured_at
        self.http_status = http_status
        self.final_url = final_url
        self.raw_payload = raw_payload
        self.failure_code = failure_code
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        if self.no_response:
            return {
                "transport_status": "NO_RESPONSE",
                "source_request_id": attempt["source_request_id"],
                "failure_at": self.received_at,
                "failure_code": self.failure_code,
            }
        provider = datetime.fromisoformat(
            self.received_at.replace("Z", "+00:00")
        ) - timedelta(seconds=1)
        raw = self.raw_payload
        if raw is None:
            raw = json.dumps(
                {
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "instType": "SWAP",
                            "instId": "BTC-USDT-SWAP",
                            "markPx": "65000.1",
                            "ts": str(int(provider.timestamp() * 1000)),
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": attempt["source_request_id"],
            "received_at": self.received_at,
            "captured_at": self.captured_at or self.received_at,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "raw_payload": raw,
        }


class RecordingTransport:
    def __init__(self, *, response: HttpCapture) -> None:
        self.response = response
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.calls += 1
        if url != OKX_V32_MARK_PRICE_URL or timeout != 15.0:
            raise AssertionError("unexpected qualification probe request")
        return self.response


class RaisingCapture:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        raise self.error


class V32QualificationMonitorProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        packet = lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        self.authority = packet["authority_document"]
        self.base = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
        self.schedule = build_v32_qualification_monitor_probe_v1(
            probe_id=f"probe::{self.authority['run_id']}",
            qualification_authority=self.authority,
            final_action_plan_digest=canonical_digest(
                {"kind": "real-test-final-plan", "run": self.authority["run_id"]}
            ),
            selection_consumption_digest=canonical_digest(
                {"kind": "real-test-selection", "run": self.authority["run_id"]}
            ),
            decision_time=iso(self.base),
        )
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def store(self, at: datetime, *, no_response: bool = False):
        clock = MutableClock(iso(at))
        capture = RecordingCapture(received_at=iso(at), no_response=no_response)
        store = LocalV32QualificationMonitorProbeStore(
            Path(self.temp.name), capture_port=capture, clock=clock
        )
        store.initialize(self.schedule)
        return store, clock, capture

    def test_before_due_is_read_only(self):
        store, _, capture = self.store(self.base + timedelta(minutes=14))
        result = store.advance_once()
        self.assertEqual(result["status"], "NOT_DUE")
        self.assertFalse(result["state_changed"])
        self.assertEqual(capture.calls, 0)
        self.assertIsNone(store.load_prefix()["attempt"])

    def test_at_due_and_within_grace_each_reserve_the_only_attempt(self):
        for offset in (15, 29):
            with self.subTest(offset=offset), TemporaryDirectory() as root:
                clock = MutableClock(iso(self.base + timedelta(minutes=offset)))
                capture = RecordingCapture(received_at=clock.value)
                store = LocalV32QualificationMonitorProbeStore(
                    Path(root), capture_port=capture, clock=clock
                )
                store.initialize(self.schedule)
                result = store.advance_once()
                self.assertEqual(result["boundary_kind"], "QUALIFICATION_MONITOR_PROBE_ATTEMPT_RESERVED")
                self.assertEqual(capture.calls, 0)

    def test_after_grace_is_terminal_without_network(self):
        store, _, capture = self.store(self.base + timedelta(minutes=31))
        result = store.advance_once()
        self.assertEqual(result["status"], "FAILED_CLOSED")
        self.assertEqual(capture.calls, 0)
        prefix = store.load_prefix()
        self.assertIsNotNone(prefix["failure"])
        self.assertIsNone(prefix["completion"])

    def test_reserved_attempt_cannot_capture_after_grace(self):
        due = self.base + timedelta(minutes=15)
        store, clock, capture = self.store(due)
        self.assertEqual(
            store.advance_once()["boundary_kind"],
            "QUALIFICATION_MONITOR_PROBE_ATTEMPT_RESERVED",
        )
        clock.value = iso(self.base + timedelta(minutes=31))
        result = store.advance_once()
        self.assertEqual(result["status"], "FAILED_CLOSED")
        self.assertEqual(capture.calls, 0)
        prefix = store.load_prefix()
        self.assertIsNotNone(prefix["failure"])
        self.assertIsNone(prefix["capture"])
        self.assertIsNone(prefix["completion"])

    def test_raw_before_shared_strict_parser_then_replay(self):
        due = self.base + timedelta(minutes=15)
        store, clock, capture = self.store(due)
        self.assertEqual(store.advance_once()["status"], "PENDING")
        clock.value = iso(due + timedelta(seconds=2))
        capture.received_at = clock.value
        self.assertEqual(store.advance_once()["boundary_kind"], "QUALIFICATION_MONITOR_PROBE_RAW_CAPTURED")
        prefix = store.load_prefix()
        self.assertIsNotNone(prefix["capture"])
        self.assertIsNone(prefix["observation"])
        self.assertEqual(store.advance_once()["boundary_kind"], "QUALIFICATION_MONITOR_PROBE_NORMALIZED")
        self.assertEqual(store.advance_once()["status"], "COMPLETE")
        replay = store.replay()
        self.assertTrue(replay["full_replay_verified"])
        self.assertEqual(replay["replay_network_calls"], 0)
        self.assertEqual(capture.calls, 1)

    def test_zero_byte_body_is_durable_before_normalization_failure(self):
        due = self.base + timedelta(minutes=15)
        clock = MutableClock(iso(due))
        capture = RecordingCapture(
            received_at=iso(due + timedelta(seconds=1)),
            raw_payload=b"",
        )
        root = Path(self.temp.name)
        store = LocalV32QualificationMonitorProbeStore(
            root, capture_port=capture, clock=clock
        )
        store.initialize(self.schedule)
        self.assertEqual(
            "QUALIFICATION_MONITOR_PROBE_ATTEMPT_RESERVED",
            store.advance_once()["boundary_kind"],
        )
        captured = store.advance_once()
        self.assertEqual(
            "QUALIFICATION_MONITOR_PROBE_RAW_CAPTURED",
            captured["boundary_kind"],
        )
        durable = store.load_prefix()["capture"]
        self.assertEqual("", durable["raw_payload_base64"])
        self.assertEqual(
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            durable["raw_payload_sha256"],
        )
        clock.value = iso(due + timedelta(seconds=2))
        failed = store.advance_once()
        self.assertEqual("FAILED_CLOSED", failed["status"])
        self.assertIn("NORMALIZATION_FAILED", failed["boundary_kind"])
        self.assertEqual(1, capture.calls)

        never_call = RaisingCapture(AssertionError("network must not reopen"))
        replay_store = LocalV32QualificationMonitorProbeStore(
            root, capture_port=never_call, clock=clock
        )
        replayed = replay_store.advance_once()
        self.assertEqual("FAILED_CLOSED", replayed["status"])
        self.assertEqual(0, never_call.calls)

    def test_no_response_never_becomes_success_root(self):
        due = self.base + timedelta(minutes=15)
        store, _, capture = self.store(due, no_response=True)
        store.advance_once()
        captured = store.advance_once()
        self.assertEqual(
            "QUALIFICATION_MONITOR_PROBE_NO_RESPONSE_CAPTURED",
            captured["boundary_kind"],
        )
        self.assertEqual(
            "PUBLIC_TIMEOUT",
            store.load_prefix()["capture"]["failure_code"],
        )
        result = store.advance_once()
        self.assertEqual(result["status"], "FAILED_CLOSED")
        prefix = store.load_prefix()
        self.assertIsNotNone(prefix["failure"])
        self.assertIsNotNone(prefix["capture"])
        self.assertIsNone(prefix["completion"])
        self.assertEqual(
            "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE:"
            "PUBLIC_TIMEOUT",
            prefix["failure"]["failure_code"],
        )
        self.assertEqual(capture.calls, 1)

    def test_no_response_rejects_response_backed_failure_code_before_capture(self):
        due = self.base + timedelta(minutes=15)
        clock = MutableClock(iso(due))
        capture = RecordingCapture(
            received_at=iso(due),
            no_response=True,
            failure_code="PUBLIC_PROVIDER_UNAVAILABLE",
        )
        store = LocalV32QualificationMonitorProbeStore(
            Path(self.temp.name), capture_port=capture, clock=clock
        )
        store.initialize(self.schedule)
        store.advance_once()
        with self.assertRaisesRegex(
            ValueError, "V32_PROBE_CAPTURE_RESULT_INVALID"
        ):
            store.advance_once()
        self.assertEqual(1, capture.calls)
        self.assertIsNone(store.load_prefix()["capture"])

        attempt = build_v32_qualification_monitor_probe_attempt_v1(
            schedule=self.schedule, reserved_at=iso(due)
        )
        with self.assertRaisesRegex(ValueError, "V32_PROBE_CAPTURE_INVALID"):
            build_v32_qualification_monitor_probe_capture_v1(
                attempt=attempt,
                schedule=self.schedule,
                requested_at=iso(due),
                captured_at=iso(due),
                transport_status="NO_RESPONSE",
                response_received_at=None,
                http_status=None,
                final_url=None,
                raw_payload=None,
                failure_code="PUBLIC_PROVIDER_UNAVAILABLE",
            )

    def test_response_failures_are_raw_captured_before_classification(self):
        due = self.base + timedelta(minutes=15)
        cases = (
            (
                "provider-503",
                {"http_status": 503},
                "QUALIFICATION_MONITOR_PROBE_PUBLIC_SOURCE_UNAVAILABLE",
            ),
            (
                "http-400",
                {"http_status": 400},
                "QUALIFICATION_MONITOR_PROBE_HTTP_STATUS_STRUCTURAL",
            ),
            (
                "redirect",
                {"final_url": "https://openapi.okx.com/api/v5/public/time"},
                "QUALIFICATION_MONITOR_PROBE_RESPONSE_IDENTITY_INVALID",
            ),
            (
                "clock",
                {"received_at": iso(due + timedelta(seconds=1))},
                "QUALIFICATION_MONITOR_PROBE_RESPONSE_CLOCK_INVALID",
            ),
        )
        for label, overrides, expected_boundary in cases:
            with self.subTest(label=label), TemporaryDirectory() as root:
                capture_options = dict(overrides)
                received_at = capture_options.pop(
                    "received_at", iso(due + timedelta(seconds=3))
                )
                clock = MutableClock(iso(due + timedelta(seconds=2)))
                capture_port = RecordingCapture(
                    received_at=received_at,
                    captured_at=iso(due + timedelta(seconds=4)),
                    **capture_options,
                )
                store = LocalV32QualificationMonitorProbeStore(
                    Path(root), capture_port=capture_port, clock=clock
                )
                store.initialize(self.schedule)
                self.assertEqual(
                    "QUALIFICATION_MONITOR_PROBE_ATTEMPT_RESERVED",
                    store.advance_once()["boundary_kind"],
                )
                captured = store.advance_once()
                self.assertEqual(
                    "QUALIFICATION_MONITOR_PROBE_RAW_CAPTURED",
                    captured["boundary_kind"],
                )
                durable_capture = store.load_prefix()["capture"]
                self.assertIsNotNone(durable_capture["raw_payload_sha256"])
                self.assertEqual(
                    capture_options.get("http_status", 200),
                    durable_capture["http_status"],
                )
                failed = store.advance_once()
                self.assertEqual("FAILED_CLOSED", failed["status"])
                self.assertEqual(expected_boundary, failed["boundary_kind"])
                self.assertEqual(
                    durable_capture["qualification_monitor_probe_capture_digest"],
                    failed["failure"]["capture_digest"],
                )

    def test_typed_transport_failure_preserves_physical_leaf_in_durable_capture(self):
        due = self.base + timedelta(minutes=15)
        clock = MutableClock(iso(due))
        capture = RaisingCapture(
            V32PublicTransportUnavailableError(
                "V32_OKX_PUBLIC_TRANSPORT_UNAVAILABLE:PUBLIC_TIMEOUT",
                coverage_failure_code="PUBLIC_TIMEOUT",
                failure_at=iso(due + timedelta(seconds=3)),
            )
        )
        store = LocalV32QualificationMonitorProbeStore(
            Path(self.temp.name), capture_port=capture, clock=clock
        )
        store.initialize(self.schedule)
        store.advance_once()
        result = store.advance_once()
        self.assertEqual(
            "QUALIFICATION_MONITOR_PROBE_NO_RESPONSE_CAPTURED",
            result["boundary_kind"],
        )
        self.assertEqual(
            "PUBLIC_TIMEOUT", store.load_prefix()["capture"]["failure_code"]
        )
        result = store.advance_once()
        self.assertEqual("FAILED_CLOSED", result["status"])
        self.assertTrue(
            result["failure"]["failure_code"].endswith(":PUBLIC_TIMEOUT")
        )
        self.assertEqual(1, capture.calls)

    def test_late_response_normalization_and_completion_each_fail_closed(self):
        due = self.base + timedelta(minutes=15)
        expires = self.base + timedelta(minutes=30)

        with self.subTest(stage="response"), TemporaryDirectory() as root:
            clock = MutableClock(iso(due))
            capture = RecordingCapture(received_at=iso(expires + timedelta(seconds=1)))
            store = LocalV32QualificationMonitorProbeStore(
                Path(root), capture_port=capture, clock=clock
            )
            store.initialize(self.schedule)
            store.advance_once()
            clock.value = iso(due + timedelta(seconds=1))
            result = store.advance_once()
            self.assertEqual(result["status"], "PENDING")
            self.assertEqual(
                "QUALIFICATION_MONITOR_PROBE_RAW_CAPTURED",
                result["boundary_kind"],
            )
            self.assertIsNotNone(store.load_prefix()["capture"])
            result = store.advance_once()
            self.assertEqual(result["status"], "FAILED_CLOSED")
            self.assertIn("RESPONSE_AFTER_WINDOW", result["boundary_kind"])

        with self.subTest(stage="normalization"), TemporaryDirectory() as root:
            clock = MutableClock(iso(due))
            capture = RecordingCapture(received_at=iso(due + timedelta(seconds=1)))
            store = LocalV32QualificationMonitorProbeStore(
                Path(root), capture_port=capture, clock=clock
            )
            store.initialize(self.schedule)
            store.advance_once()
            clock.value = iso(due + timedelta(seconds=1))
            store.advance_once()
            clock.value = iso(expires + timedelta(seconds=1))
            result = store.advance_once()
            self.assertEqual(result["status"], "FAILED_CLOSED")
            self.assertIn("NORMALIZATION_AFTER_WINDOW", result["boundary_kind"])
            self.assertIsNone(store.load_prefix()["observation"])

        with self.subTest(stage="completion"), TemporaryDirectory() as root:
            clock = MutableClock(iso(due))
            capture = RecordingCapture(received_at=iso(due + timedelta(seconds=1)))
            store = LocalV32QualificationMonitorProbeStore(
                Path(root), capture_port=capture, clock=clock
            )
            store.initialize(self.schedule)
            store.advance_once()
            clock.value = iso(due + timedelta(seconds=1))
            store.advance_once()
            store.advance_once()
            clock.value = iso(expires + timedelta(seconds=1))
            result = store.advance_once()
            self.assertEqual(result["status"], "FAILED_CLOSED")
            self.assertIn("COMPLETION_AFTER_WINDOW", result["boundary_kind"])
            self.assertIsNone(store.load_prefix()["completion"])

    def test_real_adapter_accepts_typed_probe_attempt_and_rejects_expired_request_before_network(self):
        reserved = self.base + timedelta(minutes=15)
        attempt = build_v32_qualification_monitor_probe_attempt_v1(
            schedule=self.schedule,
            reserved_at=iso(reserved),
        )
        raw = b'{"code":"0","msg":"","data":[{"instType":"SWAP","instId":"BTC-USDT-SWAP","markPx":"65000.1","ts":"1786148101000"}]}'
        response = HttpCapture(
            status=200,
            headers={"content-type": "application/json"},
            body=raw,
            received_at=reserved + timedelta(seconds=2),
            final_url=OKX_V32_MARK_PRICE_URL,
        )
        transport = RecordingTransport(response=response)
        adapter = V32OkxPublicMarkCaptureAdapter(transport=transport)
        captured = adapter.capture_public_mark(
            attempt=attempt,
            requested_at=iso(reserved + timedelta(seconds=1)),
        )
        self.assertEqual(captured["raw_payload"], raw)
        self.assertEqual(transport.calls, 1)

        expired_transport = RecordingTransport(response=response)
        with self.assertRaisesRegex(
            V32OkxPublicOutcomeAdapterError, "ATTEMPT_TIME_MISMATCH"
        ):
            V32OkxPublicMarkCaptureAdapter(
                transport=expired_transport
            ).capture_public_mark(
                attempt=attempt,
                requested_at=iso(self.base + timedelta(minutes=31)),
            )
        self.assertEqual(expired_transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
