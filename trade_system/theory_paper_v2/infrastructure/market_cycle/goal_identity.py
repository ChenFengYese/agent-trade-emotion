"""Host-derived identity gate for the one persistent V3.3.2 trading Goal."""

from __future__ import annotations

import os
import re


_CODEX_THREAD_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)


class CodexGoalIdentityError(ValueError):
    """The process is not running as an identifiable Codex Goal."""


def current_codex_goal_identity() -> str:
    """Return the current Goal identity solely from the Codex host environment."""

    thread_id = os.environ.get("CODEX_THREAD_ID")
    if not isinstance(thread_id, str) or _CODEX_THREAD_ID.fullmatch(thread_id) is None:
        raise CodexGoalIdentityError("V332_CODEX_THREAD_ID_REQUIRED")
    return f"codex-thread:{thread_id}"


__all__ = ["CodexGoalIdentityError", "current_codex_goal_identity"]
