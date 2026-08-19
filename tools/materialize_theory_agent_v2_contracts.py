#!/usr/bin/env python3
"""Freeze or deterministically materialize Theory Agent V2 contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_system.theory_paper_v2.infrastructure.contract_bundle.materialize import (  # noqa: E402
    DEFAULT_MANIFEST_RELATIVE_PATH,
    DEFAULT_OUTPUT_RELATIVE_PATH,
    FrozenManifestError,
    freeze_or_load_manifest,
    materialize_contract_bundle,
    verify_reproducible_materialization,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze once or read-only load the Theory Agent V2 canonical "
            "manifest and materialize its portable schema bundle."
        )
    )
    parser.add_argument(
        "--freeze-manifest",
        action="store_true",
        help=(
            "bootstrap only: build the catalog and create the immutable "
            "canonical manifest; an unequal existing file is rejected"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / DEFAULT_MANIFEST_RELATIVE_PATH,
        help="frozen manifest path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / DEFAULT_OUTPUT_RELATIVE_PATH,
        help="portable bundle output directory",
    )
    parser.add_argument(
        "--skip-reproducibility-check",
        action="store_true",
        help="skip isolated double-materialization comparison",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        manifest, manifest_write_status = freeze_or_load_manifest(
            args.manifest,
            freeze_manifest=args.freeze_manifest,
        )
        reproducible_file_count = None
        if not args.skip_reproducibility_check:
            reproducible_file_count = verify_reproducible_materialization(manifest)
        result = materialize_contract_bundle(manifest, args.output_dir)
    except (FrozenManifestError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest_write_status": manifest_write_status,
                "manifest_path": str(args.manifest.resolve()),
                "output_directory": str(result.output_directory.resolve()),
                "source_manifest_digest": result.source_manifest_digest,
                "bundle_index_digest": result.bundle_index_digest,
                "schema_count": result.schema_count,
                "file_count": result.file_count,
                "reproducible_file_count": reproducible_file_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

