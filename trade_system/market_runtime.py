"""Optional public-market transport for forward Binance USD-M data capture.

This module has no account credentials and no order capability. Its transport
dependency is optional so replay, research and paper tests stay dependency-free.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .binance import BinanceCaptureSession, CaptureResult
from .book_sync import BinanceBookSynchronizer
from .order_book import BookGapError, OrderBook
from .quality import DataQualityEngine, HealthPolicy
from .types import BookHealth, utc_now


FUTURES_REST_BASE = "https://fapi.binance.com"
FUTURES_WS_BASE = "wss://fstream.binance.com"


class TransportUnavailable(RuntimeError):
    pass


class SnapshotFetchError(RuntimeError):
    pass


def stream_urls(symbol: str) -> Dict[str, str]:
    normalized = symbol.lower()
    return {
        "depth": "%s/public/stream?streams=%s@depth@100ms" % (FUTURES_WS_BASE, normalized),
        "market": "%s/market/stream?streams=%s@aggTrade/%s@markPrice@1s/%s@forceOrder" % (FUTURES_WS_BASE, normalized, normalized, normalized),
    }


class BinanceRestSnapshotClient:
    def __init__(self, opener: Optional[Callable[[str, float], Dict[str, Any]]] = None) -> None:
        self._opener = opener or self._default_open

    @staticmethod
    def _default_open(url: str, timeout: float) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "agent-trade-emotion/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotFetchError("cannot fetch public depth snapshot") from exc

    def fetch_depth(self, symbol: str, limit: int = 1000, timeout: float = 10.0) -> Dict[str, Any]:
        if limit not in (5, 10, 20, 50, 100, 500, 1000):
            raise ValueError("depth limit must be one of Binance-supported values")
        query = urllib.parse.urlencode({"symbol": symbol.upper(), "limit": limit})
        payload = self._opener("%s/fapi/v1/depth?%s" % (FUTURES_REST_BASE, query), timeout)
        required = ("lastUpdateId", "bids", "asks")
        if not isinstance(payload, dict) or any(key not in payload for key in required):
            raise SnapshotFetchError("invalid public depth snapshot schema")
        return payload

    def fetch_open_interest(self, symbol: str, timeout: float = 10.0) -> Dict[str, Any]:
        query = urllib.parse.urlencode({"symbol": symbol.upper()})
        payload = self._opener("%s/fapi/v1/openInterest?%s" % (FUTURES_REST_BASE, query), timeout)
        required = ("openInterest", "time")
        if not isinstance(payload, dict) or any(key not in payload for key in required):
            raise SnapshotFetchError("invalid public open-interest schema")
        return payload

    def fetch_exchange_info(self, timeout: float = 10.0) -> Dict[str, Any]:
        payload = self._opener("%s/fapi/v1/exchangeInfo" % FUTURES_REST_BASE, timeout)
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list) or "serverTime" not in payload:
            raise SnapshotFetchError("invalid exchangeInfo schema")
        return payload


@dataclass
class MarketRuntimeStats:
    raw_captured: int = 0
    availability_written: int = 0
    parse_errors: int = 0
    book_gaps: int = 0
    snapshot_fetches: int = 0
    open_interest_polls: int = 0
    exchange_info_fetches: int = 0
    exchange_info_status: Optional[str] = None
    exchange_info_filter_count: int = 0
    connection_attempts: Dict[str, int] = field(default_factory=dict)
    reconnects: Dict[str, int] = field(default_factory=dict)
    discarded_stale_snapshots: int = 0
    errors: list = field(default_factory=list)


class BinancePublicMarketRuntime:
    """Capture depth/aggTrade/markPrice with a separate in-memory book health path."""

    def __init__(
        self,
        *,
        depth_session: BinanceCaptureSession,
        market_session: BinanceCaptureSession,
        snapshot_client: Optional[BinanceRestSnapshotClient] = None,
        snapshot_limit: int = 1000,
        connect: Optional[Callable[..., Any]] = None,
        oi_session: Optional[BinanceCaptureSession] = None,
        metadata_session: Optional[BinanceCaptureSession] = None,
        open_interest_interval_seconds: float = 5.0,
        metadata_interval_seconds: float = 300.0,
        reconnect_delay_seconds: float = 1.0,
        feature_observer: Optional[Callable[[CaptureResult], None]] = None,
    ) -> None:
        if depth_session.instrument != market_session.instrument:
            raise ValueError("all sessions must use the same instrument")
        if oi_session is not None and oi_session.instrument != depth_session.instrument:
            raise ValueError("all sessions must use the same instrument")
        if metadata_session is not None and metadata_session.instrument != depth_session.instrument:
            raise ValueError("all sessions must use the same instrument")
        if open_interest_interval_seconds <= 0:
            raise ValueError("open_interest_interval_seconds must be positive")
        if metadata_interval_seconds <= 0:
            raise ValueError("metadata_interval_seconds must be positive")
        if reconnect_delay_seconds <= 0:
            raise ValueError("reconnect_delay_seconds must be positive")
        self.depth_session = depth_session
        self.market_session = market_session
        self.snapshot_client = snapshot_client or BinanceRestSnapshotClient()
        self.snapshot_limit = snapshot_limit
        self._connect = connect
        self.oi_session = oi_session
        self.metadata_session = metadata_session
        self.open_interest_interval_seconds = open_interest_interval_seconds
        self.metadata_interval_seconds = metadata_interval_seconds
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.feature_observer = feature_observer
        self.book = OrderBook()
        self.synchronizer = BinanceBookSynchronizer(self.book)
        self.quality = DataQualityEngine(HealthPolicy({"depth", "trade"}, max_age=self._seconds(3), recovery_cooldown=self._seconds(1)))
        self.stats = MarketRuntimeStats()
        self._snapshot_loaded = False

    def _observe_feature(self, result: CaptureResult) -> None:
        if self.feature_observer is not None:
            self.feature_observer(result)

    @staticmethod
    def _seconds(value: int):
        from datetime import timedelta
        return timedelta(seconds=value)

    def capture_snapshot(self) -> None:
        snapshot = self.snapshot_client.fetch_depth(self.depth_session.instrument, self.snapshot_limit)
        self.apply_snapshot(snapshot)

    def apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Append and apply a fetched snapshot on the event-loop thread.

        The fetch itself may block, but applying it must not race depth delta
        buffering.  Keeping this mutation synchronous lets all deltas received
        while the HTTP request was in flight remain in the buffer.
        """
        result = self.depth_session.ingest("snapshot", snapshot)
        self.stats.raw_captured += 1
        self.stats.snapshot_fetches += 1
        if not result.availability_written:
            self.stats.parse_errors += 1
            raise SnapshotFetchError(result.parse_error or "snapshot parse failure")
        self.stats.availability_written += 1
        self._observe_feature(result)
        normalized = self.depth_session.normalizer.normalize("snapshot", snapshot)
        self.synchronizer.apply_snapshot(normalized)
        self._snapshot_loaded = True
        self.quality.observe_book(utc_now(), self.book.health, self.book.invalid_reason or "")

    def process_envelope(self, route: str, envelope: Dict[str, Any]) -> None:
        if not isinstance(envelope, dict):
            raise ValueError("combined stream envelope must be an object")
        stream, payload = envelope.get("stream"), envelope.get("data")
        if not isinstance(stream, str) or not isinstance(payload, dict):
            raise ValueError("combined stream envelope requires stream and data")
        session = self.depth_session if route == "depth" else self.market_session
        result = session.ingest(stream, payload)
        self.stats.raw_captured += 1
        if not result.availability_written:
            self.stats.parse_errors += 1
            self.stats.errors.append(result.parse_error or "parse_error")
            return
        self.stats.availability_written += 1
        self._observe_feature(result)
        normalized = session.normalizer.normalize(stream, payload)
        now = utc_now()
        kind = normalized["kind"]
        if kind == "delta":
            try:
                if self._snapshot_loaded:
                    if self.book.health != BookHealth.VALID:
                        self.quality.observe_book(now, BookHealth.INVALID, self.book.invalid_reason or "book_invalid")
                        return
                    self.synchronizer.apply_live_delta(normalized)
                else:
                    self.synchronizer.buffer_delta(normalized)
                self.quality.observe_book(now, self.book.health, self.book.invalid_reason or "")
            except BookGapError as exc:
                self.stats.book_gaps += 1
                self.stats.errors.append(str(exc))
                self.quality.observe_book(now, BookHealth.INVALID, "sequence_gap")
        elif kind == "trade":
            self.quality.observe("trade", now)
        # Advance recovery cooldown while the collector is active. Calling it
        # here has no trading side effect; the final health is still evaluated
        # by the CLI before a collection is considered successful.
        self.quality.evaluate(now)

    def _reset_depth_for_reconnect(self, reason: str) -> None:
        self.book.invalidate(reason)
        self.synchronizer = BinanceBookSynchronizer(self.book)
        self._snapshot_loaded = False
        self.quality.observe_book(utc_now(), BookHealth.INVALID, reason)

    async def capture_exchange_info(self) -> None:
        if self.metadata_session is None:
            return
        try:
            payload = await asyncio.to_thread(self.snapshot_client.fetch_exchange_info)
            result = self.metadata_session.ingest("exchangeInfo", payload)
            self.stats.raw_captured += 1
            self.stats.exchange_info_fetches += 1
            if result.availability_written:
                self.stats.availability_written += 1
                self._observe_feature(result)
                normalized = self.metadata_session.normalizer.normalize("exchangeInfo", payload, self.metadata_session.instrument)
                self.stats.exchange_info_status = str(normalized["status"])
                self.stats.exchange_info_filter_count = len(normalized["filters"])
                if self.stats.exchange_info_status != "TRADING":
                    self.stats.errors.append("exchangeInfo instrument status is %s" % self.stats.exchange_info_status)
            else:
                self.stats.parse_errors += 1
                self.stats.errors.append(result.parse_error or "exchange_info_parse_error")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stats.errors.append("exchangeInfo fetch error: %s" % exc)

    async def run(self, duration_seconds: Optional[float] = None) -> MarketRuntimeStats:
        connect = self._connect
        if connect is None:
            try:
                import websockets  # type: ignore
            except ImportError as exc:
                raise TransportUnavailable("install optional dependency with: pip install -e '.[market]'") from exc
            connect = websockets.connect

        urls = stream_urls(self.depth_session.instrument)
        stop_at = time.monotonic() + duration_seconds if duration_seconds is not None else None
        await self.capture_exchange_info()
        snapshot_requests: "asyncio.Queue[int]" = asyncio.Queue()
        depth_generation = 0
        requested_generations = set()
        base_connection_ids = {
            "depth": self.depth_session.connection_id,
            "market": self.market_session.connection_id,
        }

        def stopped() -> bool:
            return stop_at is not None and time.monotonic() >= stop_at

        def rotate_route_session(route: str, reconnect_number: int) -> None:
            session = self.depth_session if route == "depth" else self.market_session
            session.rotate_connection("%s-reconnect-%d" % (base_connection_ids[route], reconnect_number))

        async def consume(route: str) -> None:
            nonlocal depth_generation
            reconnect_number = 0
            while not stopped():
                if reconnect_number:
                    rotate_route_session(route, reconnect_number)
                    self.stats.reconnects[route] = reconnect_number
                self.stats.connection_attempts[route] = self.stats.connection_attempts.get(route, 0) + 1
                generation = None
                if route == "depth":
                    depth_generation += 1
                    generation = depth_generation
                    self._reset_depth_for_reconnect("depth_connection_start")
                unexpected_close = False
                try:
                    # A bounded close handshake prevents a normal short capture
                    # from evaluating freshness many seconds after its final
                    # message solely because the peer delayed WebSocket close.
                    async with connect(urls[route], ping_interval=None, open_timeout=15, close_timeout=1) as socket:
                        while not stopped():
                            timeout = max(0.1, stop_at - time.monotonic()) if stop_at is not None else None
                            try:
                                message = await asyncio.wait_for(socket.recv(), timeout=timeout)
                            except asyncio.TimeoutError:
                                if stopped():
                                    break
                                unexpected_close = True
                                self.stats.errors.append("%s receive idle timeout" % route)
                                break
                            if isinstance(message, bytes):
                                message = message.decode("utf-8")
                            envelope = json.loads(message)
                            self.process_envelope(route, envelope)
                            if route == "depth" and generation not in requested_generations:
                                requested_generations.add(generation)
                                snapshot_requests.put_nowait(generation)
                    if not stopped() and not unexpected_close:
                        unexpected_close = True
                        self.stats.errors.append("%s transport closed" % route)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    unexpected_close = True
                    self.stats.errors.append("%s transport error: %s" % (route, exc))

                if stopped():
                    break
                if route == "depth":
                    # Invalidate the current generation before sleeping. A
                    # snapshot response from it must never apply after a
                    # disconnect/reconnect boundary.
                    depth_generation += 1
                    self._reset_depth_for_reconnect("depth_transport_disconnect")
                reconnect_number += 1
                await asyncio.sleep(self.reconnect_delay_seconds)

        async def snapshot_worker() -> None:
            nonlocal depth_generation
            while True:
                generation = await snapshot_requests.get()
                if generation != depth_generation:
                    self.stats.discarded_stale_snapshots += 1
                    continue
                try:
                    snapshot = await asyncio.to_thread(
                        self.snapshot_client.fetch_depth,
                        self.depth_session.instrument,
                        self.snapshot_limit,
                    )
                    if generation != depth_generation:
                        self.stats.discarded_stale_snapshots += 1
                        continue
                    self.apply_snapshot(snapshot)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.stats.errors.append("depth snapshot error: %s" % exc)
                    self.quality.observe_book(utc_now(), BookHealth.INVALID, "snapshot_error")

        async def poll_open_interest() -> None:
            if self.oi_session is None:
                return
            while stop_at is None or time.monotonic() < stop_at:
                try:
                    payload = await asyncio.to_thread(
                        self.snapshot_client.fetch_open_interest,
                        self.oi_session.instrument,
                    )
                    result = self.oi_session.ingest("openInterest", payload)
                    self.stats.raw_captured += 1
                    self.stats.open_interest_polls += 1
                    if result.availability_written:
                        self.stats.availability_written += 1
                        self._observe_feature(result)
                    else:
                        self.stats.parse_errors += 1
                        self.stats.errors.append(result.parse_error or "open_interest_parse_error")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.stats.errors.append("open_interest poll error: %s" % exc)
                if stop_at is not None and time.monotonic() >= stop_at:
                    break
                delay = self.open_interest_interval_seconds
                if stop_at is not None:
                    delay = min(delay, max(0.0, stop_at - time.monotonic()))
                if delay <= 0:
                    break
                await asyncio.sleep(delay)

        async def poll_exchange_info() -> None:
            if self.metadata_session is None:
                return
            while stop_at is None or time.monotonic() < stop_at:
                delay = self.metadata_interval_seconds
                if stop_at is not None:
                    delay = min(delay, max(0.0, stop_at - time.monotonic()))
                if delay <= 0:
                    break
                await asyncio.sleep(delay)
                if stop_at is not None and time.monotonic() >= stop_at:
                    break
                await self.capture_exchange_info()

        depth_task = asyncio.create_task(consume("depth"))
        market_task = asyncio.create_task(consume("market"))
        snapshot_task = asyncio.create_task(snapshot_worker())
        task_group = [depth_task, market_task]
        if self.oi_session is not None:
            task_group.append(asyncio.create_task(poll_open_interest()))
        if self.metadata_session is not None:
            task_group.append(asyncio.create_task(poll_exchange_info()))
        await asyncio.gather(*task_group)
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        return self.stats
