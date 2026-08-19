#!/usr/bin/env python3
"""Materialize the portable cluster and optionally install verified role skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_system.theory_paper_v2.application.bootstrap import (
    SKILL_ROLES,
    build_skill_resolution_receipt,
    install_skill_package,
    materialize_cluster_sources,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import write_once_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--install-user-skills-root", type=Path)
    parser.add_argument("--verified-at")
    parser.add_argument("--receipt-output-root", type=Path)
    arguments = parser.parse_args()
    result = materialize_cluster_sources(arguments.project_root)
    installations: dict[str, str] = {}
    receipts: dict[str, str] = {}
    if arguments.install_user_skills_root is not None:
        if not arguments.verified_at or arguments.receipt_output_root is None:
            parser.error(
                "--verified-at and --receipt-output-root are required for installation"
            )
        sources = arguments.project_root / "agent-cluster" / "skill-sources"
        for skill_id in sorted(SKILL_ROLES):
            target = arguments.install_user_skills_root / skill_id
            installations[skill_id] = install_skill_package(
                sources / skill_id, target
            )
            receipt = build_skill_resolution_receipt(
                source_root=sources / skill_id,
                resolved_root=target,
                skill_manifest=result["skill_manifests"][skill_id],
                verified_at=arguments.verified_at,
                resolution_mode="USER_INSTALLED",
            )
            write_once_json(
                arguments.receipt_output_root / f"{skill_id}.resolution.v1.json",
                receipt,
            )
            receipts[skill_id] = receipt["receipt_digest"]
    print(
        json.dumps(
            {
                "cluster_manifest_digest": result["cluster_manifest"][
                    "manifest_digest"
                ],
                "skill_package_digests": {
                    skill_id: manifest["package_digest"]
                    for skill_id, manifest in result["skill_manifests"].items()
                },
                "installations": installations,
                "resolution_receipts": receipts,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
