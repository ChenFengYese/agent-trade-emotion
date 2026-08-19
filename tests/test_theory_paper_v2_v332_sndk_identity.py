from __future__ import annotations

import unittest

from trade_system.theory_paper_v2.domain.market_cycle.instruments import (
    InstrumentIdentityError,
    sndk_identity_graph,
)


class V332SndkIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = sndk_identity_graph(
            discovered_at="2026-08-12T16:16:37+00:00"
        )

    def test_three_market_surfaces_remain_distinct(self) -> None:
        self.assertEqual(len(self.graph.nodes), 4)
        self.assertEqual(
            self.graph.admitted_market(
                "spot:kraken-international:SNDKx-USD"
            ).symbol,
            "SNDKx-USD",
        )
        self.assertEqual(
            self.graph.admitted_market("perp:okx:SNDK-USDT-SWAP").symbol,
            "SNDK-USDT-SWAP",
        )
        with self.assertRaisesRegex(
            InstrumentIdentityError, "distinct product identities"
        ):
            self.graph.require_same_product(
                "spot:kraken-international:SNDKx-USD",
                "perp:okx:SNDK-USDT-SWAP",
            )

    def test_okx_perpetual_does_not_inherit_backed_identity(self) -> None:
        relationship = next(
            relationship
            for relationship in self.graph.relationships
            if relationship.source_product_id == "perp:okx:SNDK-USDT-SWAP"
            and relationship.target_product_id == "token:backed:SNDKx"
        )
        self.assertEqual(relationship.relationship, "IDENTITY_NOT_ESTABLISHED")
        self.assertEqual(relationship.admission_status, "NOT_ADMITTED")

    def test_unobserved_okx_state_is_unknown_not_absent(self) -> None:
        graph = sndk_identity_graph(
            discovered_at="2026-08-12T16:16:37+00:00",
            include_okx_swap=False,
        )
        self.assertEqual(graph.node("perp:okx:SNDK-USDT-SWAP").status, "UNKNOWN")
        with self.assertRaisesRegex(InstrumentIdentityError, "not an admitted"):
            graph.admitted_market("perp:okx:SNDK-USDT-SWAP")


if __name__ == "__main__":
    unittest.main()
