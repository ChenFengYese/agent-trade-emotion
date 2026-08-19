"""Frozen, credential-free provenance contract for one local paper run."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .paper_audit import _canonical, audit_paper_trail
from .action_policy import ResearchActionPolicy
from .model_artifact import ModelArtifact
from .research_report import sha256_file
from .risk_gate_profile import RiskGateProfile
from .source_registry import SourceRegistry
from .state_classifier import StateClassifier
from .types import iso_utc, utc_now


FROZEN_PAPER_RUN_CONTRACT = "FROZEN_PAPER_RUN_CONTRACT"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class PaperRunContractError(ValueError):
    pass


def _digest(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_empty(raw: Dict[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise PaperRunContractError("%s must be a non-empty string" % name)
    return value


def _binding(raw: Dict[str, Any], name: str) -> Dict[str, str]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise PaperRunContractError("bindings.%s must be an object" % name)
    identity = value.get("id")
    digest = value.get("sha256")
    if not isinstance(identity, str) or not identity or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise PaperRunContractError("bindings.%s requires id and lowercase SHA-256" % name)
    return {"id": identity, "sha256": digest}


@dataclass(frozen=True)
class PaperRunContract:
    contract_id: str
    schema_version: str
    frozen_at: str
    bindings: Dict[str, Dict[str, str]]
    digest: str

    @classmethod
    def load(cls, path: Path) -> "PaperRunContract":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperRunContractError("cannot load paper run contract") from exc
        if not isinstance(raw, dict):
            raise PaperRunContractError("paper run contract must be an object")
        contract_id = _non_empty(raw, "contract_id")
        schema_version = _non_empty(raw, "schema_version")
        if raw.get("status") != FROZEN_PAPER_RUN_CONTRACT:
            raise PaperRunContractError("paper run contract must be frozen")
        frozen_at = _non_empty(raw, "frozen_at")
        try:
            parsed = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise PaperRunContractError("frozen_at must be ISO-8601 with timezone") from exc
        if raw.get("scope") != "PAPER_ONLY" or raw.get("permissions") != {"credentials": "FORBIDDEN", "orders": "FORBIDDEN", "withdrawals": "FORBIDDEN"}:
            raise PaperRunContractError("paper run contract must remain credential-free and order-free")
        bindings_raw = raw.get("bindings")
        if not isinstance(bindings_raw, dict):
            raise PaperRunContractError("bindings are required")
        required = ("model", "action_policy", "risk_gate_profile", "source_registry", "state_classifier", "input_evidence")
        if set(bindings_raw) != set(required):
            raise PaperRunContractError("bindings must define model, action_policy, risk_gate_profile, source_registry, state_classifier and input_evidence")
        bindings = {name: _binding(bindings_raw, name) for name in required}
        execution = raw.get("execution")
        if not isinstance(execution, dict) or execution != {"broker": "LOCAL_PAPER_IOC", "allow_live_execution": False, "allow_testnet_execution": False}:
            raise PaperRunContractError("execution must be fixed to LOCAL_PAPER_IOC with no live or testnet execution")
        return cls(contract_id, schema_version, frozen_at, bindings, _digest(raw))

    def audit_context(self) -> Dict[str, Any]:
        return {
            "scope": "PAPER_ONLY",
            "paper_run_contract_id": self.contract_id,
            "paper_run_contract_sha256": self.digest,
            "bindings": self.bindings,
            "credentials_or_order_capability": False,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema_version": self.schema_version,
            "frozen_at": self.frozen_at,
            "sha256": self.digest,
            "binding_ids": {name: value["id"] for name, value in self.bindings.items()},
            "credentials_or_order_capability": False,
        }


def _started_context(audit_path: Path) -> Dict[str, Any]:
    try:
        with Path(audit_path).open("r", encoding="utf-8") as handle:
            first = json.loads(handle.readline())
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperRunContractError("cannot read paper audit start event") from exc
    try:
        context = first["payload"]["context"]
    except (KeyError, TypeError) as exc:
        raise PaperRunContractError("paper audit start context is missing") from exc
    if not isinstance(context, dict):
        raise PaperRunContractError("paper audit start context must be an object")
    return context


def verify_paper_run_binding(audit_path: Path, contract: PaperRunContract) -> Dict[str, Any]:
    audit = audit_paper_trail(Path(audit_path))
    context = _started_context(Path(audit_path))
    context_matches = context == contract.audit_context()
    return {
        "record_type": "paper_run_binding_verification",
        "valid": bool(audit["valid"] and context_matches),
        "audit_valid": audit["valid"],
        "context_matches_contract": context_matches,
        "audit": audit,
        "contract_id": contract.contract_id,
        "contract_sha256": contract.digest,
        "limitation": "Verifies only a local paper audit and frozen local bindings. It cannot establish market-data truth, exchange acceptance, testnet/live execution, account reconciliation or trading authorization.",
    }


def verify_paper_run_evidence(
    contract: PaperRunContract,
    *,
    model_artifact_path: Path,
    action_policy_path: Path,
    risk_gate_profile_path: Path,
    source_registry_path: Path,
    state_classifier_path: Path,
    input_evidence_path: Path,
    input_evidence_id: str,
) -> Dict[str, Any]:
    """Verify contract bindings against the exact local artifacts supplied."""
    if not isinstance(input_evidence_id, str) or not input_evidence_id:
        raise PaperRunContractError("input_evidence_id is required")
    try:
        model = ModelArtifact.load(Path(model_artifact_path))
        action = ResearchActionPolicy.load(Path(action_policy_path))
        risk = RiskGateProfile.load(Path(risk_gate_profile_path))
        source = SourceRegistry.load(Path(source_registry_path))
        state = StateClassifier.load(Path(state_classifier_path))
        hashes = {
            "model": sha256_file(Path(model_artifact_path)),
            "input_evidence": sha256_file(Path(input_evidence_path)),
        }
    except (OSError, ValueError) as exc:
        raise PaperRunContractError("cannot load or hash paper run evidence") from exc
    observed = {
        "model": {"id": model.model_id, "sha256": hashes["model"]},
        "action_policy": {"id": action.policy_id, "sha256": action.digest},
        "risk_gate_profile": {"id": risk.profile_id, "sha256": risk.digest},
        "source_registry": {"id": source.registry_id, "sha256": source.sha256},
        "state_classifier": {"id": state.classifier_id, "sha256": state.digest},
        "input_evidence": {"id": input_evidence_id, "sha256": hashes["input_evidence"]},
    }
    mismatches = {
        name: {"expected": contract.bindings[name], "observed": observed[name]}
        for name in contract.bindings if contract.bindings[name] != observed[name]
    }
    return {
        "record_type": "paper_run_evidence_verification",
        "valid": not mismatches,
        "contract_id": contract.contract_id,
        "contract_sha256": contract.digest,
        "mismatches": mismatches,
        "observed_bindings": observed,
        "limitation": "Matches supplied local files to frozen binding digests only. It does not establish that the files were generated from sufficient evidence, that their contents are economically valid, or that any paper/testnet/live order was accepted.",
    }


def seal_paper_run(audit_path: Path, contract: PaperRunContract, output_path: Path) -> Dict[str, Any]:
    verification = verify_paper_run_binding(Path(audit_path), contract)
    if not verification["valid"]:
        raise PaperRunContractError("paper audit is not finalized or does not match the supplied frozen run contract")
    audit = verification["audit"]
    manifest = {
        "record_type": "paper_run_manifest",
        "schema_version": "paper-run-manifest.v1",
        "written_at": iso_utc(utc_now()),
        "contract_id": contract.contract_id,
        "contract_sha256": contract.digest,
        "audit_path": str(audit_path),
        "audit_file_sha256": audit["file_sha256"],
        "audit_tail_event_sha256": audit["tail_event_sha256"],
        "audit_event_count": audit["event_count"],
        "run_id": audit["run_id"],
        "limitation": "A sealed local paper manifest binds one finalized local audit to frozen version evidence; it is not a paper/testnet account reconciliation, exchange-signed result, G3 proof or trading authorization.",
    }
    manifest["manifest_sha256"] = _digest(manifest)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise PaperRunContractError("paper run manifest already exists")
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise PaperRunContractError("cannot write paper run manifest") from exc
    return manifest
