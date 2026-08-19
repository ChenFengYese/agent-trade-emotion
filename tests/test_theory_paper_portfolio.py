import copy
import json
import unittest
from datetime import datetime, timezone

from trade_system.theory_paper.common import TheoryPaperError
from trade_system.theory_paper.portfolio import (
    PAPER_ONLY_MODE,
    deterministic_chaos_schedule,
    initialize_portfolio,
    inject_due_chaos,
    inject_manual_chaos,
    portfolio_metrics,
    process_market_bars,
    submit_actions,
    validate_portfolio_state,
)


def market(
    symbol: str,
    *,
    observed_at: str,
    price: float,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close_time_ms: int | None = None,
) -> dict:
    bar = None
    if close_time_ms is not None:
        bar = {
            "open": open_price if open_price is not None else price,
            "high": high if high is not None else price,
            "low": low if low is not None else price,
            "close": price,
            "close_time": close_time_ms,
        }
    return {
        "observed_at": observed_at,
        "symbols": [
            {
                "symbol": symbol,
                "observed_at": observed_at,
                "measures": {
                    "price": price,
                    "timeframes": {"1h": {"last_closed_bar": bar}},
                },
            }
        ],
    }


class TheoryPaperPortfolioTests(unittest.TestCase):
    def test_default_initial_state_is_exact_exogenous_paper_plan(self):
        state = initialize_portfolio(observed_at="2026-07-30T00:00:00Z")

        self.assertEqual(10000.0, state["initial_equity_usdt"])
        self.assertEqual(PAPER_ONLY_MODE, state["mode"])
        self.assertTrue(state["paper_only"])
        self.assertEqual(5, len(state["lots"]))
        self.assertEqual(11, len(state["orders"]))
        sndk = next(lot for lot in state["lots"] if lot["symbol"] == "SNDKUSDT")
        self.assertEqual(1125.0, sndk["entry_price"])
        self.assertEqual("EXOGENOUS_INITIAL_POSITION", sndk["origin"])
        self.assertEqual("EXOGENOUS", sndk["attribution"])
        self.assertIsNone(sndk["stop_price"])
        self.assertTrue(all(order["state"] == "REVIEW_REQUIRED" for order in state["orders"]))
        self.assertTrue(all(order["origin"] == "USER_INITIAL_PLAN" for order in state["orders"]))
        self.assertFalse(any(lot["symbol"] == "MUUSDT" for lot in state["lots"]))
        self.assertTrue(validate_portfolio_state(state)["valid"])
        json.dumps(state, allow_nan=False)

    def test_config_risk_policy_is_not_silently_ignored(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {"initial_cash_usdt": 10000, "positions": [], "orders": []},
                "risk_policy": {
                    "standard_thesis_risk_fraction": 0.005,
                    "per_instrument_open_pending_risk_fraction": 0.01,
                    "portfolio_open_pending_risk_fraction": 0.03,
                    "daily_realized_loss_fraction": 0.02,
                    "drawdown_no_new_risk_fraction": 0.05,
                    "gross_notional_equity_multiple": 1.5,
                    "minimum_reward_risk": 1.75,
                    "default_taker_fee_rate": 0.0006,
                    "default_maker_fee_rate": 0.0003,
                    "default_market_slippage_bps": 4,
                },
            },
            "2026-07-30T00:00:00Z",
        )
        limits = state["risk_limits"]
        self.assertEqual(0.005, limits["max_trade_risk_equity_fraction"])
        self.assertEqual(0.01, limits["max_symbol_open_risk_equity_fraction"])
        self.assertEqual(0.03, limits["max_portfolio_risk_equity_fraction"])
        self.assertEqual(0.02, limits["daily_realized_loss_fraction"])
        self.assertEqual(0.05, limits["max_drawdown_fraction"])
        self.assertEqual(1.5, limits["max_gross_leverage"])
        self.assertEqual(1.75, limits["minimum_reward_risk"])
        self.assertEqual(0.0006, limits["taker_fee_rate"])
        self.assertEqual(0.0003, limits["maker_fee_rate"])
        self.assertEqual(4.0, limits["market_slippage_bps"])

    def test_initial_order_requires_review_and_cannot_replay_pre_activation_bar(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [],
                    "orders": [
                        {"symbol": "BTCUSDT", "side": "BUY", "limit_price": 90, "notional_usdt": 100}
                    ],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        order_id = state["orders"][0]["order_id"]
        current = market("BTCUSDT", observed_at="2026-07-30T00:10:00Z", price=100)
        kept = submit_actions(
            state,
            [
                {
                    "type": "KEEP_ORDER",
                    "order_id": order_id,
                    "stop_price": 80,
                    "target_price": 110,
                    "hypothesis_id": "H-limit",
                    "risk_authorization": {"approved": True, "authority": "AGENT_DECISION"},
                }
            ],
            current,
            "2026-07-30T00:10:00Z",
        )
        self.assertEqual("ACCEPTED", kept["results"][0]["status"])

        pre_activation = market(
            "BTCUSDT",
            observed_at="2026-07-30T00:20:00Z",
            price=95,
            open_price=100,
            high=101,
            low=85,
            close_time_ms=1785369600000,
        )
        skipped = process_market_bars(state, pre_activation, "2026-07-30T00:20:00Z")
        self.assertEqual([], skipped["fills"])
        self.assertEqual("ACTIVE", state["orders"][0]["state"])

        future = market(
            "BTCUSDT",
            observed_at="2026-07-30T01:01:00Z",
            price=96,
            open_price=100,
            high=105,
            low=85,
            close_time_ms=1785373200000,
        )
        filled = process_market_bars(state, future, "2026-07-30T01:01:00Z")
        self.assertEqual(1, len(filled["fills"]))
        self.assertEqual(90.0, filled["fills"][0]["price"])
        self.assertEqual("FILLED", state["orders"][0]["state"])

    def test_new_strategy_risk_needs_authorization_hypothesis_stop_target_and_rr(self):
        state = initialize_portfolio(
            {"initial_portfolio": {"initial_cash_usdt": 10000, "positions": [], "orders": []}},
            "2026-07-30T00:00:00Z",
        )
        current = market("MUUSDT", observed_at="2026-07-30T00:05:00Z", price=100)
        missing = submit_actions(
            state,
            [{"type": "MARKET", "symbol": "MUUSDT", "side": "BUY", "notional_usdt": 100}],
            current,
        )
        self.assertEqual("RISK_REJECTED", missing["results"][0]["status"])
        self.assertIn("NEW_RISK_NOT_AUTHORIZED", missing["results"][0]["rejection_reasons"])
        self.assertIn("NEW_RISK_REQUIRES_STOP_AND_TARGET", missing["results"][0]["rejection_reasons"])

        weak_rr = submit_actions(
            state,
            [
                {
                    "type": "MARKET",
                    "symbol": "MUUSDT",
                    "side": "BUY",
                    "notional_usdt": 100,
                    "stop_price": 95,
                    "target_price": 104,
                    "hypothesis_id": "H-weak",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )
        self.assertIn(
            "MINIMUM_NET_REWARD_RISK_NOT_MET",
            weak_rr["results"][0]["rejection_reasons"],
        )

        accepted = submit_actions(
            state,
            [
                {
                    "type": "MARKET",
                    "symbol": "MUUSDT",
                    "side": "BUY",
                    "notional_usdt": 100,
                    "stop_price": 95,
                    "target_price": 110,
                    "hypothesis_id": "H-valid",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )
        self.assertEqual("FILLED", accepted["results"][0]["status"])
        self.assertEqual(1, accepted["strategy_fill_count"])
        self.assertGreater(state["fills"][-1]["price"], 100)
        self.assertGreater(state["fills"][-1]["fee_usdt"], 0)
        lot = next(lot for lot in state["lots"] if lot["status"] == "OPEN")
        self.assertGreater(
            lot["entry_reward_risk_gross"],
            lot["entry_reward_risk_net"],
        )
        self.assertEqual(
            state["risk_limits"]["taker_fee_rate"],
            lot["entry_cost_assumptions"]["entry_fee_rate"],
        )
        self.assertGreater(lot["initial_net_risk_usdt"], 0)

    def test_net_rr_rejects_a_gross_one_point_five_boundary_and_records_terms(self):
        state = initialize_portfolio(
            {"initial_portfolio": {"initial_cash_usdt": 10000, "positions": [], "orders": []}},
            "2026-07-30T00:00:00Z",
        )
        current = market("MUUSDT", observed_at="2026-07-30T00:05:00Z", price=100)
        boundary = submit_actions(
            state,
            [
                {
                    "type": "PLACE_LIMIT",
                    "symbol": "MUUSDT",
                    "side": "BUY",
                    "limit_price": 100,
                    "notional_usdt": 100,
                    "stop_price": 95,
                    "target_price": 107.5,
                    "hypothesis_id": "H-gross-boundary",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )
        self.assertEqual("REJECTED", boundary["results"][0]["status"])
        self.assertEqual(
            "MINIMUM_NET_REWARD_RISK_NOT_MET",
            boundary["results"][0]["reason"],
        )

        accepted = submit_actions(
            state,
            [
                {
                    "type": "PLACE_LIMIT",
                    "symbol": "MUUSDT",
                    "side": "BUY",
                    "limit_price": 100,
                    "notional_usdt": 100,
                    "stop_price": 95,
                    "target_price": 108,
                    "hypothesis_id": "H-net-pass",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )
        self.assertEqual("ACCEPTED", accepted["results"][0]["status"])
        order = state["orders"][0]
        terms = order["protection_terms"]
        self.assertEqual(1.6, terms["gross_reward_risk"])
        self.assertGreaterEqual(
            terms["net_reward_risk"],
            state["risk_limits"]["minimum_reward_risk"],
        )
        self.assertLess(terms["net_reward_risk"], terms["gross_reward_risk"])
        self.assertEqual(
            state["risk_limits"]["maker_fee_rate"],
            terms["assumptions"]["entry_fee_rate"],
        )

    def test_performance_tracks_excursions_costs_and_attribution(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 80,
                            "target_price": 130,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        observed = "2026-07-30T01:01:00Z"
        path = market(
            "BTCUSDT",
            observed_at=observed,
            price=105,
            open_price=100,
            high=110,
            low=95,
            close_time_ms=int(
                datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc).timestamp() * 1000
            ),
        )
        process_market_bars(state, path, observed)
        open_metrics = portfolio_metrics(state, {"BTCUSDT": 105})
        self.assertEqual(10.0, open_metrics["average_mfe_usdt"])
        self.assertEqual(5.0, open_metrics["average_mae_usdt"])

        closed = submit_actions(
            state,
            [
                {
                    "type": "CLOSE",
                    "symbol": "BTCUSDT",
                    "attribution": "STRATEGY_MANAGEMENT",
                }
            ],
            market("BTCUSDT", observed_at="2026-07-30T01:05:00Z", price=110),
        )
        self.assertEqual("FILLED", closed["results"][0]["status"])
        metrics = closed["metrics"]
        self.assertEqual(1, metrics["closed_trade_count"])
        self.assertEqual(1.0, metrics["win_rate"])
        self.assertGreater(metrics["average_r_multiple"], 0)
        self.assertEqual(3900.0, metrics["average_holding_seconds"])
        self.assertLess(
            metrics["net_realized_pnl_usdt"],
            metrics["gross_realized_pnl_usdt"],
        )
        self.assertEqual(
            metrics["average_r_multiple"],
            metrics["closed_trade_outcomes"][0]["r_multiple"],
        )
        self.assertGreater(metrics["attribution"]["STRATEGY_MANAGEMENT"]["fees_usdt"], 0)
        self.assertGreater(
            metrics["attribution"]["STRATEGY_MANAGEMENT"][
                "estimated_slippage_cost_usdt"
            ],
            0,
        )
        self.assertEqual("NOT_SIMULATED_V0_1", metrics["funding_accrual_status"])

    def test_opposite_trade_nets_fifo_and_blocks_unauthorized_excess(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 90,
                            "target_price": 120,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        current = market("BTCUSDT", observed_at="2026-07-30T01:00:00Z", price=100)
        first = submit_actions(
            state,
            [{"type": "MARKET", "symbol": "BTCUSDT", "side": "SELL", "notional_usdt": 200}],
            current,
        )["results"][0]
        self.assertEqual("PARTIALLY_FILLED_RISK_BLOCKED", first["status"])
        self.assertGreater(first["closed_quantity"], 0)
        self.assertEqual(0, first["opened_quantity"])
        self.assertIn("NEW_RISK_NOT_AUTHORIZED", first["rejection_reasons"])
        self.assertFalse(any(lot["status"] == "OPEN" for lot in state["lots"]))

        second = submit_actions(
            state,
            [
                {
                    "type": "MARKET",
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "notional_usdt": 100,
                    "stop_price": 105,
                    "target_price": 90,
                    "hypothesis_id": "H-short",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )["results"][0]
        self.assertEqual("FILLED", second["status"])
        self.assertEqual("SHORT", next(lot for lot in state["lots"] if lot["status"] == "OPEN")["side"])

    def test_same_bar_stop_and_target_uses_stop_first_and_marks_ambiguity(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "SOLUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 500,
                            "stop_price": 95,
                            "target_price": 110,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        both = market(
            "SOLUSDT",
            observed_at="2026-07-30T01:01:00Z",
            price=105,
            open_price=100,
            high=115,
            low=90,
            close_time_ms=1785373200000,
        )
        result = process_market_bars(state, both)
        fill = result["fills"][0]
        self.assertEqual("STOP", fill["reason"])
        self.assertTrue(fill["ambiguous_same_bar"])
        self.assertEqual("STOP_FIRST", fill["barrier_precedence"])
        self.assertLess(fill["price"], 95)
        self.assertFalse(any(lot["status"] == "OPEN" for lot in state["lots"]))

    def test_limit_entry_immediately_resolves_same_bar_stop_for_long_and_short(self):
        scenarios = (
            {
                "side": "BUY",
                "limit": 90,
                "stop": 80,
                "target": 110,
                "open": 100,
                "high": 115,
                "low": 75,
            },
            {
                "side": "SELL",
                "limit": 110,
                "stop": 120,
                "target": 90,
                "open": 100,
                "high": 125,
                "low": 85,
            },
        )
        for scenario in scenarios:
            with self.subTest(side=scenario["side"]):
                state = initialize_portfolio(
                    {
                        "initial_portfolio": {
                            "initial_cash_usdt": 10000,
                            "positions": [],
                            "orders": [],
                        }
                    },
                    "2026-07-30T00:00:00Z",
                )
                placed = submit_actions(
                    state,
                    [
                        {
                            "type": "PLACE_LIMIT",
                            "symbol": "BTCUSDT",
                            "side": scenario["side"],
                            "limit_price": scenario["limit"],
                            "notional_usdt": 100,
                            "stop_price": scenario["stop"],
                            "target_price": scenario["target"],
                            "hypothesis_id": f"H-{scenario['side'].lower()}",
                            "authorize_new_risk": True,
                        }
                    ],
                    market(
                        "BTCUSDT",
                        observed_at="2026-07-30T00:05:00Z",
                        price=100,
                    ),
                )
                self.assertEqual("ACCEPTED", placed["results"][0]["status"])
                result = process_market_bars(
                    state,
                    market(
                        "BTCUSDT",
                        observed_at="2026-07-30T01:01:00Z",
                        price=100,
                        open_price=scenario["open"],
                        high=scenario["high"],
                        low=scenario["low"],
                        close_time_ms=int(
                            datetime(
                                2026,
                                7,
                                30,
                                1,
                                0,
                                tzinfo=timezone.utc,
                            ).timestamp()
                            * 1000
                        ),
                    ),
                )
                self.assertEqual(["LIMIT", "STOP"], [fill["reason"] for fill in result["fills"]])
                protective = result["fills"][1]
                self.assertTrue(protective["same_bar_entry_and_exit"])
                self.assertTrue(protective["ambiguous_same_bar"])
                self.assertEqual("STOP_FIRST", protective["barrier_precedence"])
                self.assertEqual("FILLED", state["orders"][0]["state"])
                self.assertFalse(any(lot["status"] == "OPEN" for lot in state["lots"]))
                self.assertTrue(validate_portfolio_state(state)["valid"])

    def test_open_risk_uses_mark_to_slipped_stop_and_cost_aware_cap(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 90,
                            "target_price": 120,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        metrics = portfolio_metrics(state, {"BTCUSDT": 110})
        self.assertAlmostEqual(20.0719865, metrics["open_risk_usdt"], places=6)
        self.assertAlmostEqual(10.0719865, metrics["open_cost_to_stop_usdt"], places=6)
        self.assertEqual(
            metrics["open_risk_usdt"],
            metrics["open_symbol_risk_usdt"]["BTCUSDT"],
        )

        capped = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [],
                    "orders": [],
                },
                "risk_limits": {
                    "max_trade_risk_equity_fraction": 0.001005,
                },
            },
            "2026-07-30T00:00:00Z",
        )
        rejected = submit_actions(
            capped,
            [
                {
                    "type": "PLACE_LIMIT",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "limit_price": 100,
                    "notional_usdt": 100,
                    "stop_price": 90,
                    "target_price": 120,
                    "hypothesis_id": "H-cost-cap",
                    "authorize_new_risk": True,
                }
            ],
            market("BTCUSDT", observed_at="2026-07-30T00:05:00Z", price=100),
        )
        self.assertEqual("REJECTED", rejected["results"][0]["status"])
        self.assertIn("MAX_TRADE_RISK", rejected["results"][0]["reason"])

    def test_stop_is_monotonic_and_batch_can_protect_then_add_risk(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {"symbol": "ETHUSDT", "side": "LONG", "entry_price": 100, "notional_usdt": 500}
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        current = market("ETHUSDT", observed_at="2026-07-30T00:10:00Z", price=100)
        report = submit_actions(
            state,
            [
                {"type": "UPDATE_PROTECTION", "symbol": "ETHUSDT", "stop_price": 90, "target_price": 120},
                {
                    "type": "MARKET",
                    "symbol": "ETHUSDT",
                    "side": "BUY",
                    "notional_usdt": 100,
                    "stop_price": 95,
                    "target_price": 110,
                    "hypothesis_id": "H-add",
                    "authorize_new_risk": True,
                },
            ],
            current,
        )
        self.assertEqual(["ACCEPTED", "FILLED"], [row["status"] for row in report["results"]])
        tightened = submit_actions(
            state,
            [{"type": "UPDATE_PROTECTION", "symbol": "ETHUSDT", "stop_price": 96, "target_price": 120}],
            current,
        )
        self.assertEqual("ACCEPTED", tightened["results"][0]["status"])
        widened = submit_actions(
            state,
            [{"type": "UPDATE_PROTECTION", "symbol": "ETHUSDT", "stop_price": 95, "target_price": 120}],
            current,
        )
        self.assertEqual("REJECTED", widened["results"][0]["status"])
        self.assertEqual("LONG_STOP_CANNOT_WIDEN", widened["results"][0]["reason"])
        adverse_target = submit_actions(
            state,
            [{"type": "UPDATE_PROTECTION", "symbol": "ETHUSDT", "stop_price": 96, "target_price": 119}],
            current,
        )
        self.assertEqual("REJECTED", adverse_target["results"][0]["status"])
        self.assertEqual(
            "LONG_TARGET_CANNOT_MOVE_ADVERSE",
            adverse_target["results"][0]["reason"],
        )
        late = submit_actions(
            state,
            [{"type": "UPDATE_PROTECTION", "symbol": "ETHUSDT", "stop_price": 96, "target_price": 120}],
            market("ETHUSDT", observed_at="2026-07-30T01:00:00Z", price=115),
        )
        self.assertEqual("REJECTED", late["results"][0]["status"])
        self.assertEqual(
            "UPDATED_PROTECTION_MINIMUM_NET_RR_NOT_MET",
            late["results"][0]["reason"],
        )

    def test_net_performance_counts_only_full_trades_and_tracks_r_and_holding_time(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 90,
                            "target_price": 120,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        first = submit_actions(
            state,
            [
                {
                    "type": "CLOSE",
                    "symbol": "BTCUSDT",
                    "notional_usdt": 50,
                }
            ],
            market("BTCUSDT", observed_at="2026-07-30T01:00:00Z", price=110),
        )
        self.assertEqual("FILLED", first["results"][0]["status"])
        self.assertEqual(0, first["metrics"]["closed_trade_count"])
        self.assertEqual(1, first["metrics"]["exit_slice_count"])
        self.assertEqual("OPEN", state["lots"][0]["status"])

        second = submit_actions(
            state,
            [{"type": "CLOSE", "symbol": "BTCUSDT"}],
            market("BTCUSDT", observed_at="2026-07-30T02:00:00Z", price=111),
        )
        metrics = second["metrics"]
        self.assertEqual(1, metrics["closed_trade_count"])
        self.assertEqual(2, metrics["exit_slice_count"])
        self.assertEqual(7200.0, metrics["average_holding_seconds"])
        self.assertGreater(metrics["average_r_multiple"], 0)

        fee_loser = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "ETHUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 90,
                            "target_price": 120,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        closed = submit_actions(
            fee_loser,
            [{"type": "CLOSE", "symbol": "ETHUSDT"}],
            market("ETHUSDT", observed_at="2026-07-30T01:00:00Z", price=100.04),
        )
        fee_metrics = closed["metrics"]
        self.assertGreater(fee_metrics["gross_realized_pnl_usdt"], 0)
        self.assertLess(fee_metrics["net_realized_pnl_usdt"], 0)
        self.assertEqual(0, fee_metrics["winning_trade_count"])
        self.assertEqual(1, fee_metrics["losing_trade_count"])
        self.assertEqual(0.0, fee_metrics["win_rate"])
        self.assertEqual(0.0, fee_metrics["profit_factor"])
        self.assertLess(fee_metrics["average_r_multiple"], 0)
        self.assertEqual(3600.0, fee_metrics["average_holding_seconds"])

    def test_validator_rejects_id_reference_status_and_accounting_tampering(self):
        open_state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        opposite = copy.deepcopy(open_state)
        second_lot = copy.deepcopy(opposite["lots"][0])
        second_lot["lot_id"] = "lot-000002"
        second_lot["side"] = "SHORT"
        opposite["lots"].append(second_lot)
        opposite["counters"]["lot"] = 2

        zero_open = copy.deepcopy(open_state)
        zero_open["lots"][0]["quantity"] = 0.0

        duplicate = copy.deepcopy(open_state)
        duplicate["lots"].append(copy.deepcopy(duplicate["lots"][0]))

        for name, candidate in (
            ("opposite-open-side", opposite),
            ("zero-open-quantity", zero_open),
            ("duplicate-lot-id", duplicate),
        ):
            with self.subTest(case=name):
                with self.assertRaises(TheoryPaperError):
                    validate_portfolio_state(candidate)

        closed_state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "ETHUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 100,
                            "stop_price": 90,
                            "target_price": 120,
                        }
                    ],
                    "orders": [],
                }
            },
            "2026-07-30T00:00:00Z",
        )
        submit_actions(
            closed_state,
            [{"type": "CLOSE", "symbol": "ETHUSDT"}],
            market("ETHUSDT", observed_at="2026-07-30T01:00:00Z", price=110),
        )
        tampered: list[tuple[str, dict]] = []
        cash = copy.deepcopy(closed_state)
        cash["cash_balance_usdt"] += 1
        tampered.append(("cash", cash))
        gross = copy.deepcopy(closed_state)
        gross["realized_pnl_usdt"] += 1
        tampered.append(("realized", gross))
        fees = copy.deepcopy(closed_state)
        fees["fees_paid_usdt"] += 1
        tampered.append(("fees", fees))
        order_ref = copy.deepcopy(closed_state)
        order_ref["fills"][0]["order_id"] = "order-999999"
        tampered.append(("unknown-order-reference", order_ref))
        lot_ref = copy.deepcopy(closed_state)
        lot_ref["fills"][0]["closed_lots"][0]["lot_id"] = "lot-999999"
        tampered.append(("unknown-lot-reference", lot_ref))
        for name, candidate in tampered:
            with self.subTest(case=name):
                with self.assertRaises(TheoryPaperError):
                    validate_portfolio_state(candidate)

    def test_absolute_caps_and_daily_realized_loss_block_new_risk(self):
        state = initialize_portfolio(
            {
                "initial_portfolio": {
                    "initial_cash_usdt": 10000,
                    "positions": [
                        {
                            "symbol": "HYPEUSDT",
                            "side": "LONG",
                            "entry_price": 100,
                            "notional_usdt": 1000,
                            "stop_price": 80,
                            "target_price": 140,
                        }
                    ],
                    "orders": [],
                },
                "risk_limits": {
                    "max_gross_leverage": 0.12,
                    "max_symbol_equity_fraction": 0.2,
                    "max_trade_risk_equity_fraction": 0.1,
                    "max_portfolio_risk_equity_fraction": 0.1,
                    "max_symbol_open_risk_equity_fraction": 0.1,
                    "daily_realized_loss_fraction": 0.02,
                    "max_drawdown_fraction": 0.02,
                },
            },
            "2026-07-30T00:00:00Z",
        )
        current = market("HYPEUSDT", observed_at="2026-07-30T01:00:00Z", price=70)
        closed = submit_actions(state, [{"type": "CLOSE", "symbol": "HYPEUSDT"}], current)
        self.assertEqual("FILLED", closed["results"][0]["status"])
        self.assertIn("DAILY_REALIZED_LOSS_LIMIT", state["risk_state"]["reasons"])
        attempt = submit_actions(
            state,
            [
                {
                    "type": "MARKET",
                    "symbol": "HYPEUSDT",
                    "side": "BUY",
                    "notional_usdt": 500,
                    "stop_price": 65,
                    "target_price": 80,
                    "hypothesis_id": "H-after-loss",
                    "authorize_new_risk": True,
                }
            ],
            current,
        )
        self.assertIn("DAILY_REALIZED_LOSS_LIMIT", state["risk_state"]["reasons"])
        self.assertIn("DAILY_REALIZED_LOSS_LIMIT", attempt["results"][0]["rejection_reasons"])
        self.assertIn("MAX_DRAWDOWN_REACHED", attempt["results"][0]["rejection_reasons"])

    def test_auto_and_manual_chaos_are_deterministic_and_separately_attributed(self):
        activated = datetime(2026, 7, 30, tzinfo=timezone.utc)
        first = deterministic_chaos_schedule(
            activated_at=activated,
            symbols=["BTCUSDT", "ETHUSDT"],
            seed="sealed-seed",
            hour_offsets=[1],
            notionals_usdt=[100],
        )
        second = deterministic_chaos_schedule(
            activated_at=activated,
            symbols=["ETHUSDT", "BTCUSDT"],
            seed="sealed-seed",
            hour_offsets=[1],
            notionals_usdt=[100],
        )
        self.assertEqual(first, second)
        event = first[0]
        state = initialize_portfolio(
            {
                "initial_portfolio": {"initial_cash_usdt": 10000, "positions": [], "orders": []},
                "chaos_schedule": first,
            },
            "2026-07-30T00:00:00Z",
        )
        current = market(event["symbol"], observed_at="2026-07-30T01:01:00Z", price=100)
        auto = inject_due_chaos(state, current)
        self.assertEqual("FILLED", auto["results"][0]["status"])
        self.assertEqual("CHAOS_AUTO", state["fills"][-1]["attribution"])
        self.assertEqual([], inject_due_chaos(state, current)["results"])

        manual = inject_manual_chaos(
            state,
            current,
            symbol=event["symbol"],
            side=event["side"],
            notional_usdt=100,
            note="manual emotion",
        )
        self.assertEqual("FILLED", manual["status"])
        self.assertEqual("CHAOS_MANUAL", state["fills"][-1]["attribution"])
        self.assertNotEqual("STRATEGY", state["fills"][-1]["attribution"])
        self.assertGreater(portfolio_metrics(state, {event["symbol"]: 100})["gross_notional_usdt"], 0)


if __name__ == "__main__":
    unittest.main()
