from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from trade_system.theory_paper_v2.application.bootstrap import (
    REQUIRED_COMPONENT_IDS,
    build_cluster_bootstrap_receipt,
    build_kernel_component_contract,
    build_kernel_component_resolution_receipt,
    kernel_component_source_digest,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
)


ROOT = Path(__file__).resolve().parents[1]
VERIFIED_AT = "2026-07-31T12:00:00Z"


class KernelResolutionTests(unittest.TestCase):
    def test_exact_twelve_components_resolve_and_self_digest(self) -> None:
        self.assertEqual(12, len(REQUIRED_COMPONENT_IDS))
        digests = {}
        for component_id in REQUIRED_COMPONENT_IDS:
            contract = build_kernel_component_contract(ROOT, component_id)
            verify_self_digest(contract, "contract_digest")
            receipt = build_kernel_component_resolution_receipt(
                project_root=ROOT,
                component_contract=contract,
                verified_at=VERIFIED_AT,
            )
            verify_self_digest(receipt, "receipt_digest")
            self.assertEqual("PASS", receipt["verdict"])
            self.assertFalse(receipt["executable"])
            digests[component_id] = kernel_component_source_digest(
                ROOT, component_id
            )
        self.assertEqual(12, len(set(digests.values())))

    def test_tampered_contract_fails_closed(self) -> None:
        component_id = "DOMAIN_GOVERNANCE"
        contract = build_kernel_component_contract(ROOT, component_id)
        tampered = {**contract, "output_refs": ["live_order"]}
        receipt = build_kernel_component_resolution_receipt(
            project_root=ROOT,
            component_contract=tampered,
            verified_at=VERIFIED_AT,
        )
        self.assertEqual(
            "KERNEL_COMPONENT_DIGEST_MISMATCH_NO_COMMIT",
            receipt["verdict"],
        )

    def test_cluster_bootstrap_requires_all_roles_and_components(self) -> None:
        cluster = load_json_strict(
            ROOT / "agent-cluster/manifests/cluster-manifest.v1.json"
        )
        skill_receipts = {
            str(receipt["role_id"]): receipt
            for receipt in (
                load_json_strict(path)
                for path in sorted(
                    (
                        ROOT
                        / "agent-cluster/install-receipts/user-installed"
                    ).glob("*.json")
                )
            )
        }
        kernel_receipts = {
            component_id: build_kernel_component_resolution_receipt(
                project_root=ROOT,
                component_contract=build_kernel_component_contract(
                    ROOT, component_id
                ),
                verified_at=VERIFIED_AT,
            )
            for component_id in REQUIRED_COMPONENT_IDS
        }
        passed = build_cluster_bootstrap_receipt(
            cluster_manifest=cluster,
            skill_resolution_receipts=skill_receipts,
            kernel_resolution_receipts=kernel_receipts,
            verified_at=VERIFIED_AT,
        )
        self.assertEqual("PASS", passed["verdict"])
        missing = dict(kernel_receipts)
        missing.pop("APPLICATION_COMMIT")
        failed = build_cluster_bootstrap_receipt(
            cluster_manifest=cluster,
            skill_resolution_receipts=skill_receipts,
            kernel_resolution_receipts=missing,
            verified_at=VERIFIED_AT,
        )
        self.assertEqual(
            "BOOTSTRAP_INCOMPLETE_NO_COMMIT", failed["verdict"]
        )


if __name__ == "__main__":
    unittest.main()
