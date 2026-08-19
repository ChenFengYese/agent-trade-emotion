"""Offline-only R2 source-identity and terms contract verifier.

This module intentionally has no network opener, CLI entrypoint, runtime writer,
or activation capability.  A later independent Sol gate must freeze request URLs
and authorize any production transport separately.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "/Users/wt/Documents/agent-trade-emotion"
BRANCH = "codex/s0-research-foundation"
HEAD = "7ca3fc4f99a57f98217e703f222b295653ace87e"
ROUTE_PATH = "config/sol_decision.research-system-pit-authority-replay-sd0-source-identity-terms-r2-route.v1.json"
ROUTE_PHYSICAL_SHA256 = "8ef6022e737e0d5b3945c55f983cac3bd1557e9e7b5f87b8d079d735c282129e"
ROUTE_CANONICAL_SHA256 = "bb1448a71983ffb080e85ec49b2e89f7940a72006e8e24ba7c01941644626f0b"
CONTRACT_PATH = "config/pit_authority_replay.sd0_source_identity_terms_r2_measurement_contract.v1.json"
PLAN_PATH = "config/pit_authority_replay.sd0_source_identity_terms_r2_request_plan.v1.json"
CLIENT_VERSION = "pitar1-sd0-source-identity-terms-r2-metered-fetch-v1"
PREDECESSOR_IDENTITIES = {
    "artifacts/pit_authority_replay_sd0_closure_report.v1.json": "14a92eebc44449678e977f9cb57838d306e2627caf38e63b39fc565bef502e2f",
    ".runtime/pitar1-sd0-v1/receipts/requests.ndjson": "ef50d386c54f7540acf0d9417391e29bc0a2cad606dd97d8d8a80482569d8cd8",
    ".runtime/pitar1-sd0-v1/receipts/response_headers.ndjson": "22d501419228dd43f5c91083023e3982694b14201fd1a53a723b954caadbacd0",
}
INTENDED_SCOPES = (
    "AUTOMATED_DOWNLOAD_OF_EXACT_PUBLIC_MARKET_DATA_OBJECT",
    "LOCAL_RESEARCH_RETENTION",
    "INTERNAL_DERIVED_RESEARCH_ARTIFACTS",
    "NO_REDISTRIBUTION_UNLESS_SEPARATELY_EXPLICITLY_ALLOWED",
)
ALLOWED_SCOPE_OUTCOMES = {"EXPLICITLY_ALLOWED", "EXPLICITLY_PROHIBITED", "SILENT_OR_AMBIGUOUS", "NOT_APPLICABLE"}


class R2Error(RuntimeError):
    def __init__(self, state: str, detail: str) -> None:
        super().__init__(detail)
        self.state = state


@dataclass(frozen=True)
class TermsAssessment:
    terminal_disposition: str
    scope_outcomes: dict[str, str]
    source_identity_status: str
    production_activation: str


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _self(domain: str, value: Mapping[str, Any], field: str) -> str:
    copied = dict(value)
    copied.pop(field, None)
    return _sha(domain.encode("utf-8") + b"\0" + _canon(copied))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise R2Error("HALT_PROTOCOL_VIOLATION", "duplicate JSON key")
        result[key] = value
    return result


def _finite(value: Any) -> Any:
    if not math.isfinite(value):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "non-finite JSON value")
    return value


def strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, R2Error):
            raise
        raise R2Error("HALT_PROTOCOL_VIOLATION", "invalid JSON") from exc
    if not isinstance(value, dict):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "JSON root must be object")
    return value


def _safe_read(root: Path, relative: str) -> bytes:
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise R2Error("HALT_PROTOCOL_VIOLATION", "unsafe required path")
    cursor = root
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise R2Error("HALT_PROTOCOL_VIOLATION", "symlink rejected")
    return candidate.read_bytes()


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def _verify_workspace(root: Path) -> None:
    if root.resolve() != Path(WORKSPACE):
        raise R2Error("WAIT_DATA_PRODUCTION_ACTIVATION_DENIED", "alternate root is not authorized")
    if _git(root, "branch", "--show-current") != BRANCH or _git(root, "rev-parse", "HEAD") != HEAD:
        raise R2Error("HALT_PROTOCOL_VIOLATION", "workspace identity drift")


def _verify_route(root: Path) -> dict[str, Any]:
    raw = _safe_read(root, ROUTE_PATH)
    if _sha(raw) != ROUTE_PHYSICAL_SHA256:
        raise R2Error("HALT_PROTOCOL_VIOLATION", "route physical identity drift")
    route = strict_json(raw)
    if (
        route.get("decision_sha256") != ROUTE_CANONICAL_SHA256
        or _self("msta-hed/sol-research-system-pit-authority-replay-sd0-source-identity-terms-r2-route/v1", route, "decision_sha256") != ROUTE_CANONICAL_SHA256
        or route.get("decision_state") != "AUTHORIZE_SOURCE_IDENTITY_AND_TERMS_R2_CONTRACT_DRAFTING_AND_OFFLINE_TESTS_PRODUCTION_SUSPENDED"
    ):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "route canonical identity or scope drift")
    return route


def _verify_predecessor(root: Path) -> None:
    for relative, expected in PREDECESSOR_IDENTITIES.items():
        if _sha(_safe_read(root, relative)) != expected:
            raise R2Error("HALT_PROTOCOL_VIOLATION", "predecessor evidence drift")


def _verify_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "pitar1-sd0-source-identity-terms-r2-measurement-contract.v1":
        raise R2Error("HALT_PROTOCOL_VIOLATION", "contract schema")
    if contract.get("activation_status") != "DENIED_PENDING_INDEPENDENT_SOL_GATE":
        raise R2Error("HALT_PROTOCOL_VIOLATION", "contract activation")
    if tuple(contract.get("intended_use_scopes", [])) != INTENDED_SCOPES:
        raise R2Error("HALT_PROTOCOL_VIOLATION", "scope contract drift")
    if contract.get("terms_rules", {}).get("repository_software_license_is_market_data_authority") is not False:
        raise R2Error("HALT_PROTOCOL_VIOLATION", "software license cannot authorize market data")
    if _self("pitar1/sd0-source-identity-terms-r2-measurement-contract/v1", contract, "contract_sha256") != contract.get("contract_sha256"):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "contract canonical identity")


def _verify_plan(plan: Mapping[str, Any], contract_raw: bytes, contract: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != "pitar1-sd0-source-identity-terms-r2-request-plan.v1":
        raise R2Error("HALT_PROTOCOL_VIOLATION", "plan schema")
    if plan.get("activation_status") != "DENIED_PENDING_INDEPENDENT_SOL_GATE" or plan.get("requests") != []:
        raise R2Error("WAIT_DATA_PRODUCTION_ACTIVATION_DENIED", "draft plan has no executable request authority")
    binding = plan.get("measurement_contract", {})
    if binding.get("physical_sha256") != _sha(contract_raw) or binding.get("canonical_sha256") != contract.get("contract_sha256"):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "contract binding drift")
    if _self("pitar1/sd0-source-identity-terms-r2-request-plan/v1", plan, "plan_sha256") != plan.get("plan_sha256"):
        raise R2Error("HALT_PROTOCOL_VIOLATION", "plan canonical identity")


def load_draft(root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the new static drafts and return them; this never performs I/O beyond local reads."""
    _verify_workspace(root)
    _verify_route(root)
    _verify_predecessor(root)
    contract_raw = _safe_read(root, CONTRACT_PATH)
    contract = strict_json(contract_raw)
    plan = strict_json(_safe_read(root, PLAN_PATH))
    _verify_contract(contract)
    _verify_plan(plan, contract_raw, contract)
    return contract, plan


def production_activation_status(root: Path = ROOT) -> str:
    """A hard stop retained even after every offline draft check passes."""
    load_draft(root)
    return "WAIT_DATA_PRODUCTION_ACTIVATION_DENIED"


def validate_observation_shape(observation: Mapping[str, Any]) -> None:
    required = {
        "exact_url", "effective_url", "method", "status_code", "response_body_bytes", "response_header_bytes",
        "elapsed_monotonic_ns", "tls_validation_result", "proxy_endpoint", "redirect_chain", "response_body_sha256",
    }
    if set(observation) != required or observation["method"] != "GET":
        raise R2Error("HALT_PROTOCOL_VIOLATION", "observation shape")
    if not isinstance(observation["redirect_chain"], list) or observation["effective_url"] != observation["exact_url"] or observation["redirect_chain"]:
        raise R2Error("HALT_PROTOCOL_VIOLATION", "redirect or effective URL mismatch")
    if observation["status_code"] != 200 or observation["tls_validation_result"] != "VALIDATED" or observation["response_body_bytes"] <= 0:
        raise R2Error("WAIT_DATA_TERMS_D0_DENIED", "official terms object is unavailable or unusable")


def assess_terms(
    scope_outcomes: Mapping[str, str], *, actor: str, jurisdiction: str, repository_identity_complete: bool
) -> TermsAssessment:
    """Assess explicit text classifications, never infer permissions from a license label."""
    if not isinstance(actor, str) or not actor.strip() or not isinstance(jurisdiction, str) or not jurisdiction.strip():
        return TermsAssessment("WAIT_DATA_TERMS_D0_DENIED", dict(scope_outcomes), "UNRESOLVED", "DENIED")
    if set(scope_outcomes) != set(INTENDED_SCOPES) or any(value not in ALLOWED_SCOPE_OUTCOMES for value in scope_outcomes.values()):
        return TermsAssessment("WAIT_DATA_TERMS_D0_DENIED", dict(scope_outcomes), "UNRESOLVED", "DENIED")
    if not repository_identity_complete:
        return TermsAssessment("WAIT_DATA_SOURCE_IDENTITY_UNRESOLVED", dict(scope_outcomes), "UNRESOLVED", "DENIED")
    # A legal conclusion is intentionally not self-issued here: even complete
    # explicit classifications remain pending the later independent gate.
    if any(scope_outcomes[scope] != "EXPLICITLY_ALLOWED" for scope in INTENDED_SCOPES):
        return TermsAssessment("WAIT_DATA_TERMS_D0_DENIED", dict(scope_outcomes), "COMPLETE", "DENIED")
    return TermsAssessment("WAIT_DATA_PRODUCTION_ACTIVATION_DENIED", dict(scope_outcomes), "COMPLETE", "DENIED")
