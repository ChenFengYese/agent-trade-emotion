"""Frozen local EnvironmentCapabilityProfile without lowering core standards."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest
from .v32_authorized_revision_common import (
    SCHEMA_VERSION,
    V32AuthorizedRevisionContractError,
    boundary,
    sorted_unique_texts,
    text,
    time,
    verify_boundary,
)


SCHEMA_ID = "theory_paper_v32_environment_capability_profile_v1"
DIGEST_FIELD = "environment_capability_profile_digest"
CAPABILITY_CATEGORIES = (
    "AUTOMATION",
    "CODEX_DELIVERY",
    "LOCAL_STORAGE",
    "NETWORK_PUBLIC_SOURCES",
    "OPERATING_SYSTEM",
    "PYTHON_RUNTIME",
    "TIME_SOURCE",
    "TOOLS",
)
CAPABILITY_STATUSES = frozenset({"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN"})


class V32EnvironmentCapabilityError(ValueError):
    """An environment claim or localization adapter crossed the frozen boundary."""


def _capabilities(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32EnvironmentCapabilityError("V32_ENV_CAPABILITY_SET_INVALID")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "category",
            "status",
            "observed_value",
            "limit",
            "evidence_refs",
            "claim_ceiling",
        }:
            raise V32EnvironmentCapabilityError("V32_ENV_CAPABILITY_INVALID")
        category = text(item["category"], "V32_ENV_CAPABILITY_INVALID")
        status = text(item["status"], "V32_ENV_CAPABILITY_INVALID")
        if category not in CAPABILITY_CATEGORIES or status not in CAPABILITY_STATUSES:
            raise V32EnvironmentCapabilityError("V32_ENV_CAPABILITY_INVALID")
        refs = sorted_unique_texts(
            item["evidence_refs"],
            "V32_ENV_CAPABILITY_EVIDENCE_INVALID",
            allow_empty=status in {"UNKNOWN", "UNAVAILABLE"},
            maximum=32,
        )
        rows.append(
            {
                "category": category,
                "status": status,
                "observed_value": text(
                    item["observed_value"], "V32_ENV_CAPABILITY_INVALID"
                ),
                "limit": text(item["limit"], "V32_ENV_CAPABILITY_INVALID"),
                "evidence_refs": refs,
                "claim_ceiling": text(
                    item["claim_ceiling"], "V32_ENV_CAPABILITY_INVALID"
                ),
            }
        )
    rows.sort(key=lambda row: row["category"])
    if [row["category"] for row in rows] != list(CAPABILITY_CATEGORIES):
        raise V32EnvironmentCapabilityError("V32_ENV_CAPABILITY_COVERAGE_INVALID")
    return rows


def _adapters(value: Any, categories: set[str]) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32EnvironmentCapabilityError("V32_ENV_ADAPTER_SET_INVALID")
    if len(value) > 64:
        raise V32EnvironmentCapabilityError("V32_ENV_ADAPTER_SET_INVALID")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "adapter_id",
            "capability_category",
            "reason",
            "claim_ceiling",
            "test_refs",
            "rollback_plan",
            "changes_theory_core",
            "changes_evaluation_endpoint",
            "changes_data_timing",
            "changes_authority_boundary",
        }:
            raise V32EnvironmentCapabilityError("V32_ENV_ADAPTER_INVALID")
        category = text(item["capability_category"], "V32_ENV_ADAPTER_INVALID")
        if category not in categories or any(
            item[field] is not False
            for field in (
                "changes_theory_core",
                "changes_evaluation_endpoint",
                "changes_data_timing",
                "changes_authority_boundary",
            )
        ):
            raise V32EnvironmentCapabilityError("V32_ENV_ADAPTER_INVALID")
        rows.append(
            {
                "adapter_id": text(item["adapter_id"], "V32_ENV_ADAPTER_INVALID"),
                "capability_category": category,
                "reason": text(item["reason"], "V32_ENV_ADAPTER_INVALID"),
                "claim_ceiling": text(
                    item["claim_ceiling"], "V32_ENV_ADAPTER_INVALID"
                ),
                "test_refs": sorted_unique_texts(
                    item["test_refs"],
                    "V32_ENV_ADAPTER_TEST_REFS_INVALID",
                    maximum=32,
                ),
                "rollback_plan": text(
                    item["rollback_plan"], "V32_ENV_ADAPTER_INVALID"
                ),
                "changes_theory_core": False,
                "changes_evaluation_endpoint": False,
                "changes_data_timing": False,
                "changes_authority_boundary": False,
            }
        )
    rows.sort(key=lambda row: row["adapter_id"])
    if len({row["adapter_id"] for row in rows}) != len(rows):
        raise V32EnvironmentCapabilityError("V32_ENV_ADAPTER_DUPLICATE")
    return rows


def build_v32_environment_capability_profile_v1(
    *,
    profile_id: str,
    run_scope_id: str,
    frozen_at: str,
    capabilities: Sequence[Mapping[str, Any]],
    localization_adapters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        rows = _capabilities(capabilities)
        adapters = _adapters(
            localization_adapters, {row["category"] for row in rows}
        )
        document = {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "profile_id": text(profile_id, "V32_ENV_PROFILE_ID_INVALID"),
            "run_scope_id": text(run_scope_id, "V32_ENV_RUN_SCOPE_INVALID"),
            "frozen_at": time(frozen_at, "V32_ENV_TIME_INVALID"),
            "target_instrument": "BTC-USDT-SWAP",
            "capabilities": rows,
            "localization_adapters": adapters,
            "missing_capability_policy": (
                "KEEP_UNKNOWN_OR_DATA_GAP_ESCALATION_NEVER_LOWER_CORE_GATE"
            ),
            "adapter_boundary": "PORT_OR_ADAPTER_ONLY_NO_DOMAIN_MUTATION",
            "theory_core_unchanged": True,
            "evaluation_endpoints_unchanged": True,
            "pit_timing_unchanged": True,
            "authority_boundary_unchanged": True,
            "profile_is_authority": False,
            "profile_is_qualification": False,
            "network_probe_performed": False,
            "account_or_private_capability_inspected": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V32EnvironmentCapabilityError):
            raise
        raise V32EnvironmentCapabilityError("V32_ENV_PROFILE_INPUT_INVALID") from exc
    return self_digest(document, DIGEST_FIELD)


def verify_v32_environment_capability_profile_v1(
    document: Mapping[str, Any]
) -> str:
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        verify_boundary(document, "V32_ENV_PROFILE_BOUNDARY_INVALID")
        rebuilt = build_v32_environment_capability_profile_v1(
            profile_id=document["profile_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            capabilities=document["capabilities"],
            localization_adapters=document["localization_adapters"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32EnvironmentCapabilityError):
            raise
        raise V32EnvironmentCapabilityError("V32_ENV_PROFILE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32EnvironmentCapabilityError("V32_ENV_PROFILE_REPLAY_MISMATCH")
    return supplied


__all__ = [
    "CAPABILITY_CATEGORIES",
    "CAPABILITY_STATUSES",
    "DIGEST_FIELD",
    "SCHEMA_ID",
    "V32EnvironmentCapabilityError",
    "build_v32_environment_capability_profile_v1",
    "verify_v32_environment_capability_profile_v1",
]
