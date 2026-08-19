from __future__ import annotations

from contextlib import nullcontext
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.service import CycleService
from trade_system.theory_paper_v2.domain.market_cycle.attention import AgentRegistry
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.goal_identity import (
    CodexGoalIdentityError,
    current_codex_goal_identity,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    ManifestBoundCycleService,
    MarketCycleRuntimeError,
    V332GoalRegistryGate,
)
from trade_system.theory_paper_v2.presentation.market_cycle import _parser
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli


_THREAD_ID = "019ff5a3-529a-77d2-a3e4-595710406637"
_PHYSICAL_GOAL_ID = f"codex-thread:{_THREAD_ID}"


class V332GoalIdentityTest(unittest.TestCase):
    def test_public_delivery_has_no_identity_or_worker_control_arguments(self) -> None:
        decision = _parser().parse_args(
            ["deliver", "cycle-1", "/tmp/decision.md"]
        )
        self.assertEqual(decision.command, "deliver")
        self.assertFalse(hasattr(decision, "physical_goal_id"))
        self.assertFalse(hasattr(decision, "logical_agent_id"))
        for arguments in (
            ["deliver-worker-result", "cycle-1", "decision-v1"],
            ["controller-expire-decision", "cycle-1"],
            ["controller-prepare-worker", "cycle-1", "decision-v1"],
            ["controller-prepare-worker", "cycle-1", "review-v1"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                _parser().parse_args(arguments)

    def test_identity_is_derived_only_from_current_codex_thread(self) -> None:
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": _THREAD_ID}, clear=False):
            self.assertEqual(current_codex_goal_identity(), _PHYSICAL_GOAL_ID)
        for value in (None, "", "caller-supplied-goal", _THREAD_ID.upper()):
            environment = {} if value is None else {"CODEX_THREAD_ID": value}
            with (
                self.subTest(value=value),
                mock.patch.dict(os.environ, environment, clear=True),
                self.assertRaises(CodexGoalIdentityError),
            ):
                current_codex_goal_identity()

    def test_continuity_cli_routes_create_without_caller_time(self) -> None:
        state = SimpleNamespace(to_dict=lambda: {"stage": "REQUESTED"})
        runtime = SimpleNamespace(
            experiment_policy=SimpleNamespace(
                phase="CONTINUITY_24H",
                decision_horizon_seconds=3600,
                outcome_tolerance_seconds=300,
            ),
            run_manifest=SimpleNamespace(
                market_contract_identity="OKX:HYPE-USDT-SWAP:linear"
            ),
            create_goal_cycle=mock.Mock(return_value=state),
        )
        with (
            mock.patch.object(
                market_cycle_cli,
                "build_market_cycle_runtime",
                return_value=runtime,
            ),
            mock.patch.object(market_cycle_cli, "_write"),
        ):
            self.assertEqual(market_cycle_cli.main(["create", "cycle-1"]), 0)
        runtime.create_goal_cycle.assert_called_once_with("cycle-1")

    def test_capability_cli_preserves_legacy_create_defaults(self) -> None:
        state = SimpleNamespace(to_dict=lambda: {"stage": "REQUESTED"})
        service = SimpleNamespace(create=mock.Mock(return_value=state))
        runtime = SimpleNamespace(
            identity=V332_THEORY_IDENTITY,
            experiment_policy=SimpleNamespace(
                phase="CAPABILITY_PILOT",
                decision_horizon_seconds=1200,
                outcome_tolerance_seconds=300,
            ),
            run_manifest=SimpleNamespace(
                market_contract_identity="OKX:HYPE-USDT-SWAP:linear"
            ),
            service=service,
        )
        with (
            mock.patch.object(
                market_cycle_cli,
                "build_market_cycle_runtime",
                return_value=runtime,
            ),
            mock.patch.object(market_cycle_cli, "_write"),
            mock.patch.object(
                market_cycle_cli.SystemUTCMonotonicClock,
                "__call__",
                return_value="2026-08-13T08:00:01+00:00",
            ),
        ):
            self.assertEqual(market_cycle_cli.main(["create", "cycle-1"]), 0)

        request = service.create.call_args.args[0]
        self.assertEqual(request.outcome_horizon_seconds, 3600)
        self.assertEqual(request.outcome_tolerance_seconds, 60)

    def test_registry_gate_requires_the_exact_current_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = FileAttentionRepository(root / "attention")
            AgentSessionService(repository).register(
                AgentRegistry(
                    logical_agent_id="hype-paper-agent",
                    symbol="HYPE-USDT-SWAP",
                    generation=1,
                    continuity_nonce="continuity-v332-goal",
                    physical_task_id=_PHYSICAL_GOAL_ID,
                    status="ACTIVE",
                    registered_at="2026-08-13T00:00:00+00:00",
                )
            )
            gate = V332GoalRegistryGate(
                root,
                paper_account_policy={
                    "logical_agent_id": "hype-paper-agent",
                    "agent_generation": 1,
                },
            )
            with mock.patch.dict(
                os.environ, {"CODEX_THREAD_ID": _THREAD_ID}, clear=True
            ):
                self.assertEqual(gate.verify().physical_task_id, _PHYSICAL_GOAL_ID)
            with mock.patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": "119ff5a3-529a-77d2-a3e4-595710406637"},
                clear=True,
            ), self.assertRaisesRegex(
                MarketCycleRuntimeError, "V332_GOAL_REGISTRY_MISMATCH"
            ):
                gate.verify()


class V332GoalDeliveryRoutingTest(unittest.TestCase):
    @staticmethod
    def _bound_service() -> tuple[
        ManifestBoundCycleService, mock.Mock, mock.Mock, mock.Mock
    ]:
        application = mock.Mock()
        repository = mock.Mock()
        repository.locked.return_value = nullcontext()
        gate = SimpleNamespace(
            expected_theory_identity=V332_THEORY_IDENTITY,
            mutation_guard=lambda: nullcontext(),
        )
        goal_gate = mock.Mock()
        service = ManifestBoundCycleService(
            service=application,
            repository=repository,
            gate=gate,
            goal_registry_gate=goal_gate,
        )
        service._require_cycle_binding = mock.Mock()
        return service, application, repository, goal_gate

    def test_v332_decision_and_review_bypass_worker_admission(self) -> None:
        service, application, _, goal_gate = self._bound_service()
        application.deliver_goal_decision.return_value = "CREATED"
        application.deliver_goal_review.return_value = "CREATED"

        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": _THREAD_ID}, clear=True
        ):
            self.assertEqual(
                service.deliver_agent_decision("cycle-1", b"WAIT\n"),
                "CREATED",
            )
            self.assertEqual(
                service.deliver_agent_review("cycle-1", b"Review\n"),
                "CREATED",
            )

        self.assertEqual(goal_gate.verify.call_count, 2)
        goal_gate.verify.assert_called_with(
            physical_goal_id=_PHYSICAL_GOAL_ID
        )
        application.deliver_goal_decision.assert_called_once_with(
            "cycle-1", b"WAIT\n", media_type="text/markdown"
        )
        application.deliver_goal_review.assert_called_once_with(
            "cycle-1", b"Review\n", media_type="text/markdown"
        )
        application.deliver_worker_result.assert_not_called()

    def test_v332_goal_delivery_does_not_require_a_paper_registry(self) -> None:
        application = mock.Mock()
        application.deliver_goal_decision.return_value = "CREATED"
        repository = mock.Mock()
        repository.locked.return_value = nullcontext()
        service = ManifestBoundCycleService(
            service=application,
            repository=repository,
            gate=SimpleNamespace(
                expected_theory_identity=V332_THEORY_IDENTITY,
                mutation_guard=lambda: nullcontext(),
            ),
            goal_registry_gate=None,
        )
        service._require_cycle_binding = mock.Mock()

        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": _THREAD_ID}, clear=True
        ):
            self.assertEqual(
                service.deliver_agent_decision("cycle-1", b"WAIT\n"),
                "CREATED",
            )
        application.deliver_goal_decision.assert_called_once_with(
            "cycle-1", b"WAIT\n", media_type="text/markdown"
        )

    def test_v332_goal_delivery_requires_host_identity_without_paper(self) -> None:
        application = mock.Mock()
        repository = mock.Mock()
        repository.locked.return_value = nullcontext()
        service = ManifestBoundCycleService(
            service=application,
            repository=repository,
            gate=SimpleNamespace(
                expected_theory_identity=V332_THEORY_IDENTITY,
                mutation_guard=lambda: nullcontext(),
            ),
            goal_registry_gate=None,
        )
        service._require_cycle_binding = mock.Mock()

        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            MarketCycleRuntimeError, "RUN_V332_GOAL_IDENTITY_REQUIRED"
        ):
            service.deliver_agent_decision("cycle-1", b"WAIT\n")
        application.deliver_goal_decision.assert_not_called()

    def test_worker_delivery_and_worker_expiry_are_not_v332_goal_controls(self) -> None:
        service, application, _, _ = self._bound_service()
        with self.assertRaisesRegex(
            MarketCycleRuntimeError, "RUN_WORKER_RESULT_DELIVERY_NOT_SUPPORTED"
        ):
            service.deliver_worker_result("cycle-1", "decision-v1")
        with self.assertRaisesRegex(
            MarketCycleRuntimeError, "RUN_V332_GOAL_WORKER_CONTROL_FORBIDDEN"
        ):
            service.controller_expire_worker("cycle-1", "decision-v1")
        application.deliver_worker_result.assert_not_called()
        application.controller_expire_worker.assert_not_called()

    def test_all_v332_decision_worker_control_routes_are_forbidden(self) -> None:
        service, application, _, _ = self._bound_service()
        routes = (
            (service.controller_prepare_worker, ("cycle-1", "decision-v1")),
            (
                service.controller_mark_worker_spawn_requested,
                ("cycle-1", "decision-v1", "dispatch-1"),
            ),
            (
                service.controller_acknowledge_worker_spawn,
                ("cycle-1", "decision-v1", "dispatch-1", "external-ref"),
            ),
            (
                service.controller_admit_worker_result_for_delivery,
                ("cycle-1", "decision-v1"),
            ),
            (
                service.controller_complete_worker,
                ("cycle-1", "decision-v1", "dispatch-1", "a" * 64),
            ),
            (service.controller_recover_worker, ("cycle-1", "decision-v1")),
        )
        for route, arguments in routes:
            with self.subTest(route=route.__name__), self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_V332_GOAL_WORKER_CONTROL_FORBIDDEN"
            ):
                route(*arguments)
        application.controller_materialize_worker_task.assert_not_called()


class V332GoalCycleServiceTest(unittest.TestCase):
    @staticmethod
    def _service(stage: str) -> tuple[CycleService, mock.Mock, mock.Mock, object]:
        repository = mock.Mock()
        repository.locked.return_value = nullcontext()
        state = SimpleNamespace(
            cycle_id="cycle-1", stage=stage, terminal=False
        )
        repository.recover_pending.return_value = None
        repository.load_state.return_value = state
        agent = mock.Mock()
        service = object.__new__(CycleService)
        service._repository = repository
        service._agent = agent
        service._clock = mock.Mock(return_value="2026-08-13T00:00:00+00:00")
        service._theory_fragments = {"README.md": "verified"}
        service._verified_memory = ()
        service._decision_context = None
        return service, repository, agent, state

    def test_direct_delivery_methods_use_goal_transport_only(self) -> None:
        decision_service, _, decision_agent, _ = self._service("INPUT_SEALED")
        decision_agent.persist_goal_decision.return_value = "CREATED"
        self.assertEqual(
            decision_service.deliver_goal_decision("cycle-1", b"WAIT\n"),
            "CREATED",
        )
        decision_agent.persist_goal_decision.assert_called_once_with(
            "cycle-1", b"WAIT\n", media_type="text/markdown"
        )
        decision_agent.persist_decision.assert_not_called()

        review_service, _, review_agent, _ = self._service("OUTCOME_SEALED")
        review_agent.persist_goal_review.return_value = "CREATED"
        self.assertEqual(
            review_service.deliver_goal_review("cycle-1", b"Review\n"),
            "CREATED",
        )
        review_agent.persist_goal_review.assert_called_once_with(
            "cycle-1", b"Review\n", media_type="text/markdown"
        )
        review_agent.persist_review.assert_not_called()

    def test_v332_sealed_deliveries_advance_without_worker_completion(self) -> None:
        service, _, agent, state = self._service("INPUT_SEALED")
        agent.delivery_present.return_value = True
        snapshot = SimpleNamespace(theory_identity=V332_THEORY_IDENTITY)
        service._load = mock.Mock(return_value=(snapshot, object()))
        service._require_worker_completed = mock.Mock(
            side_effect=AssertionError("worker completion must not be consulted")
        )
        service._advance = mock.Mock(return_value=SimpleNamespace(stage="ANALYZED"))
        with mock.patch(
            "trade_system.theory_paper_v2.application.market_cycle.service.analyze_snapshot",
            return_value=object(),
        ):
            result = service.run_next("cycle-1")
        self.assertTrue(result.changed)
        self.assertEqual(result.state.stage, "ANALYZED")
        service._require_worker_completed.assert_not_called()
        self.assertEqual(state.stage, "INPUT_SEALED")

        review_service, _, review_agent, _ = self._service("OUTCOME_SEALED")
        review_agent.review_delivery_present.return_value = True
        plan = SimpleNamespace(theory_identity=V332_THEORY_IDENTITY)
        review_service._load = mock.Mock(
            side_effect=[
                (SimpleNamespace(analysis_profile="COLD"), object()),
                (object(), object()),
                (plan, object()),
                (object(), object()),
            ]
        )
        review_service._require_worker_completed = mock.Mock(
            side_effect=AssertionError("worker completion must not be consulted")
        )
        review_service._advance = mock.Mock(
            return_value=SimpleNamespace(stage="REVIEWED")
        )
        with mock.patch(
            "trade_system.theory_paper_v2.application.market_cycle.service.review_cycle",
            return_value=object(),
        ):
            result = review_service.run_next("cycle-1")
        self.assertTrue(result.changed)
        self.assertEqual(result.state.stage, "REVIEWED")
        review_service._require_worker_completed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
