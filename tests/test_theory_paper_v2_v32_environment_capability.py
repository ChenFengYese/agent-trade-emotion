from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD,
    V32EnvironmentCapabilityError,
    build_v32_environment_capability_profile_v1,
    verify_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_environment_capability_adapter import (
    build_local_v32_environment_capability_profile_v1,
)


RUN_ID = "v32-authorized-revision-test"
NOW = "2026-08-08T01:00:00Z"


def _capabilities() -> list[dict]:
    return [
        {
            "category": category,
            "status": "AVAILABLE",
            "observed_value": f"observed:{category}",
            "limit": "LOCAL_DECLARED_LIMIT",
            "evidence_refs": [f"local:{category.lower()}"],
            "claim_ceiling": "CAPABILITY_ONLY",
        }
        for category in reversed(CAPABILITY_CATEGORIES)
    ]


class EnvironmentCapabilityTests(unittest.TestCase):
    def test_profile_has_complete_sorted_coverage_and_exact_replay(self) -> None:
        profile = build_v32_environment_capability_profile_v1(
            profile_id="environment-profile",
            run_scope_id=RUN_ID,
            frozen_at=NOW,
            capabilities=_capabilities(),
            localization_adapters=[],
        )
        self.assertEqual(
            [row["category"] for row in profile["capabilities"]],
            list(CAPABILITY_CATEGORIES),
        )
        self.assertEqual(
            verify_v32_environment_capability_profile_v1(profile),
            profile[DIGEST_FIELD],
        )
        self.assertFalse(profile["network_probe_performed"])
        self.assertFalse(profile["profile_is_authority"])

    def test_local_adapter_preserves_unknown_without_network_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = build_local_v32_environment_capability_profile_v1(
                profile_id="local-environment-profile",
                run_scope_id=RUN_ID,
                frozen_at=NOW,
                project_root=Path(temporary),
                public_network_status="UNKNOWN",
                codex_delivery_status="UNKNOWN",
                automation_status="UNAVAILABLE",
                tool_names=["python3"],
                localization_adapters=[],
            )
        statuses = {
            row["category"]: row["status"] for row in profile["capabilities"]
        }
        self.assertEqual(statuses["NETWORK_PUBLIC_SOURCES"], "UNKNOWN")
        self.assertEqual(statuses["CODEX_DELIVERY"], "UNKNOWN")
        self.assertFalse(profile["network_probe_performed"])
        verify_v32_environment_capability_profile_v1(profile)

    def test_missing_category_and_available_without_evidence_are_rejected(self) -> None:
        with self.assertRaises(V32EnvironmentCapabilityError):
            build_v32_environment_capability_profile_v1(
                profile_id="missing-category",
                run_scope_id=RUN_ID,
                frozen_at=NOW,
                capabilities=_capabilities()[:-1],
                localization_adapters=[],
            )
        rows = _capabilities()
        rows[0]["evidence_refs"] = []
        with self.assertRaises(V32EnvironmentCapabilityError):
            build_v32_environment_capability_profile_v1(
                profile_id="missing-evidence",
                run_scope_id=RUN_ID,
                frozen_at=NOW,
                capabilities=rows,
                localization_adapters=[],
            )

    def test_localization_cannot_change_core_or_be_resigned(self) -> None:
        bad_adapter = {
            "adapter_id": "bad-core-change",
            "capability_category": "TOOLS",
            "reason": "tool difference",
            "claim_ceiling": "local only",
            "test_refs": ["test:adapter"],
            "rollback_plan": "remove adapter",
            "changes_theory_core": True,
            "changes_evaluation_endpoint": False,
            "changes_data_timing": False,
            "changes_authority_boundary": False,
        }
        with self.assertRaises(V32EnvironmentCapabilityError):
            build_v32_environment_capability_profile_v1(
                profile_id="bad-adapter",
                run_scope_id=RUN_ID,
                frozen_at=NOW,
                capabilities=_capabilities(),
                localization_adapters=[bad_adapter],
            )
        profile = build_v32_environment_capability_profile_v1(
            profile_id="tamper",
            run_scope_id=RUN_ID,
            frozen_at=NOW,
            capabilities=_capabilities(),
            localization_adapters=[],
        )
        profile["authority_boundary_unchanged"] = False
        profile = self_digest(profile, DIGEST_FIELD)
        with self.assertRaises(V32EnvironmentCapabilityError):
            verify_v32_environment_capability_profile_v1(profile)


if __name__ == "__main__":
    unittest.main()
