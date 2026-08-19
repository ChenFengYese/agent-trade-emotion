"""Minimal read-only JSON workbench for persisted V3.3.2 facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ..domain.market_cycle.data import AssetDataSliceV1
from ..infrastructure.market_cycle.attention_repository import FileAttentionRepository
from ..infrastructure.market_cycle.paper_ledger import FilePaperLedger
from ..infrastructure.market_cycle.projections import WorkbenchProjectionService
from ..infrastructure.market_cycle.repository import FileCycleRepository
from ..infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    build_hype_data_profile_service,
)
from ..infrastructure.market_data.raw_capture import FileRawCaptureStore


def load_hype_data_slices(
    *, runtime_root: Path, cycle_ids: Sequence[str]
) -> tuple[AssetDataSliceV1, ...]:
    """Rebuild admitted HYPE slices from the primary sealed-raw owner."""

    service = build_hype_data_profile_service(
        raw_store=FileRawCaptureStore(runtime_root)
    )
    slices: list[AssetDataSliceV1] = []
    for cycle_id in cycle_ids:
        result = service.replay(HYPE_OKX_DATA_PROFILE.profile_id, cycle_id=cycle_id)
        if result.data_slice is None:
            raise RuntimeError(
                f"WORKBENCH_DATA_SLICE_NOT_ADMITTED:{cycle_id}:{result.status}"
            )
        slices.append(result.data_slice)
    return tuple(slices)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v332-market-workbench",
        description="Render a read-only V3.3.2 paper/attention snapshot as JSON.",
    )
    parser.add_argument("--attention-root", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, required=True)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="Primary market-cycle runtime root containing sealed HYPE raw.",
    )
    parser.add_argument(
        "--hype-cycle-id",
        action="append",
        default=[],
        help="Cycle whose admitted HYPE data coverage should be reconstructed.",
    )
    parser.add_argument(
        "--cycle-id",
        action="append",
        default=[],
        help="Market cycle whose sealed business artifacts should enter the timeline.",
    )
    parser.add_argument("--logical-agent-id", action="append", default=[])
    parser.add_argument("--account-id", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if (arguments.hype_cycle_id or arguments.cycle_id) and arguments.runtime_root is None:
        raise SystemExit("--runtime-root is required with cycle inputs")
    data_slices = (
        ()
        if arguments.runtime_root is None
        else load_hype_data_slices(
            runtime_root=arguments.runtime_root,
            cycle_ids=tuple(arguments.hype_cycle_id),
        )
    )
    snapshot = WorkbenchProjectionService(
        attention_repository=FileAttentionRepository(arguments.attention_root),
        paper_ledger=FilePaperLedger(arguments.paper_root),
        cycle_repository=(
            None
            if arguments.runtime_root is None
            else FileCycleRepository(
                arguments.runtime_root / "cycles",
                raw_capture_verifier=FileRawCaptureStore(arguments.runtime_root),
            )
        ),
    ).build(
        logical_agent_ids=tuple(arguments.logical_agent_id),
        account_ids=tuple(arguments.account_id),
        data_slices=data_slices,
        cycle_ids=tuple(arguments.cycle_id),
    )
    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
