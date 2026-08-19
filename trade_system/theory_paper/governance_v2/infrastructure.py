"""Infrastructure adapters for successor-v2 decision-governance audits."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from trade_system.theory_paper.inference_v2.domain import (
    HISTORICAL_MODE as INFERENCE_HISTORICAL_MODE,
)
from trade_system.theory_paper.inference_v2.infrastructure import (
    load_frozen_cycle as load_verified_v1_cycle,
    read_json_object,
)

from .domain import (
    HISTORICAL_MODE,
    GovernanceV2Error,
    canonical_bytes,
    canonical_digest,
)

_CYCLE_ID_RE = re.compile(r"^cycle-\d{4}$")


def load_governance_config(path: Path) -> dict[str, Any]:
    return read_json_object(Path(path))


def load_frozen_cycle(run_dir: Path, cycle_id: str) -> dict[str, Any]:
    """Load one committed v1 decision through the existing read-only adapter."""

    source = load_verified_v1_cycle(
        Path(run_dir),
        cycle_id,
        mode=INFERENCE_HISTORICAL_MODE,
    )
    source["verified_source_mode"] = source["mode"]
    source["mode"] = HISTORICAL_MODE
    return source


def sidecar_path(output_dir: Path, cycle_id: str) -> Path:
    if not isinstance(cycle_id, str) or _CYCLE_ID_RE.fullmatch(cycle_id) is None:
        raise GovernanceV2Error("SIDECAR_CYCLE_ID_INVALID")
    output_root = Path(output_dir).resolve()
    target = (
        output_root
        / "cycles"
        / cycle_id
        / "governance-sidecar.v2.json"
    ).resolve()
    try:
        target.relative_to(output_root)
    except ValueError as exc:
        raise GovernanceV2Error("SIDECAR_TARGET_OUTSIDE_OUTPUT_ROOT") from exc
    return target


def load_existing_sidecar(
    output_dir: Path,
    cycle_id: str,
) -> dict[str, Any] | None:
    path = sidecar_path(Path(output_dir), cycle_id)
    return read_json_object(path) if path.exists() else None


def preflight_sidecar_write(
    *,
    source_run_dir: Path,
    output_dir: Path,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    source_root = Path(source_run_dir).resolve()
    output_root = Path(output_dir).resolve()
    try:
        output_root.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise GovernanceV2Error("OUTPUT_INSIDE_PROTECTED_V1_RUN")
    source = sidecar.get("source")
    if not isinstance(source, dict):
        raise GovernanceV2Error("SIDECAR_SOURCE_MISSING")
    target = sidecar_path(output_root, str(source.get("cycle_id")))
    try:
        target.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise GovernanceV2Error("SIDECAR_TARGET_INSIDE_PROTECTED_V1_RUN")
    claimed_digest = sidecar.get("sidecar_digest")
    candidate = {
        key: value for key, value in sidecar.items() if key != "sidecar_digest"
    }
    if claimed_digest != canonical_digest(candidate):
        raise GovernanceV2Error("SIDECAR_DIGEST_MISMATCH")
    payload = canonical_bytes(sidecar) + b"\n"
    if target.exists():
        if target.read_bytes() != payload:
            raise GovernanceV2Error(f"WRITE_CONFLICT:{target}")
        status = "EXISTING_IDENTICAL"
    else:
        status = "READY_TO_CREATE"
    return {
        "status": status,
        "path": str(target),
        "sidecar_digest": sidecar.get("sidecar_digest"),
    }


def write_sidecar(
    *,
    source_run_dir: Path,
    output_dir: Path,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    preflight = preflight_sidecar_write(
        source_run_dir=source_run_dir,
        output_dir=output_dir,
        sidecar=sidecar,
    )
    if preflight["status"] == "EXISTING_IDENTICAL":
        return preflight
    target = Path(preflight["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(sidecar) + b"\n"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        if target.read_bytes() == payload:
            return {
                **preflight,
                "status": "EXISTING_IDENTICAL",
            }
        raise GovernanceV2Error(f"WRITE_CONFLICT:{target}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        **preflight,
        "status": "CREATED",
    }
