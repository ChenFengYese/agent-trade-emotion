from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.infrastructure.authority import (
    v31_runtime_closure_v2 as closure_v2,
)


def _write(root: Path, relative_path: str, source: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _base_project(root: Path) -> None:
    _write(root, "pkg/__init__.py", "\n")
    _write(root, "pkg/app/__init__.py", "\n")
    _write(
        root,
        "pkg/app/root.py",
        "from ..domain import helper\n"
        "from pkg.adapters import bridge\n"
        "import json\n",
    )
    _write(root, "pkg/domain/__init__.py", "\n")
    _write(root, "pkg/domain/helper.py", "VALUE = 1\n")
    _write(root, "pkg/adapters/__init__.py", "\n")
    _write(root, "pkg/adapters/bridge.py", "from ..domain import helper\n")
    _write(root, "pkg/runtime_hook.py", "from .trace_support import VALUE\n")
    _write(root, "pkg/trace_support.py", "VALUE = 2\n")
    _write(root, "pkg/unrelated.py", "VALUE = 3\n")


class V31RuntimeClosureV2Tests(unittest.TestCase):
    def test_static_closure_recurses_and_adds_every_package_initializer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base_project(root)

            paths = closure_v2.collect_v31_static_runtime_closure_v2(
                project_root=root,
                production_root_paths=("pkg/app/root.py",),
            )

            self.assertEqual(
                (
                    "pkg/__init__.py",
                    "pkg/adapters/__init__.py",
                    "pkg/adapters/bridge.py",
                    "pkg/app/__init__.py",
                    "pkg/app/root.py",
                    "pkg/domain/__init__.py",
                    "pkg/domain/helper.py",
                ),
                paths,
            )

    def test_trace_comparison_controls_trace_only_module_and_returns_hashes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base_project(root)
            trace = ("pkg/app/root.py", "pkg/runtime_hook.py")

            comparison = closure_v2.compare_v31_runtime_closure_with_trace_v2(
                project_root=root,
                production_root_paths=("pkg/app/root.py",),
                trace_paths=trace,
            )
            bindings = closure_v2.build_v31_runtime_closure_bindings_v2(
                project_root=root,
                production_root_paths=("pkg/app/root.py",),
                trace_paths=trace,
            )

            self.assertEqual(("pkg/runtime_hook.py",), comparison.trace_only_paths)
            self.assertEqual(comparison.controlled_union_paths, tuple(bindings))
            self.assertIn("pkg/runtime_hook.py", bindings)
            self.assertIn("pkg/trace_support.py", bindings)
            self.assertEqual(
                hashlib.sha256((root / "pkg/runtime_hook.py").read_bytes()).hexdigest(),
                bindings["pkg/runtime_hook.py"],
            )
            self.assertEqual(
                bindings,
                closure_v2.verify_v31_runtime_closure_bindings_v2(
                    project_root=root,
                    production_root_paths=("pkg/app/root.py",),
                    trace_paths=trace,
                    frozen_bindings=bindings,
                ),
            )

    def test_missing_trace_binding_and_physical_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base_project(root)
            trace = ("pkg/app/root.py", "pkg/runtime_hook.py")
            bindings = closure_v2.build_v31_runtime_closure_bindings_v2(
                project_root=root,
                production_root_paths=("pkg/app/root.py",),
                trace_paths=trace,
            )
            missing_trace = dict(bindings)
            missing_trace.pop("pkg/runtime_hook.py")

            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_TRACE_PATH_UNBOUND",
            ):
                closure_v2.verify_v31_runtime_closure_bindings_v2(
                    project_root=root,
                    production_root_paths=("pkg/app/root.py",),
                    trace_paths=trace,
                    frozen_bindings=missing_trace,
                )

            extra_binding = dict(bindings)
            extra_binding["pkg/unrelated.py"] = hashlib.sha256(
                (root / "pkg/unrelated.py").read_bytes()
            ).hexdigest()
            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_BINDING_PATH_SET_INVALID",
            ):
                closure_v2.verify_v31_runtime_closure_bindings_v2(
                    project_root=root,
                    production_root_paths=("pkg/app/root.py",),
                    trace_paths=trace,
                    frozen_bindings=extra_binding,
                )

            _write(root, "pkg/domain/helper.py", "VALUE = 2\n")
            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_PHYSICAL_DRIFT",
            ):
                closure_v2.verify_v31_runtime_closure_bindings_v2(
                    project_root=root,
                    production_root_paths=("pkg/app/root.py",),
                    trace_paths=trace,
                    frozen_bindings=bindings,
                )

    def test_dynamic_import_and_relative_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base_project(root)
            _write(
                root,
                "pkg/dynamic.py",
                "import importlib\n"
                "target = 'pkg.runtime_hook'\n"
                "importlib.import_module(target)\n",
            )
            _write(root, "pkg/escape.py", "from ..outside import value\n")

            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_DYNAMIC_IMPORT_FORBIDDEN",
            ):
                closure_v2.collect_v31_static_runtime_closure_v2(
                    project_root=root,
                    production_root_paths=("pkg/dynamic.py",),
                )
            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_RELATIVE_IMPORT_ESCAPE",
            ):
                closure_v2.collect_v31_static_runtime_closure_v2(
                    project_root=root,
                    production_root_paths=("pkg/escape.py",),
                )

    def test_symlink_and_unsafe_trace_path_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _base_project(root)
            (root / "pkg/link.py").symlink_to(root / "pkg/domain/helper.py")

            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_SYMLINK_FORBIDDEN",
            ):
                closure_v2.collect_v31_static_runtime_closure_v2(
                    project_root=root,
                    production_root_paths=("pkg/link.py",),
                )
            with self.assertRaisesRegex(
                closure_v2.V31RuntimeClosureError,
                "V31_RUNTIME_CLOSURE_TRACE_PATHS_INVALID",
            ):
                closure_v2.compare_v31_runtime_closure_with_trace_v2(
                    project_root=root,
                    production_root_paths=("pkg/app/root.py",),
                    trace_paths=("pkg/app/root.py", "../outside.py"),
                )


if __name__ == "__main__":
    unittest.main()
