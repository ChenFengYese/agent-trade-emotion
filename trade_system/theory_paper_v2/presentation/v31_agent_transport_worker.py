"""Manual PTY/stdin worker for current-Codex V3.1 authoring.

This callable is entered by the Application only after attempt, request, claim,
and checkpoint reservation are durable.  It emits the canonical public request,
flushes it for the current Codex operator, and accepts exactly one JSON-line
payload.  It never asks for or records private chain of thought.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TextIO

from ..application.v31_agent_transport import (
    parse_v31_manual_worker_payload,
    render_v31_manual_worker_request,
)


class V31ManualAgentWorkerError(ValueError):
    """The manual current-Codex delivery was absent or invalid."""


_PRIVATE_REASONING_KEYS = frozenset(
    {
        "chain_of_thought",
        "private_chain_of_thought",
        "private_reasoning",
        "reasoning_trace",
        "hidden_reasoning",
    }
)


def _contains_private_reasoning_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            (
                isinstance(key, str)
                and key.casefold() in _PRIVATE_REASONING_KEYS
            )
            or _contains_private_reasoning_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_private_reasoning_key(item) for item in value)
    return False


@dataclass
class CanonicalStdioV31AgentWorker:
    """One-shot callable suitable for a terminal-backed Agent adapter."""

    input_stream: TextIO
    output_stream: TextIO
    invocation_count: int = 0

    def __call__(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.invocation_count != 0:
            raise V31ManualAgentWorkerError(
                "V31_MANUAL_WORKER_REINVOCATION_FORBIDDEN"
            )
        if not isinstance(request, Mapping):
            raise V31ManualAgentWorkerError("V31_MANUAL_WORKER_REQUEST_INVALID")
        self.invocation_count = 1
        self.output_stream.write(render_v31_manual_worker_request(request))
        self.output_stream.write("\n")
        self.output_stream.flush()

        raw = self.input_stream.readline()
        if raw == "":
            raise V31ManualAgentWorkerError(
                "V31_MANUAL_WORKER_EOF_BEFORE_PAYLOAD"
            )
        if not raw.endswith("\n"):
            raise V31ManualAgentWorkerError(
                "V31_MANUAL_WORKER_PAYLOAD_FRAME_INCOMPLETE"
            )
        try:
            payload = parse_v31_manual_worker_payload(raw[:-1])
        except ValueError as exc:
            raise V31ManualAgentWorkerError(
                "V31_MANUAL_WORKER_PAYLOAD_JSON_INVALID"
            ) from exc
        if _contains_private_reasoning_key(payload):
            raise V31ManualAgentWorkerError(
                "V31_MANUAL_WORKER_PRIVATE_REASONING_FORBIDDEN"
            )
        return payload


__all__ = [
    "CanonicalStdioV31AgentWorker",
    "V31ManualAgentWorkerError",
]
