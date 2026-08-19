"""Deterministic source identity for the installed trading-system package."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Dict


SOFTWARE_IDENTITY_SCHEMA = "trade-system-package-source-v1"


def package_source_sha256(package_root: Path = None) -> str:
    root = Path(package_root) if package_root is not None else Path(__file__).resolve().parent
    rows = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    if not rows:
        raise ValueError("trading-system package contains no Python sources")
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def collector_software_binding(package_root: Path = None) -> Dict[str, Any]:
    return {
        "schema_version": SOFTWARE_IDENTITY_SCHEMA,
        "package_source_sha256": package_source_sha256(package_root),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }
