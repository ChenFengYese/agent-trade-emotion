from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from trade_system.theory_paper_v2.application.generative_topology_run import (
    ModelAttemptStatus,
    ModelCallRequest,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
)
from trade_system.theory_paper_v2.infrastructure.generative_topology.codex_app_server import (
    ADAPTER_ID,
    PROVIDER_TRANSPORT,
    CodexAppServerGenerativeTransport,
    RawAppServerSession,
    _app_server_command,
    _thread_start_request,
    _turn_start_request,
    parse_codex_app_server_jsonl,
)


def _request(*, token_limit: int = 30_000) -> ModelCallRequest:
    prompt = b"Return the bounded semantic JSON only."
    return ModelCallRequest(
        paired_session_id="paired-001",
        topology_id="SINGLE_STRONG",
        turn_ordinal=0,
        phase_id="PROPOSE",
        role_id="PROPOSER",
        expected_output_kind="PROPOSAL",
        provider_input_bytes=prompt,
        provider_input_digest=hashlib.sha256(prompt).hexdigest(),
        semantic_output_schema_bytes=canonical_bytes(
            {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                },
                "required": ["answer"],
                "additionalProperties": False,
            }
        ),
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        token_limit=token_limit,
        timeout_seconds=120,
    )


def _event(value: dict) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
    ).encode() + b"\n"


def _transcript(
    *,
    total_tokens: int = 11_755,
    model: str = "gpt-5.6-sol",
    provider: str = "openai",
    effort: str = "medium",
    instruction_sources: list[str] | None = None,
    ephemeral: bool = True,
    turn_status: str = "completed",
    turn_error: str | None = None,
    reroute: bool = False,
    include_output: bool = True,
    include_usage: bool = True,
    tool_item: str | None = None,
) -> bytes:
    rows = [
        {"id": 1, "result": {"userAgent": "fixture"}},
        {
            "id": 2,
            "result": {
                "thread": {
                    "id": "thr_fixture",
                    "ephemeral": ephemeral,
                    "modelProvider": provider,
                },
                "model": model,
                "modelProvider": provider,
                "reasoningEffort": effort,
                "instructionSources": (
                    []
                    if instruction_sources is None
                    else instruction_sources
                ),
            },
        },
        {
            "id": 3,
            "result": {
                "turn": {
                    "id": "turn_fixture",
                    "status": "inProgress",
                }
            },
        },
    ]
    if reroute:
        rows.append(
            {
                "method": "model/rerouted",
                "params": {
                    "threadId": "thr_fixture",
                    "turnId": "turn_fixture",
                    "fromModel": model,
                    "toModel": "fallback-model",
                    "reason": "fixture",
                },
            }
        )
    if tool_item is not None:
        rows.append(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "id": "tool_fixture",
                        "type": tool_item,
                    }
                },
            }
        )
    if include_output:
        rows.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "id": "answer_fixture",
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"answer":"bounded"}',
                    }
                },
            }
        )
    if include_usage:
        rows.append(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thr_fixture",
                    "turnId": "turn_fixture",
                    "tokenUsage": {
                        "last": {
                            "inputTokens": max(total_tokens - 100, 0),
                            "cachedInputTokens": 0,
                            "outputTokens": min(total_tokens, 100),
                            "reasoningOutputTokens": 50,
                            "totalTokens": total_tokens,
                        },
                        "total": {
                            "inputTokens": max(total_tokens - 100, 0),
                            "cachedInputTokens": 0,
                            "outputTokens": min(total_tokens, 100),
                            "reasoningOutputTokens": 50,
                            "totalTokens": total_tokens,
                        },
                    },
                },
            }
        )
    error = (
        None
        if turn_error is None
        else {
            "message": "fixture turn failure",
            "codexErrorInfo": turn_error,
        }
    )
    rows.append(
        {
            "method": "turn/completed",
            "params": {
                "turn": {
                    "id": "turn_fixture",
                    "status": turn_status,
                    "error": error,
                    "items": [],
                }
            },
        }
    )
    return b"".join(_event(item) for item in rows)


class CodexAppServerTransportTests(unittest.TestCase):
    def test_exact_rollout_cap_and_rpc_requests_are_fail_closed(self):
        request = _request()
        command = _app_server_command("/fixture/codex", 30_000)
        self.assertEqual(
            [
                "/fixture/codex",
                "app-server",
                "--stdio",
                "--strict-config",
                "-c",
                "allow_provider_model_fallback=false",
                "-c",
                (
                    "features.rollout_budget={enabled=true,"
                    "limit_tokens=30000,"
                    "reminder_at_remaining_tokens=[15000],"
                    "sampling_token_weight=1.0,"
                    "prefill_token_weight=1.0}"
                ),
            ],
            command,
        )
        thread = _thread_start_request(request, "/empty")
        self.assertIs(True, thread["params"]["ephemeral"])
        self.assertEqual("read-only", thread["params"]["sandbox"])
        self.assertEqual("never", thread["params"]["approvalPolicy"])
        self.assertIs(
            False,
            thread["params"]["allowProviderModelFallback"],
        )
        self.assertIs(
            False,
            thread["params"]["config"][
                "allow_provider_model_fallback"
            ],
        )
        turn = _turn_start_request(
            request,
            thread_id="thr",
            workspace="/empty",
        )
        self.assertEqual(
            {"type": "readOnly", "networkAccess": False},
            turn["params"]["sandboxPolicy"],
        )
        self.assertEqual("medium", turn["params"]["effort"])
        self.assertEqual(
            request.provider_input_bytes.decode(),
            turn["params"]["input"][0]["text"],
        )

    def test_capability_uses_version_login_and_app_server_not_feature_name(
        self,
    ):
        observed: list[tuple[str, ...]] = []

        def runner(command, **kwargs):
            observed.append(tuple(command[1:]))
            if command[-1] == "--version":
                stdout = b"codex-cli 0.146.0-alpha.3.1\n"
            elif command[-2:] == ["login", "status"]:
                stdout = b"Logged in using ChatGPT\n"
            elif command[-2:] == ["app-server", "--help"]:
                stdout = b"Usage: codex app-server --stdio --strict-config\n"
            else:
                raise AssertionError(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=stdout,
                stderr=b"",
            )

        capability = CodexAppServerGenerativeTransport(
            codex_binary="/fixture/codex",
            probe_runner=runner,
        ).capability()
        self.assertEqual(ADAPTER_ID, capability.adapter_id)
        self.assertEqual(
            PROVIDER_TRANSPORT,
            capability.provider_transport,
        )
        self.assertTrue(capability.real_generative)
        self.assertTrue(capability.hard_token_limit_available)
        self.assertTrue(
            capability.served_model_attestation_available
        )
        self.assertEqual((), capability.reason_codes)
        self.assertNotIn(("features", "list"), observed)

    def test_parser_records_effective_config_usage_reroute_and_tool(self):
        parsed = parse_codex_app_server_jsonl(
            _transcript(reroute=True, tool_item="commandExecution")
        )
        self.assertEqual("gpt-5.6-sol", parsed.effective_model)
        self.assertEqual("openai", parsed.effective_provider)
        self.assertEqual("medium", parsed.effective_reasoning_effort)
        self.assertEqual((), parsed.instruction_sources)
        self.assertIs(True, parsed.ephemeral_thread)
        self.assertEqual(11_755, parsed.usage.total_tokens)
        self.assertEqual(
            ("commandExecution",),
            parsed.tool_call_names,
        )
        self.assertTrue(parsed.model_rerouted)
        self.assertEqual("completed", parsed.turn_status)

    def test_invoke_attests_effective_model_and_preserves_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = Path(directory) / "auth.json"
            auth.write_text('{"fixture":"chatgpt"}')
            captured: dict = {}

            def session_runner(**kwargs):
                captured.update(kwargs)
                home = Path(kwargs["env"]["CODEX_HOME"])
                workspace = Path(kwargs["cwd"])
                self.assertEqual(["auth.json"], [p.name for p in home.iterdir()])
                self.assertTrue((home / "auth.json").is_symlink())
                self.assertEqual([], list(workspace.iterdir()))
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                self.assertNotIn("CODEX_API_KEY", kwargs["env"])
                self.assertNotIn("CODEX_ACCESS_TOKEN", kwargs["env"])
                return RawAppServerSession(
                    stdout=_transcript(),
                    stderr=b"retained warning\n",
                )

            result = CodexAppServerGenerativeTransport(
                codex_binary="/fixture/codex",
                auth_json_path=auth,
                session_runner=session_runner,
            ).invoke(_request())

        self.assertEqual(ModelAttemptStatus.COMPLETE, result.status)
        self.assertEqual(b'{"answer":"bounded"}', result.raw_output_bytes)
        self.assertEqual(11_755, result.usage.total_tokens)
        self.assertEqual(b"retained warning\n", result.raw_stderr_bytes)
        attestation = json.loads(result.served_model_attestation)
        self.assertEqual("gpt-5.6-sol", attestation["model"])
        self.assertEqual("openai", attestation["provider"])
        self.assertEqual("medium", attestation["reasoning_effort"])
        self.assertIs(
            False,
            attestation["allow_provider_model_fallback"],
        )
        self.assertIn(
            "features.rollout_budget={enabled=true",
            captured["command"][-1],
        )

    def test_default_stdio_driver_completes_json_rpc_lifecycle(self):
        fixture_server = r"""
import json
import sys

def send(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        send({"id": message["id"], "result": {"userAgent": "fixture"}})
    elif method == "thread/start":
        params = message["params"]
        send({
            "id": message["id"],
            "result": {
                "thread": {
                    "id": "thr_fixture",
                    "ephemeral": params["ephemeral"],
                    "modelProvider": "openai",
                },
                "model": params["model"],
                "modelProvider": "openai",
                "reasoningEffort": params["config"]["model_reasoning_effort"],
                "instructionSources": [],
            },
        })
    elif method == "turn/start":
        send({
            "id": message["id"],
            "result": {
                "turn": {"id": "turn_fixture", "status": "inProgress"}
            },
        })
        send({
            "method": "item/completed",
            "params": {
                "item": {
                    "id": "answer",
                    "type": "agentMessage",
                    "text": '{"answer":"stdio"}',
                }
            },
        })
        usage = {
            "inputTokens": 900,
            "cachedInputTokens": 0,
            "outputTokens": 100,
            "reasoningOutputTokens": 50,
            "totalTokens": 1000,
        }
        send({
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thr_fixture",
                "turnId": "turn_fixture",
                "tokenUsage": {"last": usage, "total": usage},
            },
        })
        send({
            "method": "turn/completed",
            "params": {
                "turn": {
                    "id": "turn_fixture",
                    "status": "completed",
                    "error": None,
                    "items": [],
                }
            },
        })
"""

        def process_factory(_command, **kwargs):
            return subprocess.Popen(
                [sys.executable, "-u", "-c", fixture_server],
                **kwargs,
            )

        with tempfile.TemporaryDirectory() as directory:
            auth = Path(directory) / "auth.json"
            auth.write_text('{"fixture":"chatgpt"}')
            result = CodexAppServerGenerativeTransport(
                codex_binary="/fixture/codex",
                auth_json_path=auth,
                process_factory=process_factory,
            ).invoke(_request())
        self.assertEqual(ModelAttemptStatus.COMPLETE, result.status)
        self.assertEqual(b'{"answer":"stdio"}', result.raw_output_bytes)
        self.assertEqual(1000, result.usage.total_tokens)
        self.assertIn(b'"method":"turn/completed"', result.raw_event_bytes)

    def test_complete_is_forbidden_when_usage_exceeds_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = Path(directory) / "auth.json"
            auth.write_text('{"fixture":"chatgpt"}')

            def session_runner(**kwargs):
                return RawAppServerSession(
                    stdout=_transcript(total_tokens=30_001),
                    stderr=b"",
                )

            result = CodexAppServerGenerativeTransport(
                codex_binary="/fixture/codex",
                auth_json_path=auth,
                session_runner=session_runner,
            ).invoke(_request(token_limit=30_000))

        self.assertEqual(
            ModelAttemptStatus.PROVIDER_ERROR,
            result.status,
        )
        self.assertEqual(
            "CODEX_APP_SERVER_TOKEN_BUDGET_EXCEEDED",
            result.error_code,
        )
        self.assertEqual(30_001, result.usage.total_tokens)

    def test_session_budget_exhaustion_and_reroute_are_not_complete(self):
        cases = (
            (
                _transcript(
                    turn_status="failed",
                    turn_error="sessionBudgetExceeded",
                    include_output=False,
                    include_usage=False,
                ),
                "CODEX_APP_SERVER_SESSION_BUDGET_EXCEEDED",
                False,
            ),
            (
                _transcript(reroute=True),
                "CODEX_APP_SERVER_MODEL_REROUTED",
                True,
            ),
        )
        for transcript, expected_code, expected_reroute in cases:
            with (
                self.subTest(expected_code),
                tempfile.TemporaryDirectory() as directory,
            ):
                auth = Path(directory) / "auth.json"
                auth.write_text('{"fixture":"chatgpt"}')

                def session_runner(**kwargs):
                    return RawAppServerSession(
                        stdout=transcript,
                        stderr=b"",
                    )

                result = CodexAppServerGenerativeTransport(
                    codex_binary="/fixture/codex",
                    auth_json_path=auth,
                    session_runner=session_runner,
                ).invoke(_request())
            self.assertEqual(
                ModelAttemptStatus.PROVIDER_ERROR,
                result.status,
            )
            self.assertEqual(expected_code, result.error_code)
            self.assertIs(expected_reroute, result.model_rerouted)

    def test_instructions_or_effective_model_mismatch_fail_attestation(self):
        cases = (
            _transcript(model="fallback-model"),
            _transcript(instruction_sources=["/hidden/AGENTS.md"]),
            _transcript(ephemeral=False),
        )
        for transcript in cases:
            with self.subTest(), tempfile.TemporaryDirectory() as directory:
                auth = Path(directory) / "auth.json"
                auth.write_text('{"fixture":"chatgpt"}')

                def session_runner(**kwargs):
                    return RawAppServerSession(
                        stdout=transcript,
                        stderr=b"",
                    )

                result = CodexAppServerGenerativeTransport(
                    codex_binary="/fixture/codex",
                    auth_json_path=auth,
                    session_runner=session_runner,
                ).invoke(_request())
            self.assertEqual(
                "CODEX_APP_SERVER_EFFECTIVE_CONFIG_NOT_ATTESTED",
                result.error_code,
            )
            self.assertEqual(
                ModelAttemptStatus.PROVIDER_ERROR,
                result.status,
            )


if __name__ == "__main__":
    unittest.main()
