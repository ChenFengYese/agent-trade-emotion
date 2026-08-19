from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from external_data_interface.application.ports import HttpRequest, TransportResponse
from external_data_interface.application.service import ExternalDataService
from external_data_interface.domain.contracts import CaptureStatus
from external_data_interface.infrastructure.catalog import SourceCatalog
from external_data_interface.infrastructure.raw_store import FileRawStore, RawStoreError
from external_data_interface.infrastructure.websocket_transport import pack_messages


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class FakeTransport:
    def execute(self, request: HttpRequest) -> TransportResponse:
        body = b'{"code":"0","msg":"","data":[{"ts":"1786536000000"}]}'
        return TransportResponse(
            protocol="HTTP",
            status_code=200,
            final_url=request.url,
            stored_url=request.stored_url,
            headers={"content-type": "application/json"},
            body=body,
            request_started_at="2026-08-12T12:00:00Z",
            response_received_at="2026-08-12T12:00:01Z",
            capture_completed_at="2026-08-12T12:00:02Z",
        )


class AlphaErrorTransport:
    def execute(self, request: HttpRequest) -> TransportResponse:
        body = b'{"Information":"rate limit reached"}'
        return TransportResponse(
            protocol="HTTP",
            status_code=200,
            final_url=request.url,
            stored_url=request.stored_url,
            headers={"content-type": "application/json"},
            body=body,
            request_started_at="2026-08-12T12:00:00Z",
            response_received_at="2026-08-12T12:00:01Z",
            capture_completed_at="2026-08-12T12:00:02Z",
        )


class OkxWebSocketTransport:
    def execute(self, request) -> TransportResponse:
        body = pack_messages(
            (
                (1, b'{"event":"subscribe","arg":{"channel":"books","instId":"HYPE-USDT-SWAP"}}'),
                (1, b'{"arg":{"channel":"books","instId":"HYPE-USDT-SWAP"},"action":"snapshot","data":[{"asks":[],"bids":[],"seqId":1,"ts":"1786536000000"}]}'),
            )
        )
        return TransportResponse(
            protocol="WEBSOCKET",
            status_code=101,
            final_url=request.url,
            stored_url=request.stored_url,
            headers={},
            body=body,
            request_started_at="2026-08-12T12:00:00Z",
            response_received_at="2026-08-12T12:00:01Z",
            capture_completed_at="2026-08-12T12:00:02Z",
        )


class RawStoreAndServiceTests(unittest.TestCase):
    def test_service_seals_raw_and_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FileRawStore(Path(temporary))
            service = ExternalDataService(
                catalog=SourceCatalog(),
                transport=FakeTransport(),
                store=store,
                clock=FixedClock(),
                environment={},
            )
            result = service.collect("okx.server_time")
            self.assertIs(result.status, CaptureStatus.OBSERVED_RAW)
            self.assertIsNotNone(result.raw_ref)
            body = store.load_raw(result.raw_ref or {})
            self.assertEqual(hashlib.sha256(body).hexdigest(), result.raw_ref["sha256"])
            observation = json.loads(Path(result.observation_path or "").read_text())
            self.assertEqual(observation["raw_sha256"], result.raw_ref["sha256"])
            self.assertEqual(observation["available_at"], "2026-08-12T12:00:01Z")
            audit = store.audit()
            self.assertEqual(audit["capture_count"], 1)
            self.assertEqual(audit["valid_count"], 1)
            self.assertEqual(audit["observation_count"], 1)

    def test_store_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FileRawStore(Path(temporary))
            request = SourceCatalog().get("okx.server_time").build_request(
                parameters={}, environment={}, now=FixedClock().now()
            )
            response = FakeTransport().execute(request)
            reference = store.seal_transport(
                definition=SourceCatalog().get("okx.server_time").definition,
                request=request,
                response=response,
            )
            Path(reference["body_path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(RawStoreError, "V332_RAW_SIZE_MISMATCH"):
                store.load_raw(reference)
            audit = store.audit()
            self.assertEqual(audit["invalid_count"], 1)
            self.assertIn("BODY_SHA256_MISMATCH", audit["items"][0]["errors"])

    def test_raw_only_crash_window_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FileRawStore(Path(temporary))
            request = SourceCatalog().get("okx.server_time").build_request(
                parameters={}, environment={}, now=FixedClock().now()
            )
            response = FakeTransport().execute(request)
            store.seal_transport(
                definition=SourceCatalog().get("okx.server_time").definition,
                request=request,
                response=response,
            )
            audit = store.audit()
            self.assertEqual(audit["valid_count"], 0)
            self.assertEqual(audit["invalid_count"], 1)
            self.assertEqual(audit["items"][0]["completion_status"], "INCOMPLETE")
            self.assertIn("OBSERVATION_MISSING", audit["items"][0]["errors"])

    def test_okx_websocket_is_not_rejected_for_absent_http_provider_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = ExternalDataService(
                catalog=SourceCatalog(),
                transport=OkxWebSocketTransport(),
                store=FileRawStore(Path(temporary)),
                clock=FixedClock(),
                environment={},
            ).collect(
                "okx.order_book_stream",
                parameters={"instrument": "HYPE-USDT-SWAP"},
            )
            self.assertIs(result.status, CaptureStatus.OBSERVED_RAW)
            self.assertIsNone(result.reason)
            self.assertEqual(result.summary["data_message_count"], 1)

    def test_missing_key_does_not_dispatch_or_create_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            service = ExternalDataService(
                catalog=SourceCatalog(),
                transport=FakeTransport(),
                store=FileRawStore(Path(temporary)),
                clock=FixedClock(),
                environment={},
            )
            result = service.collect("fred.series")
            self.assertIs(result.status, CaptureStatus.WAITING_USER_CONFIG)
            self.assertIsNone(result.raw_ref)
            self.assertFalse((Path(temporary) / "captures").exists())

    def test_alphavantage_http_200_error_payload_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            service = ExternalDataService(
                catalog=SourceCatalog(),
                transport=AlphaErrorTransport(),
                store=FileRawStore(Path(temporary)),
                clock=FixedClock(),
                environment={"ALPHAVANTAGE_API_KEY": "secret"},
            )
            result = service.collect("alphavantage.daily")
            self.assertIs(result.status, CaptureStatus.CAPTURE_FAILED)
            self.assertEqual(
                result.reason, "ALPHAVANTAGE_PROVIDER_ERROR:Information"
            )

    def test_manual_google_trends_csv_is_raw_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "trends.csv"
            source.write_text("Week,bitcoin\n2026-08-02,40\n2026-08-09,55\n")
            output = Path(temporary) / "output"
            service = ExternalDataService(
                catalog=SourceCatalog(),
                transport=FakeTransport(),
                store=FileRawStore(output),
                clock=FixedClock(),
                environment={},
            )
            result = service.import_manual(
                "google_trends.manual_csv",
                source_file=source,
                observed_at="2026-08-09T00:00:00Z",
                available_at="2026-08-12T11:00:00Z",
                source_url="https://trends.google.com/trends/explore?q=bitcoin",
            )
            self.assertIs(result.status, CaptureStatus.OBSERVED_RAW)
            self.assertEqual(result.summary["record_count"], 2)
            capture = json.loads(Path(result.raw_ref["capture_path"]).read_text())
            self.assertEqual(
                capture["response"]["final_url"],
                "https://trends.google.com/trends/explore?q=bitcoin",
            )


if __name__ == "__main__":
    unittest.main()
