from __future__ import annotations

from datetime import UTC, datetime
import unittest

from external_data_interface.domain.contracts import (
    AccessMode,
    CaptureStatus,
    SourceDefinition,
    TransportKind,
    source_readiness,
)
from external_data_interface.infrastructure.catalog import SourceCatalog


class ContractAndCatalogTests(unittest.TestCase):
    def test_no_auth_source_is_ready_without_environment(self) -> None:
        source = SourceDefinition(
            source_id="test.public",
            family="test",
            dataset="test",
            provider="test",
            access_mode=AccessMode.NO_AUTH,
            transport=TransportKind.HTTP,
            endpoint="https://example.test/data",
            terms_url="https://example.test/terms",
            cadence="once",
            history="none",
            time_semantics="capture time",
            claim_ceiling="test only",
            default_enabled=True,
        )
        self.assertEqual(
            source_readiness(source, environment={}, parameters={}), (None, None)
        )

    def test_catalog_covers_every_current_missing_family(self) -> None:
        catalog = SourceCatalog()
        ids = {source.definition.source_id for source in catalog.list()}
        expected = {
            "okx.order_book_stream",
            "okx.liquidation_stream",
            "okx.taker_volume",
            "okx.long_short_contract",
            "bls.labor_snapshot",
            "treasury.yield_curve",
            "gdelt.bitcoin_news",
            "coinmetrics.btc_daily",
            "blockstream.mempool",
            "defillama.stablecoins",
            "cboe.vix_daily",
            "cftc.cot_current",
            "nyfed.primary_dealer_latest",
            "google_trends.manual_csv",
            "bluesky.search_posts",
            "sec.submissions",
            "execution.account_truth",
            "eia.bulk_manifest",
            "fred_graph.nfci_leverage",
        }
        self.assertTrue(expected.issubset(ids), expected - ids)
        self.assertEqual(len(ids), len(catalog.list()))
        self.assertEqual(len(ids), 70)

    def test_default_sources_require_no_credentials_and_are_not_streams(self) -> None:
        definitions = [
            source.definition
            for source in SourceCatalog().list()
            if source.definition.default_enabled
        ]
        self.assertEqual(len(definitions), 50)
        self.assertTrue(
            all(item.access_mode is AccessMode.NO_AUTH for item in definitions)
        )
        self.assertTrue(all(not item.stream for item in definitions))

    def test_every_no_auth_adapter_builds_with_no_environment(self) -> None:
        now = datetime(2026, 8, 12, tzinfo=UTC)
        built = []
        for source in SourceCatalog().list():
            if source.definition.access_mode is not AccessMode.NO_AUTH:
                continue
            request = source.build_request(parameters={}, environment={}, now=now)
            self.assertTrue(request.url.startswith(("https://", "wss://")))
            built.append(source.definition.source_id)
        self.assertEqual(len(built), 53)

    def test_public_fred_graph_request_needs_no_key_and_has_bounded_history(self) -> None:
        request = SourceCatalog().get("fred_graph.treasury_10y").build_request(
            parameters={}, environment={}, now=datetime(2026, 8, 12, tzinfo=UTC)
        )
        self.assertNotIn("api_key", request.url)
        self.assertIn("id=DGS10", request.url)
        self.assertIn("cosd=2023-08-10", request.url)

    def test_secret_sources_redact_request_metadata(self) -> None:
        catalog = SourceCatalog()
        now = datetime(2026, 8, 12, tzinfo=UTC)
        fred = catalog.get("fred.series").build_request(
            parameters={"realtime_start": "2025-01-01", "realtime_end": "2025-01-01"},
            environment={"FRED_API_KEY": "super-secret"},
            now=now,
        )
        self.assertIn("super-secret", fred.url)
        self.assertNotIn("super-secret", fred.stored_url)
        self.assertIn("realtime_start=2025-01-01", fred.url)
        sec = catalog.get("sec.submissions").build_request(
            parameters={"cik": "1364742"},
            environment={"SEC_USER_AGENT": "Project real@example.com"},
            now=now,
        )
        self.assertEqual(sec.headers["User-Agent"], "Project real@example.com")
        self.assertEqual(sec.stored_headers["User-Agent"], "CONFIGURED_REDACTED")
        for source_id, variable in (
            ("eia.crude_stocks", "EIA_API_KEY"),
            ("bea.gdp", "BEA_USER_ID"),
            ("youtube.search", "YOUTUBE_API_KEY"),
            ("alphavantage.daily", "ALPHAVANTAGE_API_KEY"),
        ):
            request = catalog.get(source_id).build_request(
                parameters={}, environment={variable: "secret-value"}, now=now
            )
            self.assertIn("secret-value", request.url)
            self.assertNotIn("secret-value", request.stored_url)

    def test_okx_stream_allows_only_the_documented_primary_and_backup_routes(self) -> None:
        source = SourceCatalog().get("okx.order_book_stream")
        now = datetime(2026, 8, 12, tzinfo=UTC)
        primary = source.build_request(parameters={}, environment={}, now=now)
        backup = source.build_request(
            parameters={"route": "aws"}, environment={}, now=now
        )
        self.assertEqual(primary.url, "wss://ws.okx.com:8443/ws/v5/public")
        self.assertEqual(backup.url, "wss://wsaws.okx.com:8443/ws/v5/public")
        with self.assertRaisesRegex(ValueError, "V332_OKX_WS_ROUTE_INVALID"):
            source.build_request(
                parameters={"route": "unapproved"}, environment={}, now=now
            )

    def test_unobservable_is_not_reported_as_waiting_for_a_key(self) -> None:
        definition = SourceCatalog().get("institution.current_intent").definition
        status, reason = source_readiness(
            definition, environment={}, parameters={}
        )
        self.assertIs(status, CaptureStatus.UNOBSERVABLE)
        self.assertEqual(reason, "PUBLIC_SOURCE_CANNOT_OBSERVE_THIS_FACT")


if __name__ == "__main__":
    unittest.main()
