"""Fail closed before any February market-input access after the A2F1 terminal hold.

This guard deliberately reads only local governance JSON from deterministic
workspace locations.  It has no ZIP, checksum, downloader, or scorer imports.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional


POLICY_PATH = Path("config/s0_009_february_terminal_seen_guard.a3e1.json")
POLICY_SHA256 = "5cdc23c6d0db3c84c89016920835265faba5c70f0c8520a1328b652029bd5e8a"
AUTHORITY_ROOT = Path(__file__).resolve().parents[1]


class FebruaryTerminalSeenError(ValueError):
    """The exact February diagnostic is terminal and cannot access inputs."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _fail(message: str) -> None:
    raise FebruaryTerminalSeenError("S0-009 February terminal-SEEN guard: " + message)


def _require_authority_root(workspace_root: Optional[Path]) -> Path:
    if workspace_root is None:
        return AUTHORITY_ROOT
    candidate = Path(workspace_root)
    if candidate.is_symlink() or candidate.resolve() != AUTHORITY_ROOT:
        _fail("alternate or symlinked workspace root is not an authority override")
    return AUTHORITY_ROOT


def _authority_file(root: Path, relative: str, label: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        _fail(label + " path is not workspace-relative")
    path = root / relative_path
    if path.is_symlink() or not path.is_file():
        _fail(label + " is missing or symlinked")
    return path


def _load_authority_json(root: Path, relative: str, expected_sha256: str, label: str) -> Mapping[str, Any]:
    path = _authority_file(root, relative, label)
    if _sha256_file(path) != expected_sha256:
        _fail(label + " SHA-256 drifted")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FebruaryTerminalSeenError("S0-009 February terminal-SEEN guard: cannot parse " + label) from exc
    if not isinstance(value, dict):
        _fail(label + " must be a JSON object")
    return value


def _require_supplied_authority_path(value: Path, expected: Path, label: str) -> None:
    supplied = Path(value)
    if supplied.is_symlink() or supplied.resolve() != expected:
        _fail(label + " path is not the deterministic authority path")


def reject_february_terminal_seen_attempt(
    *,
    plan_path: Path,
    receipt_path: Path,
    workspace_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    registry_path: Optional[Path] = None,
) -> None:
    """Always reject the exact terminal February identity before market I/O.

    ``output_path`` and ``registry_path`` are deliberately non-authoritative:
    changing them cannot make a terminal February attempt admissible.
    """
    del output_path, registry_path
    root = _require_authority_root(workspace_root)
    policy = _load_authority_json(root, str(POLICY_PATH), POLICY_SHA256, "A3E1 policy")
    identity = policy.get("diagnostic_identity")
    artifacts = policy.get("deterministic_authority_artifacts")
    required_terminal = policy.get("required_terminal_state")
    if not isinstance(identity, dict) or not isinstance(artifacts, dict) or not isinstance(required_terminal, dict):
        _fail("A3E1 policy structure drifted")

    expected_plan = _authority_file(root, identity.get("plan_path", ""), "frozen February plan")
    expected_receipt = _authority_file(root, identity.get("receipt_path", ""), "R1 receipt")
    _require_supplied_authority_path(plan_path, expected_plan, "plan")
    _require_supplied_authority_path(receipt_path, expected_receipt, "receipt")

    config = _load_authority_json(root, artifacts["a2f1_config"]["path"], artifacts["a2f1_config"]["sha256"], "A2F1 config")
    terminal = _load_authority_json(root, artifacts["a2f1_terminal"]["path"], artifacts["a2f1_terminal"]["sha256"], "A2F1 terminal")
    supersession = _load_authority_json(root, artifacts["a2f1_supersession"]["path"], artifacts["a2f1_supersession"]["sha256"], "A2F1 supersession")

    try:
        plan = json.loads(expected_plan.read_text(encoding="utf-8"))
        receipt = json.loads(expected_receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FebruaryTerminalSeenError("S0-009 February terminal-SEEN guard: cannot parse identity artifact") from exc
    if not isinstance(plan, dict) or not isinstance(receipt, dict):
        _fail("identity artifacts must be JSON objects")
    if plan.get("diagnostic_id") != identity.get("diagnostic_id") or tuple(plan.get("dates", ())) != tuple(identity.get("dates", ())):
        _fail("February diagnostic identity drifted")
    if receipt.get("receipt_id") != identity.get("receipt_id"):
        _fail("R1 receipt identity drifted")
    if _canonical_sha256(receipt.get("authorized_targets")) != identity.get("target_set_canonical_sha256"):
        _fail("R1 canonical target-set digest drifted")

    if config.get("decision_id") != required_terminal.get("decision_id") or config.get("artifact_revision") != required_terminal.get("artifact_revision"):
        _fail("A2F1 config identity drifted")
    if config.get("execution_state") != required_terminal.get("state") or config.get("execution_gate") != required_terminal.get("execution_gate"):
        _fail("A2F1 config terminal state drifted")
    for key in ("decision_id", "artifact_revision", "state", "execution_gate", "input_role", "independent_evaluation_role", "score_executed", "g2_eligibility", "trading_authorization"):
        if terminal.get(key) != required_terminal.get(key):
            _fail("A2F1 terminal %s drifted" % key)
    if supersession.get("decision_unchanged") is not True or supersession.get("new_authorization_created") is not False:
        _fail("A2F1 supersession continuity drifted")

    _fail("February 2025 is terminal SEEN and no builder, receipt, registry, or scorer path may continue")


def reject_if_bound_february_terminal_identity(
    *,
    plan_path: Path,
    receipt_path: Path,
    workspace_root: Optional[Path],
    output_path: Optional[Path] = None,
    registry_path: Optional[Path] = None,
) -> None:
    """Reject the exact R1 February identity, while leaving synthetic fixtures alone.

    The identity probe reads only the two supplied JSON documents.  A matching
    plan/receipt is then handed to the strict deterministic-authority guard,
    so a copied root, a symlink, or alternate output/registry cannot bypass it.
    """
    supplied_plan = Path(plan_path)
    supplied_receipt = Path(receipt_path)
    # Never parse a market archive masquerading as an identity document.  A
    # symlink is also an immediate terminal rejection rather than a route to
    # an alternate authority tree.
    if (
        supplied_plan.is_symlink()
        or supplied_receipt.is_symlink()
        or str(supplied_plan).endswith((".zip", ".CHECKSUM"))
        or str(supplied_receipt).endswith((".zip", ".CHECKSUM"))
    ):
        reject_february_terminal_seen_attempt(
            plan_path=supplied_plan,
            receipt_path=supplied_receipt,
            workspace_root=workspace_root,
            output_path=output_path,
            registry_path=registry_path,
        )
    policy = _load_authority_json(AUTHORITY_ROOT, str(POLICY_PATH), POLICY_SHA256, "A3E1 policy")
    identity = policy["diagnostic_identity"]
    try:
        plan = json.loads(supplied_plan.read_text(encoding="utf-8"))
        receipt = json.loads(supplied_receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(plan, dict) or not isinstance(receipt, dict):
        return
    if (
        plan.get("diagnostic_id") == identity["diagnostic_id"]
        and tuple(plan.get("dates", ())) == tuple(identity["dates"])
        and receipt.get("receipt_id") == identity["receipt_id"]
    ):
        reject_february_terminal_seen_attempt(
            plan_path=supplied_plan,
            receipt_path=supplied_receipt,
            workspace_root=workspace_root,
            output_path=output_path,
            registry_path=registry_path,
        )


def reject_if_terminal_receipt_id(*, receipt_id: str, registry_path: Optional[Path] = None) -> None:
    """Prevent direct registry mutation for the terminal R1 receipt identity."""
    policy = _load_authority_json(AUTHORITY_ROOT, str(POLICY_PATH), POLICY_SHA256, "A3E1 policy")
    if receipt_id == policy["diagnostic_identity"]["receipt_id"]:
        reject_february_terminal_seen_attempt(
            plan_path=AUTHORITY_ROOT / policy["diagnostic_identity"]["plan_path"],
            receipt_path=AUTHORITY_ROOT / policy["diagnostic_identity"]["receipt_path"],
            workspace_root=AUTHORITY_ROOT,
            registry_path=registry_path,
        )


__all__ = [
    "FebruaryTerminalSeenError",
    "reject_february_terminal_seen_attempt",
    "reject_if_bound_february_terminal_identity",
    "reject_if_terminal_receipt_id",
]
