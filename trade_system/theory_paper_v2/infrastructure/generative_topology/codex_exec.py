"""Codex CLI ChatGPT-login transport for formal generative topology turns."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ...application.generative_topology_run import (
    ModelAttemptResult,
    ModelAttemptStatus,
    ModelCallRequest,
    ModelTransportCapability,
    UsageRecord,
)


EXPECTED_CODEX_CLI_VERSION = "codex-cli 0.146.0-alpha.3.1"
PROVIDER_TRANSPORT = "CODEX_EXEC_CHATGPT_LOGIN"


class CodexExecTransportError(ValueError):
    pass


def _event_is_tool_call(event: Mapping[str, Any]) -> str | None:
    if event.get("type") not in {"item.started", "item.completed"}:
        return None
    item = event.get("item")
    if not isinstance(item, Mapping):
        return None
    item_type = str(item.get("type", ""))
    if item_type in {"", "agent_message", "reasoning"}:
        return None
    tool_markers = (
        "tool",
        "command",
        "exec",
        "shell",
        "web_search",
        "mcp",
        "browser",
        "computer",
    )
    if any(marker in item_type for marker in tool_markers):
        return item_type
    return None


def parse_codex_exec_jsonl(
    raw_stdout: bytes,
) -> tuple[
    bytes | None,
    UsageRecord | None,
    tuple[str, ...],
    int,
    bool,
]:
    """Extract final bytes and usage while retaining stdout as authority."""

    output_text: str | None = None
    usage: UsageRecord | None = None
    tool_calls: list[str] = []
    retry_count = 0
    model_rerouted = False
    for line in raw_stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodexExecTransportError("CODEX_JSONL_INVALID") from exc
        if not isinstance(event, dict):
            raise CodexExecTransportError("CODEX_JSONL_EVENT_INVALID")
        event_type = event.get("type")
        if event_type == "item.completed":
            item = event.get("item")
            if (
                isinstance(item, dict)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                output_text = item["text"]
        if event_type == "turn.completed":
            raw_usage = event.get("usage")
            if not isinstance(raw_usage, dict):
                raise CodexExecTransportError(
                    "CODEX_USAGE_EVENT_INVALID"
                )
            try:
                input_tokens = int(raw_usage["input_tokens"])
                output_tokens = int(raw_usage["output_tokens"])
                cached_input_tokens = int(
                    raw_usage.get("cached_input_tokens", 0)
                )
                reasoning_output_tokens = int(
                    raw_usage.get("reasoning_output_tokens", 0)
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CodexExecTransportError(
                    "CODEX_USAGE_EVENT_INVALID"
                ) from exc
            usage = UsageRecord(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_output_tokens=reasoning_output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
        if event_type in {"stream_error", "retry"}:
            retry_count += 1
        if event_type == "model_reroute":
            model_rerouted = True
        tool_call = _event_is_tool_call(event)
        if tool_call is not None:
            tool_calls.append(tool_call)
    return (
        output_text.encode("utf-8") if output_text is not None else None,
        usage,
        tuple(tool_calls),
        retry_count,
        model_rerouted,
    )


class CodexExecGenerativeTransport:
    """Invoke one ephemeral, schema-constrained Codex turn."""

    def __init__(
        self,
        *,
        codex_binary: str | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[bytes]] = (
            subprocess.run
        ),
        capability_override: ModelTransportCapability | None = None,
    ) -> None:
        self._binary = codex_binary or shutil.which("codex")
        self._run = command_runner
        self._capability_override = capability_override

    def _probe(
        self, arguments: Sequence[str], *, timeout: int = 10
    ) -> subprocess.CompletedProcess[bytes] | None:
        if self._binary is None:
            return None
        try:
            return self._run(
                [self._binary, *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def capability(self) -> ModelTransportCapability:
        if self._capability_override is not None:
            return self._capability_override
        reasons: list[str] = []
        version = self._probe(("--version",))
        cli_version = (
            version.stdout.decode("utf-8", "replace").strip()
            if version is not None and version.returncode == 0
            else "UNAVAILABLE"
        )
        if version is None or version.returncode != 0:
            reasons.append("CODEX_CLI_UNAVAILABLE")
        elif cli_version != EXPECTED_CODEX_CLI_VERSION:
            reasons.append("CODEX_CLI_VERSION_MISMATCH")
        login = self._probe(("login", "status"))
        authenticated = bool(
            login is not None
            and login.returncode == 0
            and b"Logged in using ChatGPT" in login.stdout + login.stderr
        )
        if not authenticated:
            reasons.append("CODEX_CHATGPT_LOGIN_UNAVAILABLE")
        features = self._probe(("features", "list"))
        token_budget_available = bool(
            features is not None
            and features.returncode == 0
            and any(
                line.split(maxsplit=1)[0] == b"token_budget"
                for line in features.stdout.splitlines()
                if line.split(maxsplit=1)
            )
        )
        if not token_budget_available:
            reasons.append("CODEX_TOKEN_BUDGET_FEATURE_UNAVAILABLE")
        return ModelTransportCapability(
            adapter_id="CODEX_EXEC_GENERATIVE_TRANSPORT:1.0.0",
            transport_evidence_class="REAL_GENERATIVE",
            provider_transport=PROVIDER_TRANSPORT,
            cli_version=cli_version,
            authenticated=authenticated,
            real_generative=authenticated,
            ephemeral_sessions=True,
            read_only_workspace=True,
            empty_temporary_workspace=True,
            tool_calls_detectable=True,
            usage_available=True,
            hard_token_limit_available=token_budget_available,
            served_model_attestation_available=False,
            reason_codes=tuple(reasons),
        )

    def invoke(self, request: ModelCallRequest) -> ModelAttemptResult:
        if self._binary is None:
            return ModelAttemptResult(
                status=ModelAttemptStatus.PROVIDER_ERROR,
                raw_event_bytes=b"",
                raw_stderr_bytes=b"",
                raw_output_bytes=None,
                requested_model=request.model,
                served_model_attestation=None,
                usage=None,
                tool_call_names=(),
                retry_count=0,
                latency_ms=0,
                error_code="CODEX_CLI_UNAVAILABLE",
            )
        started = time.monotonic()
        with (
            tempfile.TemporaryDirectory(
                prefix="ta2-codex-empty-workspace-"
            ) as workspace,
            tempfile.TemporaryDirectory(
                prefix="ta2-codex-output-schema-"
            ) as schema_directory,
        ):
            schema_path = Path(schema_directory) / "output.schema.json"
            schema_path.write_bytes(request.semantic_output_schema_bytes)
            command = [
                self._binary,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--json",
                "--model",
                request.model,
                "-c",
                f'model_reasoning_effort="{request.reasoning_effort}"',
                "--enable",
                "token_budget",
                "-c",
                f"token_budget.limit_tokens={request.token_limit}",
                "--sandbox",
                "read-only",
                "--cd",
                workspace,
                "--output-schema",
                str(schema_path),
                "-",
            ]
            try:
                completed = self._run(
                    command,
                    input=request.provider_input_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=request.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                return ModelAttemptResult(
                    status=ModelAttemptStatus.TIMEOUT,
                    raw_event_bytes=(
                        exc.stdout
                        if isinstance(exc.stdout, bytes)
                        else b""
                    ),
                    raw_stderr_bytes=(
                        exc.stderr
                        if isinstance(exc.stderr, bytes)
                        else b""
                    ),
                    raw_output_bytes=None,
                    requested_model=request.model,
                    served_model_attestation=None,
                    usage=None,
                    tool_call_names=(),
                    retry_count=0,
                    latency_ms=latency_ms,
                    error_code="CODEX_EXEC_TIMEOUT",
                )
            latency_ms = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            return ModelAttemptResult(
                status=ModelAttemptStatus.PROVIDER_ERROR,
                raw_event_bytes=completed.stdout,
                raw_stderr_bytes=completed.stderr,
                raw_output_bytes=None,
                requested_model=request.model,
                served_model_attestation=None,
                usage=None,
                tool_call_names=(),
                retry_count=0,
                latency_ms=latency_ms,
                error_code=f"CODEX_EXEC_NONZERO:{completed.returncode}",
            )
        try:
            (
                output,
                usage,
                tool_calls,
                retry_count,
                model_rerouted,
            ) = parse_codex_exec_jsonl(completed.stdout)
        except CodexExecTransportError as exc:
            return ModelAttemptResult(
                status=ModelAttemptStatus.PROVIDER_ERROR,
                raw_event_bytes=completed.stdout,
                raw_stderr_bytes=completed.stderr,
                raw_output_bytes=None,
                requested_model=request.model,
                served_model_attestation=None,
                usage=None,
                tool_call_names=(),
                retry_count=0,
                latency_ms=latency_ms,
                error_code=str(exc),
            )
        if output is None:
            return ModelAttemptResult(
                status=ModelAttemptStatus.PROVIDER_ERROR,
                raw_event_bytes=completed.stdout,
                raw_stderr_bytes=completed.stderr,
                raw_output_bytes=None,
                requested_model=request.model,
                served_model_attestation=None,
                usage=usage,
                tool_call_names=tool_calls,
                retry_count=retry_count,
                latency_ms=latency_ms,
                error_code="CODEX_AGENT_MESSAGE_MISSING",
                model_rerouted=model_rerouted,
            )
        return ModelAttemptResult(
            status=ModelAttemptStatus.COMPLETE,
            raw_event_bytes=completed.stdout,
            raw_stderr_bytes=completed.stderr,
            raw_output_bytes=output,
            requested_model=request.model,
            served_model_attestation=None,
            usage=usage,
            tool_call_names=tool_calls,
            retry_count=retry_count,
            latency_ms=latency_ms,
            model_rerouted=model_rerouted,
        )


__all__ = [
    "CodexExecGenerativeTransport",
    "CodexExecTransportError",
    "EXPECTED_CODEX_CLI_VERSION",
    "PROVIDER_TRANSPORT",
    "parse_codex_exec_jsonl",
]
