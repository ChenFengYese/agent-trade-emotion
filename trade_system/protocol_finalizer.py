"""Safe G1-only finalization of a fully preregistered research protocol."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .g1_report import load_verified_g1_report
from .protocol import (
    FROZEN_STATUS,
    PENDING_G1_DIGEST,
    PENDING_PROTOCOL_STATUS,
    V2_SCHEMA_VERSION,
    V2_PROTOCOL_ID,
    ProtocolError,
    ProtocolSupersessionGuard,
    ResearchProtocol,
    canonical_sha256,
)
from .types import iso_utc, utc_now


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unresolved(value: Any, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _unresolved(child, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _unresolved(child, "%s[%d]" % (path, index))
    elif isinstance(value, str) and (value.startswith("REQUIRED:") or value.startswith("PENDING_")):
        yield path, value


def finalize_research_protocol(
    preregistered_path: Path,
    *,
    g1_report_path: Path,
    output_path: Path,
    supersession_guard_path: Path,
    frozen_at: str = "",
) -> Dict[str, Any]:
    """Fill only the verified G1 digest and freeze into a new file."""
    try:
        pending = json.loads(Path(preregistered_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot load preregistered protocol") from exc
    if not isinstance(pending, dict) or pending.get("status") != PENDING_PROTOCOL_STATUS:
        raise ProtocolError("protocol finalizer requires status %s" % PENDING_PROTOCOL_STATUS)
    guard = ProtocolSupersessionGuard.load(Path(supersession_guard_path))
    guard.assert_legacy_v1_is_protected()
    if pending.get("schema_version") != V2_SCHEMA_VERSION or pending.get("protocol_id") != V2_PROTOCOL_ID:
        raise ProtocolError("protocol finalizer only accepts the unique v2 preregistration")
    pending_sha = canonical_sha256(pending)
    guard.assert_trusted_v2_lineage(pending)
    # Loading first enforces the common action/availability contract without
    # granting frozen-research status.
    ResearchProtocol.load(Path(preregistered_path))
    eligibility = pending.get("data_eligibility")
    if not isinstance(eligibility, dict):
        raise ProtocolError("v2 protocol is missing data eligibility")
    eligibility = eligibility.get("g1_qualification")
    if not isinstance(eligibility, dict) or eligibility.get("required_g1_report_sha256") != PENDING_G1_DIGEST:
        raise ProtocolError("preregistered protocol must contain the untouched pending G1 digest sentinel")
    report = load_verified_g1_report(Path(g1_report_path), require_pass=True)
    if report.get("policy_id") != eligibility.get("required_g1_policy_id"):
        raise ProtocolError("PASS G1 report policy ID does not match preregistration")
    expected_policy_sha = eligibility.get("required_g1_policy_sha256")
    if not isinstance(expected_policy_sha, str) or report.get("policy_sha256") != expected_policy_sha:
        raise ProtocolError("PASS G1 report policy digest does not match preregistration")
    requirements = report.get("requirements")
    source_registry = pending.get("source_registry")
    if not isinstance(requirements, dict) or not isinstance(source_registry, dict):
        raise ProtocolError("PASS G1 report is missing frozen source requirements")
    if requirements.get("source_registry_id") != source_registry.get("registry_id") or requirements.get("source_registry_sha256") != source_registry.get("sha256"):
        raise ProtocolError("PASS G1 source registry does not match preregistration")
    result = deepcopy(pending)
    result["status"] = FROZEN_STATUS
    result["frozen_at"] = frozen_at or iso_utc(utc_now())
    result["data_eligibility"]["g1_qualification"]["required_g1_report_sha256"] = report["report_sha256"]
    unresolved = list(_unresolved(result))
    if unresolved:
        raise ProtocolError("frozen protocol contains unresolved value at %s" % unresolved[0][0])
    # The domain validator is applied before any output path is created.
    ResearchProtocol._validate_v2(result)
    guard.assert_trusted_v2_lineage(result)
    canonical = _canonical(result)
    protocol_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ProtocolError("frozen protocol output already exists: %s" % target)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ProtocolError("cannot write frozen research protocol") from exc
    # Load the exact persisted bytes as the final postcondition.
    persisted = ResearchProtocol.load(target)
    if persisted.digest != protocol_sha:
        raise ProtocolError("persisted frozen protocol digest changed unexpectedly")
    return {
        "record_type": "research_protocol_finalization",
        "protocol_id": persisted.protocol_id,
        "status": persisted.status,
        "preregistered_protocol_sha256": pending_sha,
        "g1_report_sha256": report["report_sha256"],
        "protocol_sha256": persisted.digest,
        "output": str(target),
        "live_trading_authorization": result.get("live_trading_authorization", "UNSPECIFIED"),
    }
