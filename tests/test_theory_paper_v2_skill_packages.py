from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / "agent-cluster" / "skill-sources"
EXPECTED_ROLE_SKILLS = {
    "trade-decision-proposer",
    "trade-decision-challenger",
    "trade-bounded-selector",
}
CONTROLLER_SKILL = "run-theory-agent-e0-experiment"
ACTION_CONTROLLER_SKILL = "run-theory-agent-action-discrimination-experiment"
ACTION_E0B_CONTROLLER_SKILL = (
    "run-theory-agent-action-discrimination-e0b-experiment"
)
EXPECTED_SKILL_SOURCES = EXPECTED_ROLE_SKILLS | {
    CONTROLLER_SKILL,
    ACTION_CONTROLLER_SKILL,
    ACTION_E0B_CONTROLLER_SKILL,
}


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(?P<body>.*?)\n---\n", text, re.DOTALL)
    if match is None:
        raise AssertionError("missing YAML frontmatter")
    result: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"invalid frontmatter line: {line!r}")
        result[key.strip()] = value.strip()
    return result


def _simple_openai_yaml(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"  ([a-z_]+): \"([^\"]*)\"", line)
        if match is not None:
            result[match.group(1)] = match.group(2)
    return result


class TheoryPaperV2SkillPackageTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.packages = {
            name: SKILL_ROOT / name
            for name in EXPECTED_ROLE_SKILLS
        }

    def test_exact_three_role_packages_and_three_controller_packages_exist(self) -> None:
        actual = {
            path.name
            for path in SKILL_ROOT.iterdir()
            if path.is_dir()
        }
        self.assertEqual(actual, EXPECTED_SKILL_SOURCES)

        for package in self.packages.values():
            files = {
                path.relative_to(package).as_posix()
                for path in package.rglob("*")
                if path.is_file()
            }
            self.assertEqual(
                files,
                {
                    "SKILL.md",
                    "agents/openai.yaml",
                    "references/role-contract.md",
                },
            )

        controller_files = {
            CONTROLLER_SKILL: {
                "SKILL.md",
                "agents/openai.yaml",
                "references/experiment-protocol.md",
                "references/recovery-contract.md",
                "scripts/native_experiment_state.py",
            },
            ACTION_CONTROLLER_SKILL: {
                "SKILL.md",
                "agents/openai.yaml",
                "references/experiment-protocol.md",
                "references/recovery-contract.md",
                "scripts/native_action_state.py",
            },
            ACTION_E0B_CONTROLLER_SKILL: {
                "SKILL.md",
                "agents/openai.yaml",
                "references/experiment-protocol.md",
                "references/recovery-contract.md",
                "scripts/native_action_state.py",
            },
        }
        for name, expected_files in controller_files.items():
            controller = SKILL_ROOT / name
            actual_files = {
                path.relative_to(controller).as_posix()
                for path in controller.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_files, expected_files)
            frontmatter = _frontmatter(
                (controller / "SKILL.md").read_text(encoding="utf-8")
            )
            self.assertEqual(set(frontmatter), {"name", "description"})
            self.assertEqual(frontmatter["name"], name)
            self.assertLessEqual(len(frontmatter["description"]), 1024)

    def test_action_controller_is_frozen_offline_and_hindsight_safe(self) -> None:
        package = SKILL_ROOT / ACTION_CONTROLLER_SKILL
        text = (package / "SKILL.md").read_text(encoding="utf-8")
        for fragment in (
            "E0_OFFLINE_COUNTERFACTUAL",
            "NONE_E0",
            "all 192 role outputs",
            "Challenger must not receive or see the Proposer output",
            "Do not rewrite invalid JSON",
            "Do not tune and rerun the same outcome window",
        ):
            self.assertIn(fragment, text)
        metadata = _simple_openai_yaml(
            (package / "agents" / "openai.yaml").read_text(encoding="utf-8")
        )
        self.assertIn(f"${ACTION_CONTROLLER_SKILL}", metadata["default_prompt"])

        e0b_package = SKILL_ROOT / ACTION_E0B_CONTROLLER_SKILL
        e0b_text = (e0b_package / "SKILL.md").read_text(encoding="utf-8")
        for fragment in (
            "E0_OFFLINE_COUNTERFACTUAL",
            "NONE_E0",
            "all 192 role outputs",
            "blind Challenger must not receive or see the Proposer output",
            "Every task ID is globally unique for the full run",
            "Do not tune and rerun the same outcome window",
        ):
            self.assertIn(fragment, e0b_text)
        e0b_metadata = _simple_openai_yaml(
            (e0b_package / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(
            f"${ACTION_E0B_CONTROLLER_SKILL}",
            e0b_metadata["default_prompt"],
        )

    def test_skill_frontmatter_is_closed_and_trigger_descriptions_are_bounded(self) -> None:
        required_trigger_fragments = {
            "trade-decision-proposer": (
                "valid Proposer role view",
                "requests AgentProposalEnvelope",
                "never calculate canonical risk",
                "never calculate canonical risk, validate, select, commit",
            ),
            "trade-decision-challenger": (
                "valid Challenger role view",
                "requests ChallengeEnvelope",
                "frozen proposal for post-proposal mode",
                "valid blinding proof for blind mode",
                "never edit, veto, vote, select, commit",
            ),
            "trade-bounded-selector": (
                "complete FeasibleActionSet",
                "valid Selector role view",
                "requests AgentSelection",
                "Select only an existing feasible candidate",
                "never create evidence or candidates",
            ),
        }

        for name, package in self.packages.items():
            skill_text = (package / "SKILL.md").read_text(encoding="utf-8")
            frontmatter = _frontmatter(skill_text)
            self.assertEqual(set(frontmatter), {"name", "description"})
            self.assertEqual(frontmatter["name"], name)
            self.assertLessEqual(len(frontmatter["description"]), 1024)
            self.assertNotIn("TODO", skill_text)
            for fragment in required_trigger_fragments[name]:
                self.assertIn(fragment, frontmatter["description"])

    def test_openai_metadata_matches_each_skill(self) -> None:
        for name, package in self.packages.items():
            metadata_text = (package / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertTrue(metadata_text.startswith("interface:\n"))
            metadata = _simple_openai_yaml(metadata_text)
            self.assertEqual(
                set(metadata),
                {"display_name", "short_description", "default_prompt"},
            )
            self.assertGreaterEqual(len(metadata["short_description"]), 25)
            self.assertLessEqual(len(metadata["short_description"]), 64)
            self.assertIn(f"${name}", metadata["default_prompt"])
            self.assertTrue(
                metadata_text.endswith(
                    "policy:\n  allow_implicit_invocation: false\n"
                )
            )

    def test_all_roles_are_tool_free_e0_and_fail_closed(self) -> None:
        common_required = (
            "resolved_role_input_document.v1",
            "ResolvedRoleInputBundle.v1",
            "ClusterBootstrapReceipt.v1",
            "SkillResolutionReceipt.v1",
            "RoleContextView.v1",
            "repository_access",
            "evidence_refresh",
            "external_execution",
            "DENIED",
            "E0_OFFLINE_COUNTERFACTUAL",
            "NONE_E0",
            "executable=false",
            "Use no tools.",
            "Do not browse",
            "Do not invent prices",
            "stop without emitting",
            "no-commit error",
            "place orders",
        )
        for package in self.packages.values():
            skill_text = (package / "SKILL.md").read_text(encoding="utf-8")
            for fragment in common_required:
                self.assertIn(fragment, skill_text)

    def test_proposer_owns_only_bounded_semantic_proposal(self) -> None:
        text = (
            self.packages["trade-decision-proposer"] / "SKILL.md"
        ).read_text(encoding="utf-8")
        required = (
            "AgentProposalEnvelope.v1",
            "one primary path",
            "alternative path",
            "null/no-action path",
            "other/unknown path",
            "NO_ACTION_WITH_OBLIGATION",
            "EXIT_TO_REENTRY_PENDING",
            "CREATE_REENTRY_CONTRACT",
            "Do not run a calculator",
            "Do not select a winning candidate",
            "Do not infer that model failure",
            "update the prior strategic hypothesis",
        )
        for fragment in required:
            self.assertIn(fragment, text)

    def test_challenger_modes_and_non_veto_boundary_are_explicit(self) -> None:
        text = (
            self.packages["trade-decision-challenger"] / "SKILL.md"
        ).read_text(encoding="utf-8")
        required = (
            "ChallengeEnvelope.v1",
            "ChallengeClaim.v1",
            "POST_PROPOSAL",
            "BLIND_CONTEXT_ONLY",
            "valid blinding proof",
            "null proposal references",
            "Do not edit or rewrite proposal bytes",
            "Do not declare a deterministic `ChallengeDisposition`",
            "market_preference_only=true",
            "Do not leak or reconstruct proposal information in blind mode",
        )
        for fragment in required:
            self.assertIn(fragment, text)

    def test_selector_cannot_escape_feasible_set_or_invent_objective(self) -> None:
        text = (
            self.packages["trade-bounded-selector"] / "SKILL.md"
        ).read_text(encoding="utf-8")
        required = (
            "AgentSelection.v1",
            "exact member of the supplied feasible set",
            "DecisionCriterionPolicy.v1",
            "best retained feasible alternative",
            "explicit no-action candidate",
            "opportunity-cost",
            "residual typed unknowns",
            "Do not invent a utility function",
            "Do not silently optimize caution",
            "Do not create, edit, merge, delete, or revalidate a candidate",
        )
        for fragment in required:
            self.assertIn(fragment, text)

    def test_references_record_mutually_exclusive_authority(self) -> None:
        proposer = (
            self.packages["trade-decision-proposer"]
            / "references"
            / "role-contract.md"
        ).read_text(encoding="utf-8")
        challenger = (
            self.packages["trade-decision-challenger"]
            / "references"
            / "role-contract.md"
        ).read_text(encoding="utf-8")
        selector = (
            self.packages["trade-bounded-selector"]
            / "references"
            / "role-contract.md"
        ).read_text(encoding="utf-8")

        self.assertIn("semantic multi-path proposal composition", proposer)
        self.assertNotIn("choice among existing feasible members", proposer)
        self.assertIn("typed conflict and omission claims", challenger)
        self.assertIn("ChallengeDisposition.v1", challenger)
        self.assertIn("choice among existing feasible members", selector)
        self.assertIn("candidate assembly", selector)
        for text in (proposer, challenger, selector):
            self.assertIn(
                "E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false",
                text,
            )

    def test_no_auxiliary_or_executable_skill_files_are_present(self) -> None:
        forbidden_names = {
            "README.md",
            "INSTALLATION_GUIDE.md",
            "QUICK_REFERENCE.md",
            "CHANGELOG.md",
        }
        for package in self.packages.values():
            self.assertFalse(any((package / name).exists() for name in forbidden_names))
            self.assertFalse((package / "scripts").exists())
            self.assertFalse((package / "assets").exists())


if __name__ == "__main__":
    unittest.main()
