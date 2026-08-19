"""Verifier for a bounded, non-adjudicating historical evidence ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


FROZEN_LEDGER = "FROZEN_BINANCE_CM_HISTORICAL_EVIDENCE_LEDGER_V1"


class HistoricalEvidenceLedgerError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_sha(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoricalEvidenceLedgerError("cannot load %s" % label) from exc
    if not isinstance(value, dict):
        raise HistoricalEvidenceLedgerError("%s must be an object" % label)
    return value


def _relative(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HistoricalEvidenceLedgerError("%s is required" % field)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HistoricalEvidenceLedgerError("%s must be a workspace-relative path" % field)
    return root / path


def verify_historical_evidence_ledger(ledger_path: Path, *, workspace_root: Path) -> Dict[str, Any]:
    """Recheck the exact v1 plan/report/software receipts without adjudicating Hs."""
    ledger = _load(ledger_path, "historical evidence ledger")
    if ledger.get("status") != FROZEN_LEDGER:
        raise HistoricalEvidenceLedgerError("ledger is not frozen")
    if ledger.get("evidence_stage") != "E0-X" or ledger.get("current_action") != "STOP_CURRENT_V1_ACTION":
        raise HistoricalEvidenceLedgerError("ledger must remain a stopped E0-X record")
    if ledger.get("eligible_for_binance_g2") is not False or ledger.get("trading_authorization") != "DENIED":
        raise HistoricalEvidenceLedgerError("ledger cannot grant G2 or trading eligibility")
    adjudications = ledger.get("hypothesis_adjudications")
    required = {"H-001": "NOT_ADJUDICATED", "H-002": "NOT_ADJUDICATED", "H-003": "WAIT_DATA", "H-004": "NOT_TESTED"}
    if adjudications != required:
        raise HistoricalEvidenceLedgerError("ledger hypothesis adjudications differ from frozen v1 scope")
    dates = ledger.get("date_evidence")
    if not isinstance(dates, list) or [item.get("date") for item in dates if isinstance(item, dict)] != ["2025-01-%02d" % day for day in range(1, 29)] or any(item.get("status") != "SEEN_DEVELOPMENT" for item in dates):
        raise HistoricalEvidenceLedgerError("every January date must be recorded as SEEN_DEVELOPMENT")
    root = Path(workspace_root).resolve()
    plan_binding = ledger.get("plan")
    report_binding = ledger.get("report")
    software = ledger.get("software_bindings")
    if not isinstance(plan_binding, dict) or not isinstance(report_binding, dict) or not isinstance(software, dict):
        raise HistoricalEvidenceLedgerError("ledger bindings are incomplete")
    plan_path = _relative(root, plan_binding.get("path"), "plan.path")
    report_path = _relative(root, report_binding.get("path"), "report.path")
    if sha256_file(plan_path) != plan_binding.get("file_sha256") or sha256_file(report_path) != report_binding.get("file_sha256"):
        raise HistoricalEvidenceLedgerError("bound plan/report file digest drifted")
    report = _load(report_path, "bound historical report")
    plan = _load(plan_path, "bound historical plan")
    if _canonical_sha(plan) != plan_binding.get("report_plan_sha256") or report.get("plan_sha256") != plan_binding.get("report_plan_sha256"):
        raise HistoricalEvidenceLedgerError("bound plan canonical digest drifted")
    audit = report.get("input_audit")
    if not isinstance(audit, dict) or _canonical_sha(audit) != report_binding.get("input_manifest_sha256") or report.get("input_manifest_sha256") != report_binding.get("input_manifest_sha256"):
        raise HistoricalEvidenceLedgerError("bound report provenance drifted")
    expected = ledger.get("expected_report")
    if not isinstance(expected, dict):
        raise HistoricalEvidenceLedgerError("expected_report is required")
    required_fields = {"venue": "BINANCE_COINM", "instrument": "BTCUSD_PERP", "plan_status": "FROZEN_BINANCE_CM_HISTORICAL_MECHANISM_PLAN_V1", "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
    if any(report.get(key) != value for key, value in required_fields.items()):
        raise HistoricalEvidenceLedgerError("bound report safety boundary drifted")
    if report.get("rows") != expected.get("rows") or report.get("cost_descriptive", {}).get("locked_evaluation") != expected.get("locked_evaluation_cost"):
        raise HistoricalEvidenceLedgerError("bound report sample/cost facts drifted")
    report_software = report.get("software_bindings")
    if not isinstance(report_software, dict) or report_software.get("entrypoint") != software.get("entrypoint"):
        raise HistoricalEvidenceLedgerError("bound software entrypoint drifted")
    for item in (software.get("experiment_module"), software.get("model")):
        if not isinstance(item, dict):
            raise HistoricalEvidenceLedgerError("software receipt is invalid")
    experiment_path = _relative(root, software["experiment_module"].get("workspace_path"), "experiment_module.workspace_path")
    model_path = _relative(root, software["model"].get("workspace_path"), "model.workspace_path")
    if (report_software.get("experiment_module", {}).get("sha256") != software["experiment_module"].get("sha256") or report_software.get("model", {}).get("module_sha256") != software["model"].get("module_sha256") or sha256_file(experiment_path) != software["experiment_module"].get("sha256") or sha256_file(model_path) != software["model"].get("module_sha256")):
        raise HistoricalEvidenceLedgerError("bound software source digest drifted")
    return {"record_type": "historical_evidence_ledger_verification.v1", "ledger_id": ledger.get("ledger_id"), "binding_verified": True, "evidence_stage": "E0-X", "current_action": "STOP_CURRENT_V1_ACTION", "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
