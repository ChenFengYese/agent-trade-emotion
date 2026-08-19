"""Read-only access to already materialized legacy evaluation artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...domain.contracts.canonical import load_json_strict, verify_self_digest


class LegacyReadOnlyError(ValueError):
    pass


def read_existing_evaluation(*, run_root: Path) -> dict[str, Any]:
    root = Path(run_root).resolve(strict=True)
    checkpoint = load_json_strict(root / "checkpoint.json")
    candidates = []
    evaluation_path = checkpoint.get("evaluation_path")
    if isinstance(evaluation_path, str) and evaluation_path:
        candidates.append(root / evaluation_path)
    candidates.extend(
        (
            root / "evaluation" / "raw-evaluation.json",
            root / "evaluation.json",
        )
    )
    for path in candidates:
        if not path.is_file():
            continue
        document = load_json_strict(path)
        for digest_field in (
            "evaluation_digest",
            "raw_evaluation_digest",
            "report_digest",
        ):
            if digest_field in document:
                try:
                    verify_self_digest(document, digest_field)
                except ValueError as exc:
                    raise LegacyReadOnlyError("LEGACY_EVALUATION_DIGEST_INVALID") from exc
                return {
                    "status": "EXISTING_EVALUATION_READ_ONLY",
                    "path": path.relative_to(root).as_posix(),
                    "evaluation": document,
                    "mutation_performed": False,
                }
        raise LegacyReadOnlyError("LEGACY_EVALUATION_DIGEST_MISSING")
    return {
        "status": "LEGACY_EVALUATION_NOT_MATERIALIZED",
        "path": None,
        "evaluation": None,
        "mutation_performed": False,
    }
