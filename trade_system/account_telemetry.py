"""Frozen private-account telemetry contract for the future paper/testnet path.

This module deliberately validates a contract only.  It contains no API key
handling, signing, account request, user-stream connection or order path.  The
contract prevents those later integrations from silently omitting the fields
needed for reconciliation and execution-cost calibration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .types import iso_utc, parse_utc, utc_now


FROZEN_ACCOUNT_TELEMETRY_CONTRACT = "FROZEN_ACCOUNT_TELEMETRY_CONTRACT"


class AccountTelemetryContractError(ValueError):
    pass


class AccountTelemetryArtifactError(ValueError):
    pass


def _canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_strings(value: Any, name: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise AccountTelemetryContractError("%s must be a non-empty list of strings" % name)
    return tuple(value)


def _require_subset(actual: Tuple[str, ...], expected: set[str], name: str) -> None:
    missing = expected - set(actual)
    if missing:
        raise AccountTelemetryContractError("%s is missing required fields: %s" % (name, ",".join(sorted(missing))))


@dataclass(frozen=True)
class AccountTelemetryContract:
    contract_id: str
    schema_version: str
    status: str
    frozen_at: str
    venue: str
    environment: str
    instrument_scope: Tuple[str, ...]
    sha256: str
    event_names: Tuple[str, ...]
    required_fields_by_event: Dict[str, Tuple[str, ...]]

    @classmethod
    def load(cls, path: Path) -> "AccountTelemetryContract":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AccountTelemetryContractError("cannot load account telemetry contract") from exc
        if not isinstance(raw, dict):
            raise AccountTelemetryContractError("account telemetry contract must be an object")
        scalar = ("contract_id", "schema_version", "status", "frozen_at")
        if any(not isinstance(raw.get(field), str) or not raw[field] for field in scalar):
            raise AccountTelemetryContractError("contract identity is incomplete")
        if raw["status"] != FROZEN_ACCOUNT_TELEMETRY_CONTRACT:
            raise AccountTelemetryContractError("account telemetry contract must be frozen")
        try:
            timestamp = raw["frozen_at"].replace("Z", "+00:00")
            if datetime.fromisoformat(timestamp).tzinfo is None:
                raise ValueError("timezone is required")
        except (AttributeError, ValueError) as exc:
            raise AccountTelemetryContractError("frozen_at must be an ISO-8601 timestamp with timezone") from exc
        scope = raw.get("scope")
        if not isinstance(scope, dict) or not isinstance(scope.get("venue"), str) or not scope["venue"]:
            raise AccountTelemetryContractError("scope.venue is required")
        if scope.get("environment") != "PAPER_OR_TESTNET_ONLY":
            raise AccountTelemetryContractError("contract scope must remain PAPER_OR_TESTNET_ONLY")
        instruments = tuple(item.upper() for item in _required_strings(scope.get("instrument_scope"), "scope.instrument_scope"))
        permissions = raw.get("permissions")
        if not isinstance(permissions, dict):
            raise AccountTelemetryContractError("permissions are required")
        expected_permissions = {
            "private_rest": "READ_ONLY_REQUIRED",
            "user_stream": "READ_ONLY_REQUIRED",
            "trading": "FORBIDDEN",
            "withdrawal": "FORBIDDEN",
        }
        if any(permissions.get(key) != value for key, value in expected_permissions.items()):
            raise AccountTelemetryContractError("permissions must require read-only telemetry and forbid trading/withdrawal")
        events_raw = raw.get("event_contracts")
        if not isinstance(events_raw, list) or not events_raw:
            raise AccountTelemetryContractError("event_contracts must be a non-empty list")
        required_event_fields = {
            "order_update": {"local_receive_time", "source_event_time", "submit_time", "ack_time", "reject_reason", "client_order_id", "exchange_order_id", "status", "side", "order_type", "original_quantity", "executed_quantity", "raw_payload_sha256"},
            "execution_fill": {"local_receive_time", "source_event_time", "fill_time", "client_order_id", "exchange_order_id", "fill_id", "fill_quantity", "fill_price", "fee_amount", "fee_asset", "raw_payload_sha256"},
            "account_update": {"local_receive_time", "source_event_time", "asset", "wallet_balance", "available_balance", "instrument", "position_quantity", "entry_price", "raw_payload_sha256"},
            "funding_update": {"local_receive_time", "source_event_time", "funding_time", "asset", "funding_amount", "raw_payload_sha256"},
            "rest_recovery_snapshot": {"local_receive_time", "source_as_of", "open_orders", "positions", "balances", "commission_schedule", "income_history_cursor", "raw_payload_sha256"},
        }
        event_names = []
        required_fields_by_event: Dict[str, Tuple[str, ...]] = {}
        for event in events_raw:
            if not isinstance(event, dict) or not isinstance(event.get("name"), str) or not isinstance(event.get("source_id"), str):
                raise AccountTelemetryContractError("each event contract requires name and source_id")
            name = event["name"]
            if name in event_names:
                raise AccountTelemetryContractError("event contract names must be unique")
            if name not in required_event_fields:
                raise AccountTelemetryContractError("unsupported event contract: %s" % name)
            fields = _required_strings(event.get("required_fields"), "event_contracts.%s.required_fields" % name)
            _require_subset(fields, required_event_fields[name], "event_contracts.%s.required_fields" % name)
            if not isinstance(event.get("ordering"), str) or not event["ordering"]:
                raise AccountTelemetryContractError("event_contracts.%s.ordering is required" % name)
            event_names.append(name)
            required_fields_by_event[name] = fields
        if set(event_names) != set(required_event_fields):
            raise AccountTelemetryContractError("contract must define every required account event type")
        reconciliation = raw.get("reconciliation")
        if not isinstance(reconciliation, dict) or reconciliation.get("required_before_new_risk") is not True or reconciliation.get("max_unexplained_position_differences") != 0:
            raise AccountTelemetryContractError("reconciliation must halt new risk on any unexplained position difference")
        _require_subset(_required_strings(reconciliation.get("required_snapshot_fields"), "reconciliation.required_snapshot_fields"), {"open_orders", "positions", "balances", "commission_schedule", "income_history_cursor"}, "reconciliation.required_snapshot_fields")
        calibration = raw.get("cost_calibration")
        if not isinstance(calibration, dict):
            raise AccountTelemetryContractError("cost_calibration is required")
        _require_subset(_required_strings(calibration.get("required_fields"), "cost_calibration.required_fields"), {"fee_amount", "fee_asset", "funding_amount", "fill_price", "fill_quantity", "submit_time", "ack_time", "fill_time", "reject_reason"}, "cost_calibration.required_fields")
        if calibration.get("may_calibrate_live_execution") is not False:
            raise AccountTelemetryContractError("contract must not claim live execution calibration")
        return cls(
            contract_id=raw["contract_id"],
            schema_version=raw["schema_version"],
            status=raw["status"],
            frozen_at=raw["frozen_at"],
            venue=scope["venue"],
            environment=scope["environment"],
            instrument_scope=instruments,
            sha256=_sha256(raw),
            event_names=tuple(event_names),
            required_fields_by_event=required_fields_by_event,
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "frozen_at": self.frozen_at,
            "venue": self.venue,
            "environment": self.environment,
            "instrument_scope": list(self.instrument_scope),
            "event_names": list(self.event_names),
            "sha256": self.sha256,
            "credential_or_order_capability": False,
        }


_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_KEYS = {"api_key", "apikey", "api_secret", "secret", "signature", "listen_key", "listenkey", "token", "private_key"}
_DECIMAL_FIELDS = {
    "original_quantity", "executed_quantity", "fill_quantity", "fill_price", "fee_amount",
    "wallet_balance", "available_balance", "position_quantity", "entry_price", "funding_amount",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AccountTelemetryArtifactError("cannot hash telemetry artifact") from exc
    return digest.hexdigest()


def _reject_secrets(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_KEYS:
                raise AccountTelemetryArtifactError("telemetry artifact must not contain credentials or signatures")
            _reject_secrets(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item)


def _require_timestamp(row: Dict[str, Any], field: str) -> None:
    try:
        parse_utc(str(row[field]))
    except (KeyError, ValueError) as exc:
        raise AccountTelemetryArtifactError("telemetry field %s must be an ISO-8601 timestamp with timezone" % field) from exc


def _require_decimal(row: Dict[str, Any], field: str) -> None:
    try:
        value = Decimal(str(row[field]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise AccountTelemetryArtifactError("telemetry field %s must be decimal" % field) from exc
    if not value.is_finite():
        raise AccountTelemetryArtifactError("telemetry field %s must be a finite decimal" % field)


def _require_nested_decimal(row: Dict[str, Any], field: str, context: str) -> None:
    if not isinstance(row, dict):
        raise AccountTelemetryArtifactError("telemetry %s must be an object" % context)
    try:
        value = Decimal(str(row[field]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise AccountTelemetryArtifactError("telemetry %s.%s must be decimal" % (context, field)) from exc
    if not value.is_finite():
        raise AccountTelemetryArtifactError("telemetry %s.%s must be a finite decimal" % (context, field))


def _validate_snapshot(row: Dict[str, Any]) -> None:
    for field in ("open_orders", "positions", "balances"):
        if not isinstance(row[field], list):
            raise AccountTelemetryArtifactError("telemetry snapshot field %s must be a list" % field)
    for index, position in enumerate(row["positions"]):
        context = "positions[%d]" % index
        if not isinstance(position, dict) or not isinstance(position.get("instrument"), str) or not position["instrument"]:
            raise AccountTelemetryArtifactError("telemetry %s requires instrument" % context)
        _require_nested_decimal(position, "position_quantity", context)
    for index, balance in enumerate(row["balances"]):
        context = "balances[%d]" % index
        if not isinstance(balance, dict) or not isinstance(balance.get("asset"), str) or not balance["asset"]:
            raise AccountTelemetryArtifactError("telemetry %s requires asset" % context)
        _require_nested_decimal(balance, "wallet_balance", context)
        _require_nested_decimal(balance, "available_balance", context)


def load_normalized_telemetry(path: Path, contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    """Load normalized, credential-free private telemetry captured elsewhere.

    This intentionally accepts no Binance wire payload and performs no network
    access. Each row must be explicitly bound to the frozen contract so files
    from another contract cannot silently enter paper reconciliation.
    """
    rows: List[Dict[str, Any]] = []
    fill_ids = set()
    try:
        handle = Path(path).open("r", encoding="utf-8")
    except OSError as exc:
        raise AccountTelemetryArtifactError("cannot read telemetry artifact") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise AccountTelemetryArtifactError("telemetry artifact contains a blank line")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AccountTelemetryArtifactError("invalid telemetry JSON at line %d" % line_number) from exc
            if not isinstance(row, dict) or row.get("record_type") != "normalized_account_telemetry":
                raise AccountTelemetryArtifactError("telemetry row %d has invalid record_type" % line_number)
            _reject_secrets(row)
            if row.get("contract_id") != contract.contract_id or row.get("contract_sha256") != contract.sha256:
                raise AccountTelemetryArtifactError("telemetry row %d is not bound to the supplied frozen contract" % line_number)
            event_name = row.get("event_name")
            if event_name not in contract.required_fields_by_event:
                raise AccountTelemetryArtifactError("telemetry row %d has unsupported event_name" % line_number)
            missing = set(contract.required_fields_by_event[event_name]) - set(row)
            if missing:
                raise AccountTelemetryArtifactError("telemetry row %d is missing fields: %s" % (line_number, ",".join(sorted(missing))))
            payload_hash = row.get("raw_payload_sha256")
            if not isinstance(payload_hash, str) or not _SHA256.fullmatch(payload_hash):
                raise AccountTelemetryArtifactError("telemetry row %d has invalid raw_payload_sha256" % line_number)
            _require_timestamp(row, "local_receive_time")
            _require_timestamp(row, "source_as_of" if event_name == "rest_recovery_snapshot" else "source_event_time")
            if event_name == "order_update":
                _require_timestamp(row, "submit_time")
                _require_timestamp(row, "ack_time")
            if event_name == "execution_fill":
                _require_timestamp(row, "fill_time")
            if event_name == "funding_update":
                _require_timestamp(row, "funding_time")
            for field in _DECIMAL_FIELDS.intersection(row):
                _require_decimal(row, field)
            if event_name == "account_update" and str(row["instrument"]).upper() not in contract.instrument_scope:
                raise AccountTelemetryArtifactError("telemetry row %d is outside the contract instrument scope" % line_number)
            if event_name == "rest_recovery_snapshot":
                _validate_snapshot(row)
            if event_name == "execution_fill":
                fill_key = (str(row["exchange_order_id"]), str(row["fill_id"]))
                if fill_key in fill_ids:
                    raise AccountTelemetryArtifactError("duplicate immutable exchange fill identity")
                fill_ids.add(fill_key)
            rows.append(row)
    return rows


def audit_normalized_telemetry(path: Path, contract: AccountTelemetryContract) -> Dict[str, Any]:
    rows = load_normalized_telemetry(path, contract)
    by_event = {name: 0 for name in contract.event_names}
    for row in rows:
        by_event[row["event_name"]] += 1
    return {
        "record_type": "normalized_account_telemetry_audit",
        "contract_id": contract.contract_id,
        "contract_sha256": contract.sha256,
        "telemetry_path": str(path),
        "telemetry_sha256": _sha256_file(Path(path)),
        "event_counts": by_event,
        "missing_event_types": sorted(name for name, count in by_event.items() if count == 0),
        "limitation": "Validates a normalized local artifact only. It does not establish a network session, account authority, source completeness, exchange truth or trading permission.",
    }


def reconcile_recovery_report_with_telemetry(
    recovery_report: Dict[str, Any],
    telemetry_path: Path,
    contract: AccountTelemetryContract,
) -> Dict[str, Any]:
    """Compare a fail-closed local recovery handoff with a later REST snapshot.

    The caller must first verify the recovery report against its exact paper
    audit trail. This function does not clear a halt or make a session ready.
    """
    if recovery_report.get("record_type") != "paper_audit_recovery_report" or recovery_report.get("recovery_status") != "HALT_AND_RECONCILE_REQUIRED":
        raise AccountTelemetryArtifactError("invalid fail-closed recovery report")
    telemetry_audit = audit_normalized_telemetry(Path(telemetry_path), contract)
    rows = load_normalized_telemetry(Path(telemetry_path), contract)
    snapshots = [row for row in rows if row["event_name"] == "rest_recovery_snapshot"]
    if not snapshots:
        return {
            "reconciliation_status": "SNAPSHOT_MISSING",
            "expected_open_client_order_ids": sorted(str(item) for item in recovery_report.get("expected_open_client_order_ids", [])),
            "observed_open_client_order_ids": [],
            "position_difference": None,
            "issues": ["no rest_recovery_snapshot in normalized telemetry artifact"],
            "telemetry_audit": telemetry_audit,
        }
    snapshot = max(snapshots, key=lambda row: (parse_utc(str(row["source_as_of"])), parse_utc(str(row["local_receive_time"]))))
    expected_open = {str(item) for item in recovery_report.get("expected_open_client_order_ids", [])}
    observed_open = set()
    issues = []
    for order in snapshot["open_orders"]:
        if not isinstance(order, dict) or not isinstance(order.get("client_order_id"), str) or not order["client_order_id"]:
            issues.append("snapshot contains open order without client_order_id")
            continue
        observed_open.add(order["client_order_id"])
    local_state = recovery_report.get("last_local_state")
    expected_position: Optional[Decimal] = None
    if isinstance(local_state, dict) and "position_quantity" in local_state:
        try:
            expected_position = Decimal(str(local_state["position_quantity"]))
            if not expected_position.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            issues.append("recovery report local position_quantity is invalid")
    else:
        issues.append("recovery report has no local position expectation")
    positions = [
        row for row in snapshot["positions"]
        if isinstance(row, dict) and str(row.get("instrument", "")).upper() in contract.instrument_scope
    ]
    foreign_nonzero_positions = [
        {"instrument": str(row["instrument"]), "position_quantity": str(row["position_quantity"])}
        for row in snapshot["positions"]
        if str(row["instrument"]).upper() not in contract.instrument_scope
        and Decimal(str(row["position_quantity"])) != Decimal("0")
    ]
    if foreign_nonzero_positions:
        issues.append("foreign nonzero positions observed")
    observed_position: Optional[Decimal] = None
    if len(positions) != 1:
        issues.append("snapshot must contain exactly one scoped instrument position")
    else:
        try:
            observed_position = Decimal(str(positions[0]["position_quantity"]))
        except (KeyError, InvalidOperation, ValueError):
            issues.append("snapshot scoped position_quantity is invalid")
    foreign_open = sorted(observed_open - expected_open)
    missing_open = sorted(expected_open - observed_open)
    if foreign_open:
        issues.append("foreign open client orders observed")
    if missing_open:
        issues.append("expected open client orders are missing")
    position_difference: Optional[str] = None
    if expected_position is not None and observed_position is not None:
        position_difference = str(observed_position - expected_position)
        if observed_position != expected_position:
            issues.append("position quantity mismatch")
    return {
        "reconciliation_status": "MATCHED_MANUAL_CLEAR_REQUIRED" if not issues else "MISMATCH",
        "snapshot_source_as_of": snapshot["source_as_of"],
        "snapshot_local_receive_time": snapshot["local_receive_time"],
        "expected_open_client_order_ids": sorted(expected_open),
        "observed_open_client_order_ids": sorted(observed_open),
        "foreign_open_client_order_ids": foreign_open,
        "missing_open_client_order_ids": missing_open,
        "expected_position_quantity": str(expected_position) if expected_position is not None else None,
        "observed_position_quantity": str(observed_position) if observed_position is not None else None,
        "foreign_nonzero_positions": foreign_nonzero_positions,
        "position_difference": position_difference,
        "issues": issues,
        "telemetry_audit": telemetry_audit,
    }


def write_recovery_telemetry_reconciliation_report(
    output_path: Path,
    *,
    recovery_report_path: Path,
    recovery_report: Dict[str, Any],
    telemetry_path: Path,
    contract: AccountTelemetryContract,
) -> Dict[str, Any]:
    reconciliation = reconcile_recovery_report_with_telemetry(recovery_report, Path(telemetry_path), contract)
    report = {
        "record_type": "paper_recovery_telemetry_reconciliation_report",
        "schema_version": "paper-recovery-telemetry-reconciliation.v1",
        "written_at": iso_utc(utc_now()),
        "contract_id": contract.contract_id,
        "contract_sha256": contract.sha256,
        "recovery_report_path": str(recovery_report_path),
        "recovery_report_sha256": _sha256_file(Path(recovery_report_path)),
        "recovery_status": recovery_report.get("recovery_status"),
        "reconciliation": reconciliation,
        "next_step": "Keep HALT_AND_RECONCILE active. A matched local artifact comparison still requires policy recovery conditions and explicit manual clearance; this report cannot resume an OMS or submit orders.",
    }
    report["report_sha256"] = _sha256(report)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise AccountTelemetryArtifactError("recovery telemetry reconciliation report already exists")
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical_json(report) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise AccountTelemetryArtifactError("cannot write recovery telemetry reconciliation report") from exc
    return report
