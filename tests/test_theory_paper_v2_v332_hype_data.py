from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.data_profiles import (
    AssetDataProfileMarketDataAdapter,
    project_market_data_observation,
)
from trade_system.theory_paper_v2.application.market_cycle.source import (
    capture_input_snapshot,
)
from trade_system.theory_paper_v2.application.market_cycle.ports import (
    MarketCaptureRequest,
    MarketDataObservation,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    HYPE_OKX_PROFILE_ID,
    OkxAssetProfileError,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_snapshot import (
    OkxSnapshotError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    MAX_PUBLIC_RESPONSE_BYTES,
    OPEN_INTEREST_PATH,
    SERVER_TIME_PATH,
    build_public_get_request,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import CycleRequest
from trade_system.theory_paper_v2.domain.market_cycle.theory import V332_THEORY_IDENTITY


_ROUTE_POLICY = "V332_OFFLINE_HYPE_FIXTURE_NO_NETWORK_V1"
_BASE = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def _time(offset_seconds: int) -> str:
    return (_BASE + timedelta(seconds=offset_seconds)).isoformat().replace(
        "+00:00", "Z"
    )


def _ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _seal(
    store: FileRawCaptureStore,
    *,
    cycle_id: str,
    capture_id: str,
    component_id: str,
    path: str,
    query: dict[str, str],
    body: bytes,
    start_offset: int,
) -> None:
    _, final_url, ordered_query = build_public_get_request(path=path, query=query)
    store.seal_response(
        cycle_id=cycle_id,
        capture_id=capture_id,
        payload=body,
        summary={
            "component_id": component_id,
            "method": "GET",
            "path": path,
            "query": ordered_query,
            "request_started_at": _time(start_offset),
            "response_received_at": _time(start_offset + 1),
            "capture_completed_at": _time(start_offset + 2),
            "http_status": 200,
            "final_url": final_url,
            "route_policy_id": _ROUTE_POLICY,
            "attempt_number": 1,
            "retry_allowed": False,
            "response_limit_bytes": MAX_PUBLIC_RESPONSE_BYTES,
            "body_truncated": False,
        },
    )


def _server_body() -> bytes:
    return _json({"code": "0", "msg": "", "data": [{"ts": _ms(_BASE + timedelta(seconds=1))}]})


def _instrument_body(
    *,
    instrument_id: str = HYPE_OKX_INSTRUMENT_ID,
    settle_currency: str = "USDT",
) -> bytes:
    return _json(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": instrument_id,
                    "state": "live",
                    "ctType": "linear",
                    "ctValCcy": "HYPE",
                    "settleCcy": settle_currency,
                    "ctVal": "0.1",
                    "ctMult": "1",
                    "lotSz": "1",
                    "minSz": "1",
                    "tickSz": "0.001",
                }
            ],
        }
    )


def _mark_body(
    *,
    instrument_id: str = HYPE_OKX_INSTRUMENT_ID,
    provider_at: datetime | None = None,
) -> bytes:
    return _json(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": instrument_id,
                    "markPx": "43.125",
                    "ts": _ms(provider_at or (_BASE + timedelta(seconds=7))),
                }
            ],
        }
    )


def _candles_body(*, unconfirmed_index: int | None = None) -> bytes:
    latest_open = _BASE - timedelta(minutes=15)
    earliest_open = latest_open - timedelta(minutes=15 * 95)
    rows: list[list[str]] = []
    for index in range(96):
        opened = earliest_open + timedelta(minutes=15 * index)
        close = f"{40 + index / 100:.2f}"
        rows.append(
            [
                _ms(opened),
                close,
                f"{40.5 + index / 100:.2f}",
                f"{39.5 + index / 100:.2f}",
                close,
                "100",
                "100",
                "4000",
                "0" if unconfirmed_index == index else "1",
            ]
        )
    return _json({"code": "0", "msg": "", "data": list(reversed(rows))})


def _open_interest_body(*, provider_at: datetime) -> bytes:
    return _json(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": HYPE_OKX_INSTRUMENT_ID,
                    "oi": "12345",
                    "oiCcy": "1234.5",
                    "oiUsd": "53240.625",
                    "ts": _ms(provider_at),
                }
            ],
        }
    )


def _seal_core(
    store: FileRawCaptureStore,
    *,
    cycle_id: str,
    instrument_body: bytes | None = None,
    mark_body: bytes | None = None,
    candles_body: bytes | None = None,
) -> None:
    boundary = _ms(_BASE)
    _seal(
        store,
        cycle_id=cycle_id,
        capture_id="server-time",
        component_id="SERVER_TIME",
        path=SERVER_TIME_PATH,
        query={},
        body=_server_body(),
        start_offset=0,
    )
    _seal(
        store,
        cycle_id=cycle_id,
        capture_id="instrument",
        component_id="INSTRUMENT",
        path=INSTRUMENT_PATH,
        query={"instId": HYPE_OKX_INSTRUMENT_ID, "instType": "SWAP"},
        body=instrument_body or _instrument_body(),
        start_offset=3,
    )
    _seal(
        store,
        cycle_id=cycle_id,
        capture_id="mark-price",
        component_id="MARK_PRICE",
        path=MARK_PRICE_PATH,
        query={"instId": HYPE_OKX_INSTRUMENT_ID, "instType": "SWAP"},
        body=mark_body or _mark_body(),
        start_offset=6,
    )
    _seal(
        store,
        cycle_id=cycle_id,
        capture_id="closed-candles-15m",
        component_id="CLOSED_CANDLES_15M",
        path=CLOSED_CANDLES_15M_PATH,
        query={
            "after": boundary,
            "bar": "15m",
            "instId": HYPE_OKX_INSTRUMENT_ID,
            "limit": "96",
        },
        body=candles_body or _candles_body(),
        start_offset=9,
    )


class V332HypeDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FileRawCaptureStore(Path(self.temp.name))

    def _replay(self, cycle_id: str = "hype-cycle-001", **kwargs):  # noqa: ANN003, ANN202
        service = build_hype_data_profile_service(raw_store=self.store)
        return service.replay(
            HYPE_OKX_PROFILE_ID,
            cycle_id=cycle_id,
            **kwargs,
        )

    def test_sealed_hype_core_admits_raw_bound_slice_and_pure_projection(self) -> None:
        cycle_id = "hype-cycle-admitted"
        _seal_core(self.store, cycle_id=cycle_id)
        _seal(
            self.store,
            cycle_id=cycle_id,
            capture_id="open-interest",
            component_id="OPEN_INTEREST",
            path=OPEN_INTEREST_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "instType": "SWAP"},
            body=_open_interest_body(
                provider_at=_BASE + timedelta(seconds=14, milliseconds=26)
            ),
            start_offset=12,
        )

        result = self._replay(cycle_id)

        self.assertEqual("ADMITTED", result.status)
        data_slice = result.data_slice
        self.assertIsNotNone(data_slice)
        assert data_slice is not None
        self.assertEqual("HYPE-USDT-SWAP", data_slice.instrument_identity.venue_symbol)
        self.assertEqual("HYPE", data_slice.instrument_identity.base_asset)
        self.assertEqual("USDT", data_slice.instrument_identity.quote_asset)
        self.assertEqual("USDT", data_slice.instrument_identity.settle_asset)
        self.assertEqual(5, len(data_slice.raw_refs))
        mark = data_slice.core_observations["mark_price"]
        self.assertEqual("USDT_PER_HYPE", mark["unit"])
        self.assertEqual("OKX", mark["venue"])
        self.assertIn(mark["raw_sha256"], {item.sha256 for item in data_slice.raw_refs})
        self.assertLessEqual(mark["available_at"], data_slice.cutoff_at)
        first_bar = data_slice.core_observations["closed_15m_bars"]["value"][0]
        self.assertEqual("100", first_bar["volume_contracts"])
        self.assertEqual("100", first_bar["volume_base"])
        self.assertEqual("4000", first_bar["volume_quote"])
        open_interest = data_slice.optional_observations["okx_open_interest"]
        self.assertEqual(
            _time(13),
            open_interest["observed_at"],
        )
        self.assertEqual(_time(14), open_interest["available_at"])
        self.assertEqual(
            (_BASE + timedelta(seconds=14, milliseconds=26))
            .isoformat()
            .replace("+00:00", "Z"),
            open_interest["value"]["provider_as_of"],
        )
        self.assertEqual(1026, open_interest["provider_clock_ahead_milliseconds"])

        projected = project_market_data_observation(data_slice)
        self.assertIsInstance(projected, MarketDataObservation)
        self.assertEqual(data_slice.cutoff_at, projected.cutoff_at)
        self.assertEqual(data_slice.data_cursor, data_slice.to_dict()["data_cursor"])
        self.assertEqual(
            data_slice.core_observations["mark_price"]["value"],
            projected.core_observations["mark_price"]["value"],
        )

    def test_missing_optional_data_remains_typed_unknown_not_zero(self) -> None:
        cycle_id = "hype-cycle-optional-unknown"
        _seal_core(self.store, cycle_id=cycle_id)

        data_slice = self._replay(cycle_id).data_slice

        assert data_slice is not None
        by_component = {item.component_id: item for item in data_slice.typed_unknowns}
        for component in (
            "ORDER_BOOK",
            "RECENT_TRADES",
            "OPEN_INTEREST",
            "FUNDING_RATE_HISTORY",
        ):
            self.assertEqual("UNKNOWN", by_component[component].status)
            self.assertIs(by_component[component].missing_is_zero, False)
        self.assertEqual({}, dict(data_slice.optional_observations))

    def test_instrument_identity_mismatch_fails_closed(self) -> None:
        cycle_id = "hype-cycle-identity-mismatch"
        _seal_core(
            self.store,
            cycle_id=cycle_id,
            instrument_body=_instrument_body(settle_currency="USDC"),
        )

        with self.assertRaisesRegex(
            OkxSnapshotError, "OKX_INSTRUMENT_IDENTITY_INVALID"
        ):
            self._replay(cycle_id)

    def test_mark_instrument_mismatch_fails_closed(self) -> None:
        cycle_id = "hype-cycle-mark-mismatch"
        _seal_core(
            self.store,
            cycle_id=cycle_id,
            mark_body=_mark_body(instrument_id="BTC-USDT-SWAP"),
        )

        with self.assertRaisesRegex(
            OkxSnapshotError, "OKX_MARK_INSTRUMENT_MISMATCH"
        ):
            self._replay(cycle_id)

    def test_unconfirmed_candle_is_not_admitted_as_closed(self) -> None:
        cycle_id = "hype-cycle-unconfirmed"
        _seal_core(
            self.store,
            cycle_id=cycle_id,
            candles_body=_candles_body(unconfirmed_index=95),
        )

        with self.assertRaisesRegex(
            OkxSnapshotError, "OKX_CLOSED_CANDLE_SCHEMA_INVALID"
        ):
            self._replay(cycle_id)

    def test_future_provider_datum_is_rejected(self) -> None:
        cycle_id = "hype-cycle-future"
        _seal_core(
            self.store,
            cycle_id=cycle_id,
            mark_body=_mark_body(provider_at=_BASE + timedelta(seconds=30)),
        )

        with self.assertRaisesRegex(OkxSnapshotError, "FUTURE_DATUM"):
            self._replay(cycle_id)

    def test_cutoff_before_available_at_is_pit_violation(self) -> None:
        cycle_id = "hype-cycle-pit"
        _seal_core(self.store, cycle_id=cycle_id)

        with self.assertRaisesRegex(OkxAssetProfileError, "PIT_VIOLATION"):
            self._replay(cycle_id, cutoff_at=_time(7))

    def test_old_core_at_later_cutoff_is_stale(self) -> None:
        cycle_id = "hype-cycle-stale"
        _seal_core(self.store, cycle_id=cycle_id)

        with self.assertRaisesRegex(OkxAssetProfileError, "CORE_STALE"):
            self._replay(cycle_id, cutoff_at=_time(132))

    def test_raw_sha_and_available_at_are_bound_to_sealed_store(self) -> None:
        cycle_id = "hype-cycle-raw-binding"
        _seal_core(self.store, cycle_id=cycle_id)

        data_slice = self._replay(cycle_id).data_slice

        assert data_slice is not None
        for capture in data_slice.capture_refs:
            loaded = self.store.verify_reference(
                cycle_id=cycle_id,
                reference=capture.raw_ref.to_dict(),
            )
            self.assertEqual(
                hashlib.sha256(loaded.payload).hexdigest(),
                capture.raw_ref.sha256,
            )
            self.assertEqual(
                loaded.summary["capture_completed_at"], capture.captured_at
            )

    def test_replay_is_deterministic(self) -> None:
        cycle_id = "hype-cycle-deterministic"
        _seal_core(self.store, cycle_id=cycle_id)

        first = self._replay(cycle_id).to_dict()
        second = self._replay(cycle_id).to_dict()

        self.assertEqual(first, second)

    def test_raw_only_partial_capture_set_is_incomplete_without_network(self) -> None:
        cycle_id = "hype-cycle-raw-only"
        _seal(
            self.store,
            cycle_id=cycle_id,
            capture_id="server-time",
            component_id="SERVER_TIME",
            path=SERVER_TIME_PATH,
            query={},
            body=_server_body(),
            start_offset=0,
        )

        result = self._replay(cycle_id)

        self.assertEqual("INCOMPLETE", result.status)
        self.assertIsNone(result.data_slice)
        self.assertEqual(
            ("instrument", "mark-price", "closed-candles-15m"),
            result.missing_capture_ids,
        )
        self.assertEqual(1, len(result.raw_refs))

    def test_thin_market_data_adapter_keeps_explicit_hype_identity(self) -> None:
        cycle_id = "hype-cycle-port"
        _seal_core(self.store, cycle_id=cycle_id)
        service = build_hype_data_profile_service(raw_store=self.store)
        adapter = AssetDataProfileMarketDataAdapter(
            service=service,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
        )

        observation = adapter.capture(
            MarketCaptureRequest(
                cycle_id=cycle_id,
                venue_id="OKX",
                instrument_id=HYPE_OKX_INSTRUMENT_ID,
                contract_type=HYPE_OKX_CONTRACT_IDENTITY,
                requested_at=_time(0),
                analysis_profile="COLD",
                data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
            )
        )

        self.assertEqual("43.125", observation.core_observations["mark_price"]["value"])

    def test_public_collection_requires_explicit_adapter_and_replays_primary_raw(self) -> None:
        cycle_id = "hype-cycle-explicit-collection"
        calls: list[str] = []
        store = self.store

        class _Collector:
            def collect(self, profile, *, request) -> None:  # noqa: ANN001
                calls.append(request.cycle_id)
                self_outer.assertEqual(HYPE_OKX_DATA_PROFILE, profile)
                _seal_core(store, cycle_id=request.cycle_id)

        self_outer = self
        request = MarketCaptureRequest(
            cycle_id=cycle_id,
            venue_id="OKX",
            instrument_id=HYPE_OKX_INSTRUMENT_ID,
            contract_type=HYPE_OKX_CONTRACT_IDENTITY,
            requested_at=_time(0),
            analysis_profile="COLD",
            data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        )
        replay_only = AssetDataProfileMarketDataAdapter(
            service=build_hype_data_profile_service(raw_store=store),
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
        )
        with self.assertRaisesRegex(
            Exception, "V332_MARKET_CAPTURE_RAW_INCOMPLETE"
        ):
            replay_only.capture(request)
        self.assertEqual([], calls)

        collecting = AssetDataProfileMarketDataAdapter(
            service=build_hype_data_profile_service(raw_store=store),
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            collector=_Collector(),
        )
        observation = collecting.capture(request)

        self.assertEqual([cycle_id], calls)
        self.assertEqual("43.125", observation.core_observations["mark_price"]["value"])
        self.assertIsNotNone(
            store.load_response(cycle_id=cycle_id, capture_id="mark-price")
        )

    def test_existing_input_snapshot_creator_accepts_v332_hype_slice(self) -> None:
        cycle_id = "hype-cycle-input-snapshot"
        _seal_core(self.store, cycle_id=cycle_id)
        adapter = AssetDataProfileMarketDataAdapter(
            service=build_hype_data_profile_service(raw_store=self.store),
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
        )
        request = CycleRequest(
            request_id="hype-v332-request",
            cycle_id=cycle_id,
            requested_at=_time(0),
            venue_id="OKX",
            instrument_id=HYPE_OKX_INSTRUMENT_ID,
            contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
            analysis_profile="COLD",
            data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
            outcome_horizon_seconds=3600,
            outcome_tolerance_seconds=60,
            lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
            theory_identity=V332_THEORY_IDENTITY,
        )

        snapshot = capture_input_snapshot(
            request,
            market_data=adapter,
            clock=lambda: _time(20),
        )

        self.assertEqual(V332_THEORY_IDENTITY, snapshot.theory_identity)
        self.assertEqual("43.125", snapshot.core_observations["mark_price"]["value"])
        self.assertEqual(HYPE_OKX_INSTRUMENT_ID, snapshot.instrument_id)


if __name__ == "__main__":
    unittest.main()
