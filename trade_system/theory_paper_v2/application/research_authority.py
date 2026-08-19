"""Read-only application query for current research-start authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..infrastructure.authority.current_research import (
    CURRENT_RESEARCH_AUTHORITY_PATH,
    load_current_research_authority,
)


def research_authority_status(*, project_root: Path) -> dict[str, Any]:
    document = load_current_research_authority(project_root)
    return {
        **document,
        "authority_path": CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        "new_research_start_available": (
            document["status"] == "ACTIVE_FROZEN_RESEARCH"
            and document["experiment_start_authorized"] is True
        ),
    }


__all__ = ["research_authority_status"]
