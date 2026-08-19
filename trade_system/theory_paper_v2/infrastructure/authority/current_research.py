"""Load and physically verify the current research-start authority document."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ...domain.contracts.canonical import load_json_strict
from ...domain.governance.research_authority import (
    ResearchAuthorityError,
    assert_research_start_authorized,
    validate_research_authorization_receipt,
    validate_research_authority,
)


CURRENT_RESEARCH_AUTHORITY_PATH = Path(
    "config/theory_paper_v2.current_research_authority.v1.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_file(project: Path, relative_path: str, code: str) -> Path:
    try:
        target = (project / relative_path).resolve(strict=True)
        target.relative_to(project)
    except (OSError, ValueError) as exc:
        raise ResearchAuthorityError(code) from exc
    if not target.is_file():
        raise ResearchAuthorityError(code)
    return target


def load_current_research_authority(project_root: Path) -> dict[str, Any]:
    project = Path(project_root).resolve(strict=True)
    authority_path = _contained_file(
        project,
        CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        "CURRENT_RESEARCH_AUTHORITY_FILE_INVALID",
    )
    document = load_json_strict(authority_path)
    validate_research_authority(document)
    for field in ("current_theory", "candidate_theory"):
        binding = document[field]
        theory_path = _contained_file(
            project,
            str(binding["path"]),
            "CURRENT_THEORY_BINDING_PATH_INVALID",
        )
        if _sha256_file(theory_path) != binding["physical_sha256"]:
            raise ResearchAuthorityError(f"CURRENT_THEORY_BINDING_DRIFT:{field}")
    return document


def _load_authorization_receipt(
    project: Path, authority: dict[str, Any]
) -> dict[str, Any] | None:
    receipt_ref = authority.get("authorization_receipt_path")
    if receipt_ref is None:
        return None
    receipt_path = _contained_file(
        project,
        str(receipt_ref),
        "CURRENT_RESEARCH_AUTHORIZATION_RECEIPT_PATH_INVALID",
    )
    receipt = load_json_strict(receipt_path)
    validate_research_authorization_receipt(receipt, authority)
    return receipt


def assert_current_research_start_authorized(
    *,
    project_root: Path,
    operation: str,
    run_id: str,
    template_path: Path,
) -> dict[str, Any]:
    project = Path(project_root).resolve(strict=True)
    authority = load_current_research_authority(project)
    try:
        template_candidate = Path(template_path)
        if not template_candidate.is_absolute():
            template_candidate = project / template_candidate
        template = template_candidate.resolve(strict=True)
        template.relative_to(project)
    except (OSError, ValueError) as exc:
        raise ResearchAuthorityError("RESEARCH_TEMPLATE_PATH_INVALID") from exc
    assert_research_start_authorized(
        authority,
        operation=operation,
        run_id=run_id,
        template_sha256=_sha256_file(template),
        authorization_receipt=_load_authorization_receipt(project, authority),
    )
    return authority


__all__ = [
    "CURRENT_RESEARCH_AUTHORITY_PATH",
    "assert_current_research_start_authorized",
    "load_current_research_authority",
]
