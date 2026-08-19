from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from decimal import Decimal

from trade_system.theory_paper_v2.domain.behavior_planning import legal_action_keys
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.financial_evaluation import (
    build_financial_evaluation_receipt,
)
from trade_system.theory_paper_v2.domain.probability_cloud import ProbabilityMode
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    build_minimal_experiment_contract,
)
from trade_system.theory_paper_v2.domain.v31_financial_shadow import (
    V31FinancialShadowError,
    build_frozen_financial_shadow_runtime,
    build_frozen_shadow_financial_evaluation,
    verify_frozen_financial_shadow_runtime,
)


DECISION_AT = "2026-08-07T10:00:00Z"


def experiment_contract() -> dict:
    return build_minimal_experiment_contract(
        contract_id="contract:v31:financial-shadow",
        run_id="run:v31:financial-shadow",
        frozen_at="2026-08-07T09:00:00Z",
    )


def native_market_economics() -> dict[str, str]:
    return {
        "symbol": "BTC-USDT-SWAP",
        "available_at": "2026-08-07T09:59:59Z",
        "mark_price": "60000.03",
        "contract_multiplier": "0.01",
        "contract_size_multiplier": "1",
        "quantity_step_contracts": "0.01",
        "minimum_quantity_contracts": "0.01",
        "price_tick_usdt": "0.1",
        "long_protective_stop_price": "58800",
        "short_protective_stop_price": "61200.1",
    }


def candidate_documents() -> tuple[dict[str, object], ...]:
    common = {
        "target_lot_ids": [],
        "authorized": False,
        "path_refs": ["path:fixture"],
    }
    return (
        {
            **common,
            "candidate_id": "candidate:wait",
            "action": "WAIT",
            "scale_pct": None,
            "target_role": None,
        },
        {
            **common,
            "candidate_id": "candidate:long",
            "action": "OPEN_LONG",
            "scale_pct": 25,
            "target_role": "TACTICAL",
        },
        {
            **common,
            "candidate_id": "candidate:short",
            "action": "OPEN_SHORT",
            "scale_pct": 25,
            "target_role": "TACTICAL",
        },
    )


class V31FrozenFinancialShadowTests(unittest.TestCase):
    def test_contract_and_pit_market_build_the_exact_flat_three_action_runtime(
        self,
    ) -> None:
        contract = experiment_contract()
        native = native_market_economics()
        runtime = build_frozen_financial_shadow_runtime(
            experiment_contract=contract,
            decision_at=DECISION_AT,
            native_market_economics=native,
        )

        self.assertEqual("FLAT", runtime.position_truth_input()["intended_side"])
        self.assertEqual([], runtime.position_truth_input()["lots"])
        self.assertEqual([], runtime.position_truth_input()["pending_orders"])
        self.assertEqual(8, len(runtime.risk_policy_input()))
        self.assertEqual((25,), runtime.entry_scale_grid_pct)
        self.assertEqual(("TACTICAL",), runtime.allowed_entry_roles)
        self.assertEqual(3, runtime.legal_candidate_count)
        self.assertEqual("58800", runtime.long_protective_stop_price)
        self.assertEqual("61200.1", runtime.short_protective_stop_price)
        context = runtime.decision_context(
            probability_mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
            probability_cloud_digest="c" * 64,
        )
        self.assertEqual(3, len(legal_action_keys(context)))

    def test_official_evaluation_discretizes_quantity_and_prices_adversely(
        self,
    ) -> None:
        contract = experiment_contract()
        native = native_market_economics()
        runtime = build_frozen_financial_shadow_runtime(
            experiment_contract=contract,
            decision_at=DECISION_AT,
            native_market_economics=native,
        )
        context, receipt = build_frozen_shadow_financial_evaluation(
            runtime=runtime,
            experiment_contract=contract,
            native_market_economics=native,
            cycle_index=1,
            evaluated_at=DECISION_AT,
            probability_mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
            probability_cloud_digest="c" * 64,
            candidates=candidate_documents(),
        )
        by_id = {row["candidate_id"]: row for row in receipt["evaluations"]}
        long = by_id["candidate:long"]
        short = by_id["candidate:short"]
        self.assertEqual("0.41", long["economics"]["quantity_delta"])
        self.assertEqual("0.41", short["economics"]["quantity_delta"])
        self.assertGreater(
            Decimal(long["economics"]["unrounded_quantity_delta"]),
            Decimal(long["economics"]["quantity_delta"]),
        )
        self.assertEqual("60120.1", long["economics"]["estimated_fill_price"])
        self.assertEqual("59880", short["economics"]["estimated_fill_price"])
        self.assertEqual("58800", long["economics"]["protective_stop_after"])
        self.assertEqual("61200.1", short["economics"]["protective_stop_after"])
        self.assertEqual("UNKNOWN_NOT_INCLUDED", receipt["funding_cost_status"])
        self.assertFalse(receipt["funding_cost_included"])
        self.assertIsNone(receipt["funding_cost_usdt"])
        self.assertEqual(context.portfolio_truth_digest, receipt["portfolio_truth_digest"])

    def test_below_minimum_is_infeasible_and_never_rounded_up(self) -> None:
        position = {
            "intended_side": "FLAT",
            "mark_price": "100.03",
            "contract_multiplier": "1",
            "reentry_contract_active": False,
            "account": {
                "equity_usdt": "2000",
                "margin_used_usdt": "0",
                "margin_available_usdt": "2000",
                "max_gross_leverage": "2",
            },
            "lots": [],
            "pending_orders": [],
        }
        policy = {
            "fee_rate": "0.001",
            "slippage_rate": "0.002",
            "initial_margin_rate": "0.5",
            "max_gross_leverage": "2",
            "portfolio_risk_cap_usdt": "500",
            "symbol_risk_cap_usdt": "300",
            "gross_notional_cap_usdt": "5000",
            "symbol_notional_cap_usdt": "3000",
        }
        market = {
            "symbol": "BTC-USDT-SWAP",
            "available_at": DECISION_AT,
            "mark_price": "100.03",
            "contract_multiplier": "1",
            "contract_size_multiplier": "1",
            "quantity_step_contracts": "1",
            "minimum_quantity_contracts": "10",
            "price_tick_usdt": "0.1",
            "long_protective_stop_price": "98",
            "short_protective_stop_price": "103",
        }
        candidate = candidate_documents()[1]
        receipt = build_financial_evaluation_receipt(
            run_id="run:minimum",
            cycle_index=1,
            decision_at=DECISION_AT,
            evaluated_at=DECISION_AT,
            symbol="BTC-USDT-SWAP",
            position_truth=position,
            risk_policy=policy,
            market_economics=market,
            probability_mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
            probability_cloud_digest="c" * 64,
            calibration_receipt_digests=(),
            proper_scoring_receipt_digests=(),
            oos_evaluation_receipt_digests=(),
            candidates=(candidate,),
        )
        evaluation = receipt["evaluations"][0]
        self.assertFalse(evaluation["feasible"])
        self.assertIn("BELOW_MINIMUM_QUANTITY", evaluation["infeasible_reasons"])
        self.assertEqual("7", evaluation["economics"]["quantity_delta"])
        self.assertNotEqual("10", evaluation["economics"]["quantity_delta"])
        self.assertEqual("100.3", evaluation["economics"]["estimated_fill_price"])

    def test_contract_market_stop_and_runtime_drift_all_fail_closed(self) -> None:
        contract = experiment_contract()
        native = native_market_economics()
        runtime = build_frozen_financial_shadow_runtime(
            experiment_contract=contract,
            decision_at=DECISION_AT,
            native_market_economics=native,
        )

        for field, drifted in (
            ("contract_multiplier", "0.02"),
            ("contract_size_multiplier", "2"),
            ("quantity_step_contracts", "0.02"),
            ("minimum_quantity_contracts", "0.02"),
            ("price_tick_usdt", "0.2"),
        ):
            with self.subTest(field=field):
                bad_native = {**native, field: drifted}
                with self.assertRaises(V31FinancialShadowError):
                    build_frozen_financial_shadow_runtime(
                        experiment_contract=contract,
                        decision_at=DECISION_AT,
                        native_market_economics=bad_native,
                    )

        bad_stop = {**native, "long_protective_stop_price": "58799.9"}
        with self.assertRaisesRegex(
            V31FinancialShadowError,
            "V31_FINANCIAL_RUNTIME_PROTECTIVE_STOP_DRIFT",
        ):
            build_frozen_financial_shadow_runtime(
                experiment_contract=contract,
                decision_at=DECISION_AT,
                native_market_economics=bad_stop,
            )

        bad_contract = copy.deepcopy(contract)
        bad_contract["portfolio_scope"]["financial_shadow"]["risk_policy"][
            "fee_rate"
        ] = "0.0001"
        bad_contract.pop("experiment_contract_digest")
        bad_contract = self_digest(bad_contract, "experiment_contract_digest")
        with self.assertRaises(V31FinancialShadowError):
            build_frozen_financial_shadow_runtime(
                experiment_contract=bad_contract,
                decision_at=DECISION_AT,
                native_market_economics=native,
            )

        forged = replace(runtime, equity_usdt="9999")
        with self.assertRaisesRegex(
            V31FinancialShadowError, "V31_FINANCIAL_RUNTIME_DRIFT"
        ):
            verify_frozen_financial_shadow_runtime(
                runtime=forged,
                experiment_contract=contract,
                native_market_economics=native,
            )


if __name__ == "__main__":
    unittest.main()
