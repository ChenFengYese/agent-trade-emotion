from __future__ import annotations

import unittest
from pathlib import Path

from trade_system.theory_paper.common import digest_json
from trade_system.theory_paper.inference_v2.infrastructure import read_json_object
from trade_system.theory_paper_v2.infrastructure.legacy_v1 import (
    LegacyAdapterError,
    LegacyV1Adapter,
)


class LegacyV1AdapterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(".runtime/theory-paper-v1/current").resolve()
        if not cls.root.is_dir():
            raise unittest.SkipTest("frozen V1 runtime is unavailable")
        cls.manifest = read_json_object(cls.root / "manifest.json")
        cls.manifest_digest = digest_json(cls.manifest)
        cls.adapter = LegacyV1Adapter(
            expected_run_id=cls.manifest["run_id"],
        )

    def test_complete_cycle_loads_with_v2_state_kept_unknown(self) -> None:
        envelope = self.adapter.load_cycle(
            self.root, 2, self.manifest_digest
        )
        self.assertEqual("PASS", envelope.integrity_verdict)
        self.assertIsNotNone(envelope.agent_decision)
        self.assertEqual(
            envelope.source_tree_digest_before, envelope.source_tree_digest_after
        )
        gap_names = {item.field_name for item in envelope.gap_entries}
        self.assertIn("strategic_episode_state", gap_names)
        self.assertIn("reentry_contract", gap_names)

    def test_missing_raw_agent_artifact_is_unknown_not_fabricated(self) -> None:
        for cycle_id in (1, 22, 23, 24):
            envelope = self.adapter.load_cycle(
                self.root, cycle_id, self.manifest_digest
            )
            self.assertIsNone(envelope.agent_decision)
            self.assertIn(
                "agent_decision",
                {item.field_name for item in envelope.gap_entries},
            )

    def test_cycle_25_is_out_of_scope(self) -> None:
        with self.assertRaisesRegex(LegacyAdapterError, "LEGACY_CYCLE_OUT_OF_SCOPE"):
            self.adapter.load_cycle(self.root, 25, self.manifest_digest)

    def test_manifest_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            LegacyAdapterError, "LEGACY_MANIFEST_DIGEST_MISMATCH"
        ):
            self.adapter.load_cycle(self.root, 2, "0" * 64)


if __name__ == "__main__":
    unittest.main()
