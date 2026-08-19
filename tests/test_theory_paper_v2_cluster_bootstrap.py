from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.bootstrap import (
    BootstrapError,
    REQUIRED_COMPONENT_IDS,
    SKILL_ROLES,
    build_cluster_manifest,
    build_role_skill_manifest,
    build_skill_resolution_receipt,
    install_skill_package,
    materialize_cluster_sources,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
)


ROOT = Path(__file__).resolve().parents[1]


class ClusterBootstrapTests(unittest.TestCase):
    def test_cluster_is_exactly_three_roles_and_twelve_kernel_components(self) -> None:
        manifests = {
            skill_id: build_role_skill_manifest(
                ROOT / "agent-cluster" / "skill-sources" / skill_id, skill_id
            )
            for skill_id in SKILL_ROLES
        }
        cluster = build_cluster_manifest(manifests)
        verify_self_digest(cluster, "manifest_digest")
        self.assertEqual(
            ["PROPOSER", "CHALLENGER", "SELECTOR"],
            cluster["required_role_ids"],
        )
        self.assertEqual(12, len(cluster["required_kernel_component_refs"]))
        self.assertEqual(
            set(REQUIRED_COMPONENT_IDS),
            {
                value.removeprefix("kernel-component:").removesuffix(":1.0.0")
                for value in cluster["required_kernel_component_refs"]
            },
        )
        self.assertEqual(
            "PROPOSE_ONCE_CHALLENGE_ONCE_CALCULATE_ONCE_SELECT_ONCE_GOVERN_ONCE",
            cluster["fixed_dag"],
        )

    def test_user_install_is_exact_and_conflicts_fail_closed(self) -> None:
        skill_id = "trade-decision-proposer"
        source = ROOT / "agent-cluster" / "skill-sources" / skill_id
        manifest = build_role_skill_manifest(source, skill_id)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / skill_id
            self.assertEqual("INSTALLED", install_skill_package(source, target))
            self.assertEqual(
                "EXISTING_IDENTICAL", install_skill_package(source, target)
            )
            receipt = build_skill_resolution_receipt(
                source_root=source,
                resolved_root=target,
                skill_manifest=manifest,
                verified_at="2026-07-31T00:00:00Z",
                resolution_mode="USER_INSTALLED",
            )
            self.assertEqual("PASS", receipt["verdict"])
            self.assertTrue(receipt["installed"])
            (target / "SKILL.md").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(BootstrapError, "SKILL_INSTALL_CONFLICT"):
                install_skill_package(source, target)

    def test_project_manifests_are_write_once_and_self_digesting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent-cluster").mkdir()
            source = ROOT / "agent-cluster" / "skill-sources"
            target = root / "agent-cluster" / "skill-sources"
            target.symlink_to(source, target_is_directory=True)
            first = materialize_cluster_sources(root)
            second = materialize_cluster_sources(root)
            self.assertEqual(
                first["cluster_manifest"]["manifest_digest"],
                second["cluster_manifest"]["manifest_digest"],
            )
            frozen = load_json_strict(
                root
                / "agent-cluster"
                / "manifests"
                / "cluster-manifest.v1.json"
            )
            verify_self_digest(frozen, "manifest_digest")

    def test_agents_template_has_all_thirteen_contract_sections(self) -> None:
        text = (
            ROOT / "agent-cluster" / "templates" / "AGENTS.template.md"
        ).read_text(encoding="utf-8")
        for index in range(1, 14):
            self.assertIn(f"## {index}.", text)
        self.assertIn("UnitOfWork", text)
        self.assertIn("E0_OFFLINE_COUNTERFACTUAL", text)
        self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
