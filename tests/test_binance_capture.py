import tempfile
import unittest
from datetime import timedelta

from trade_system.binance import BinanceCaptureSession
from trade_system.event_store import EventStore
from trade_system.types import utc_now


class BinanceCaptureTests(unittest.TestCase):
    def test_agg_trade_side_and_depth_sequence_are_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = BinanceCaptureSession(EventStore(temp_dir), "ws-1")
            received = utc_now()
            result = session.ingest(
                "aggTrade",
                {"e": "aggTrade", "E": 1700000000000, "a": 1, "p": "100", "q": "2", "m": True},
                received_at=received,
            )
            self.assertTrue(result.availability_written)
            record = list(session.store.iter_availability())[0]
            self.assertEqual("SELL", record.normalized["side"])
            self.assertGreaterEqual(record.available_at, received)

    def test_parse_failure_preserves_raw_without_availability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            session = BinanceCaptureSession(store, "ws-1")
            result = session.ingest("depthUpdate", {"e": "depthUpdate", "E": 1700000000000})
            self.assertFalse(result.availability_written)
            self.assertIn("missing required field", result.parse_error)
            self.assertEqual(1, sum(1 for _ in store.iter_raw()))
            self.assertEqual(0, sum(1 for _ in store.iter_availability()))

    def test_force_order_is_captured_as_censored_liquidation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = BinanceCaptureSession(EventStore(temp_dir), "ws-force")
            result = session.ingest("btcusdt@forceOrder", {
                "e": "forceOrder", "E": 1700000000000,
                "o": {"S": "SELL", "ap": "100", "q": "2", "o": "LIMIT"},
            })
            self.assertTrue(result.availability_written)
            record = list(session.store.iter_availability())[0]
            self.assertEqual("liquidation", record.normalized["kind"])
            self.assertTrue(record.normalized["censored"])

    def test_exchange_info_keeps_target_contract_filters_as_actual_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = BinanceCaptureSession(EventStore(temp_dir), "ws-metadata", instrument="BTCUSDT")
            result = session.ingest("exchangeInfo", {
                "serverTime": 1700000000000,
                "symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL", "baseAsset": "BTC", "quoteAsset": "USDT", "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.1"}]}],
            })
            self.assertTrue(result.availability_written)
            record = list(session.store.iter_availability())[0]
            self.assertEqual("exchange_info", record.normalized["kind"])
            self.assertEqual("TRADING", record.normalized["status"])
            self.assertEqual("PRICE_FILTER", record.normalized["filters"][0]["filterType"])
