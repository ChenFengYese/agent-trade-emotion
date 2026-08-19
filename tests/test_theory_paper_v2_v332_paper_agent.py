from __future__ import annotations

import io
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AttentionRequest,
)
from trade_system.theory_paper_v2.presentation import paper_agent


class V332PaperAgentCliTests(unittest.TestCase):
    _THREAD_ID = "019ffb95-4195-7292-8a44-9870151a97f5"
    _GOAL_ID = f"codex-thread:{_THREAD_ID}"

    def test_parser_exposes_only_run_identity_and_decision_cycle(self) -> None:
        parsed = paper_agent._parser().parse_args(
            [
                "--runtime-root",
                "/tmp/v332-run",
                "--theory-package",
                "/tmp/v332-theory",
                "commit",
                "decision-1",
            ]
        )
        self.assertEqual(
            {
                "runtime_root": Path("/tmp/v332-run"),
                "theory_package": Path("/tmp/v332-theory"),
                "command": "commit",
                "decision_cycle_id": "decision-1",
            },
            vars(parsed),
        )
        prepared = paper_agent._parser().parse_args(
            [
                "--runtime-root",
                "/tmp/v332-run",
                "prepare",
                "decision-1",
            ]
        )
        self.assertEqual("prepare", prepared.command)
        self.assertEqual("decision-1", prepared.decision_cycle_id)
        processed = paper_agent._parser().parse_args(
            [
                "--runtime-root",
                "/tmp/v332-run",
                "process",
                "market-cycle-1",
            ]
        )
        self.assertEqual("process", processed.command)
        self.assertEqual("market-cycle-1", processed.cycle_id)
        setup = paper_agent._parser().parse_args(
            ["--runtime-root", "/tmp/v332-run", "setup"]
        )
        self.assertEqual("setup", setup.command)
        self.assertNotIn("physical_task_id", vars(setup))
        self.assertNotIn("continuity_nonce", vars(setup))
        checkpoint = paper_agent._parser().parse_args(
            [
                "--runtime-root",
                "/tmp/v332-run",
                "checkpoint",
                "/tmp/attention-request.json",
            ]
        )
        self.assertEqual(
            {
                "runtime_root": Path("/tmp/v332-run"),
                "theory_package": paper_agent._DEFAULT_V332_THEORY_PACKAGE,
                "command": "checkpoint",
                "attention_request_path": Path("/tmp/attention-request.json"),
            },
            vars(checkpoint),
        )
        forbidden = (
            "action",
            "side",
            "qty",
            "price",
            "account",
            "time",
            "execution-ref",
            "approve",
            "override",
            "physical-task-id",
            "continuity-nonce",
            "registered-at",
            "opened-at",
            "account-id",
            "accepted-at",
            "issued-at",
            "schedule",
            "wake",
        )
        routes = (
            ("commit", "decision-1"),
            ("checkpoint", "/tmp/attention-request.json"),
        )
        for route, positional in routes:
            for option in forbidden:
                with self.subTest(route=route, option=option):
                    with (
                        mock.patch.object(
                            paper_agent.sys, "stderr", io.StringIO()
                        ),
                        self.assertRaises(SystemExit),
                    ):
                        paper_agent._parser().parse_args(
                            [
                                "--runtime-root",
                                "/tmp/v332-run",
                                route,
                                positional,
                                f"--{option}",
                                "caller-value",
                            ]
                        )

    def test_public_entrypoint_has_only_identity_inputs(self) -> None:
        setup_signature = inspect.signature(paper_agent.setup_paper_account)
        self.assertEqual(
            ["runtime_root", "theory_package"],
            list(setup_signature.parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in setup_signature.parameters.values()
            )
        )
        for entrypoint in (
            paper_agent.prepare_paper_action,
            paper_agent.commit_paper_action,
        ):
            signature = inspect.signature(entrypoint)
            self.assertEqual(
                ["runtime_root", "theory_package", "decision_cycle_id"],
                list(signature.parameters),
            )
            self.assertTrue(
                all(
                    parameter.kind is inspect.Parameter.KEYWORD_ONLY
                    for parameter in signature.parameters.values()
                )
            )
        process_signature = inspect.signature(paper_agent.process_market_cycle)
        self.assertEqual(
            ["runtime_root", "theory_package", "cycle_id"],
            list(process_signature.parameters),
        )
        self.assertNotIn("granularity", process_signature.parameters)
        self.assertNotIn("action", process_signature.parameters)
        self.assertNotIn("coverage_end_at", process_signature.parameters)
        self.assertNotIn("funding_rate", process_signature.parameters)
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in process_signature.parameters.values()
            )
        )
        checkpoint_signature = inspect.signature(
            paper_agent.submit_attention_checkpoint
        )
        self.assertEqual(
            ["runtime_root", "theory_package", "attention_request_path"],
            list(checkpoint_signature.parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in checkpoint_signature.parameters.values()
            )
        )
        with self.assertRaises(TypeError):
            paper_agent.commit_paper_action(
                runtime_root=Path("/tmp/v332-run"),
                theory_package=Path("/tmp/v332-theory"),
                decision_cycle_id="decision-1",
                action="OPEN",  # type: ignore[call-arg]
            )

    def test_public_entrypoint_uses_replay_policy_and_only_action_port(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            experiment_policy=SimpleNamespace(
                paper_account={"setup_cycle_id": "sealed-paper-setup"}
            )
        )
        paper_runtime = mock.Mock()
        paper_runtime._registered_goal_identity.return_value = self._GOAL_ID
        result = {
            "status": "COMMITTED",
            "physical_goal_id": "codex:/root/hype-paper-agent",
        }
        port = mock.Mock()
        port.commit_paper_action.return_value = result

        with (
            mock.patch.object(
                paper_agent,
                "build_market_cycle_runtime",
                return_value=runtime,
            ) as build,
            mock.patch.object(
                paper_agent,
                "V332HypePaperRuntime",
                return_value=paper_runtime,
            ) as compose,
            mock.patch.object(
                paper_agent,
                "V332AgentPaperActionPort",
                return_value=port,
            ) as port_type,
            mock.patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": self._THREAD_ID},
                clear=True,
            ),
        ):
            returned = paper_agent.commit_paper_action(
                runtime_root=Path("/tmp/v332-run"),
                theory_package=Path("/tmp/v332-theory"),
                decision_cycle_id="decision-1",
            )

        self.assertEqual(result, returned)
        build.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=Path("/tmp/v332-theory"),
            expected_theory_identity=V332_THEORY_IDENTITY,
            allow_public_collection=False,
        )
        compose.assert_called_once_with(
            runtime,
            setup_cycle_id="sealed-paper-setup",
        )
        port_type.assert_called_once_with(paper_runtime)
        port.commit_paper_action.assert_called_once_with(
            decision_cycle_id="decision-1"
        )

    def test_setup_derives_goal_and_continuity_without_caller_controls(
        self,
    ) -> None:
        paper = mock.Mock()
        paper._runtime.run_manifest.run_id = "v332-run"
        paper._policy.policy_sha256 = "a" * 64
        paper.logical_agent_id = "hype-paper-agent"
        paper.agent_generation = 1
        account = SimpleNamespace(account_id="paper-hype", version=1)
        paper.setup.return_value = account
        paper._registered_goal_identity.return_value = self._GOAL_ID
        paper.status.return_value = {"ledger_head_record_sha256": "b" * 64}

        with (
            mock.patch.object(
                paper_agent, "_paper_runtime", return_value=paper
            ),
            mock.patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": self._THREAD_ID},
                clear=True,
            ),
        ):
            result = paper_agent.setup_paper_account(
                runtime_root=Path("/tmp/v332-run"),
                theory_package=Path("/tmp/v332-theory"),
            )

        paper.setup.assert_called_once_with()
        self.assertEqual("SETUP", result["status"])
        self.assertEqual(self._GOAL_ID, result["physical_goal_id"])
        self.assertFalse(result["external_orders_supported"])

    def test_goal_mismatch_rejects_before_direct_port_or_write(self) -> None:
        paper = mock.Mock()
        paper._registered_goal_identity.return_value = (
            "codex-thread:11111111-1111-1111-1111-111111111111"
        )
        with (
            mock.patch.object(
                paper_agent, "_paper_runtime", return_value=paper
            ),
            mock.patch.object(
                paper_agent, "V332AgentPaperActionPort"
            ) as port_type,
            mock.patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": self._THREAD_ID},
                clear=True,
            ),
            self.assertRaisesRegex(
                ValueError, "V332_PAPER_AGENT_CALLER_GOAL_MISMATCH"
            ),
        ):
            paper_agent.prepare_paper_action(
                runtime_root=Path("/tmp/v332-run"),
                theory_package=Path("/tmp/v332-theory"),
                decision_cycle_id="decision-1",
            )
        port_type.assert_not_called()
        paper.setup.assert_not_called()

    def test_missing_host_goal_identity_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ValueError, "V332_PAPER_AGENT_CODEX_THREAD_ID_REQUIRED"
            ):
                paper_agent._current_codex_goal_identity()

    def test_main_delegates_to_public_entrypoint_and_writes_canonical_json(
        self,
    ) -> None:
        result = {
            "status": "COMMITTED",
            "physical_goal_id": "codex:/root/hype-paper-agent",
        }
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(
                paper_agent,
                "commit_paper_action",
                return_value=result,
            ) as commit,
            mock.patch.object(paper_agent.sys, "stdout", output),
        ):
            returned = paper_agent.main(
                [
                    "--runtime-root",
                    "/tmp/v332-run",
                    "--theory-package",
                    "/tmp/v332-theory",
                    "commit",
                    "decision-1",
                ]
            )

        self.assertEqual(0, returned)
        commit.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=Path("/tmp/v332-theory"),
            decision_cycle_id="decision-1",
        )
        self.assertEqual(
            canonical_bytes(result) + b"\n", output.buffer.getvalue()
        )

    def test_main_prepare_delegates_without_trade_fields(self) -> None:
        result = {
            "status": "PREPARED",
            "physical_goal_id": "codex:/root/hype-paper-agent",
        }
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(
                paper_agent,
                "prepare_paper_action",
                return_value=result,
            ) as prepare,
            mock.patch.object(paper_agent.sys, "stdout", output),
        ):
            returned = paper_agent.main(
                [
                    "--runtime-root",
                    "/tmp/v332-run",
                    "prepare",
                    "decision-1",
                ]
            )
        self.assertEqual(0, returned)
        prepare.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=paper_agent._DEFAULT_V332_THEORY_PACKAGE,
            decision_cycle_id="decision-1",
        )
        self.assertEqual(
            canonical_bytes(result) + b"\n", output.buffer.getvalue()
        )

    def test_main_setup_has_no_identity_or_account_arguments(self) -> None:
        result = {
            "status": "SETUP",
            "physical_goal_id": self._GOAL_ID,
            "account_id": "paper-hype",
        }
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(
                paper_agent,
                "setup_paper_account",
                return_value=result,
            ) as setup,
            mock.patch.object(paper_agent.sys, "stdout", output),
        ):
            returned = paper_agent.main(
                ["--runtime-root", "/tmp/v332-run", "setup"]
            )
        self.assertEqual(0, returned)
        setup.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=paper_agent._DEFAULT_V332_THEORY_PACKAGE,
        )
        self.assertEqual(
            canonical_bytes(result) + b"\n", output.buffer.getvalue()
        )

    def test_main_process_delegates_without_fill_controls(self) -> None:
        result = {
            "status": "PROCESSED",
            "observation_kind": "QUOTE",
        }
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(
                paper_agent,
                "process_market_cycle",
                return_value=result,
            ) as process,
            mock.patch.object(paper_agent.sys, "stdout", output),
        ):
            returned = paper_agent.main(
                [
                    "--runtime-root",
                    "/tmp/v332-run",
                    "process",
                    "market-cycle-1",
                ]
            )
        self.assertEqual(0, returned)
        process.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=paper_agent._DEFAULT_V332_THEORY_PACKAGE,
            cycle_id="market-cycle-1",
        )
        self.assertEqual(
            canonical_bytes(result) + b"\n", output.buffer.getvalue()
        )

    def test_main_checkpoint_delegates_only_exact_request_path(self) -> None:
        result = {
            "status": "CHECKPOINTED",
            "request_sha256": "a" * 64,
        }
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(
                paper_agent,
                "submit_attention_checkpoint",
                return_value=result,
            ) as checkpoint,
            mock.patch.object(paper_agent.sys, "stdout", output),
        ):
            returned = paper_agent.main(
                [
                    "--runtime-root",
                    "/tmp/v332-run",
                    "checkpoint",
                    "/tmp/attention-request.json",
                ]
            )
        self.assertEqual(0, returned)
        checkpoint.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=paper_agent._DEFAULT_V332_THEORY_PACKAGE,
            attention_request_path=Path("/tmp/attention-request.json"),
        )
        self.assertEqual(
            canonical_bytes(result) + b"\n", output.buffer.getvalue()
        )

    def test_checkpoint_entrypoint_forwards_exact_canonical_agent_fact(self) -> None:
        request = AttentionRequest(
            request_id="attention-001",
            logical_agent_id="HYPE_CAPABILITY_TRADER",
            agent_generation=1,
            continuity_nonce="hype-continuity-g1",
            symbol="HYPE-USDT-SWAP",
            mode="WAKE_AFTER",
            issued_at="2026-08-13T12:00:20+00:00",
            continue_until=None,
            earliest_wake_at="2026-08-13T12:00:30+00:00",
            latest_useful_at="2026-08-13T12:01:00+00:00",
            reason_summary="The Goal selected its next observation window.",
            requested_focus="Re-evaluate the current hypothesis.",
            hypothesis_or_episode_ref="episode-001",
            position_and_open_order_ref="paper-account-001",
            data_cursor="cursor-001",
        )
        result = {
            "status": "CHECKPOINTED",
            "request_sha256": request.agent_owned_sha256,
        }
        runtime = mock.Mock()
        runtime.submit_goal_attention_checkpoint.return_value = result
        with (
            mock.patch.object(
                Path,
                "read_bytes",
                return_value=canonical_bytes(request.to_dict()) + b"\n",
            ),
            mock.patch.object(
                paper_agent,
                "build_market_cycle_runtime",
                return_value=runtime,
            ) as build,
        ):
            returned = paper_agent.submit_attention_checkpoint(
                runtime_root=Path("/tmp/v332-run"),
                theory_package=Path("/tmp/v332-theory"),
                attention_request_path=Path("/tmp/attention-request.json"),
            )
        self.assertEqual(result, returned)
        build.assert_called_once_with(
            runtime_root=Path("/tmp/v332-run"),
            theory_package=Path("/tmp/v332-theory"),
            expected_theory_identity=V332_THEORY_IDENTITY,
            allow_public_collection=False,
        )
        runtime.submit_goal_attention_checkpoint.assert_called_once_with(request)

    def test_commit_rejects_missing_frozen_paper_account(self) -> None:
        runtime = SimpleNamespace(
            experiment_policy=SimpleNamespace(paper_account=None)
        )
        with (
            mock.patch.object(
                paper_agent,
                "build_market_cycle_runtime",
                return_value=runtime,
            ),
            mock.patch.object(paper_agent, "V332HypePaperRuntime") as compose,
            mock.patch.object(paper_agent, "V332AgentPaperActionPort") as port,
        ):
            with self.assertRaisesRegex(
                ValueError, "V332_PAPER_AGENT_POLICY_ACCOUNT_REQUIRED"
            ):
                paper_agent.main(
                    [
                        "--runtime-root",
                        "/tmp/v332-run",
                        "commit",
                        "decision-1",
                    ]
                )
        compose.assert_not_called()
        port.assert_not_called()


if __name__ == "__main__":
    unittest.main()
