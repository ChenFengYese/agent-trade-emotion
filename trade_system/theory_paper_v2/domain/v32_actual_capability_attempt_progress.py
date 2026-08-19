"""Pure contract for one durable V3.2 capability-attempt observation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Callable, Mapping

from .governance.v32_authorization import CAPABILITY_KEYS


class V32ActualCapabilityAttemptProgressError(ValueError):
    """An attempt adapter returned a structurally invalid observation."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RESULT_FIELDS = frozenset(
    {
        "capability",
        "status",
        "state_changed",
        "pending_reason",
        "resume_token",
        "resume_requested_at",
        "observed_state_digest",
        "evidence_root",
        "evidence_root_binding",
        "attempt_count",
        "retry_performed",
        "source_scope",
        "external_execution_authority",
        "executable",
    }
)
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)


def _invalid() -> V32ActualCapabilityAttemptProgressError:
    return V32ActualCapabilityAttemptProgressError(
        "V32_ACTUAL_ATTEMPT_RESULT_INVALID"
    )


def _digest(value: Any) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise _invalid()
    return value


def _time(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid() from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise _invalid()
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _invalid()
    return value


def _binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise _invalid()
    path_text = _text(value.get("path"))
    path = PurePosixPath(path_text)
    if (
        "\\" in path_text
        or path.is_absolute()
        or path.as_posix() != path_text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _invalid()
    return {
        "path": path_text,
        "schema_id": _text(value.get("schema_id")),
        "digest_field": _text(value.get("digest_field")),
        "semantic_digest": _digest(value.get("semantic_digest")),
        "physical_sha256": _digest(value.get("physical_sha256")),
    }


def verify_v32_actual_capability_attempt_progress_v1(
    result: Mapping[str, Any],
    *,
    evidence_root_verifier: Callable[[Mapping[str, Any]], str],
) -> None:
    """Validate progress independently of its infrastructure adapter."""

    if (
        not isinstance(result, Mapping)
        or set(result) != _RESULT_FIELDS
        or not callable(evidence_root_verifier)
    ):
        raise _invalid()
    capability = result.get("capability")
    status = result.get("status")
    if capability not in CAPABILITY_KEYS or status not in {"PENDING", "COMPLETE"}:
        raise _invalid()
    _digest(result.get("observed_state_digest"))
    resume = result.get("resume_token")
    requested = result.get("resume_requested_at")
    if resume is not None:
        _digest(resume)
    if requested is not None:
        _time(requested)
    if (resume is None) != (requested is None):
        raise _invalid()
    if (
        not isinstance(result.get("state_changed"), bool)
        or result.get("attempt_count") != 1
        or result.get("retry_performed") is not False
        or result.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or result.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or result.get("executable") is not False
    ):
        raise _invalid()
    if status == "PENDING":
        if (
            not isinstance(result.get("pending_reason"), str)
            or not result["pending_reason"]
            or result.get("evidence_root") is not None
            or result.get("evidence_root_binding") is not None
        ):
            raise _invalid()
        return
    root = result.get("evidence_root")
    binding = result.get("evidence_root_binding")
    if resume is not None or requested is not None:
        raise _invalid()
    try:
        checked_binding = _binding(binding)
        root_digest = (
            evidence_root_verifier(root) if isinstance(root, Mapping) else None
        )
    except (TypeError, ValueError) as exc:
        raise _invalid() from exc
    if (
        result.get("pending_reason") is not None
        or not isinstance(root, Mapping)
        or root.get("capability") != capability
        or root_digest != checked_binding["semantic_digest"]
        or result.get("observed_state_digest")
        != checked_binding["semantic_digest"]
    ):
        raise _invalid()


__all__ = [
    "V32ActualCapabilityAttemptProgressError",
    "verify_v32_actual_capability_attempt_progress_v1",
]
