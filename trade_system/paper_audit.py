"""Write-once, locally verifiable audit trail for paper OMS lifecycle events.

The trail is deliberately transport-free and stores no credentials or account
data. It detects accidental or local-file tampering through a chained digest;
it is not a substitute for an exchange-signed execution record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import iso_utc, parse_utc, utc_now


class PaperAuditError(ValueError):
    pass


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso_utc(value)
    raise TypeError("paper audit value is not JSON serializable")


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _digest(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class PaperAuditTrail:
    """Single-process append-only audit trail with an explicit terminal event."""

    def __init__(self, path: Path, *, run_id: str, context: Dict[str, Any]) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise PaperAuditError("run_id contains unsupported characters")
        if not isinstance(context, dict):
            raise PaperAuditError("paper audit context must be an object")
        self.path = Path(path)
        if self.path.exists():
            raise PaperAuditError("paper audit path already exists: %s" % self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._sequence = 0
        self._previous_digest: Optional[str] = None
        self._finalized = False
        self._event_count = 0
        self.append("RUN_STARTED", {"context": context}, observed_at=utc_now())

    def append(self, event_type: str, payload: Dict[str, Any], *, observed_at: Optional[datetime] = None) -> Dict[str, Any]:
        if self._finalized:
            raise PaperAuditError("paper audit trail is already finalized")
        if not isinstance(event_type, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", event_type):
            raise PaperAuditError("paper audit event_type is invalid")
        if not isinstance(payload, dict):
            raise PaperAuditError("paper audit payload must be an object")
        occurred = observed_at or utc_now()
        if occurred.tzinfo is None:
            raise PaperAuditError("paper audit observed_at must be timezone aware")
        self._sequence += 1
        event = {
            "record_type": "paper_audit_event",
            "schema_version": "paper-audit.v1",
            "run_id": self.run_id,
            "sequence": self._sequence,
            "event_type": event_type,
            "observed_at": iso_utc(occurred),
            "previous_event_sha256": self._previous_digest,
            "payload": payload,
        }
        event["event_sha256"] = _digest(event)
        try:
            with self.path.open("a" if self.path.exists() else "x", encoding="utf-8") as handle:
                handle.write(_canonical(event) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise PaperAuditError("cannot append paper audit event") from exc
        self._previous_digest = event["event_sha256"]
        self._event_count += 1
        return dict(event)

    def finalize(self, final_state: Dict[str, Any], *, observed_at: Optional[datetime] = None) -> Dict[str, Any]:
        event = self.append("RUN_FINALIZED", {"final_state": final_state}, observed_at=observed_at)
        self._finalized = True
        return event

    def summary(self) -> Dict[str, Any]:
        if not self._finalized:
            raise PaperAuditError("paper audit trail has not been finalized")
        return {
            "path": str(self.path),
            "run_id": self.run_id,
            "event_count": self._event_count,
            "tail_event_sha256": self._previous_digest,
        }


def audit_paper_trail(path: Path) -> Dict[str, Any]:
    """Verify ordered hashes and require one final event as the final record."""
    target = Path(path)
    issues: List[str] = []
    expected_sequence = 1
    previous_digest: Optional[str] = None
    run_id: Optional[str] = None
    event_count = 0
    finalized = False
    file_digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for line_number, line in enumerate(handle, start=1):
                file_digest.update(line)
                if not line.strip():
                    issues.append("blank line at %d" % line_number)
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    issues.append("invalid JSON at %d" % line_number)
                    continue
                if not isinstance(event, dict):
                    issues.append("non-object event at %d" % line_number)
                    continue
                if event.get("record_type") != "paper_audit_event" or event.get("schema_version") != "paper-audit.v1":
                    issues.append("invalid event identity at %d" % line_number)
                    continue
                if event.get("sequence") != expected_sequence:
                    issues.append("unexpected sequence at %d" % line_number)
                event_run_id = event.get("run_id")
                if not isinstance(event_run_id, str) or not _RUN_ID.fullmatch(event_run_id):
                    issues.append("invalid run_id at %d" % line_number)
                elif run_id is None:
                    run_id = event_run_id
                elif run_id != event_run_id:
                    issues.append("run_id changed at %d" % line_number)
                if event.get("previous_event_sha256") != previous_digest:
                    issues.append("previous digest mismatch at %d" % line_number)
                event_digest = event.get("event_sha256")
                body = dict(event)
                body.pop("event_sha256", None)
                if not isinstance(event_digest, str) or event_digest != _digest(body):
                    issues.append("event digest mismatch at %d" % line_number)
                try:
                    parse_utc(str(event.get("observed_at")))
                except ValueError:
                    issues.append("invalid observed_at at %d" % line_number)
                if event_count == 0 and event.get("event_type") != "RUN_STARTED":
                    issues.append("first event must be RUN_STARTED")
                if finalized:
                    issues.append("event appears after finalization at %d" % line_number)
                if event.get("event_type") == "RUN_FINALIZED":
                    finalized = True
                previous_digest = event_digest if isinstance(event_digest, str) else None
                expected_sequence += 1
                event_count += 1
    except OSError:
        issues.append("cannot read paper audit trail")
    if event_count == 0:
        issues.append("paper audit trail is empty")
    if not finalized:
        issues.append("paper audit trail is not finalized")
    return {
        "path": str(target),
        "valid": not issues,
        "issues": issues,
        "run_id": run_id,
        "event_count": event_count,
        "tail_event_sha256": previous_digest,
        "file_sha256": file_digest.hexdigest(),
        "limitation": "Local chained hashes detect file inconsistency but are not a venue-signed execution record or proof of live trading.",
    }


def _read_verified_event_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperAuditError("cannot read verified paper audit events") from exc
    return rows


def write_paper_recovery_report(
    audit_path: Path,
    output_path: Path,
    *,
    confirm_process_stopped: bool,
) -> Dict[str, Any]:
    """Write a fail-closed recovery handoff for an unfinalized local run.

    The report intentionally never reconstructs an executable OMS or changes
    the audit trail. A future account adapter must reconcile the listed local
    expectation with the venue before any new risk can be considered.
    """
    if not confirm_process_stopped:
        raise PaperAuditError("paper recovery requires --confirm-process-stopped")
    audit = audit_paper_trail(Path(audit_path))
    integrity_issues = [issue for issue in audit["issues"] if issue != "paper audit trail is not finalized"]
    if integrity_issues:
        raise PaperAuditError("paper audit trail has integrity errors and cannot be recovered")
    if audit["valid"]:
        raise PaperAuditError("finalized paper audit trail does not require recovery")
    if audit["issues"] != ["paper audit trail is not finalized"]:
        raise PaperAuditError("paper audit trail is not an eligible interrupted run")
    events = _read_verified_event_rows(Path(audit_path))
    latest_state: Optional[Dict[str, Any]] = None
    for event in reversed(events):
        payload = event.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("state"), dict):
            latest_state = dict(payload["state"])
            break
    orders = latest_state.get("orders", {}) if isinstance(latest_state, dict) else {}
    expected_open_client_order_ids = []
    if isinstance(orders, dict):
        for order in orders.values():
            if not isinstance(order, dict):
                continue
            if order.get("status") in {"SUBMITTED", "ACKNOWLEDGED", "PARTIAL"} and isinstance(order.get("client_order_id"), str):
                expected_open_client_order_ids.append(order["client_order_id"])
    report = {
        "record_type": "paper_audit_recovery_report",
        "schema_version": "paper-audit-recovery.v1",
        "recovery_status": "HALT_AND_RECONCILE_REQUIRED",
        "written_at": iso_utc(utc_now()),
        "run_id": audit["run_id"],
        "audit_path": str(audit_path),
        "audit_file_sha256": audit["file_sha256"],
        "audit_tail_event_sha256": audit["tail_event_sha256"],
        "audit_event_count": audit["event_count"],
        "expected_open_client_order_ids": sorted(expected_open_client_order_ids),
        "last_local_state": latest_state,
        "required_next_step": "Reconcile orders, fills, position, protection and balances against a read-only venue snapshot before any new risk; do not auto-resume this local run.",
        "limitation": "This report is a local fail-closed handoff, not account reconciliation, exchange acknowledgement or permission to trade.",
    }
    report["report_sha256"] = _digest(report)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise PaperAuditError("paper recovery report already exists: %s" % output)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(report) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise PaperAuditError("cannot write paper recovery report") from exc
    return report


def verify_paper_recovery_report(report_path: Path, audit_path: Path) -> Dict[str, Any]:
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperAuditError("cannot load paper recovery report") from exc
    if not isinstance(report, dict) or report.get("record_type") != "paper_audit_recovery_report" or report.get("schema_version") != "paper-audit-recovery.v1":
        raise PaperAuditError("invalid paper recovery report identity")
    digest = report.get("report_sha256")
    body = dict(report)
    body.pop("report_sha256", None)
    if not isinstance(digest, str) or digest != _digest(body):
        raise PaperAuditError("paper recovery report digest does not match content")
    audit = audit_paper_trail(Path(audit_path))
    expected_issue = ["paper audit trail is not finalized"]
    audit_matches = (
        audit["run_id"] == report.get("run_id")
        and audit["file_sha256"] == report.get("audit_file_sha256")
        and audit["tail_event_sha256"] == report.get("audit_tail_event_sha256")
        and audit["event_count"] == report.get("audit_event_count")
        and audit["issues"] == expected_issue
    )
    return {
        "valid": audit_matches,
        "report_path": str(report_path),
        "audit_path": str(audit_path),
        "recovery_status": report.get("recovery_status"),
        "audit_matches_report": audit_matches,
        "limitation": "A valid report still requires venue account reconciliation and does not permit automatic resume or trading.",
    }
