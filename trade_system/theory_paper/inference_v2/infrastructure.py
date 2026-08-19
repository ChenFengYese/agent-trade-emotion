"""Infrastructure adapters for successor-v2 shadow inference."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from trade_system.theory_paper.common import sha256_file, verify_ledger

from .domain import (
    HISTORICAL_MODE,
    LIVE_MODE,
    InferenceV2Error,
    canonical_bytes,
    canonical_digest,
    parse_utc,
)


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise InferenceV2Error("JSON_NONFINITE")
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except FileNotFoundError as exc:
        raise InferenceV2Error(f"SOURCE_FILE_MISSING:{path.name}") from exc
    except (_DuplicateKey, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InferenceV2Error(f"SOURCE_JSON_INVALID:{path.name}") from exc
    if not isinstance(value, dict):
        raise InferenceV2Error(f"SOURCE_JSON_ROOT_INVALID:{path.name}")
    _assert_finite(value)
    return value


def load_framework_config(path: Path) -> dict[str, Any]:
    return read_json_object(Path(path))


def _artifact_digest(
    commit: dict[str, Any],
    relative_path: str,
    actual_path: Path,
) -> str:
    artifact_digests = commit.get("artifact_digests")
    if not isinstance(artifact_digests, dict):
        raise InferenceV2Error("SOURCE_COMMIT_ARTIFACTS_MISSING")
    expected = artifact_digests.get(relative_path)
    actual = canonical_digest(read_json_object(actual_path))
    if expected != actual:
        raise InferenceV2Error(f"SOURCE_ARTIFACT_DIGEST_MISMATCH:{relative_path}")
    return actual


def _names(rows: Any, field: str, reason: str) -> list[str]:
    if not isinstance(rows, list):
        raise InferenceV2Error(reason)
    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(field), str):
            raise InferenceV2Error(reason)
        result.append(row[field])
    if len(result) != len(set(result)):
        raise InferenceV2Error(reason)
    return result


def load_frozen_cycle(
    run_dir: Path,
    cycle_id: str,
    *,
    mode: str,
) -> dict[str, Any]:
    """Read and verify one v1 cycle without mutating the v1 tree."""

    if mode not in {HISTORICAL_MODE, LIVE_MODE}:
        raise InferenceV2Error("SOURCE_MODE_INVALID")
    if (
        not isinstance(cycle_id, str)
        or not cycle_id.startswith("cycle-")
        or not cycle_id[6:].isdigit()
    ):
        raise InferenceV2Error("SOURCE_CYCLE_ID_INVALID")
    root = Path(run_dir).resolve()
    manifest_path = root / "manifest.json"
    ledger_path = root / "ledger.ndjson"
    if not ledger_path.is_file():
        raise InferenceV2Error("SOURCE_LEDGER_MISSING")
    manifest = read_json_object(manifest_path)
    if manifest.get("schema_version") != "theory-paper-run-manifest.v1":
        raise InferenceV2Error("SOURCE_MANIFEST_SCHEMA_MISMATCH")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise InferenceV2Error("SOURCE_RUN_ID_MISSING")
    authority = manifest.get("authority_boundary")
    if not isinstance(authority, dict):
        raise InferenceV2Error("SOURCE_AUTHORITY_BOUNDARY_MISSING")
    if (
        authority.get("credential_capability") is not False
        or authority.get("exchange_private_api_capability") is not False
        or authority.get("live_order_capability") is not False
        or authority.get("paper_permission") != "LOCAL_SIMULATION_ONLY"
    ):
        raise InferenceV2Error("SOURCE_AUTHORITY_BOUNDARY_UNSAFE")
    try:
        ledger_verdict = verify_ledger(root)
    except Exception as exc:
        raise InferenceV2Error("SOURCE_LEDGER_INVALID") from exc

    cycle_root = root / "cycles" / cycle_id
    market_path = cycle_root / "market.json"
    news_path = cycle_root / "news.json"
    analysis_path = cycle_root / "analysis.json"
    analysis_commit_path = root / "transactions" / f"{cycle_id}-analysis.commit.json"
    market = read_json_object(market_path)
    news = read_json_object(news_path)
    analysis = read_json_object(analysis_path)
    analysis_commit = read_json_object(analysis_commit_path)
    if analysis_commit.get("schema_version") != "theory-paper-transaction-commit.v1":
        raise InferenceV2Error("SOURCE_ANALYSIS_COMMIT_SCHEMA_MISMATCH")
    if analysis_commit.get("transaction_id") != f"{cycle_id}-analysis":
        raise InferenceV2Error("SOURCE_ANALYSIS_COMMIT_ID_MISMATCH")
    if analysis_commit.get("ledger_event_type") != "HOURLY_ANALYSIS_FROZEN":
        raise InferenceV2Error("SOURCE_ANALYSIS_COMMIT_EVENT_MISMATCH")
    source_artifacts: dict[str, str] = {
        "manifest.json.physical_sha256": sha256_file(manifest_path),
        "analysis.commit.json.physical_sha256": sha256_file(analysis_commit_path),
        "market.json": _artifact_digest(
            analysis_commit, f"cycles/{cycle_id}/market.json", market_path
        ),
        "news.json": _artifact_digest(
            analysis_commit, f"cycles/{cycle_id}/news.json", news_path
        ),
        "analysis.json": _artifact_digest(
            analysis_commit, f"cycles/{cycle_id}/analysis.json", analysis_path
        ),
    }
    source_committed_at: str | None = None
    agent_decision: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    if mode == HISTORICAL_MODE:
        agent_path = cycle_root / "agent-decision.json"
        decision_path = cycle_root / "decision.json"
        decision_commit_path = (
            root / "transactions" / f"{cycle_id}-decision.commit.json"
        )
        agent_decision = read_json_object(agent_path)
        decision = read_json_object(decision_path)
        decision_commit = read_json_object(decision_commit_path)
        if (
            decision_commit.get("schema_version")
            != "theory-paper-transaction-commit.v1"
        ):
            raise InferenceV2Error("SOURCE_DECISION_COMMIT_SCHEMA_MISMATCH")
        if decision_commit.get("transaction_id") != f"{cycle_id}-decision":
            raise InferenceV2Error("SOURCE_DECISION_COMMIT_ID_MISMATCH")
        if decision_commit.get("ledger_event_type") != "AGENT_DECISION_APPLIED":
            raise InferenceV2Error("SOURCE_DECISION_COMMIT_EVENT_MISMATCH")
        source_artifacts.update(
            {
                "agent-decision.json.physical_sha256": sha256_file(agent_path),
                "decision.json": _artifact_digest(
                    decision_commit,
                    f"cycles/{cycle_id}/decision.json",
                    decision_path,
                ),
                "decision.commit.json.physical_sha256": sha256_file(
                    decision_commit_path
                ),
            }
        )
        internal_analysis_digest = analysis.get("analysis_digest")
        decision_at = analysis.get("decision_at")
        validated = decision.get("validated_decision")
        if not isinstance(validated, dict):
            raise InferenceV2Error("SOURCE_VALIDATED_DECISION_MISSING")
        if (
            agent_decision.get("analysis_digest") != internal_analysis_digest
            or validated.get("analysis_digest") != internal_analysis_digest
            or agent_decision.get("decision_at") != decision_at
            or validated.get("decision_at") != decision_at
        ):
            raise InferenceV2Error("SOURCE_DECISION_ANALYSIS_BINDING_MISMATCH")
        if decision.get("analysis_digest") != source_artifacts["analysis.json"]:
            raise InferenceV2Error("SOURCE_DECISION_ARTIFACT_BINDING_MISMATCH")
        if decision.get("cycle_id") != cycle_id:
            raise InferenceV2Error("SOURCE_DECISION_CYCLE_MISMATCH")
        source_committed_at = decision.get("decided_at")
        if parse_utc(source_committed_at) < parse_utc(decision_at):
            raise InferenceV2Error("SOURCE_DECISION_COMMIT_TIME_INVALID")

    manifest_symbols = manifest.get("symbols")
    if not isinstance(manifest_symbols, list) or not all(
        isinstance(symbol, str) for symbol in manifest_symbols
    ):
        raise InferenceV2Error("SOURCE_MANIFEST_SYMBOLS_INVALID")
    analysis_symbols = _names(
        analysis.get("symbols"), "symbol", "SOURCE_ANALYSIS_SYMBOLS_INVALID"
    )
    market_symbols = _names(
        market.get("symbols"), "symbol", "SOURCE_MARKET_SYMBOLS_INVALID"
    )
    if analysis_symbols != market_symbols or analysis_symbols != manifest_symbols:
        raise InferenceV2Error("SOURCE_SYMBOL_SET_MISMATCH")
    if mode == HISTORICAL_MODE:
        assert agent_decision is not None and decision is not None
        agent_symbols = _names(
            agent_decision.get("symbol_decisions"),
            "symbol",
            "SOURCE_AGENT_SYMBOLS_INVALID",
        )
        validated_symbols = _names(
            decision["validated_decision"].get("symbol_decisions"),
            "symbol",
            "SOURCE_VALIDATED_SYMBOLS_INVALID",
        )
        if agent_symbols != analysis_symbols or validated_symbols != analysis_symbols:
            raise InferenceV2Error("SOURCE_DECISION_SYMBOL_SET_MISMATCH")

    return {
        "schema_version": "SourceCycleEnvelope.v1",
        "run_id": run_id,
        "cycle_id": cycle_id,
        "mode": mode,
        "run_dir": str(root),
        "manifest": manifest,
        "market": market,
        "news": news,
        "analysis": analysis,
        "agent_decision": agent_decision,
        "decision": decision,
        "source_committed_at": source_committed_at,
        "source_artifacts": dict(sorted(source_artifacts.items())),
        "ledger_verdict": ledger_verdict,
        "source_envelope_digest": canonical_digest(
            {
                "run_id": run_id,
                "cycle_id": cycle_id,
                "mode": mode,
                "source_artifacts": dict(sorted(source_artifacts.items())),
            }
        ),
    }


def sidecar_path(output_dir: Path, cycle_id: str) -> Path:
    return Path(output_dir) / "cycles" / cycle_id / "inference-sidecar.v2.json"


def load_existing_sidecar(output_dir: Path, cycle_id: str) -> dict[str, Any] | None:
    path = sidecar_path(output_dir, cycle_id)
    if not path.exists():
        return None
    return read_json_object(path)


def preflight_sidecar_write(
    *,
    source_run_dir: Path,
    output_dir: Path,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    source_root = Path(source_run_dir).resolve()
    output_root = Path(output_dir).resolve()
    try:
        output_root.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise InferenceV2Error("OUTPUT_INSIDE_PROTECTED_V1_RUN")
    target = sidecar_path(output_root, str(sidecar["source"]["cycle_id"]))
    payload = canonical_bytes(sidecar) + b"\n"
    if target.exists():
        if target.read_bytes() != payload:
            raise InferenceV2Error(f"WRITE_CONFLICT:{target}")
        status = "EXISTING_IDENTICAL"
    else:
        status = "READY_TO_CREATE"
    return {
        "status": status,
        "path": str(target),
        "sidecar_digest": sidecar["sidecar_digest"],
    }


def write_sidecar(
    *,
    source_run_dir: Path,
    output_dir: Path,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    preflight = preflight_sidecar_write(
        source_run_dir=source_run_dir,
        output_dir=output_dir,
        sidecar=sidecar,
    )
    target = Path(preflight["path"])
    payload = canonical_bytes(sidecar) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    if preflight["status"] == "EXISTING_IDENTICAL":
        return {
            "status": "EXISTING_IDENTICAL",
            "path": str(target),
            "sidecar_digest": sidecar["sidecar_digest"],
        }
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InferenceV2Error(f"WRITE_RACE:{target}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "status": "CREATED",
        "path": str(target),
        "sidecar_digest": sidecar["sidecar_digest"],
    }
