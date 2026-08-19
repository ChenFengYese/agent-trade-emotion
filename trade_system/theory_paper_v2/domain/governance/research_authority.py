"""Pure authorization contract for starting a new research chronology.

Historical templates are immutable evidence, not ambient authority.  Starting a
new run therefore requires a separate current authority document that binds one
frozen theory, one operation, one run id, and one physical template digest.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..contracts.canonical import verify_self_digest


class ResearchAuthorityError(ValueError):
    """A new research chronology lacks explicit current authority."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_START_OPERATIONS = frozenset(
    {"PREPARE_SEEN_V1", "PREPARE_PROSPECTIVE", "RUN_NATIVE_MARKET_PILOT"}
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authority_id",
        "recorded_at",
        "status",
        "reason",
        "current_theory",
        "candidate_theory",
        "experiment_start_authorized",
        "authorized_operations",
        "authorized_run_ids",
        "authorized_template_sha256s",
        "authorization_receipt_path",
        "authorization_receipt_digest",
        "external_execution_authority",
        "executable",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "authority_id",
        "issued_at",
        "current_theory_sha256",
        "authorized_operations",
        "authorized_run_ids",
        "authorized_template_sha256s",
        "external_execution_authority",
        "executable",
        "authorization_receipt_digest",
    }
)
_THEORY_FIELDS = frozenset(
    {"path", "version", "review_status", "physical_sha256"}
)


def _nonempty_unique_strings(value: Any, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ResearchAuthorityError(code)
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ResearchAuthorityError(code)
    return result


def validate_research_authority(document: Mapping[str, Any]) -> None:
    """Validate shape and permanent no-execution boundaries."""

    if (
        not isinstance(document, Mapping)
        or set(document) != _TOP_LEVEL_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_current_research_authority"
        or document.get("schema_version") != "1.0.0"
        or not str(document.get("authority_id") or "")
        or not str(document.get("recorded_at") or "")
        or not str(document.get("status") or "")
        or not str(document.get("reason") or "").strip()
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORITY_INVALID")
    for field in ("current_theory", "candidate_theory"):
        binding = document.get(field)
        if (
            not isinstance(binding, Mapping)
            or set(binding) != _THEORY_FIELDS
            or any(
                not isinstance(binding.get(item), str) or not binding.get(item)
                for item in ("path", "version", "review_status")
            )
            or _HEX_64.fullmatch(str(binding.get("physical_sha256") or ""))
            is None
        ):
            raise ResearchAuthorityError("CURRENT_THEORY_BINDING_INVALID")
    operations = _nonempty_unique_strings(
        document.get("authorized_operations"),
        "CURRENT_RESEARCH_AUTHORIZED_OPERATIONS_INVALID",
    )
    if not set(operations).issubset(_START_OPERATIONS):
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORIZED_OPERATIONS_INVALID")
    _nonempty_unique_strings(
        document.get("authorized_run_ids"),
        "CURRENT_RESEARCH_AUTHORIZED_RUN_IDS_INVALID",
    )
    template_digests = _nonempty_unique_strings(
        document.get("authorized_template_sha256s"),
        "CURRENT_RESEARCH_AUTHORIZED_TEMPLATES_INVALID",
    )
    if any(_HEX_64.fullmatch(item) is None for item in template_digests):
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORIZED_TEMPLATES_INVALID")
    receipt_path = document.get("authorization_receipt_path")
    receipt = document.get("authorization_receipt_digest")
    if (receipt_path is None) != (receipt is None) or (
        receipt_path is not None
        and (
            not isinstance(receipt_path, str)
            or not receipt_path
            or _HEX_64.fullmatch(str(receipt)) is None
        )
    ):
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORIZATION_RECEIPT_INVALID")


def validate_research_authorization_receipt(
    receipt: Mapping[str, Any], authority: Mapping[str, Any]
) -> None:
    """Bind a self-digested receipt to the exact active authority envelope."""

    try:
        digest = verify_self_digest(receipt, "authorization_receipt_digest")
    except ValueError as exc:
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORIZATION_RECEIPT_INVALID") from exc
    if (
        set(receipt) != _RECEIPT_FIELDS
        or receipt.get("schema_id")
        != "theory_paper_v2_research_authorization_receipt"
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("authority_id") != authority.get("authority_id")
        or not str(receipt.get("issued_at") or "")
        or receipt.get("current_theory_sha256")
        != authority["current_theory"]["physical_sha256"]
        or receipt.get("authorized_operations")
        != authority.get("authorized_operations")
        or receipt.get("authorized_run_ids") != authority.get("authorized_run_ids")
        or receipt.get("authorized_template_sha256s")
        != authority.get("authorized_template_sha256s")
        or receipt.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or receipt.get("executable") is not False
        or digest != authority.get("authorization_receipt_digest")
    ):
        raise ResearchAuthorityError("CURRENT_RESEARCH_AUTHORIZATION_RECEIPT_INVALID")


def assert_research_start_authorized(
    document: Mapping[str, Any],
    *,
    operation: str,
    run_id: str,
    template_sha256: str,
    authorization_receipt: Mapping[str, Any] | None,
) -> None:
    """Require one explicit, digest-bound, frozen-theory start authorization."""

    validate_research_authority(document)
    if operation not in _START_OPERATIONS:
        raise ResearchAuthorityError("CURRENT_RESEARCH_OPERATION_INVALID")
    if (
        document.get("status") != "ACTIVE_FROZEN_RESEARCH"
        or document.get("experiment_start_authorized") is not True
    ):
        raise ResearchAuthorityError("RESEARCH_START_SUSPENDED_USER_REVIEW_REQUIRED")
    current_theory = document["current_theory"]
    if current_theory.get("review_status") != "FROZEN_APPROVED":
        raise ResearchAuthorityError("RESEARCH_START_THEORY_NOT_FROZEN")
    if (
        not document.get("authorization_receipt_path")
        or _HEX_64.fullmatch(
            str(document.get("authorization_receipt_digest") or "")
        )
        is None
        or authorization_receipt is None
    ):
        raise ResearchAuthorityError("RESEARCH_START_RECEIPT_MISSING_OR_UNVERIFIED")
    validate_research_authorization_receipt(authorization_receipt, document)
    if operation not in document["authorized_operations"]:
        raise ResearchAuthorityError("RESEARCH_START_OPERATION_NOT_AUTHORIZED")
    if run_id not in document["authorized_run_ids"]:
        raise ResearchAuthorityError("RESEARCH_START_RUN_ID_NOT_AUTHORIZED")
    if template_sha256 not in document["authorized_template_sha256s"]:
        raise ResearchAuthorityError("RESEARCH_START_TEMPLATE_NOT_AUTHORIZED")


__all__ = [
    "ResearchAuthorityError",
    "assert_research_start_authorized",
    "validate_research_authorization_receipt",
    "validate_research_authority",
]
