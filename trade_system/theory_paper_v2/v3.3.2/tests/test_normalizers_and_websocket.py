from __future__ import annotations

import json
import unittest

from external_data_interface.infrastructure.normalizers import normalize_payload
from external_data_interface.infrastructure.websocket_transport import (
    pack_messages,
    summarize_websocket_container,
    unpack_messages,
)


class NormalizerAndWebSocketTests(unittest.TestCase):
    def test_okx_provider_code_and_records_are_visible(self) -> None:
        summary = normalize_payload(
            source_id="okx.taker_volume",
            raw=b'{"code":"0","msg":"","data":[["1","2","3"]]}',
            content_type="application/json",
        )
        self.assertEqual(summary["provider_code"], "0")
        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(
            summary["record_fields"], ["ts", "buy_volume", "sell_volume"]
        )
        self.assertEqual(summary["preview"][0]["buy_volume"], "2")

    def test_cftc_normalizer_filters_bitcoin_codes(self) -> None:
        raw = (
            b'Market_and_Exchange_Names,CFTC_Contract_Market_Code,Open_Interest_All\n'
            b'BITCOIN - CME,133741,100\nMICRO BITCOIN - CME,133742,200\nSOFR,134741,300\n'
        )
        summary = normalize_payload(
            source_id="cftc.cot_current", raw=raw, content_type="text/csv"
        )
        self.assertEqual(summary["bitcoin_contract_record_count"], 2)

    def test_websocket_container_preserves_text_and_binary_payloads(self) -> None:
        text = json.dumps(
            {"arg": {"channel": "books"}, "data": [{"ts": "1"}]}
        ).encode()
        raw = pack_messages(((1, text), (2, b"\x01\x02")))
        self.assertEqual(unpack_messages(raw), ((1, text), (2, b"\x01\x02")))
        summary = summarize_websocket_container(raw)
        self.assertEqual(summary["message_count"], 2)
        self.assertEqual(summary["data_message_count"], 1)
        self.assertEqual(summary["binary_message_count"], 1)

    def test_eia_manifest_exposes_official_bulk_download_metadata(self) -> None:
        raw = b'{"dataset":{"PET":{"name":"Petroleum","last_updated":"2026-08-11","accessURL":"https://www.eia.gov/opendata/bulk/PET.zip","temporal":"weekly"}}}'
        summary = normalize_payload(
            source_id="eia.bulk_manifest", raw=raw, content_type="application/json"
        )
        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["preview"][0]["identifier"], "PET")

    def test_alphavantage_daily_series_is_counted(self) -> None:
        raw = json.dumps(
            {
                "Meta Data": {"2. Symbol": "SPY"},
                "Time Series (Daily)": {
                    "2026-08-12": {
                        "1. open": "1",
                        "2. high": "2",
                        "3. low": "0.5",
                        "4. close": "1.5",
                        "5. volume": "100",
                    }
                },
            }
        ).encode()
        summary = normalize_payload(
            source_id="alphavantage.daily", raw=raw, content_type="application/json"
        )
        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["preview"][0]["date"], "2026-08-12")
        self.assertIsNone(summary["provider_error_field"])

    def test_youtube_error_is_visible_without_becoming_records(self) -> None:
        raw = json.dumps(
            {
                "error": {
                    "code": 403,
                    "status": "PERMISSION_DENIED",
                    "message": "Requests are blocked.",
                    "errors": [{"reason": "forbidden"}],
                }
            }
        ).encode()
        summary = normalize_payload(
            source_id="youtube.search", raw=raw, content_type="application/json"
        )
        self.assertEqual(summary["record_count"], 0)
        self.assertEqual(summary["provider_error_code"], 403)
        self.assertEqual(summary["provider_error_reasons"], ["forbidden"])

    def test_duplicate_json_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "V332_JSON_DUPLICATE_KEY"):
            normalize_payload(
                source_id="okx.server_time",
                raw=b'{"code":"0","code":"1","data":[]}',
                content_type="application/json",
            )


if __name__ == "__main__":
    unittest.main()
