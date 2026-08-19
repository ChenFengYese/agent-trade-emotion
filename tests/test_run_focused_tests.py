from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import run_focused_tests


class FocusedTestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "owner.py").write_text("OWNER = True\n")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_sample.py").write_text(
            "import unittest\n\n"
            "class SampleTests(unittest.TestCase):\n"
            "    def test_one(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

    def catalog(self) -> dict:
        return {
            "version": 1,
            "no_business_tests": ["docs/**"],
            "targets": {
                "sample": {
                    "owner": "tools/owner.py",
                    "trigger_paths": ["src/sample.py"],
                    "selectors": [
                        "tests.test_sample.SampleTests.test_one"
                    ],
                    "budget_seconds": 1,
                    "use_when": "sample changes",
                    "forbidden_uses": ["not integration evidence"],
                    "manual_only": False,
                    "escalation": {
                        "automatic": False,
                        "when": [],
                        "to": [],
                    },
                }
            },
        }

    def write_catalog(self, catalog: dict | str) -> Path:
        path = self.root / "tests" / "targets.json"
        text = catalog if isinstance(catalog, str) else json.dumps(catalog)
        path.write_text(text, encoding="utf-8")
        return path

    def test_repository_catalog_is_valid_and_marks_slow_targets_manual(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn(str(root), run_focused_tests.sys.path)
        catalog = run_focused_tests.load_catalog(root)
        self.assertTrue(catalog["targets"])
        self.assertTrue(catalog["targets"]["v32-cycle-acceptance-e2e"]["manual_only"])
        self.assertTrue(catalog["targets"]["v32-market-graph-replay"]["manual_only"])
        for target in catalog["targets"].values():
            self.assertTrue(target["use_when"])
            self.assertTrue(target["forbidden_uses"])
            for selector in target["selectors"]:
                self.assertNotIn("*", selector)
                self.assertIsNotNone(run_focused_tests._SELECTOR.fullmatch(selector))

    def test_plan_deduplicates_shared_exact_test_ids(self):
        catalog = self.catalog()
        catalog["targets"]["second"] = deepcopy(catalog["targets"]["sample"])
        loaded = run_focused_tests.load_catalog(
            self.root, self.write_catalog(catalog)
        )
        plan = run_focused_tests.plan_targets(loaded, ["sample", "second"])
        self.assertEqual(1, plan["test_count"])
        self.assertEqual(
            ["tests.test_sample.SampleTests.test_one"], plan["selectors"]
        )
        self.assertEqual(2, plan["budget_seconds"])

    def test_changed_paths_map_targets_and_docs_can_plan_zero(self):
        catalog = self.catalog()
        catalog["targets"]["manual-check"] = deepcopy(
            catalog["targets"]["sample"]
        )
        catalog["targets"]["manual-check"]["manual_only"] = True
        loaded = run_focused_tests.load_catalog(
            self.root, self.write_catalog(catalog)
        )
        changed = run_focused_tests.plan_changed(loaded, ["src/sample.py"])
        self.assertEqual(["sample"], changed["targets"])
        self.assertEqual(["manual-check"], changed["manual_recommendations"])
        docs = run_focused_tests.plan_changed(loaded, ["docs/guide.md"])
        self.assertEqual([], docs["targets"])
        self.assertEqual([], docs["selectors"])
        self.assertEqual(
            "NO_BUSINESS_TESTS", run_focused_tests.run_plan(docs)["status"]
        )

        catalog["targets"]["sample"]["trigger_paths"] = ["src/other.py"]
        manual_only = run_focused_tests.plan_changed(catalog, ["src/sample.py"])
        self.assertEqual([], manual_only["selectors"])
        self.assertEqual(
            "MANUAL_RECOMMENDATION_ONLY",
            run_focused_tests.run_plan(manual_only)["status"],
        )

    def test_unmapped_change_fails_before_runner(self):
        loaded = run_focused_tests.load_catalog(
            self.root, self.write_catalog(self.catalog())
        )
        with patch.object(run_focused_tests, "run_plan") as runner, self.assertRaisesRegex(
            run_focused_tests.FocusedTestError, "CHANGED_PATH_UNMAPPED"
        ):
            plan = run_focused_tests.plan_changed(loaded, ["src/unknown.py"])
            runner(plan)
        runner.assert_not_called()

    def test_catalog_rejects_duplicate_keys_wildcards_and_unknown_selectors(self):
        duplicate = (
            '{"version":1,"version":1,"no_business_tests":[],"targets":{}}'
        )
        with self.assertRaisesRegex(
            run_focused_tests.FocusedTestError, "DUPLICATE_KEY"
        ):
            run_focused_tests.load_catalog(
                self.root, self.write_catalog(duplicate)
            )

        wildcard = self.catalog()
        wildcard["targets"]["sample"]["selectors"] = ["tests.test_sample.*"]
        with self.assertRaisesRegex(
            run_focused_tests.FocusedTestError, "SELECTOR_UNKNOWN_OR_NOT_EXACT"
        ):
            run_focused_tests.load_catalog(
                self.root, self.write_catalog(wildcard)
            )

        unknown = self.catalog()
        unknown["targets"]["sample"]["selectors"] = [
            "tests.test_sample.SampleTests.test_missing"
        ]
        with self.assertRaisesRegex(
            run_focused_tests.FocusedTestError, "SELECTOR_UNKNOWN_OR_NOT_EXACT"
        ):
            run_focused_tests.load_catalog(
                self.root, self.write_catalog(unknown)
            )

    def test_run_uses_exact_selectors_and_reports_budget_without_widening(self):
        selectors = ["tests.test_sample.SampleTests.test_one"]
        plan = {
            "targets": ["sample"],
            "manual_targets": [],
            "selectors": selectors,
            "test_count": 1,
            "budget_seconds": 1,
        }
        suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        with patch.object(
            run_focused_tests.unittest.defaultTestLoader,
            "loadTestsFromNames",
            return_value=suite,
        ) as loader, patch.object(
            run_focused_tests.time, "monotonic", side_effect=[10.0, 12.0]
        ):
            result = run_focused_tests.run_plan(plan, stream=io.StringIO())
        loader.assert_called_once_with(selectors)
        self.assertEqual("OVER_BUDGET", result["status"])
        self.assertNotIn("discover", str(loader.call_args))


if __name__ == "__main__":
    unittest.main()
