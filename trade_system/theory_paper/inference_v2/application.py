"""Application use cases for successor-v2 shadow replay."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .domain import (
    HISTORICAL_MODE,
    LIVE_MODE,
    InferenceV2Error,
    build_cycle_sidecar,
    validate_sidecar,
)
from .infrastructure import (
    load_existing_sidecar,
    load_framework_config,
    load_frozen_cycle,
    preflight_sidecar_write,
    write_sidecar,
)

_CYCLE_RE = re.compile(r"^cycle-(\d{4})$")


def _cycle_number(cycle_id: str) -> int:
    match = _CYCLE_RE.fullmatch(cycle_id)
    if match is None:
        raise InferenceV2Error(f"SOURCE_CYCLE_ID_INVALID:{cycle_id}")
    return int(match.group(1))


def cycle_range(first_cycle: str, last_cycle: str) -> list[str]:
    first = _cycle_number(first_cycle)
    last = _cycle_number(last_cycle)
    if first > last:
        raise InferenceV2Error("CYCLE_RANGE_REVERSED")
    return [f"cycle-{number:04d}" for number in range(first, last + 1)]


def replay_cycles(
    *,
    run_dir: Path,
    output_dir: Path,
    config_path: Path,
    first_cycle: str,
    last_cycle: str,
    mode: str = HISTORICAL_MODE,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Build and validate a contiguous range before writing any sidecar."""

    if mode not in {HISTORICAL_MODE, LIVE_MODE}:
        raise InferenceV2Error("SOURCE_MODE_INVALID")
    cycle_ids = cycle_range(first_cycle, last_cycle)
    config = load_framework_config(config_path)
    sources = [
        load_frozen_cycle(run_dir, cycle_id, mode=mode) for cycle_id in cycle_ids
    ]
    run_ids = {source["run_id"] for source in sources}
    if len(run_ids) != 1:
        raise InferenceV2Error("CROSS_RUN_RANGE_FORBIDDEN")

    previous: dict[str, Any] | None = None
    first_number = _cycle_number(first_cycle)
    if first_number > 1:
        previous_id = f"cycle-{first_number - 1:04d}"
        previous = load_existing_sidecar(output_dir, previous_id)
        if previous is not None:
            validate_sidecar(previous, config, allow_unresolved_prior=True)
        elif mode == LIVE_MODE:
            raise InferenceV2Error("LIVE_PRIOR_SIDECAR_REQUIRED")

    sidecars: list[dict[str, Any]] = []
    for source in sources:
        sidecar = build_cycle_sidecar(source, config, previous)
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
        "mode": mode,
        "run_id": sources[0]["run_id"],
        "cycle_ids": cycle_ids,
        "sidecar_count": len(sidecars),
        "writes": writes,
        "v1_mutation": "NONE_READ_ONLY_SOURCE",
        "shadow_consume_enabled": False,
        "existing_automation_switched": False,
    }
