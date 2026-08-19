from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import urllib.parse

from trade_system.theory_paper_v2.application.market_cycle.ports import (
    MarketCaptureRequest,
    OutcomeRequest,
)
from trade_system.theory_paper_v2.application.market_cycle.source import (
    capture_input_snapshot,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import CycleRequest
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    ArtifactRef,
    Outcome,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.okx_outcome import (
    OkxMarkOutcome,
    OkxOutcomeError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_snapshot import (
    BAR_INTERVAL_MILLISECONDS,
    OkxBaselineMarketData,
    OkxSnapshotError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    ALLOWED_PUBLIC_PATHS,
    CLOSED_CANDLES_15M_PATH,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    SERVER_TIME_PATH,
    OkxPublicTransport,
    OkxPublicTransportError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
    RawCaptureError,
)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _milliseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value - epoch) // timedelta(milliseconds=1)


def _body(data: object, *, code: str = "0") -> bytes:
    return json.dumps(
        {"code": code, "msg": "", "data": data},
        separators=(",", ":"),
    ).encode("utf-8")


def _instrument_row(instrument_id: str) -> dict[str, str]:
    base, quote, _ = instrument_id.split("-")
    return {
        "instType": "SWAP",
        "instId": instrument_id,
        "state": "live",
        "ctType": "linear",
        "ctValCcy": base,
        "settleCcy": quote,
        "ctVal": "0.01",
        "ctMult": "1",
        "lotSz": "1",
        "minSz": "1",
        "tickSz": "0.1",
        "uly": f"{base}-{quote}",
    }


def _candle_rows(cutoff_ms: int, *, count: int = 20) -> list[list[str]]:
    return [
        [
            str(cutoff_ms - (index + 1) * BAR_INTERVAL_MILLISECONDS),
            "100",
            "103",
            "99",
            "102",
            "10",
            "1",
            "1000",
            "1",
        ]
        for index in range(count)
    ]


class _StepClock:
    def __init__(self, start: datetime, *, step_ms: int = 100) -> None:
        self.current = start
        self.step = timedelta(milliseconds=step_ms)

    def __call__(self) -> str:
        value = self.current
        self.current += self.step
        return _time_text(value)


class _CountingClock:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.value


class _CrashAfterClaimStore(FileRawCaptureStore):
    def claim_attempt(self, **kwargs) -> bool:
        super().claim_attempt(**kwargs)
        raise RuntimeError("simulated crash after durable attempt claim")


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        final_url: str | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.final_url = final_url
        self.closed = False

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]

    def geturl(self) -> str:
        if self.final_url is None:
            raise AssertionError("opener did not bind final URL")
        return self.final_url

    def close(self) -> None:
        self.closed = True


class _MemoryRawSink:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def seal_response(self, *, cycle_id, capture_id, payload, summary):
        digest = hashlib.sha256(payload).hexdigest()
        row = {
            "cycle_id": cycle_id,
            "capture_id": capture_id,
            "payload": payload,
            "summary": dict(summary),
        }
        self.rows.append(row)
        return {
            "artifact_type": "RawCapture",
            "artifact_id": f"{cycle_id}.{capture_id}.raw",
            "path": f"raw/{capture_id}/body.bin",
            "size_bytes": len(payload),
            "sha256": digest,
        }


class _Opener:
    def __init__(self, outcomes, *, sink: _MemoryRawSink | None = None) -> None:
        self.outcomes = deque(outcomes)
        self.sink = sink
        self.requests = []
        self.timeouts: list[float] = []

    def open(self, request, timeout):
        if self.sink is not None and self.requests:
            # A subsequent request is illegal until the preceding response was
            # persisted by the transport's raw-first boundary.
            if len(self.sink.rows) != len(self.requests):
                raise AssertionError("next request opened before raw seal")
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome.final_url is None:
            outcome.final_url = request.full_url
        return outcome


def _market_request(
    *,
    instrument_id: str = "BTC-USDT-SWAP",
    requested_at: str = "2026-08-11T00:00:00Z",
) -> MarketCaptureRequest:
    return MarketCaptureRequest(
        cycle_id="cycle-market-data-1",
        venue_id="OKX",
        instrument_id=instrument_id,
        contract_type="SWAP",
        requested_at=requested_at,
        analysis_profile="COLD",
        data_profile="BASELINE_PRICE",
    )


def _baseline_adapter(
    *,
    base: datetime,
    instrument_id: str = "BTC-USDT-SWAP",
    mark_instrument_id: str | None = None,
    mark_value: str = "65000",
    candles: list[list[str]] | None = None,
) -> tuple[OkxBaselineMarketData, _Opener, _MemoryRawSink]:
    base_ms = _milliseconds(base)
    sink = _MemoryRawSink()
    outcomes = [
        _Response(_body([{"ts": str(base_ms)}])),
        _Response(_body([_instrument_row(instrument_id)])),
        _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": mark_instrument_id or instrument_id,
                        "markPx": mark_value,
                        "ts": str(base_ms),
                    }
                ]
            )
        ),
        _Response(
            _body(
                _candle_rows(base_ms) if candles is None else candles
            )
        ),
    ]
    opener = _Opener(outcomes, sink=sink)
    transport = OkxPublicTransport(
        raw_sink=sink,
        clock=_StepClock(base),
        opener=opener,
    )
    return OkxBaselineMarketData(transport=transport), opener, sink


class MarketCycleMarketDataTests(unittest.TestCase):
    def test_baseline_issues_exact_four_public_requests_in_raw_first_order(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, opener, sink = _baseline_adapter(base=base)

        observed = adapter.capture(_market_request())

        self.assertEqual(4, len(opener.requests))
        self.assertEqual(4, len(sink.rows))
        self.assertEqual(
            [
                SERVER_TIME_PATH,
                INSTRUMENT_PATH,
                MARK_PRICE_PATH,
                CLOSED_CANDLES_15M_PATH,
            ],
            [urllib.parse.urlsplit(row.full_url).path for row in opener.requests],
        )
        candle_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(opener.requests[-1].full_url).query
        )
        self.assertEqual([str(_milliseconds(base))], candle_query["after"])
        self.assertEqual(["15m"], candle_query["bar"])
        self.assertEqual(["96"], candle_query["limit"])
        for request in opener.requests:
            self.assertEqual("GET", request.get_method())
            names = {name.casefold() for name, _ in request.header_items()}
            self.assertFalse(
                names
                & {
                    "authorization",
                    "cookie",
                    "ok-access-key",
                    "ok-access-passphrase",
                    "ok-access-sign",
                    "proxy-authorization",
                }
            )
        self.assertEqual("65000", observed.core_observations["mark_price"]["value"])
        self.assertEqual(
            20,
            observed.core_observations["closed_15m_bars"]["count"],
        )
        first_bar = observed.core_observations["closed_15m_bars"]["value"][0]
        self.assertNotIn("volume_contracts", first_bar)
        self.assertNotIn("volume_base", first_bar)
        self.assertNotIn("volume_quote", first_bar)
        self.assertEqual(
            {"server_time", "instrument", "mark_price", "closed_15m_bars"},
            set(observed.core_observations),
        )
        self.assertEqual(4, len(observed.raw_refs))
        self.assertEqual(4, len(observed.source_health))
        self.assertTrue(all(not row["retry_allowed"] for row in observed.source_health))
        self.assertEqual({}, observed.optional_observations)
        self.assertTrue(all(not row["missing_is_zero"] for row in observed.unknowns))
        self.assertTrue(all(row["code"] for row in observed.unknowns))
        self.assertTrue(all(row["summary"]["retry_allowed"] is False for row in sink.rows))

    def test_semantic_failure_occurs_only_after_that_response_is_sealed(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, opener, sink = _baseline_adapter(
            base=base, mark_value="6.5e4"
        )
        with self.assertRaisesRegex(OkxSnapshotError, "MARK_VALUE_INVALID"):
            adapter.capture(_market_request())
        self.assertEqual(3, len(opener.requests))
        self.assertEqual(
            ["server-time", "instrument", "mark-price"],
            [str(row["capture_id"]) for row in sink.rows],
        )

        sink = _MemoryRawSink()
        opener = _Opener([_Response(b"[]")], sink=sink)
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        with self.assertRaisesRegex(
            OkxSnapshotError, "SERVER_TIME_RESPONSE_INVALID"
        ):
            OkxBaselineMarketData(transport=transport).capture(_market_request())
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(1, len(sink.rows))

    def test_observation_directly_seals_under_the_domain_input_contract(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, _, _ = _baseline_adapter(base=base)
        request = CycleRequest(
            request_id="request-market-data-1",
            cycle_id="cycle-market-data-1",
            requested_at="2026-08-11T00:00:00+00:00",
            venue_id="OKX",
            instrument_id="BTC-USDT-SWAP",
            contract_identity="OKX:BTC-USDT-SWAP:linear",
            analysis_profile="COLD",
            data_profile="BASELINE_PRICE",
            outcome_horizon_seconds=900,
            outcome_tolerance_seconds=60,
            lawful_actions=("WAIT", "PROBE_REFERENCE"),
        )
        snapshot = capture_input_snapshot(
            request,
            market_data=adapter,
            clock=lambda: "2026-08-11T00:00:05Z",
        )
        self.assertEqual(request.cycle_id, snapshot.cycle_id)
        self.assertEqual(
            {"server_time", "instrument", "mark_price", "closed_15m_bars"},
            set(snapshot.core_observations),
        )
        self.assertEqual(4, len(snapshot.raw_refs))
        self.assertTrue(all(ref.artifact_type == "RawCapture" for ref in snapshot.raw_refs))

    def test_instrument_identity_and_mark_identity_fail_closed(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, _, sink = _baseline_adapter(
            base=base, mark_instrument_id="ETH-USDT-SWAP"
        )
        with self.assertRaisesRegex(OkxSnapshotError, "INSTRUMENT_MISMATCH"):
            adapter.capture(_market_request())
        self.assertEqual(3, len(sink.rows))

        adapter, opener, sink = _baseline_adapter(base=base)
        opener.outcomes[1] = _Response(_body([_instrument_row("ETH-USDT-SWAP")]))
        with self.assertRaisesRegex(OkxSnapshotError, "IDENTITY_INVALID"):
            adapter.capture(_market_request())
        self.assertEqual(2, len(sink.rows))

    def test_unclosed_future_or_discontinuous_candles_are_never_admitted(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        rows = _candle_rows(_milliseconds(base))
        rows[0][8] = "0"
        adapter, _, sink = _baseline_adapter(base=base, candles=rows)
        with self.assertRaisesRegex(OkxSnapshotError, "CANDLE_SCHEMA_INVALID"):
            adapter.capture(_market_request())
        self.assertEqual(4, len(sink.rows))

        rows = _candle_rows(_milliseconds(base))
        rows[5][0] = str(int(rows[5][0]) - BAR_INTERVAL_MILLISECONDS)
        adapter, _, _ = _baseline_adapter(base=base, candles=rows)
        with self.assertRaisesRegex(OkxSnapshotError, "CANDLES_COVERAGE_INVALID"):
            adapter.capture(_market_request())

    def test_provider_future_time_and_no_retry_transport_failure_fail_closed(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        future = base + timedelta(seconds=6)
        sink = _MemoryRawSink()
        opener = _Opener(
            [_Response(_body([{"ts": str(_milliseconds(future))}]))], sink=sink
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        with self.assertRaisesRegex(OkxSnapshotError, "FUTURE_DATUM"):
            OkxBaselineMarketData(transport=transport).capture(_market_request())
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(1, len(sink.rows))

        sink = _MemoryRawSink()
        opener = _Opener([TimeoutError("one bounded failure")], sink=sink)
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        with self.assertRaises(OkxPublicTransportError) as raised:
            OkxBaselineMarketData(transport=transport).capture(_market_request())
        self.assertEqual("PUBLIC_TIMEOUT", raised.exception.failure_code)
        self.assertTrue(raised.exception.coverage_eligible)
        self.assertEqual(1, len(opener.requests))
        self.assertEqual([], sink.rows)

    def test_redirect_and_transient_http_bodies_are_sealed_before_rejection(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    b"redirect-body",
                    final_url="https://openapi.okx.com/api/v5/public/time?moved=1",
                )
            ],
            sink=sink,
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        with self.assertRaises(OkxPublicTransportError) as raised:
            transport.get_once(
                cycle_id="cycle-redirect-1",
                capture_id="server-time",
                component_id="SERVER_TIME",
                path=SERVER_TIME_PATH,
                query={},
            )
        self.assertEqual("PUBLIC_REDIRECT_FORBIDDEN", raised.exception.failure_code)
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(b"redirect-body", sink.rows[0]["payload"])

        sink = _MemoryRawSink()
        opener = _Opener(
            [_Response(b"provider-down", status=503)], sink=sink
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        with self.assertRaises(OkxPublicTransportError) as raised:
            transport.get_once(
                cycle_id="cycle-provider-1",
                capture_id="server-time",
                component_id="SERVER_TIME",
                path=SERVER_TIME_PATH,
                query={},
            )
        self.assertEqual("PUBLIC_PROVIDER_UNAVAILABLE", raised.exception.failure_code)
        self.assertTrue(raised.exception.coverage_eligible)
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(b"provider-down", sink.rows[0]["payload"])

    def test_file_raw_store_publishes_body_and_summary_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileRawCaptureStore(root)
            summary = {
                "component_id": "SERVER_TIME",
                "method": "GET",
                "path": SERVER_TIME_PATH,
            }
            first = store.seal_response(
                cycle_id="cycle-raw-1",
                capture_id="server-time",
                payload=b"raw-body",
                summary=summary,
            )
            second = store.seal_response(
                cycle_id="cycle-raw-1",
                capture_id="server-time",
                payload=b"raw-body",
                summary=summary,
            )
            self.assertEqual(first, second)
            self.assertEqual(
                b"raw-body",
                (
                    root
                    / "cycles/cycle-raw-1"
                    / str(first["path"])
                ).read_bytes(),
            )
            summary_path = (
                root / "cycles/cycle-raw-1" / str(first["path"])
            ).with_name("capture.json")
            capture = json.loads(summary_path.read_text())
            self.assertEqual(
                hashlib.sha256(b"raw-body").hexdigest(),
                capture["body_sha256"],
            )
            with self.assertRaises(RawCaptureError):
                store.seal_response(
                    cycle_id="cycle-raw-1",
                    capture_id="server-time",
                    payload=b"changed",
                    summary=summary,
                )

    def test_restart_replays_sealed_response_without_a_second_request(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        payload = _body([{"ts": str(_milliseconds(base))}])
        with tempfile.TemporaryDirectory() as directory:
            store = FileRawCaptureStore(Path(directory))
            first_opener = _Opener([_Response(payload)])
            first = OkxPublicTransport(
                raw_sink=store,
                clock=_StepClock(base),
                opener=first_opener,
            ).get_once(
                cycle_id="cycle-recovery-1",
                capture_id="server-time",
                component_id="SERVER_TIME",
                path=SERVER_TIME_PATH,
                query={},
            )

            loaded = store.load_response(
                cycle_id="cycle-recovery-1", capture_id="server-time"
            )
            self.assertIsNotNone(loaded)
            self.assertEqual(payload, loaded.payload)
            self.assertEqual(first.raw_ref, loaded.raw_ref)

            no_network = _Opener([])
            replayed = OkxPublicTransport(
                raw_sink=store,
                clock=lambda: "2099-01-01T00:00:00Z",
                opener=no_network,
            ).get_once(
                cycle_id="cycle-recovery-1",
                capture_id="server-time",
                component_id="SERVER_TIME",
                path=SERVER_TIME_PATH,
                query={},
            )
            self.assertEqual(first, replayed)
            self.assertEqual([], no_network.requests)

    def test_crash_after_durable_claim_restarts_without_clock_or_network(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        request = {
            "cycle_id": "cycle-attempt-claim-crash-1",
            "capture_id": "mark-price",
            "component_id": "MARK_PRICE",
            "path": MARK_PRICE_PATH,
            "query": {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_clock = _CountingClock(_time_text(base))
            first_opener = _Opener([])
            with self.assertRaises(OkxPublicTransportError) as raised:
                OkxPublicTransport(
                    raw_sink=_CrashAfterClaimStore(root),
                    clock=first_clock,
                    opener=first_opener,
                ).get_once(**request)
            self.assertEqual(
                "PUBLIC_ATTEMPT_CLAIM_FAILED", raised.exception.failure_code
            )
            self.assertEqual(0, first_clock.calls)
            self.assertEqual([], first_opener.requests)

            restart_clock = _CountingClock(_time_text(base))
            restart_opener = _Opener([])
            with self.assertRaises(OkxPublicTransportError) as raised:
                OkxPublicTransport(
                    raw_sink=FileRawCaptureStore(root),
                    clock=restart_clock,
                    opener=restart_opener,
                ).get_once(**request)
            self.assertEqual(
                "PUBLIC_PREVIOUS_ATTEMPT_INDETERMINATE",
                raised.exception.failure_code,
            )
            self.assertTrue(raised.exception.coverage_eligible)
            self.assertEqual(0, restart_clock.calls)
            self.assertEqual([], restart_opener.requests)

    def test_durable_attempt_binding_drift_fails_before_clock_or_network(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = {
                "cycle_id": "cycle-attempt-binding-1",
                "capture_id": "mark-price",
                "component_id": "MARK_PRICE",
                "path": MARK_PRICE_PATH,
                "query": {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
            }
            with self.assertRaises(OkxPublicTransportError):
                OkxPublicTransport(
                    raw_sink=_CrashAfterClaimStore(root),
                    clock=_CountingClock(_time_text(base)),
                    opener=_Opener([]),
                ).get_once(**original)

            drifted = dict(original)
            drifted["query"] = {
                "instId": "ETH-USDT-SWAP",
                "instType": "SWAP",
            }
            drift_clock = _CountingClock(_time_text(base))
            drift_opener = _Opener([])
            with self.assertRaises(OkxPublicTransportError) as raised:
                OkxPublicTransport(
                    raw_sink=FileRawCaptureStore(root),
                    clock=drift_clock,
                    opener=drift_opener,
                ).get_once(**drifted)
            self.assertEqual(
                "PUBLIC_ATTEMPT_CLAIM_FAILED", raised.exception.failure_code
            )
            self.assertEqual(0, drift_clock.calls)
            self.assertEqual([], drift_opener.requests)

    def test_recovery_request_binding_mismatch_fails_without_network(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            store = FileRawCaptureStore(Path(directory))
            OkxPublicTransport(
                raw_sink=store,
                clock=_StepClock(base),
                opener=_Opener([_Response(_body([]))]),
            ).get_once(
                cycle_id="cycle-recovery-mismatch-1",
                capture_id="mark-price",
                component_id="MARK_PRICE",
                path=MARK_PRICE_PATH,
                query={"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
            )

            no_network = _Opener([])
            transport = OkxPublicTransport(
                raw_sink=store,
                clock=_StepClock(base),
                opener=no_network,
            )
            with self.assertRaises(OkxPublicTransportError) as raised:
                transport.get_once(
                    cycle_id="cycle-recovery-mismatch-1",
                    capture_id="mark-price",
                    component_id="MARK_PRICE",
                    path=MARK_PRICE_PATH,
                    query={"instId": "ETH-USDT-SWAP", "instType": "SWAP"},
                )
            self.assertEqual(
                "RAW_CAPTURE_RECOVERY_MISMATCH", raised.exception.failure_code
            )
            self.assertEqual([], no_network.requests)

            (
                Path(directory)
                / "cycles/cycle-recovery-mismatch-1/raw/mark-price/body.bin"
            ).write_bytes(b"tampered")
            no_network_after_tamper = _Opener([])
            transport = OkxPublicTransport(
                raw_sink=store,
                clock=_StepClock(base),
                opener=no_network_after_tamper,
            )
            with self.assertRaises(OkxPublicTransportError) as raised:
                transport.get_once(
                    cycle_id="cycle-recovery-mismatch-1",
                    capture_id="mark-price",
                    component_id="MARK_PRICE",
                    path=MARK_PRICE_PATH,
                    query={"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
                )
            self.assertEqual(
                "RAW_CAPTURE_RECOVERY_INVALID", raised.exception.failure_code
            )
            self.assertEqual([], no_network_after_tamper.requests)

    def test_sink_without_reader_keeps_the_in_process_one_attempt_guard(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener([_Response(_body([]))], sink=sink)
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(base), opener=opener
        )
        request = {
            "cycle_id": "cycle-nonrecoverable-sink-1",
            "capture_id": "mark-price",
            "component_id": "MARK_PRICE",
            "path": MARK_PRICE_PATH,
            "query": {"instId": "BTC-USDT-SWAP", "instType": "SWAP"},
        }
        transport.get_once(**request)
        with self.assertRaises(OkxPublicTransportError) as raised:
            transport.get_once(**request)
        self.assertEqual(
            "PUBLIC_REQUEST_ALREADY_ATTEMPTED", raised.exception.failure_code
        )
        self.assertEqual(1, len(opener.requests))


class MarketCycleOutcomeTests(unittest.TestCase):
    def _request(
        self,
        *,
        due_at: str = "2026-08-11T01:00:00Z",
        tolerance_seconds: int = 60,
        instrument_id: str = "ETH-USDT-SWAP",
    ) -> OutcomeRequest:
        return OutcomeRequest(
            cycle_id="cycle-outcome-1",
            venue_id="OKX",
            instrument_id=instrument_id,
            price_field="MARK_PRICE",
            due_at=due_at,
            tolerance_seconds=tolerance_seconds,
        )

    def test_v332_outcome_seals_ordered_closed_15m_path_without_intrabar_guess(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [{
                            "instType": "SWAP",
                            "instId": "ETH-USDT-SWAP",
                            "markPx": "4200.5",
                            "ts": str(_milliseconds(due)),
                        }]
                    )
                ),
                _Response(_body(_candle_rows(_milliseconds(due), count=20))),
            ],
            sink=sink,
        )
        outcome = OkxMarkOutcome(
            transport=OkxPublicTransport(
                raw_sink=sink,
                clock=_StepClock(due, step_ms=100),
                opener=opener,
            ),
            clock=lambda: _time_text(due),
        ).observe(
            OutcomeRequest(
                cycle_id="cycle-outcome-path-1",
                venue_id="OKX",
                instrument_id="ETH-USDT-SWAP",
                price_field="MARK_PRICE",
                due_at=_time_text(due),
                tolerance_seconds=60,
                path_start_at=_time_text(due - timedelta(minutes=30)),
            )
        )
        self.assertEqual("OBSERVED", outcome.terminal_status)
        self.assertEqual("ORDERED", outcome.path_observations["status"])
        self.assertEqual(2, len(outcome.path_observations["points"]))
        self.assertEqual(
            [
                _time_text(due - timedelta(minutes=15)),
                _time_text(due),
            ],
            [point["closed_at"] for point in outcome.path_observations["points"]],
        )
        self.assertEqual(
            "UNRESOLVED_WITHIN_BAR",
            outcome.path_observations["intrabar_order"],
        )
        self.assertEqual(1, len(outcome.additional_raw_refs))
        self.assertEqual(2, len(sink.rows))
        mark_ref = ArtifactRef.from_dict(outcome.raw_ref)
        path_ref = ArtifactRef.from_dict(outcome.additional_raw_refs[0])
        sealed = Outcome(
            outcome_id="cycle-outcome-path-1.outcome",
            cycle_id="cycle-outcome-path-1",
            behavior_plan_ref=ArtifactRef(
                artifact_type="BehaviorPlan",
                artifact_id="cycle-outcome-path-1.plan",
                path="artifacts/BehaviorPlan.json",
                size_bytes=1,
                sha256="a" * 64,
            ),
            due_at=_time_text(due),
            tolerance_seconds=60,
            observed_at=outcome.observed_at,
            sealed_at=outcome.observed_at,
            terminal_status="OBSERVED",
            endpoint_observation={
                "value": outcome.value,
                "unit": outcome.unit,
                "price_field": "MARK_PRICE",
                "effective_at": outcome.effective_at,
                "available_at": outcome.available_at,
                "raw_sha256": mark_ref.sha256,
            },
            typed_missing=None,
            path_observations={
                **dict(outcome.path_observations),
                "source_health": list(outcome.source_health),
            },
            raw_refs=(mark_ref, path_ref),
            theory_identity=V332_THEORY_IDENTITY,
        )
        tampered = sealed.to_dict()
        tampered["path_observations"]["points"][0]["close"] = "999"
        with self.assertRaisesRegex(ValueError, "path geometry"):
            Outcome.from_dict(tampered)

        missing_path = sealed.to_dict()
        missing_path["path_observations"] = {"source_health": []}
        with self.assertRaisesRegex(ValueError, "requires the ordered path"):
            Outcome.from_dict(missing_path)

        downgraded = sealed.to_dict()
        downgraded["path_observations"]["schema_version"] = "0.9.0"
        with self.assertRaisesRegex(ValueError, "path contract is invalid"):
            Outcome.from_dict(downgraded)

        shifted = sealed.to_dict()
        for point in shifted["path_observations"]["points"]:
            for field in ("opened_at", "closed_at"):
                point[field] = _time_text(
                    datetime.fromisoformat(point[field].replace("Z", "+00:00"))
                    - timedelta(minutes=15)
                )
        with self.assertRaisesRegex(ValueError, "path chronology"):
            Outcome.from_dict(shifted)

        premature_availability = sealed.to_dict()
        premature_availability["path_observations"]["points"][0][
            "available_at"
        ] = premature_availability["path_observations"]["points"][0][
            "opened_at"
        ]
        with self.assertRaisesRegex(ValueError, "path chronology"):
            Outcome.from_dict(premature_availability)

        censored = sealed.to_dict()
        censored["path_observations"].update(
            {
                "status": "CENSORED",
                "points": [],
                "coverage": {
                    "expected_point_count": 2,
                    "observed_point_count": 0,
                    "gap_count": 2,
                    "covers_all_closed_intervals": False,
                },
                "missing_reason": "ORDERED_PATH_CAPTURE_UNAVAILABLE",
            }
        )
        self.assertEqual(
            "CENSORED",
            Outcome.from_dict(censored).path_observations["status"],
        )

    def test_v332_path_excludes_bar_opened_before_agent_decision(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [{
                            "instType": "SWAP",
                            "instId": "ETH-USDT-SWAP",
                            "markPx": "4200.5",
                            "ts": str(_milliseconds(due)),
                        }]
                    )
                ),
                _Response(_body(_candle_rows(_milliseconds(due), count=20))),
            ],
            sink=sink,
        )
        outcome = OkxMarkOutcome(
            transport=OkxPublicTransport(
                raw_sink=sink,
                clock=_StepClock(due, step_ms=100),
                opener=opener,
            ),
            clock=lambda: _time_text(due),
        ).observe(
            OutcomeRequest(
                cycle_id="cycle-outcome-path-post-decision",
                venue_id="OKX",
                instrument_id="ETH-USDT-SWAP",
                price_field="MARK_PRICE",
                due_at=_time_text(due),
                tolerance_seconds=60,
                path_start_at=_time_text(
                    due - timedelta(minutes=30) + timedelta(seconds=1)
                ),
            )
        )
        self.assertEqual("ORDERED", outcome.path_observations["status"])
        self.assertEqual(1, len(outcome.path_observations["points"]))
        self.assertEqual(
            _time_text(due - timedelta(minutes=15)),
            outcome.path_observations["points"][0]["opened_at"],
        )

    def test_v332_outcome_path_semantic_tamper_fails_after_raw_seal(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        malformed = _candle_rows(_milliseconds(due), count=20)
        malformed[0][8] = "0"
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [{
                            "instType": "SWAP",
                            "instId": "ETH-USDT-SWAP",
                            "markPx": "4200.5",
                            "ts": str(_milliseconds(due)),
                        }]
                    )
                ),
                _Response(_body(malformed)),
            ],
            sink=sink,
        )
        outcome = OkxMarkOutcome(
            transport=OkxPublicTransport(
                raw_sink=sink,
                clock=_StepClock(due, step_ms=100),
                opener=opener,
            ),
            clock=lambda: _time_text(due),
        ).observe(
            OutcomeRequest(
                cycle_id="cycle-outcome-path-invalid",
                venue_id="OKX",
                instrument_id="ETH-USDT-SWAP",
                price_field="MARK_PRICE",
                due_at=_time_text(due),
                tolerance_seconds=60,
                path_start_at=_time_text(due - timedelta(minutes=30)),
            )
        )
        self.assertEqual("OBSERVED", outcome.terminal_status)
        self.assertEqual("4200.5", outcome.value)
        self.assertEqual("CENSORED", outcome.path_observations["status"])
        self.assertEqual(
            "OUTCOME_PATH_RESPONSE_INVALID",
            outcome.path_observations["missing_reason"],
        )
        self.assertEqual(2, len(sink.rows))

    def test_v332_path_transport_failure_does_not_erase_observed_endpoint(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [{
                            "instType": "SWAP",
                            "instId": "ETH-USDT-SWAP",
                            "markPx": "4200.5",
                            "ts": str(_milliseconds(due)),
                        }]
                    )
                ),
                TimeoutError("path provider timeout"),
            ],
            sink=sink,
        )
        outcome = OkxMarkOutcome(
            transport=OkxPublicTransport(
                raw_sink=sink,
                clock=_StepClock(due, step_ms=100),
                opener=opener,
            ),
            clock=lambda: _time_text(due),
        ).observe(
            OutcomeRequest(
                cycle_id="cycle-outcome-path-provider-failure",
                venue_id="OKX",
                instrument_id="ETH-USDT-SWAP",
                price_field="MARK_PRICE",
                due_at=_time_text(due),
                tolerance_seconds=60,
                path_start_at=_time_text(due - timedelta(minutes=30)),
            )
        )
        self.assertEqual("OBSERVED", outcome.terminal_status)
        self.assertEqual("4200.5", outcome.value)
        self.assertEqual("CENSORED", outcome.path_observations["status"])
        self.assertEqual(2, len(opener.requests))

    def test_v332_mark_missing_still_captures_ordered_path(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(_body([])),
                _Response(_body(_candle_rows(_milliseconds(due), count=20))),
            ],
            sink=sink,
        )
        outcome = OkxMarkOutcome(
            transport=OkxPublicTransport(
                raw_sink=sink,
                clock=_StepClock(due, step_ms=100),
                opener=opener,
            ),
            clock=lambda: _time_text(due),
        ).observe(
            OutcomeRequest(
                cycle_id="cycle-outcome-mark-missing-path-observed",
                venue_id="OKX",
                instrument_id="ETH-USDT-SWAP",
                price_field="MARK_PRICE",
                due_at=_time_text(due),
                tolerance_seconds=60,
                path_start_at=_time_text(due - timedelta(minutes=30)),
            )
        )
        self.assertEqual("MISSING", outcome.terminal_status)
        self.assertEqual("PUBLIC_DATA_EMPTY", outcome.missing_reason)
        self.assertEqual("ORDERED", outcome.path_observations["status"])
        self.assertEqual(2, len(outcome.path_observations["points"]))
        self.assertEqual(1, len(outcome.additional_raw_refs))
        self.assertEqual(2, len(sink.rows))

    def test_before_and_after_window_make_no_request_or_substitution(self) -> None:
        class NoCallTransport:
            def __init__(self) -> None:
                self.calls = 0

            def get_once(self, **kwargs):
                self.calls += 1
                raise AssertionError("out-of-window outcome must not request")

        transport = NoCallTransport()
        pending = OkxMarkOutcome(
            transport=transport,
            clock=lambda: "2026-08-11T00:59:59Z",
        ).observe(self._request())
        self.assertEqual("PENDING", pending.terminal_status)
        self.assertEqual("OUTCOME_WINDOW_NOT_OPEN", pending.missing_reason)
        self.assertEqual(0, transport.calls)

        missing = OkxMarkOutcome(
            transport=transport,
            clock=lambda: "2026-08-11T01:01:01Z",
        ).observe(self._request())
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual("OUTCOME_WINDOW_EXPIRED", missing.missing_reason)
        self.assertIsNone(missing.raw_ref)
        self.assertEqual(0, transport.calls)

    def test_replay_only_outcome_never_opens_public_network(self) -> None:
        class NoCallTransport:
            def __init__(self) -> None:
                self.calls = 0

            def get_once(self, **kwargs):
                self.calls += 1
                raise AssertionError("replay-only outcome must not request")

        transport = NoCallTransport()
        missing = OkxMarkOutcome(
            transport=transport,
            clock=lambda: "2026-08-11T01:00:00Z",
            allow_public_collection=False,
        ).observe(self._request())
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual(
            "OUTCOME_PUBLIC_COLLECTION_NOT_AUTHORIZED", missing.missing_reason
        )
        self.assertIsNone(missing.raw_ref)
        self.assertEqual(0, transport.calls)

    def test_parameterized_instrument_uses_one_same_measure_mark_request(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        capture_start = due + timedelta(seconds=1)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [
                            {
                                "instType": "SWAP",
                                "instId": "ETH-USDT-SWAP",
                                "markPx": "4200.50",
                                "ts": str(_milliseconds(capture_start)),
                            }
                        ]
                    )
                )
            ],
            sink=sink,
        )
        transport = OkxPublicTransport(
            raw_sink=sink,
            clock=_StepClock(capture_start),
            opener=opener,
        )
        outcome = OkxMarkOutcome(
            transport=transport,
            clock=lambda: _time_text(capture_start),
        ).observe(self._request())
        self.assertEqual("OBSERVED", outcome.terminal_status)
        self.assertEqual("4200.5", outcome.value)
        self.assertEqual("USDT_PER_ETH", outcome.unit)
        self.assertIsNone(outcome.missing_reason)
        self.assertEqual(_time_text(capture_start), outcome.effective_at)
        self.assertIsNotNone(outcome.available_at)
        self.assertLessEqual(
            datetime.fromisoformat(outcome.effective_at.replace("Z", "+00:00")),
            datetime.fromisoformat(outcome.available_at.replace("Z", "+00:00")),
        )
        self.assertEqual(1, len(opener.requests))
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(opener.requests[0].full_url).query
        )
        self.assertEqual(["ETH-USDT-SWAP"], query["instId"])
        self.assertEqual(["SWAP"], query["instType"])
        self.assertEqual(1, len(sink.rows))

    def test_restart_replays_sealed_outcome_before_reading_late_clock(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        payload = _body(
            [
                {
                    "instType": "SWAP",
                    "instId": "ETH-USDT-SWAP",
                    "markPx": "4200.50",
                    "ts": str(_milliseconds(due)),
                }
            ]
        )

        class LateClock:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self) -> str:
                self.calls += 1
                return _time_text(due + timedelta(seconds=61))

        with tempfile.TemporaryDirectory() as directory:
            store = FileRawCaptureStore(Path(directory))
            first_opener = _Opener([_Response(payload)])
            first = OkxMarkOutcome(
                transport=OkxPublicTransport(
                    raw_sink=store,
                    clock=_StepClock(due),
                    opener=first_opener,
                ),
                clock=lambda: _time_text(due),
            ).observe(self._request())
            self.assertEqual("OBSERVED", first.terminal_status)

            late_clock = LateClock()
            no_network = _Opener([])
            recovered = OkxMarkOutcome(
                transport=OkxPublicTransport(
                    raw_sink=store,
                    clock=late_clock,
                    opener=no_network,
                ),
                clock=late_clock,
            ).observe(self._request())

            self.assertEqual(first, recovered)
            self.assertEqual(0, late_clock.calls)
            self.assertEqual([], no_network.requests)

    def test_empty_or_transport_unavailable_is_terminal_typed_missing(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener([_Response(_body([]))], sink=sink)
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(due), opener=opener
        )
        missing = OkxMarkOutcome(
            transport=transport, clock=lambda: _time_text(due)
        ).observe(self._request())
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual("PUBLIC_DATA_EMPTY", missing.missing_reason)
        self.assertIsNotNone(missing.raw_ref)
        self.assertEqual(1, len(opener.requests))

        class UnavailableTransport:
            def __init__(self) -> None:
                self.calls = 0

            def get_once(self, **kwargs):
                self.calls += 1
                raise OkxPublicTransportError(
                    "PUBLIC_TIMEOUT",
                    coverage_eligible=True,
                    failure_at="2026-08-11T01:00:02Z",
                )

        unavailable = UnavailableTransport()
        missing = OkxMarkOutcome(
            transport=unavailable, clock=lambda: _time_text(due)
        ).observe(self._request())
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual("PUBLIC_TIMEOUT", missing.missing_reason)
        self.assertEqual(1, unavailable.calls)

    def test_response_that_completes_outside_window_is_not_substituted(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        late = due + timedelta(seconds=2)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [
                            {
                                "instType": "SWAP",
                                "instId": "ETH-USDT-SWAP",
                                "markPx": "4200",
                                "ts": str(_milliseconds(late)),
                            }
                        ]
                    )
                )
            ],
            sink=sink,
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(late), opener=opener
        )
        missing = OkxMarkOutcome(
            transport=transport, clock=lambda: _time_text(due)
        ).observe(self._request(tolerance_seconds=1))
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual("OUTCOME_CAPTURE_OUTSIDE_WINDOW", missing.missing_reason)
        self.assertIsNotNone(missing.raw_ref)
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(1, len(sink.rows))

    def test_provider_datum_outside_tolerance_is_typed_missing(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        provider_time = due - timedelta(seconds=61)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [
                            {
                                "instType": "SWAP",
                                "instId": "ETH-USDT-SWAP",
                                "markPx": "4200",
                                "ts": str(_milliseconds(provider_time)),
                            }
                        ]
                    )
                )
            ],
            sink=sink,
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(due), opener=opener
        )
        missing = OkxMarkOutcome(
            transport=transport, clock=lambda: _time_text(due)
        ).observe(self._request(tolerance_seconds=60))
        self.assertEqual("MISSING", missing.terminal_status)
        self.assertEqual(
            "OUTCOME_MARK_EFFECTIVE_TIME_OUTSIDE_WINDOW",
            missing.missing_reason,
        )
        self.assertIsNone(missing.effective_at)
        self.assertIsNone(missing.available_at)
        self.assertIsNotNone(missing.raw_ref)

    def test_wrong_outcome_instrument_is_structural_not_replaced(self) -> None:
        due = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        sink = _MemoryRawSink()
        opener = _Opener(
            [
                _Response(
                    _body(
                        [
                            {
                                "instType": "SWAP",
                                "instId": "BTC-USDT-SWAP",
                                "markPx": "65000",
                                "ts": str(_milliseconds(due)),
                            }
                        ]
                    )
                )
            ],
            sink=sink,
        )
        transport = OkxPublicTransport(
            raw_sink=sink, clock=_StepClock(due), opener=opener
        )
        with self.assertRaisesRegex(OkxOutcomeError, "MARK_RESPONSE_INVALID"):
            OkxMarkOutcome(
                transport=transport, clock=lambda: _time_text(due)
            ).observe(self._request())
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(1, len(sink.rows))

    def test_outcome_scope_is_frozen_to_mark_price(self) -> None:
        request = self._request()
        wrong = OutcomeRequest(
            cycle_id=request.cycle_id,
            venue_id=request.venue_id,
            instrument_id=request.instrument_id,
            price_field="LAST_PRICE",
            due_at=request.due_at,
            tolerance_seconds=request.tolerance_seconds,
        )
        with self.assertRaisesRegex(OkxOutcomeError, "SCOPE_INVALID"):
            OkxMarkOutcome(
                transport=object(),
                clock=lambda: "2026-08-11T01:00:00Z",
            ).observe(wrong)


class MarketCycleDependencyBoundaryTests(unittest.TestCase):
    def test_new_market_data_slice_has_no_legacy_qualification_or_target_import(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = [
            root
            / "trade_system/theory_paper_v2/infrastructure/market_data/raw_capture.py",
            root
            / "trade_system/theory_paper_v2/infrastructure/market_data/okx_transport.py",
            root
            / "trade_system/theory_paper_v2/infrastructure/market_data/okx_snapshot.py",
            root
            / "trade_system/theory_paper_v2/infrastructure/market_cycle/okx_outcome.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for forbidden in (
            "v32_public_source_collector",
            "v32_okx_public_bundle_transport",
            "qualification",
            "target_wake",
            "authorized_target",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertEqual(
            {
                SERVER_TIME_PATH,
                INSTRUMENT_PATH,
                MARK_PRICE_PATH,
                CLOSED_CANDLES_15M_PATH,
            },
            set(ALLOWED_PUBLIC_PATHS),
        )


if __name__ == "__main__":
    unittest.main()
