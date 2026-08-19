#!/usr/bin/env python3
"""Freeze or offline-verify the formal Binance BTCUSDT E0 dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_system.theory_paper_v2.infrastructure.fresh_market import (
    BinanceUsdmFreshCollector,
    UrllibPublicHttpTransport,
    freeze_binance_btcusdt_hourly,
    verify_fresh_market_bundle,
)


def _result(value: object) -> dict[str, object]:
    return {
        "bundle_id": value.bundle_id,
        "bundle_root": str(value.bundle_root),
        "manifest_path": str(value.manifest_path),
        "manifest_digest": value.manifest_digest,
        "quality_status": value.quality_status.value,
        "closed_bar_count": value.closed_bar_count,
        "decision_slot_count": value.decision_slot_count,
        "replay_admissibility_status": (
            value.replay_admissibility_status.value
        ),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--bundle-id")
    parser.add_argument("--prior-bundle-root", type=Path)
    parser.add_argument("--experiment-contract", type=Path)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--verify-bundle-root", type=Path)
    arguments = parser.parse_args()
    if arguments.verify_bundle_root is not None:
        if any(
            value is not None
            for value in (
                arguments.output_root,
                arguments.bundle_id,
                arguments.prior_bundle_root,
                arguments.experiment_contract,
            )
        ):
            parser.error(
                "--verify-bundle-root cannot be combined with freeze arguments"
            )
        result = verify_fresh_market_bundle(
            arguments.verify_bundle_root
        )
    else:
        if arguments.output_root is None or not arguments.bundle_id:
            parser.error(
                "--output-root and --bundle-id are required for freezing"
            )
        collector = BinanceUsdmFreshCollector(
            transport=UrllibPublicHttpTransport(),
            timeout=arguments.timeout,
        )
        kwargs: dict[str, object] = {
            "output_root": arguments.output_root,
            "bundle_id": arguments.bundle_id,
            "collector": collector,
            "prior_bundle_root": arguments.prior_bundle_root,
        }
        if arguments.experiment_contract is not None:
            kwargs["experiment_contract_path"] = (
                arguments.experiment_contract
            )
        result = freeze_binance_btcusdt_hourly(**kwargs)
    print(
        json.dumps(
            _result(result),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
