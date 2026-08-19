import asyncio
import json
import tempfile
import unittest

from trade_system.binance import BinanceCaptureSession
from trade_system.event_store import EventStore
from trade_system.market_runtime import BinancePublicMarketRuntime, BinanceRestSnapshotClient, stream_urls
from trade_system.types import BookHealth


class MarketRuntimeTests(unittest.TestCase):
    def test_routes_follow_public_and_market_split(self):
        routes = stream_urls("BTCUSDT")
        self.assertIn("/public/stream?streams=btcusdt@depth@100ms", routes["depth"])
        self.assertIn("/market/stream?streams=btcusdt@aggTrade/btcusdt@markPrice@1s", routes["market"])
        self.assertIn("/btcusdt@forceOrder", routes["market"])

    def test_buffers_depth_then_applies_injected_rest_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-1")
            market = BinanceCaptureSession(store, "market-1")
            client = BinanceRestSnapshotClient(lambda _url, _timeout: {
                "lastUpdateId": 100,
                "bids": [["99", "1"]],
                "asks": [["101", "1"]],
            })
            runtime = BinancePublicMarketRuntime(depth_session=depth, market_session=market, snapshot_client=client)
            runtime.process_envelope("depth", {"stream": "btcusdt@depth@100ms", "data": {
                "e": "depthUpdate", "E": 1700000000000, "U": 101, "u": 101, "pu": 100, "b": [["99", "2"]], "a": []
            }})
            self.assertFalse(runtime._snapshot_loaded)
            runtime.capture_snapshot()
            self.assertTrue(runtime._snapshot_loaded)
            self.assertEqual(BookHealth.VALID, runtime.book.health)
            self.assertEqual(101, runtime.book.last_update_id)
            self.assertEqual(2, runtime.stats.raw_captured)
            self.assertEqual(2, runtime.stats.availability_written)

    def test_no_depth_message_terminates_without_snapshot_wait_hang(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-timeout")
            market = BinanceCaptureSession(store, "market-timeout")

            class TimedOutSocket:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    raise asyncio.TimeoutError()

            def connect(*args, **kwargs):
                self.assertEqual(1, kwargs["close_timeout"])
                return TimedOutSocket()

            runtime = BinancePublicMarketRuntime(depth_session=depth, market_session=market, connect=connect)
            stats = asyncio.run(runtime.run(duration_seconds=0.01))
            self.assertEqual(0, stats.snapshot_fetches)
            self.assertTrue(any("depth receive idle timeout" in item for item in stats.errors))

    def test_invalid_book_does_not_repeat_the_same_gap_for_every_later_delta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-gap")
            market = BinanceCaptureSession(store, "market-gap")
            runtime = BinancePublicMarketRuntime(depth_session=depth, market_session=market)
            runtime.apply_snapshot({"lastUpdateId": 100, "bids": [["99", "1"]], "asks": [["101", "1"]]})
            gap = {"stream": "btcusdt@depth@100ms", "data": {
                "e": "depthUpdate", "E": 1700000000000, "U": 102, "u": 102, "pu": 99, "b": [], "a": []
            }}
            runtime.process_envelope("depth", gap)
            runtime.process_envelope("depth", gap)
            self.assertEqual(BookHealth.INVALID, runtime.book.health)
            self.assertEqual(1, runtime.stats.book_gaps)

    def test_open_interest_is_polled_and_captured_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-oi")
            market = BinanceCaptureSession(store, "market-oi")
            oi = BinanceCaptureSession(store, "oi-1")

            class TimedOutSocket:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    raise asyncio.TimeoutError()

            client = BinanceRestSnapshotClient(lambda url, _timeout: {
                "symbol": "BTCUSDT", "openInterest": "123", "time": 1700000000000
            } if "openInterest" in url else (_ for _ in ()).throw(AssertionError(url)))
            runtime = BinancePublicMarketRuntime(
                depth_session=depth,
                market_session=market,
                oi_session=oi,
                snapshot_client=client,
                connect=lambda *args, **kwargs: TimedOutSocket(),
                open_interest_interval_seconds=60,
            )
            stats = asyncio.run(runtime.run(duration_seconds=0.01))
            self.assertEqual(1, stats.open_interest_polls)
            self.assertEqual(1, stats.availability_written)
            self.assertEqual("oi", list(store.iter_availability())[0].normalized["kind"])

    def test_exchange_info_is_captured_once_as_metadata_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-meta")
            market = BinanceCaptureSession(store, "market-meta")
            metadata = BinanceCaptureSession(store, "metadata-1")

            class TimedOutSocket:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    raise asyncio.TimeoutError()

            client = BinanceRestSnapshotClient(lambda url, _timeout: {
                "serverTime": 1700000000000,
                "symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": []}],
            } if "exchangeInfo" in url else (_ for _ in ()).throw(AssertionError(url)))
            runtime = BinancePublicMarketRuntime(
                depth_session=depth, market_session=market, metadata_session=metadata,
                snapshot_client=client, connect=lambda *args, **kwargs: TimedOutSocket(),
            )
            stats = asyncio.run(runtime.run(duration_seconds=0.01))
            self.assertEqual(1, stats.exchange_info_fetches)
            self.assertEqual("TRADING", stats.exchange_info_status)
            self.assertEqual("exchange_info", list(store.iter_availability())[0].normalized["kind"])

    def test_non_trading_exchange_info_is_preserved_but_fails_collection_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-meta")
            market = BinanceCaptureSession(store, "market-meta")
            metadata = BinanceCaptureSession(store, "metadata-1")
            client = BinanceRestSnapshotClient(lambda _url, _timeout: {
                "serverTime": 1700000000000,
                "symbols": [{"symbol": "BTCUSDT", "status": "BREAK", "filters": []}],
            })
            runtime = BinancePublicMarketRuntime(depth_session=depth, market_session=market, metadata_session=metadata, snapshot_client=client)
            asyncio.run(runtime.capture_exchange_info())
            self.assertEqual("BREAK", runtime.stats.exchange_info_status)
            self.assertIn("exchangeInfo instrument status is BREAK", runtime.stats.errors)
            self.assertEqual("exchange_info", list(store.iter_availability())[0].normalized["kind"])

    def test_exchange_info_poll_detects_a_later_non_trading_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-meta")
            market = BinanceCaptureSession(store, "market-meta")
            metadata = BinanceCaptureSession(store, "metadata-1")
            calls = 0

            class TimedOutSocket:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    raise asyncio.TimeoutError()

            def open_exchange_info(_url, _timeout):
                nonlocal calls
                calls += 1
                return {"serverTime": 1700000000000 + calls, "symbols": [{"symbol": "BTCUSDT", "status": "TRADING" if calls == 1 else "BREAK", "filters": []}]}

            runtime = BinancePublicMarketRuntime(
                depth_session=depth, market_session=market, metadata_session=metadata,
                snapshot_client=BinanceRestSnapshotClient(open_exchange_info), connect=lambda *args, **kwargs: TimedOutSocket(),
                metadata_interval_seconds=0.001, reconnect_delay_seconds=0.001,
            )
            # Leave enough wall-clock budget for the first thread-backed REST
            # call and at least one scheduled re-poll on slower CI hosts.
            stats = asyncio.run(runtime.run(duration_seconds=0.05))
            self.assertGreaterEqual(stats.exchange_info_fetches, 2)
            self.assertEqual("BREAK", stats.exchange_info_status)
            self.assertIn("exchangeInfo instrument status is BREAK", stats.errors)

    def test_depth_reconnect_rotates_evidence_connection_and_resynchronizes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(temp_dir)
            depth = BinanceCaptureSession(store, "depth-reconnect")
            market = BinanceCaptureSession(store, "market-reconnect")

            class FailingSocket:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    raise OSError("simulated disconnect")

            class BlockingSocket:
                def __init__(self, message=None):
                    self.message = message

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def recv(self):
                    if self.message is not None:
                        message, self.message = self.message, None
                        return message
                    await asyncio.sleep(1)

            depth_calls = 0

            def connect(url, **kwargs):
                nonlocal depth_calls
                if "/public/" not in url:
                    return BlockingSocket()
                depth_calls += 1
                if depth_calls == 1:
                    return FailingSocket()
                return BlockingSocket(json.dumps({"stream": "btcusdt@depth@100ms", "data": {
                    "e": "depthUpdate", "E": 1700000000000, "U": 101, "u": 101, "pu": 100, "b": [["99", "2"]], "a": []
                }}))

            client = BinanceRestSnapshotClient(lambda _url, _timeout: {
                "lastUpdateId": 100, "bids": [["99", "1"]], "asks": [["101", "1"]]
            })
            runtime = BinancePublicMarketRuntime(
                depth_session=depth,
                market_session=market,
                snapshot_client=client,
                connect=connect,
                reconnect_delay_seconds=0.001,
            )
            stats = asyncio.run(runtime.run(duration_seconds=0.05))
            self.assertEqual(1, stats.reconnects["depth"])
            self.assertEqual(2, stats.connection_attempts["depth"])
            self.assertTrue(depth.connection_id.endswith("-reconnect-1"))
            self.assertEqual(BookHealth.VALID, runtime.book.health)
