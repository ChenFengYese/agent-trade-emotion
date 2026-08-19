#!/usr/bin/env python3
"""Plan and run explicit owning tests without discovery or wide fallback."""

from __future__ import annotations

import argparse
import ast
from fnmatch import fnmatchcase
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Any, TextIO
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_ROOT / "tests" / "targets.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_TOP_FIELDS = {"version", "no_business_tests", "targets"}
_TARGET_FIELDS = {
    "owner",
    "trigger_paths",
    "selectors",
    "budget_seconds",
    "use_when",
    "forbidden_uses",
    "manual_only",
    "escalation",
}
_ESCALATION_FIELDS = {"automatic", "when", "to"}
_TARGET_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SELECTOR = re.compile(
    r"tests(?:\.[A-Za-z_][A-Za-z0-9_]*)+\."
    r"[A-Za-z_][A-Za-z0-9_]*\.test_[A-Za-z0-9_]+\Z"
)


class FocusedTestError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FocusedTestError(f"FOCUSED_CATALOG_DUPLICATE_KEY:{key}")
        result[key] = value
    return result


def _string_list(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
    )


def _normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FocusedTestError("FOCUSED_CHANGED_PATH_INVALID")
    candidate = value[2:] if value.startswith("./") else value
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts or candidate in {"", "."}:
        raise FocusedTestError("FOCUSED_CHANGED_PATH_INVALID")
    return path.as_posix()


def _selector_exists(root: Path, selector: str) -> bool:
    if _SELECTOR.fullmatch(selector) is None:
        return False
    module, class_name, method_name = selector.rsplit(".", 2)
    path = root.joinpath(*module.split(".")).with_suffix(".py")
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError):
        return False
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        return any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name == method_name
            for member in node.body
        )
    return False


def load_catalog(root: Path, path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    catalog_path = path or root / "tests" / "targets.json"
    try:
        catalog = json.loads(
            catalog_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except FocusedTestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FocusedTestError("FOCUSED_CATALOG_UNREADABLE") from exc
    if (
        not isinstance(catalog, dict)
        or set(catalog) != _TOP_FIELDS
        or catalog.get("version") != 1
        or not _string_list(catalog.get("no_business_tests"), allow_empty=True)
        or not isinstance(catalog.get("targets"), dict)
        or not catalog["targets"]
    ):
        raise FocusedTestError("FOCUSED_CATALOG_SHAPE_INVALID")

    for name, target in catalog["targets"].items():
        if _TARGET_NAME.fullmatch(name) is None or not isinstance(target, dict):
            raise FocusedTestError(f"FOCUSED_TARGET_INVALID:{name}")
        if set(target) != _TARGET_FIELDS:
            raise FocusedTestError(f"FOCUSED_TARGET_FIELDS_INVALID:{name}")
        escalation = target.get("escalation")
        budget = target.get("budget_seconds")
        if (
            not isinstance(target.get("owner"), str)
            or not (root / target["owner"]).is_file()
            or not _string_list(target.get("trigger_paths"))
            or not _string_list(target.get("selectors"))
            or len(target["selectors"]) != len(set(target["selectors"]))
            or isinstance(budget, bool)
            or not isinstance(budget, (int, float))
            or budget <= 0
            or not isinstance(target.get("use_when"), str)
            or not target["use_when"]
            or not _string_list(target.get("forbidden_uses"))
            or not isinstance(target.get("manual_only"), bool)
            or not isinstance(escalation, dict)
            or set(escalation) != _ESCALATION_FIELDS
            or escalation.get("automatic") is not False
            or not _string_list(escalation.get("when"), allow_empty=True)
            or not _string_list(escalation.get("to"), allow_empty=True)
        ):
            raise FocusedTestError(f"FOCUSED_TARGET_CONTRACT_INVALID:{name}")
        for pattern in target["trigger_paths"]:
            _normalize_path(pattern)
        for selector in target["selectors"]:
            if not _selector_exists(root, selector):
                raise FocusedTestError(
                    f"FOCUSED_SELECTOR_UNKNOWN_OR_NOT_EXACT:{name}:{selector}"
                )

    names = set(catalog["targets"])
    for name, target in catalog["targets"].items():
        unknown = set(target["escalation"]["to"]) - names
        if unknown:
            raise FocusedTestError(
                f"FOCUSED_ESCALATION_TARGET_UNKNOWN:{name}:{sorted(unknown)}"
            )
    return catalog


def _build_plan(catalog: dict[str, Any], names: list[str]) -> dict[str, Any]:
    unknown = sorted(set(names) - set(catalog["targets"]))
    if unknown:
        raise FocusedTestError(f"FOCUSED_TARGET_UNKNOWN:{unknown}")
    ordered_names = list(dict.fromkeys(names))
    selectors = sorted(
        {
            selector
            for name in ordered_names
            for selector in catalog["targets"][name]["selectors"]
        }
    )
    return {
        "targets": ordered_names,
        "manual_targets": [
            name for name in ordered_names if catalog["targets"][name]["manual_only"]
        ],
        "selectors": selectors,
        "test_count": len(selectors),
        "budget_seconds": sum(
            catalog["targets"][name]["budget_seconds"] for name in ordered_names
        ),
    }


def plan_targets(catalog: dict[str, Any], names: list[str]) -> dict[str, Any]:
    if not names:
        raise FocusedTestError("FOCUSED_TARGET_REQUIRED")
    return _build_plan(catalog, names)


def plan_changed(catalog: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    if not paths:
        raise FocusedTestError("FOCUSED_CHANGED_PATH_REQUIRED")
    selected: set[str] = set()
    manual_recommendations: set[str] = set()
    unmapped: list[str] = []
    normalized = list(dict.fromkeys(_normalize_path(path) for path in paths))
    for path in normalized:
        matches = [
            name
            for name, target in catalog["targets"].items()
            if any(fnmatchcase(path, pattern) for pattern in target["trigger_paths"])
        ]
        for name in matches:
            if catalog["targets"][name]["manual_only"]:
                manual_recommendations.add(name)
            else:
                selected.add(name)
        if not matches and not any(
            fnmatchcase(path, pattern) for pattern in catalog["no_business_tests"]
        ):
            unmapped.append(path)
    if unmapped:
        raise FocusedTestError(f"FOCUSED_CHANGED_PATH_UNMAPPED:{unmapped}")
    plan = _build_plan(catalog, sorted(selected))
    plan["changed_paths"] = normalized
    plan["manual_recommendations"] = sorted(manual_recommendations)
    return plan


def run_plan(plan: dict[str, Any], *, stream: TextIO | None = None) -> dict[str, Any]:
    selectors = plan["selectors"]
    if not selectors:
        status = (
            "MANUAL_RECOMMENDATION_ONLY"
            if plan.get("manual_recommendations")
            else "NO_BUSINESS_TESTS"
        )
        return {**plan, "status": status, "elapsed_seconds": 0.0}
    suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
    if suite.countTestCases() != len(selectors):
        raise FocusedTestError("FOCUSED_RUNTIME_SELECTOR_COUNT_MISMATCH")
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream or sys.stderr, verbosity=2).run(suite)
    elapsed = time.monotonic() - started
    status = "PASS" if result.wasSuccessful() else "FAIL"
    if status == "PASS" and elapsed > plan["budget_seconds"]:
        status = "OVER_BUDGET"
    return {
        **plan,
        "status": status,
        "elapsed_seconds": round(elapsed, 6),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    show = subparsers.add_parser("show")
    show.add_argument("target")
    for command in ("plan", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("targets", nargs="*")
        child.add_argument("--changed", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        catalog = load_catalog(PROJECT_ROOT, args.catalog)
        if args.command == "list":
            output = {
                name: {
                    "manual_only": target["manual_only"],
                    "budget_seconds": target["budget_seconds"],
                    "use_when": target["use_when"],
                }
                for name, target in catalog["targets"].items()
            }
        elif args.command == "show":
            if args.target not in catalog["targets"]:
                raise FocusedTestError(f"FOCUSED_TARGET_UNKNOWN:{args.target}")
            output = catalog["targets"][args.target]
        else:
            if args.targets and args.changed:
                raise FocusedTestError("FOCUSED_TARGET_AND_CHANGED_ARE_EXCLUSIVE")
            plan = (
                plan_changed(catalog, args.changed)
                if args.changed
                else plan_targets(catalog, args.targets)
            )
            output = run_plan(plan) if args.command == "run" else plan
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        if args.command == "run" and output["status"] not in {
            "PASS",
            "NO_BUSINESS_TESTS",
            "MANUAL_RECOMMENDATION_ONLY",
        }:
            return 1
        return 0
    except FocusedTestError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
