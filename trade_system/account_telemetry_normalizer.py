"""Offline normalization for credential-free Binance USD-M private telemetry.

The input is a locally captured, sanitized JSONL export; this module never
opens a network connection, signs a request, or accepts credentials.  It
recognizes only the pinned v1 source envelope and rejects unknown events so a
provider schema change cannot silently enter paper reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List

from .account_telemetry import (
    AccountTelemetryArtifactError,
    AccountTelemetryContract,
    _canonical_json,
    _reject_secrets,
    audit_normalized_telemetry,
)
from .types import iso_utc, parse_utc


SOURCE_SCHEMA_VERSION = "binance-usdm-private.v1"
USER_STREAM = "BINANCE_USDM_USER_STREAM"
INCOME_REST = "BINANCE_USDM_PRIVATE_REST_INCOME"
RECOVERY_REST = "BINANCE_USDM_PRIVATE_REST_RECOVERY"


def _hash(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AccountTelemetryArtifactError("%s must be an object" % name)
    return value


def _require(value: Dict[str, Any], key: str, context: str) -> Any:
    if key not in value:
        raise AccountTelemetryArtifactError("%s is missing %s" % (context, key))
    return value[key]


def _timestamp(value: Any, context: str) -> str:
    if isinstance(value, bool):
        raise AccountTelemetryArtifactError("%s must be an ISO timestamp or epoch milliseconds" % context)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            numeric = Decimal(str(value))
            if not numeric.is_finite() or numeric != numeric.to_integral_value() or numeric < 0:
                raise ValueError
            return iso_utc(datetime.fromtimestamp(float(numeric / Decimal("1000")), tz=timezone.utc))
        except (InvalidOperation, OSError, OverflowError, ValueError) as exc:
            raise AccountTelemetryArtifactError("%s must be epoch milliseconds" % context) from exc
    try:
        return iso_utc(parse_utc(str(value)))
    except ValueError as exc:
        raise AccountTelemetryArtifactError("%s must be an ISO timestamp with timezone" % context) from exc


def _finite(value: Any, context: str) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AccountTelemetryArtifactError("%s must be decimal" % context) from exc
    if not parsed.is_finite():
        raise AccountTelemetryArtifactError("%s must be a finite decimal" % context)
    return str(parsed)


def _text(value: Any, context: str) -> str:
    if not isinstance(value, (str, int)) or not str(value):
        raise AccountTelemetryArtifactError("%s must be a non-empty string" % context)
    return str(value)


def _record_base(
    record: Dict[str, Any], payload: Dict[str, Any], event_name: str, contract: AccountTelemetryContract
) -> Dict[str, Any]:
    return {
        "record_type": "normalized_account_telemetry",
        "normalizer_schema_version": SOURCE_SCHEMA_VERSION,
        "contract_id": contract.contract_id,
        "contract_sha256": contract.sha256,
        "event_name": event_name,
        "local_receive_time": _timestamp(_require(record, "local_receive_time", "source envelope"), "local_receive_time"),
        "raw_payload_sha256": _hash(payload),
        "source_record_sha256": _hash(record),
    }


def _scoped_instrument(value: Any, contract: AccountTelemetryContract, context: str) -> str:
    instrument = _text(value, context).upper()
    if instrument not in contract.instrument_scope:
        raise AccountTelemetryArtifactError("%s is outside frozen instrument scope" % context)
    return instrument


def _normalize_order_update(record: Dict[str, Any], payload: Dict[str, Any], contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    order = _require_mapping(_require(payload, "o", "ORDER_TRADE_UPDATE"), "ORDER_TRADE_UPDATE.o")
    source_time = _timestamp(_require(payload, "E", "ORDER_TRADE_UPDATE"), "ORDER_TRADE_UPDATE.E")
    transaction_time = _timestamp(_require(payload, "T", "ORDER_TRADE_UPDATE"), "ORDER_TRADE_UPDATE.T")
    _scoped_instrument(_require(order, "s", "ORDER_TRADE_UPDATE.o"), contract, "ORDER_TRADE_UPDATE.o.s")
    normalized = _record_base(record, payload, "order_update", contract)
    normalized.update({
        "source_event_time": source_time,
        "submit_time": _timestamp(_require(order, "T", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.T"),
        "ack_time": transaction_time,
        "reject_reason": order.get("r"),
        "client_order_id": _text(_require(order, "c", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.c"),
        "exchange_order_id": _text(_require(order, "i", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.i"),
        "status": _text(_require(order, "X", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.X"),
        "side": _text(_require(order, "S", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.S"),
        "order_type": _text(_require(order, "o", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.o"),
        "original_quantity": _finite(_require(order, "q", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.q"),
        "executed_quantity": _finite(_require(order, "z", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.z"),
    })
    rows = [normalized]
    if _text(_require(order, "x", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.x") == "TRADE":
        last_quantity = _finite(_require(order, "l", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.l")
        if Decimal(last_quantity) <= 0:
            raise AccountTelemetryArtifactError("ORDER_TRADE_UPDATE TRADE must have positive last fill quantity")
        fill = _record_base(record, payload, "execution_fill", contract)
        fill.update({
            "source_event_time": source_time,
            "fill_time": _timestamp(_require(order, "T", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.T"),
            "client_order_id": normalized["client_order_id"],
            "exchange_order_id": normalized["exchange_order_id"],
            "fill_id": _text(_require(order, "t", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.t"),
            "fill_quantity": last_quantity,
            "fill_price": _finite(_require(order, "L", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.L"),
            "fee_amount": _finite(_require(order, "n", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.n"),
            "fee_asset": _text(_require(order, "N", "ORDER_TRADE_UPDATE.o"), "ORDER_TRADE_UPDATE.o.N"),
        })
        rows.append(fill)
    return rows


def _normalize_account_update(record: Dict[str, Any], payload: Dict[str, Any], contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    account = _require_mapping(_require(payload, "a", "ACCOUNT_UPDATE"), "ACCOUNT_UPDATE.a")
    balances = _require(account, "B", "ACCOUNT_UPDATE.a")
    positions = _require(account, "P", "ACCOUNT_UPDATE.a")
    if not isinstance(balances, list) or len(balances) != 1:
        raise AccountTelemetryArtifactError("ACCOUNT_UPDATE.a.B must contain exactly one sanitized balance")
    scoped = [item for item in positions if isinstance(item, dict) and str(item.get("s", "")).upper() in contract.instrument_scope]
    if not isinstance(positions, list) or len(scoped) != 1:
        raise AccountTelemetryArtifactError("ACCOUNT_UPDATE.a.P must contain exactly one scoped position")
    balance = _require_mapping(balances[0], "ACCOUNT_UPDATE.a.B[0]")
    position = scoped[0]
    normalized = _record_base(record, payload, "account_update", contract)
    normalized.update({
        "source_event_time": _timestamp(_require(payload, "E", "ACCOUNT_UPDATE"), "ACCOUNT_UPDATE.E"),
        "asset": _text(_require(balance, "a", "ACCOUNT_UPDATE.a.B[0]"), "ACCOUNT_UPDATE.a.B[0].a"),
        "wallet_balance": _finite(_require(balance, "wb", "ACCOUNT_UPDATE.a.B[0]"), "ACCOUNT_UPDATE.a.B[0].wb"),
        "available_balance": _finite(_require(balance, "cw", "ACCOUNT_UPDATE.a.B[0]"), "ACCOUNT_UPDATE.a.B[0].cw"),
        "instrument": _scoped_instrument(_require(position, "s", "ACCOUNT_UPDATE.a.P[0]"), contract, "ACCOUNT_UPDATE.a.P[0].s"),
        "position_quantity": _finite(_require(position, "pa", "ACCOUNT_UPDATE.a.P[0]"), "ACCOUNT_UPDATE.a.P[0].pa"),
        "entry_price": _finite(_require(position, "ep", "ACCOUNT_UPDATE.a.P[0]"), "ACCOUNT_UPDATE.a.P[0].ep"),
    })
    return [normalized]


def _normalize_funding(record: Dict[str, Any], payload: Dict[str, Any], contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    if _text(_require(payload, "incomeType", "income record"), "income record.incomeType") != "FUNDING_FEE":
        raise AccountTelemetryArtifactError("income record must be FUNDING_FEE")
    _scoped_instrument(_require(payload, "symbol", "income record"), contract, "income record.symbol")
    funding_time = _timestamp(_require(payload, "time", "income record"), "income record.time")
    normalized = _record_base(record, payload, "funding_update", contract)
    normalized.update({
        "source_event_time": funding_time,
        "funding_time": funding_time,
        "asset": _text(_require(payload, "asset", "income record"), "income record.asset"),
        "funding_amount": _finite(_require(payload, "income", "income record"), "income record.income"),
    })
    return [normalized]


def _normalize_recovery(record: Dict[str, Any], payload: Dict[str, Any], contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    open_orders = _require(payload, "open_orders", "recovery snapshot")
    positions = _require(payload, "positions", "recovery snapshot")
    balances = _require(payload, "balances", "recovery snapshot")
    if not all(isinstance(value, list) for value in (open_orders, positions, balances)):
        raise AccountTelemetryArtifactError("recovery snapshot open_orders, positions and balances must be lists")
    normalized_orders = []
    for index, order in enumerate(open_orders):
        order = _require_mapping(order, "recovery snapshot open_orders[%d]" % index)
        normalized_orders.append({
            "client_order_id": _text(_require(order, "clientOrderId", "recovery order"), "recovery order.clientOrderId"),
            "exchange_order_id": _text(_require(order, "orderId", "recovery order"), "recovery order.orderId"),
        })
    normalized_positions = []
    for index, position in enumerate(positions):
        position = _require_mapping(position, "recovery snapshot positions[%d]" % index)
        normalized_positions.append({
            "instrument": _text(_require(position, "symbol", "recovery position"), "recovery position.symbol").upper(),
            "position_quantity": _finite(_require(position, "positionAmt", "recovery position"), "recovery position.positionAmt"),
        })
    normalized_balances = []
    for index, balance in enumerate(balances):
        balance = _require_mapping(balance, "recovery snapshot balances[%d]" % index)
        normalized_balances.append({
            "asset": _text(_require(balance, "asset", "recovery balance"), "recovery balance.asset"),
            "wallet_balance": _finite(_require(balance, "balance", "recovery balance"), "recovery balance.balance"),
            "available_balance": _finite(_require(balance, "availableBalance", "recovery balance"), "recovery balance.availableBalance"),
        })
    normalized = _record_base(record, payload, "rest_recovery_snapshot", contract)
    normalized.update({
        "source_as_of": _timestamp(_require(payload, "source_as_of", "recovery snapshot"), "recovery snapshot.source_as_of"),
        "open_orders": normalized_orders,
        "positions": normalized_positions,
        "balances": normalized_balances,
        "commission_schedule": _require_mapping(_require(payload, "commission_schedule", "recovery snapshot"), "recovery snapshot.commission_schedule"),
        "income_history_cursor": payload.get("income_history_cursor"),
    })
    return [normalized]


def normalize_record(record: Dict[str, Any], contract: AccountTelemetryContract) -> List[Dict[str, Any]]:
    _reject_secrets(record)
    if record.get("record_type") != "sanitized_private_source_event":
        raise AccountTelemetryArtifactError("source row must have record_type sanitized_private_source_event")
    if record.get("source_schema_version") != SOURCE_SCHEMA_VERSION:
        raise AccountTelemetryArtifactError("source row has unsupported source_schema_version")
    payload = _require_mapping(_require(record, "payload", "source row"), "source row.payload")
    source_kind = record.get("source_kind")
    if source_kind == USER_STREAM:
        event = payload.get("e")
        if event == "ORDER_TRADE_UPDATE":
            return _normalize_order_update(record, payload, contract)
        if event == "ACCOUNT_UPDATE":
            return _normalize_account_update(record, payload, contract)
        raise AccountTelemetryArtifactError("unsupported user-stream event: %s" % event)
    if source_kind == INCOME_REST:
        return _normalize_funding(record, payload, contract)
    if source_kind == RECOVERY_REST:
        return _normalize_recovery(record, payload, contract)
    raise AccountTelemetryArtifactError("unsupported source_kind")


def normalize_sanitized_telemetry(input_path: Path, output_path: Path, contract: AccountTelemetryContract) -> Dict[str, Any]:
    """Create a new credential-free normalized artifact from a local JSONL input."""
    output = Path(output_path)
    if output.exists():
        raise AccountTelemetryArtifactError("normalized telemetry output already exists")
    rows: List[Dict[str, Any]] = []
    try:
        handle = Path(input_path).open("r", encoding="utf-8")
    except OSError as exc:
        raise AccountTelemetryArtifactError("cannot read sanitized telemetry input") from exc
    source_row_count = 0
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise AccountTelemetryArtifactError("sanitized telemetry input contains a blank line")
            try:
                source_record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AccountTelemetryArtifactError("invalid source JSON at line %d" % line_number) from exc
            try:
                rows.extend(normalize_record(_require_mapping(source_record, "source row"), contract))
            except AccountTelemetryArtifactError as exc:
                raise AccountTelemetryArtifactError("source line %d: %s" % (line_number, exc)) from exc
            source_row_count += 1
    if not rows:
        raise AccountTelemetryArtifactError("sanitized telemetry input contains no normalizable rows")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            for row in rows:
                handle.write(_canonical_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise AccountTelemetryArtifactError("cannot write normalized telemetry output") from exc
    try:
        audit = audit_normalized_telemetry(output, contract)
    except AccountTelemetryArtifactError:
        # Preserve the immutable failed artifact for forensic inspection; it
        # cannot be reused because the write-once path already exists.
        raise
    return {
        "record_type": "normalized_account_telemetry_conversion",
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "input_path": str(input_path),
        "output_path": str(output),
        "source_row_count": source_row_count,
        "normalized_row_count": len(rows),
        "audit": audit,
        "limitation": "Offline conversion of a sanitized local file only; no credentials, network session, signing, order submission, recovery clearance or OMS resume capability exists.",
    }
