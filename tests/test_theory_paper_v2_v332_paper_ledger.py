from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingError,
    PaperTradingService,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    CarryAccrualV1,
    FundingCoverageAdvanceV1,
    FundingSettlementModelV1,
    InstrumentSpecV1,
    OrderTruthV1,
    PaperCommandV1,
    PaperContractError,
    PaperCostModelV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
    PaperLedgerError,
)


ZERO_SHA = "0" * 64
ONE_SHA = "1" * 64


class _DecisionAuthority:
    def __init__(self) -> None:
        self.generations = {"hype-trader": 1, "contract-agent": 1}
        self.decisions = {ONE_SHA}

    def current_generation(self, logical_agent_id: str) -> int | None:
        return self.generations.get(logical_agent_id)

    def verifies_decision(self, command: PaperCommandV1) -> bool:
        return command.decision_sha256 in self.decisions


class _MarketEvidence:
    def __init__(self) -> None:
        self.sources = {ZERO_SHA, ONE_SHA, "2" * 64}

    def verifies_market_slice(self, market: PaperMarketSliceV1) -> bool:
        return market.source_sha256 in self.sources

    def verifies_instrument_spec(
        self,
        spec: InstrumentSpecV1,
        *,
        available_by: str,
    ) -> bool:
        del available_by
        return (
            spec.parameter_status == "OBSERVED_RAW_BOUND"
            and spec.parameter_source_sha256 in self.sources
        )


class _CarryEvidence:
    def __init__(self) -> None:
        self.allowed = {ONE_SHA}

    def verifies_carry_accrual(self, accrual: CarryAccrualV1) -> bool:
        return (
            accrual.rate_source_sha256 in self.allowed
            and accrual.price_source_sha256 in self.allowed
        )

    def verifies_funding_coverage(
        self, advance: FundingCoverageAdvanceV1
    ) -> bool:
        return isinstance(advance, FundingCoverageAdvanceV1)


def _instrument_spec(
    *,
    instrument_spec_id: str = "hype-test-contract-v1",
    multiplier: str = "1",
    source_sha256: str = ZERO_SHA,
) -> InstrumentSpecV1:
    return InstrumentSpecV1(
        instrument_spec_id=instrument_spec_id,
        symbol="HYPE-USDT-SWAP",
        account_mode="LINEAR_PERP",
        quote_currency="USDT",
        contract_multiplier=multiplier,
        quantity_basis="CONTRACTS",
        parameter_status="OBSERVED_RAW_BOUND",
        parameter_source_sha256=source_sha256,
    )


class V332PaperLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.model = PaperCostModelV1(
            model_id="public-stress-v1",
            maker_fee_bps="1",
            taker_fee_bps="2",
            market_impact_bps="1",
            funding_status="UNKNOWN",
            borrow_status="UNKNOWN",
        )
        self.ledger = FilePaperLedger(self.root)
        self.authority = _DecisionAuthority()
        self.authority.generations["loss-agent"] = 1
        self.market_evidence = _MarketEvidence()
        self.service = PaperTradingService(
            self.ledger,
            cost_models=(self.model,),
            decision_authority=self.authority,
            market_evidence=self.market_evidence,
            carry_evidence=_CarryEvidence(),
        )
        self.service.open_account(
            account_id="hype-paper",
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="hype-trader",
            base_currency="USDT",
            permitted_symbol="HYPE-USDT-SWAP",
            max_leverage="5",
            initial_balance="10000",
            opened_at="2026-08-12T12:00:00+00:00",
            instrument_spec=_instrument_spec(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _command(
        self,
        *,
        command_id: str,
        version: int,
        command_type: str = "MARKET",
        side: str | None = "BUY",
        quantity: str | None = "2",
        limit_price: str | None = None,
        trigger_price: str | None = None,
        target_order_id: str | None = None,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
        agent_generation: int = 1,
        submitted_at: str = "2026-08-12T12:01:00+00:00",
        expires_at: str | None = None,
    ) -> PaperCommandV1:
        return PaperCommandV1(
            command_id=command_id,
            account_id="hype-paper",
            logical_agent_id="hype-trader",
            agent_generation=agent_generation,
            decision_cycle_id="hype-decision-cycle-001",
            decision_sha256=ONE_SHA,
            expected_account_version=version,
            symbol="HYPE-USDT-SWAP",
            command_type=command_type,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            trigger_price=trigger_price,
            target_order_id=target_order_id,
            reduce_only=reduce_only,
            time_in_force=time_in_force,
            submitted_at=submitted_at,
            expires_at=expires_at,
            cost_model_id=self.model.model_id,
        )

    @staticmethod
    def _quote(
        *,
        observed_at: str,
        bid: str,
        ask: str,
        quantity: str | None = "10",
        source: str = ZERO_SHA,
        available_at: str | None = None,
    ) -> PaperMarketSliceV1:
        return PaperMarketSliceV1(
            symbol="HYPE-USDT-SWAP",
            observed_at=observed_at,
            available_at=available_at or observed_at,
            source_sha256=source,
            granularity="QUOTE",
            path_status="ORDERED",
            bid=bid,
            ask=ask,
            available_quantity=quantity,
        )

    def test_market_fill_is_replayable_idempotent_and_cost_explicit(self) -> None:
        command = self._command(command_id="open-long", version=1)
        submitted = self.service.submit(command)
        self.assertEqual(submitted.version, 3)
        filled = self.service.observe(
            account_id="hype-paper",
            expected_account_version=3,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        self.assertEqual(filled.version, 5)
        self.assertEqual(filled.positions[0].quantity, "2")
        self.assertEqual(filled.positions[0].average_entry_price, "100.01")
        self.assertEqual(filled.orders[0].state, "FILLED")
        self.assertLess(float(filled.cash_balance), 10000.0)
        self.assertGreater(float(filled.reserved_margin), 0.0)
        self.assertEqual(
            Decimal(filled.available_balance),
            Decimal(filled.cash_balance) - Decimal(filled.reserved_margin),
        )

        duplicate = self.service.submit(command)
        self.assertEqual(duplicate.version, 5)
        restarted = PaperTradingService(
            FilePaperLedger(self.root), cost_models=(self.model,)
        ).load_account("hype-paper")
        self.assertEqual(restarted.to_dict(), filled.to_dict())
        fill_payload = self.ledger.load_records("hype-paper")[-1].payload["fill"]
        self.assertEqual(fill_payload["funding_cost_status"], "UNKNOWN")
        self.assertIsNone(fill_payload["funding_cost"])
        self.assertEqual(fill_payload["borrow_cost_status"], "NOT_APPLICABLE")
        self.assertIsNone(fill_payload["borrow_cost"])

    def test_cycle_bound_command_round_trips_and_legacy_replay_fails_closed(self) -> None:
        command = self._command(command_id="cycle-bound-command", version=1)
        serialized = command.to_dict()

        self.assertEqual("1.1.0", serialized["schema_version"])
        self.assertEqual("hype-decision-cycle-001", serialized["decision_cycle_id"])
        self.assertEqual(command, PaperCommandV1.from_dict(serialized))

        legacy_command = dict(serialized)
        legacy_command["schema_version"] = "1.0.0"
        legacy_command.pop("decision_cycle_id")
        with self.assertRaisesRegex(PaperContractError, "paper command fields mismatch"):
            PaperCommandV1.from_dict(legacy_command)

        legacy_command["account_id"] = "legacy-paper"
        digest_payload = {
            "schema_id": "agent-trade-emotion.paper-ledger-record",
            "schema_version": "1.0.0",
            "account_id": "legacy-paper",
            "revision": 1,
            "previous_record_sha256": None,
            "event_id": "legacy-command-event",
            "event_type": "COMMAND_ACCEPTED",
            "occurred_at": legacy_command["submitted_at"],
            "payload": {"command": legacy_command},
        }
        serialized_record = {
            **digest_payload,
            "record_sha256": canonical_digest(digest_payload),
        }
        legacy_ledger = FilePaperLedger(self.root / "legacy-ledger")
        events_path = (
            legacy_ledger.root / "accounts" / "legacy-paper" / "events.jsonl"
        )
        events_path.parent.mkdir(parents=True)
        events_path.write_bytes(canonical_bytes(serialized_record) + b"\n")

        with self.assertRaisesRegex(
            PaperLedgerError,
            "PAPER_LEDGER_RECORD_INVALID:1",
        ):
            legacy_ledger.load_records("legacy-paper")

    def test_version_and_agent_account_isolation_fail_closed(self) -> None:
        with self.assertRaisesRegex(PaperTradingError, "PAPER_ACCOUNT_VERSION_CONFLICT"):
            self.service.submit(self._command(command_id="stale", version=0))
        foreign = self._command(command_id="foreign", version=1)
        foreign = PaperCommandV1(**{
            **{key: value for key, value in foreign.to_dict().items() if key not in {"schema_id", "schema_version"}},
            "logical_agent_id": "sndk-trader",
        })
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_AGENT_ACCOUNT_OWNERSHIP_MISMATCH"
        ):
            self.service.submit(foreign)
        self.assertEqual(self.service.load_account("hype-paper").version, 1)

    def test_limit_partial_fill_then_cancel_records_exact_history(self) -> None:
        limit = self._command(
            command_id="limit-buy",
            version=1,
            command_type="LIMIT",
            limit_price="95",
        )
        state = self.service.submit(limit)
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="94.8",
                ask="94.9",
                quantity="1",
            ),
        )
        self.assertEqual(state.orders[0].state, "PARTIALLY_FILLED")
        self.assertEqual(state.orders[0].remaining_quantity, "1")
        cancel = self._command(
            command_id="cancel-limit",
            version=state.version,
            command_type="CANCEL",
            side=None,
            quantity=None,
            target_order_id="limit-buy",
            submitted_at="2026-08-12T12:01:02+00:00",
        )
        cancelled = self.service.submit(cancel)
        self.assertEqual(cancelled.orders[0].state, "CANCELLED")
        self.assertEqual(cancelled.positions[0].quantity, "1")

    def test_reduce_only_rejects_absent_or_oversized_position(self) -> None:
        reduce = self._command(
            command_id="reduce-empty",
            version=1,
            command_type="REDUCE",
            side="SELL",
            quantity="1",
            reduce_only=True,
        )
        state = self.service.submit(reduce)
        self.assertEqual(state.orders[0].state, "REJECTED")
        self.assertEqual(state.orders[0].resolution_reason, "REDUCE_ONLY_WITHOUT_POSITION")

    def test_reduce_fill_releases_margin_and_records_realized_pnl(self) -> None:
        state = self.service.submit(self._command(command_id="open", version=1))
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        reduce = self._command(
            command_id="take-one",
            version=state.version,
            command_type="REDUCE",
            side="SELL",
            quantity="1",
            reduce_only=True,
            submitted_at="2026-08-12T12:02:00+00:00",
        )
        state = self.service.submit(reduce)
        before_margin = Decimal(state.reserved_margin)
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00", bid="109.9", ask="110"
            ),
        )
        self.assertEqual(state.positions[0].quantity, "1")
        self.assertGreater(Decimal(state.realized_pnl), 0)
        self.assertLess(Decimal(state.reserved_margin), before_margin)

    def test_market_without_observable_size_is_unresolved_not_filled(self) -> None:
        state = self.service.submit(self._command(command_id="unknown-size", version=1))
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
                quantity=None,
            ),
        )
        self.assertEqual(state.orders[0].state, "UNRESOLVED")
        self.assertEqual(state.orders[0].resolution_reason, "NO_EXECUTABLE_QUOTE_OR_SIZE")
        self.assertEqual(state.positions, ())

    def test_fill_that_exceeds_isolated_collateral_is_unresolved(self) -> None:
        state = self.service.submit(
            self._command(command_id="oversized", version=1, quantity="1000")
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
                quantity="1000",
            ),
        )
        self.assertEqual(state.orders[0].state, "UNRESOLVED")
        self.assertEqual(
            state.orders[0].resolution_reason,
            "AVAILABLE_COLLATERAL_INSUFFICIENT_AT_FILL",
        )
        self.assertEqual(state.reserved_margin, "0")

    def test_unordered_bar_that_touches_stop_and_target_does_not_choose_path(self) -> None:
        state = self.service.submit(self._command(command_id="entry", version=1))
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        stop = self._command(
            command_id="protect-stop",
            version=state.version,
            command_type="STOP_LOSS",
            side="SELL",
            quantity="2",
            trigger_price="90",
            reduce_only=True,
            submitted_at="2026-08-12T12:02:00+00:00",
        )
        state = self.service.submit(stop)
        target = self._command(
            command_id="protect-target",
            version=state.version,
            command_type="TAKE_PROFIT",
            side="SELL",
            quantity="2",
            trigger_price="110",
            reduce_only=True,
            submitted_at="2026-08-12T12:02:01+00:00",
        )
        state = self.service.submit(target)
        bar = PaperMarketSliceV1(
            symbol="HYPE-USDT-SWAP",
            observed_at="2026-08-12T12:03:00+00:00",
            available_at="2026-08-12T12:03:01+00:00",
            source_sha256=ONE_SHA,
            granularity="BAR",
            path_status="UNORDERED",
            low="85",
            high="115",
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=bar,
        )
        protective = [order for order in state.orders if order.command_type != "MARKET"]
        self.assertEqual({order.state for order in protective}, {"UNRESOLVED"})
        self.assertEqual(state.positions[0].quantity, "2")

    def test_command_shape_and_ledger_tamper_are_rejected(self) -> None:
        with self.assertRaises(PaperContractError):
            self._command(
                command_id="bad-limit",
                version=1,
                command_type="LIMIT",
                limit_price=None,
            )
        self.service.submit(self._command(command_id="tamper", version=1))
        path = self.root / "accounts" / "hype-paper" / "events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        value = json.loads(lines[-1])
        value["payload"]["order"]["state"] = "FILLED"
        lines[-1] = json.dumps(value, separators=(",", ":"), sort_keys=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(PaperLedgerError):
            FilePaperLedger(self.root).load_records("hype-paper")

    def test_market_cursor_is_durable_and_duplicate_or_regressive_slice_is_rejected(self) -> None:
        first = self._quote(
            observed_at="2026-08-12T12:00:01+00:00",
            available_at="2026-08-12T12:00:02+00:00",
            bid="99",
            ask="100",
            source=ONE_SHA,
        )
        state = self.service.observe(
            account_id="hype-paper", expected_account_version=1, market=first
        )
        self.assertEqual(state.version, 2)
        self.assertEqual(state.last_market_observed_at, first.observed_at)
        self.assertEqual(state.last_market_available_at, first.available_at)
        self.assertEqual(state.last_market_source_sha256, ONE_SHA)
        restarted = PaperTradingService(
            FilePaperLedger(self.root), cost_models=(self.model,)
        ).load_account("hype-paper")
        self.assertEqual(restarted.to_dict(), state.to_dict())
        with self.assertRaisesRegex(PaperTradingError, "PAPER_MARKET_SLICE_NOT_FORWARD"):
            self.service.observe(
                account_id="hype-paper", expected_account_version=state.version, market=first
            )
        with self.assertRaisesRegex(PaperTradingError, "PAPER_MARKET_SLICE_NOT_FORWARD"):
            self.service.observe(
                account_id="hype-paper",
                expected_account_version=state.version,
                market=self._quote(
                    observed_at="2026-08-12T12:00:00+00:00",
                    available_at="2026-08-12T12:00:03+00:00",
                    bid="99",
                    ask="100",
                    source="2" * 64,
                ),
            )

    def test_one_slice_shares_side_liquidity_and_market_remainder_is_terminal(self) -> None:
        state = self.service.submit(
            self._command(command_id="first-market", version=1, quantity="2")
        )
        state = self.service.submit(
            self._command(
                command_id="second-market",
                version=state.version,
                quantity="2",
                submitted_at="2026-08-12T12:01:00+00:00",
            )
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
                quantity="3",
            ),
        )
        orders = {order.order_id: order for order in state.orders}
        self.assertEqual(orders["first-market"].state, "FILLED")
        self.assertEqual(orders["second-market"].filled_quantity, "1")
        self.assertEqual(orders["second-market"].state, "UNRESOLVED")
        self.assertEqual(
            orders["second-market"].resolution_reason,
            "UNFILLED_REMAINDER_AFTER_FIRST_ELIGIBLE_SLICE",
        )
        self.assertEqual(state.positions[0].quantity, "3")

    def test_legal_reduce_can_close_into_explicit_collateral_deficit(self) -> None:
        account_id = "loss-paper"
        self.service.open_account(
            account_id=account_id,
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="loss-agent",
            base_currency="USDT",
            permitted_symbol="HYPE-USDT-SWAP",
            max_leverage="5",
            initial_balance="1.1",
            opened_at="2026-08-12T12:00:00+00:00",
            instrument_spec=_instrument_spec(
                instrument_spec_id="hype-loss-contract-v1"
            ),
        )
        def command(command_id: str, version: int, kind: str, side: str, when: str) -> PaperCommandV1:
            return PaperCommandV1(
                command_id=command_id,
                account_id=account_id,
                logical_agent_id="loss-agent",
                agent_generation=1,
                decision_cycle_id="hype-loss-cycle-001",
                decision_sha256=ONE_SHA,
                expected_account_version=version,
                symbol="HYPE-USDT-SWAP",
                command_type=kind,
                side=side,
                quantity="1",
                limit_price=None,
                trigger_price=None,
                target_order_id=None,
                reduce_only=kind == "REDUCE",
                time_in_force="GTC",
                submitted_at=when,
                expires_at=None,
                cost_model_id=self.model.model_id,
            )
        state = self.service.submit(
            command("loss-open", 1, "MARKET", "BUY", "2026-08-12T12:01:00+00:00")
        )
        state = self.service.observe(
            account_id=account_id,
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="4.99", ask="5"
            ),
        )
        state = self.service.submit(
            command("loss-close", state.version, "REDUCE", "SELL", "2026-08-12T12:02:00+00:00")
        )
        state = self.service.observe(
            account_id=account_id,
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00", bid="0.01", ask="0.02"
            ),
        )
        self.assertEqual(state.positions[0].quantity, "0")
        self.assertLess(Decimal(state.available_balance), 0)
        self.assertGreater(Decimal(state.collateral_deficit), 0)

    def test_command_time_and_agent_generation_are_monotone(self) -> None:
        with self.assertRaisesRegex(PaperTradingError, "PAPER_COMMAND_TIME_REGRESSION"):
            self.service.submit(
                self._command(
                    command_id="before-open",
                    version=1,
                    submitted_at="2026-08-12T11:59:59+00:00",
                )
            )
        self.authority.generations["hype-trader"] = 2
        state = self.service.submit(
            self._command(
                command_id="next-generation",
                version=1,
                agent_generation=2,
            )
        )
        self.assertEqual(state.owner_agent_generation, 2)
        with self.assertRaisesRegex(PaperTradingError, "PAPER_AGENT_GENERATION_NOT_CURRENT"):
            self.service.submit(
                self._command(
                    command_id="old-generation",
                    version=state.version,
                    agent_generation=1,
                    submitted_at="2026-08-12T12:01:01+00:00",
                )
            )

    def test_command_and_market_require_current_sealed_authority(self) -> None:
        self.authority.decisions.clear()
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_DECISION_REFERENCE_UNVERIFIED"
        ):
            self.service.submit(self._command(command_id="forged-decision", version=1))
        self.authority.decisions.add(ONE_SHA)
        state = self.service.submit(self._command(command_id="valid-decision", version=1))
        self.market_evidence.sources.clear()
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_MARKET_EVIDENCE_UNVERIFIED"
        ):
            self.service.observe(
                account_id="hype-paper",
                expected_account_version=state.version,
                market=self._quote(
                    observed_at="2026-08-12T12:01:01+00:00",
                    bid="99",
                    ask="100",
                ),
            )

    def test_ioc_limit_expires_on_first_eligible_slice_and_limit_cost_is_taker(self) -> None:
        state = self.service.submit(
            self._command(
                command_id="ioc-away",
                version=1,
                command_type="LIMIT",
                limit_price="90",
                time_in_force="IOC",
            )
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99", ask="100"
            ),
        )
        self.assertEqual(state.orders[0].state, "EXPIRED")
        self.assertEqual(state.orders[0].resolution_reason, "IOC_NOT_FILLED")

        limit = self._command(
            command_id="crossed-limit",
            version=state.version,
            command_type="LIMIT",
            limit_price="101",
            submitted_at="2026-08-12T12:02:00+00:00",
        )
        state = self.service.submit(limit)
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00", bid="99.9", ask="100"
            ),
        )
        fill = self.ledger.load_records("hype-paper")[-1].payload["fill"]
        self.assertEqual(fill["fee"], "0.040004")
        self.assertEqual(fill["impact_cost"], "0.02")

    def test_ioc_impact_protection_expires_instead_of_becoming_unresolved(self) -> None:
        state = self.service.submit(
            self._command(
                command_id="ioc-at-exact-limit",
                version=1,
                command_type="LIMIT",
                limit_price="100",
                time_in_force="IOC",
            )
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
            ),
        )

        order = state.orders[0]
        self.assertEqual("EXPIRED", order.state)
        self.assertEqual("IOC_NOT_FILLED", order.resolution_reason)
        self.assertEqual((), state.positions)
        self.assertFalse(
            any(
                record.event_type == "FILL_RECORDED"
                for record in self.ledger.load_records("hype-paper")
            )
        )

    def test_gtc_explicit_expiry_remains_distinct_from_limit_protection(self) -> None:
        state = self.service.submit(
            self._command(
                command_id="expiring-gtc",
                version=1,
                command_type="LIMIT",
                limit_price="90",
                expires_at="2026-08-12T12:02:00+00:00",
            )
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:00+00:00",
                bid="99.9",
                ask="100",
            ),
        )

        self.assertEqual("EXPIRED", state.orders[0].state)
        self.assertEqual("ORDER_EXPIRY_REACHED", state.orders[0].resolution_reason)

    def test_modeled_impact_never_executes_beyond_agent_limit(self) -> None:
        initial_cash = self.service.load_account("hype-paper").cash_balance
        buy = self.service.submit(
            self._command(
                command_id="buy-at-exact-limit",
                version=1,
                command_type="LIMIT",
                limit_price="100",
            )
        )
        buy = self.service.observe(
            account_id="hype-paper",
            expected_account_version=buy.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
            ),
        )
        buy_order = next(
            order for order in buy.orders if order.command_id == "buy-at-exact-limit"
        )
        self.assertEqual("OPEN", buy_order.state)
        self.assertIsNone(buy_order.resolution_reason)
        self.assertEqual((), buy.positions)
        self.assertEqual(initial_cash, buy.cash_balance)

        buy = self.service.observe(
            account_id="hype-paper",
            expected_account_version=buy.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:02+00:00",
                bid="99.97",
                ask="99.98",
            ),
        )
        buy_order = next(
            order for order in buy.orders if order.command_id == "buy-at-exact-limit"
        )
        self.assertEqual("FILLED", buy_order.state)
        buy_fill = next(
            record.payload["fill"]
            for record in self.ledger.load_records("hype-paper")
            if record.event_type == "FILL_RECORDED"
        )
        self.assertLessEqual(Decimal(buy_fill["price"]), Decimal("100"))

        cash_before_reduce = buy.cash_balance
        position_before_reduce = buy.positions[0]
        reduced = self.service.submit(
            self._command(
                command_id="reduce-at-exact-limit",
                version=buy.version,
                command_type="LIMIT_REDUCE",
                side="SELL",
                quantity="2",
                limit_price="100",
                reduce_only=True,
                submitted_at="2026-08-12T12:02:00+00:00",
            )
        )
        reduced = self.service.observe(
            account_id="hype-paper",
            expected_account_version=reduced.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00",
                bid="100",
                ask="100.1",
            ),
        )
        reduce_order = next(
            order
            for order in reduced.orders
            if order.command_id == "reduce-at-exact-limit"
        )
        self.assertEqual("OPEN", reduce_order.state)
        self.assertIsNone(reduce_order.resolution_reason)
        self.assertEqual(position_before_reduce, reduced.positions[0])
        self.assertEqual(cash_before_reduce, reduced.cash_balance)

        reduced = self.service.observe(
            account_id="hype-paper",
            expected_account_version=reduced.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:02+00:00",
                bid="100.02",
                ask="100.03",
            ),
        )
        reduce_order = next(
            order
            for order in reduced.orders
            if order.command_id == "reduce-at-exact-limit"
        )
        self.assertEqual("FILLED", reduce_order.state)
        self.assertEqual("0", reduced.positions[0].quantity)
        reduce_fill = tuple(
            record.payload["fill"]
            for record in self.ledger.load_records("hype-paper")
            if record.event_type == "FILL_RECORDED"
        )[-1]
        self.assertGreaterEqual(Decimal(reduce_fill["price"]), Decimal("100"))

    def test_system_position_notional_cap_is_enforced_on_actual_fill(self) -> None:
        capped = PaperTradingService(
            self.ledger,
            cost_models=(self.model,),
            decision_authority=self.authority,
            market_evidence=self.market_evidence,
            carry_evidence=_CarryEvidence(),
            max_position_notional="150",
        )
        submitted = capped.submit(
            self._command(command_id="over-frozen-cap", version=1)
        )
        result = capped.observe(
            account_id="hype-paper",
            expected_account_version=submitted.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9",
                ask="100",
            ),
        )
        self.assertEqual((), result.positions)
        self.assertEqual("10000", result.cash_balance)
        self.assertEqual("0", result.reserved_margin)
        self.assertEqual("UNRESOLVED", result.orders[0].state)
        self.assertEqual(
            "MAX_POSITION_NOTIONAL_EXCEEDED_AT_FILL",
            result.orders[0].resolution_reason,
        )
        self.assertFalse(
            any(
                record.event_type == "FILL_RECORDED"
                for record in self.ledger.load_records("hype-paper")
            )
        )

    def test_competing_reduce_orders_terminalize_after_position_is_consumed(self) -> None:
        state = self.service.submit(self._command(command_id="position", version=1))
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        first = self._command(
            command_id="reduce-first", version=state.version, command_type="REDUCE",
            side="SELL", quantity="2", reduce_only=True,
            submitted_at="2026-08-12T12:02:00+00:00",
        )
        state = self.service.submit(first)
        second = self._command(
            command_id="reduce-second", version=state.version, command_type="REDUCE",
            side="SELL", quantity="2", reduce_only=True,
            submitted_at="2026-08-12T12:02:00+00:00",
        )
        state = self.service.submit(second)
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00", bid="101", ask="101.1"
            ),
        )
        orders = {order.order_id: order for order in state.orders}
        self.assertEqual(orders["reduce-first"].state, "FILLED")
        self.assertEqual(orders["reduce-second"].state, "UNRESOLVED")
        self.assertEqual(
            orders["reduce-second"].resolution_reason,
            "REDUCE_ONLY_NO_REMAINING_POSITION",
        )
        self.assertEqual(state.positions[0].quantity, "0")

    def test_cost_model_without_amount_source_rejects_modeled_or_observed_status(self) -> None:
        for status in ("MODELED", "OBSERVED"):
            with self.subTest(status=status), self.assertRaises(PaperContractError):
                PaperCostModelV1(
                    model_id=f"bad-{status.lower()}",
                    maker_fee_bps="1",
                    taker_fee_bps="2",
                    market_impact_bps="1",
                    funding_status=status,
                    borrow_status="UNKNOWN",
                )
        with self.assertRaises(PaperContractError):
            PaperCostModelV1(
                model_id="impossible-impact",
                maker_fee_bps="1",
                taker_fee_bps="2",
                market_impact_bps="10000",
            )

    def test_linear_perp_account_requires_verified_raw_bound_instrument_spec(self) -> None:
        records_before = self.ledger.load_records("missing-spec-paper")
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_LINEAR_PERP_INSTRUMENT_SPEC_REQUIRED"
        ):
            self.service.open_account(
                account_id="missing-spec-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="hype-trader",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="5",
                initial_balance="1000",
                opened_at="2026-08-12T12:00:00+00:00",
            )
        with self.assertRaisesRegex(
            PaperTradingError,
            "PAPER_LINEAR_PERP_INSTRUMENT_SPEC_RAW_BOUND_REQUIRED",
        ):
            self.service.open_account(
                account_id="modeled-spec-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="hype-trader",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="5",
                initial_balance="1000",
                opened_at="2026-08-12T12:00:00+00:00",
                instrument_spec=InstrumentSpecV1(
                    instrument_spec_id="unverified-contract-v1",
                    symbol="HYPE-USDT-SWAP",
                    account_mode="LINEAR_PERP",
                    quote_currency="USDT",
                    contract_multiplier="1",
                    quantity_basis="CONTRACTS",
                ),
            )
        self.assertEqual(records_before, ())
        self.assertEqual(self.ledger.load_records("missing-spec-paper"), ())
        self.assertEqual(self.ledger.load_records("modeled-spec-paper"), ())

    def test_sourced_funding_is_effective_time_bound_idempotent_and_completes_carry(self) -> None:
        state = self.service.submit(self._command(command_id="funding-position", version=1))
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        cash_before = Decimal(state.cash_balance)
        accrual = CarryAccrualV1(
            accrual_id="funding-20260812-1202",
            account_id="hype-paper",
            symbol="HYPE-USDT-SWAP",
            kind="FUNDING",
            status="OBSERVED",
            amount="0.2",
            rate="0.001",
            reference_price="100",
            position_quantity="2",
            effective_at="2026-08-12T12:02:00+00:00",
            available_at="2026-08-12T12:02:01+00:00",
            rate_source_sha256=ONE_SHA,
            price_source_sha256=ONE_SHA,
            reason="settled funding bound to explicit rate and reference mark",
            coverage_status="COMPLETE",
            coverage_start_at="2026-08-12T04:00:00+00:00",
            coverage_end_at="2026-08-12T12:02:00+00:00",
        )
        funded = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=accrual,
        )
        self.assertEqual(Decimal(funded.cash_balance), cash_before - Decimal("0.2"))
        self.assertEqual(funded.funding_paid, "0.2")
        self.assertEqual(funded.funding_coverage_status, "COMPLETE")
        self.assertEqual(funded.borrow_coverage_status, "NOT_APPLICABLE")
        self.assertEqual(funded.carry_coverage_status, "COMPLETE")
        duplicate = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=accrual,
        )
        self.assertEqual(duplicate.to_dict(), funded.to_dict())

    def test_funding_coverage_segments_must_touch_and_preserve_open_start(
        self,
    ) -> None:
        model = FundingSettlementModelV1(
            model_id="incremental-funding-v1",
            model_version="v1",
            price_proxy_method="LAST_CONFIRMED_15M_CLOSE_NOT_AFTER_EFFECTIVE_AT",
            cost_model_id=self.model.model_id,
            cost_model_digest=self.model.model_digest,
            effective_from="2026-08-12T11:00:00+00:00",
            effective_to="2026-08-12T14:00:00+00:00",
        )

        def advance(
            *, identity: str, start: str, end: str, available: str
        ) -> FundingCoverageAdvanceV1:
            return FundingCoverageAdvanceV1(
                advance_id=identity,
                account_id="hype-paper",
                symbol="HYPE-USDT-SWAP",
                coverage_start_at=start,
                coverage_end_at=end,
                available_at=available,
                settlement_model=model,
                funding_history_source_sha256=ONE_SHA,
                price_proxy_source_sha256=ONE_SHA,
                history_boundary_before_at="2026-08-12T11:59:00+00:00",
                history_boundary_after_at=(
                    datetime.fromisoformat(end) + timedelta(minutes=1)
                ).isoformat(),
                event_effective_ats=(),
                event_accrual_sha256s=(),
            )

        state = self.service.load_account("hype-paper")
        first = advance(
            identity="funding-segment-1",
            start="2026-08-12T12:00:00+00:00",
            end="2026-08-12T12:01:00+00:00",
            available="2026-08-12T12:03:00+00:00",
        )
        state = self.service.settle_funding_window(
            account_id="hype-paper",
            expected_account_version=state.version,
            accruals=(),
            advance=first,
        )
        second = advance(
            identity="funding-segment-2",
            start=first.coverage_end_at,
            end="2026-08-12T12:02:00+00:00",
            available="2026-08-12T12:04:00+00:00",
        )
        state = self.service.settle_funding_window(
            account_id="hype-paper",
            expected_account_version=state.version,
            accruals=(),
            advance=second,
        )
        self.assertEqual("2026-08-12T12:00:00+00:00", state.funding_coverage_start_at)
        self.assertEqual(second.coverage_end_at, state.funding_coverage_end_at)

        records_before = self.ledger.load_records("hype-paper")
        gap = advance(
            identity="funding-segment-gap",
            start="2026-08-12T12:02:00.000001+00:00",
            end="2026-08-12T12:03:00+00:00",
            available="2026-08-12T12:05:00+00:00",
        )
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_FUNDING_COVERAGE_ACCOUNT_MISMATCH"
        ):
            self.service.settle_funding_window(
                account_id="hype-paper",
                expected_account_version=state.version,
                accruals=(),
                advance=gap,
            )
        self.assertEqual(
            records_before, self.ledger.load_records("hype-paper")
        )

    def test_positive_funding_rate_credits_the_bound_short_position(self) -> None:
        state = self.service.submit(
            self._command(
                command_id="funding-short-position",
                version=1,
                side="SELL",
            )
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="100",
                ask="100.1",
            ),
        )
        self.assertEqual(state.positions[0].quantity, "-2")
        cash_before = Decimal(state.cash_balance)
        funded = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=CarryAccrualV1(
                accrual_id="funding-short-20260812-1202",
                account_id="hype-paper",
                symbol="HYPE-USDT-SWAP",
                kind="FUNDING",
                status="OBSERVED",
                amount="-0.2",
                rate="0.001",
                reference_price="100",
                position_quantity="-2",
                effective_at="2026-08-12T12:02:00+00:00",
                available_at="2026-08-12T12:02:01+00:00",
                rate_source_sha256=ONE_SHA,
                price_source_sha256=ONE_SHA,
                reason="positive funding credits the exact short position snapshot",
                coverage_status="COMPLETE",
                coverage_start_at="2026-08-12T04:00:00+00:00",
                coverage_end_at="2026-08-12T12:02:00+00:00",
            ),
        )

        self.assertEqual(Decimal(funded.cash_balance), cash_before + Decimal("0.2"))
        self.assertEqual(funded.funding_paid, "-0.2")
        self.assertEqual(funded.carry_coverage_status, "COMPLETE")

    def test_same_funding_economic_event_with_new_id_is_not_deducted_twice(self) -> None:
        state = self.service.submit(
            self._command(command_id="funding-idempotent-position", version=1)
        )
        state = self.service.observe(
            account_id="hype-paper",
            expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00", bid="99.9", ask="100"
            ),
        )
        accrual = CarryAccrualV1(
            accrual_id="funding-economic-event-a",
            account_id="hype-paper",
            symbol="HYPE-USDT-SWAP",
            kind="FUNDING",
            status="OBSERVED",
            amount="0.2",
            rate="0.001",
            reference_price="100",
            position_quantity="2",
            effective_at="2026-08-12T12:02:00+00:00",
            available_at="2026-08-12T12:02:01+00:00",
            rate_source_sha256=ONE_SHA,
            price_source_sha256=ONE_SHA,
            reason="first delivery of one economic settlement",
            coverage_status="COMPLETE",
            coverage_start_at="2026-08-12T04:00:00+00:00",
            coverage_end_at="2026-08-12T12:02:00+00:00",
        )
        first = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=accrual,
        )
        duplicate = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=first.version,
            accrual=CarryAccrualV1(
                **{
                    **accrual.to_dict(),
                    "accrual_id": "funding-economic-event-b",
                    "reason": "same settlement delivered under another request id",
                }
            ),
        )

        self.assertEqual(duplicate.to_dict(), first.to_dict())
        self.assertEqual(duplicate.funding_paid, "0.2")
        self.assertEqual(
            len(
                [
                    item
                    for item in self.ledger.load_records("hype-paper")
                    if item.event_type == "CARRY_ACCRUED"
                ]
            ),
            1,
        )
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_CARRY_ECONOMIC_EVENT_CONFLICT"
        ):
            self.service.accrue_carry(
                account_id="hype-paper",
                expected_account_version=first.version,
                accrual=CarryAccrualV1(
                    **{
                        **accrual.to_dict(),
                        "accrual_id": "funding-economic-event-conflict",
                        "amount": "0.4",
                    }
                ),
            )
        replay_duplicate = CarryAccrualV1(
            **{
                **accrual.to_dict(),
                "accrual_id": "funding-economic-event-ledger-tamper",
            }
        )
        self.ledger.append_many(
            account_id="hype-paper",
            expected_revision=first.version,
            events=(
                {
                    "event_id": replay_duplicate.accrual_id,
                    "event_type": "CARRY_ACCRUED",
                    "occurred_at": replay_duplicate.available_at,
                    "payload": {
                        "accrual": replay_duplicate.to_dict(),
                        "cash_balance": str(
                            Decimal(first.cash_balance) - Decimal("0.2")
                        ),
                        "funding_paid": "0.4",
                        "borrow_paid": first.borrow_paid,
                    },
                },
            ),
        )
        with self.assertRaisesRegex(
            PaperTradingError,
            "PAPER_CARRY_ECONOMIC_EVENT_DUPLICATE_IN_LEDGER",
        ):
            self.service.load_account("hype-paper")

    def test_unknown_funding_stays_null_and_cannot_change_cash(self) -> None:
        state = self.service.load_account("hype-paper")
        accrual = CarryAccrualV1(
            accrual_id="funding-unknown-window",
            account_id="hype-paper",
            symbol="HYPE-USDT-SWAP",
            kind="FUNDING",
            status="UNKNOWN",
            amount=None,
            rate=None,
            reference_price=None,
            position_quantity="0",
            effective_at="2026-08-12T12:01:00+00:00",
            available_at="2026-08-12T12:01:01+00:00",
            rate_source_sha256=None,
            price_source_sha256=None,
            reason="funding interval has no complete source binding",
            coverage_status="UNKNOWN",
            coverage_start_at="2026-08-12T04:00:00+00:00",
            coverage_end_at="2026-08-12T12:01:00+00:00",
        )
        updated = self.service.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=accrual,
        )
        self.assertEqual(updated.cash_balance, state.cash_balance)
        self.assertEqual(updated.funding_paid, "0")
        event = self.ledger.load_records("hype-paper")[-1]
        self.assertIsNone(event.payload["accrual"]["amount"])

    def test_carry_contract_rejects_inconsistent_na_and_out_of_window_effective_time(self) -> None:
        common = {
            "accrual_id": "funding-invalid-contract",
            "account_id": "hype-paper",
            "symbol": "HYPE-USDT-SWAP",
            "kind": "FUNDING",
            "status": "OBSERVED",
            "amount": "0.2",
            "rate": "0.001",
            "reference_price": "100",
            "position_quantity": "2",
            "effective_at": "2026-08-12T12:02:00+00:00",
            "available_at": "2026-08-12T12:02:01+00:00",
            "rate_source_sha256": ONE_SHA,
            "price_source_sha256": ONE_SHA,
            "reason": "invalid carry contract fixture",
            "coverage_start_at": "2026-08-12T12:02:00+00:00",
            "coverage_end_at": "2026-08-12T12:02:00+00:00",
        }
        with self.assertRaisesRegex(
            PaperContractError,
            "status and coverage_status must agree on NOT_APPLICABLE",
        ):
            CarryAccrualV1(**common, coverage_status="NOT_APPLICABLE")

        with self.assertRaisesRegex(
            PaperContractError,
            "coverage window must contain effective_at",
        ):
            CarryAccrualV1(
                **{
                    **common,
                    "coverage_status": "COMPLETE",
                    "coverage_start_at": "2026-08-12T12:02:01+00:00",
                    "coverage_end_at": "2026-08-12T12:03:00+00:00",
                }
            )

    def test_linear_perp_funding_cannot_be_marked_not_applicable_or_replayed(self) -> None:
        state = self.service.load_account("hype-paper")
        accrual = CarryAccrualV1(
            accrual_id="funding-invalid-not-applicable",
            account_id="hype-paper",
            symbol="HYPE-USDT-SWAP",
            kind="FUNDING",
            status="NOT_APPLICABLE",
            amount=None,
            rate=None,
            reference_price=None,
            position_quantity="0",
            effective_at="2026-08-12T12:01:00+00:00",
            available_at="2026-08-12T12:01:01+00:00",
            rate_source_sha256=None,
            price_source_sha256=None,
            reason="perpetual funding may be unknown but is not inapplicable",
            coverage_status="NOT_APPLICABLE",
            coverage_start_at="2026-08-12T12:01:00+00:00",
            coverage_end_at="2026-08-12T12:01:00+00:00",
        )
        with self.assertRaisesRegex(
            PaperTradingError,
            "PAPER_PERP_FUNDING_CANNOT_BE_NOT_APPLICABLE",
        ):
            self.service.accrue_carry(
                account_id="hype-paper",
                expected_account_version=state.version,
                accrual=accrual,
            )
        self.assertEqual(self.service.load_account("hype-paper").version, state.version)

        self.ledger.append_many(
            account_id="hype-paper",
            expected_revision=state.version,
            events=(
                {
                    "event_id": accrual.accrual_id,
                    "event_type": "CARRY_ACCRUED",
                    "occurred_at": accrual.available_at,
                    "payload": {"accrual": accrual.to_dict()},
                },
            ),
        )
        with self.assertRaisesRegex(
            PaperTradingError,
            "PAPER_PERP_FUNDING_CANNOT_BE_NOT_APPLICABLE",
        ):
            self.service.load_account("hype-paper")

    def test_complete_carry_window_with_initial_gap_fails_before_ledger_append(self) -> None:
        state = self.service.load_account("hype-paper")
        gap = CarryAccrualV1(
            accrual_id="funding-gap-window",
            account_id="hype-paper",
            symbol="HYPE-USDT-SWAP",
            kind="FUNDING",
            status="OBSERVED",
            amount="0",
            rate="0.001",
            reference_price="100",
            position_quantity="0",
            effective_at="2026-08-12T12:01:00+00:00",
            available_at="2026-08-12T12:01:01+00:00",
            rate_source_sha256=ONE_SHA,
            price_source_sha256=ONE_SHA,
            reason="source window starts after the paper account",
            coverage_status="COMPLETE",
            coverage_start_at="2026-08-12T12:00:30+00:00",
            coverage_end_at="2026-08-12T12:01:01+00:00",
        )

        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_CARRY_COVERAGE_INITIAL_GAP"
        ):
            self.service.accrue_carry(
                account_id="hype-paper",
                expected_account_version=state.version,
                accrual=gap,
            )
        self.assertEqual(
            self.service.load_account("hype-paper").version, state.version
        )

    def test_replay_rejects_order_identity_that_conflicts_with_account(self) -> None:
        wrong = OrderTruthV1(
            order_id="wrong-order",
            command_id="wrong-command",
            account_id="different-account",
            logical_agent_id="hype-trader",
            symbol="HYPE-USDT-SWAP",
            command_type="MARKET",
            side="BUY",
            original_quantity="1",
            filled_quantity="0",
            remaining_quantity="1",
            limit_price=None,
            trigger_price=None,
            reduce_only=False,
            time_in_force="GTC",
            expires_at=None,
            cost_model_id=self.model.model_id,
            state="OPEN",
            created_at="2026-08-12T12:01:00+00:00",
            updated_at="2026-08-12T12:01:00+00:00",
        )
        self.ledger.append_many(
            account_id="hype-paper",
            expected_revision=1,
            events=({
                "event_id": "wrong-order-event",
                "event_type": "ORDER_OPENED",
                "occurred_at": "2026-08-12T12:01:00+00:00",
                "payload": {"order": wrong.to_dict()},
            },),
        )
        with self.assertRaisesRegex(PaperTradingError, "PAPER_ORDER_ACCOUNT_MISMATCH"):
            self.service.load_account("hype-paper")

    def test_instrument_spec_multiplier_drives_notional_margin_and_pnl(self) -> None:
        spec = InstrumentSpecV1(
            instrument_spec_id="hype-contract-v1",
            symbol="HYPE-USDT-SWAP",
            account_mode="LINEAR_PERP",
            quote_currency="USDT",
            contract_multiplier="0.1",
            quantity_basis="CONTRACTS",
            parameter_status="OBSERVED_RAW_BOUND",
            parameter_source_sha256=ONE_SHA,
        )
        self.service.open_account(
            account_id="contract-paper",
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="contract-agent",
            base_currency="USDT",
            permitted_symbol="HYPE-USDT-SWAP",
            max_leverage="5",
            initial_balance="1000",
            opened_at="2026-08-12T12:00:00+00:00",
            instrument_spec=spec,
        )
        command = PaperCommandV1(
            command_id="ten-contracts", account_id="contract-paper",
            logical_agent_id="contract-agent", agent_generation=1,
            decision_cycle_id="hype-contract-cycle-001",
            decision_sha256=ONE_SHA, expected_account_version=1,
            symbol="HYPE-USDT-SWAP", command_type="MARKET", side="BUY",
            quantity="10", limit_price=None, trigger_price=None,
            target_order_id=None, reduce_only=False, time_in_force="GTC",
            submitted_at="2026-08-12T12:01:00+00:00", expires_at=None,
            cost_model_id=self.model.model_id,
        )
        state = self.service.submit(command)
        state = self.service.observe(
            account_id="contract-paper", expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:01:01+00:00",
                bid="99.9", ask="100", quantity="10",
            ),
        )
        self.assertEqual(state.instrument_spec, spec)
        self.assertEqual(state.reserved_margin, "20.002")
        self.assertEqual(state.fees_paid, "0.020002")
        close = PaperCommandV1(
            command_id="close-contracts", account_id="contract-paper",
            logical_agent_id="contract-agent", agent_generation=1,
            decision_cycle_id="hype-contract-cycle-001",
            decision_sha256=ONE_SHA, expected_account_version=state.version,
            symbol="HYPE-USDT-SWAP", command_type="REDUCE", side="SELL",
            quantity="10", limit_price=None, trigger_price=None,
            target_order_id=None, reduce_only=True, time_in_force="GTC",
            submitted_at="2026-08-12T12:02:00+00:00", expires_at=None,
            cost_model_id=self.model.model_id,
        )
        state = self.service.submit(close)
        state = self.service.observe(
            account_id="contract-paper", expected_account_version=state.version,
            market=self._quote(
                observed_at="2026-08-12T12:02:01+00:00",
                bid="110", ask="110.1", quantity="10",
            ),
        )
        self.assertEqual(state.positions[0].quantity, "0")
        self.assertEqual(state.reserved_margin, "0")
        self.assertEqual(state.realized_pnl, "9.979")
        fill = self.ledger.load_records("contract-paper")[-1].payload["fill"]
        self.assertEqual(fill["instrument_spec_id"], "hype-contract-v1")
        self.assertEqual(fill["quantity_basis"], "CONTRACTS")
        self.assertEqual(fill["contract_multiplier"], "0.1")
        self.assertEqual(fill["notional"], "109.989")


if __name__ == "__main__":
    unittest.main()
