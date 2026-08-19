"""Explicit production composition for V3.1 public-source qualification.

There is intentionally no CLI and no combined initialize-and-collect command.
Initialization creates only the durable, reviewable reservation.  Calling the
separate execute function is the sole action in this module that performs the
fixed OKX public GET set; it has no credential, account, order, or experiment
interface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ..application.v31_source_qualification import (
    execute_v31_source_qualification,
    initialize_v31_source_qualification,
    source_qualification_status,
)
from ..domain.v31_source_qualification import (
    APPROVED_V31_THEORY_SHA256,
    QUALIFICATION_TIMEOUT_SECONDS,
)
from ..infrastructure.fresh_market.okx_public import OkxPublicFreshCollector
from ..infrastructure.native_market_collector import OkxNativeMarketCollector
from ..infrastructure.v31_market_adapter import adapt_native_public_snapshot
from ..infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def initialize_local_v31_source_qualification(
    *, qualification_root: Path, qualification_id: str
) -> Mapping[str, Any]:
    """Create the durable reservation without making any network request."""

    return initialize_v31_source_qualification(
        store=LocalV31SourceQualificationStore(qualification_root),
        qualification_id=qualification_id,
        created_at=_now(),
        theory_sha256=APPROVED_V31_THEORY_SHA256,
    )


def execute_local_v31_source_qualification(
    *, qualification_root: Path, qualification_id: str
) -> Mapping[str, Any]:
    """Perform the one reserved public-source attempt and seal its evidence."""

    return execute_v31_source_qualification(
        store=LocalV31SourceQualificationStore(qualification_root),
        qualification_id=qualification_id,
        collector=OkxNativeMarketCollector(
            collector=OkxPublicFreshCollector(
                timeout=float(QUALIFICATION_TIMEOUT_SECONDS)
            )
        ),
        adapter=adapt_native_public_snapshot,
        clock=_now,
    )


def local_v31_source_qualification_status(
    *, qualification_root: Path, qualification_id: str
) -> Mapping[str, Any]:
    """Read the independent qualification cursor without network access."""

    return source_qualification_status(
        store=LocalV31SourceQualificationStore(qualification_root),
        qualification_id=qualification_id,
    )


__all__ = [
    "execute_local_v31_source_qualification",
    "initialize_local_v31_source_qualification",
    "local_v31_source_qualification_status",
]
