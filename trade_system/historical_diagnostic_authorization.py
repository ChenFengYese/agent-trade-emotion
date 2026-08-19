"""Fail-closed receipts for the bounded 2025-02 historical diagnostic.

This module intentionally has no downloader, parser, model import, or CLI
entrypoint.  It makes an eventual external-data diagnostic auditable without
turning an authorization document into either a research result or trading
permission.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import fcntl
import csv
import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .binance_cm_historical_mechanism import _HEADERS as HISTORICAL_MECHANISM_HEADERS
from .historical_diagnostic_terminal_guard import (
    FebruaryTerminalSeenError,
    reject_if_bound_february_terminal_identity,
    reject_if_terminal_receipt_id,
)


ABSENCE_RECORD = "pre_download_absence_inventory.v1"
AUTHORIZATION_RECORD = "pre_download_authorization_receipt.v1"
CONTRACT_RECORD = "authorized_execution_contract.v2"
ACQUISITION_RECORD = "historical_diagnostic_acquisition_receipt.v1"
REGISTRY_RECORD = "historical_diagnostic_consumption_registry.v1"
EXPECTED_KINDS = ("aggTrades", "bookDepth", "metrics")
EXPECTED_DATES = tuple("2025-02-%02d" % day for day in range(1, 29))
SOL_DECISION_ID = "SOL-S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1"
FROZEN_PLAN_SHA256 = "75ee48cb7abb9374ebae65929ac5eec6148f21bdfc2a13eea19607a931c9d6fb"
FROZEN_PLAN_CANONICAL_SHA256 = "85a95d0845ca0c78b9bc3be12d8dcafd051625fab5be318398ace2f92531087b"
V4_ROWS = {"path": ".runtime/historical-experiments/binance-cm-2025-01-v4-final.rows.ndjson", "sha256": "72664e1bce597073cceeb9e30998bcdea25bee043ea74f0de9c340d6fc1346cd"}
V4_MODEL = {"path": ".runtime/historical-experiments/binance-cm-2025-01-v4-final.model.json", "sha256": "be4ce118827ae680242348c4ef821f06b865121a07dc40adebf66fff29e967e1"}
V4_MANIFEST = {"path": ".runtime/historical-experiments/binance-cm-2025-01-v4-final.manifest.json", "sha256": "6c43d5164c98d83403e6cb3f52e8bcfb8ee000279ac2d4baa514ca25fa67d2ba"}
V4_DEVELOPMENT_SOURCE_SHA256 = "d149cbc38f96fcef2d68176ec26cd1f28bbfd97031eb86d2ea72547716dbc664"


class HistoricalDiagnosticAuthorizationError(ValueError):
    pass


def _reject_terminal_february_identity(*, plan_path: Path, receipt_path: Path, workspace_root: Path) -> None:
    """Fail before any market input probe when the bound R1 identity is terminal."""
    try:
        reject_if_bound_february_terminal_identity(
            plan_path=plan_path,
            receipt_path=receipt_path,
            workspace_root=workspace_root,
        )
    except FebruaryTerminalSeenError as exc:
        raise HistoricalDiagnosticAuthorizationError(str(exc)) from exc


def _reject_terminal_february_registry_mutation(*, receipt_id: str, registry_path: Path) -> None:
    try:
        reject_if_terminal_receipt_id(receipt_id=receipt_id, registry_path=registry_path)
    except FebruaryTerminalSeenError as exc:
        raise HistoricalDiagnosticAuthorizationError(str(exc)) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _load(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoricalDiagnosticAuthorizationError("cannot load %s" % label) from exc
    if not isinstance(value, dict):
        raise HistoricalDiagnosticAuthorizationError("%s must be an object" % label)
    return value


def _relative(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HistoricalDiagnosticAuthorizationError("%s is required" % field)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HistoricalDiagnosticAuthorizationError("%s must be a workspace-relative path" % field)
    return root / path


def _sha_binding(root: Path, binding: Any, field: str) -> Dict[str, Any]:
    if not isinstance(binding, dict):
        raise HistoricalDiagnosticAuthorizationError("%s binding is required" % field)
    path = _relative(root, binding.get("path"), field + ".path")
    digest = binding.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or sha256_file(path) != digest:
        raise HistoricalDiagnosticAuthorizationError("%s digest drifted" % field)
    return binding


def _plan_targets(plan: Mapping[str, Any], *, download_root: str) -> list[Dict[str, str]]:
    if plan.get("diagnostic_id") != "XH-CM-btcusd-perp-2025-02-v2" or plan.get("status") != "FROZEN_BEFORE_DOWNLOAD":
        raise HistoricalDiagnosticAuthorizationError("only the frozen 2025-02 diagnostic may be authorized")
    if tuple(plan.get("dates", ())) != EXPECTED_DATES:
        raise HistoricalDiagnosticAuthorizationError("diagnostic dates are not the exact unopened 2025-02 set")
    input_contract = plan.get("input_contract")
    if not isinstance(input_contract, dict) or tuple(input_contract.get("required_daily_kinds", ())) != EXPECTED_KINDS:
        raise HistoricalDiagnosticAuthorizationError("diagnostic required kinds differ from the frozen contract")
    template = input_contract.get("source_url_template")
    if not isinstance(template, str) or "data.binance.vision" not in template:
        raise HistoricalDiagnosticAuthorizationError("official source URL template is required")
    if not isinstance(download_root, str) or not download_root or Path(download_root).is_absolute() or ".." in Path(download_root).parts:
        raise HistoricalDiagnosticAuthorizationError("download_root must be a safe workspace-relative path")
    targets = []
    for kind in EXPECTED_KINDS:
        for day in EXPECTED_DATES:
            name = "BTCUSD_PERP-%s-%s.zip" % (kind, day)
            archive_path = "%s/%s/%s" % (download_root.rstrip("/"), kind, name)
            targets.append({"kind": kind, "date": day, "archive_url": template.format(kind=kind, date=day), "checksum_url": template.format(kind=kind, date=day) + ".CHECKSUM", "archive_path": archive_path, "checksum_path": archive_path + ".CHECKSUM"})
    return targets


def build_pre_download_absence_inventory(plan_path: Path, *, workspace_root: Path, download_root: str) -> Dict[str, Any]:
    """Read only: return the exact 84 archive/84 checksum targets or reject."""
    root = Path(workspace_root).resolve()
    plan = _load(plan_path, "frozen diagnostic plan")
    targets = _plan_targets(plan, download_root=download_root)
    present = []
    for target in targets:
        for field in ("archive_path", "checksum_path"):
            path = _relative(root, target[field], "target." + field)
            if path.exists():
                present.append({"kind": target["kind"], "date": target["date"], "field": field, "path": target[field]})
    if present:
        raise HistoricalDiagnosticAuthorizationError("pre-download absence inventory refused: one or more exact February targets already exist")
    inventory = {"record_type": ABSENCE_RECORD, "diagnostic_id": plan["diagnostic_id"], "plan_sha256": sha256_file(plan_path), "download_root": download_root, "target_count": len(targets), "expected_archive_count": 84, "expected_checksum_count": 84, "targets": targets, "present": [], "status": "ALL_TARGETS_ABSENT"}
    inventory["inventory_sha256"] = canonical_sha256({key: value for key, value in inventory.items() if key != "inventory_sha256"})
    return inventory


def verify_pre_download_absence_inventory(inventory: Mapping[str, Any], *, plan_path: Path, workspace_root: Path, require_current_absence: bool = True) -> Dict[str, Any]:
    if not isinstance(inventory, Mapping) or inventory.get("record_type") != ABSENCE_RECORD:
        raise HistoricalDiagnosticAuthorizationError("absence inventory record type is invalid")
    # A later acquisition necessarily makes the targets present.  The receipt
    # verifier must therefore recheck the frozen target set without pretending
    # that the post-acquisition filesystem is still an authorization-time
    # observation.  Callers performing the actual pre-download gate keep the
    # default, which reads the filesystem and refuses any present target.
    plan = _load(plan_path, "frozen diagnostic plan")
    targets = _plan_targets(plan, download_root=inventory.get("download_root"))
    expected = {"record_type": ABSENCE_RECORD, "diagnostic_id": plan["diagnostic_id"], "plan_sha256": sha256_file(plan_path), "download_root": inventory.get("download_root"), "target_count": len(targets), "expected_archive_count": 84, "expected_checksum_count": 84, "targets": targets, "present": [], "status": "ALL_TARGETS_ABSENT"}
    expected["inventory_sha256"] = canonical_sha256({key: value for key, value in expected.items() if key != "inventory_sha256"})
    if require_current_absence:
        build_pre_download_absence_inventory(plan_path, workspace_root=workspace_root, download_root=inventory.get("download_root"))
    supplied_digest = inventory.get("inventory_sha256")
    if supplied_digest != canonical_sha256({key: value for key, value in inventory.items() if key != "inventory_sha256"}):
        raise HistoricalDiagnosticAuthorizationError("absence inventory summary digest drifted")
    if dict(inventory) != expected:
        raise HistoricalDiagnosticAuthorizationError("absence inventory differs from exact frozen targets")
    return {"record_type": "pre_download_absence_inventory_verification.v1", "verified": True, "target_count": 84, "input_count": 168, "status": "ALL_TARGETS_ABSENT"}


def _receipt_scope(receipt: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in receipt.items() if key not in {"authorized_execution_contract", "receipt_scope_sha256"}})


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalDiagnosticAuthorizationError("%s is required" % field)
    return value


def _verify_denials(record: Mapping[str, Any]) -> None:
    if record.get("eligible_for_binance_g2") is not False or record.get("trading_authorization") != "DENIED":
        raise HistoricalDiagnosticAuthorizationError("historical diagnostic receipts cannot grant G2 or trading eligibility")


def _verify_policy_bundle(receipt: Mapping[str, Any], *, workspace_root: Path) -> Dict[str, Any]:
    bundle = receipt.get("model_and_policy")
    if not isinstance(bundle, dict):
        raise HistoricalDiagnosticAuthorizationError("candidate/control/model policy bundle is required")
    required = ("candidate_model", "control_model", "calibration", "payoff_policy", "selection_policy", "evaluation_policy", "runner", "evaluator", "package", "test_report")
    if any(not isinstance(bundle.get(key), dict) for key in required):
        raise HistoricalDiagnosticAuthorizationError("candidate/control/model policy bundle is incomplete")
    for key in required:
        item = bundle[key]
        _require_text(item.get("id"), "model_and_policy.%s.id" % key)
        if key in {"runner", "evaluator", "package", "test_report"}:
            _sha_binding(workspace_root, item, "model_and_policy.%s" % key)
    return bundle


def verify_authorized_execution_contract(contract_path: Path, receipt_path: Path, *, plan_path: Path, workspace_root: Path) -> Dict[str, Any]:
    root = Path(workspace_root).resolve()
    contract = _load(contract_path, "authorized execution contract")
    receipt = _load(receipt_path, "pre-download authorization receipt")
    if contract.get("record_type") != CONTRACT_RECORD or contract.get("status") != "AUTHORIZED_RECEIPT_BOUND":
        raise HistoricalDiagnosticAuthorizationError("execution contract is not AUTHORIZED_RECEIPT_BOUND")
    _verify_denials(contract)
    plan = _sha_binding(root, contract.get("frozen_design"), "contract.frozen_design")
    if plan.get("path") != str(Path(plan_path).resolve().relative_to(root)) or plan.get("sha256") != sha256_file(plan_path):
        raise HistoricalDiagnosticAuthorizationError("execution contract does not bind the supplied frozen design")
    binding = contract.get("authorization_receipt")
    expected_receipt_path = str(Path(receipt_path).resolve().relative_to(root))
    if not isinstance(binding, dict) or binding.get("receipt_id") != receipt.get("receipt_id") or binding.get("receipt_scope_sha256") != _receipt_scope(receipt) or binding.get("path") != expected_receipt_path:
        raise HistoricalDiagnosticAuthorizationError("execution contract receipt binding drifted")
    _relative(root, binding.get("path"), "contract.authorization_receipt.path")
    if receipt.get("authorized_execution_contract", {}).get("contract_id") != contract.get("contract_id"):
        raise HistoricalDiagnosticAuthorizationError("receipt does not refer back to execution contract")
    return {"record_type": "authorized_execution_contract_verification.v2", "verified": True, "contract_id": contract.get("contract_id"), "receipt_id": receipt.get("receipt_id"), "status": "AUTHORIZED_RECEIPT_BOUND"}


def verify_pre_download_authorization_receipt(receipt_path: Path, *, plan_path: Path, workspace_root: Path) -> Dict[str, Any]:
    _reject_terminal_february_identity(plan_path=plan_path, receipt_path=receipt_path, workspace_root=workspace_root)
    root = Path(workspace_root).resolve()
    receipt = _load(receipt_path, "pre-download authorization receipt")
    if receipt.get("record_type") != AUTHORIZATION_RECORD or receipt.get("status") != "AUTHORIZED":
        raise HistoricalDiagnosticAuthorizationError("authorization receipt is not authorized")
    _verify_denials(receipt)
    _require_text(receipt.get("receipt_id"), "receipt_id")
    if receipt.get("sol_decision_id") != SOL_DECISION_ID:
        raise HistoricalDiagnosticAuthorizationError("authorization receipt Sol decision ID is not the exact conditional authorization")
    frozen = _sha_binding(root, receipt.get("frozen_design"), "frozen_design")
    expected_plan = Path(plan_path).resolve()
    if frozen.get("path") != str(expected_plan.relative_to(root)) or frozen.get("sha256") != sha256_file(expected_plan):
        raise HistoricalDiagnosticAuthorizationError("receipt frozen design binding drifted")
    if frozen.get("sha256") != FROZEN_PLAN_SHA256 or receipt.get("frozen_design_canonical_sha256") != FROZEN_PLAN_CANONICAL_SHA256 or canonical_sha256(_load(expected_plan, "frozen diagnostic plan")) != FROZEN_PLAN_CANONICAL_SHA256:
        raise HistoricalDiagnosticAuthorizationError("receipt frozen design is not the exact Sol-authorized plan")
    inventory = receipt.get("absence_inventory")
    verify_pre_download_absence_inventory(inventory, plan_path=expected_plan, workspace_root=root, require_current_absence=False)
    if inventory.get("plan_sha256") != frozen.get("sha256"):
        raise HistoricalDiagnosticAuthorizationError("receipt absence inventory is not bound to frozen design")
    ledger = _sha_binding(root, receipt.get("v1_ledger"), "v1_ledger")
    verification = _sha_binding(root, receipt.get("v1_ledger_verification_report"), "v1_ledger_verification_report")
    january = receipt.get("january_v2_development_evidence")
    if not isinstance(january, dict) or not isinstance(january.get("row_count"), int) or january["row_count"] <= 0:
        raise HistoricalDiagnosticAuthorizationError("receipt must bind a nonzero actual January v2 development row count")
    _require_text(january.get("manifest_id"), "january_v2_development_evidence.manifest_id")
    manifest_binding = _sha_binding(root, january.get("manifest"), "january_v2_development_evidence.manifest")
    rows_binding = _sha_binding(root, january.get("rows_artifact"), "january_v2_development_evidence.rows_artifact")
    model_binding = _sha_binding(root, january.get("model"), "january_v2_development_evidence.model")
    manifest = _load(_relative(root, manifest_binding["path"], "january_v2_development_evidence.manifest.path"), "January v2 development manifest")
    if manifest_binding != V4_MANIFEST or rows_binding != V4_ROWS or model_binding != V4_MODEL or january.get("manifest_id") != "XH-CM-btcusd-perp-2025-01-seen-development-v2-post-pressure-response-v2":
        raise HistoricalDiagnosticAuthorizationError("receipt does not bind the exact v4 January development artifacts")
    if manifest.get("manifest_id") != january["manifest_id"] or manifest.get("semantic_version") != "post_pressure_response_v2":
        raise HistoricalDiagnosticAuthorizationError("January v2 manifest semantic identity drifted")
    if manifest.get("row_count") != january["row_count"] or manifest.get("rows_artifact") != rows_binding or manifest.get("model") != model_binding:
        raise HistoricalDiagnosticAuthorizationError("receipt and January v2 manifest row evidence do not cross-validate")
    source = manifest.get("software_bindings", {}).get("development_module") if isinstance(manifest.get("software_bindings"), dict) else None
    if not isinstance(source, dict) or source.get("sha256") != V4_DEVELOPMENT_SOURCE_SHA256:
        raise HistoricalDiagnosticAuthorizationError("v4 manifest development source binding drifted")
    _verify_policy_bundle(receipt, workspace_root=root)
    targets = receipt.get("authorized_targets")
    expected_targets = _plan_targets(_load(expected_plan, "frozen diagnostic plan"), download_root=inventory["download_root"])
    if not isinstance(targets, list) or targets != expected_targets or len(targets) != 84:
        raise HistoricalDiagnosticAuthorizationError("receipt must bind exactly the frozen 84 archive targets")
    limits = receipt.get("download_limits")
    if not isinstance(limits, dict) or not isinstance(limits.get("max_archive_bytes_each"), int) or not isinstance(limits.get("max_total_archive_bytes"), int) or limits["max_archive_bytes_each"] <= 0 or limits["max_total_archive_bytes"] < limits["max_archive_bytes_each"]:
        raise HistoricalDiagnosticAuthorizationError("receipt download limits are invalid")
    contract_binding = receipt.get("authorized_execution_contract")
    if not isinstance(contract_binding, dict):
        raise HistoricalDiagnosticAuthorizationError("receipt must bind an authorized execution contract")
    contract_path = _relative(root, contract_binding.get("path"), "authorized_execution_contract.path")
    if sha256_file(contract_path) != contract_binding.get("sha256"):
        raise HistoricalDiagnosticAuthorizationError("authorized execution contract digest drifted")
    verify_authorized_execution_contract(contract_path, receipt_path, plan_path=expected_plan, workspace_root=root)
    if receipt.get("receipt_scope_sha256") != _receipt_scope(receipt):
        raise HistoricalDiagnosticAuthorizationError("authorization receipt scope digest drifted")
    return {"record_type": "pre_download_authorization_receipt_verification.v1", "verified": True, "receipt_id": receipt["receipt_id"], "sol_decision_id": receipt["sol_decision_id"], "target_count": 84, "input_count": 168, "ledger_id": ledger.get("id", ledger.get("ledger_id")), "verification_report": verification.get("path"), "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}


def _expected_day_bounds(day: str) -> tuple[str, str]:
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise HistoricalDiagnosticAuthorizationError("invalid input date") from exc
    start = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
    return start.isoformat(), datetime.fromtimestamp(start.timestamp() + 86400, tz=timezone.utc).isoformat()


def _read_checksum(path: Path, expected_filename: str) -> str:
    try:
        tokens = path.read_text(encoding="utf-8").strip().split()
    except (OSError, IndexError) as exc:
        raise HistoricalDiagnosticAuthorizationError("cannot read official checksum file") from exc
    if len(tokens) != 2 or tokens[1] != expected_filename:
        raise HistoricalDiagnosticAuthorizationError("official checksum filename declaration is invalid")
    token = tokens[0]
    if len(token) != 64 or any(char not in "0123456789abcdefABCDEF" for char in token):
        raise HistoricalDiagnosticAuthorizationError("official checksum content is invalid")
    return token.lower()


def _parse_csv_timestamp(value: str) -> datetime:
    value = value.strip()
    try:
        numeric = int(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HistoricalDiagnosticAuthorizationError("CSV timestamp is neither epoch nor ISO-8601") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if numeric <= 0:
        raise HistoricalDiagnosticAuthorizationError("CSV epoch timestamp must be positive")
    if numeric >= 10**12:
        return datetime.fromtimestamp(numeric / 1000.0, tz=timezone.utc)
    if numeric >= 10**9:
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    raise HistoricalDiagnosticAuthorizationError("CSV epoch timestamp has an unsupported unit")


def _schema_for_kind(kind: str, headers: Sequence[str]) -> tuple[str, str]:
    if tuple(headers) != HISTORICAL_MECHANISM_HEADERS[kind]:
        raise HistoricalDiagnosticAuthorizationError("CSV schema does not match declared %s archive" % kind)
    return "binance_cm_" + kind, {"aggTrades": "transact_time", "bookDepth": "timestamp", "metrics": "create_time"}[kind]


def _gap_limit_ms(plan: Mapping[str, Any], kind: str) -> int:
    timing = plan.get("timing_policy")
    if not isinstance(timing, dict):
        raise HistoricalDiagnosticAuthorizationError("frozen plan timing policy is required for acquisition audit")
    field = "max_oi_age_seconds" if kind == "metrics" else "max_book_gap_seconds"
    seconds = timing.get(field)
    if not isinstance(seconds, int) or seconds < 1:
        raise HistoricalDiagnosticAuthorizationError("frozen plan %s is invalid" % field)
    return seconds * 1000


def _audit_archive_csv(archive_path: Path, *, kind: str, day: str, plan: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            expected_member = archive_path.with_suffix(".csv").name
            if len(members) != 1 or members[0].filename != expected_member or Path(members[0].filename).is_absolute() or ".." in Path(members[0].filename).parts:
                raise HistoricalDiagnosticAuthorizationError("archive must contain exactly one safe CSV member")
            csv_bytes = archive.read(members[0])
    except (OSError, zipfile.BadZipFile) as exc:
        raise HistoricalDiagnosticAuthorizationError("cannot read acquired ZIP archive") from exc
    try:
        rows = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        headers = rows.fieldnames or []
        schema_id, timestamp_key = _schema_for_kind(kind, headers)
        records = list(rows)
        timestamps = [_parse_csv_timestamp(row.get(timestamp_key, "")) for row in records]
    except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise HistoricalDiagnosticAuthorizationError("cannot parse acquired CSV") from exc
    if not timestamps:
        raise HistoricalDiagnosticAuthorizationError("acquired CSV has no rows")
    if kind == "aggTrades":
        ordering = []
        for row, timestamp in zip(records, timestamps):
            try:
                aggregate_id = int(row["agg_trade_id"])
                price, quantity = float(row["price"]), float(row["quantity"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HistoricalDiagnosticAuthorizationError("aggTrades numeric fields are invalid") from exc
            if aggregate_id < 0 or price <= 0 or quantity <= 0 or row.get("is_buyer_maker") not in {"true", "false", "True", "False"}:
                raise HistoricalDiagnosticAuthorizationError("aggTrades row contents are invalid")
            ordering.append((timestamp, aggregate_id))
        if ordering != sorted(ordering) or len(set(ordering)) != len(ordering):
            raise HistoricalDiagnosticAuthorizationError("aggTrades must be strictly ordered by (time, aggregate id)")
    elif kind == "metrics":
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise HistoricalDiagnosticAuthorizationError("metrics timestamps must be strictly increasing")
        for row in records:
            try:
                open_interest = float(row["sum_open_interest"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HistoricalDiagnosticAuthorizationError("metrics open interest is invalid") from exc
            if row.get("symbol") != "BTCUSD_PERP" or open_interest <= 0:
                raise HistoricalDiagnosticAuthorizationError("metrics symbol/open interest is invalid")
    else:
        groups: Dict[datetime, Dict[float, int]] = {}
        for row, timestamp in zip(records, timestamps):
            try:
                percentage, depth = float(row["percentage"]), float(row["depth"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HistoricalDiagnosticAuthorizationError("bookDepth numeric fields are invalid") from exc
            if depth <= 0:
                raise HistoricalDiagnosticAuthorizationError("bookDepth depth must be positive")
            counts = groups.setdefault(timestamp, {})
            counts[percentage] = counts.get(percentage, 0) + 1
        if any(counts.get(-1.0) != 1 or counts.get(1.0) != 1 for counts in groups.values()):
            raise HistoricalDiagnosticAuthorizationError("bookDepth snapshot lacks complete +/-1 depth")
        timestamps = sorted(groups)
    start_text, end_text = _expected_day_bounds(day)
    start, end = datetime.fromisoformat(start_text), datetime.fromisoformat(end_text)
    if any(timestamp < start or timestamp >= end for timestamp in timestamps):
        raise HistoricalDiagnosticAuthorizationError("acquired CSV contains timestamps outside its declared UTC date")
    internal_gap = max((int((right - left).total_seconds() * 1000) for left, right in zip(timestamps, timestamps[1:])), default=0)
    coverage = {"start_at": start.isoformat(), "end_at": end.isoformat(), "archive_date_membership_verified": True, "first_at": timestamps[0].isoformat(), "last_at": timestamps[-1].isoformat()}
    if kind == "aggTrades":
        # Trades are event observations, not a heartbeat.  A quiet interval is
        # market information and must be handled by the later entry/path label
        # censoring policy, never recast here as download/ingest loss.
        coverage["complete_cadence_coverage"] = False
        return {"schema_id": schema_id, "zip_member": members[0].filename, "zip_member_sha256": hashlib.sha256(csv_bytes).hexdigest(), "csv_header": headers, "csv_schema_sha256": canonical_sha256(headers), "row_count": len(records), "time_coverage": coverage, "gap_audit": {"status": "OBSERVED_INTER_EVENT_NOT_INGEST_GAP", "max_inter_event_gap_ms": internal_gap, "scorer_must_censor_entry_or_path_gaps": True}}
    first_offset = int((timestamps[0] - start).total_seconds() * 1000)
    end_offset = int((end - timestamps[-1]).total_seconds() * 1000)
    max_gap = max(first_offset, end_offset, internal_gap)
    limit = _gap_limit_ms(plan, kind)
    if max_gap > limit:
        raise HistoricalDiagnosticAuthorizationError("acquired CSV exceeds the frozen maximum age/gap")
    coverage.update({"complete_cadence_coverage": True, "first_age_ms": first_offset, "last_age_ms": end_offset})
    return {"schema_id": schema_id, "zip_member": members[0].filename, "zip_member_sha256": hashlib.sha256(csv_bytes).hexdigest(), "csv_header": headers, "csv_schema_sha256": canonical_sha256(headers), "row_count": len(records), "time_coverage": coverage, "gap_audit": {"status": "PASS", "missing_intervals": 0, "max_gap_ms": max_gap, "frozen_max_gap_ms": limit}}


def _write_once_json(path: Path, value: Mapping[str, Any]) -> None:
    if Path(path).exists():
        raise HistoricalDiagnosticAuthorizationError("input acquisition receipt is write-once and already exists")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise HistoricalDiagnosticAuthorizationError("input acquisition receipt is write-once and already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def build_input_acquisition_receipt(plan_path: Path, receipt_path: Path, output_path: Path, *, workspace_root: Path) -> Dict[str, Any]:
    """Parse all authorized local ZIPs and create the only admissible input receipt.

    This function has no network calls.  The caller must have already received
    authorization and placed the exact archives/checksums at the frozen paths.
    """
    root = Path(workspace_root).resolve()
    output = Path(output_path).resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise HistoricalDiagnosticAuthorizationError("output_path must stay inside workspace_root") from exc
    authorization = verify_pre_download_authorization_receipt(receipt_path, plan_path=plan_path, workspace_root=root)
    receipt = _load(receipt_path, "pre-download authorization receipt")
    plan = _load(plan_path, "frozen diagnostic plan")
    contract_binding = receipt["authorized_execution_contract"]
    contract_path = _relative(root, contract_binding["path"], "authorized_execution_contract.path")
    inputs = []
    total_bytes = 0
    for target in receipt["authorized_targets"]:
        archive = _relative(root, target["archive_path"], "target.archive_path")
        checksum = _relative(root, target["checksum_path"], "target.checksum_path")
        if not archive.is_file() or not checksum.is_file():
            raise HistoricalDiagnosticAuthorizationError("one or more authorized archives/checksums are missing")
        size = archive.stat().st_size
        if size > receipt["download_limits"]["max_archive_bytes_each"]:
            raise HistoricalDiagnosticAuthorizationError("archive exceeds authorized per-file download limit")
        total_bytes += size
        archive_digest = sha256_file(archive)
        if _read_checksum(checksum, archive.name) != archive_digest:
            raise HistoricalDiagnosticAuthorizationError("official checksum does not validate acquired archive")
        audit = _audit_archive_csv(archive, kind=target["kind"], day=target["date"], plan=plan)
        inputs.append(dict(target, archive_sha256=archive_digest, checksum_sha256=sha256_file(checksum), **audit))
    if total_bytes > receipt["download_limits"]["max_total_archive_bytes"]:
        raise HistoricalDiagnosticAuthorizationError("acquisition exceeds authorized total download limit")
    result = {"record_type": ACQUISITION_RECORD, "status": "ACQUIRED_NOT_SCORED", "plan": {"path": str(Path(plan_path).resolve().relative_to(root)), "sha256": sha256_file(plan_path)}, "authorized_execution_contract": {"contract_id": contract_binding["contract_id"], "path": contract_binding["path"], "sha256": sha256_file(contract_path)}, "authorization_receipt": {"receipt_id": authorization["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"]}, "model_and_policy_sha256": canonical_sha256(receipt["model_and_policy"]), "inputs": inputs, "quality_summary": {"archive_count": 84, "checksum_count": 84, "total_archive_bytes": total_bytes, "total_csv_rows": sum(item["row_count"] for item in inputs), "aggtrade_observed_inter_event_noncontinuity_count": 28, "all_schema_date_coverage_and_gap_audits": "PASS_WITH_AGGTRADES_CENSORING_REQUIRED"}, "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
    _write_once_json(output, result)
    return result


def verify_acquisition_receipt(acquisition_path: Path, receipt_path: Path, *, plan_path: Path, workspace_root: Path) -> Dict[str, Any]:
    root = Path(workspace_root).resolve()
    authorization = verify_pre_download_authorization_receipt(receipt_path, plan_path=plan_path, workspace_root=root)
    receipt = _load(receipt_path, "pre-download authorization receipt")
    frozen_plan = _load(plan_path, "frozen diagnostic plan")
    acquisition = _load(acquisition_path, "acquisition receipt")
    if acquisition.get("record_type") != ACQUISITION_RECORD or acquisition.get("status") != "ACQUIRED_NOT_SCORED":
        raise HistoricalDiagnosticAuthorizationError("acquisition receipt must remain ACQUIRED_NOT_SCORED")
    _verify_denials(acquisition)
    plan_binding = acquisition.get("plan")
    if not isinstance(plan_binding, dict) or plan_binding.get("path") != str(Path(plan_path).resolve().relative_to(root)) or plan_binding.get("sha256") != sha256_file(plan_path):
        raise HistoricalDiagnosticAuthorizationError("acquisition receipt frozen plan binding drifted")
    contract_binding = acquisition.get("authorized_execution_contract")
    receipt_contract = receipt.get("authorized_execution_contract")
    if not isinstance(contract_binding, dict) or contract_binding != {"contract_id": receipt_contract.get("contract_id"), "path": receipt_contract.get("path"), "sha256": receipt_contract.get("sha256")}:
        raise HistoricalDiagnosticAuthorizationError("acquisition receipt execution contract binding drifted")
    binding = acquisition.get("authorization_receipt")
    if not isinstance(binding, dict) or binding.get("receipt_id") != authorization["receipt_id"] or binding.get("receipt_scope_sha256") != receipt.get("receipt_scope_sha256"):
        raise HistoricalDiagnosticAuthorizationError("acquisition receipt is not bound to authorization")
    if acquisition.get("model_and_policy_sha256") != canonical_sha256(receipt["model_and_policy"]):
        raise HistoricalDiagnosticAuthorizationError("software/model/policy receipt drifted before scoring")
    expected = {(target["kind"], target["date"]): target for target in receipt["authorized_targets"]}
    inputs = acquisition.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != 84 or {(item.get("kind"), item.get("date")) for item in inputs if isinstance(item, dict)} != set(expected):
        raise HistoricalDiagnosticAuthorizationError("acquisition receipt must have exactly one entry for every authorized archive")
    total_bytes = 0
    for item in inputs:
        target = expected[(item["kind"], item["date"])]
        for key in ("archive_path", "checksum_path", "archive_url", "checksum_url"):
            if item.get(key) != target[key]:
                raise HistoricalDiagnosticAuthorizationError("acquisition target binding drifted")
        archive = _relative(root, item["archive_path"], "input.archive_path")
        checksum = _relative(root, item["checksum_path"], "input.checksum_path")
        if archive.stat().st_size > receipt["download_limits"]["max_archive_bytes_each"]:
            raise HistoricalDiagnosticAuthorizationError("archive exceeds authorized per-file download limit")
        total_bytes += archive.stat().st_size
        if item.get("archive_sha256") != sha256_file(archive) or item.get("checksum_sha256") != sha256_file(checksum):
            raise HistoricalDiagnosticAuthorizationError("acquired archive/checksum digest drifted")
        if _read_checksum(checksum, archive.name) != item["archive_sha256"]:
            raise HistoricalDiagnosticAuthorizationError("official checksum does not validate acquired archive")
        recomputed = _audit_archive_csv(archive, kind=item["kind"], day=item["date"], plan=frozen_plan)
        for key in ("schema_id", "zip_member", "zip_member_sha256", "csv_header", "csv_schema_sha256", "row_count", "time_coverage", "gap_audit"):
            if item.get(key) != recomputed[key]:
                raise HistoricalDiagnosticAuthorizationError("acquisition receipt schema/coverage/gap facts drifted from local archive")
        expected_schema = {"aggTrades": "binance_cm_aggTrades", "bookDepth": "binance_cm_bookDepth", "metrics": "binance_cm_metrics"}[item["kind"]]
        if item.get("schema_id") != expected_schema or not isinstance(item.get("row_count"), int) or item["row_count"] <= 0:
            raise HistoricalDiagnosticAuthorizationError("input schema is not declared")
        start, end = _expected_day_bounds(item["date"])
        coverage = item.get("time_coverage")
        audit = item.get("gap_audit")
        if not isinstance(coverage, dict) or coverage.get("start_at") != start or coverage.get("end_at") != end or coverage.get("archive_date_membership_verified") is not True:
            raise HistoricalDiagnosticAuthorizationError("input date membership audit is invalid")
        if item["kind"] == "aggTrades":
            if coverage.get("complete_cadence_coverage") is not False or not isinstance(audit, dict) or audit.get("status") != "OBSERVED_INTER_EVENT_NOT_INGEST_GAP" or audit.get("scorer_must_censor_entry_or_path_gaps") is not True or not isinstance(audit.get("max_inter_event_gap_ms"), int) or audit["max_inter_event_gap_ms"] < 0:
                raise HistoricalDiagnosticAuthorizationError("aggTrades receipt falsely claims cadence continuity or lacks censoring boundary")
        elif coverage.get("complete_cadence_coverage") is not True or not isinstance(audit, dict) or audit.get("status") != "PASS" or audit.get("missing_intervals") != 0 or not isinstance(audit.get("max_gap_ms"), int) or audit["max_gap_ms"] < 0:
            raise HistoricalDiagnosticAuthorizationError("cadenced input gap audit is not a passing factual audit")
    if total_bytes > receipt["download_limits"]["max_total_archive_bytes"]:
        raise HistoricalDiagnosticAuthorizationError("acquisition exceeds authorized total download limit")
    summary = acquisition.get("quality_summary")
    if not isinstance(summary, dict) or summary.get("archive_count") != 84 or summary.get("checksum_count") != 84 or summary.get("total_archive_bytes") != total_bytes or summary.get("total_csv_rows") != sum(item["row_count"] for item in inputs) or summary.get("aggtrade_observed_inter_event_noncontinuity_count") != 28 or summary.get("all_schema_date_coverage_and_gap_audits") != "PASS_WITH_AGGTRADES_CENSORING_REQUIRED":
        raise HistoricalDiagnosticAuthorizationError("acquisition quality summary drifted")
    return {"record_type": "historical_diagnostic_acquisition_receipt_verification.v1", "verified": True, "receipt_id": authorization["receipt_id"], "archive_count": 84, "checksum_count": 84, "total_archive_bytes": total_bytes, "status": "ACQUIRED_NOT_SCORED", "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".authorization-registry-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_registry(path: Path) -> Dict[str, Any]:
    if not Path(path).exists():
        return {"record_type": REGISTRY_RECORD, "entries": {}}
    registry = _load(path, "authorization consumption registry")
    if registry.get("record_type") != REGISTRY_RECORD or not isinstance(registry.get("entries"), dict):
        raise HistoricalDiagnosticAuthorizationError("authorization consumption registry is invalid")
    return registry


def _mutate_registry_atomically(path: Path, mutate: Any) -> Dict[str, Any]:
    """Serialize check-and-consume so two scorers cannot both win a race."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            registry = _load_registry(path)
            result = mutate(registry)
            _atomic_write_json(path, registry)
            return result
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def register_wait_data_not_scored(registry_path: Path, *, receipt_id: str, receipt_scope_sha256: str, summary_sha256: str) -> Dict[str, Any]:
    """Atomically record a terminal no-model, no-score WAIT_DATA state."""
    _reject_terminal_february_registry_mutation(receipt_id=receipt_id, registry_path=registry_path)
    _require_text(receipt_id, "receipt_id")
    if not all(isinstance(value, str) and len(value) == 64 for value in (receipt_scope_sha256, summary_sha256)):
        raise HistoricalDiagnosticAuthorizationError("receipt and summary digests must be SHA-256 values")
    expected = {"receipt_scope_sha256": receipt_scope_sha256, "summary_sha256": summary_sha256, "status": "WAIT_DATA_NOT_SCORED"}

    def mutate(registry: Dict[str, Any]) -> Dict[str, Any]:
        existing = registry["entries"].get(receipt_id)
        if existing is not None:
            if existing != expected:
                raise HistoricalDiagnosticAuthorizationError("existing authorization registry entry drifted")
            raise HistoricalDiagnosticAuthorizationError("duplicate WAIT_DATA registration is refused")
        registry["entries"][receipt_id] = expected
        return dict(expected, receipt_id=receipt_id)

    return _mutate_registry_atomically(Path(registry_path), mutate)


def register_ready_to_score(registry_path: Path, acquisition_path: Path, receipt_path: Path, *, plan_path: Path, workspace_root: Path, summary_sha256: str) -> Dict[str, Any]:
    """Only a complete, verified acquisition may enter the fresh-score state."""
    acquisition = verify_acquisition_receipt(acquisition_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root)
    receipt = _load(receipt_path, "pre-download authorization receipt")
    if not isinstance(summary_sha256, str) or len(summary_sha256) != 64:
        raise HistoricalDiagnosticAuthorizationError("summary_sha256 must be a SHA-256 value")
    expected = {"receipt_scope_sha256": receipt["receipt_scope_sha256"], "summary_sha256": summary_sha256, "status": "READY_TO_SCORE", "acquisition_receipt_sha256": sha256_file(acquisition_path), "verified_archive_count": acquisition["archive_count"]}

    def mutate(registry: Dict[str, Any]) -> Dict[str, Any]:
        if registry["entries"].get(receipt["receipt_id"]) is not None:
            raise HistoricalDiagnosticAuthorizationError("authorization already has an immutable registry state")
        registry["entries"][receipt["receipt_id"]] = expected
        return dict(expected, receipt_id=receipt["receipt_id"])

    return _mutate_registry_atomically(Path(registry_path), mutate)


def consume_fresh_scoring_authorization(registry_path: Path, acquisition_path: Path, receipt_path: Path, *, plan_path: Path, workspace_root: Path, summary_sha256: str, scoring_attempt_id: str) -> Dict[str, Any]:
    """Consume a fresh authorization before scoring; it cannot be reopened."""
    acquisition = verify_acquisition_receipt(acquisition_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root)
    receipt = _load(receipt_path, "pre-download authorization receipt")
    _require_text(scoring_attempt_id, "scoring_attempt_id")
    if not isinstance(summary_sha256, str) or len(summary_sha256) != 64:
        raise HistoricalDiagnosticAuthorizationError("summary_sha256 must be a SHA-256 value")
    expected = {"receipt_scope_sha256": receipt["receipt_scope_sha256"], "summary_sha256": summary_sha256, "status": "READY_TO_SCORE", "acquisition_receipt_sha256": sha256_file(acquisition_path), "verified_archive_count": acquisition["archive_count"]}

    def mutate(registry: Dict[str, Any]) -> Dict[str, Any]:
        existing = registry["entries"].get(receipt["receipt_id"])
        if existing != expected:
            raise HistoricalDiagnosticAuthorizationError("scoring requires one exact prior READY_TO_SCORE registry entry")
        registry["entries"][receipt["receipt_id"]] = {"receipt_scope_sha256": receipt["receipt_scope_sha256"], "summary_sha256": summary_sha256, "status": "CONSUMED_SCORING_STARTED", "scoring_attempt_id": scoring_attempt_id, "acquisition_receipt_sha256": sha256_file(acquisition_path), "verified_archive_count": acquisition["archive_count"]}
        return dict(registry["entries"][receipt["receipt_id"]], receipt_id=receipt["receipt_id"])

    return _mutate_registry_atomically(Path(registry_path), mutate)


def get_authorization_registry_entry(registry_path: Path, *, receipt_id: str, receipt_scope_sha256: str) -> Dict[str, Any]:
    """Read-only state query; it never upgrades or opens an authorization."""
    _require_text(receipt_id, "receipt_id")
    if not isinstance(receipt_scope_sha256, str) or len(receipt_scope_sha256) != 64:
        raise HistoricalDiagnosticAuthorizationError("receipt_scope_sha256 must be a SHA-256 value")
    entry = _load_registry(registry_path)["entries"].get(receipt_id)
    if not isinstance(entry, dict) or entry.get("receipt_scope_sha256") != receipt_scope_sha256:
        raise HistoricalDiagnosticAuthorizationError("authorization registry entry is missing or drifted")
    state = entry.get("status")
    if state not in {"WAIT_DATA_NOT_SCORED", "READY_TO_SCORE", "CONSUMED_SCORING_STARTED", "SCORING_COMPLETE", "SCORING_FAILED_CONSUMED"}:
        raise HistoricalDiagnosticAuthorizationError("authorization registry state is invalid")
    if state == "READY_TO_SCORE" and (not isinstance(entry.get("acquisition_receipt_sha256"), str) or entry.get("verified_archive_count") != 84):
        raise HistoricalDiagnosticAuthorizationError("READY_TO_SCORE entry lacks verified acquisition binding")
    if state == "CONSUMED_SCORING_STARTED" and not isinstance(entry.get("scoring_attempt_id"), str):
        raise HistoricalDiagnosticAuthorizationError("consumed authorization lacks scoring attempt identity")
    return dict(entry, receipt_id=receipt_id)


def finalize_consumed_scoring(registry_path: Path, *, receipt_id: str, receipt_scope_sha256: str, status: str, report_sha256: str) -> Dict[str, Any]:
    """Atomically seal a consumed score attempt to one final factual state."""
    if status not in {"SCORING_COMPLETE", "SCORING_FAILED_CONSUMED"} or not isinstance(report_sha256,str) or len(report_sha256)!=64:
        raise HistoricalDiagnosticAuthorizationError("final scoring state is invalid")
    def mutate(registry: Dict[str, Any]) -> Dict[str, Any]:
        prior=registry["entries"].get(receipt_id)
        if not isinstance(prior,dict) or prior.get("status")!="CONSUMED_SCORING_STARTED" or prior.get("receipt_scope_sha256")!=receipt_scope_sha256:
            raise HistoricalDiagnosticAuthorizationError("only a consumed scoring attempt may be finalized")
        final=dict(prior,status=status,final_report_sha256=report_sha256)
        registry["entries"][receipt_id]=final
        return dict(final,receipt_id=receipt_id)
    return _mutate_registry_atomically(Path(registry_path),mutate)
