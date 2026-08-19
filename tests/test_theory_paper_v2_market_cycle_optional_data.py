from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
import hashlib
import json
import unittest
import urllib.parse

from trade_system.theory_paper_v2.application.market_cycle.ports import (
    MarketCaptureRequest,
)
from trade_system.theory_paper_v2.application.market_cycle.source import (
    capture_input_snapshot,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import CycleRequest
from trade_system.theory_paper_v2.infrastructure.market_data.okx_derivatives import (
    OkxDerivativesIntegrityError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_microstructure import (
    OkxMicrostructureIntegrityError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_snapshot import (
    BAR_INTERVAL_MILLISECONDS,
    OkxBaselineMarketData,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    FUNDING_RATE_HISTORY_PATH,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    OPEN_INTEREST_PATH,
    ORDER_BOOK_PATH,
    RECENT_TRADES_PATH,
    SERVER_TIME_PATH,
    OkxPublicTransport,
    OkxPublicTransportError,
    build_public_get_request,
)
from trade_system.theory_paper_v2.infrastructure.market_data.optional_context import (
    OKX_PUBLIC_OPTIONAL_PROFILE,
    OkxOptionalContextMarketData,
)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _milliseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value - epoch) // timedelta(milliseconds=1)


def _body(data: object, *, code: str = "0") -> bytes:
    return json.dumps(
        {"code": code, "msg": "", "data": data}, separators=(",", ":")
    ).encode()


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


def _candles(cutoff_ms: int) -> list[list[str]]:
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
        for index in range(20)
    ]


class _StepClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> str:
        value = self.current
        self.current += timedelta(milliseconds=100)
        return _time_text(value)


class _Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.url: str | None = None

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]

    def geturl(self) -> str:
        if self.url is None:
            raise AssertionError("response URL not bound")
        return self.url

    def close(self) -> None:
        return None


class _RawSink:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def seal_response(self, *, cycle_id, capture_id, payload, summary):
        self.rows.append(
            {
                "cycle_id": cycle_id,
                "capture_id": capture_id,
                "payload": payload,
                "summary": dict(summary),
            }
        )
        return {
            "artifact_type": "RawCapture",
            "artifact_id": f"{cycle_id}.{capture_id}.raw",
            "path": f"raw/{capture_id}/body.bin",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }


class _Opener:
    def __init__(self, outcomes, *, sink: _RawSink) -> None:
        self.outcomes = deque(outcomes)
        self.sink = sink
        self.requests = []

    def open(self, request, timeout):
        if self.requests and len(self.sink.rows) != len(self.requests):
            raise AssertionError("next request opened before previous raw seal")
        self.requests.append(request)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        outcome.url = request.full_url
        return outcome


def _responses(
    base: datetime,
    *,
    instrument_id: str = "BTC-USDT-SWAP",
    optional_override: dict[int, _Response] | None = None,
) -> list[_Response]:
    milliseconds = _milliseconds(base)
    rows = [
        _Response(_body([{"ts": str(milliseconds)}])),
        _Response(_body([_instrument_row(instrument_id)])),
        _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": instrument_id,
                        "markPx": "65000",
                        "ts": str(milliseconds),
                    }
                ]
            )
        ),
        _Response(_body(_candles(milliseconds))),
        _Response(
            _body(
                [
                    {
                        "asks": [["65001", "3", "0", "2"]],
                        "bids": [["64999", "4", "0", "3"]],
                        "ts": str(milliseconds),
                        "checksum": 123,
                        "seqId": 9007199254740993,
                        "prevSeqId": 9007199254740992,
                    }
                ]
            )
        ),
        _Response(
            _body(
                [
                    {
                        "instId": instrument_id,
                        "tradeId": "101",
                        "px": "65000",
                        "sz": "2",
                        "side": "buy",
                        "ts": str(milliseconds),
                        "count": "1",
                        "source": "0",
                    }
                ]
            )
        ),
        _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": instrument_id,
                        "oi": "12345",
                        "oiCcy": "123.45",
                        "oiUsd": "8024250",
                        "ts": str(milliseconds),
                    }
                ]
            )
        ),
        _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": instrument_id,
                        "fundingRate": "0.0001",
                        "fundingTime": str(milliseconds),
                        "formulaType": "withRate",
                        "method": "current_period",
                        "realizedRate": "0.0001",
                    }
                ]
            )
        ),
    ]
    for index, response in (optional_override or {}).items():
        rows[index] = response
    return rows


def _adapter(
    base: datetime, *, outcomes: list[_Response]
) -> tuple[OkxOptionalContextMarketData, _Opener, _RawSink]:
    sink = _RawSink()
    opener = _Opener(outcomes, sink=sink)
    transport = OkxPublicTransport(
        raw_sink=sink,
        clock=_StepClock(base),
        opener=opener,
    )
    core = OkxBaselineMarketData(transport=transport)
    return (
        OkxOptionalContextMarketData(core=core, transport=transport),
        opener,
        sink,
    )


def _request(*, profile: str) -> MarketCaptureRequest:
    return MarketCaptureRequest(
        cycle_id="cycle-optional-1",
        venue_id="OKX",
        instrument_id="BTC-USDT-SWAP",
        contract_type="SWAP",
        requested_at="2026-08-11T00:00:00Z",
        analysis_profile="COLD",
        data_profile=profile,
    )


class MarketCycleOptionalDataTests(unittest.TestCase):
    def test_legacy_profile_keeps_exact_four_request_behavior(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, opener, sink = _adapter(base, outcomes=_responses(base)[:4])

        observed = adapter.capture(_request(profile="BASELINE_PRICE"))

        self.assertEqual(4, len(opener.requests))
        self.assertEqual(4, len(sink.rows))
        self.assertEqual({}, observed.optional_observations)
        self.assertEqual(
            [
                SERVER_TIME_PATH,
                INSTRUMENT_PATH,
                MARK_PRICE_PATH,
                CLOSED_CANDLES_15M_PATH,
            ],
            [urllib.parse.urlsplit(row.full_url).path for row in opener.requests],
        )

    def test_new_profile_issues_eight_raw_first_requests_and_seals_four_values(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        adapter, opener, sink = _adapter(base, outcomes=_responses(base))

        observed = adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))

        self.assertEqual(8, len(opener.requests))
        self.assertEqual(8, len(sink.rows))
        self.assertEqual(
            [
                SERVER_TIME_PATH,
                INSTRUMENT_PATH,
                MARK_PRICE_PATH,
                CLOSED_CANDLES_15M_PATH,
                ORDER_BOOK_PATH,
                RECENT_TRADES_PATH,
                OPEN_INTEREST_PATH,
                FUNDING_RATE_HISTORY_PATH,
            ],
            [urllib.parse.urlsplit(row.full_url).path for row in opener.requests],
        )
        self.assertEqual(
            {
                "okx_order_book",
                "okx_recent_trades",
                "okx_open_interest",
                "okx_funding_rate_history",
            },
            set(observed.optional_observations),
        )
        for observation in observed.optional_observations.values():
            self.assertIn(observation["raw_sha256"], {
                row["sha256"] for row in observed.raw_refs
            })
            self.assertEqual(observed.captured_at, observed.cutoff_at)
        book = observed.optional_observations["okx_order_book"]["value"]
        self.assertEqual("9007199254740993", book["seq_id"])
        trade = observed.optional_observations["okx_recent_trades"]["value"][0]
        self.assertEqual("101", trade["trade_id"])

        request = CycleRequest(
            request_id="request-optional-1",
            cycle_id="cycle-optional-1",
            requested_at="2026-08-11T00:00:00Z",
            venue_id="OKX",
            instrument_id="BTC-USDT-SWAP",
            contract_identity="OKX:BTC-USDT-SWAP:linear",
            analysis_profile="COLD",
            data_profile=OKX_PUBLIC_OPTIONAL_PROFILE,
            outcome_horizon_seconds=900,
            outcome_tolerance_seconds=60,
            lawful_actions=("WAIT",),
        )
        second_adapter, _, _ = _adapter(base, outcomes=_responses(base))
        snapshot = capture_input_snapshot(
            request,
            market_data=second_adapter,
            clock=lambda: "2026-08-11T00:00:05Z",
        )
        self.assertEqual(OKX_PUBLIC_OPTIONAL_PROFILE, snapshot.data_profile)
        self.assertEqual(8, len(snapshot.raw_refs))

    def test_each_optional_transport_failure_is_unknown_and_core_continues(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        components = ["ORDER_BOOK", "RECENT_TRADES", "OPEN_INTEREST", "FUNDING_RATE_HISTORY"]
        observation_names = [
            "okx_order_book",
            "okx_recent_trades",
            "okx_open_interest",
            "okx_funding_rate_history",
        ]
        for offset, (component, observation_name) in enumerate(
            zip(components, observation_names, strict=True), start=4
        ):
            with self.subTest(component=component):
                outcomes = _responses(
                    base,
                    optional_override={offset: _Response(b"provider unavailable", status=503)},
                )
                adapter, opener, sink = _adapter(base, outcomes=outcomes)
                observed = adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
                self.assertEqual(8, len(opener.requests))
                self.assertEqual(8, len(sink.rows))
                self.assertNotIn(observation_name, observed.optional_observations)
                unknown = [row for row in observed.unknowns if row["component_id"] == component]
                self.assertEqual("UNKNOWN", unknown[0]["status"])
                self.assertFalse(unknown[0]["missing_is_zero"])
                self.assertEqual(4, len(observed.core_observations))

    def test_each_optional_parser_failure_is_unknown_after_raw_seal(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        components = ["ORDER_BOOK", "RECENT_TRADES", "OPEN_INTEREST", "FUNDING_RATE_HISTORY"]
        for offset, component in enumerate(components, start=4):
            with self.subTest(component=component):
                outcomes = _responses(
                    base,
                    optional_override={offset: _Response(_body([]))},
                )
                adapter, _, sink = _adapter(base, outcomes=outcomes)
                observed = adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
                self.assertEqual(8, len(sink.rows))
                health = [
                    row for row in observed.source_health if row["component_id"] == component
                ]
                self.assertEqual("UNKNOWN", health[0]["status"])
                self.assertIn("raw_ref", health[0])

    def test_optional_identity_and_future_provider_time_fail_closed(self) -> None:
        base = datetime(2026, 8, 11, tzinfo=UTC)
        wrong_oi = _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": "ETH-USDT-SWAP",
                        "oi": "1",
                        "oiCcy": "1",
                        "ts": str(_milliseconds(base)),
                    }
                ]
            )
        )
        adapter, _, sink = _adapter(
            base, outcomes=_responses(base, optional_override={6: wrong_oi})
        )
        with self.assertRaises(OkxDerivativesIntegrityError):
            adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
        self.assertEqual(7, len(sink.rows))

        bounded_ahead_oi = _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": "BTC-USDT-SWAP",
                        "oi": "12345",
                        "oiCcy": "123.45",
                        "oiUsd": "8024250",
                        # The provider clock is 126ms beyond the local response
                        # receipt for this fixture. Preserve it
                        # as provenance but never promote it to knowledge time.
                        "ts": str(_milliseconds(base) + 2026),
                    }
                ]
            )
        )
        adapter, _, _ = _adapter(
            base,
            outcomes=_responses(base, optional_override={6: bounded_ahead_oi}),
        )
        observed = adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
        oi = observed.optional_observations["okx_open_interest"]
        self.assertEqual(
            _time_text(base + timedelta(milliseconds=2026)),
            oi["value"]["provider_as_of"],
        )
        self.assertEqual(
            _time_text(base + timedelta(milliseconds=1900)),
            oi["observed_at"],
        )
        self.assertEqual(
            _time_text(base + timedelta(seconds=2)), oi["available_at"]
        )
        self.assertEqual(126, oi["provider_clock_ahead_milliseconds"])

        future_oi = _Response(
            _body(
                [
                    {
                        "instType": "SWAP",
                        "instId": "BTC-USDT-SWAP",
                        "oi": "12345",
                        "oiCcy": "123.45",
                        "ts": str(_milliseconds(base + timedelta(seconds=10))),
                    }
                ]
            )
        )
        adapter, _, sink = _adapter(
            base,
            outcomes=_responses(base, optional_override={6: future_oi}),
        )
        with self.assertRaises(OkxDerivativesIntegrityError):
            adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
        self.assertEqual(7, len(sink.rows))

        future_trade = _Response(
            _body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "tradeId": "1",
                        "px": "65000",
                        "sz": "1",
                        "side": "buy",
                        "ts": str(_milliseconds(base + timedelta(minutes=1))),
                    }
                ]
            )
        )
        adapter, _, sink = _adapter(
            base, outcomes=_responses(base, optional_override={5: future_trade})
        )
        with self.assertRaises(OkxMicrostructureIntegrityError):
            adapter.capture(_request(profile=OKX_PUBLIC_OPTIONAL_PROFILE))
        self.assertEqual(6, len(sink.rows))

    def test_optional_endpoint_queries_are_fixed_and_no_broader_shape_is_accepted(self) -> None:
        instrument = "BTC-USDT-SWAP"
        valid = {
            ORDER_BOOK_PATH: {"instId": instrument, "sz": "20"},
            RECENT_TRADES_PATH: {"instId": instrument, "limit": "100"},
            OPEN_INTEREST_PATH: {"instId": instrument, "instType": "SWAP"},
            FUNDING_RATE_HISTORY_PATH: {"instId": instrument, "limit": "10"},
        }
        for path, query in valid.items():
            request, _, ordered = build_public_get_request(path=path, query=query)
            self.assertEqual(query, ordered)
            self.assertEqual("GET", request.get_method())
            expanded = dict(query)
            expanded["before"] = "1"
            with self.assertRaisesRegex(OkxPublicTransportError, "QUERY_INVALID"):
                build_public_get_request(path=path, query=expanded)


if __name__ == "__main__":
    unittest.main()
