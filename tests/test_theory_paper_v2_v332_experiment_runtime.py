from __future__ import annotations

import tempfile
import os
from pathlib import Path
import unittest
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    LAWFUL_REFERENCE_ACTIONS,
    CycleRequest,
)
from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.domain.market_cycle.experiment import (
    EXPERIMENT_MISSING_DATA_POLICY,
    ExperimentPolicyError,
    ExperimentPolicyV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    EXPERIMENT_POLICY_RELATIVE_PATH,
    RUN_CLOSURE_RELATIVE_PATH,
    RUN_MANIFEST_RELATIVE_PATH,
    MarketCycleRuntimeError,
    build_market_cycle_runtime,
    initialize_v332_run,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.capability_evaluation_store import (
    FileCapabilityEvaluationStore,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.operational_evaluation_store import (
    FileOperationalEvaluationStore,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_capability_evaluation_store import (
    FilePaperCapabilityEvaluationStore,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.continuity_checkpoint import (
    FileContinuityCheckpointStore,
)
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli


_V332_PACKAGE = Path(__file__).resolve().parents[1] / "theory" / "versions" / "v3.3.2"


class _Clock:
    def __init__(self, current: str) -> None:
        self.current = current
        self._monotonic = 0

    def __call__(self) -> str:
        return self.current

    def monotonic_ns(self) -> int:
        self._monotonic += 1
        return self._monotonic


def _policy(
    run_id: str,
    *,
    phase: str = "CAPABILITY_PILOT",
    duration_seconds: int = 1200,
    public_data_authorized: bool = True,
) -> ExperimentPolicyV1:
    return ExperimentPolicyV1(
        experiment_id=f"{run_id}.policy",
        run_id=run_id,
        phase=phase,
        venue_id="OKX",
        instrument_id="HYPE-USDT-SWAP",
        market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        starts_at="2026-08-13T08:00:00Z",
        duration_seconds=duration_seconds,
        decision_horizon_seconds=1200,
        outcome_tolerance_seconds=60,
        base_sampling_seconds=300,
        active_sampling_seconds=60,
        capability_ids=(
            "DATA_ADMISSION",
            "SYSTEM_EXECUTION",
            "MARKET_ANALYSIS",
            "HYPOTHESIS_GENERATION",
            "TRADING_DECISION",
            "POSITION_MANAGEMENT",
            "ATTENTION_SCHEDULING",
            "RECOVERY_REPLAY",
            "OPERATIONAL_EVALUATION",
        ),
        public_data_authorized=public_data_authorized,
        local_paper_authorized=True,
        testnet_authorized=False,
        live_authorized=False,
        private_credentials_authorized=False,
        external_orders_authorized=False,
        funds_authorized=False,
        paper_account={
            "account_id": f"{run_id}.paper",
            "setup_cycle_id": f"{run_id}.paper-setup",
            "logical_agent_id": "HYPE_CAPABILITY_TRADER",
            "agent_generation": 1,
            "account_mode": "LINEAR_PERP",
            "base_currency": "USDT",
            "initial_balance": "10000",
            "max_leverage": "2",
            "max_position_notional": "10000",
            "max_decision_loss": "100",
            "max_observed_drawdown": "500",
            "cost_model": {
                "model_id": "v332-pilot-modeled-costs-v1",
                "maker_fee_bps": "2",
                "taker_fee_bps": "5",
                "market_impact_bps": "3",
                "funding_status": "UNKNOWN",
                "borrow_status": "NOT_APPLICABLE",
                "effective_from": "2026-08-13T08:00:00Z",
                "effective_to": "2026-08-15T08:00:00Z",
            },
        },
        evaluation={
            "mode": (
                "INDEPENDENT_CAPABILITY_PILOT"
                if phase == "CAPABILITY_PILOT"
                else "CONTINUITY_FORWARD_PAPER"
            ),
            "total_score_enabled": False,
            "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
            "predictive_claim": "NOT_EVALUATED_UNTIL_FROZEN_ORDERED_OUTCOME",
            "continuity_claim": "NOT_TESTED" if phase == "CAPABILITY_PILOT" else "PRIMARY",
        },
        missing_data_policy=EXPERIMENT_MISSING_DATA_POLICY,
        restart_if=(
            "FUTURE_LEAKAGE",
            "IDENTITY_OR_PIT_MISMATCH",
            "DURABLE_FACT_CHAIN_CORRUPTION",
            "UNAUTHORIZED_EXTERNAL_SIDE_EFFECT",
        ),
        continue_if=(
            "OPTIONAL_DATA_TYPED_UNKNOWN",
            "AGENT_LEGITIMATELY_CHOSES_WAIT",
            "NON_CONTAMINATING_OBSERVABILITY_DEFECT",
        ),
    )


class V332ExperimentPolicyTests(unittest.TestCase):
    def test_policy_is_canonical_digest_bound_and_forbids_external_authority(self) -> None:
        policy = _policy("v332-capability-policy")
        self.assertEqual(
            ExperimentPolicyV1.from_dict(policy.to_dict()).to_dict(),
            policy.to_dict(),
        )
        self.assertEqual(len(policy.policy_sha256), 64)
        with self.assertRaisesRegex(
            ExperimentPolicyError, "EXTERNAL_SIDE_EFFECT_AUTHORITY_FORBIDDEN"
        ):
            ExperimentPolicyV1.from_dict(
                {**policy.to_dict(), "external_orders_authorized": True}
            )

    def test_continuity_phase_requires_exactly_24_hours(self) -> None:
        with self.assertRaisesRegex(
            ExperimentPolicyError, "PHASE_DURATION_MISMATCH"
        ):
            _policy(
                "v332-continuity-wrong-duration",
                phase="CONTINUITY_24H",
                duration_seconds=86399,
            )
        policy = _policy(
            "v332-continuity-exact-duration",
            phase="CONTINUITY_24H",
            duration_seconds=86400,
        )
        self.assertEqual(policy.duration_seconds, 86400)


class V332RunInitializationTests(unittest.TestCase):
    def test_fresh_run_binds_policy_and_public_collection_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "v332-authorized-run"
            policy = _policy(runtime_root.name)
            manifest = initialize_v332_run(
                runtime_root,
                theory_package=_V332_PACKAGE,
                experiment_policy=policy,
            )
            self.assertEqual(manifest.experiment_identity, policy.policy_sha256)
            self.assertEqual(
                (runtime_root / EXPERIMENT_POLICY_RELATIVE_PATH).read_bytes(),
                canonical_bytes(policy.to_dict()) + b"\n",
            )
            runtime = build_market_cycle_runtime(
                runtime_root=runtime_root,
                theory_package=_V332_PACKAGE,
                expected_theory_identity=V332_THEORY_IDENTITY,
                allow_public_collection=True,
            )
            self.assertEqual(runtime.experiment_policy, policy)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_ROOT_ALREADY_EXISTS"
            ):
                initialize_v332_run(
                    runtime_root,
                    theory_package=_V332_PACKAGE,
                    experiment_policy=policy,
                )

    def test_policy_without_public_authority_cannot_enable_collector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "v332-replay-only-run"
            policy = _policy(runtime_root.name, public_data_authorized=False)
            initialize_v332_run(
                runtime_root,
                theory_package=_V332_PACKAGE,
                experiment_policy=policy,
            )
            replay = build_market_cycle_runtime(
                runtime_root=runtime_root,
                theory_package=_V332_PACKAGE,
                expected_theory_identity=V332_THEORY_IDENTITY,
            )
            self.assertFalse(replay.experiment_policy.public_data_authorized)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "PUBLIC_COLLECTION_NOT_AUTHORIZED_BY_POLICY"
            ):
                build_market_cycle_runtime(
                    runtime_root=runtime_root,
                    theory_package=_V332_PACKAGE,
                    expected_theory_identity=V332_THEORY_IDENTITY,
                    allow_public_collection=True,
                )

    def test_cli_initializes_only_from_canonical_policy_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "v332-cli-run"
            policy = _policy(runtime_root.name)
            policy_file = root / "policy.json"
            policy_file.write_bytes(canonical_bytes(policy.to_dict()) + b"\n")
            with mock.patch.object(market_cycle_cli, "_write") as write:
                self.assertEqual(
                    market_cycle_cli.main(
                        [
                            "--runtime-root",
                            str(runtime_root),
                            "--theory-version",
                            "3.3.2",
                            "initialize-run",
                            str(policy_file),
                        ]
                    ),
                    0,
                )
            payload = write.call_args.args[0]
            self.assertEqual(payload["experiment_policy_sha256"], policy.policy_sha256)
            self.assertTrue((runtime_root / "controller" / "run.json").is_file())


class V332GoalCycleAdmissionTests(unittest.TestCase):
    _THREAD_ID = "019ffb95-4195-7292-8a44-9870151a97f5"
    _GOAL_ID = f"codex-thread:{_THREAD_ID}"

    def setUp(self) -> None:
        host = mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": self._THREAD_ID}, clear=False
        )
        host.start()
        self.addCleanup(host.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "v332-goal-cycle"
        self.policy = _policy(
            self.root.name,
            phase="CONTINUITY_24H",
            duration_seconds=86_400,
        )
        initialize_v332_run(
            self.root,
            theory_package=_V332_PACKAGE,
            experiment_policy=self.policy,
        )
        self.clock = _Clock("2026-08-13T08:00:01+00:00")
        self.runtime = build_market_cycle_runtime(
            runtime_root=self.root,
            theory_package=_V332_PACKAGE,
            expected_theory_identity=V332_THEORY_IDENTITY,
            clock=self.clock,
        )
        self.attention_repository = FileAttentionRepository(
            self.root / "attention"
        )
        self.registry = AgentRegistry(
            logical_agent_id=str(self.policy.paper_account["logical_agent_id"]),
            symbol=self.policy.instrument_id,
            generation=int(self.policy.paper_account["agent_generation"]),
            continuity_nonce="v332-goal-cycle-continuity",
            physical_task_id=self._GOAL_ID,
            status="ACTIVE",
            registered_at="2026-08-13T08:00:00+00:00",
        )
        AgentSessionService(self.attention_repository).register(self.registry)

    def _checkpoint(self) -> AttentionRequest:
        request = AttentionRequest(
            request_id="goal-cycle-attention-1",
            logical_agent_id=self.registry.logical_agent_id,
            agent_generation=self.registry.generation,
            continuity_nonce=self.registry.continuity_nonce,
            symbol=self.registry.symbol,
            mode="WAKE_AFTER",
            issued_at="2026-08-13T08:00:02+00:00",
            continue_until=None,
            earliest_wake_at="2026-08-13T08:00:05+00:00",
            latest_useful_at="2026-08-13T08:00:10+00:00",
            reason_summary="The Goal chose a bounded follow-up window.",
            requested_focus="Re-evaluate the sealed HYPE hypothesis.",
            hypothesis_or_episode_ref="goal-cycle-bootstrap.plan",
            position_and_open_order_ref=str(
                self.policy.paper_account["account_id"]
            ),
            data_cursor="goal-cycle-bootstrap.input",
        )
        self.clock.current = "2026-08-13T08:00:03+00:00"
        self.runtime.submit_goal_attention_checkpoint(request)
        return request

    def test_goal_cycle_rechecks_trusted_latest_and_exact_retry_skips_clock(self) -> None:
        bypass = CycleRequest(
            request_id="goal-cycle-bypass.request",
            cycle_id="goal-cycle-bypass",
            requested_at="2026-08-13T08:00:01+00:00",
            venue_id=self.policy.venue_id,
            instrument_id=self.policy.instrument_id,
            contract_identity=self.policy.market_contract_identity,
            analysis_profile="COLD",
            data_profile=self.policy.data_profile,
            outcome_horizon_seconds=self.policy.decision_horizon_seconds,
            outcome_tolerance_seconds=self.policy.outcome_tolerance_seconds,
            lawful_actions=LAWFUL_REFERENCE_ACTIONS,
            theory_identity=self.runtime.identity,
        )
        with self.assertRaisesRegex(
            MarketCycleRuntimeError, "GOAL_WINDOW_CREATE_REQUIRED"
        ):
            self.runtime.service.create(bypass)
        self.assertFalse((self.root / "cycles" / bypass.cycle_id).exists())

        bootstrap = self.runtime.create_goal_cycle("goal-cycle-bootstrap")
        self.assertEqual(bootstrap.stage, "REQUESTED")
        self._checkpoint()

        before = {
            path.relative_to(self.root): None if path.is_dir() else path.read_bytes()
            for path in self.root.rglob("*")
        }
        self.clock.current = "2026-08-13T08:00:10.000001+00:00"
        with mock.patch.object(
            self.runtime.controller_state,
            "trusted_now",
            wraps=self.runtime.controller_state.trusted_now,
        ) as trusted_now:
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "ATTENTION_WINDOW_EXPIRED"
            ):
                self.runtime.create_goal_cycle("goal-cycle-late")
        self.assertEqual(trusted_now.call_count, 1)
        self.assertFalse((self.root / "cycles" / "goal-cycle-late").exists())
        self.assertEqual(
            {
                path.relative_to(self.root): (
                    None if path.is_dir() else path.read_bytes()
                )
                for path in self.root.rglob("*")
            },
            before,
        )

        self.clock.current = "2026-08-13T08:00:10+00:00"
        created = self.runtime.create_goal_cycle("goal-cycle-followup")
        persisted = self.runtime.repository.load_request("goal-cycle-followup")
        self.assertEqual(created.stage, "REQUESTED")
        self.assertEqual(persisted.requested_at, self.clock.current)
        self.clock.current = "2026-08-13T08:01:00+00:00"
        with mock.patch.object(
            self.runtime.controller_state,
            "trusted_now",
            wraps=self.runtime.controller_state.trusted_now,
        ) as trusted_now:
            duplicate = self.runtime.create_goal_cycle("goal-cycle-followup")
        self.assertEqual(duplicate, created)
        trusted_now.assert_not_called()

class V332RunClosureTests(unittest.TestCase):
    def _runtime(self, root: Path):
        policy = _policy(root.name)
        initialize_v332_run(
            root,
            theory_package=_V332_PACKAGE,
            experiment_policy=policy,
        )
        return build_market_cycle_runtime(
            runtime_root=root,
            theory_package=_V332_PACKAGE,
            expected_theory_identity=V332_THEORY_IDENTITY,
        )

    def test_capability_close_is_reentrant_and_freezes_without_terminal_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "v332-close-capability"
            runtime = self._runtime(root)
            with runtime.mutation_guard():
                with runtime.mutation_guard():
                    self.assertEqual(runtime.run_manifest.status, "OPEN")

            closed = runtime.close_run()
            self.assertEqual(closed.status, "CLOSED")
            self.assertEqual(runtime.close_run().status, "CLOSED")
            self.assertTrue((root / RUN_CLOSURE_RELATIVE_PATH).is_file())
            self.assertEqual(
                loads_json_strict((root / RUN_MANIFEST_RELATIVE_PATH).read_bytes())[
                    "status"
                ],
                "CLOSED",
            )
            before = {
                path.relative_to(root): None if path.is_dir() else path.read_bytes()
                for path in root.rglob("*")
            }
            request = CycleRequest(
                request_id="closed-cycle.request",
                cycle_id="closed-cycle",
                requested_at="2026-08-13T08:01:00Z",
                venue_id="OKX",
                instrument_id="HYPE-USDT-SWAP",
                contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
                analysis_profile="COLD",
                data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
                outcome_horizon_seconds=1200,
                outcome_tolerance_seconds=60,
                lawful_actions=LAWFUL_REFERENCE_ACTIONS,
                theory_identity=V332_THEORY_IDENTITY,
            )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                runtime.service.create(request)
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                runtime.service.controller_recover_worker(
                    "closed-ghost-cycle", "daily-deep-v1"
                )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                runtime.service.controller_admit_worker_result_for_delivery(
                    "closed-ghost-cycle", "daily-deep-v1"
                )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                FileCapabilityEvaluationStore(runtime).prepare_assessor(
                    cycle_id="closed-cycle",
                    task_id="closed-capability-task",
                    capability_id="DATA_ADMISSION",
                    assessment_due_at="2026-08-13T08:10:00Z",
                )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                FileOperationalEvaluationStore(runtime).evaluate_and_seal(
                    cycle_id="closed-cycle",
                    evaluation_id="closed-evaluation",
                    evidence_policy=mock.Mock(),
                )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                FilePaperCapabilityEvaluationStore(runtime).prepare_assessor(
                    cycle_ids=("closed-cycle",),
                    task_id="closed-paper-capability-task",
                    capability_id="TRADING_DECISION",
                    assessment_due_at="2026-08-13T08:10:00Z",
                )
            with self.assertRaisesRegex(MarketCycleRuntimeError, "NOT_OPEN"):
                FileContinuityCheckpointStore(
                    runtime, clock=runtime.controller_state.trusted_now
                ).open()
            self.assertEqual(
                {
                    path.relative_to(root): (
                        None if path.is_dir() else path.read_bytes()
                    )
                    for path in root.rglob("*")
                },
                before,
            )

    def test_only_explicit_close_recovers_marker_written_manifest_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "v332-close-recovery"
            runtime = self._runtime(root)
            with mock.patch(
                "trade_system.theory_paper_v2.infrastructure.market_cycle.runtime.atomic_replace_json",
                side_effect=OSError("simulated manifest publication crash"),
            ):
                with self.assertRaisesRegex(
                    MarketCycleRuntimeError, "RUN_CLOSE_PUBLICATION_FAILED"
                ):
                    runtime.close_run()
            self.assertEqual(
                loads_json_strict((root / RUN_MANIFEST_RELATIVE_PATH).read_bytes())[
                    "status"
                ],
                "OPEN",
            )
            read_snapshot = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_CLOSURE_RECOVERY_REQUIRED"
            ):
                build_market_cycle_runtime(
                    runtime_root=root,
                    theory_package=_V332_PACKAGE,
                    expected_theory_identity=V332_THEORY_IDENTITY,
                )
            self.assertEqual(
                {
                    path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
                read_snapshot,
            )
            self.assertEqual(
                loads_json_strict((root / RUN_MANIFEST_RELATIVE_PATH).read_bytes())[
                    "status"
                ],
                "OPEN",
            )
            with mock.patch.object(market_cycle_cli, "_write") as write:
                self.assertEqual(
                    market_cycle_cli.main(
                        ["--runtime-root", str(root), "close-run"]
                    ),
                    0,
                )
            self.assertEqual(write.call_args.args[0]["closure_status"], "CLOSED")
            self.assertEqual(
                loads_json_strict((root / RUN_MANIFEST_RELATIVE_PATH).read_bytes())[
                    "status"
                ],
                "CLOSED",
            )

    def test_continuity_close_rejects_before_full_86400_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "v332-continuity-close-early"
            policy = _policy(
                root.name, phase="CONTINUITY_24H", duration_seconds=86_400
            )
            initialize_v332_run(
                root,
                theory_package=_V332_PACKAGE,
                experiment_policy=policy,
            )
            runtime = build_market_cycle_runtime(
                runtime_root=root,
                theory_package=_V332_PACKAGE,
                expected_theory_identity=V332_THEORY_IDENTITY,
                clock=_Clock("2026-08-14T07:59:59Z"),
            )
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_CLOSE_CONTINUITY_ELAPSED_REQUIRED"
            ):
                runtime.close_run()
            self.assertFalse((root / RUN_CLOSURE_RELATIVE_PATH).exists())

    def test_capability_close_rejects_active_assessor_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "v332-close-active-assessor"
            runtime = self._runtime(root)
            controller = dict(runtime.controller_state.status())
            controller["events"] = {}
            controller["worker_dispatches"] = {
                "cycle::capability-assessor-v1": {
                    "status": "DISPATCHED"
                }
            }
            before = {
                path.relative_to(root): None if path.is_dir() else path.read_bytes()
                for path in root.rglob("*")
            }
            with mock.patch.object(
                runtime.controller_state, "status", return_value=controller
            ):
                with self.assertRaisesRegex(
                    MarketCycleRuntimeError, "RUN_CLOSE_ACTIVE_WORKER"
                ):
                    runtime.close_run()
            self.assertFalse((root / RUN_CLOSURE_RELATIVE_PATH).exists())
            self.assertEqual(
                {
                    path.relative_to(root): (
                        None if path.is_dir() else path.read_bytes()
                    )
                    for path in root.rglob("*")
                },
                before,
            )


if __name__ == "__main__":
    unittest.main()
