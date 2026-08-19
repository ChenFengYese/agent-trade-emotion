#!/usr/bin/env python3
"""Freeze V2 deterministic-kernel resolution receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trade_system.theory_paper_v2.application.bootstrap import (
    materialize_kernel_resolution,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
    )
    parser.add_argument("--verified-at", required=True)
    arguments = parser.parse_args()
    result = materialize_kernel_resolution(
        arguments.project_root,
        verified_at=arguments.verified_at,
    )
    print(
        json.dumps(
            {
                "kernel_component_count": len(
                    result["kernel_component_contracts"]
                ),
                "bootstrap_verdict": result[
                    "cluster_bootstrap_receipt"
                ]["verdict"],
                "bootstrap_receipt_digest": result[
                    "cluster_bootstrap_receipt"
                ]["receipt_digest"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
