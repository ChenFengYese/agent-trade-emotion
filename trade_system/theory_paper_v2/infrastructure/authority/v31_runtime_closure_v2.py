"""Contained static and observed-import closure for a successor V3.1 freeze.

The active V3.1 authority uses an explicit historical path list.  This module
does not alter that list.  It builds a successor binding set from explicit
production roots, project-local static imports, package initializers, and a
caller-supplied fresh-process import trace.

No import is executed here.  Dynamic import APIs are rejected because their
targets cannot be proven by static analysis.  Trace-only Python modules are
also parsed recursively before they may join the controlled union.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


class V31RuntimeClosureError(ValueError):
    """A successor runtime closure or binding is unsafe or incomplete."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_DYNAMIC_IMPORT_CALLS = frozenset(
    {
        "__import__",
        "import_module",
        "spec_from_file_location",
        "SourceFileLoader",
        "SourcelessFileLoader",
        "ExtensionFileLoader",
    }
)


@dataclass(frozen=True, slots=True)
class V31RuntimeClosureComparison:
    """Static-versus-observed paths and their recursively controlled union."""

    production_root_paths: tuple[str, ...]
    static_paths: tuple[str, ...]
    trace_paths: tuple[str, ...]
    trace_only_paths: tuple[str, ...]
    static_not_traced_paths: tuple[str, ...]
    controlled_union_paths: tuple[str, ...]


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_ROOT_SYMLINK")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_PROJECT_ROOT_INVALID")
    return root


def _relative_python_path(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise V31RuntimeClosureError(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or path.suffix != ".py"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31RuntimeClosureError(code)
    return value


def _contained_source(root: Path, relative_path: str) -> Path:
    relative = _relative_python_path(
        relative_path, "V31_RUNTIME_CLOSURE_PATH_INVALID"
    )
    cursor = root
    try:
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31RuntimeClosureError(
                    "V31_RUNTIME_CLOSURE_SYMLINK_FORBIDDEN"
                )
        target = cursor.resolve(strict=True)
        target.relative_to(root)
    except V31RuntimeClosureError:
        raise
    except (OSError, ValueError) as exc:
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_PATH_ESCAPE_OR_MISSING"
        ) from exc
    if not target.is_file() or target.is_symlink():
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_SOURCE_REQUIRED")
    return target


def _existing_source(root: Path, relative_path: str) -> Path | None:
    relative = _relative_python_path(
        relative_path, "V31_RUNTIME_CLOSURE_PATH_INVALID"
    )
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise V31RuntimeClosureError(
                "V31_RUNTIME_CLOSURE_SYMLINK_FORBIDDEN"
            )
        if not cursor.exists():
            return None
    return _contained_source(root, relative)


def _normalize_path_set(
    root: Path,
    values: Sequence[str],
    *,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise V31RuntimeClosureError(code)
    try:
        rows = tuple(values)
    except TypeError as exc:
        raise V31RuntimeClosureError(code) from exc
    if (
        (not allow_empty and not rows)
        or any(not isinstance(row, str) for row in rows)
        or len(rows) != len(set(rows))
    ):
        raise V31RuntimeClosureError(code)
    normalized = tuple(
        _relative_python_path(row, code)
        for row in rows
    )
    for relative_path in normalized:
        _contained_source(root, relative_path)
    return tuple(sorted(normalized))


def _ancestor_initializers(root: Path, relative_path: str) -> tuple[str, ...]:
    parts = PurePosixPath(relative_path).parts
    initializers: list[str] = []
    for index in range(1, len(parts)):
        candidate = PurePosixPath(*parts[:index], "__init__.py").as_posix()
        if _existing_source(root, candidate) is not None:
            initializers.append(candidate)
    return tuple(initializers)


def _module_and_package(relative_path: str) -> tuple[str, tuple[str, ...]]:
    path = PurePosixPath(relative_path)
    if path.name == "__init__.py":
        package_parts = path.parts[:-1]
        return ".".join(package_parts), package_parts
    module_parts = (*path.parts[:-1], path.stem)
    return ".".join(module_parts), path.parts[:-1]


def _module_candidates(module_name: str) -> tuple[str, str]:
    parts = tuple(module_name.split("."))
    if not parts or any(not part or not part.isidentifier() for part in parts):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_MODULE_NAME_INVALID")
    stem = PurePosixPath(*parts).as_posix()
    return f"{stem}.py", f"{stem}/__init__.py"


def _resolve_local_module(root: Path, module_name: str) -> str | None:
    if not module_name:
        return None
    found = [
        candidate
        for candidate in _module_candidates(module_name)
        if _existing_source(root, candidate) is not None
    ]
    if len(found) > 1:
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_AMBIGUOUS_LOCAL_MODULE"
        )
    return found[0] if found else None


def _top_level_is_local(root: Path, module_name: str) -> bool:
    top = module_name.split(".", 1)[0]
    module_file, package_init = _module_candidates(top)
    if _existing_source(root, module_file) is not None:
        return True
    if _existing_source(root, package_init) is not None:
        return True
    directory = root / top
    if directory.is_symlink():
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_SYMLINK_FORBIDDEN")
    return directory.is_dir()


def _absolute_from_module(
    node: ast.ImportFrom,
    *,
    package_parts: tuple[str, ...],
) -> str:
    if node.level == 0:
        return node.module or ""
    if node.level > len(package_parts):
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_RELATIVE_IMPORT_ESCAPE"
        )
    retained = package_parts[: len(package_parts) - node.level + 1]
    suffix = tuple((node.module or "").split(".")) if node.module else ()
    return ".".join((*retained, *suffix))


def _reject_dynamic_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            continue
        if name in _DYNAMIC_IMPORT_CALLS:
            raise V31RuntimeClosureError(
                "V31_RUNTIME_CLOSURE_DYNAMIC_IMPORT_FORBIDDEN"
            )


def _parse_source(root: Path, relative_path: str) -> ast.Module:
    path = _contained_source(root, relative_path)
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=relative_path)
    except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_SOURCE_PARSE_INVALID"
        ) from exc


def _local_import_paths(
    root: Path,
    *,
    relative_path: str,
    tree: ast.Module,
) -> tuple[str, ...]:
    _module_name, package_parts = _module_and_package(relative_path)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_local_module(root, alias.name)
                if resolved is not None:
                    imported.add(resolved)
                elif _top_level_is_local(root, alias.name):
                    raise V31RuntimeClosureError(
                        "V31_RUNTIME_CLOSURE_LOCAL_IMPORT_MISSING"
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = _absolute_from_module(
                node,
                package_parts=package_parts,
            )
            resolved_any = False
            base = _resolve_local_module(root, module_name)
            if base is not None:
                imported.add(base)
                resolved_any = True
            for alias in node.names:
                if alias.name == "*":
                    continue
                child_name = ".".join(
                    part for part in (module_name, alias.name) if part
                )
                child = _resolve_local_module(root, child_name)
                if child is not None:
                    imported.add(child)
                    resolved_any = True
            if node.level and not resolved_any:
                raise V31RuntimeClosureError(
                    "V31_RUNTIME_CLOSURE_LOCAL_IMPORT_MISSING"
                )
            if (
                not node.level
                and module_name
                and not resolved_any
                and _top_level_is_local(root, module_name)
            ):
                raise V31RuntimeClosureError(
                    "V31_RUNTIME_CLOSURE_LOCAL_IMPORT_MISSING"
                )
    return tuple(sorted(imported))


def _collect_static_closure(
    root: Path,
    production_root_paths: tuple[str, ...],
) -> tuple[str, ...]:
    closure: set[str] = set()
    pending = list(reversed(production_root_paths))
    while pending:
        relative_path = pending.pop()
        if relative_path in closure:
            continue
        _contained_source(root, relative_path)
        closure.add(relative_path)
        dependencies = set(_ancestor_initializers(root, relative_path))
        tree = _parse_source(root, relative_path)
        _reject_dynamic_imports(tree)
        dependencies.update(
            _local_import_paths(
                root,
                relative_path=relative_path,
                tree=tree,
            )
        )
        for dependency in sorted(dependencies, reverse=True):
            if dependency not in closure:
                pending.append(dependency)
    return tuple(sorted(closure))


def collect_v31_static_runtime_closure_v2(
    *,
    project_root: Path,
    production_root_paths: Sequence[str],
) -> tuple[str, ...]:
    """Return the deterministic project-local AST closure of explicit roots."""

    root = _project_root(project_root)
    normalized_roots = _normalize_path_set(
        root,
        production_root_paths,
        code="V31_RUNTIME_CLOSURE_PRODUCTION_ROOTS_INVALID",
        allow_empty=False,
    )
    return _collect_static_closure(root, normalized_roots)


def compare_v31_runtime_closure_with_trace_v2(
    *,
    project_root: Path,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
) -> V31RuntimeClosureComparison:
    """Compare a caller-recorded fresh-process trace with the static closure."""

    root = _project_root(project_root)
    normalized_roots = _normalize_path_set(
        root,
        production_root_paths,
        code="V31_RUNTIME_CLOSURE_PRODUCTION_ROOTS_INVALID",
        allow_empty=False,
    )
    normalized_trace = _normalize_path_set(
        root,
        trace_paths,
        code="V31_RUNTIME_CLOSURE_TRACE_PATHS_INVALID",
        allow_empty=False,
    )
    if not set(normalized_roots).issubset(normalized_trace):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_TRACE_ROOT_MISSING")
    static_paths = _collect_static_closure(root, normalized_roots)
    controlled_roots = tuple(sorted(set(normalized_roots) | set(normalized_trace)))
    controlled_union = _collect_static_closure(root, controlled_roots)
    static_set = set(static_paths)
    trace_set = set(normalized_trace)
    return V31RuntimeClosureComparison(
        production_root_paths=normalized_roots,
        static_paths=static_paths,
        trace_paths=normalized_trace,
        trace_only_paths=tuple(sorted(trace_set - static_set)),
        static_not_traced_paths=tuple(sorted(static_set - trace_set)),
        controlled_union_paths=controlled_union,
    )


def _sha256_source(root: Path, relative_path: str) -> str:
    path = _contained_source(root, relative_path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_v31_runtime_closure_bindings_v2(
    *,
    project_root: Path,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
) -> dict[str, str]:
    """Return ordered SHA-256 bindings for the controlled static/trace union."""

    root = _project_root(project_root)
    comparison = compare_v31_runtime_closure_with_trace_v2(
        project_root=root,
        production_root_paths=production_root_paths,
        trace_paths=trace_paths,
    )
    return {
        path: _sha256_source(root, path)
        for path in comparison.controlled_union_paths
    }


def verify_v31_runtime_closure_bindings_v2(
    *,
    project_root: Path,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
    frozen_bindings: Mapping[str, str],
) -> dict[str, str]:
    """Rebuild and verify the exact ordered closure and every physical hash."""

    root = _project_root(project_root)
    comparison = compare_v31_runtime_closure_with_trace_v2(
        project_root=root,
        production_root_paths=production_root_paths,
        trace_paths=trace_paths,
    )
    if not isinstance(frozen_bindings, Mapping):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_BINDINGS_INVALID")
    if any(path not in frozen_bindings for path in comparison.trace_paths):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_TRACE_PATH_UNBOUND")
    if tuple(frozen_bindings) != comparison.controlled_union_paths:
        raise V31RuntimeClosureError(
            "V31_RUNTIME_CLOSURE_BINDING_PATH_SET_INVALID"
        )
    if any(
        not isinstance(digest, str) or _HEX_64.fullmatch(digest) is None
        for digest in frozen_bindings.values()
    ):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_BINDINGS_INVALID")
    actual = {
        path: _sha256_source(root, path)
        for path in comparison.controlled_union_paths
    }
    if actual != dict(frozen_bindings):
        raise V31RuntimeClosureError("V31_RUNTIME_CLOSURE_PHYSICAL_DRIFT")
    return actual


__all__ = [
    "V31RuntimeClosureComparison",
    "V31RuntimeClosureError",
    "build_v31_runtime_closure_bindings_v2",
    "collect_v31_static_runtime_closure_v2",
    "compare_v31_runtime_closure_with_trace_v2",
    "verify_v31_runtime_closure_bindings_v2",
]
