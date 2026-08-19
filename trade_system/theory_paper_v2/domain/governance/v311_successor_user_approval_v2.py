"""Typed user approval for the V3.1.1 successor addendum and experiment."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from ..contracts.canonical import self_digest, verify_self_digest


class V311SuccessorUserApprovalV2Error(ValueError):
    """The successor approval is absent, altered, or permission-expanding."""


SUCCESSOR_USER_APPROVAL_SCHEMA_ID = (
    "theory_paper_v311_successor_user_approval_receipt_v2"
)
SUCCESSOR_USER_APPROVAL_SCHEMA_VERSION = "2.0.0"
SUCCESSOR_USER_APPROVAL_DIGEST_FIELD = "successor_user_approval_digest"
SUCCESSOR_USER_APPROVAL_PATH = (
    "config/theory_paper_v311.successor_user_approval.20260807.v2.json"
)
REQUIRED_USER_APPROVAL_STATEMENTS = (
    "持续进行下一步，我授权，直到完成目标实验",
    "修复完成后进行全面检查并记录日志，清理工作区",
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def _time(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise V311SuccessorUserApprovalV2Error("V311_APPROVAL_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311SuccessorUserApprovalV2Error(
            "V311_APPROVAL_TIME_INVALID"
        ) from exc
    if parsed.tzinfo is None:
        raise V311SuccessorUserApprovalV2Error("V311_APPROVAL_TIME_INVALID")
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V311SuccessorUserApprovalV2Error("V311_APPROVAL_TIME_INVALID")


def build_v311_successor_user_approval_receipt_v2(
    *,
    approval_id: str,
    approved_at: str,
    theory_addendum_binding: Mapping[str, Any],
    user_statements: Sequence[str],
) -> dict[str, Any]:
    """Seal only the two explicit user statements already present in-thread."""

    if not isinstance(approval_id, str) or _SAFE_ID.fullmatch(approval_id) is None:
        raise V311SuccessorUserApprovalV2Error("V311_APPROVAL_ID_INVALID")
    _time(approved_at)
    if tuple(user_statements) != REQUIRED_USER_APPROVAL_STATEMENTS:
        raise V311SuccessorUserApprovalV2Error(
            "V311_APPROVAL_USER_STATEMENTS_INVALID"
        )
    if (
        not isinstance(theory_addendum_binding, Mapping)
        or set(theory_addendum_binding)
        != {"path", "version", "review_status", "physical_sha256"}
        or theory_addendum_binding.get("path")
        != "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md"
        or theory_addendum_binding.get("version") != "3.1.1"
        or theory_addendum_binding.get("review_status")
        != "FROZEN_APPROVED_SUCCESSOR"
        or not isinstance(theory_addendum_binding.get("physical_sha256"), str)
        or _HEX_64.fullmatch(theory_addendum_binding["physical_sha256"])
        is None
    ):
        raise V311SuccessorUserApprovalV2Error(
            "V311_APPROVAL_ADDENDUM_BINDING_INVALID"
        )
    document = {
        "schema_id": SUCCESSOR_USER_APPROVAL_SCHEMA_ID,
        "schema_version": SUCCESSOR_USER_APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id,
        "approved_at": approved_at,
        "approval_source": "CURRENT_CODEX_THREAD_EXPLICIT_USER_MESSAGES",
        "user_statements": list(REQUIRED_USER_APPROVAL_STATEMENTS),
        "theory_addendum_binding": dict(theory_addendum_binding),
        "approved_scope": {
            "v311_theory_correction": True,
            "two_run_qualification_then_target": True,
            "target_experiment_until_terminal_supervisor_boundary": True,
            "post_fix_review_logging_and_safe_workspace_cleanup": True,
            "public_data_only": True,
            "local_only": True,
            "non_executable": True,
        },
        "not_authorized": [
            "ACCOUNT_ACCESS",
            "AUTOMATION_PERMISSION_EXPANSION",
            "CREDENTIAL_ACCESS",
            "FUNDS_ACCESS",
            "LIVE_TRADING",
            "ORDER_SUBMISSION",
            "PAPER_TRADING",
            "REENTRY_OR_PORTFOLIO_MUTATION",
            "RETRY_AFTER_FAIL_CLOSED",
        ],
        "chat_history_is_runtime_authority": False,
        "receipt_is_required_authority_input": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, SUCCESSOR_USER_APPROVAL_DIGEST_FIELD)


def verify_v311_successor_user_approval_receipt_v2(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V311SuccessorUserApprovalV2Error("V311_APPROVAL_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(
            document, SUCCESSOR_USER_APPROVAL_DIGEST_FIELD
        )
        rebuilt = build_v311_successor_user_approval_receipt_v2(
            approval_id=document["approval_id"],
            approved_at=document["approved_at"],
            theory_addendum_binding=document["theory_addendum_binding"],
            user_statements=document["user_statements"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorUserApprovalV2Error):
            raise
        raise V311SuccessorUserApprovalV2Error(
            "V311_APPROVAL_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[SUCCESSOR_USER_APPROVAL_DIGEST_FIELD]:
        raise V311SuccessorUserApprovalV2Error(
            "V311_APPROVAL_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "REQUIRED_USER_APPROVAL_STATEMENTS",
    "SUCCESSOR_USER_APPROVAL_DIGEST_FIELD",
    "SUCCESSOR_USER_APPROVAL_PATH",
    "SUCCESSOR_USER_APPROVAL_SCHEMA_ID",
    "SUCCESSOR_USER_APPROVAL_SCHEMA_VERSION",
    "V311SuccessorUserApprovalV2Error",
    "build_v311_successor_user_approval_receipt_v2",
    "verify_v311_successor_user_approval_receipt_v2",
]
