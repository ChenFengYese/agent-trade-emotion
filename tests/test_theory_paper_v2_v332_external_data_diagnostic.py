from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import tempfile
import unittest


_PROTOTYPE_PARENT = (
    Path(__file__).resolve().parents[1]
    / "trade_system"
    / "theory_paper_v2"
    / "v3.3.2"
)
sys.path.insert(0, str(_PROTOTYPE_PARENT))
try:
    from external_data_interface.application.ports import TransportResponse
    from external_data_interface.application.service import ExternalDataService
    from external_data_interface.domain.contracts import CaptureStatus, TransportKind
    from external_data_interface.infrastructure.catalog import SourceCatalog
    from external_data_interface.infrastructure.raw_store import FileRawStore
    from external_data_interface.infrastructure.websocket_transport import pack_messages
finally:
    sys.path.remove(str(_PROTOTYPE_PARENT))


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class _OkxWebSocketTransport:
    def execute(self, _request: object) -> TransportResponse:
        return TransportResponse(
            protocol="WEBSOCKET",
            status_code=101,
            final_url="wss://ws.okx.com:8443/ws/v5/public",
            stored_url="wss://ws.okx.com:8443/ws/v5/public",
            headers={},
            body=pack_messages(
                (
                    (
                        1,
                        b'{"event":"subscribe","arg":{"channel":"books",'
                        b'"instId":"HYPE-USDT-SWAP"}}',
                    ),
                    (
                        1,
                        b'{"arg":{"channel":"books","instId":"HYPE-USDT-SWAP"},'
                        b'"action":"snapshot","data":[{"asks":[],"bids":[],'
                        b'"seqId":1,"ts":"1786536000000"}]}',
                    ),
                )
            ),
            request_started_at="2026-08-12T12:00:00Z",
            response_received_at="2026-08-12T12:00:01Z",
            capture_completed_at="2026-08-12T12:00:02Z",
        )


def _http_response(request_url: str) -> TransportResponse:
    return TransportResponse(
        protocol="HTTP",
        status_code=200,
        final_url=request_url,
        stored_url=request_url,
        headers={"content-type": "application/json"},
        body=b'{"code":"0","msg":"","data":[{"ts":"1786536000000"}]}',
        request_started_at="2026-08-12T12:00:00Z",
        response_received_at="2026-08-12T12:00:01Z",
        capture_completed_at="2026-08-12T12:00:02Z",
    )


class V332ExternalDataDiagnosticTests(unittest.TestCase):
    def test_okx_websocket_does_not_require_http_provider_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = ExternalDataService(
                catalog=SourceCatalog(),
                transport=_OkxWebSocketTransport(),
                store=FileRawStore(Path(temporary)),
                clock=_FixedClock(),
                environment={},
            ).collect(
                "okx.order_book_stream",
                parameters={"instrument_id": "HYPE-USDT-SWAP"},
            )

        self.assertIs(result.status, CaptureStatus.OBSERVED_RAW)
        self.assertIsNone(result.reason)
        self.assertEqual(result.summary["format"], "v332_websocket_message_container")
        self.assertEqual(result.summary["data_message_count"], 1)
        self.assertNotIn("provider_code", result.summary)

    def test_raw_only_capture_audits_as_incomplete_and_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FileRawStore(Path(temporary))
            source = SourceCatalog().get("okx.server_time")
            request = source.build_request(
                parameters={}, environment={}, now=_FixedClock().now()
            )
            store.seal_transport(
                definition=source.definition,
                request=request,
                response=_http_response(request.stored_url),
            )

            audit = store.audit()

        self.assertEqual(audit["capture_count"], 1)
        self.assertEqual(audit["observation_count"], 0)
        self.assertEqual(audit["valid_count"], 0)
        self.assertEqual(audit["invalid_count"], 1)
        self.assertEqual(audit["items"][0]["completion_status"], "INCOMPLETE")
        self.assertFalse(audit["items"][0]["valid"])
        self.assertIn("OBSERVATION_MISSING", audit["items"][0]["errors"])

    def test_order_book_stream_claim_keeps_sequence_checks_unknown(self) -> None:
        definition = SourceCatalog().get("okx.order_book_stream").definition
        claim = definition.claim_ceiling.lower()

        self.assertIs(definition.transport, TransportKind.WEBSOCKET)
        self.assertTrue(definition.stream)
        self.assertIn("finite raw public book frames only", claim)
        self.assertIn("sequence continuity", claim)
        self.assertIn("remain unknown", claim)
        self.assertNotIn("sequence-checked", claim)
        self.assertNotIn("sequence checked", claim)


if __name__ == "__main__":
    unittest.main()
