"""Read-only macOS/POSIX capability inspection for a V3.2 profile.

No network probe is performed.  Network, Codex delivery and automation status
must be supplied as bounded observations; UNKNOWN remains UNKNOWN.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Mapping, Sequence

from ..domain.v32_environment_capability import (
    CAPABILITY_STATUSES,
    build_v32_environment_capability_profile_v1,
)


class V32EnvironmentCapabilityAdapterError(ValueError):
    """A caller attempted to overclaim a locally inspected capability."""


def _status(value: str) -> str:
    if value not in CAPABILITY_STATUSES:
        raise V32EnvironmentCapabilityAdapterError(
            "V32_ENV_ADAPTER_STATUS_INVALID"
        )
    return value


def build_local_v32_environment_capability_profile_v1(
    *,
    profile_id: str,
    run_scope_id: str,
    frozen_at: str,
    project_root: Path,
    public_network_status: str,
    codex_delivery_status: str,
    automation_status: str,
    tool_names: Sequence[str],
    localization_adapters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise V32EnvironmentCapabilityAdapterError(
            "V32_ENV_ADAPTER_PROJECT_ROOT_INVALID"
        )
    network = _status(public_network_status)
    delivery = _status(codex_delivery_status)
    automation = _status(automation_status)
    tools = sorted(set(tool_names))
    if not tools or any(not isinstance(name, str) or not name for name in tools):
        raise V32EnvironmentCapabilityAdapterError("V32_ENV_ADAPTER_TOOL_SET_INVALID")
    resolved_tools = {name: shutil.which(name) for name in tools}
    tool_status = "AVAILABLE" if all(resolved_tools.values()) else "DEGRADED"
    storage_status = "AVAILABLE" if os.access(root, os.R_OK | os.W_OK) else "DEGRADED"

    def external_refs(category: str, status: str) -> list[str]:
        return [] if status in {"UNKNOWN", "UNAVAILABLE"} else [f"local:{category.lower()}:declared"]

    capabilities = [
        {
            "category": "AUTOMATION",
            "status": automation,
            "observed_value": "CALLER_DECLARED_NO_RUNTIME_MUTATION",
            "limit": "ONE_PREEXISTING_MONITOR_ONLY_WHEN_SEPARATELY_AUTHORIZED",
            "evidence_refs": external_refs("automation", automation),
            "claim_ceiling": "CAPABILITY_ONLY_NOT_AUTOMATION_AUTHORITY",
        },
        {
            "category": "CODEX_DELIVERY",
            "status": delivery,
            "observed_value": "CALLER_DECLARED_CURRENT_CODEX_CONTEXT",
            "limit": "BOUNDED_TYPED_INPUT_OUTPUT_SINGLE_ATTEMPT",
            "evidence_refs": external_refs("codex-delivery", delivery),
            "claim_ceiling": "DELIVERY_CAPABILITY_NOT_MODEL_ATTESTATION",
        },
        {
            "category": "LOCAL_STORAGE",
            "status": storage_status,
            "observed_value": str(root),
            "limit": "PROJECT_ROOT_LOCAL_WRITE_ONCE_PATHS_ONLY",
            "evidence_refs": ["local:storage:os-access"],
            "claim_ceiling": "LOCAL_DURABILITY_NOT_REMOTE_BACKUP",
        },
        {
            "category": "NETWORK_PUBLIC_SOURCES",
            "status": network,
            "observed_value": "NO_NETWORK_PROBE_PERFORMED",
            "limit": "PUBLIC_GET_ONLY_AFTER_SEPARATE_QUALIFICATION_AUTHORITY",
            "evidence_refs": external_refs("public-network", network),
            "claim_ceiling": "DECLARED_CAPABILITY_NOT_SOURCE_QUALIFICATION",
        },
        {
            "category": "OPERATING_SYSTEM",
            "status": "AVAILABLE",
            "observed_value": f"{platform.system()} {platform.release()} {platform.machine()}",
            "limit": "CURRENT_LOCAL_PROCESS_ONLY",
            "evidence_refs": ["local:os:platform"],
            "claim_ceiling": "LOCAL_HOST_FACT_NOT_CROSS_HOST_PORTABILITY",
        },
        {
            "category": "PYTHON_RUNTIME",
            "status": "AVAILABLE",
            "observed_value": (
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}:{Path(sys.executable).resolve()}"
            ),
            "limit": "CURRENT_INTERPRETER_AND_INSTALLED_DEPENDENCIES",
            "evidence_refs": ["local:python:sys-version"],
            "claim_ceiling": "LOCAL_RUNTIME_FACT_NOT_TRANSPORT_ATTESTATION",
        },
        {
            "category": "TIME_SOURCE",
            "status": "AVAILABLE",
            "observed_value": "CALLER_SUPPLIED_CANONICAL_UTC_WITH_PYTHON_VALIDATION",
            "limit": "NO_EXTERNAL_CLOCK_ACCURACY_CLAIM",
            "evidence_refs": ["local:time:canonical-parser"],
            "claim_ceiling": "FORMAT_VALIDITY_ONLY_NOT_NTP_ACCURACY",
        },
        {
            "category": "TOOLS",
            "status": tool_status,
            "observed_value": ",".join(
                f"{name}={resolved_tools[name] or 'MISSING'}" for name in tools
            ),
            "limit": "READ_ONLY_DISCOVERY_NO_INSTALL_PERFORMED",
            "evidence_refs": ["local:tools:path-resolution"],
            "claim_ceiling": "LOCAL_PATH_PRESENCE_NOT_SERVICE_RELIABILITY",
        },
    ]
    return build_v32_environment_capability_profile_v1(
        profile_id=profile_id,
        run_scope_id=run_scope_id,
        frozen_at=frozen_at,
        capabilities=capabilities,
        localization_adapters=localization_adapters,
    )


__all__ = [
    "V32EnvironmentCapabilityAdapterError",
    "build_local_v32_environment_capability_profile_v1",
]
