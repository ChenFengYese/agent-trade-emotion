from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import inspect
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.test_theory_paper_v2_v332_experiment_runtime import (
    _V332_PACKAGE,
    _policy,
)
from tests.test_theory_paper_v2_v332_hype_data import (
    _BASE,
    _candles_body,
    _instrument_body,
    _json,
    _mark_body,
    _ms,
    _seal,
    _seal_core,
    _server_body,
)
from tests.test_theory_paper_v2_v332_offline_e2e import (
    _DECISION_BYTES,
    _DECISION_SHA,
    _FixedRuntimeClock,
    _seal_execution_book,
    _v332_request,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PaperBracketV1,
    PaperCommandV1,
    PaperExecutionIntentV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AttentionRequest,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_runtime import (
    V332AgentPaperActionPort,
    V332HypePaperRuntime,
    V332PaperRuntimeError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle import (
    paper_runtime as paper_runtime_module,
)
from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingError,
    PaperTradingService,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_intent_mailbox import (
    LocalPaperExecutionIntentMailbox,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.funding_scheduler import (
    AdmittedSliceFundingScheduler,
    FundingSchedulerError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    RUN_CLOSURE_RELATIVE_PATH,
    MarketCycleRuntimeError,
    build_market_cycle_runtime,
    initialize_v332_run,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_INSTRUMENT_ID,
    HYPE_OKX_PROFILE_ID,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    SERVER_TIME_PATH,
    FUNDING_RATE_HISTORY_PATH,
    ORDER_BOOK_PATH,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.v32_durable_json import write_once_json


class V332HypePaperRuntimeTests(unittest.TestCase):
    _THREAD_ID = "019ffb95-4195-7292-8a44-9870151a97f5"
    _GOAL_ID = f"codex-thread:{_THREAD_ID}"

    def setUp(self) -> None:
        host_identity = patch.dict(
            os.environ, {"CODEX_THREAD_ID": self._THREAD_ID}, clear=False
        )
        host_identity.start()
        self.addCleanup(host_identity.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime_root = Path(self.temporary.name) / "v332-paper-runtime"
        self.setup_cycle_id = f"{self.runtime_root.name}.paper-setup"
        policy = replace(
            _policy(self.runtime_root.name),
            starts_at="2026-08-13T12:00:00Z",
        )
        initialize_v332_run(
            self.runtime_root,
            theory_package=_V332_PACKAGE,
            experiment_policy=policy,
        )
        self.clock = _FixedRuntimeClock()
        self.runtime = build_market_cycle_runtime(
            runtime_root=self.runtime_root,
            theory_package=_V332_PACKAGE,
            expected_theory_identity=V332_THEORY_IDENTITY,
            clock=self.clock,
        )
        self.clock.current = "2026-08-13T12:00:11.500000+00:00"
        self.raw_store = FileRawCaptureStore(self.runtime_root)
        _seal_core(self.raw_store, cycle_id=self.setup_cycle_id)
        self.paper = V332HypePaperRuntime(
            self.runtime,
            setup_cycle_id=self.setup_cycle_id,
        )

    def _setup_account(self):
        return self.paper.setup()

    def _attention_request(
        self, request_id: str = "hype-goal-attention-001"
    ) -> AttentionRequest:
        registry = self.paper.status()["agent_registry"]
        return AttentionRequest(
            request_id=request_id,
            logical_agent_id=str(registry["logical_agent_id"]),
            agent_generation=int(registry["generation"]),
            continuity_nonce=str(registry["continuity_nonce"]),
            symbol=HYPE_OKX_INSTRUMENT_ID,
            mode="WAKE_AFTER",
            issued_at="2026-08-13T12:00:20+00:00",
            continue_until=None,
            earliest_wake_at="2026-08-13T12:00:30+00:00",
            latest_useful_at="2026-08-13T12:01:00+00:00",
            reason_summary="The Goal selected its own next observation window.",
            requested_focus="Re-evaluate the active HYPE paper hypothesis.",
            hypothesis_or_episode_ref="hype-attention-episode-001",
            position_and_open_order_ref=self.paper.account_id,
            data_cursor="hype-attention-cursor-001",
        )

    def test_goal_attention_uses_trusted_clock_and_exact_retry(self) -> None:
        self._setup_account()
        request = self._attention_request()
        self.clock.current = "2026-08-13T12:00:25.500000+00:00"
        with patch.object(
            self.runtime.controller_state,
            "trusted_now",
            wraps=self.runtime.controller_state.trusted_now,
        ) as trusted_now:
            first = self.runtime.submit_goal_attention_checkpoint(request)
            self.clock.current = "2026-08-13T12:00:26+00:00"
            duplicate = self.runtime.submit_goal_attention_checkpoint(request)
        self.assertEqual(1, trusted_now.call_count)
        self.assertEqual("2026-08-13T12:00:25.500000+00:00", first["accepted_at"])
        self.assertNotEqual(request.issued_at, first["accepted_at"])
        events = FileAttentionRepository(
            self.runtime_root / "attention"
        ).replay(request.logical_agent_id)
        payload = events[-1].payload
        self.assertEqual(request.to_dict(), dict(payload["request"]))
        self.assertEqual(self._GOAL_ID, payload["goal_checkpoint"]["physical_goal_id"])
        self.assertEqual(
            "CONTROLLER_TRUSTED_CLOCK",
            payload["goal_checkpoint"]["accepted_clock_source"],
        )
        self.assertEqual(first, duplicate)
        self.assertEqual(len(events), len(FileAttentionRepository(
            self.runtime_root / "attention"
        ).replay(request.logical_agent_id)))

    def test_goal_attention_wrong_goal_and_expired_are_zero_write(self) -> None:
        self._setup_account()
        request = self._attention_request()
        repository = FileAttentionRepository(self.runtime_root / "attention")
        before = repository.replay(request.logical_agent_id)
        with patch.dict(
            os.environ,
            {"CODEX_THREAD_ID": "11111111-1111-1111-1111-111111111111"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "REGISTRY_MISMATCH"
            ):
                self.runtime.submit_goal_attention_checkpoint(request)
        self.assertEqual(before, repository.replay(request.logical_agent_id))
        self.clock.current = "2026-08-13T12:01:00.000001+00:00"
        with self.assertRaisesRegex(
            MarketCycleRuntimeError, "ATTENTION_REQUEST_EXPIRED"
        ):
            self.runtime.submit_goal_attention_checkpoint(request)
        self.assertEqual(before, repository.replay(request.logical_agent_id))

    def test_closed_run_rejects_goal_attention_without_writes(self) -> None:
        self._setup_account()
        request = self._attention_request()
        repository = FileAttentionRepository(self.runtime_root / "attention")
        before = repository.replay(request.logical_agent_id)
        self.runtime.close_run()
        with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
            self.runtime.submit_goal_attention_checkpoint(request)
        self.assertEqual(before, repository.replay(request.logical_agent_id))

    def test_closed_run_rejects_setup_and_direct_prepare_without_writes(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-closed-paper-001")
        self.runtime.close_run()
        records_before = self.paper._ledger.load_records(self.paper.account_id)
        intent_request = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "paper-execution-intent-request.json"
        )
        self.assertFalse(intent_request.exists())
        with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
            self.paper.setup()
        with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
            V332AgentPaperActionPort(self.paper).prepare_paper_action(
                decision_cycle_id=cycle_id
            )
        self.assertEqual(
            self.paper._ledger.load_records(self.paper.account_id), records_before
        )
        self.assertFalse(intent_request.exists())

    def test_close_rejects_live_incomplete_paper_intent_without_marker(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-close-live-intent")
        V332AgentPaperActionPort(self.paper).prepare_paper_action(
            decision_cycle_id=cycle_id
        )
        before = {
            path.relative_to(self.runtime_root): (
                None if path.is_dir() else path.read_bytes()
            )
            for path in self.runtime_root.rglob("*")
        }
        with patch.object(
            self.runtime.controller_state,
            "status",
            return_value={"events": {}, "worker_dispatches": {}},
        ):
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_CLOSE_LIVE_PAPER_INTENT"
            ):
                self.runtime.close_run()
        self.assertFalse(
            (self.runtime_root / RUN_CLOSURE_RELATIVE_PATH).exists()
        )
        self.assertEqual(
            {
                path.relative_to(self.runtime_root): (
                    None if path.is_dir() else path.read_bytes()
                )
                for path in self.runtime_root.rglob("*")
            },
            before,
        )

    def test_close_allows_expired_incomplete_intent_without_action(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-close-expired-intent")
        prepared = V332AgentPaperActionPort(self.paper).prepare_paper_action(
            decision_cycle_id=cycle_id
        )
        transport = self.runtime_root / "cycles" / cycle_id / "transport"
        records_before = self.paper._ledger.load_records(self.paper.account_id)
        self.clock.current = (
            datetime.fromisoformat(str(prepared["valid_until"]))
            + timedelta(microseconds=1)
        ).isoformat()
        with patch.object(
            self.runtime.controller_state,
            "status",
            return_value={"events": {}, "worker_dispatches": {}},
        ):
            self.assertEqual(self.runtime.close_run().status, "CLOSED")
        self.assertEqual(
            self.paper._ledger.load_records(self.paper.account_id), records_before
        )
        self.assertFalse((transport / "paper-execution-intent.json").exists())
        self.assertFalse(
            (transport / "paper-action-execution-receipt.json").exists()
        )

    def test_close_allows_completed_action_and_preserves_open_order(self) -> None:
        cycle_id, _, _ = self._prepare_direct_paper_action()
        self.clock.current = "2026-08-13T12:00:28.500000+00:00"
        V332AgentPaperActionPort(self.paper).commit_paper_action(
            decision_cycle_id=cycle_id
        )
        account_before = self.paper._require_account()
        self.assertTrue(account_before.orders)
        with patch.object(
            self.runtime.controller_state,
            "status",
            return_value={"events": {}, "worker_dispatches": {}},
        ):
            self.assertEqual(self.runtime.close_run().status, "CLOSED")
        account_after = self.paper._require_account()
        self.assertEqual(account_after, account_before)

    def _seal_post_account_core(self, cycle_id: str) -> None:
        """Capture the four independent public routes after account setup."""

        server_offset = 12
        instrument_offset = 15
        mark_offset = 18
        candles_offset = 21
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="server-time",
            component_id="SERVER_TIME",
            path=SERVER_TIME_PATH,
            query={},
            body=_server_body(),
            start_offset=server_offset,
        )
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="instrument",
            component_id="INSTRUMENT",
            path=INSTRUMENT_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "instType": "SWAP"},
            body=_instrument_body(),
            start_offset=instrument_offset,
        )
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="mark-price",
            component_id="MARK_PRICE",
            path=MARK_PRICE_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "instType": "SWAP"},
            body=_mark_body(),
            start_offset=mark_offset,
        )
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="closed-candles-15m",
            component_id="CLOSED_CANDLES_15M",
            path=CLOSED_CANDLES_15M_PATH,
            query={
                "after": _ms(_BASE),
                "bar": "15m",
                "instId": HYPE_OKX_INSTRUMENT_ID,
                "limit": "96",
            },
            body=_candles_body(),
            start_offset=candles_offset,
        )

    def _seal_post_account_with_funding(
        self, cycle_id: str, *, moments: tuple[datetime, ...]
    ) -> None:
        """Seal one complete core plus caller-independent official history."""

        self._seal_post_account_core(cycle_id)
        rows = [
            {
                "instType": "SWAP",
                "instId": HYPE_OKX_INSTRUMENT_ID,
                "fundingRate": "0.0001",
                "fundingTime": _ms(moment),
                "realizedRate": "0.0001",
            }
            for moment in moments
        ]
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="funding-rate-history",
            component_id="FUNDING_RATE_HISTORY",
            path=FUNDING_RATE_HISTORY_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "limit": "10"},
            body=_json({"code": "0", "msg": "", "data": rows}),
            start_offset=30,
        )

    def _seal_decision(
        self,
        cycle_id: str = "hype-decision-001",
        *,
        seal_plan: bool = True,
    ) -> str:
        request = replace(
            _v332_request(cycle_id),
            requested_at="2026-08-13T12:00:11.750000+00:00",
        )
        self.runtime.service.create(request)
        self._seal_post_account_core(cycle_id)
        self.clock.current = "2026-08-13T12:00:24+00:00"
        self.assertEqual(
            self.runtime.service.run_next(cycle_id).state.stage,
            "INPUT_SEALED",
        )
        pending = self.runtime.service.run_next(cycle_id)
        self.assertFalse(pending.changed)
        self.assertEqual(pending.pending_reason, "AGENT_DELIVERY_PENDING")
        self.clock.current = "2026-08-13T12:00:24.200000+00:00"
        self.assertEqual(
            "CREATED",
            self.runtime.service.deliver_agent_decision(
                cycle_id, _DECISION_BYTES
            ),
        )
        self.assertEqual(
            self.runtime.service.run_next(cycle_id).state.stage,
            "ANALYZED",
        )
        if seal_plan:
            self.assertEqual(
                self.runtime.service.run_next(cycle_id).state.stage,
                "PLAN_SEALED",
            )
        return cycle_id

    def _intent(
        self, cycle_id: str, *, intent_request_sha256: str
    ) -> PaperExecutionIntentV1:
        request = loads_json_strict(
            (
                self.runtime_root
                / "cycles"
                / cycle_id
                / "transport"
                / "agent-request.json"
            ).read_bytes()
        )
        paper_context = request["packet"]["paper_context"]
        command = PaperCommandV1(
            command_id="hype-intent-open-001",
            account_id=self.paper.account_id,
            logical_agent_id=self.paper.logical_agent_id,
            agent_generation=1,
            decision_cycle_id=cycle_id,
            decision_sha256=_DECISION_SHA,
            expected_account_version=1,
            symbol="HYPE-USDT-SWAP",
            command_type="MARKET",
            side="BUY",
            quantity="2",
            limit_price=None,
            trigger_price=None,
            target_order_id=None,
            reduce_only=False,
            time_in_force="GTC",
            submitted_at="2026-08-13T12:00:26+00:00",
            expires_at=None,
            cost_model_id="v332-pilot-modeled-costs-v1",
        )
        return PaperExecutionIntentV1(
            intent_id=command.command_id,
            execution_intent_request_sha256=intent_request_sha256,
            decision_request_sha256=request["packet_sha256"],
            paper_context_sha256=paper_context["paper_context_sha256"],
            ledger_head_record_sha256=paper_context["ledger_head"][
                "record_sha256"
            ],
            decision_cycle_id=cycle_id,
            decision_sha256=_DECISION_SHA,
            account_id=self.paper.account_id,
            logical_agent_id=self.paper.logical_agent_id,
            agent_generation=1,
            expected_account_version=1,
            symbol="HYPE-USDT-SWAP",
            authored_at="2026-08-13T12:00:26+00:00",
            valid_until="2026-08-13T12:01:00+00:00",
            action="OPEN",
            episode_id="hype-episode-001",
            transition_id="hype-transition-001",
            tranche_id="hype-tranche-001",
            role="TACTICAL",
            pre_state={"signed_quantity": "0"},
            target_state={"signed_quantity": "2"},
            position_delta={"signed_quantity_change": "2"},
            evidence_delta="The sealed HYPE path activated the bounded probe.",
            activation="Exact decision and paper head remain valid.",
            hard_invalidation="The Agent cancels or the risk boundary fails.",
            risk_budget={
                "maximum_loss": "50",
                "notional_cap": "1000",
                "max_observed_drawdown": "500",
            },
            command=command,
        )

    def _mailbox(self) -> LocalPaperExecutionIntentMailbox:
        return LocalPaperExecutionIntentMailbox(
            self.runtime_root / "cycles",
            clock=lambda: "2026-08-13T12:00:27+00:00",
        )

    def _short_bracket_intent(
        self,
        cycle_id: str,
        *,
        intent_request_sha256: str,
        stop_price: str = "43.125",
        maximum_loss: str = "50",
    ) -> PaperExecutionIntentV1:
        base = self._intent(
            cycle_id, intent_request_sha256=intent_request_sha256
        )
        assert base.command is not None
        common = {
            "account_id": base.account_id,
            "logical_agent_id": base.logical_agent_id,
            "agent_generation": base.agent_generation,
            "decision_cycle_id": base.decision_cycle_id,
            "decision_sha256": base.decision_sha256,
            "expected_account_version": base.expected_account_version,
            "symbol": base.symbol,
            "submitted_at": base.authored_at,
            "expires_at": None,
            "cost_model_id": base.command.cost_model_id,
        }
        entry = PaperCommandV1(
            command_id="hype-short-bracket-001",
            command_type="LIMIT",
            side="SELL",
            quantity="2",
            limit_price="43.1",
            trigger_price=None,
            target_order_id=None,
            reduce_only=False,
            time_in_force="GTC",
            **common,
        )
        stop = PaperCommandV1(
            command_id="hype-short-bracket-stop-001",
            command_type="STOP_LOSS",
            side="BUY",
            quantity="2",
            limit_price=None,
            trigger_price=stop_price,
            target_order_id=None,
            reduce_only=True,
            time_in_force="GTC",
            **common,
        )
        target = PaperCommandV1(
            command_id="hype-short-bracket-target-001",
            command_type="TAKE_PROFIT",
            side="BUY",
            quantity="2",
            limit_price=None,
            trigger_price="43",
            target_order_id=None,
            reduce_only=True,
            time_in_force="GTC",
            **common,
        )
        bracket = PaperBracketV1(
            bracket_id=entry.command_id,
            entry=entry,
            protective_stop=stop,
            take_profits=(target,),
        )
        return replace(
            base,
            intent_id=entry.command_id,
            transition_id="hype-short-bracket-transition-001",
            tranche_id="hype-short-bracket-tranche-001",
            target_state={"signed_quantity": "-2"},
            position_delta={"signed_quantity_change": "-2"},
            risk_budget={
                "maximum_loss": maximum_loss,
                "notional_cap": "1000",
                "max_observed_drawdown": "500",
            },
            command=entry,
            bracket=bracket,
            wire_schema_version="1.3.0",
        )

    def _issue_intent_request(self, cycle_id: str):
        self.clock.current = "2026-08-13T12:00:25.500000+00:00"
        mailbox = self._mailbox()
        prepared = V332AgentPaperActionPort(
            self.paper
        ).prepare_paper_action(
            decision_cycle_id=cycle_id
        )
        document = loads_json_strict(
            mailbox.intent_request_path(cycle_id).read_bytes()
        )
        issued = SimpleNamespace(
            document=document,
            request_sha256=prepared["intent_request_sha256"],
        )
        return mailbox, issued

    def _commit_intent(self, cycle_id: str):
        earliest_receipt = datetime.fromisoformat(
            "2026-08-13T12:00:27+00:00"
        )
        if datetime.fromisoformat(self.clock.current) < earliest_receipt:
            self.clock.current = earliest_receipt.isoformat()
        V332AgentPaperActionPort(self.paper).commit_paper_action(
            decision_cycle_id=cycle_id
        )
        return self.paper._require_account()

    @staticmethod
    def _write_intent(
        mailbox: LocalPaperExecutionIntentMailbox,
        intent: PaperExecutionIntentV1,
    ) -> None:
        write_once_json(
            mailbox.intent_path(intent.decision_cycle_id), intent.to_dict()
        )

    def _prepare_direct_paper_action(
        self,
        *,
        intent_transform=lambda value: value,
    ):
        self._setup_account()
        cycle_id = self._seal_decision(seal_plan=False)
        self.assertEqual(
            "PLAN_SEALED",
            self.runtime.service.run_next(cycle_id).state.stage,
        )
        prepared = V332AgentPaperActionPort(
            self.paper
        ).prepare_paper_action(
            decision_cycle_id=cycle_id
        )
        intent_mailbox = self._mailbox()
        issued = loads_json_strict(
            intent_mailbox.intent_request_path(cycle_id).read_bytes()
        )
        intent = self._intent(
            cycle_id,
            intent_request_sha256=hashlib.sha256(
                canonical_bytes(issued) + b"\n"
            ).hexdigest(),
        )
        self._write_intent(intent_mailbox, intent_transform(intent))
        return cycle_id, prepared, intent_mailbox

    def test_setup_is_after_admitted_slice_and_has_no_external_order_surface(self) -> None:
        before = self.paper.status()
        self.assertIsNone(before["account"])
        self.assertIsNone(before["agent_registry"])

        account = self.paper.setup()
        self.assertEqual(self.clock.current, account.last_fact_at)
        self.assertEqual(account.account_mode, "LINEAR_PERP")
        self.assertEqual(
            account.instrument_spec.parameter_status, "OBSERVED_RAW_BOUND"
        )
        status = self.paper.status()
        self.assertFalse(status["external_orders_supported"])
        self.assertFalse(self.paper.external_orders_supported)
        self.assertEqual(status["ledger_revision"], 1)
        self.assertEqual(
            status["agent_registry"]["logical_agent_id"],
            "HYPE_CAPABILITY_TRADER",
        )
        self.assertEqual(
            self._GOAL_ID, status["agent_registry"]["physical_task_id"]
        )
        self.assertRegex(
            status["agent_registry"]["continuity_nonce"],
            r"^v332-goal-g1-[0-9a-f]{64}$",
        )
        self.assertEqual({}, inspect.signature(self.paper.setup).parameters)
        self.assertEqual(["V332PaperRuntimeError"], paper_runtime_module.__all__)
        self.assertEqual(
            {"decision_cycle_id"},
            set(
                inspect.signature(
                    V332AgentPaperActionPort(self.paper).commit_paper_action
                ).parameters
            ),
        )
        self.assertEqual(
            {"cycle_id"},
            set(
                inspect.signature(
                    V332AgentPaperActionPort(self.paper).process_market_cycle
                ).parameters
            ),
        )
        self.assertEqual(
            {"decision_cycle_id"},
            set(
                inspect.signature(
                    V332AgentPaperActionPort(self.paper).prepare_paper_action
                ).parameters
            ),
        )
        for removed in (
            "issue_attention_decision_request",
            "receive_and_bind_attention",
            "issue_execution_intent_request",
            "receive_and_submit_intent",
            "materialize_paper_action_worker",
            "observe_latest",
            "advance_funding",
            "_require_decision_worker_identity",
            "_persist_decision_attention",
            "_validate_decision_attention",
            "_issue_attention_decision_request",
            "_receive_and_bind_attention",
            "_receive_and_submit_intent",
            "_attention_mailbox",
        ):
            self.assertFalse(hasattr(self.paper, removed), removed)
        forbidden = {
            "approve",
            "action",
            "side",
            "quantity",
            "price",
            "account_id",
            "valid_until",
            "mailbox",
            "path",
            "execution_ref",
            "override",
            "granularity",
        }
        self.assertTrue(
            forbidden.isdisjoint(
                inspect.signature(
                    V332AgentPaperActionPort(self.paper).commit_paper_action
                ).parameters
            )
        )
        self.assertTrue(
            forbidden.isdisjoint(
                inspect.signature(
                    V332AgentPaperActionPort(self.paper).process_market_cycle
                ).parameters
            )
        )

    def test_setup_retry_is_idempotent_and_goal_change_is_zero_write(self) -> None:
        first = self._setup_account()
        self.clock.current = "2026-08-13T12:00:12+00:00"
        retried = self._setup_account()
        self.assertEqual(first, retried)
        self.assertEqual(1, self.paper.status()["ledger_revision"])

        with (
            patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": "11111111-1111-1111-1111-111111111111"},
                clear=False,
            ),
            self.assertRaisesRegex(
                V332PaperRuntimeError, "EXISTING_GOAL_BINDING_MISMATCH"
            ),
        ):
            self.paper.setup()
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_direct_runtime_requires_host_identity_before_any_write(self) -> None:
        port = V332AgentPaperActionPort(self.paper)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                V332PaperRuntimeError, "CODEX_THREAD_ID_REQUIRED"
            ):
                self.paper.setup()
            for mutate, keyword in (
                (
                    port.prepare_paper_action,
                    {"decision_cycle_id": "decision-1"},
                ),
                (port.commit_paper_action, {"decision_cycle_id": "decision-1"}),
                (port.process_market_cycle, {"cycle_id": "market-cycle-1"}),
            ):
                with self.subTest(mutate=mutate.__name__), self.assertRaisesRegex(
                    V332PaperRuntimeError, "CODEX_THREAD_ID_REQUIRED"
                ):
                    mutate(**keyword)

        status = self.paper.status()
        self.assertIsNone(status["agent_registry"])
        self.assertEqual(0, status["ledger_revision"])

    def test_direct_runtime_mutations_require_the_registered_host_goal(self) -> None:
        self._setup_account()
        port = V332AgentPaperActionPort(self.paper)
        ledger_revision = self.paper.status()["ledger_revision"]

        with patch.dict(
            os.environ,
            {"CODEX_THREAD_ID": "11111111-1111-1111-1111-111111111111"},
            clear=False,
        ):
            for mutate, keyword in (
                (
                    port.prepare_paper_action,
                    {"decision_cycle_id": "decision-1"},
                ),
                (port.commit_paper_action, {"decision_cycle_id": "decision-1"}),
                (port.process_market_cycle, {"cycle_id": "market-cycle-1"}),
            ):
                with self.subTest(mutate=mutate.__name__), self.assertRaisesRegex(
                    V332PaperRuntimeError, "CALLER_GOAL_MISMATCH"
                ):
                    mutate(**keyword)

        self.assertEqual(ledger_revision, self.paper.status()["ledger_revision"])
        self.assertFalse((self.runtime_root / "cycles" / "decision-1").exists())

    def test_exact_direct_intent_and_admitted_quote_close_the_local_loop(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision()
        mailbox, issued = self._issue_intent_request(cycle_id)
        intent = self._intent(
            cycle_id, intent_request_sha256=issued.request_sha256
        )
        self._write_intent(mailbox, intent)

        submitted = self._commit_intent(cycle_id)
        self.assertEqual(submitted.orders[0].state, "OPEN")
        self.assertEqual(self.paper.status()["ledger_revision"], 3)

        execution_cycle = "hype-execution-quote-001"
        _seal_execution_book(self.raw_store, cycle_id=execution_cycle)
        processed = V332AgentPaperActionPort(
            self.paper
        ).process_market_cycle(cycle_id=execution_cycle)
        self.assertEqual("QUOTE", processed["observation_kind"])
        self.assertEqual("UNKNOWN", processed["funding"]["status"])
        self.assertEqual(
            "OFFICIAL_FUNDING_HISTORY_UNAVAILABLE",
            processed["funding"]["reason"],
        )
        observed = self.paper._require_account()
        self.assertEqual(observed.orders[0].state, "FILLED")
        self.assertEqual(observed.positions[0].quantity, "2")
        self.assertGreater(len(self.paper.status()["ledger_head_record_sha256"]), 0)

    def test_direct_prepare_and_commit_need_no_controller_worker_record(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-decision-no-worker-record")
        controller_state_path = self.runtime_root / "controller" / "wake-dispatch.json"
        controller_state_path.unlink()

        prepared = V332AgentPaperActionPort(
            self.paper
        ).prepare_paper_action(decision_cycle_id=cycle_id)
        mailbox = self._mailbox()
        intent = self._intent(
            cycle_id,
            intent_request_sha256=str(prepared["intent_request_sha256"]),
        )
        self._write_intent(mailbox, intent)
        self.clock.current = "2026-08-13T12:00:28.500000+00:00"
        completed = V332AgentPaperActionPort(
            self.paper
        ).commit_paper_action(decision_cycle_id=cycle_id)

        self.assertEqual("COMMITTED", completed["status"])
        binding_path = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "decision-goal-binding.json"
        )
        binding = loads_json_strict(binding_path.read_bytes())
        self.assertEqual(
            hashlib.sha256(binding_path.read_bytes()).hexdigest(),
            prepared["decision_goal_binding_sha256"],
        )
        self.assertEqual(
            {
                "request.json",
                "artifacts/InputSnapshot.json",
                "transport/agent-request.json",
                "transport/agent-delivery.json",
                "artifacts/HypothesisRecord.json",
                "artifacts/BehaviorPlan.json",
                "transport/paper-execution-intent-request.json",
            },
            {
                binding["cycle_request_relative_path"],
                binding["input_snapshot_relative_path"],
                binding["agent_request_relative_path"],
                binding["agent_delivery_relative_path"],
                binding["hypothesis_record_relative_path"],
                binding["behavior_plan_relative_path"],
                binding["intent_request_relative_path"],
            },
        )
        self.assertEqual(
            prepared["decision_goal_binding_sha256"],
            completed["decision_goal_binding_sha256"],
        )
        self.assertFalse(controller_state_path.exists())

    def test_direct_commit_rejects_registry_identity_drift(self) -> None:
        cycle_id, _, _ = self._prepare_direct_paper_action()
        registry = self.paper._sessions.current(self.paper.logical_agent_id)
        with patch.object(
            self.paper._sessions,
            "current",
            return_value=replace(
                registry, physical_task_id="codex-thread:tampered-goal"
            ),
        ):
            with self.assertRaisesRegex(
                V332PaperRuntimeError,
                "CALLER_GOAL_MISMATCH",
            ):
                V332AgentPaperActionPort(self.paper).commit_paper_action(
                    decision_cycle_id=cycle_id
                )
        self.assertFalse(self._mailbox().receipt_path(cycle_id).exists())
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_wait_intent_is_durable_without_creating_an_order(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision()
        mailbox, issued = self._issue_intent_request(cycle_id)
        executable = self._intent(
            cycle_id, intent_request_sha256=issued.request_sha256
        )
        wait = replace(
            executable,
            intent_id="hype-intent-wait-001",
            action="WAIT",
            transition_id="hype-transition-wait-001",
            tranche_id=None,
            role="CASH_FLAT",
            target_state={"signed_quantity": "0"},
            position_delta={"signed_quantity_change": "0"},
            command=None,
        )
        self._write_intent(mailbox, wait)

        recorded = self._commit_intent(cycle_id)

        self.assertEqual(2, recorded.version)
        self.assertEqual((), recorded.orders)
        self.assertEqual((), recorded.positions)
        self.assertEqual((), recorded.applied_command_ids)
        self.assertEqual(2, self.paper.status()["ledger_revision"])
        self.assertEqual(
            recorded,
            self._commit_intent(cycle_id),
        )

    def test_intent_request_is_not_issued_before_behavior_plan_is_sealed(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision(seal_plan=False)
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "PLAN_NOT_SEALED"
        ):
            self._issue_intent_request(cycle_id)
        self.assertFalse(
            self._mailbox().intent_request_path(cycle_id).exists()
        )

    def test_policy_risk_cap_rejects_before_ledger_mutation(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision()
        mailbox, issued = self._issue_intent_request(cycle_id)
        intent = replace(
            self._intent(
                cycle_id, intent_request_sha256=issued.request_sha256
            ),
            risk_budget={
                "maximum_loss": "101",
                "notional_cap": "1000",
                "max_observed_drawdown": "500",
            },
        )
        self._write_intent(mailbox, intent)
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "RISK_POLICY_EXCEEDED"
        ):
            self._commit_intent(cycle_id)
        self.assertEqual(self.paper.status()["ledger_revision"], 1)

    def test_recomputed_notional_and_unbounded_short_reject_before_mutation(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision()
        mailbox, issued = self._issue_intent_request(cycle_id)
        too_small = replace(
            self._intent(cycle_id, intent_request_sha256=issued.request_sha256),
            risk_budget={
                "maximum_loss": "50",
                "notional_cap": "1",
                "max_observed_drawdown": "500",
            },
        )
        self._write_intent(mailbox, too_small)
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "RECOMPUTED_NOTIONAL_CAP_EXCEEDED"
        ):
            self._commit_intent(cycle_id)
        self.assertEqual(1, self.paper.status()["ledger_revision"])

        short_cycle = self._seal_decision("hype-decision-short-risk")
        short_mailbox, short_issued = self._issue_intent_request(short_cycle)
        long_intent = self._intent(
            short_cycle, intent_request_sha256=short_issued.request_sha256
        )
        assert long_intent.command is not None
        short_command = replace(
            long_intent.command,
            command_id="hype-intent-short-001",
            decision_cycle_id=short_cycle,
            side="SELL",
            submitted_at="2026-08-13T12:00:26+00:00",
        )
        short = replace(
            long_intent,
            intent_id=short_command.command_id,
            decision_cycle_id=short_cycle,
            transition_id="hype-transition-short-001",
            tranche_id="hype-tranche-short-001",
            target_state={"signed_quantity": "-2"},
            position_delta={"signed_quantity_change": "-2"},
            command=short_command,
        )
        self._write_intent(short_mailbox, short)
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "UNBOUNDED_SHORT_RISK_FORBIDDEN"
        ):
            self._commit_intent(short_cycle)
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_linear_perp_short_bracket_is_atomic_held_and_forward_only(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-short-bracket-runtime")
        mailbox, issued = self._issue_intent_request(cycle_id)
        intent = self._short_bracket_intent(
            cycle_id, intent_request_sha256=issued.request_sha256
        )
        self._write_intent(mailbox, intent)

        accepted = self._commit_intent(cycle_id)
        self.assertEqual(
            ["OPEN", "HELD", "HELD"],
            [item.state for item in accepted.orders],
        )
        self.assertEqual(
            [item.command_id for item in intent.bracket.commands],
            list(accepted.applied_command_ids),
        )

        entry_cycle = "hype-short-bracket-entry-quote"
        _seal_execution_book(self.raw_store, cycle_id=entry_cycle)
        entry_filled = self.paper._observe_latest(
            cycle_id=entry_cycle, granularity="QUOTE"
        )
        self.assertEqual("-2", entry_filled.positions[0].quantity)
        self.assertEqual(
            ["FILLED", "OPEN", "OPEN"],
            [item.state for item in entry_filled.orders],
        )

        forward_cycle = "hype-short-bracket-forward-stop-quote"
        _seal_core(self.raw_store, cycle_id=forward_cycle)
        _seal(
            self.raw_store,
            cycle_id=forward_cycle,
            capture_id="order-book",
            component_id="ORDER_BOOK",
            path=ORDER_BOOK_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "sz": "20"},
            body=_json(
                {
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "asks": [["43.13", "10", "0", "1"]],
                            "bids": [["43.12", "8", "0", "1"]],
                            "ts": _ms(_BASE + timedelta(seconds=70)),
                            "seqId": "102",
                            "prevSeqId": "101",
                        }
                    ],
                }
            ),
            start_offset=70,
        )
        stopped = self.paper._observe_latest(
            cycle_id=forward_cycle, granularity="QUOTE"
        )
        self.assertEqual("0", stopped.positions[0].quantity)
        self.assertEqual(
            ["FILLED", "FILLED", "CANCELLED"],
            [item.state for item in stopped.orders],
        )

    def test_short_bracket_modeled_loss_over_policy_is_zero_write(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-short-bracket-over-policy")
        mailbox, issued = self._issue_intent_request(cycle_id)
        intent = self._short_bracket_intent(
            cycle_id,
            intent_request_sha256=issued.request_sha256,
            stop_price="600",
            maximum_loss="100",
        )
        self._write_intent(mailbox, intent)

        with self.assertRaisesRegex(
            V332PaperRuntimeError,
            "BRACKET_MODELED_LOSS_CAP_EXCEEDED",
        ):
            self._commit_intent(cycle_id)
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_action_window_rejects_request_and_receipt_at_outcome_hard_stop(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision()
        plan = self.runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
        mailbox = self._mailbox()
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "ACTION_WINDOW_EXCEEDS_HARD_STOP"
        ):
            self.paper._issue_execution_intent_request(
                mailbox,
                decision_cycle_id=cycle_id,
                valid_until=(
                    datetime.fromisoformat(plan["outcome_due_at"])
                    + timedelta(seconds=1)
                ).isoformat(),
            )
        self.assertFalse(mailbox.intent_request_path(cycle_id).exists())

        mailbox, issued = self._issue_intent_request(cycle_id)
        self._write_intent(
            mailbox,
            self._intent(
                cycle_id, intent_request_sha256=issued.request_sha256
            ),
        )
        self.clock.current = plan["outcome_due_at"]
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "ACTION_WINDOW_EXPIRED"
        ):
            self._commit_intent(cycle_id)
        self.assertFalse(mailbox.receipt_path(cycle_id).exists())
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_direct_prepare_owns_time_and_retry_reuses_sealed_time(self) -> None:
        self.assertNotIn(
            "issued_at",
            inspect.signature(
                V332AgentPaperActionPort(self.paper).prepare_paper_action
            ).parameters,
        )
        self._setup_account()
        cycle_id = self._seal_decision(seal_plan=False)
        self.assertEqual(
            "PLAN_SEALED",
            self.runtime.service.run_next(cycle_id).state.stage,
        )

        self.clock.current = "2026-08-13T12:00:25.500000+00:00"
        trusted_now = self.runtime.controller_state.trusted_now
        with patch.object(
            self.runtime.controller_state,
            "trusted_now",
            side_effect=trusted_now,
        ) as intent_clock:
            first_intent = V332AgentPaperActionPort(
                self.paper
            ).prepare_paper_action(
                decision_cycle_id=cycle_id
            )
        self.assertEqual(1, intent_clock.call_count)
        self.assertEqual(
            "2026-08-13T12:00:25.500000+00:00",
            first_intent["issued_at"],
        )

        plan = self.runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
        request_path = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "paper-execution-intent-request.json"
        )
        binding_path = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "decision-goal-binding.json"
        )
        sealed_request = request_path.read_bytes()
        sealed_binding = binding_path.read_bytes()
        self.clock.current = plan["outcome_due_at"]
        trusted_now = self.runtime.controller_state.trusted_now
        with patch.object(
            self.runtime.controller_state,
            "trusted_now",
            side_effect=trusted_now,
        ) as retry_clock:
            retried_intent = V332AgentPaperActionPort(
                self.paper
            ).prepare_paper_action(
                decision_cycle_id=cycle_id
            )
        self.assertEqual(0, retry_clock.call_count)
        self.assertEqual(first_intent, retried_intent)
        self.assertEqual(sealed_request, request_path.read_bytes())
        self.assertEqual(sealed_binding, binding_path.read_bytes())

    def test_direct_first_prepare_after_hard_stop_is_zero_write(self) -> None:
        self._setup_account()
        cycle_id = self._seal_decision("hype-decision-expired-first-prepare")
        plan = self.runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
        self.clock.current = plan["outcome_due_at"]

        with self.assertRaisesRegex(
            V332PaperRuntimeError, "ACTION_WINDOW_EXPIRED"
        ):
            V332AgentPaperActionPort(self.paper).prepare_paper_action(
                decision_cycle_id=cycle_id
            )

        transport_root = self.runtime_root / "cycles" / cycle_id / "transport"
        self.assertFalse(
            (transport_root / "paper-execution-intent-request.json").exists()
        )
        self.assertFalse(
            (transport_root / "decision-goal-binding.json").exists()
        )

    def test_persistent_goal_prepares_and_commits_without_paper_worker(self) -> None:
        cycle_id, prepared, _ = self._prepare_direct_paper_action()
        self.assertEqual("PREPARED", prepared["status"])
        self.assertEqual(
            self._GOAL_ID,
            prepared["physical_goal_id"],
        )
        self.assertFalse(
            (
                self.runtime_root
                / "cycles"
                / cycle_id
                / "transport"
                / "attention-decision.json"
            ).exists()
        )
        self.clock.current = "2026-08-13T12:00:28.500000+00:00"
        completed = V332AgentPaperActionPort(
            self.paper
        ).commit_paper_action(
            decision_cycle_id=cycle_id,
        )
        self.assertEqual("COMMITTED", completed["status"])
        self.assertEqual("2.1.0", completed["schema_version"])
        self.assertEqual(
            prepared["decision_goal_binding_sha256"],
            completed["decision_goal_binding_sha256"],
        )
        self.assertEqual(
            prepared["physical_goal_id"], completed["physical_goal_id"]
        )
        execution_receipt = loads_json_strict(
            (
                self.runtime_root
                / "cycles"
                / cycle_id
                / "transport"
                / "paper-action-execution-receipt.json"
            ).read_bytes()
        )
        self.assertNotIn("dispatch_id", execution_receipt)
        self.assertNotIn("attention_receipt_sha256", execution_receipt)
        self.assertEqual(
            self.paper.status()["ledger_head_record_sha256"],
            execution_receipt["ledger_after_head_record_sha256"],
        )
        self.assertEqual(
            completed,
            V332AgentPaperActionPort(self.paper).commit_paper_action(
                decision_cycle_id=cycle_id
            ),
        )

    def test_idle_persistent_goal_can_resume_and_use_direct_port(self) -> None:
        """Host-level rest must not invalidate the durable trading Goal."""

        cycle_id, _, _ = self._prepare_direct_paper_action()
        registry = self.paper._sessions.current(self.paper.logical_agent_id)
        with patch.object(
            self.paper._sessions,
            "current",
            return_value=replace(registry, status="IDLE"),
        ):
            self.clock.current = "2026-08-13T12:00:28.500000+00:00"
            completed = V332AgentPaperActionPort(
                self.paper
            ).commit_paper_action(decision_cycle_id=cycle_id)
        self.assertEqual("COMMITTED", completed["status"])
        self.assertEqual(
            registry.physical_task_id, completed["physical_goal_id"]
        )

    def test_direct_commit_rejects_decision_goal_binding_tamper(self) -> None:
        cycle_id, _, _ = self._prepare_direct_paper_action()
        binding_path = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "decision-goal-binding.json"
        )
        binding = loads_json_strict(binding_path.read_bytes())
        binding_path.write_bytes(
            canonical_bytes(
                {**binding, "physical_goal_id": "codex-thread:tampered-goal"}
            )
            + b"\n"
        )

        with self.assertRaisesRegex(
            V332PaperRuntimeError, "DECISION_GOAL_BINDING_MISMATCH"
        ):
            V332AgentPaperActionPort(self.paper).commit_paper_action(
                decision_cycle_id=cycle_id
            )
        self.assertFalse(self._mailbox().receipt_path(cycle_id).exists())
        self.assertEqual(1, self.paper.status()["ledger_revision"])

    def test_direct_risk_rejection_does_not_mutate_fact_owners(self) -> None:
        def excessive_risk(intent):
            return replace(
                intent,
                risk_budget={
                    **intent.risk_budget,
                    "maximum_loss": "101",
                },
            )

        cycle_id, _, _ = self._prepare_direct_paper_action(
            intent_transform=excessive_risk
        )
        self.clock.current = "2026-08-13T12:00:28.500000+00:00"
        with self.assertRaisesRegex(
            V332PaperRuntimeError, "RISK_POLICY_EXCEEDED"
        ):
            V332AgentPaperActionPort(self.paper).commit_paper_action(
                decision_cycle_id=cycle_id
            )
        status = self.paper.status()
        self.assertEqual(1, status["ledger_revision"])
        self.assertEqual([], status["attention_request_ids"])

    def test_direct_recovers_owner_facts_without_receipt_after_deadline(self) -> None:
        cycle_id, _, _ = self._prepare_direct_paper_action()
        execution_receipt = (
            self.runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / "paper-action-execution-receipt.json"
        )
        self.clock.current = "2026-08-13T12:00:28.500000+00:00"
        def fail_execution_receipt(path, value):
            if Path(path).name == "paper-action-execution-receipt.json":
                raise CanonicalContractError("simulated receipt crash")
            return write_once_json(path, value)

        with patch(
            (
                "trade_system.theory_paper_v2.infrastructure.market_cycle."
                "paper_runtime.write_once_json"
            ),
            side_effect=fail_execution_receipt,
        ):
            with self.assertRaisesRegex(
                V332PaperRuntimeError,
                "ACTION_EXECUTION_RECEIPT_FAILED",
            ):
                V332AgentPaperActionPort(self.paper).commit_paper_action(
                    decision_cycle_id=cycle_id
                )
        self.assertFalse(execution_receipt.exists())
        committed_status = self.paper.status()
        self.assertGreater(committed_status["ledger_revision"], 1)
        self.assertEqual([], committed_status["attention_request_ids"])

        # A later fill may legitimately extend the ledger before the crashed
        # commit publishes its receipt. Recovery must bind the original
        # transaction prefix rather than treating the current head as its end.
        execution_cycle = "hype-direct-recovery-later-fill"
        _seal_execution_book(self.raw_store, cycle_id=execution_cycle)
        processed = V332AgentPaperActionPort(
            self.paper
        ).process_market_cycle(cycle_id=execution_cycle)
        self.assertEqual("QUOTE", processed["observation_kind"])
        status_after_later_fact = self.paper.status()
        self.assertGreater(
            status_after_later_fact["ledger_revision"],
            committed_status["ledger_revision"],
        )

        plan = self.runtime.repository.load_artifact(
            cycle_id, "BehaviorPlan"
        )
        self.clock.current = (
            datetime.fromisoformat(plan["outcome_due_at"])
            + timedelta(seconds=1)
        ).isoformat()
        completed = V332AgentPaperActionPort(
            self.paper
        ).commit_paper_action(decision_cycle_id=cycle_id)
        self.assertEqual("COMMITTED", completed["status"])
        self.assertEqual(status_after_later_fact, self.paper.status())
        receipt = loads_json_strict(execution_receipt.read_bytes())
        self.assertLess(
            datetime.fromisoformat(receipt["completed_at"]),
            datetime.fromisoformat(plan["outcome_due_at"]),
        )
        self.assertEqual(
            committed_status["ledger_revision"],
            receipt["ledger_after_revision"],
        )
        self.assertEqual(
            loads_json_strict(
                (
                    self.runtime_root
                    / "cycles"
                    / cycle_id
                    / "transport"
                    / "paper-execution-intent.json"
                ).read_bytes()
            )["paper_context_sha256"],
            receipt["paper_context_sha256"],
        )
        self.assertEqual(
            completed,
            V332AgentPaperActionPort(self.paper).commit_paper_action(
                decision_cycle_id=cycle_id
            ),
        )

    def test_direct_recovery_accepts_later_episode_bracket_linkage(self) -> None:
        """A later bracket links the episode root instead of registering twice."""

        self._setup_account()
        cycle_id = self._seal_decision("hype-linked-bracket-recovery")
        mailbox, issued = self._issue_intent_request(cycle_id)
        root = self._short_bracket_intent(
            cycle_id, intent_request_sha256=issued.request_sha256
        )
        self._write_intent(mailbox, root)
        root_state = self._commit_intent(cycle_id)
        before_records = tuple(
            self.paper._ledger.load_records(self.paper.account_id)
        )
        root_comparators = tuple(
            record
            for record in before_records
            if record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED"
        )
        self.assertEqual(1, len(root_comparators))

        continuation_cycle = "hype-linked-bracket-recovery-2"
        assert root.bracket is not None

        def continuation_command(command, *, command_id):
            return replace(
                command,
                command_id=command_id,
                decision_cycle_id=continuation_cycle,
                expected_account_version=root_state.version,
                submitted_at="2026-08-13T12:00:28+00:00",
            )

        entry = continuation_command(
            root.bracket.entry, command_id="hype-short-bracket-002"
        )
        stop = continuation_command(
            root.bracket.protective_stop,
            command_id="hype-short-bracket-stop-002",
        )
        target = continuation_command(
            root.bracket.take_profits[0],
            command_id="hype-short-bracket-target-002",
        )
        continuation = replace(
            root,
            intent_id=entry.command_id,
            decision_cycle_id=continuation_cycle,
            expected_account_version=root_state.version,
            ledger_head_record_sha256=before_records[-1].record_sha256,
            authored_at="2026-08-13T12:00:28+00:00",
            valid_until="2026-08-13T12:01:00+00:00",
            transition_id="hype-short-bracket-transition-002",
            tranche_id="hype-short-bracket-tranche-002",
            command=entry,
            bracket=PaperBracketV1(
                bracket_id=entry.command_id,
                entry=entry,
                protective_stop=stop,
                take_profits=(target,),
            ),
        )
        class _ContinuationAuthority:
            @staticmethod
            def current_generation(logical_agent_id):
                return 1

            @staticmethod
            def verifies_decision(command):
                return True

            @staticmethod
            def verifies_execution_intent(intent):
                return True

        after = PaperTradingService(
            self.paper._ledger,
            cost_models=(self.paper._cost_model,),
            decision_authority=_ContinuationAuthority(),
            require_execution_intent=True,
            max_position_notional=self.paper._account_policy[
                "max_position_notional"
            ],
        ).submit_intent(
            continuation, received_at=continuation.authored_at
        )
        all_records = tuple(self.paper._ledger.load_records(self.paper.account_id))
        suffix = all_records[len(before_records) :]
        self.assertEqual(1, sum(
            record.event_type == "STATIC_NO_TRANSITION_PREREGISTERED"
            for record in all_records
        ))
        self.assertIn("static_comparator_linkage", suffix[0].payload)
        V332AgentPaperActionPort._validate_committed_ledger_suffix(
            before_records=before_records,
            suffix=suffix,
            intent=continuation,
            received_at=continuation.authored_at,
        )
        self.assertEqual(after.version, len(all_records))

    def test_runtime_funding_uses_admitted_slice_and_is_idempotent(self) -> None:
        account = self._setup_account()
        cycle_id = "hype-funding-runtime-001"
        self._seal_post_account_with_funding(
            cycle_id,
            moments=(
                datetime.fromisoformat(account.last_fact_at)
                - timedelta(seconds=1),
                datetime.fromisoformat(account.last_fact_at)
                + timedelta(seconds=2),
            ),
        )
        first = V332AgentPaperActionPort(
            self.paper
        ).process_market_cycle(
            cycle_id=cycle_id
        )
        self.assertEqual("MARK", first["observation_kind"])
        self.assertEqual("COMPLETE", first["funding"]["status"])
        self.assertEqual(
            (
                datetime.fromisoformat(account.last_fact_at)
                + timedelta(seconds=2, microseconds=-1)
            ).isoformat(),
            first["funding"]["account_coverage_end_at"],
        )
        replay = self.paper._advance_funding(cycle_id=cycle_id)
        self.assertEqual("COMPLETE", replay.status)
        self.assertEqual(
            first["ledger_after_revision"], replay.account_version
        )

    def test_process_preserves_partial_before_forward_funding_boundary(self) -> None:
        account = self._setup_account()
        cycle_id = "hype-funding-runtime-not-forward"
        self._seal_post_account_with_funding(
            cycle_id,
            moments=(
                datetime.fromisoformat(account.last_fact_at)
                - timedelta(seconds=2),
                datetime.fromisoformat(account.last_fact_at)
                - timedelta(seconds=1),
            ),
        )

        processed = V332AgentPaperActionPort(
            self.paper
        ).process_market_cycle(cycle_id=cycle_id)

        self.assertEqual("PARTIAL", processed["funding"]["status"])
        self.assertEqual(
            "LATEST_OFFICIAL_SETTLEMENT_NOT_FORWARD_OF_ACCOUNT",
            processed["funding"]["reason"],
        )
        self.assertEqual(
            "UNKNOWN", processed["funding"]["account_coverage_status"]
        )
        self.assertIsNone(processed["funding"]["account_coverage_end_at"])

    def test_process_maps_only_bounded_scheduler_window_error_to_partial(
        self,
    ) -> None:
        account = self._setup_account()
        cycle_id = "hype-funding-runtime-bounded-scheduler-error"
        self._seal_post_account_with_funding(
            cycle_id,
            moments=(
                datetime.fromisoformat(account.last_fact_at)
                - timedelta(seconds=1),
                datetime.fromisoformat(account.last_fact_at)
                + timedelta(seconds=2),
            ),
        )
        port = V332AgentPaperActionPort(self.paper)
        with patch.object(
            AdmittedSliceFundingScheduler,
            "run",
            side_effect=FundingSchedulerError(
                "PAPER_FUNDING_MODEL_WINDOW_MISMATCH"
            ),
        ):
            processed = port.process_market_cycle(cycle_id=cycle_id)

        self.assertEqual("PARTIAL", processed["funding"]["status"])
        self.assertEqual(
            (
                "FUNDING_WINDOW_NOT_PROCESSABLE:"
                "PAPER_FUNDING_MODEL_WINDOW_MISMATCH"
            ),
            processed["funding"]["reason"],
        )
        replay = port.process_market_cycle(cycle_id=cycle_id)
        self.assertEqual("COMPLETE", replay["funding"]["status"])
        records = self.paper._ledger.load_records(self.paper.account_id)
        self.assertEqual(
            1,
            sum(record.event_type == "MARKET_OBSERVED" for record in records),
        )

    def test_process_exactly_replays_market_after_hard_funding_failures(
        self,
    ) -> None:
        account = self._setup_account()
        cycle_id = "hype-funding-runtime-hard-failure-retry"
        self._seal_post_account_with_funding(
            cycle_id,
            moments=(
                datetime.fromisoformat(account.last_fact_at)
                - timedelta(seconds=1),
                datetime.fromisoformat(account.last_fact_at)
                + timedelta(seconds=2),
            ),
        )
        port = V332AgentPaperActionPort(self.paper)
        with patch.object(
            AdmittedSliceFundingScheduler,
            "run",
            side_effect=FundingSchedulerError("PAPER_FUNDING_SCOPE_MISMATCH"),
        ):
            with self.assertRaisesRegex(
                FundingSchedulerError, "PAPER_FUNDING_SCOPE_MISMATCH"
            ):
                port.process_market_cycle(cycle_id=cycle_id)
        with patch.object(
            AdmittedSliceFundingScheduler,
            "run",
            side_effect=RuntimeError("injected unknown funding crash"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "injected unknown funding crash"
            ):
                port.process_market_cycle(cycle_id=cycle_id)

        recovered = port.process_market_cycle(cycle_id=cycle_id)
        self.assertEqual("COMPLETE", recovered["funding"]["status"])
        records = self.paper._ledger.load_records(self.paper.account_id)
        self.assertEqual(
            1,
            sum(record.event_type == "MARKET_OBSERVED" for record in records),
        )
        self.assertEqual(
            1,
            sum(
                record.event_type == "FUNDING_COVERAGE_ADVANCED"
                for record in records
            ),
        )

    def test_process_does_not_replay_exact_fact_behind_newer_market(self) -> None:
        self._setup_account()
        cycle_a = "hype-process-replay-market-a"
        cycle_b = "hype-process-replay-market-b"
        self._seal_post_account_core(cycle_a)
        _seal_execution_book(self.raw_store, cycle_id=cycle_b)
        port = V332AgentPaperActionPort(self.paper)

        first = port.process_market_cycle(cycle_id=cycle_a)
        second = port.process_market_cycle(cycle_id=cycle_b)
        self.assertEqual("MARK", first["observation_kind"])
        self.assertEqual("QUOTE", second["observation_kind"])
        records_before = tuple(
            self.paper._ledger.load_records(self.paper.account_id)
        )

        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_MARKET_TIME_REGRESSION"
        ):
            port.process_market_cycle(cycle_id=cycle_a)

        self.assertEqual(
            records_before,
            tuple(self.paper._ledger.load_records(self.paper.account_id)),
        )

    def test_public_process_rebuilds_runtime_across_three_funding_windows(
        self,
    ) -> None:
        account = self._setup_account()
        opened = datetime.fromisoformat(account.last_fact_at)
        cases = (
            (
                "hype-public-funding-window-1",
                (opened - timedelta(seconds=1), opened + timedelta(seconds=2)),
                opened + timedelta(seconds=2, microseconds=-1),
            ),
            (
                "hype-public-funding-window-2",
                (
                    opened - timedelta(seconds=1),
                    opened + timedelta(seconds=2),
                    opened + timedelta(seconds=10),
                ),
                opened + timedelta(seconds=10, microseconds=-1),
            ),
            (
                "hype-public-funding-window-3",
                (
                    opened - timedelta(seconds=1),
                    opened + timedelta(seconds=2),
                    opened + timedelta(seconds=10),
                    opened + timedelta(seconds=18),
                ),
                opened + timedelta(seconds=18, microseconds=-1),
            ),
        )
        results = []
        for cycle_id, moments, expected_end in cases:
            self._seal_post_account_with_funding(
                cycle_id, moments=moments
            )
            rebuilt = V332HypePaperRuntime(
                self.runtime,
                setup_cycle_id=self.setup_cycle_id,
            )
            processed = V332AgentPaperActionPort(
                rebuilt
            ).process_market_cycle(cycle_id=cycle_id)
            self.assertEqual("COMPLETE", processed["funding"]["status"])
            self.assertEqual(
                expected_end.isoformat(),
                processed["funding"]["account_coverage_end_at"],
            )
            results.append(processed)

        records = self.paper._ledger.load_records(self.paper.account_id)
        advances = [
            record.payload["advance"]
            for record in records
            if record.event_type == "FUNDING_COVERAGE_ADVANCED"
        ]
        accruals = [
            record.payload["accrual"]
            for record in records
            if record.event_type == "CARRY_ACCRUED"
        ]
        self.assertEqual(3, len(advances))
        self.assertEqual(2, len(accruals))
        self.assertEqual(
            [
                account.last_fact_at,
                cases[0][2].isoformat(),
                cases[1][2].isoformat(),
            ],
            [item["coverage_start_at"] for item in advances],
        )
        self.assertEqual(
            3,
            len(
                {
                    item["funding_history_source_sha256"]
                    for item in advances
                }
            ),
        )
        self.assertEqual(
            2,
            len({item["effective_at"] for item in accruals}),
        )
        self.assertEqual(
            1,
            sum(record.event_type == "MARKET_OBSERVED" for record in records),
        )
        self.assertEqual(
            cases[-1][2].isoformat(),
            results[-1]["funding"]["account_coverage_end_at"],
        )


if __name__ == "__main__":
    unittest.main()
