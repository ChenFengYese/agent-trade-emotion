from __future__ import annotations

import unittest

from trade_system.theory_paper_v2.application.market_cycle.data_profiles import (
    AssetDataProfileError,
    AssetDataReplayResultV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import ArtifactRef
from trade_system.theory_paper_v2.domain.market_cycle.data import (
    AssetDataContractError,
    CaptureRefV1,
    InstrumentIdentityV1,
    TypedUnknownV1,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    profile_for_asset,
)
from trade_system.theory_paper_v2.infrastructure.market_data.source_catalog import (
    OKX_SOURCE_CATALOG,
)


def _raw_ref(capture_id: str = "instrument") -> ArtifactRef:
    return ArtifactRef(
        artifact_type="RawCapture",
        artifact_id=f"cycle-v332.{capture_id}.raw",
        path=f"raw/{capture_id}/body.bin",
        size_bytes=10,
        sha256="a" * 64,
    )


class V332DataContractTests(unittest.TestCase):
    def test_instrument_identity_reuses_existing_artifact_ref(self) -> None:
        identity = InstrumentIdentityV1(
            instrument_key="OKX:HYPE-USDT-SWAP:SWAP:linear",
            venue="OKX",
            market_type="SWAP",
            venue_symbol="HYPE-USDT-SWAP",
            base_asset="HYPE",
            quote_asset="USDT",
            settle_asset="USDT",
            underlying_identity="CRYPTO_ASSET:HYPE",
            product_identity="OKX_SWAP:HYPE-USDT-SWAP",
            contract_semantics="LINEAR_PERPETUAL_SWAP",
            quantity_basis="1 HYPE PER_CONTRACT X 1",
            session_semantics="CONTINUOUS_24X7_PROVIDER_SESSION",
            status="ACTIVE",
            effective_at="2026-08-13T00:00:00Z",
            discovered_at="2026-08-13T00:00:01Z",
            source_ref=_raw_ref(),
        )

        self.assertIsInstance(identity.source_ref, ArtifactRef)
        self.assertEqual("HYPE-USDT-SWAP", identity.to_dict()["venue_symbol"])
        self.assertEqual(
            identity,
            InstrumentIdentityV1.from_dict(identity.to_dict()),
        )

    def test_instrument_effective_time_cannot_follow_discovery(self) -> None:
        with self.assertRaisesRegex(
            AssetDataContractError,
            "V332_DATA_INSTRUMENT_EFFECTIVE_AFTER_DISCOVERY",
        ):
            InstrumentIdentityV1(
                instrument_key="OKX:HYPE-USDT-SWAP:SWAP:linear",
                venue="OKX",
                market_type="SWAP",
                venue_symbol="HYPE-USDT-SWAP",
                base_asset="HYPE",
                quote_asset="USDT",
                settle_asset="USDT",
                underlying_identity="CRYPTO_ASSET:HYPE",
                product_identity="OKX_SWAP:HYPE-USDT-SWAP",
                contract_semantics="LINEAR_PERPETUAL_SWAP",
                quantity_basis="1 HYPE PER_CONTRACT X 1",
                session_semantics="CONTINUOUS_24X7_PROVIDER_SESSION",
                status="ACTIVE",
                effective_at="2026-08-13T00:00:02Z",
                discovered_at="2026-08-13T00:00:01Z",
                source_ref=_raw_ref(),
            )

    def test_capture_ref_binds_time_request_and_raw_artifact(self) -> None:
        capture = CaptureRefV1(
            capture_id="instrument",
            source_id="okx.public.swap_instrument",
            request_binding={
                "component_id": "INSTRUMENT",
                "method": "GET",
                "path": "/api/v5/public/instruments",
                "query": {"instId": "HYPE-USDT-SWAP", "instType": "SWAP"},
                "route_policy_id": "FIXTURE",
                "attempt_number": 1,
                "retry_allowed": False,
            },
            request_started_at="2026-08-13T00:00:00Z",
            response_received_at="2026-08-13T00:00:01Z",
            captured_at="2026-08-13T00:00:02Z",
            raw_ref=_raw_ref(),
            parser_version="okx-baseline-price-v1",
        )

        self.assertEqual("RawCapture", capture.raw_ref.artifact_type)
        self.assertEqual("a" * 64, capture.to_dict()["raw_ref"]["sha256"])

    def test_typed_unknown_cannot_be_zero(self) -> None:
        unknown = TypedUnknownV1(
            component_id="OPEN_INTEREST",
            source_id="okx.public.open_interest",
            missing_reason="NOT_CAPTURED",
            claim_ceiling="UNKNOWN_ONLY",
        )
        self.assertEqual("UNKNOWN", unknown.status)
        self.assertIs(unknown.to_dict()["missing_is_zero"], False)
        with self.assertRaisesRegex(
            AssetDataContractError, "V332_DATA_TYPED_UNKNOWN_INVALID"
        ):
            TypedUnknownV1(
                component_id="OPEN_INTEREST",
                source_id="okx.public.open_interest",
                missing_reason="NOT_CAPTURED",
                claim_ceiling="UNKNOWN_ONLY",
                missing_is_zero=True,
            )

    def test_source_catalog_freezes_time_window_and_claim_ceiling(self) -> None:
        self.assertEqual(4, len(OKX_SOURCE_CATALOG.core_routes))
        self.assertEqual(4, len(OKX_SOURCE_CATALOG.optional_routes))
        for route in OKX_SOURCE_CATALOG.routes:
            contract = route.contract
            self.assertEqual("NO_AUTH_PUBLIC", contract.access_mode)
            self.assertTrue(contract.history_window)
            self.assertTrue(contract.event_time_semantics)
            self.assertTrue(contract.publish_time_semantics)
            self.assertTrue(contract.claim_ceiling)
            self.assertGreaterEqual(contract.max_staleness_seconds, 0)

    def test_profile_lookup_has_no_implicit_btc_fallback(self) -> None:
        self.assertEqual(HYPE_OKX_DATA_PROFILE, profile_for_asset("HYPE"))
        with self.assertRaisesRegex(
            AssetDataProfileError, "V332_DATA_PROFILE_NOT_REGISTERED:BTC"
        ):
            profile_for_asset("BTC")

    def test_raw_only_result_is_explicitly_incomplete(self) -> None:
        result = AssetDataReplayResultV1(
            status="INCOMPLETE",
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            cycle_id="cycle-v332",
            data_slice=None,
            raw_refs=(_raw_ref("server-time"),),
            missing_capture_ids=("instrument", "mark-price", "closed-candles-15m"),
            reason="RAW_CAPTURE_SET_INCOMPLETE",
        )

        self.assertEqual("INCOMPLETE", result.status)
        self.assertIsNone(result.slice)
        self.assertEqual("RAW_CAPTURE_SET_INCOMPLETE", result.reason)


if __name__ == "__main__":
    unittest.main()
