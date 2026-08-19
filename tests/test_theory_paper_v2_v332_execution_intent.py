from __future__ import annotations

import tempfile
from dataclasses import replace
import hashlib
from pathlib import Path
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingError,
    PaperTradingService,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PaperBracketV1,
    PaperCommandV1,
    PaperContractError,
    PaperCostModelV1,
    PaperExecutionIntentV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_intent_mailbox import (
    LocalPaperExecutionIntentMailbox,
)
from trade_system.theory_paper_v2.v32_durable_json import write_once_json


class _DecisionAuthority:
    @staticmethod
    def current_generation(logical_agent_id: str) -> int | None:
        return 1 if logical_agent_id == "HYPE_TRADER" else None

    @staticmethod
    def verifies_decision(command: PaperCommandV1) -> bool:
        return command.decision_cycle_id == "hype-decision-1"

    @staticmethod
    def verifies_execution_intent(intent: PaperExecutionIntentV1) -> bool:
        return (
            intent.execution_intent_request_sha256 == "5" * 64
            and intent.decision_request_sha256 == "2" * 64
            and intent.paper_context_sha256 == "3" * 64
            and len(intent.ledger_head_record_sha256) == 64
        )


class _MarketEvidence:
    @staticmethod
    def verifies_market_slice(market: PaperMarketSliceV1) -> bool:
        return market.source_sha256 == "6" * 64


def _command(*, side: str = "BUY") -> PaperCommandV1:
    return PaperCommandV1(
        command_id="hype-transition-1",
        account_id="hype-paper",
        logical_agent_id="HYPE_TRADER",
        agent_generation=1,
        decision_cycle_id="hype-decision-1",
        decision_sha256="1" * 64,
        expected_account_version=1,
        symbol="HYPE-USDT-SWAP",
        command_type="MARKET",
        side=side,
        quantity="1",
        limit_price=None,
        trigger_price=None,
        target_order_id=None,
        reduce_only=False,
        time_in_force="GTC",
        submitted_at="2026-08-13T08:01:00Z",
        expires_at=None,
        cost_model_id="paper-cost-v1",
    )


def _intent(*, command: PaperCommandV1 | None = None) -> PaperExecutionIntentV1:
    selected = _command() if command is None else command
    signed_quantity = "-1" if selected.side == "SELL" else "1"
    return PaperExecutionIntentV1(
        intent_id="hype-transition-1",
        execution_intent_request_sha256="5" * 64,
        decision_request_sha256="2" * 64,
        paper_context_sha256="3" * 64,
        ledger_head_record_sha256="4" * 64,
        decision_cycle_id="hype-decision-1",
        decision_sha256="1" * 64,
        account_id="hype-paper",
        logical_agent_id="HYPE_TRADER",
        agent_generation=1,
        expected_account_version=1,
        symbol="HYPE-USDT-SWAP",
        authored_at="2026-08-13T08:01:00Z",
        valid_until="2026-08-13T08:06:00Z",
        action="OPEN",
        episode_id="hype-episode-1",
        transition_id="hype-transition-1",
        tranche_id="hype-core-1",
        role="CORE",
        pre_state={"status": "FLAT", "signed_quantity": "0"},
        target_state={"status": "ACTIVE", "signed_quantity": signed_quantity},
        position_delta={"action": "OPEN", "signed_quantity_change": signed_quantity},
        evidence_delta="The frozen activation condition is observed at the cutoff.",
        activation="Only execute this exact one-contract paper command.",
        hard_invalidation="Cancel if the intent expires before submission.",
        risk_budget={
            "maximum_loss": "50",
            "notional_cap": "500",
            "max_observed_drawdown": "100",
            "stress_note": "Local paper only; unknown gap and carry remain explicit.",
        },
        command=selected,
    )


class V332PaperExecutionIntentTests(unittest.TestCase):
    def test_readable_text_fields_reject_json_objects(self) -> None:
        for field_name in (
            "evidence_delta",
            "activation",
            "hard_invalidation",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(PaperContractError, "readable text"):
                    replace(
                        _intent(),
                        **{field_name: {"status": "BLOCKED_SAFE_WAIT"}},
                    )

    @staticmethod
    def _bracket_intent(*, ledger_head: str = "4" * 64) -> PaperExecutionIntentV1:
        entry = replace(
            _command(),
            command_type="LIMIT",
            limit_price="56.18",
        )
        stop = replace(
            entry,
            command_id="hype-transition-1-stop",
            command_type="STOP_LOSS",
            side="SELL",
            limit_price=None,
            trigger_price="56.1",
            reduce_only=True,
        )
        target_one = replace(
            stop,
            command_id="hype-transition-1-tp-1",
            command_type="TAKE_PROFIT",
            quantity="0.75",
            trigger_price="56.3",
        )
        target_two = replace(
            target_one,
            command_id="hype-transition-1-tp-2",
            quantity="0.25",
            trigger_price="56.4",
        )
        base = _intent(command=entry)
        return replace(
            base,
            ledger_head_record_sha256=ledger_head,
            bracket=PaperBracketV1(
                bracket_id=base.intent_id,
                entry=entry,
                protective_stop=stop,
                take_profits=(target_one, target_two),
            ),
        )

    def test_bracket_13_round_trip_rejects_invalid_geometry_and_preserves_12(self) -> None:
        intent = self._bracket_intent()
        self.assertEqual(intent, PaperExecutionIntentV1.from_dict(intent.to_dict()))
        self.assertEqual("1.3.0", intent.to_dict()["schema_version"])
        with self.assertRaisesRegex(PaperContractError, "geometry"):
            replace(
                intent.bracket,
                protective_stop=replace(
                    intent.bracket.protective_stop,
                    trigger_price="56.3",
                ),
            )
        legacy = replace(
            _intent(), bracket=None, wire_schema_version="1.2.0"
        )
        legacy_document = legacy.to_dict()
        self.assertNotIn("bracket", legacy_document)
        self.assertEqual(legacy_document, PaperExecutionIntentV1.from_dict(legacy_document).to_dict())

    def test_bracket_entry_activates_exits_then_stop_cancels_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = FilePaperLedger(Path(temporary) / "paper")
            model = PaperCostModelV1(
                model_id="paper-cost-v1",
                maker_fee_bps="2",
                taker_fee_bps="5",
                market_impact_bps="0",
                funding_status="NOT_APPLICABLE",
                borrow_status="NOT_APPLICABLE",
            )
            service = PaperTradingService(
                ledger,
                cost_models=(model,),
                decision_authority=_DecisionAuthority(),
                market_evidence=_MarketEvidence(),
                require_execution_intent=True,
            )
            service.open_account(
                account_id="hype-paper",
                account_mode="CASH_SPOT",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="1",
                initial_balance="10000",
                opened_at="2026-08-13T08:00:00Z",
            )
            intent = self._bracket_intent(
                ledger_head=ledger.load_records("hype-paper")[-1].record_sha256
            )
            accepted = service.submit_intent(
                intent, received_at="2026-08-13T08:02:00Z"
            )
            preregistrations = [
                record
                for record in ledger.load_records("hype-paper")
                if record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED"
            ]
            self.assertEqual(1, len(preregistrations))
            comparator = preregistrations[0].payload["comparator"]
            self.assertEqual(intent.intent_sha256, comparator["intent_sha256"])
            self.assertEqual(
                intent.ledger_head_record_sha256,
                comparator["account_pre_head_record_sha256"],
            )
            self.assertEqual("56.18", comparator["reference"]["entry_price"])
            self.assertEqual("1", comparator["reference"]["initial_quantity"])
            self.assertEqual("56.1", comparator["reference"]["protective_stop"]["price"])
            self.assertEqual(
                "paper-cost-v1", comparator["reference"]["cost_model_id"]
            )
            self.assertEqual(
                ["OPEN", "HELD", "HELD", "HELD"],
                [item.state for item in accepted.orders],
            )
            entry_filled = service.observe(
                account_id="hype-paper",
                expected_account_version=accepted.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-13T08:02:01Z",
                    available_at="2026-08-13T08:02:01Z",
                    source_sha256="6" * 64,
                    granularity="QUOTE",
                    path_status="ORDERED",
                    bid="56.17",
                    ask="56.18",
                    available_quantity="10",
                ),
            )
            self.assertEqual("1", entry_filled.positions[0].quantity)
            self.assertEqual(
                ["FILLED", "OPEN", "OPEN", "OPEN"],
                [item.state for item in entry_filled.orders],
            )
            self.assertEqual(
                1,
                sum(
                    record.event_type
                    == "STATIC_NO_TRANSITION_PREREGISTERED"
                    for record in ledger.load_records("hype-paper")
                ),
            )
            partially_stopped = service.observe(
                account_id="hype-paper",
                expected_account_version=entry_filled.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-13T08:02:02Z",
                    available_at="2026-08-13T08:02:02Z",
                    source_sha256="6" * 64,
                    granularity="QUOTE",
                    path_status="ORDERED",
                    bid="56.09",
                    ask="56.1",
                    available_quantity="0.4",
                ),
            )
            self.assertEqual("0.6", partially_stopped.positions[0].quantity)
            self.assertEqual(
                ["FILLED", "PARTIALLY_FILLED", "CANCELLED", "CANCELLED"],
                [item.state for item in partially_stopped.orders],
            )
            stopped = service.observe(
                account_id="hype-paper",
                expected_account_version=partially_stopped.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-13T08:02:03Z",
                    available_at="2026-08-13T08:02:03Z",
                    source_sha256="6" * 64,
                    granularity="QUOTE",
                    path_status="ORDERED",
                    bid="56.08",
                    ask="56.09",
                    available_quantity="0.6",
                ),
            )
            self.assertEqual("0", stopped.positions[0].quantity)
            self.assertEqual(
                ["FILLED", "FILLED", "CANCELLED", "CANCELLED"],
                [item.state for item in stopped.orders],
            )
            self.assertEqual(
                stopped.to_dict(),
                PaperTradingService(
                    FilePaperLedger(Path(temporary) / "paper"),
                    cost_models=(model,),
                ).load_account("hype-paper").to_dict(),
            )

    def test_zero_fill_bracket_expiry_cancels_held_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = FilePaperLedger(Path(temporary) / "paper")
            model = PaperCostModelV1(
                model_id="paper-cost-v1",
                maker_fee_bps="2",
                taker_fee_bps="5",
                market_impact_bps="0",
                funding_status="NOT_APPLICABLE",
                borrow_status="NOT_APPLICABLE",
            )
            service = PaperTradingService(
                ledger,
                cost_models=(model,),
                decision_authority=_DecisionAuthority(),
                market_evidence=_MarketEvidence(),
                require_execution_intent=True,
            )
            service.open_account(
                account_id="hype-paper",
                account_mode="CASH_SPOT",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="1",
                initial_balance="10000",
                opened_at="2026-08-13T08:00:00Z",
            )
            base = self._bracket_intent(
                ledger_head=ledger.load_records("hype-paper")[-1].record_sha256
            )
            expiring_entry = replace(
                base.command, expires_at="2026-08-13T08:02:01Z"
            )
            intent = replace(
                base,
                command=expiring_entry,
                bracket=replace(base.bracket, entry=expiring_entry),
            )
            accepted = service.submit_intent(
                intent, received_at="2026-08-13T08:02:00Z"
            )
            expired = service.observe(
                account_id="hype-paper",
                expected_account_version=accepted.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-13T08:02:01Z",
                    available_at="2026-08-13T08:02:01Z",
                    source_sha256="6" * 64,
                    granularity="QUOTE",
                    path_status="ORDERED",
                    bid="56.16",
                    ask="56.17",
                    available_quantity="10",
                ),
            )
            self.assertEqual(
                ["EXPIRED", "CANCELLED", "CANCELLED", "CANCELLED"],
                [item.state for item in expired.orders],
            )
            self.assertEqual((), expired.positions)

    def test_later_same_episode_intent_links_root_without_new_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = FilePaperLedger(Path(temporary) / "paper")
            model = PaperCostModelV1(
                model_id="paper-cost-v1",
                maker_fee_bps="2",
                taker_fee_bps="5",
                market_impact_bps="0",
                funding_status="NOT_APPLICABLE",
                borrow_status="NOT_APPLICABLE",
            )
            service = PaperTradingService(
                ledger,
                cost_models=(model,),
                decision_authority=_DecisionAuthority(),
                require_execution_intent=True,
            )
            service.open_account(
                account_id="hype-paper",
                account_mode="CASH_SPOT",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="1",
                initial_balance="10000",
                opened_at="2026-08-13T08:00:00Z",
            )
            root_intent = self._bracket_intent(
                ledger_head=ledger.load_records("hype-paper")[-1].record_sha256
            )
            root_state = service.submit_intent(
                root_intent, received_at="2026-08-13T08:02:00Z"
            )
            root_record = next(
                record
                for record in ledger.load_records("hype-paper")
                if record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED"
            )

            continuation_document = _intent().to_dict()
            continuation_document.update(
                {
                    "intent_id": "hype-wait-2",
                    "expected_account_version": root_state.version,
                    "ledger_head_record_sha256": ledger.load_records(
                        "hype-paper"
                    )[-1].record_sha256,
                    "authored_at": "2026-08-13T08:02:01Z",
                    "valid_until": "2026-08-13T08:06:00Z",
                    "action": "WAIT",
                    "transition_id": "hype-wait-transition-2",
                    "tranche_id": None,
                    "role": "CASH_FLAT",
                    "pre_state": {"status": "FLAT", "signed_quantity": "0"},
                    "target_state": {"status": "FLAT", "signed_quantity": "0"},
                    "position_delta": {
                        "action": "WAIT",
                        "signed_quantity_change": "0",
                    },
                    "command": None,
                }
            )
            continuation = PaperExecutionIntentV1.from_dict(
                continuation_document
            )
            service.submit_intent(
                continuation, received_at=continuation.authored_at
            )

            records = ledger.load_records("hype-paper")
            self.assertEqual(
                1,
                sum(
                    record.event_type
                    == "STATIC_NO_TRANSITION_PREREGISTERED"
                    for record in records
                ),
            )
            linkage = records[-1].payload["static_comparator_linkage"]
            root = root_record.payload["comparator"]
            self.assertEqual("ONGOING_NOT_INDEPENDENT", linkage["status"])
            self.assertEqual(root["comparator_id"], linkage["root_comparator_id"])
            self.assertEqual(root_intent.intent_sha256, linkage["root_intent_sha256"])
            self.assertEqual(continuation.intent_sha256, linkage["current_intent_sha256"])
            self.assertEqual("NOT_COMPARABLE", linkage["comparison_status"])
            self.assertEqual(1, linkage["continuation_index"])
            self.assertEqual(
                service.load_account("hype-paper"),
                service.submit_intent(
                    continuation, received_at=continuation.authored_at
                ),
            )

    def test_write_once_agent_intent_gets_one_trusted_receipt_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cycles"
            times = iter(("2026-08-13T08:02:00Z", "2026-08-13T08:05:00Z"))
            mailbox = LocalPaperExecutionIntentMailbox(
                root, clock=lambda: next(times)
            )
            packet = {
                "cycle_id": "hype-decision-1",
                "paper_context": {
                    "paper_context_sha256": "3" * 64,
                    "ledger_head": {
                        "revision": 1,
                        "record_sha256": "4" * 64,
                    },
                    "account": {
                        "account_id": "hype-paper",
                        "owner_logical_agent_id": "HYPE_TRADER",
                        "owner_agent_generation": 1,
                        "permitted_symbol": "HYPE-USDT-SWAP",
                    },
                },
            }
            packet_sha256 = hashlib.sha256(canonical_bytes(packet)).hexdigest()
            write_once_json(
                root / "hype-decision-1" / "transport" / "agent-request.json",
                {"packet": packet, "packet_sha256": packet_sha256},
            )
            issued = mailbox.issue_request(
                "hype-decision-1",
                logical_agent_id="HYPE_TRADER",
                agent_generation=1,
                physical_task_id="hype-trader-task-g1",
                decision_sha256="1" * 64,
                issued_at="2026-08-13T08:00:30Z",
                valid_until="2026-08-13T08:06:00Z",
            )
            intent = replace(
                _intent(),
                execution_intent_request_sha256=issued.request_sha256,
                decision_request_sha256=packet_sha256,
            )
            write_once_json(
                mailbox.intent_path(intent.decision_cycle_id), intent.to_dict()
            )

            first = mailbox.receive(intent.decision_cycle_id)
            second = mailbox.receive(intent.decision_cycle_id)

            self.assertEqual("2026-08-13T08:02:00Z", first.received_at)
            self.assertEqual(first, second)
            self.assertEqual(intent, first.intent)

    def test_intent_binds_every_command_field_and_transition_semantics(self) -> None:
        intent = _intent()
        self.assertEqual(
            PaperExecutionIntentV1.from_dict(intent.to_dict()).to_dict(),
            intent.to_dict(),
        )
        self.assertEqual(len(intent.intent_sha256), 64)
        sell_intent = _intent(command=_command(side="SELL"))
        self.assertNotEqual(intent.intent_sha256, sell_intent.intent_sha256)
        mismatched_document = intent.to_dict()
        mismatched_document["intent_id"] = "different-intent-id"
        with self.assertRaisesRegex(PaperContractError, "command binding mismatch"):
            PaperExecutionIntentV1.from_dict(mismatched_document)

    def test_intent_required_service_rejects_direct_command_and_replays_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = FilePaperLedger(Path(temporary) / "paper")
            model = PaperCostModelV1(
                model_id="paper-cost-v1",
                maker_fee_bps="2",
                taker_fee_bps="5",
                market_impact_bps="3",
                funding_status="NOT_APPLICABLE",
                borrow_status="NOT_APPLICABLE",
            )
            service = PaperTradingService(
                ledger,
                cost_models=(model,),
                decision_authority=_DecisionAuthority(),
                require_execution_intent=True,
            )
            service.open_account(
                account_id="hype-paper",
                account_mode="CASH_SPOT",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="1",
                initial_balance="10000",
                opened_at="2026-08-13T08:00:00Z",
            )
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_EXECUTION_INTENT_REQUIRED"
            ):
                service.submit(_command())
            intent = _intent()
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_EXECUTION_INTENT_RECEIPT_TIME_REQUIRED"
            ):
                service.submit_intent(intent)
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_EXECUTION_INTENT_EXPIRED"
            ):
                service.submit_intent(
                    intent, received_at="2026-08-13T08:07:00Z"
                )
            trusted_received_at = "2026-08-13T08:02:00Z"
            state = service.submit_intent(
                intent, received_at=trusted_received_at
            )
            self.assertEqual(state.applied_command_ids, (intent.intent_id,))
            self.assertEqual(state.orders[0].state, "OPEN")
            self.assertEqual(state.orders[0].created_at, trusted_received_at)
            self.assertEqual(
                service.submit_intent(intent, received_at=trusted_received_at), state
            )
            records = ledger.load_records("hype-paper")
            accepted = next(
                item for item in records if item.event_type == "COMMAND_ACCEPTED"
            )
            self.assertEqual(
                accepted.payload["execution_intent"], intent.to_dict()
            )
            self.assertEqual(accepted.payload["accepted_at"], trusted_received_at)
            self.assertEqual(accepted.occurred_at, trusted_received_at)
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_EXECUTION_INTENT_RECEIPT_CONFLICT"
            ):
                service.submit_intent(
                    intent, received_at="2026-08-13T08:03:00Z"
                )

    def test_non_executable_wait_is_persisted_without_order_or_fill(self) -> None:
        wait_document = _intent().to_dict()
        wait_document.update(
            {
                "action": "WAIT",
                "role": "CASH_FLAT",
                "command": None,
                "target_state": {"status": "FLAT", "signed_quantity": "0"},
                "position_delta": {
                    "action": "WAIT",
                    "signed_quantity_change": "0",
                },
            }
        )
        wait = PaperExecutionIntentV1.from_dict(wait_document)
        forbidden_wait = _intent().to_dict()
        forbidden_wait["action"] = "WAIT"
        forbidden_wait["role"] = "CASH_FLAT"
        with self.assertRaisesRegex(
            PaperContractError, "non-executable action cannot carry"
        ):
            PaperExecutionIntentV1.from_dict(forbidden_wait)
        with tempfile.TemporaryDirectory() as temporary:
            ledger = FilePaperLedger(Path(temporary) / "paper")
            service = PaperTradingService(
                ledger,
                cost_models=(
                    PaperCostModelV1(
                        model_id="paper-cost-v1",
                        maker_fee_bps="2",
                        taker_fee_bps="5",
                        market_impact_bps="3",
                        funding_status="NOT_APPLICABLE",
                        borrow_status="NOT_APPLICABLE",
                    ),
                ),
                decision_authority=_DecisionAuthority(),
                require_execution_intent=True,
            )
            service.open_account(
                account_id="hype-paper",
                account_mode="CASH_SPOT",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="1",
                initial_balance="10000",
                opened_at="2026-08-13T08:00:00Z",
            )
            wait = replace(
                wait,
                ledger_head_record_sha256=ledger.load_records("hype-paper")[-1].record_sha256,
            )
            state = service.submit_intent(wait, received_at=wait.authored_at)
            self.assertEqual(2, state.version)
            self.assertEqual((), state.orders)
            self.assertEqual((), state.positions)
            self.assertEqual((), state.applied_command_ids)
            self.assertEqual(
                "INTENT_RECORDED", ledger.load_records("hype-paper")[-1].event_type
            )
            self.assertFalse(
                any(
                    record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED"
                    for record in ledger.load_records("hype-paper")
                )
            )
            self.assertEqual(
                state,
                service.submit_intent(wait, received_at=wait.authored_at),
            )


if __name__ == "__main__":
    unittest.main()
