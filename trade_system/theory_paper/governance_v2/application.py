"""Application use cases for successor-v2 governance shadow audits."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .domain import (
    GovernanceV2Error,
    build_legacy_audit_sidecar,
    validate_sidecar,
)
from .infrastructure import (
    load_existing_sidecar,
    load_frozen_cycle,
    load_governance_config,
    preflight_sidecar_write,
    write_sidecar,
)

_CYCLE_RE = re.compile(r"^cycle-(\d{4})$")


def _cycle_number(cycle_id: str) -> int:
    match = _CYCLE_RE.fullmatch(cycle_id)
    if match is None:
        raise GovernanceV2Error(f"SOURCE_CYCLE_ID_INVALID:{cycle_id}")
    return int(match.group(1))


def cycle_range(first_cycle: str, last_cycle: str) -> list[str]:
    first = _cycle_number(first_cycle)
    last = _cycle_number(last_cycle)
    if first > last:
        raise GovernanceV2Error("CYCLE_RANGE_REVERSED")
    return [f"cycle-{number:04d}" for number in range(first, last + 1)]


def audit_cycles(
    *,
    run_dir: Path,
    output_dir: Path,
    config_path: Path,
    first_cycle: str,
    last_cycle: str,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Audit a contiguous committed range before writing any sidecar."""

    cycle_ids = cycle_range(first_cycle, last_cycle)
    config = load_governance_config(config_path)
    sources = [load_frozen_cycle(run_dir, cycle_id) for cycle_id in cycle_ids]
    run_ids = {source["run_id"] for source in sources}
    if len(run_ids) != 1:
        raise GovernanceV2Error("CROSS_RUN_RANGE_FORBIDDEN")

    previous: dict[str, Any] | None = None
    first_number = _cycle_number(first_cycle)
    if first_number > 1:
        previous_id = f"cycle-{first_number - 1:04d}"
        previous = load_existing_sidecar(output_dir, previous_id)
        if previous is not None:
            validate_sidecar(previous, config)

    sidecars: list[dict[str, Any]] = []
    for source in sources:
        sidecar = build_legacy_audit_sidecar(source, config, previous)
        validate_sidecar(sidecar, config, previous)
        sidecars.append(sidecar)
        previous = sidecar

    if validate_only:
        writes = [
            {
                "status": "VALIDATED_NOT_WRITTEN",
                "path": None,
                "sidecar_digest": sidecar["sidecar_digest"],
            }
            for sidecar in sidecars
        ]
    else:
        for sidecar in sidecars:
            preflight_sidecar_write(
                source_run_dir=run_dir,
                output_dir=output_dir,
                sidecar=sidecar,
            )
        writes = [
            write_sidecar(
                source_run_dir=run_dir,
                output_dir=output_dir,
                sidecar=sidecar,
            )
            for sidecar in sidecars
        ]
    return {
        "status": "VALIDATED" if validate_only else "COMPLETED",
        "run_id": sources[0]["run_id"],
        "cycle_ids": cycle_ids,
        "sidecar_count": len(sidecars),
        "writes": writes,
        "blocking_violation_counts": [
            sidecar["summary"]["blocking_violation_count"]
            for sidecar in sidecars
        ],
        "v1_mutation": "NONE_READ_ONLY_SOURCE",
        "paper_action_authority": "NONE_SHADOW_ONLY",
        "existing_automation_switched": False,
    }
