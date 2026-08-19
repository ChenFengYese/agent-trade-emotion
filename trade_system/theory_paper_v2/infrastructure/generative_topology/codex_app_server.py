"""Attested Codex app-server transport for one bounded generative turn.

The adapter is deliberately separate from the legacy ``codex exec`` transport.
It uses the app-server stdio JSON-RPC protocol so the effective model, provider,
and reasoning effort come from the server response.  A per-call isolated
``CODEX_HOME`` exposes only the existing ChatGPT ``auth.json`` and the model
turn runs in an empty, read-only temporary working directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from ...application.generative_topology_run import (
    ModelAttemptResult,
    ModelAttemptStatus,
    ModelCallRequest,
    ModelTransportCapability,
    UsageRecord,
)


EXPECTED_CODEX_CLI_VERSION = "codex-cli 0.146.0-alpha.3.1"
ADAPTER_ID = (
    "CODEX_APP_SERVER_GENERATIVE_TRANSPORT:"
    "1.0.0-ROLLOUT-BUDGET-ATTESTED"
)
PROVIDER_TRANSPORT = "CODEX_APP_SERVER_CHATGPT_LOGIN"

_INITIALIZE_REQUEST_ID = 1
_THREAD_START_REQUEST_ID = 2
_TURN_START_REQUEST_ID = 3
_CLIENT_INFO = {
    "name": "theory_agent_v2_formal_e0",
    "title": "Theory Agent V2 Formal E0",
    "version": "1.0.0",
}
_TOOL_ITEM_TYPES = {
    "commandExecution",
    "fileChange",
    "mcpToolCall",
    "dynamicToolCall",
    "collabAgentToolCall",
    "webSearch",
    "imageView",
    "imageGeneration",
    "sleep",
}


class CodexAppServerTransportError(ValueError):
    """A fail-closed app-server protocol or attestation error."""


@dataclass(frozen=True, slots=True)
class RawAppServerSession:
    """Exact process streams returned by one isolated app-server session."""

    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    launch_error: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedAppServerSession:
    """Fields derived from retained JSON-RPC stdout."""

    output: bytes | None
    usage: UsageRecord | None
    tool_call_names: tuple[str, ...]
    retry_count: int
    model_rerouted: bool
    effective_model: str | None
    effective_provider: str | None
    effective_reasoning_effort: str | None
    instruction_sources: tuple[str, ...] | None
    ephemeral_thread: bool | None
    turn_status: str | None
    turn_error_code: str | None


def _json_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _decode_event(line: bytes) -> Mapping[str, Any]:
    try:
        event = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_JSONL_INVALID"
        ) from exc
    if not isinstance(event, dict):
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_JSONL_EVENT_INVALID"
        )
    return event


def _usage_from_notification(
    params: Mapping[str, Any],
) -> UsageRecord:
    token_usage = params.get("tokenUsage")
    if not isinstance(token_usage, Mapping):
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_USAGE_EVENT_INVALID"
        )
    last = token_usage.get("last")
    if not isinstance(last, Mapping):
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_USAGE_EVENT_INVALID"
        )
    try:
        input_tokens = int(last["inputTokens"])
        cached_input_tokens = int(last.get("cachedInputTokens", 0))
        output_tokens = int(last["outputTokens"])
        reasoning_output_tokens = int(
            last.get("reasoningOutputTokens", 0)
        )
        total_tokens = int(last["totalTokens"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_USAGE_EVENT_INVALID"
        ) from exc
    return UsageRecord(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
    )


def _turn_error_code(turn: Mapping[str, Any]) -> str | None:
    error = turn.get("error")
    if not isinstance(error, Mapping):
        return None
    info = error.get("codexErrorInfo")
    if isinstance(info, str) and info:
        return info
    if isinstance(info, Mapping) and len(info) == 1:
        return str(next(iter(info)))
    return "unknown"


def _is_server_tool_request(event: Mapping[str, Any]) -> str | None:
    if "id" not in event or "result" in event or "error" in event:
        return None
    method = event.get("method")
    if not isinstance(method, str):
        return None
    lowered = method.casefold()
    if any(
        marker in lowered
        for marker in (
            "approval",
            "tool/",
            "mcp",
            "elicitation",
            "requestuserinput",
        )
    ):
        return method
    return None


def parse_codex_app_server_jsonl(
    raw_stdout: bytes,
) -> ParsedAppServerSession:
    """Parse an exact app-server transcript without discarding raw authority."""

    output: bytes | None = None
    usage: UsageRecord | None = None
    tools: list[str] = []
    retry_count = 0
    model_rerouted = False
    effective_model: str | None = None
    effective_provider: str | None = None
    effective_effort: str | None = None
    instruction_sources: tuple[str, ...] | None = None
    ephemeral: bool | None = None
    turn_status: str | None = None
    turn_error: str | None = None

    for line in raw_stdout.splitlines():
        if not line.strip():
            continue
        event = _decode_event(line)
        if event.get("id") == _THREAD_START_REQUEST_ID:
            result = event.get("result")
            if not isinstance(result, Mapping):
                continue
            effective_model = (
                str(result["model"])
                if isinstance(result.get("model"), str)
                else None
            )
            effective_provider = (
                str(result["modelProvider"])
                if isinstance(result.get("modelProvider"), str)
                else None
            )
            effective_effort = (
                str(result["reasoningEffort"])
                if isinstance(result.get("reasoningEffort"), str)
                else None
            )
            sources = result.get("instructionSources")
            if isinstance(sources, list) and all(
                isinstance(item, str) for item in sources
            ):
                instruction_sources = tuple(sources)
            thread = result.get("thread")
            if isinstance(thread, Mapping) and isinstance(
                thread.get("ephemeral"), bool
            ):
                ephemeral = bool(thread["ephemeral"])

        method = event.get("method")
        params = event.get("params")
        if method == "item/completed" and isinstance(params, Mapping):
            item = params.get("item")
            if isinstance(item, Mapping):
                item_type = item.get("type")
                if (
                    item_type == "agentMessage"
                    and isinstance(item.get("text"), str)
                ):
                    output = str(item["text"]).encode("utf-8")
                elif (
                    isinstance(item_type, str)
                    and item_type in _TOOL_ITEM_TYPES
                    and item_type not in tools
                ):
                    tools.append(item_type)
        elif method == "item/started" and isinstance(params, Mapping):
            item = params.get("item")
            if isinstance(item, Mapping):
                item_type = item.get("type")
                if (
                    isinstance(item_type, str)
                    and item_type in _TOOL_ITEM_TYPES
                    and item_type not in tools
                ):
                    tools.append(item_type)
        elif (
            method == "thread/tokenUsage/updated"
            and isinstance(params, Mapping)
        ):
            usage = _usage_from_notification(params)
        elif method == "model/rerouted":
            model_rerouted = True
        elif method == "turn/completed" and isinstance(params, Mapping):
            turn = params.get("turn")
            if isinstance(turn, Mapping):
                turn_status = (
                    str(turn["status"])
                    if isinstance(turn.get("status"), str)
                    else None
                )
                turn_error = _turn_error_code(turn)
        if isinstance(method, str) and "retry" in method.casefold():
            retry_count += 1
        server_tool = _is_server_tool_request(event)
        if server_tool is not None and server_tool not in tools:
            tools.append(server_tool)

    return ParsedAppServerSession(
        output=output,
        usage=usage,
        tool_call_names=tuple(tools),
        retry_count=retry_count,
        model_rerouted=model_rerouted,
        effective_model=effective_model,
        effective_provider=effective_provider,
        effective_reasoning_effort=effective_effort,
        instruction_sources=instruction_sources,
        ephemeral_thread=ephemeral,
        turn_status=turn_status,
        turn_error_code=turn_error,
    )


def _rollout_budget_config(token_limit: int) -> str:
    if type(token_limit) is not int or token_limit < 2:
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_TOKEN_LIMIT_INVALID"
        )
    reminder = token_limit // 2
    return (
        "features.rollout_budget={"
        "enabled=true,"
        f"limit_tokens={token_limit},"
        f"reminder_at_remaining_tokens=[{reminder}],"
        "sampling_token_weight=1.0,"
        "prefill_token_weight=1.0"
        "}"
    )


def _app_server_command(binary: str, token_limit: int) -> list[str]:
    return [
        binary,
        "app-server",
        "--stdio",
        "--strict-config",
        "-c",
        "allow_provider_model_fallback=false",
        "-c",
        _rollout_budget_config(token_limit),
    ]


def _thread_start_request(
    request: ModelCallRequest,
    workspace: str,
) -> Mapping[str, Any]:
    return {
        "method": "thread/start",
        "id": _THREAD_START_REQUEST_ID,
        "params": {
            "model": request.model,
            "cwd": workspace,
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "ephemeral": True,
            "allowProviderModelFallback": False,
            "config": {
                "model_reasoning_effort": request.reasoning_effort,
                "allow_provider_model_fallback": False,
            },
            "serviceName": "theory_agent_v2_formal_e0",
        },
    }


def _turn_start_request(
    request: ModelCallRequest,
    *,
    thread_id: str,
    workspace: str,
) -> Mapping[str, Any]:
    try:
        prompt = request.provider_input_bytes.decode("utf-8")
        output_schema = json.loads(request.semantic_output_schema_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_REQUEST_BYTES_INVALID"
        ) from exc
    if not isinstance(output_schema, dict):
        raise CodexAppServerTransportError(
            "CODEX_APP_SERVER_OUTPUT_SCHEMA_INVALID"
        )
    return {
        "method": "turn/start",
        "id": _TURN_START_REQUEST_ID,
        "params": {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
            "cwd": workspace,
            "approvalPolicy": "never",
            "sandboxPolicy": {
                "type": "readOnly",
                "networkAccess": False,
            },
            "model": request.model,
            "effort": request.reasoning_effort,
            "outputSchema": output_schema,
        },
    }


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.stdin is not None:
            process.stdin.close()
    except OSError:
        pass
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_stdio_app_server(
    *,
    command: Sequence[str],
    env: Mapping[str, str],
    cwd: str,
    request: ModelCallRequest,
    timeout_seconds: int,
    process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> RawAppServerSession:
    """Drive one app-server connection using newline-delimited JSON-RPC."""

    try:
        process = process_factory(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=dict(env),
            bufsize=0,
            start_new_session=True,
        )
    except OSError as exc:
        return RawAppServerSession(
            stdout=b"",
            stderr=str(exc).encode("utf-8", "replace"),
            launch_error="CODEX_APP_SERVER_LAUNCH_FAILED",
        )
    if (
        process.stdin is None
        or process.stdout is None
        or process.stderr is None
    ):
        _terminate_process(process)
        return RawAppServerSession(
            stdout=b"",
            stderr=b"",
            launch_error="CODEX_APP_SERVER_PIPE_UNAVAILABLE",
        )

    stdout_queue: queue.Queue[bytes | None] = queue.Queue()
    stderr_chunks: list[bytes] = []

    def read_stdout() -> None:
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                stdout_queue.put(line)
        finally:
            stdout_queue.put(None)

    def read_stderr() -> None:
        while True:
            chunk = process.stderr.read(8192)
            if not chunk:
                break
            stderr_chunks.append(chunk)

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    transcript: list[bytes] = []
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    launch_error: str | None = None

    def send(value: Mapping[str, Any]) -> None:
        process.stdin.write(_json_line(value))
        process.stdin.flush()

    def receive_until(
        predicate: Callable[[Mapping[str, Any]], bool],
    ) -> Mapping[str, Any] | None:
        nonlocal timed_out
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                return None
            try:
                line = stdout_queue.get(timeout=remaining)
            except queue.Empty:
                timed_out = True
                return None
            if line is None:
                return None
            transcript.append(line)
            event = _decode_event(line)
            if predicate(event):
                return event

    try:
        send(
            {
                "method": "initialize",
                "id": _INITIALIZE_REQUEST_ID,
                "params": {"clientInfo": dict(_CLIENT_INFO)},
            }
        )
        initialized = receive_until(
            lambda item: item.get("id") == _INITIALIZE_REQUEST_ID
        )
        if initialized is None or "error" in initialized:
            launch_error = "CODEX_APP_SERVER_INITIALIZE_FAILED"
        else:
            send({"method": "initialized", "params": {}})
            send(_thread_start_request(request, cwd))
            started = receive_until(
                lambda item: item.get("id") == _THREAD_START_REQUEST_ID
            )
            if started is None or "error" in started:
                launch_error = "CODEX_APP_SERVER_THREAD_START_FAILED"
            else:
                result = started.get("result")
                thread = (
                    result.get("thread")
                    if isinstance(result, Mapping)
                    else None
                )
                thread_id = (
                    thread.get("id")
                    if isinstance(thread, Mapping)
                    else None
                )
                if not isinstance(thread_id, str) or not thread_id:
                    launch_error = (
                        "CODEX_APP_SERVER_THREAD_ID_MISSING"
                    )
                else:
                    send(
                        _turn_start_request(
                            request,
                            thread_id=thread_id,
                            workspace=cwd,
                        )
                    )

                    def terminal(item: Mapping[str, Any]) -> bool:
                        if (
                            item.get("id") == _TURN_START_REQUEST_ID
                            and "error" in item
                        ):
                            return True
                        if item.get("method") == "turn/completed":
                            return True
                        return _is_server_tool_request(item) is not None

                    terminal_event = receive_until(terminal)
                    if terminal_event is None:
                        if not timed_out:
                            launch_error = (
                                "CODEX_APP_SERVER_TURN_STREAM_ENDED"
                            )
                    elif (
                        terminal_event.get("id")
                        == _TURN_START_REQUEST_ID
                        and "error" in terminal_event
                    ):
                        launch_error = (
                            "CODEX_APP_SERVER_TURN_START_FAILED"
                        )
                    elif _is_server_tool_request(terminal_event):
                        launch_error = (
                            "CODEX_APP_SERVER_TOOL_REQUEST_FORBIDDEN"
                        )
    except (
        BrokenPipeError,
        OSError,
        CodexAppServerTransportError,
    ) as exc:
        launch_error = (
            str(exc)
            if isinstance(exc, CodexAppServerTransportError)
            else "CODEX_APP_SERVER_PROTOCOL_IO_FAILED"
        )
    finally:
        _terminate_process(process)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        while True:
            try:
                line = stdout_queue.get_nowait()
            except queue.Empty:
                break
            if line is not None:
                transcript.append(line)

    return RawAppServerSession(
        stdout=b"".join(transcript),
        stderr=b"".join(stderr_chunks),
        timed_out=timed_out,
        launch_error=launch_error,
    )


def _attestation(
    *,
    model: str,
    provider: str,
    reasoning_effort: str,
) -> str:
    return json.dumps(
        {
            "allow_provider_model_fallback": False,
            "model": model,
            "provider": provider,
            "reasoning_effort": reasoning_effort,
            "transport": PROVIDER_TRANSPORT,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


class CodexAppServerGenerativeTransport:
    """Invoke one effective-model-attested, hard-budgeted Codex turn."""

    def __init__(
        self,
        *,
        codex_binary: str | None = None,
        auth_json_path: Path | None = None,
        probe_runner: Callable[..., subprocess.CompletedProcess[bytes]] = (
            subprocess.run
        ),
        process_factory: Callable[..., subprocess.Popen[bytes]] = (
            subprocess.Popen
        ),
        session_runner: Callable[..., RawAppServerSession] | None = None,
        capability_override: ModelTransportCapability | None = None,
    ) -> None:
        self._binary = codex_binary or shutil.which("codex")
        self._auth_path = (
            Path(auth_json_path).expanduser().resolve()
            if auth_json_path is not None
            else None
        )
        self._probe_runner = probe_runner
        self._process_factory = process_factory
        self._session_runner = session_runner
        self._capability_override = capability_override

    def _probe(
        self, arguments: Sequence[str], *, timeout: int = 10
    ) -> subprocess.CompletedProcess[bytes] | None:
        if self._binary is None:
            return None
        try:
            return self._probe_runner(
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
        exact_version = cli_version == EXPECTED_CODEX_CLI_VERSION
        if version is None or version.returncode != 0:
            reasons.append("CODEX_CLI_UNAVAILABLE")
        elif not exact_version:
            reasons.append("CODEX_CLI_VERSION_MISMATCH")

        login = self._probe(("login", "status"))
        authenticated = bool(
            login is not None
            and login.returncode == 0
            and b"Logged in using ChatGPT" in login.stdout + login.stderr
        )
        if not authenticated:
            reasons.append("CODEX_CHATGPT_LOGIN_UNAVAILABLE")

        help_result = self._probe(("app-server", "--help"))
        app_server_available = bool(
            help_result is not None
            and help_result.returncode == 0
            and b"--stdio" in help_result.stdout + help_result.stderr
            and b"--strict-config" in help_result.stdout
            + help_result.stderr
        )
        if not app_server_available:
            reasons.append("CODEX_APP_SERVER_UNAVAILABLE")

        attested_mechanism = (
            exact_version and authenticated and app_server_available
        )
        return ModelTransportCapability(
            adapter_id=ADAPTER_ID,
            transport_evidence_class="REAL_GENERATIVE",
            provider_transport=PROVIDER_TRANSPORT,
            cli_version=cli_version,
            authenticated=authenticated,
            real_generative=attested_mechanism,
            ephemeral_sessions=True,
            read_only_workspace=True,
            empty_temporary_workspace=True,
            tool_calls_detectable=True,
            usage_available=True,
            hard_token_limit_available=attested_mechanism,
            served_model_attestation_available=attested_mechanism,
            reason_codes=tuple(reasons),
        )

    def _auth_source(self) -> Path:
        if self._auth_path is not None:
            return self._auth_path
        codex_home = os.environ.get("CODEX_HOME")
        root = (
            Path(codex_home).expanduser()
            if codex_home
            else Path.home() / ".codex"
        )
        return (root / "auth.json").resolve()

    @staticmethod
    def _error(
        request: ModelCallRequest,
        *,
        raw: RawAppServerSession,
        started: float,
        code: str,
        parsed: ParsedAppServerSession | None = None,
        status: ModelAttemptStatus = ModelAttemptStatus.PROVIDER_ERROR,
    ) -> ModelAttemptResult:
        return ModelAttemptResult(
            status=status,
            raw_event_bytes=raw.stdout,
            raw_stderr_bytes=raw.stderr,
            raw_output_bytes=None,
            requested_model=request.model,
            served_model_attestation=(
                _attestation(
                    model=parsed.effective_model,
                    provider=parsed.effective_provider,
                    reasoning_effort=parsed.effective_reasoning_effort,
                )
                if (
                    parsed is not None
                    and parsed.effective_model is not None
                    and parsed.effective_provider is not None
                    and parsed.effective_reasoning_effort is not None
                )
                else None
            ),
            usage=parsed.usage if parsed is not None else None,
            tool_call_names=(
                parsed.tool_call_names if parsed is not None else ()
            ),
            retry_count=parsed.retry_count if parsed is not None else 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_code=code,
            model_rerouted=(
                parsed.model_rerouted if parsed is not None else False
            ),
        )

    def invoke(self, request: ModelCallRequest) -> ModelAttemptResult:
        started = time.monotonic()
        empty = RawAppServerSession(stdout=b"", stderr=b"")
        if self._binary is None:
            return self._error(
                request,
                raw=empty,
                started=started,
                code="CODEX_CLI_UNAVAILABLE",
            )
        if (
            type(request.token_limit) is not int
            or request.token_limit < 2
            or request.timeout_seconds <= 0
            or hashlib.sha256(request.provider_input_bytes).hexdigest()
            != request.provider_input_digest
        ):
            return self._error(
                request,
                raw=empty,
                started=started,
                code="CODEX_APP_SERVER_REQUEST_INVALID",
            )
        try:
            request.provider_input_bytes.decode("utf-8")
            schema = json.loads(request.semantic_output_schema_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            schema = None
        if not isinstance(schema, dict):
            return self._error(
                request,
                raw=empty,
                started=started,
                code="CODEX_APP_SERVER_REQUEST_BYTES_INVALID",
            )

        auth_source = self._auth_source()
        if not auth_source.is_file():
            return self._error(
                request,
                raw=empty,
                started=started,
                code="CODEX_APP_SERVER_CHATGPT_AUTH_UNAVAILABLE",
            )

        with (
            tempfile.TemporaryDirectory(
                prefix="ta2-codex-app-server-home-"
            ) as isolated_home,
            tempfile.TemporaryDirectory(
                prefix="ta2-codex-app-server-empty-workspace-"
            ) as workspace,
        ):
            home = Path(isolated_home)
            (home / "auth.json").symlink_to(auth_source)
            environment = dict(os.environ)
            environment["CODEX_HOME"] = isolated_home
            for key in (
                "OPENAI_API_KEY",
                "CODEX_API_KEY",
                "CODEX_ACCESS_TOKEN",
            ):
                environment.pop(key, None)
            command = _app_server_command(
                self._binary, request.token_limit
            )
            runner = self._session_runner or _run_stdio_app_server
            kwargs: dict[str, Any] = {
                "command": command,
                "env": environment,
                "cwd": workspace,
                "request": request,
                "timeout_seconds": request.timeout_seconds,
            }
            if self._session_runner is None:
                kwargs["process_factory"] = self._process_factory
            raw = runner(**kwargs)

        if raw.timed_out:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_TIMEOUT",
                status=ModelAttemptStatus.TIMEOUT,
            )
        try:
            parsed = parse_codex_app_server_jsonl(raw.stdout)
        except CodexAppServerTransportError as exc:
            return self._error(
                request,
                raw=raw,
                started=started,
                code=str(exc),
            )
        if raw.launch_error is not None:
            return self._error(
                request,
                raw=raw,
                started=started,
                code=raw.launch_error,
                parsed=parsed,
            )
        if parsed.turn_error_code == "sessionBudgetExceeded":
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_SESSION_BUDGET_EXCEEDED",
                parsed=parsed,
            )
        attestation_valid = (
            parsed.effective_model == request.model
            and isinstance(parsed.effective_provider, str)
            and bool(parsed.effective_provider)
            and parsed.effective_reasoning_effort
            == request.reasoning_effort
            and parsed.instruction_sources == ()
            and parsed.ephemeral_thread is True
        )
        if not attestation_valid:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_EFFECTIVE_CONFIG_NOT_ATTESTED",
                parsed=parsed,
            )
        if parsed.model_rerouted:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_MODEL_REROUTED",
                parsed=parsed,
            )
        if parsed.turn_status != "completed":
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_TURN_NOT_COMPLETED",
                parsed=parsed,
            )
        if parsed.usage is None:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_USAGE_MISSING",
                parsed=parsed,
            )
        if parsed.usage.total_tokens > request.token_limit:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_TOKEN_BUDGET_EXCEEDED",
                parsed=parsed,
            )
        if parsed.output is None:
            return self._error(
                request,
                raw=raw,
                started=started,
                code="CODEX_APP_SERVER_AGENT_MESSAGE_MISSING",
                parsed=parsed,
            )
        return ModelAttemptResult(
            status=ModelAttemptStatus.COMPLETE,
            raw_event_bytes=raw.stdout,
            raw_stderr_bytes=raw.stderr,
            raw_output_bytes=parsed.output,
            requested_model=request.model,
            served_model_attestation=_attestation(
                model=parsed.effective_model,
                provider=parsed.effective_provider,
                reasoning_effort=parsed.effective_reasoning_effort,
            ),
            usage=parsed.usage,
            tool_call_names=parsed.tool_call_names,
            retry_count=parsed.retry_count,
            latency_ms=int((time.monotonic() - started) * 1000),
            model_rerouted=False,
        )


__all__ = [
    "ADAPTER_ID",
    "CodexAppServerGenerativeTransport",
    "CodexAppServerTransportError",
    "EXPECTED_CODEX_CLI_VERSION",
    "PROVIDER_TRANSPORT",
    "ParsedAppServerSession",
    "RawAppServerSession",
    "parse_codex_app_server_jsonl",
]
