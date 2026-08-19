"""Composition root for the local continuous-core synthetic fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..application.continuous_fixture import run_four_cycle_synthetic_fixture
from ..infrastructure.continuous_fixture import (
    CanonicalContinuousArtifactRepository,
    LocalContinuousCheckpointRepository,
    LocalResearchCycleStoreFactory,
    LocalRunLease,
    SyntheticComparator,
    SyntheticMarketCollector,
    SyntheticStrategyAgent,
)
from ..infrastructure.research_review_repository import (
    ReceiptBoundFourCycleReviewRepository,
)


def run_continuous_fixture(
    *,
    runtime_root: Path,
    run_id: str,
    through_cycle: int = 4,
    max_agent_input_bytes: int = 196_608,
    max_agent_output_bytes: int = 196_608,
) -> dict[str, Any]:
    run_root = Path(runtime_root).resolve() / run_id
    manifest_exists = (run_root / "manifest.json").is_file()
    if run_root.exists() and not manifest_exists:
        top_level_entries = {path.name for path in run_root.iterdir()}
        if top_level_entries - {"controller"}:
            raise ValueError("CONTINUOUS_FIXTURE_EXISTING_ROOT_HAS_NO_MANIFEST")
    with LocalRunLease(run_root, run_id=run_id):
        # Re-read after acquiring the lease so a waiting window cannot use a
        # stale pre-lock decision and accidentally re-initialize a completed run.
        resume_existing = (run_root / "manifest.json").is_file()
        if not resume_existing:
            top_level_entries = {path.name for path in run_root.iterdir()}
            if top_level_entries - {"controller"}:
                raise ValueError("CONTINUOUS_FIXTURE_EXISTING_ROOT_HAS_NO_MANIFEST")
        artifacts = CanonicalContinuousArtifactRepository(run_root)
        return run_four_cycle_synthetic_fixture(
            run_id=run_id,
            artifacts=artifacts,
            checkpoints=LocalContinuousCheckpointRepository(run_root),
            cycle_stores=LocalResearchCycleStoreFactory(run_root),
            collector=SyntheticMarketCollector(artifacts),
            strategy_agent=SyntheticStrategyAgent(artifacts),
            comparator=SyntheticComparator(),
            review_sources=ReceiptBoundFourCycleReviewRepository(run_root),
            resume_existing=resume_existing,
            through_cycle=through_cycle,
            max_agent_input_bytes=max_agent_input_bytes,
            max_agent_output_bytes=max_agent_output_bytes,
        )
