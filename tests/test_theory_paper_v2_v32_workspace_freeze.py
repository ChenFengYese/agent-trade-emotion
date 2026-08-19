from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from trade_system.theory_paper_v2.domain.governance.v32_workspace_freeze import (
    DIGEST_FIELD,
    build_v32_workspace_freeze_receipt_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_workspace_freeze import (
    V32WorkspaceFreezeInfrastructureError,
    verify_live_v32_workspace_freeze_v1,
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class V32WorkspaceFreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, "init", "-b", "codex/test")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "config", "user.name", "V32 Test")
        (self.root / ".gitignore").write_text(
            ".runtime/\n"
            "config/theory_paper_v32.current_research_authority.v1.json\n",
            encoding="utf-8",
        )
        (self.root / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
        git(self.root, "add", ".gitignore", "runtime.py")
        git(self.root, "commit", "-m", "freeze")
        self.commit = git(self.root, "rev-parse", "HEAD")
        self.tree = git(self.root, "show", "-s", "--format=%T", "HEAD")
        self.digest = hashlib.sha256((self.root / "runtime.py").read_bytes()).hexdigest()
        self.receipt = build_v32_workspace_freeze_receipt_v1(
            receipt_id="workspace-freeze",
            observed_at="2026-08-08T00:00:00Z",
            branch="codex/test",
            frozen_commit_sha=self.commit,
            frozen_tree_sha=self.tree,
            relevant_paths=["runtime.py"],
            relevant_path_sha256={"runtime.py": self.digest},
            allowed_untracked_user_artifacts=[],
            ignored_runtime_roots=[".runtime"],
        )

    def test_exact_commit_and_clean_worktree_pass(self) -> None:
        self.assertEqual(
            self.receipt[DIGEST_FIELD],
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=self.receipt
            ),
        )

    def test_tracked_or_untracked_drift_fails(self) -> None:
        (self.root / "runtime.py").write_text("VALUE = 2\n", encoding="utf-8")
        with self.assertRaises(V32WorkspaceFreezeInfrastructureError):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=self.receipt
            )
        git(self.root, "restore", "runtime.py")
        (self.root / "unexpected.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(V32WorkspaceFreezeInfrastructureError):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=self.receipt
            )

    def test_exact_user_owned_untracked_artifact_may_be_preserved(self) -> None:
        user_copy = self.root / "user-copy.md"
        user_copy.write_text("keep\n", encoding="utf-8")
        copy_digest = hashlib.sha256(user_copy.read_bytes()).hexdigest()
        receipt = build_v32_workspace_freeze_receipt_v1(
            receipt_id="workspace-freeze-with-user-copy",
            observed_at="2026-08-08T00:00:00Z",
            branch="codex/test",
            frozen_commit_sha=self.commit,
            frozen_tree_sha=self.tree,
            relevant_paths=["runtime.py"],
            relevant_path_sha256={"runtime.py": self.digest},
            allowed_untracked_user_artifacts=[
                {"relative_ref": "user-copy.md", "physical_sha256": copy_digest}
            ],
            ignored_runtime_roots=[".runtime"],
        )
        self.assertEqual(
            receipt[DIGEST_FIELD],
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=receipt
            ),
        )
        tampered = deepcopy(receipt)
        tampered["allowed_untracked_user_artifacts"][0]["physical_sha256"] = "f" * 64
        with self.assertRaises(V32WorkspaceFreezeInfrastructureError):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=tampered
            )

    def test_exact_runtime_authority_is_ignored_but_other_config_drift_is_not(self) -> None:
        authority = (
            self.root
            / "config/theory_paper_v32.current_research_authority.v1.json"
        )
        authority.parent.mkdir(parents=True, exist_ok=True)
        authority.write_text("{}\n", encoding="utf-8")
        self.assertEqual(
            self.receipt[DIGEST_FIELD],
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=self.receipt
            ),
        )

        unexpected = self.root / "config/v32-unexpected.json"
        unexpected.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(V32WorkspaceFreezeInfrastructureError):
            verify_live_v32_workspace_freeze_v1(
                project_root=self.root, receipt=self.receipt
            )


if __name__ == "__main__":
    unittest.main()
