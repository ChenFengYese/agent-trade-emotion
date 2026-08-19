from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "trade_system"
    / "theory_paper_v2"
)


def _import_targets(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            targets.append((node.lineno, node.module or ""))
        elif isinstance(node, ast.Import):
            targets.extend((node.lineno, alias.name) for alias in node.names)
    return targets


def _contains_layer(target: str, layer: str) -> bool:
    return layer in target.split(".")


class V32LayerDependencyTests(unittest.TestCase):
    def test_domain_v32_modules_do_not_import_outer_layers(self) -> None:
        violations: list[str] = []
        for path in sorted((PACKAGE_ROOT / "domain").glob("v32*.py")):
            for line, target in _import_targets(path):
                if any(
                    _contains_layer(target, layer)
                    for layer in ("application", "infrastructure", "presentation")
                ):
                    violations.append(f"{path.name}:{line}:{target}")
        self.assertEqual([], violations)

    def test_application_v32_modules_do_not_import_infrastructure(self) -> None:
        violations: list[str] = []
        for path in sorted((PACKAGE_ROOT / "application").glob("v32*.py")):
            for line, target in _import_targets(path):
                if _contains_layer(target, "infrastructure"):
                    violations.append(f"{path.name}:{line}:{target}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
