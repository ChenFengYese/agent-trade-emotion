import unittest
from datetime import timedelta
from decimal import Decimal

from trade_system.order_book import OrderBook
from trade_system.paper import PaperBroker
from trade_system.instrument_rules import BinanceInstrumentRules
from trade_system.risk import OrderManager, RiskEngine, RiskLimits
from trade_system.types import OrderIntent, OrderStatus, PositionStage, Side, SystemHealth, utc_now


class RiskAndPaperTests(unittest.TestCase):
    def setUp(self):
        self.risk = RiskEngine(
            RiskLimits(
                max_episode_loss=Decimal("100"),
                max_total_notional=Decimal("1000"),
                max_single_order_quantity=Decimal("5"),
                tail_cost_per_unit=Decimal("1"),
                max_unprotected_duration=timedelta(milliseconds=1),
            )
        )
        self.risk.set_health(SystemHealth.READY)
        self.manager = OrderManager(self.risk)
        self.intent = OrderIntent(
            intent_id="intent-1",
            episode_id="episode-1",
            side=Side.BUY,
            stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("2"),
            limit_price=Decimal("101"),
            stop_price=Decimal("98"),
            created_at=utc_now(),
            model_version="v1",
            policy_version="p1",
        )

    def test_idempotent_intent_and_partial_fill_requires_protection(self):
        first = self.manager.submit_intent(self.intent)
        self.assertIs(first, self.manager.submit_intent(self.intent))
        book = OrderBook()
        book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "1"]])
        fills = PaperBroker(Decimal("0")).execute_ioc(self.manager, self.intent.intent_id, book, utc_now())
        self.assertEqual(Decimal("1"), fills[0].quantity)
        self.assertFalse(self.manager.verify_protection(utc_now()))
        self.manager.confirm_protection(self.intent.intent_id, Decimal("1"), utc_now())
        self.assertTrue(self.manager.verify_protection(utc_now()))
        self.assertTrue(self.manager.reconcile_position(Decimal("1"), utc_now()))

    def test_unprotected_position_halts_after_approved_window(self):
        self.manager.submit_intent(self.intent)
        book = OrderBook()
        book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "2"]])
        PaperBroker(Decimal("0")).execute_ioc(self.manager, self.intent.intent_id, book, utc_now())
        self.assertFalse(self.manager.verify_protection(utc_now() + timedelta(seconds=1)))
        self.assertIn("UNPROTECTED_POSITION", self.manager.halt_reasons)

    def test_paper_oms_rejects_intent_that_violates_captured_tick_or_lot_rules(self):
        rules = BinanceInstrumentRules.from_exchange_info("metadata-1", {
            "kind": "exchange_info", "symbol": "BTCUSDT", "status": "TRADING",
            "filters": [
                {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.5"},
                {"filterType": "LOT_SIZE", "minQty": "0.1", "maxQty": "10", "stepSize": "0.1"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        })
        manager = OrderManager(self.risk, instrument_rules=rules)
        invalid = OrderIntent(
            intent_id="invalid-tick", episode_id="episode-1", side=Side.BUY, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("0.15"), limit_price=Decimal("101.1"), stop_price=Decimal("98"), created_at=utc_now(), model_version="v1", policy_version="p1",
        )
        rejected = manager.submit_intent(invalid)
        self.assertEqual(OrderStatus.RISK_REJECTED, rejected.status)
        self.assertIn("QUANTITY_STEP_FILTER", rejected.rejection_reason)
        self.assertIn("PRICE_TICK_FILTER", rejected.rejection_reason)
        valid = OrderIntent(
            intent_id="valid-rules", episode_id="episode-1", side=Side.BUY, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("0.2"), limit_price=Decimal("101.0"), stop_price=Decimal("98"), created_at=utc_now(), model_version="v1", policy_version="p1",
        )
        self.assertEqual(OrderStatus.ACKNOWLEDGED, manager.submit_intent(valid).status)

    def test_account_reconciliation_halts_on_foreign_or_missing_order(self):
        order = self.manager.submit_intent(self.intent)
        matched = self.manager.reconcile_account(
            exchange_position_quantity=Decimal("0"),
            observed_open_client_order_ids={order.client_order_id},
            now=utc_now(),
        )
        self.assertTrue(matched.matched)

        foreign = self.manager.reconcile_account(
            exchange_position_quantity=Decimal("0"),
            observed_open_client_order_ids={order.client_order_id, "manual-order"},
            now=utc_now(),
        )
        self.assertFalse(foreign.matched)
        self.assertIn("FOREIGN_ORDER", foreign.reasons)
        self.assertIn("FOREIGN_ORDER", self.manager.halt_reasons)

    def test_account_reconciliation_marks_missing_order_unknown(self):
        order = self.manager.submit_intent(self.intent)
        result = self.manager.reconcile_account(
            exchange_position_quantity=Decimal("0"),
            observed_open_client_order_ids=set(),
            now=utc_now(),
        )
        self.assertFalse(result.matched)
        self.assertIn("UNKNOWN_ORDER", result.reasons)
        self.assertEqual(OrderStatus.UNKNOWN, order.status)

    def test_confirmed_add_is_rejected_until_existing_position_is_protected(self):
        risk = RiskEngine(RiskLimits(
            max_episode_loss=Decimal("100"), max_total_notional=Decimal("1000"),
            max_single_order_quantity=Decimal("5"), tail_cost_per_unit=Decimal("1"),
            max_unprotected_duration=timedelta(seconds=10),
        ))
        risk.set_health(SystemHealth.READY)
        manager = OrderManager(risk)
        manager.submit_intent(self.intent)
        book = OrderBook()
        book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "1"]])
        PaperBroker(Decimal("0")).execute_ioc(manager, self.intent.intent_id, book, utc_now())
        add = OrderIntent(
            intent_id="add-1", episode_id="episode-1", side=Side.BUY, stage=PositionStage.ADD_POSITION_CONFIRMED,
            quantity=Decimal("1"), limit_price=Decimal("101"), stop_price=Decimal("98"), created_at=utc_now(), model_version="v1", policy_version="p1",
        )
        rejected = manager.submit_intent(add)
        self.assertEqual(OrderStatus.RISK_REJECTED, rejected.status)
        self.assertEqual("PROTECTION_NOT_CONFIRMED", rejected.rejection_reason)
        manager.confirm_protection(self.intent.intent_id, Decimal("1"), utc_now())
        allowed = manager.submit_intent(OrderIntent(
            intent_id="add-2", episode_id="episode-1", side=Side.BUY, stage=PositionStage.ADD_POSITION_CONFIRMED,
            quantity=Decimal("1"), limit_price=Decimal("101"), stop_price=Decimal("98"), created_at=utc_now(), model_version="v1", policy_version="p1",
        ))
        self.assertEqual(OrderStatus.ACKNOWLEDGED, allowed.status)

    def test_halt_cancels_pending_entry_intents(self):
        order = self.manager.submit_intent(self.intent)
        self.assertEqual(OrderStatus.ACKNOWLEDGED, order.status)
        self.manager.halt("DATA_EXECUTION_HALT")
        self.assertEqual(OrderStatus.CANCELED, order.status)
        self.assertEqual(OrderStatus.CANCELED, order.status_history[-1])

    def test_reduce_only_exit_flattens_position_while_entry_gate_is_halted(self):
        self.manager.submit_intent(self.intent)
        entry_book = OrderBook()
        entry_book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "2"]])
        PaperBroker(Decimal("0")).execute_ioc(self.manager, self.intent.intent_id, entry_book, utc_now())
        self.manager.confirm_protection(self.intent.intent_id, Decimal("2"), utc_now())
        self.manager.halt("DATA_EXECUTION_HALT")

        exit_intent = OrderIntent(
            intent_id="exit-1", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("2"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        )
        exit_order = self.manager.submit_intent(exit_intent)
        self.assertEqual(OrderStatus.ACKNOWLEDGED, exit_order.status)
        exit_book = OrderBook()
        exit_book.reset_snapshot(last_update_id=2, bids=[["99", "2"]], asks=[["101", "4"]])
        PaperBroker(Decimal("0")).execute_ioc(self.manager, exit_intent.intent_id, exit_book, utc_now())

        self.assertEqual(OrderStatus.FILLED, exit_order.status)
        self.assertNotIn(OrderStatus.PROTECTION_REQUIRED, exit_order.status_history)
        self.assertEqual(Decimal("0"), self.manager.position_quantity)
        self.assertEqual(Decimal("0"), self.manager.risk.current_notional)
        self.assertEqual(Decimal("0"), self.manager.effective_protected_quantity)
        self.assertEqual(Decimal("-4"), self.manager.realized_pnl)
        self.assertTrue(self.manager.reconcile_position(Decimal("0"), utc_now()))

    def test_partial_reduce_only_exit_shrinks_protection_and_rejects_risk_increasing_exit_forms(self):
        self.manager.submit_intent(self.intent)
        entry_book = OrderBook()
        entry_book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "2"]])
        PaperBroker(Decimal("0")).execute_ioc(self.manager, self.intent.intent_id, entry_book, utc_now())
        self.manager.confirm_protection(self.intent.intent_id, Decimal("2"), utc_now())

        wrong_side = self.manager.submit_intent(OrderIntent(
            intent_id="bad-exit-side", episode_id="episode-1", side=Side.BUY, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("1"), limit_price=Decimal("101"), stop_price=Decimal("98"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        ))
        self.assertEqual("REDUCE_ONLY_SIDE_MISMATCH", wrong_side.rejection_reason)
        wrong_size = self.manager.submit_intent(OrderIntent(
            intent_id="bad-exit-size", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("3"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        ))
        self.assertEqual("REDUCE_ONLY_QUANTITY_EXCEEDS_POSITION", wrong_size.rejection_reason)
        zero_quantity = self.manager.submit_intent(OrderIntent(
            intent_id="bad-exit-zero", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("0"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        ))
        self.assertEqual("ORDER_QUANTITY_LIMIT", zero_quantity.rejection_reason)
        opposite_entry = self.manager.submit_intent(OrderIntent(
            intent_id="bad-opposite-entry", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("1"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1",
        ))
        self.assertEqual("OPPOSITE_SIDE_REQUIRES_REDUCE_ONLY", opposite_entry.rejection_reason)

        exit_intent = OrderIntent(
            intent_id="partial-exit", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("2"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        )
        self.manager.submit_intent(exit_intent)
        exit_book = OrderBook()
        exit_book.reset_snapshot(last_update_id=2, bids=[["99", "1"]], asks=[["101", "4"]])
        PaperBroker(Decimal("0")).execute_ioc(self.manager, exit_intent.intent_id, exit_book, utc_now())

        self.assertEqual(OrderStatus.CANCELED, self.manager.orders_by_intent[exit_intent.intent_id].status)
        self.assertEqual(Decimal("1"), self.manager.position_quantity)
        self.assertEqual(Decimal("101"), self.manager.risk.current_notional)
        self.assertEqual(Decimal("1"), self.manager.effective_protected_quantity)
        self.assertEqual(Decimal("-2"), self.manager.realized_pnl)
        self.assertTrue(self.manager.verify_protection(utc_now()))

    def test_realized_daily_loss_limit_halts_after_exit_and_blocks_new_risk(self):
        risk = RiskEngine(RiskLimits(
            max_episode_loss=Decimal("100"), max_total_notional=Decimal("1000"),
            max_single_order_quantity=Decimal("5"), tail_cost_per_unit=Decimal("1"),
            max_unprotected_duration=timedelta(seconds=10), max_daily_realized_loss=Decimal("3"),
        ))
        risk.set_health(SystemHealth.READY)
        manager = OrderManager(risk)
        manager.submit_intent(self.intent)
        entry_book = OrderBook()
        entry_book.reset_snapshot(last_update_id=1, bids=[["99", "4"]], asks=[["101", "2"]])
        PaperBroker(Decimal("0")).execute_ioc(manager, self.intent.intent_id, entry_book, utc_now())
        manager.confirm_protection(self.intent.intent_id, Decimal("2"), utc_now())
        exit_intent = OrderIntent(
            intent_id="loss-exit", episode_id="episode-1", side=Side.SELL, stage=PositionStage.ENTER_PROBE,
            quantity=Decimal("2"), limit_price=Decimal("99"), stop_price=Decimal("102"), created_at=utc_now(),
            model_version="v1", policy_version="p1", reduce_only=True,
        )
        manager.submit_intent(exit_intent)
        exit_book = OrderBook()
        exit_book.reset_snapshot(last_update_id=2, bids=[["99", "2"]], asks=[["101", "4"]])
        PaperBroker(Decimal("0")).execute_ioc(manager, exit_intent.intent_id, exit_book, utc_now())
        self.assertIn("DAILY_REALIZED_LOSS_LIMIT", manager.halt_reasons)
        self.assertEqual(SystemHealth.HALTED, risk.system_health)
        self.assertEqual(Decimal("-4"), risk.daily_realized_pnl[utc_now().date().isoformat()])

    def test_realized_drawdown_limit_is_explicit_and_uses_no_unrealized_pnl(self):
        risk = RiskEngine(RiskLimits(
            max_episode_loss=Decimal("100"), max_total_notional=Decimal("1000"),
            max_single_order_quantity=Decimal("5"), tail_cost_per_unit=Decimal("1"),
            max_unprotected_duration=timedelta(seconds=10), max_session_realized_drawdown=Decimal("3"),
        ))
        now = utc_now()
        self.assertEqual((), risk.record_realized_pnl(Decimal("5"), now))
        self.assertEqual(("MAX_REALIZED_DRAWDOWN_LIMIT",), risk.record_realized_pnl(Decimal("-4"), now))
        self.assertEqual(Decimal("4"), risk.session_realized_drawdown)
        self.assertEqual(Decimal("1"), risk.session_realized_pnl)
