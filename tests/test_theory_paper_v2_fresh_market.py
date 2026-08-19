from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market import (
    BinanceUsdmFreshCollector,
    FreshMarketFreezeError,
    HttpCapture,
    UrllibPublicHttpTransport,
    freeze_binance_btcusdt_hourly,
    verify_fresh_market_bundle,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    BinanceUsdmCollectionError,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.quality import (
    FORMAL_EXPERIMENT_CONTRACT_DIGEST,
    prepare_fresh_market_dataset,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.store import (
    FreshMarketStoreError,
)


HOUR_MS = 3_600_000


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def _exchange_info(*, trading: bool = True) -> dict[str, object]:
    return {
        "timezone": "UTC",
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING" if trading else "BREAK",
                "contractType": "PERPETUAL",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": "0.10",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.001",
                    },
                ],
            }
        ],
    }


def _kline(open_time_ms: int) -> list[object]:
    basis = 10_000 + (open_time_ms // HOUR_MS) % 1_000
    return [
        open_time_ms,
        str(basis),
        str(basis + 10),
        str(basis - 10),
        str(basis + 5),
        "100.000",
        open_time_ms + HOUR_MS - 1,
        "1000000.000",
        10,
        "50.000",
        "500000.000",
        "0",
    ]


class FakeBinanceTransport:
    def __init__(
        self,
        *,
        server_time_ms: int,
        gap: bool = False,
        duplicate: bool = False,
        trading: bool = True,
        pretty_exchange: bool = False,
        mutate_open_time_ms: int | None = None,
    ) -> None:
        self.server_time_ms = server_time_ms
        self.received_at = (
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(milliseconds=server_time_ms, seconds=1)
        )
        self.gap = gap
        self.duplicate = duplicate
        self.trading = trading
        self.pretty_exchange = pretty_exchange
        self.mutate_open_time_ms = mutate_open_time_ms
        self.requested_urls: list[str] = []
        self.bodies: dict[str, bytes] = {}

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.requested_urls.append(url)
        parsed = urlsplit(url)
        if parsed.path == "/fapi/v1/time":
            body = _json_bytes({"serverTime": self.server_time_ms})
        elif parsed.path == "/fapi/v1/exchangeInfo":
            body = _json_bytes(
                _exchange_info(trading=self.trading),
                pretty=self.pretty_exchange,
            )
        elif parsed.path == "/fapi/v1/klines":
            query = parse_qs(parsed.query)
            start = int(query["startTime"][0])
            end = int(query["endTime"][0])
            limit = int(query["limit"][0])
            self.assert_query = (start, end, limit)
            rows = [_kline(start + index * HOUR_MS) for index in range(limit)]
            if self.gap:
                rows.pop(100)
            if self.duplicate:
                rows[101][0] = rows[100][0]
                rows[101][6] = rows[100][6]
            if self.mutate_open_time_ms is not None:
                for row in rows:
                    if row[0] == self.mutate_open_time_ms:
                        row[4] = str(int(str(row[4])) + 1)
                        break
            body = _json_bytes(rows)
        else:
            raise AssertionError(parsed.path)
        self.bodies[parsed.path] = body
        return HttpCapture(
            status=200,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Date": "Fri, 31 Jul 2026 10:30:01 GMT",
            },
            body=body,
            received_at=self.received_at,
            final_url=url,
        )


def _collector(
    transport: FakeBinanceTransport,
) -> BinanceUsdmFreshCollector:
    started = transport.received_at - timedelta(seconds=1)
    return BinanceUsdmFreshCollector(
        transport=transport,
        clock=lambda: started,
        timeout=2,
    )


class FreshMarketFreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server_time_ms = int(
            datetime(
                2026, 7, 31, 10, 30, tzinfo=timezone.utc
            ).timestamp()
            * 1000
        )

    def test_formal_capture_freezes_256_closed_bars_and_96_pit_slots(
        self,
    ) -> None:
        transport = FakeBinanceTransport(
            server_time_ms=self.server_time_ms
        )
        with tempfile.TemporaryDirectory() as directory:
            result = freeze_binance_btcusdt_hourly(
                output_root=Path(directory),
                bundle_id="formal-market-001",
                collector=_collector(transport),
            )
            self.assertEqual(result.quality_status.value, "PASS")
            self.assertEqual(result.closed_bar_count, 256)
            self.assertEqual(result.decision_slot_count, 96)
            verified = verify_fresh_market_bundle(result.bundle_root)
            self.assertEqual(
                verified.manifest_digest, result.manifest_digest
            )
            manifest = load_json_strict(result.manifest_path)
            self.assertEqual(
                manifest["experiment_contract_digest"],
                FORMAL_EXPERIMENT_CONTRACT_DIGEST,
            )
            self.assertEqual(
                manifest["decision_indices_inclusive"], [96, 191]
            )
            self.assertEqual(
                manifest["outcome_horizons_hours"], [1, 4, 8, 24]
            )
            verify_self_digest(manifest, "manifest_digest")
            dataset = load_json_strict(
                result.bundle_root / "normalized" / "dataset.json"
            )
            self.assertEqual(len(dataset["bars"]), 256)
            self.assertEqual(len(dataset["decision_slots"]), 96)
            self.assertEqual(len(dataset["outcome_bindings"]), 384)
            first = dataset["decision_slots"][0]
            self.assertEqual(len(first["visible_bar_ids"]), 97)
            self.assertEqual(
                first["visible_through_bar_id"],
                dataset["bars"][96]["bar_id"],
            )
            for binding in dataset["outcome_bindings"]:
                slot = dataset["decision_slots"][
                    binding["decision_bar_index"] - 96
                ]
                self.assertFalse(binding["role_visible"])
                self.assertNotIn(
                    binding["outcome_bar_id"],
                    slot["visible_bar_ids"],
                )
            unknowns = [
                field
                for field in first["interface_fields"]
                if field["status"] == "UNKNOWN"
            ]
            self.assertTrue(unknowns)
            self.assertTrue(
                all(
                    field["value"] is None and field["reason_code"]
                    for field in unknowns
                )
            )
            self.assertTrue(
                all(
                    bar["availability_status"] == "DERIVED"
                    and bar["availability_basis"]
                    == "PROVIDER_CLOSED_BAR_PROTOCOL"
                    and bar["decision_contemporaneous_status"]
                    == "UNKNOWN"
                    for bar in dataset["bars"]
                )
            )
            kline_url = next(
                url
                for url in transport.requested_urls
                if "/klines?" in url
            )
            query = parse_qs(urlsplit(kline_url).query)
            current_hour = (
                self.server_time_ms // HOUR_MS
            ) * HOUR_MS
            self.assertEqual(
                int(query["endTime"][0]), current_hour - 1
            )
            self.assertEqual(int(query["limit"][0]), 256)
            raw_path = (
                result.bundle_root
                / "raw"
                / "binance-usdm-btcusdt-1h-klines.body"
            )
            self.assertEqual(
                raw_path.read_bytes(),
                transport.bodies["/fapi/v1/klines"],
            )
            self.assertEqual(
                hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                next(
                    item["sha256"]
                    for item in manifest["artifacts"]
                    if item["relative_path"]
                    == "raw/binance-usdm-btcusdt-1h-klines.body"
                ),
            )
            raw_path.write_bytes(raw_path.read_bytes() + b"\n")
            with self.assertRaises(FreshMarketFreezeError):
                verify_fresh_market_bundle(result.bundle_root)

    def test_gap_duplicate_and_illegal_instrument_fail_quality(self) -> None:
        cases = (
            {"gap": True},
            {"duplicate": True},
            {"trading": False},
        )
        for case in cases:
            with self.subTest(case=case):
                transport = FakeBinanceTransport(
                    server_time_ms=self.server_time_ms, **case
                )
                responses = _collector(transport).collect()
                prepared = prepare_fresh_market_dataset(responses)
                self.assertEqual(
                    prepared.quality.overall_status.value, "FAIL"
                )
                self.assertTrue(prepared.quality.hard_failures)

    def test_cross_cycle_overlap_is_bound_and_revision_fails(self) -> None:
        first_transport = FakeBinanceTransport(
            server_time_ms=self.server_time_ms
        )
        second_server = self.server_time_ms + HOUR_MS
        with tempfile.TemporaryDirectory() as directory:
            first = freeze_binance_btcusdt_hourly(
                output_root=Path(directory),
                bundle_id="cycle-001",
                collector=_collector(first_transport),
            )
            second_transport = FakeBinanceTransport(
                server_time_ms=second_server
            )
            second = freeze_binance_btcusdt_hourly(
                output_root=Path(directory),
                bundle_id="cycle-002",
                collector=_collector(second_transport),
                prior_bundle_root=first.bundle_root,
            )
            self.assertEqual(second.quality_status.value, "PASS")
            prior_data = load_json_strict(
                first.bundle_root / "normalized" / "dataset.json"
            )
            changed_open = prior_data["bars"][100]["open_time_ms"]
            third_transport = FakeBinanceTransport(
                server_time_ms=second_server,
                mutate_open_time_ms=changed_open,
            )
            revised = freeze_binance_btcusdt_hourly(
                output_root=Path(directory),
                bundle_id="cycle-003",
                collector=_collector(third_transport),
                prior_bundle_root=first.bundle_root,
            )
            self.assertEqual(revised.quality_status.value, "FAIL")
            quality = load_json_strict(
                revised.bundle_root / "receipts" / "quality.json"
            )
            cross = next(
                check
                for check in quality["checks"]
                if check["check_id"] == "cross_cycle_consistency"
            )
            self.assertEqual(cross["status"], "FAIL")
            self.assertEqual(
                cross["reason_codes"], ["CROSS_CYCLE_BAR_REVISION"]
            )

    def test_bundle_write_once_rejects_changed_exact_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            freeze_binance_btcusdt_hourly(
                output_root=Path(directory),
                bundle_id="write-once-001",
                collector=_collector(
                    FakeBinanceTransport(
                        server_time_ms=self.server_time_ms
                    )
                ),
            )
            with self.assertRaises(FreshMarketStoreError):
                freeze_binance_btcusdt_hourly(
                    output_root=Path(directory),
                    bundle_id="write-once-001",
                    collector=_collector(
                        FakeBinanceTransport(
                            server_time_ms=self.server_time_ms,
                            pretty_exchange=True,
                        )
                    ),
                )

    def test_public_transport_rejects_non_allowlisted_source(self) -> None:
        with self.assertRaises(BinanceUsdmCollectionError):
            UrllibPublicHttpTransport().get(
                "https://example.com/fapi/v1/time", timeout=1
            )


if __name__ == "__main__":
    unittest.main()
