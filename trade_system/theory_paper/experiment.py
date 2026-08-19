"""Orchestration for the credential-free 72-hour theory paper experiment."""

from __future__ import annotations

import copy
import json
import os
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .common import (
    TheoryPaperError,
    append_ledger_event,
    digest_json,
    experiment_lock,
    iso_utc,
    parse_utc,
    read_json,
    sha256_file,
    verify_ledger,
    write_atomic_json,
    write_new_json,
)
from .market import BinancePublicClient, fetch_market_snapshot, fetch_news_headlines
from .portfolio import (
    initialize_portfolio,
    inject_due_chaos,
    inject_manual_chaos,
    portfolio_metrics,
    process_market_bars,
    submit_actions,
)
from .theory import (
    build_cycle_analysis,
    build_decision_template,
    build_method_candidates,
    score_cycle,
    score_method_practice,
    validate_decision,
)


MarketFetcher = Callable[..., dict[str, Any]]
NewsFetcher = Callable[..., dict[str, Any]]

LIVE_CLOCK = "LIVE_WALL_CLOCK"
SIMULATED_CLOCK = "SIMULATED_CLOCK_TEST_ONLY"
AUTHORITY_BINDING_PATHS = (
    "archive/experiments/THEORY_PAPER_AGENT_GUIDE.md",
    "archive/authority/CORE_TRADING_THEORY_v2_1.md",
    "theory/history/GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md",
    "theory/history/RESEARCH_SYSTEM_DYNAMIC_HYPOTHESIS_GRAPH_CHALLENGER_v1_2.md",
    "archive/authority/DATA_AUTHORITY_STANDARD_v1_0.md",
    "config/theory_paper_automation_prompt.v1.md",
    "trade_system/cli.py",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _secret_shape_paths(value: Any, path: str = "$") -> list[str]:
    """Return config/receipt paths that look capable of carrying credentials."""

    forbidden_keys = {
        "apikey",
        "apisecret",
        "secretkey",
        "credential",
        "credentials",
        "privatekey",
        "accesstoken",
        "refreshtoken",
        "listenkey",
        "signature",
        "passphrase",
        "mnemonic",
        "seedphrase",
    }
    value_patterns = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?i)\b(?:api[_-]?key|api[_-]?secret|access[_-]?token)\s*[:=]\s*\S+"),
    )
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _normalized_key(key) in forbidden_keys:
                found.append(child_path)
            found.extend(_secret_shape_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_secret_shape_paths(child, f"{path}[{index}]"))
    elif isinstance(value, str) and any(pattern.search(value) for pattern in value_patterns):
        found.append(path)
    return found


def _clock_policy(config: Mapping[str, Any]) -> tuple[str, float]:
    policy = config.get("clock_policy")
    if not isinstance(policy, Mapping):
        raise TheoryPaperError("clock_policy is required")
    mode = policy.get("mode")
    if mode not in {LIVE_CLOCK, SIMULATED_CLOCK}:
        raise TheoryPaperError("clock_policy.mode is invalid")
    tolerance = policy.get("future_tolerance_seconds")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise TheoryPaperError("clock future tolerance must be numeric")
    tolerance_value = float(tolerance)
    if tolerance_value < 0 or tolerance_value > 300:
        raise TheoryPaperError("clock future tolerance must be between 0 and 300 seconds")
    return str(mode), tolerance_value


def _require_wall_clock(config: Mapping[str, Any], value: datetime, label: str) -> None:
    mode, tolerance = _clock_policy(config)
    if mode != LIVE_CLOCK:
        return
    wall_now = datetime.now(timezone.utc)
    if abs((value.astimezone(timezone.utc) - wall_now).total_seconds()) > tolerance:
        raise TheoryPaperError(
            f"{label} must match the live wall clock within {tolerance:g} seconds"
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _file_binding(path: Path, relative: str) -> dict[str, Any]:
    if not path.is_file():
        raise TheoryPaperError(f"authority binding is missing: {relative}")
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _load_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    secret_paths = _secret_shape_paths(config)
    if secret_paths:
        raise TheoryPaperError(
            "experiment config contains credential-shaped material: "
            + ",".join(secret_paths[:5])
        )
    if (
        config.get("status")
        != "EXPERIMENTAL_PAPER_PRACTICE_VALIDATION_NOT_CAUSAL_OR_PREDICTIVE_PROOF"
    ):
        raise TheoryPaperError(
            "experiment config must retain its bounded paper-practice validation status"
        )
    boundary = config.get("authority_boundary")
    if not isinstance(boundary, dict):
        raise TheoryPaperError("authority_boundary is required")
    forbidden = (
        boundary.get("live_order_capability"),
        boundary.get("credential_capability"),
        boundary.get("exchange_private_api_capability"),
    )
    if any(value is not False for value in forbidden):
        raise TheoryPaperError("paper experiment must have no live, credential, or private API capability")
    symbols = config.get("symbols")
    if not isinstance(symbols, list) or not symbols or len(symbols) != len(set(symbols)):
        raise TheoryPaperError("symbols must be a nonempty unique list")
    if int(config.get("duration_hours", 0)) != 72:
        raise TheoryPaperError("this experiment contract is fixed to 72 hours")
    if int(config.get("analysis_interval_hours", 0)) != 1:
        raise TheoryPaperError("analysis interval is fixed to one hour")
    if int(config.get("review_interval_hours", 0)) != 8:
        raise TheoryPaperError("review interval is fixed to eight hours")
    _clock_policy(config)
    scoring = config.get("scoring_policy")
    expected_theory_weights = {
        "measurement_chain": 20,
        "multiscale_roles": 15,
        "structural_position": 10,
        "phi_competition": 25,
        "actor_boundary": 15,
        "geometry_boundary": 15,
    }
    expected_method_weights = {
        "evidence_discipline": 20,
        "hypothesis_competition": 20,
        "falsification_discipline": 20,
        "geometry_and_risk": 20,
        "review_learning": 20,
    }
    if (
        not isinstance(scoring, Mapping)
        or scoring.get("theory_integrity_weights") != expected_theory_weights
        or scoring.get("method_practice_weights") != expected_method_weights
    ):
        raise TheoryPaperError("scoring policy does not match the frozen v0.1 scorers")
    return config


def _config_for_run(run_dir: Path) -> dict[str, Any]:
    config = _load_config(Path(run_dir) / "config.json")
    _verify_implementation_bindings(Path(run_dir))
    return config


def _hour_key(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")


def _cycle_name(number: int) -> str:
    return f"cycle-{number:04d}"


def _cycle_dir(run_dir: Path, number: int) -> Path:
    return Path(run_dir) / "cycles" / _cycle_name(number)


def _decision_path(run_dir: Path, number: int) -> Path:
    return _cycle_dir(run_dir, number) / "decision.json"


def _transaction_is_committed(root: Path, transaction_id: str) -> bool:
    prepare = Path(root) / "transactions" / f"{transaction_id}.prepare.json"
    commit = Path(root) / "transactions" / f"{transaction_id}.commit.json"
    return (
        prepare.exists()
        and commit.exists()
        and _ledger_transaction_event(Path(root), transaction_id) is not None
    )


def _verify_implementation_bindings(run_dir: Path) -> dict[str, Any]:
    """Fail closed if code, theory authority, guide, or prompt changed."""

    root = Path(run_dir)
    manifest = read_json(root / "manifest.json")
    config = read_json(root / "config.json")
    state = read_json(root / "state.json")
    config_digest = digest_json(config)
    if (
        manifest.get("config_digest") != config_digest
        or state.get("config_digest") != config_digest
        or manifest.get("run_id") != state.get("run_id")
        or manifest.get("started_at") != state.get("started_at")
        or manifest.get("ends_at") != state.get("ends_at")
        or manifest.get("symbols") != config.get("symbols")
        or state.get("manifest_digest") != digest_json(manifest)
    ):
        raise TheoryPaperError("run manifest, config, and state bindings disagree")
    bindings = manifest.get("implementation_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise TheoryPaperError("run manifest has no implementation bindings")
    package_root = Path(__file__).resolve().parent
    expected = {
        "common.py",
        "market.py",
        "theory.py",
        "portfolio.py",
        "experiment.py",
    }
    observed_names: set[str] = set()
    mismatches: list[str] = []
    for raw in bindings:
        if not isinstance(raw, Mapping):
            raise TheoryPaperError("implementation binding must be an object")
        name = str(raw.get("path") or "")
        if name not in expected or name in observed_names:
            raise TheoryPaperError("implementation bindings contain an unexpected path")
        observed_names.add(name)
        path = package_root / name
        if (
            not path.is_file()
            or raw.get("sha256") != sha256_file(path)
            or raw.get("size_bytes") != path.stat().st_size
        ):
            mismatches.append(name)
    if observed_names != expected:
        raise TheoryPaperError("implementation bindings are incomplete")
    if mismatches:
        raise TheoryPaperError(
            "experiment implementation drift: " + ",".join(sorted(mismatches))
        )
    authority_bindings = manifest.get("authority_bindings")
    if not isinstance(authority_bindings, list):
        raise TheoryPaperError("run manifest has no authority bindings")
    authority_expected = set(AUTHORITY_BINDING_PATHS)
    authority_observed: set[str] = set()
    authority_mismatches: list[str] = []
    project_root = _project_root()
    for raw in authority_bindings:
        if not isinstance(raw, Mapping):
            raise TheoryPaperError("authority binding must be an object")
        relative = str(raw.get("path") or "")
        if relative not in authority_expected or relative in authority_observed:
            raise TheoryPaperError("authority bindings contain an unexpected path")
        authority_observed.add(relative)
        path = project_root / relative
        if (
            not path.is_file()
            or raw.get("sha256") != sha256_file(path)
            or raw.get("size_bytes") != path.stat().st_size
        ):
            authority_mismatches.append(relative)
    if authority_observed != authority_expected:
        raise TheoryPaperError("authority bindings are incomplete")
    if authority_mismatches:
        raise TheoryPaperError(
            "experiment theory or prompt drift: "
            + ",".join(sorted(authority_mismatches))
        )
    return {
        "valid": True,
        "paths": sorted(observed_names),
        "authority_paths": sorted(authority_observed),
    }


def _ledger_transaction_event(root: Path, transaction_id: str) -> dict[str, Any] | None:
    ledger = Path(root) / "ledger.ndjson"
    if not ledger.exists():
        return None
    matches: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TheoryPaperError("ledger contains invalid JSON") from exc
            if (
                isinstance(event, dict)
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("transaction_id") == transaction_id
            ):
                matches.append(event)
    if len(matches) > 1:
        raise TheoryPaperError("ledger contains a duplicate transaction id")
    return matches[0] if matches else None


def _transaction_artifact_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise TheoryPaperError("transaction artifact path is required")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise TheoryPaperError("transaction artifact path must stay inside the run")
    target = (Path(root) / path).resolve()
    resolved_root = Path(root).resolve()
    if resolved_root not in target.parents:
        raise TheoryPaperError("transaction artifact escapes the run directory")
    return target


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        if digest_json(read_json(path)) != digest_json(value):
            raise TheoryPaperError(f"transaction artifact mismatch: {path}")
        return
    write_new_json(path, value)


def _apply_prepared_transaction(root: Path, prepared: Mapping[str, Any]) -> dict[str, Any]:
    """Idempotently finish a prepared multi-file state transition."""

    transaction_id = str(prepared.get("transaction_id") or "")
    if not transaction_id:
        raise TheoryPaperError("prepared transaction has no id")
    artifacts = prepared.get("artifacts")
    post_state = prepared.get("post_state")
    ledger_event = prepared.get("ledger_event")
    if not isinstance(artifacts, list) or not isinstance(post_state, Mapping):
        raise TheoryPaperError("prepared transaction payload is incomplete")
    if not isinstance(ledger_event, Mapping):
        raise TheoryPaperError("prepared transaction ledger event is missing")
    state_path = Path(root) / "state.json"
    pre_digest = prepared.get("pre_state_digest")
    post_digest = digest_json(post_state)
    current_digest = digest_json(read_json(state_path)) if state_path.exists() else None
    if current_digest not in {pre_digest, post_digest}:
        raise TheoryPaperError(
            "prepared transaction cannot overwrite an unrelated state"
        )
    for artifact in artifacts:
        if not isinstance(artifact, Mapping) or not isinstance(
            artifact.get("value"), Mapping
        ):
            raise TheoryPaperError("prepared transaction artifact is invalid")
        _write_or_verify_json(
            _transaction_artifact_path(root, artifact.get("path")),
            artifact["value"],
        )
    if current_digest != post_digest:
        write_atomic_json(state_path, post_state)
    payload = dict(ledger_event.get("payload") or {})
    payload["transaction_id"] = transaction_id
    existing = _ledger_transaction_event(Path(root), transaction_id)
    if existing is None:
        append_ledger_event(
            Path(root),
            str(ledger_event.get("event_type") or ""),
            payload,
            observed_at=str(ledger_event.get("observed_at") or ""),
        )
    elif (
        existing.get("event_type") != ledger_event.get("event_type")
        or existing.get("observed_at") != ledger_event.get("observed_at")
        or existing.get("payload") != payload
    ):
        raise TheoryPaperError("ledger transaction event does not match preparation")
    commit = {
        "schema_version": "theory-paper-transaction-commit.v1",
        "transaction_id": transaction_id,
        "prepared_digest": digest_json(prepared),
        "pre_state_digest": prepared.get("pre_state_digest"),
        "post_state_digest": digest_json(post_state),
        "artifact_digests": {
            str(item["path"]): digest_json(item["value"]) for item in artifacts
        },
        "ledger_event_type": ledger_event.get("event_type"),
    }
    _write_or_verify_json(
        Path(root) / "transactions" / f"{transaction_id}.commit.json",
        commit,
    )
    return commit


def _commit_transaction(
    root: Path,
    *,
    transaction_id: str,
    post_state: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    event_type: str,
    event_payload: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    prepared = {
        "schema_version": "theory-paper-transaction-prepare.v1",
        "transaction_id": transaction_id,
        "pre_state_digest": (
            digest_json(read_json(Path(root) / "state.json"))
            if (Path(root) / "state.json").exists()
            else None
        ),
        "post_state": copy.deepcopy(dict(post_state)),
        "artifacts": copy.deepcopy(list(artifacts)),
        "ledger_event": {
            "event_type": event_type,
            "observed_at": observed_at,
            "payload": copy.deepcopy(dict(event_payload)),
        },
    }
    path = Path(root) / "transactions" / f"{transaction_id}.prepare.json"
    _write_or_verify_json(path, prepared)
    return _apply_prepared_transaction(Path(root), prepared)


def _recover_pending_transactions(root: Path) -> list[str]:
    recovered: list[str] = []
    directory = Path(root) / "transactions"
    if not directory.exists():
        return recovered
    for path in sorted(directory.glob("*.prepare.json")):
        transaction_id = path.name[: -len(".prepare.json")]
        commit = directory / f"{transaction_id}.commit.json"
        if commit.exists():
            continue
        _apply_prepared_transaction(Path(root), read_json(path))
        recovered.append(transaction_id)
    return recovered


def _verify_latest_transaction_state(root: Path) -> dict[str, Any]:
    ledger = Path(root) / "ledger.ndjson"
    verify_ledger(Path(root))
    transaction_events: list[dict[str, Any]] = []
    if ledger.exists():
        with ledger.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TheoryPaperError("ledger contains invalid JSON") from exc
                if (
                    isinstance(event, dict)
                    and isinstance(event.get("payload"), dict)
                    and event["payload"].get("transaction_id")
                ):
                    transaction_events.append(event)
    prior_post_digest: str | None = None
    ledger_transaction_ids: list[str] = []
    for event in transaction_events:
        transaction_id = str(event["payload"]["transaction_id"])
        if transaction_id in ledger_transaction_ids:
            raise TheoryPaperError("ledger contains a duplicate transaction id")
        ledger_transaction_ids.append(transaction_id)
        prepare_path = (
            Path(root) / "transactions" / f"{transaction_id}.prepare.json"
        )
        commit_path = (
            Path(root) / "transactions" / f"{transaction_id}.commit.json"
        )
        if not prepare_path.exists() or not commit_path.exists():
            raise TheoryPaperError("ledger transaction is missing prepare or commit")
        prepared = read_json(prepare_path)
        commit = read_json(commit_path)
        if (
            prepared.get("transaction_id") != transaction_id
            or commit.get("transaction_id") != transaction_id
            or
            commit.get("prepared_digest") != digest_json(prepared)
            or commit.get("pre_state_digest") != prepared.get("pre_state_digest")
            or commit.get("post_state_digest")
            != digest_json(prepared.get("post_state"))
        ):
            raise TheoryPaperError("transaction prepare/commit digest mismatch")
        if (
            prior_post_digest is not None
            and prepared.get("pre_state_digest") != prior_post_digest
        ):
            raise TheoryPaperError("transaction state digest chain is discontinuous")
        prior_post_digest = str(commit.get("post_state_digest"))
        prepared_ledger = prepared.get("ledger_event")
        prepared_ledger = (
            prepared_ledger if isinstance(prepared_ledger, Mapping) else {}
        )
        expected_payload = dict(prepared_ledger.get("payload") or {})
        expected_payload["transaction_id"] = transaction_id
        ledger_event = prepared_ledger
        if (
            event.get("event_type") != ledger_event.get("event_type")
            or event.get("observed_at") != ledger_event.get("observed_at")
            or event.get("payload") != expected_payload
        ):
            raise TheoryPaperError("transaction ledger event disagrees with preparation")
        artifact_digests = commit.get("artifact_digests")
        if not isinstance(artifact_digests, Mapping):
            raise TheoryPaperError("transaction commit has no artifact digests")
        prepared_artifact_digests = {
            str(item.get("path")): digest_json(item.get("value"))
            for item in prepared.get("artifacts", [])
            if isinstance(item, Mapping)
        }
        if artifact_digests != prepared_artifact_digests:
            raise TheoryPaperError("transaction artifact set disagrees with preparation")
        for relative, expected_digest in artifact_digests.items():
            target = _transaction_artifact_path(Path(root), relative)
            if not target.exists() or digest_json(read_json(target)) != expected_digest:
                raise TheoryPaperError("transaction artifact digest mismatch")
    transaction_dir = Path(root) / "transactions"
    committed_ids = {
        path.name[: -len(".commit.json")]
        for path in transaction_dir.glob("*.commit.json")
    } if transaction_dir.exists() else set()
    if committed_ids != set(ledger_transaction_ids):
        raise TheoryPaperError("commit receipts and ledger transactions disagree")
    if not ledger_transaction_ids or ledger_transaction_ids[0] != "experiment-initialize":
        raise TheoryPaperError("transaction chain has no initialization anchor")
    initialization = read_json(
        Path(root) / "transactions" / "experiment-initialize.prepare.json"
    )
    if initialization.get("pre_state_digest") is not None:
        raise TheoryPaperError("initialization transaction must start from no state")
    state_digest = digest_json(read_json(Path(root) / "state.json"))
    if prior_post_digest is not None and prior_post_digest != state_digest:
        raise TheoryPaperError("current state does not match the latest transaction")
    return {
        "valid": True,
        "transaction_count": len(transaction_events),
        "latest_transaction_id": (
            ledger_transaction_ids[-1] if ledger_transaction_ids else None
        ),
        "post_state_digest": state_digest,
    }


def _extract_marks(market: Mapping[str, Any]) -> dict[str, float]:
    marks: dict[str, float] = {}
    for item in market.get("symbols", []):
        if not isinstance(item, dict):
            continue
        measures = item.get("measures")
        if not isinstance(measures, dict):
            continue
        try:
            marks[str(item["symbol"])] = float(measures["price"])
        except (KeyError, TypeError, ValueError):
            continue
    return marks


def _build_sealed_chaos_schedule(
    config: Mapping[str, Any],
    *,
    started_at: datetime,
) -> tuple[dict[str, Any], str]:
    policy = config.get("chaos_policy", {})
    if not isinstance(policy, dict) or not policy.get("enabled"):
        schedule = {"schema_version": "theory-paper-chaos-schedule.v1", "seed": "", "events": []}
        return schedule, digest_json(schedule)
    windows = policy.get("eligible_offset_hour_windows")
    symbols = config.get("symbols")
    if not isinstance(windows, list) or not isinstance(symbols, list):
        raise TheoryPaperError("chaos policy windows and symbols are required")
    count = int(policy.get("auto_injection_count", 0))
    if count != len(windows):
        raise TheoryPaperError("one sealed chaos window is required per auto injection")
    seed = secrets.token_hex(32)
    generator = random.Random(int(seed, 16))
    events: list[dict[str, Any]] = []
    minimum = float(policy.get("notional_min_usdt", 100.0))
    maximum = float(policy.get("notional_max_usdt", 250.0))
    for index, raw_window in enumerate(windows, start=1):
        if not isinstance(raw_window, list) or len(raw_window) != 2:
            raise TheoryPaperError("invalid chaos offset window")
        lower, upper = int(raw_window[0]), int(raw_window[1])
        offset = generator.randint(lower * 60, upper * 60) / 60.0
        notional = round(generator.uniform(minimum, maximum), 2)
        events.append(
            {
                "chaos_id": f"chaos-auto-{index:02d}",
                "due_at": iso_utc(started_at + timedelta(hours=offset)),
                "symbol": generator.choice(symbols),
                "side": generator.choice(["BUY", "SELL"]),
                "notional_usdt": notional,
                "origin": "EXOGENOUS_EMOTION_INJECTION",
                "strategy_entry_attribution": "NONE",
                "state": "SEALED_PENDING",
            }
        )
    schedule = {
        "schema_version": "theory-paper-chaos-schedule.v1",
        "seed": seed,
        "created_at": iso_utc(started_at),
        "events": events,
    }
    return schedule, digest_json(schedule)


def initialize_experiment(
    config_path: Path,
    run_dir: Path,
    *,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Initialize one local run and seal future chaos timing from analysis."""
    root = Path(run_dir)
    config = _load_config(Path(config_path))
    config_digest = digest_json(config)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with experiment_lock(root):
        state_path = root / "state.json"
        initialization_prepare = (
            root / "transactions" / "experiment-initialize.prepare.json"
        )
        if initialization_prepare.exists() and not state_path.exists():
            _apply_prepared_transaction(root, read_json(initialization_prepare))
        if state_path.exists():
            state = read_json(state_path)
            if state.get("config_digest") != config_digest:
                raise TheoryPaperError("existing run uses a different config")
            _recover_pending_transactions(root)
            _config_for_run(root)
            _verify_latest_transaction_state(root)
            return {
                "initialized": False,
                "reason": "ALREADY_INITIALIZED",
                "run_id": state["run_id"],
                "run_dir": str(root.resolve()),
            }
        unexpected = [
            path.name
            for path in root.iterdir()
            if path.name != ".experiment.lock"
        ]
        if unexpected:
            raise TheoryPaperError(
                "run directory exists and is not an initialized experiment"
            )

        start = started_at or datetime.now(timezone.utc)
        if start.tzinfo is None:
            raise TheoryPaperError("started_at must be timezone aware")
        start = start.astimezone(timezone.utc)
        _require_wall_clock(config, start, "experiment start")
        run_id = (
            "msta-paper-"
            + start.strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + secrets.token_hex(4)
        )
        schedule, chaos_commitment = _build_sealed_chaos_schedule(
            config,
            started_at=start,
        )
        portfolio_config = dict(config)
        portfolio_config["chaos_schedule"] = [
            {
                "chaos_id": item["chaos_id"],
                "due_at": item["due_at"],
                "symbol": item["symbol"],
                "side": item["side"],
                "notional_usdt": item["notional_usdt"],
                "stop_distance_fraction": 0.02,
                "target_distance_fraction": 0.04,
            }
            for item in schedule["events"]
        ]
        portfolio = initialize_portfolio(portfolio_config, iso_utc(start))
        clock_mode, _ = _clock_policy(config)
        state: dict[str, Any] = {
            "schema_version": "theory-paper-run-state.v1",
            "run_id": run_id,
            "status": "ACTIVE",
            "clock_mode": clock_mode,
            "started_at": iso_utc(start),
            "ends_at": iso_utc(
                start + timedelta(hours=int(config["duration_hours"]))
            ),
            "config_digest": config_digest,
            "cycle_count": 0,
            "last_cycle_hour": None,
            "expected_hour_slots": [
                _hour_key(start + timedelta(hours=offset))
                for offset in range(int(config["duration_hours"]))
            ],
            "completed_hour_slots": [],
            "last_review_cycle": 0,
            "review_count": 0,
            "pending_decision_cycle": None,
            "valid_hours_without_strategy_fill": 0,
            "open_hypotheses": [],
            "active_method_delta": None,
            "method_delta_history": [],
            "chaos_commitment": chaos_commitment,
            "chaos_blinding_status": "BLINDING_NOT_ENFORCED_SAME_PRINCIPAL",
            "portfolio": portfolio,
        }
        package_root = Path(__file__).resolve().parent
        implementation_bindings = [
            _file_binding(path, path.name)
            for path in (
                package_root / "common.py",
                package_root / "market.py",
                package_root / "theory.py",
                package_root / "portfolio.py",
                package_root / "experiment.py",
            )
        ]
        project_root = _project_root()
        authority_bindings = [
            _file_binding(project_root / relative, relative)
            for relative in AUTHORITY_BINDING_PATHS
        ]
        manifest = {
            "schema_version": "theory-paper-run-manifest.v1",
            "run_id": run_id,
            "status": config["status"],
            "clock_mode": clock_mode,
            "started_at": state["started_at"],
            "ends_at": state["ends_at"],
            "config_digest": config_digest,
            "chaos_schedule_commitment": chaos_commitment,
            "chaos_blinding_status": state["chaos_blinding_status"],
            "symbols": config["symbols"],
            "authority_boundary": config["authority_boundary"],
            "implementation_bindings": implementation_bindings,
            "authority_bindings": authority_bindings,
            "automation_prompt_path": "config/theory_paper_automation_prompt.v1.md",
            "runtime_directory_is_git_ignored": True,
        }
        state["manifest_digest"] = digest_json(manifest)
        initial_state_digest = digest_json(state)
        _commit_transaction(
            root,
            transaction_id="experiment-initialize",
            post_state=state,
            artifacts=[
                {"path": "config.json", "value": config},
                {"path": "manifest.json", "value": manifest},
                {"path": ".sealed-chaos.json", "value": schedule},
            ],
            event_type="EXPERIMENT_INITIALIZED",
            event_payload={
                "run_id": run_id,
                "config_digest": config_digest,
                "manifest_digest": state["manifest_digest"],
                "initial_state_digest": initial_state_digest,
                "chaos_schedule_commitment": chaos_commitment,
                "portfolio_digest": digest_json(portfolio),
                "clock_mode": clock_mode,
            },
            observed_at=state["started_at"],
        )
        _verify_latest_transaction_state(root)
        return {
            "initialized": True,
            "run_id": run_id,
            "run_dir": str(root.resolve()),
            "started_at": state["started_at"],
            "ends_at": state["ends_at"],
            "symbols": config["symbols"],
            "paper_only": True,
            "clock_mode": clock_mode,
            "chaos_schedule_commitment": chaos_commitment,
            "chaos_blinding_status": state["chaos_blinding_status"],
        }


def run_hourly_cycle(
    run_dir: Path,
    *,
    decision_at: datetime | None = None,
    market_snapshot: dict[str, Any] | None = None,
    news_snapshot: dict[str, Any] | None = None,
    market_fetcher: MarketFetcher = fetch_market_snapshot,
    news_fetcher: NewsFetcher = fetch_news_headlines,
) -> dict[str, Any]:
    """Freeze one PIT packet and open a separately submitted agent decision."""
    root = Path(run_dir)
    requested_at = (decision_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with experiment_lock(root):
        config = _config_for_run(root)
        _require_wall_clock(config, requested_at, "cycle time")
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        state = read_json(root / "state.json")
        if state.get("status") != "ACTIVE":
            raise TheoryPaperError("experiment is not active")
        if requested_at < parse_utc(state["started_at"]):
            raise TheoryPaperError("cycle time cannot precede experiment start")
        if requested_at > parse_utc(state["ends_at"]):
            raise TheoryPaperError("cycle time is after the 72-hour experiment window")
        if state.get("pending_decision_cycle") is not None:
            pending = int(state["pending_decision_cycle"])
            return {
                "created": False,
                "reason": "PRIOR_DECISION_REQUIRED",
                "cycle_id": _cycle_name(pending),
                "analysis_path": str((_cycle_dir(root, pending) / "analysis.json").resolve()),
                "decision_template_path": str((_cycle_dir(root, pending) / "decision-template.json").resolve()),
            }
        hour = _hour_key(requested_at)
        expected_slots = state.get("expected_hour_slots")
        if not isinstance(expected_slots, list) or hour not in expected_slots:
            raise TheoryPaperError("cycle is outside the frozen hourly slot schedule")
        if state.get("last_cycle_hour") == hour:
            number = int(state["cycle_count"])
            return {
                "created": False,
                "reason": "IDEMPOTENT_HOUR_ALREADY_CREATED",
                "cycle_id": _cycle_name(number),
                "analysis_path": str((_cycle_dir(root, number) / "analysis.json").resolve()),
            }
        number = int(state["cycle_count"]) + 1
        cycle_id = _cycle_name(number)
        cycle_root = _cycle_dir(root, number)
        if cycle_root.exists():
            raise TheoryPaperError("cycle directory exists without committed run state")

        market = market_snapshot or market_fetcher(
            config["symbols"],
            client=BinancePublicClient(),
            observed_at=requested_at,
        )
        news = news_snapshot or news_fetcher(config["data_policy"]["news_queries"])
        now = (
            requested_at
            if decision_at is not None
            else datetime.now(timezone.utc)
        )
        _require_wall_clock(config, now, "cycle completion time")
        hour = _hour_key(now)
        if now > parse_utc(state["ends_at"]) or hour not in expected_slots:
            raise TheoryPaperError("data collection crossed the frozen experiment window")
        if state.get("last_cycle_hour") == hour:
            number = int(state["cycle_count"])
            return {
                "created": False,
                "reason": "IDEMPOTENT_HOUR_ALREADY_CREATED",
                "cycle_id": _cycle_name(number),
                "analysis_path": str((_cycle_dir(root, number) / "analysis.json").resolve()),
            }
        prior_update = state.get("portfolio", {}).get("updated_at")
        if isinstance(prior_update, str) and now < parse_utc(prior_update):
            raise TheoryPaperError("cycle time cannot precede the portfolio state")
        for label, packet in (("market", market), ("news", news)):
            observed = packet.get("observed_at") if isinstance(packet, Mapping) else None
            if isinstance(observed, str) and parse_utc(observed) > now:
                raise TheoryPaperError(f"{label} snapshot is from the future")
        marks = _extract_marks(market)
        if not marks:
            raise TheoryPaperError("cycle has no usable market marks")

        next_state = copy.deepcopy(state)
        portfolio = next_state["portfolio"]
        market_execution = process_market_bars(portfolio, market, iso_utc(now))
        chaos_execution = inject_due_chaos(portfolio, market, iso_utc(now))
        analysis_portfolio = json.loads(json.dumps(portfolio))
        analysis_portfolio["chaos"] = {
            "future_schedule_hidden": True,
            "schedule_commitment": next_state["chaos_commitment"],
            "manual_injection_count": portfolio.get("chaos", {}).get("manual_injection_count", 0),
            "executed_or_rejected_count": sum(
                1
                for item in portfolio.get("chaos", {}).get("schedule", [])
                if item.get("state") != "SEALED"
            ),
        }
        analysis_portfolio["experiment_activity"] = {
            "valid_hours_without_strategy_fill": int(
                state["valid_hours_without_strategy_fill"]
            ),
            "probe_threshold_hours": int(
                config["activity_policy"]["valid_hours_without_strategy_fill_before_probe"]
            ),
        }
        analysis_portfolio["valid_hours_without_strategy_fill"] = int(
            state["valid_hours_without_strategy_fill"]
        )
        analysis_config = copy.deepcopy(config)
        active_method_delta = state.get("active_method_delta")
        analysis_config["active_method_delta"] = (
            {
                "id": str(active_method_delta.get("method_delta_id")),
                "version": str(active_method_delta.get("version")),
                "effective_cycle": cycle_id,
                "proposed_method_delta": str(
                    active_method_delta.get("proposed_method_delta")
                ),
                "falsification_test": str(
                    active_method_delta.get("falsification_test")
                ),
            }
            if isinstance(active_method_delta, Mapping)
            else None
        )
        run_manifest = read_json(root / "manifest.json")
        authority_bindings = run_manifest.get("authority_bindings", [])
        prompt_binding = next(
            (
                item
                for item in authority_bindings
                if isinstance(item, Mapping)
                and item.get("path")
                == "config/theory_paper_automation_prompt.v1.md"
            ),
            {},
        )
        analysis_config["decision_authority"] = {
            "path": prompt_binding.get("path"),
            "automation_prompt_sha256": prompt_binding.get("sha256"),
            "theory_authority_digest": digest_json(authority_bindings),
        }
        analysis = build_cycle_analysis(
            market,
            news,
            analysis_portfolio,
            analysis_config,
            cycle_id=cycle_id,
            decision_at=iso_utc(now),
        )
        template = build_decision_template(analysis)
        quality_valid = len(market.get("failures", {})) == 0
        next_state["portfolio"] = portfolio
        next_state["cycle_count"] = number
        next_state["last_cycle_hour"] = hour
        completed_slots = next_state.setdefault("completed_hour_slots", [])
        if hour in completed_slots:
            raise TheoryPaperError("hourly slot was already completed")
        completed_slots.append(hour)
        next_state["pending_decision_cycle"] = number
        if quality_valid:
            next_state["valid_hours_without_strategy_fill"] = int(
                next_state["valid_hours_without_strategy_fill"]
            ) + 1
        event_payload = {
            "cycle_id": cycle_id,
            "market_digest": market.get("market_snapshot_digest", digest_json(market)),
            "news_digest": digest_json(news),
            "analysis_digest": digest_json(analysis),
            "portfolio_digest": digest_json(portfolio),
            "market_execution_digest": digest_json(market_execution),
            "chaos_execution_digest": digest_json(chaos_execution),
        }
        _commit_transaction(
            root,
            transaction_id=f"{cycle_id}-analysis",
            post_state=next_state,
            artifacts=[
                {"path": f"cycles/{cycle_id}/market.json", "value": market},
                {"path": f"cycles/{cycle_id}/news.json", "value": news},
                {
                    "path": f"cycles/{cycle_id}/market-execution.json",
                    "value": market_execution,
                },
                {
                    "path": f"cycles/{cycle_id}/chaos-execution.json",
                    "value": chaos_execution,
                },
                {"path": f"cycles/{cycle_id}/analysis.json", "value": analysis},
                {
                    "path": f"cycles/{cycle_id}/decision-template.json",
                    "value": template,
                },
            ],
            event_type="HOURLY_ANALYSIS_FROZEN",
            event_payload=event_payload,
            observed_at=iso_utc(now),
        )
        return {
            "created": True,
            "cycle_id": cycle_id,
            "decision_at": iso_utc(now),
            "symbols_observed": sorted(marks),
            "market_failures": market.get("failures", {}),
            "analysis_path": str((cycle_root / "analysis.json").resolve()),
            "decision_template_path": str((cycle_root / "decision-template.json").resolve()),
            "decision_required": True,
            "review_due_after_submit": number - int(next_state["last_review_cycle"]) >= int(config["review_interval_hours"]),
        }


def submit_agent_decision(
    run_dir: Path,
    decision: Mapping[str, Any] | Path | None = None,
    *,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate an agent decision, apply it only to paper state, and seal a receipt."""
    root = Path(run_dir)
    now = (decided_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with experiment_lock(root):
        config = _config_for_run(root)
        _require_wall_clock(config, now, "decision time")
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        state = read_json(root / "state.json")
        if state.get("status") != "ACTIVE":
            raise TheoryPaperError("experiment is not active")
        pending = state.get("pending_decision_cycle")
        if pending is None:
            latest = int(state.get("cycle_count", 0))
            existing_latest = _decision_path(root, latest) if latest else None
            if existing_latest is not None and existing_latest.exists():
                transaction_id = f"{_cycle_name(latest)}-decision"
                if not _transaction_is_committed(root, transaction_id):
                    raise TheoryPaperError(
                        "decision artifact exists without a committed transaction"
                    )
                return read_json(existing_latest)
            raise TheoryPaperError("there is no pending agent decision")
        number = int(pending)
        existing = _decision_path(root, number)
        if existing.exists():
            raise TheoryPaperError(
                "pending decision path was preoccupied without a committed state transition"
            )
        cycle_root = _cycle_dir(root, number)
        analysis = read_json(cycle_root / "analysis.json")
        market = read_json(cycle_root / "market.json")
        if decision is None:
            supplied = read_json(cycle_root / "decision-template.json")
        elif isinstance(decision, (str, Path)):
            supplied = read_json(Path(decision))
        else:
            supplied = dict(decision)
        validation = validate_decision(supplied, analysis, config)
        if not validation.get("valid"):
            raise TheoryPaperError(
                "agent decision rejected: " + "; ".join(validation.get("errors", []))
            )
        validated = validation["normalized_decision"]
        if now < parse_utc(str(analysis.get("decision_at"))):
            raise TheoryPaperError("decision time cannot precede the frozen analysis")
        prior_update = state.get("portfolio", {}).get("updated_at")
        if isinstance(prior_update, str) and now < parse_utc(prior_update):
            raise TheoryPaperError("decision time cannot precede the portfolio state")
        next_state = copy.deepcopy(state)
        execution = submit_actions(
            next_state["portfolio"],
            validated.get("actions", []),
            market,
            iso_utc(now),
        )
        rejected = [
            item
            for item in execution.get("results", [])
            if item.get("status") == "REJECTED"
        ]
        if rejected:
            raise TheoryPaperError(
                "paper portfolio action rejected; transaction rolled back: "
                + "; ".join(str(item.get("reason")) for item in rejected)
            )
        overdue_unprotected = [
            lot["lot_id"]
            for lot in next_state["portfolio"].get("lots", [])
            if isinstance(lot, Mapping)
            and lot.get("status") == "OPEN"
            and (
                lot.get("stop_price") is None
                or lot.get("target_price") is None
            )
            and isinstance(lot.get("legacy_protection_grace_through_cycle"), int)
            and number >= int(lot["legacy_protection_grace_through_cycle"])
        ]
        if overdue_unprotected:
            raise TheoryPaperError(
                "initial position protection SLA failed; transaction rolled back: "
                + ",".join(sorted(overdue_unprotected))
            )
        order_review_sla = int(
            config.get("initial_portfolio", {}).get(
                "initial_position_protection_sla_cycles",
                1,
            )
        )
        unresolved_initial_orders = [
            order["order_id"]
            for order in next_state["portfolio"].get("orders", [])
            if isinstance(order, Mapping)
            and order.get("origin") == "USER_INITIAL_PLAN"
            and order.get("state") == "REVIEW_REQUIRED"
            and number >= order_review_sla
        ]
        if unresolved_initial_orders:
            raise TheoryPaperError(
                "initial order review SLA failed; transaction rolled back: "
                + ",".join(sorted(unresolved_initial_orders))
            )
        strategy_fills = int(execution.get("strategy_fill_count", 0))
        orchestration_gate = _mapping(validated.get("orchestration_gate"))
        executed_new_risk_symbols = orchestration_gate.get(
            "executed_new_risk_symbols",
            [],
        )
        if strategy_fills or (
            isinstance(executed_new_risk_symbols, list)
            and bool(executed_new_risk_symbols)
        ):
            next_state["valid_hours_without_strategy_fill"] = 0
        open_hypotheses = next_state.setdefault("open_hypotheses", [])
        for symbol_decision in validated.get("symbol_decisions", []):
            if not isinstance(symbol_decision, Mapping):
                continue
            instance = {
                "hypothesis_instance_id": (
                    f"{_cycle_name(number)}:{symbol_decision.get('symbol')}"
                ),
                "cycle_id": _cycle_name(number),
                "decision_at": validated.get("decision_at"),
                "symbol_decision": copy.deepcopy(dict(symbol_decision)),
            }
            if not any(
                item.get("hypothesis_instance_id")
                == instance["hypothesis_instance_id"]
                for item in open_hypotheses
                if isinstance(item, Mapping)
            ):
                open_hypotheses.append(instance)
        receipt = {
            "schema_version": "theory-paper-decision-receipt.v1",
            "cycle_id": _cycle_name(number),
            "decided_at": iso_utc(now),
            "paper_only": True,
            "analysis_digest": digest_json(analysis),
            "validated_decision": validated,
            "validation_warnings": validation.get("warnings", []),
            "execution": execution,
            "portfolio_metrics": portfolio_metrics(next_state["portfolio"], _extract_marks(market)),
            "portfolio_digest_after": digest_json(next_state["portfolio"]),
        }
        receipt["decision_receipt_digest"] = digest_json(receipt)
        next_state["pending_decision_cycle"] = None
        event_payload = {
            "cycle_id": receipt["cycle_id"],
            "decision_receipt_digest": receipt["decision_receipt_digest"],
            "portfolio_digest_after": receipt["portfolio_digest_after"],
            "strategy_fill_count": strategy_fills,
            "executed_new_risk_symbols": copy.deepcopy(
                executed_new_risk_symbols
            ),
        }
        _commit_transaction(
            root,
            transaction_id=f"{_cycle_name(number)}-decision",
            post_state=next_state,
            artifacts=[
                {
                    "path": f"cycles/{_cycle_name(number)}/decision.json",
                    "value": receipt,
                }
            ],
            event_type="AGENT_DECISION_APPLIED",
            event_payload=event_payload,
            observed_at=iso_utc(now),
        )
        return receipt


def _symbol_analysis_by_name(
    analysis: Mapping[str, Any],
    symbol: str,
) -> Mapping[str, Any] | None:
    for item in analysis.get("symbols", []):
        if isinstance(item, Mapping) and item.get("symbol") == symbol:
            return item
    return None


def _role_direction(symbol_analysis: Mapping[str, Any], timeframe: str) -> Any:
    belief = symbol_analysis.get("multi_scale_state_belief")
    roles = belief.get("role_states") if isinstance(belief, Mapping) else None
    if not isinstance(roles, list):
        return None
    for item in roles:
        if isinstance(item, Mapping) and item.get("timeframe") == timeframe:
            return item.get("direction_state")
    return None


def _observable_value(symbol_analysis: Mapping[str, Any], observable_id: str) -> Any:
    measurement = symbol_analysis.get("measurement_snapshot")
    measurement = measurement if isinstance(measurement, Mapping) else {}
    axes = measurement.get("axes")
    axes = axes if isinstance(axes, Mapping) else {}
    structural = symbol_analysis.get("structural_position")
    structural = structural if isinstance(structural, Mapping) else {}
    lookup = {
        "REFERENCE_PRICE": measurement.get("reference_price"),
        "D_SIGNED_TAKER_IMBALANCE": (
            axes.get("D", {}).get("observations", {}).get("signed_taker_imbalance")
            if isinstance(axes.get("D"), Mapping)
            else None
        ),
        "D_HOURLY_TAKER_BUY_SELL_RATIO": (
            axes.get("D", {}).get("observations", {}).get(
                "hourly_taker_buy_sell_ratio"
            )
            if isinstance(axes.get("D"), Mapping)
            else None
        ),
        "L_OI_VALUE_1H_CHANGE_PCT": (
            axes.get("L", {}).get("observations", {}).get(
                "open_interest_value_1h_change_pct"
            )
            if isinstance(axes.get("L"), Mapping)
            else None
        ),
        "C_FUNDING_RATE": (
            axes.get("C", {}).get("observations", {}).get("funding_rate")
            if isinstance(axes.get("C"), Mapping)
            else None
        ),
        "15M_DIRECTION": _role_direction(symbol_analysis, "15m"),
        "1H_DIRECTION": _role_direction(symbol_analysis, "1h"),
        "4H_DIRECTION": _role_direction(symbol_analysis, "4h"),
        "1D_DIRECTION": _role_direction(symbol_analysis, "1d"),
        "OPERATIONAL_PHASE": structural.get("operational_phase"),
        "LOCATION_STAGE": structural.get("location_stage"),
    }
    value = lookup.get(observable_id)
    return None if value in (None, "UNKNOWN") else value


def _evaluate_predicate(
    predicate: Mapping[str, Any],
    symbol_analysis: Mapping[str, Any],
) -> tuple[bool | None, Any]:
    observed = _observable_value(
        symbol_analysis,
        str(predicate.get("observable_id") or ""),
    )
    if observed is None:
        return None, None
    expected = predicate.get("value")
    operator = predicate.get("operator")
    if operator in {"GT", "GTE", "LT", "LTE"}:
        try:
            left, right = float(observed), float(expected)
        except (TypeError, ValueError):
            return None, observed
        result = {
            "GT": left > right,
            "GTE": left >= right,
            "LT": left < right,
            "LTE": left <= right,
        }[str(operator)]
        return result, observed
    if operator == "EQ":
        return observed == expected, observed
    if operator == "NE":
        return observed != expected, observed
    return None, observed


def _hypothesis_assessments(
    symbol_decisions: Sequence[Mapping[str, Any]],
    evaluation_analyses: Sequence[Mapping[str, Any]],
    reviewed_at: datetime,
    decision_at: str,
) -> list[dict[str, Any]]:
    assessments: list[dict[str, Any]] = []
    for decision in symbol_decisions:
        symbol = str(decision.get("symbol") or "")
        expiry = parse_utc(str(decision.get("expiry_at")))
        observations: list[dict[str, Any]] = []
        support_match: dict[str, Any] | None = None
        falsifier_match: dict[str, Any] | None = None
        ambiguous_same_observation = False
        for evaluation_analysis in evaluation_analyses:
            evaluation_time = evaluation_analysis.get("decision_at")
            if (
                not isinstance(evaluation_time, str)
                or parse_utc(evaluation_time) <= parse_utc(decision_at)
                or parse_utc(evaluation_time) > reviewed_at
                or parse_utc(evaluation_time) > expiry
            ):
                continue
            evaluation = _symbol_analysis_by_name(evaluation_analysis, symbol)
            if not isinstance(evaluation, Mapping):
                continue
            support_result, support_observed = _evaluate_predicate(
                decision.get("support_predicate", {}),
                evaluation,
            )
            falsifier_result, falsifier_observed = _evaluate_predicate(
                decision.get("falsifier_predicate", {}),
                evaluation,
            )
            row = {
                "analysis_digest": evaluation_analysis.get("analysis_digest"),
                "observed_at": evaluation_time,
                "support_observed": support_observed,
                "support_matched": support_result,
                "falsifier_observed": falsifier_observed,
                "falsifier_matched": falsifier_result,
            }
            observations.append(row)
            if support_result is True and support_match is None:
                support_match = row
            if falsifier_result is True and falsifier_match is None:
                falsifier_match = row
            if support_result is True and falsifier_result is True:
                ambiguous_same_observation = True
        if falsifier_match is not None:
            status = "FALSIFIED"
        elif reviewed_at >= expiry and support_match is not None:
            status = "SUPPORTED_AT_EXPIRY"
        elif reviewed_at >= expiry:
            status = "EXPIRED_UNSUPPORTED"
        elif support_match is not None:
            status = "SUPPORTED_ACTIVE"
        else:
            status = "UNRESOLVED_UNKNOWN"
        assessments.append(
            {
                "symbol": symbol,
                "selected_phi_id": decision.get("selected_phi_id"),
                "status": status,
                "support_predicate": copy.deepcopy(decision.get("support_predicate")),
                "falsifier_predicate": copy.deepcopy(
                    decision.get("falsifier_predicate")
                ),
                "expiry_at": decision.get("expiry_at"),
                "observations": observations,
                "first_support_match": support_match,
                "first_falsifier_match": falsifier_match,
                "ambiguous_same_observation": ambiguous_same_observation,
                "thesis_unchanged": True,
            }
        )
    return assessments


def run_review(
    run_dir: Path,
    *,
    reviewed_at: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Score the latest closed window and freeze at most one primary method delta."""
    root = Path(run_dir)
    now = (reviewed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with experiment_lock(root):
        config = _config_for_run(root)
        _require_wall_clock(config, now, "review time")
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        state = read_json(root / "state.json")
        if state.get("status") != "ACTIVE":
            raise TheoryPaperError("experiment is not active")
        if state.get("pending_decision_cycle") is not None:
            raise TheoryPaperError("submit the pending decision before review")
        prior_update = state.get("portfolio", {}).get("updated_at")
        if isinstance(prior_update, str) and now < parse_utc(prior_update):
            raise TheoryPaperError("review time cannot precede the portfolio state")
        start_cycle = int(state["last_review_cycle"]) + 1
        required = int(config["review_interval_hours"])
        available = int(state["cycle_count"]) - int(state["last_review_cycle"])
        clock_mode, _ = _clock_policy(config)
        if force and clock_mode == LIVE_CLOCK and available < required:
            raise TheoryPaperError("live-clock review cannot force an incomplete window")
        if available < required and not force:
            return {
                "created": False,
                "reason": "REVIEW_NOT_DUE",
                "cycles_until_due": required - available,
            }
        end_cycle = (
            start_cycle + required - 1
            if available >= required
            else int(state["cycle_count"])
        )
        if end_cycle < start_cycle:
            latest_path = (
                root
                / "reviews"
                / f"review-{int(state.get('review_count', 0)):03d}.json"
            )
            if latest_path.exists():
                return {"created": False, "reason": "REVIEW_ALREADY_FROZEN", **read_json(latest_path)}
            raise TheoryPaperError("review window has no completed cycle")
        analyses: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        latest_market: dict[str, Any] = {}
        for number in range(start_cycle, end_cycle + 1):
            cycle_root = _cycle_dir(root, number)
            analyses.append(read_json(cycle_root / "analysis.json"))
            decisions.append(read_json(cycle_root / "decision.json"))
            latest_market = read_json(cycle_root / "market.json")
        if analyses and now < parse_utc(str(analyses[-1].get("decision_at"))):
            raise TheoryPaperError("review time cannot precede the review window")
        all_analyses = [
            read_json(_cycle_dir(root, number) / "analysis.json")
            for number in range(1, end_cycle + 1)
        ]
        practice_records: list[dict[str, Any]] = []
        cycle_scores: list[dict[str, Any]] = []
        for cycle_index, (analysis, receipt) in enumerate(zip(analyses, decisions)):
            normalized = receipt.get("validated_decision", {})
            symbol_decisions = normalized.get("symbol_decisions", [])
            action_types = [
                item.get("action")
                for item in symbol_decisions
                if isinstance(item, dict)
            ]
            issue_codes: list[str] = []
            integrity = analysis.get("theory_integrity_score", {})
            integrity_deductions = " ".join(integrity.get("deductions", []))
            if (
                analysis.get("failed_market_symbols") not in ({}, "UNKNOWN", None)
                or "MEASUREMENT" in integrity_deductions
            ):
                issue_codes.append("DATA_QUALITY")
            if any("PHI" in item for item in integrity.get("deductions", [])):
                issue_codes.append("PHI_COMPETITION")
            if receipt.get("portfolio_metrics", {}).get("unprotected_lot_ids"):
                issue_codes.append("RISK_DISCIPLINE")
            if action_types and all(
                action in {"KEEP", "ABSTAIN"} for action in action_types
            ):
                actionable = any(
                    item.get("market_actionability") == "ACTIONABLE"
                    for item in symbol_decisions
                    if isinstance(item, dict)
                )
                has_probe_plan = any(
                    item.get("active_probe_plan") is True
                    for item in symbol_decisions
                    if isinstance(item, dict)
                )
                if actionable and not has_probe_plan:
                    issue_codes.append("UNDERTRADING")
            execution_results = receipt.get("execution", {}).get("results", [])
            if any(item.get("status") == "REJECTED" for item in execution_results):
                issue_codes.append("EXECUTION")
            hypothesis_assessments = _hypothesis_assessments(
                [
                    item
                    for item in symbol_decisions
                    if isinstance(item, Mapping)
                ],
                analyses[cycle_index + 1 :],
                now,
                str(normalized.get("decision_at")),
            )
            lifecycle_statuses = {
                item["status"] for item in hypothesis_assessments
            }
            if "FALSIFIED" in lifecycle_statuses:
                lifecycle_status = "FALSIFIED"
            elif "SUPPORTED_AT_EXPIRY" in lifecycle_statuses:
                lifecycle_status = "SUPPORTED_AT_EXPIRY"
            elif (
                lifecycle_statuses
                and lifecycle_statuses == {"EXPIRED_UNSUPPORTED"}
            ):
                lifecycle_status = "EXPIRED_UNSUPPORTED"
            elif "SUPPORTED_ACTIVE" in lifecycle_statuses:
                lifecycle_status = "SUPPORTED_ACTIVE"
            else:
                lifecycle_status = "UNRESOLVED_UNKNOWN"
            method_observations = normalized.get("method_observations", [])
            method_observations = (
                copy.deepcopy(method_observations)
                if isinstance(method_observations, list)
                else []
            )
            assessment = {
                "hypothesis_status": lifecycle_status,
                "hypothesis_assessments": hypothesis_assessments,
                "method_issue_codes": sorted(set(issue_codes)),
                "evidence_refs": [
                    str(analysis.get("analysis_digest")),
                    str(receipt.get("decision_receipt_digest")),
                    *[
                        str(item.get("analysis_digest"))
                        for hypothesis in hypothesis_assessments
                        for item in hypothesis.get("observations", [])
                        if item.get("analysis_digest")
                    ],
                ],
                "method_observations": method_observations,
                "lesson": (
                    "Cycle discipline was evaluated from the frozen pre-action thesis, "
                    "machine-readable support and falsifier predicates, subsequent "
                    "closed observations, execution receipt, data gaps, and risk state; "
                    "the original thesis was not rewritten. "
                    + (
                        "Agent method notes: "
                        + " | ".join(str(item) for item in method_observations)
                        if method_observations
                        else "No additional agent method note was supplied."
                    )
                ),
                "posthoc_thesis_changed": False,
            }
            score_decision = {
                "execution_scope": "PAPER_ONLY",
                "symbol_decisions": symbol_decisions,
                "actions": normalized.get("actions", []),
            }
            practice_record = {
                "cycle_id": analysis.get("cycle_id"),
                "analysis": analysis,
                "decision": score_decision,
                "review": assessment,
            }
            practice_records.append(practice_record)
            cycle_scores.append(
                score_cycle(analysis, decision=score_decision, review=assessment)
            )

        def aggregate(key: str) -> dict[str, Any]:
            rows = [row[key] for row in cycle_scores if isinstance(row.get(key), dict)]
            numeric = [
                float(row["score"])
                for row in rows
                if isinstance(row.get("score"), (int, float))
            ]
            return {
                "score": None if not numeric else round(sum(numeric) / len(numeric), 2),
                "cycle_count": len(rows),
                "cycles": rows,
            }

        scores = {
            "theory_integrity": aggregate("theory_integrity"),
            "method_practice": score_method_practice(practice_records),
        }
        lifecycle_updates: list[dict[str, Any]] = []
        remaining_open_hypotheses: list[dict[str, Any]] = []
        for open_item in state.get("open_hypotheses", []):
            if not isinstance(open_item, Mapping):
                continue
            symbol_decision = open_item.get("symbol_decision")
            if not isinstance(symbol_decision, Mapping):
                continue
            updates = _hypothesis_assessments(
                [symbol_decision],
                all_analyses,
                now,
                str(open_item.get("decision_at")),
            )
            if not updates:
                continue
            update = {
                "hypothesis_instance_id": open_item.get("hypothesis_instance_id"),
                "origin_cycle_id": open_item.get("cycle_id"),
                **updates[0],
            }
            lifecycle_updates.append(update)
            if update["status"] in {"UNRESOLVED_UNKNOWN", "SUPPORTED_ACTIVE"}:
                remaining_open_hypotheses.append(copy.deepcopy(dict(open_item)))
        candidates = build_method_candidates(
            practice_records,
            review_id=f"review-{int(state['review_count']) + 1:03d}",
            window_hours=end_cycle - start_cycle + 1,
        )
        marks = _extract_marks(latest_market)
        review_number = int(state["review_count"]) + 1
        review_id = f"review-{review_number:03d}"

        terminal_outcome_points = {
            "SUPPORTED_AT_EXPIRY": 100.0,
            "EXPIRED_UNSUPPORTED": 20.0,
            "FALSIFIED": 0.0,
        }
        terminal_updates = [
            item
            for item in lifecycle_updates
            if item.get("status") in terminal_outcome_points
        ]
        hypothesis_outcome = {
            "schema_version": "HypothesisOutcomeDiagnostics.v1",
            "score": (
                None
                if not terminal_updates
                else round(
                    sum(
                        terminal_outcome_points[str(item["status"])]
                        for item in terminal_updates
                    )
                    / len(terminal_updates),
                    2,
                )
            ),
            "terminal_count": len(terminal_updates),
            "active_count": sum(
                item.get("status") == "SUPPORTED_ACTIVE"
                for item in lifecycle_updates
            ),
            "unknown_count": sum(
                item.get("status") == "UNRESOLVED_UNKNOWN"
                for item in lifecycle_updates
            ),
            "status_counts": {
                status: sum(item.get("status") == status for item in lifecycle_updates)
                for status in (
                    "SUPPORTED_ACTIVE",
                    "SUPPORTED_AT_EXPIRY",
                    "FALSIFIED",
                    "EXPIRED_UNSUPPORTED",
                    "UNRESOLVED_UNKNOWN",
                )
            },
            "scoring_rule": terminal_outcome_points,
            "calibration_status": "UNCALIBRATED_SMALL_SAMPLE_DESCRIPTIVE",
            "boundary": (
                "JUDGMENT_OUTCOME_DIAGNOSTIC_ONLY; UNRESOLVED_EXCLUDED; "
                "DOES_NOT_CHANGE_THEORY_INTEGRITY_OR_METHOD_PROCESS_SCORE"
            ),
        }

        active_delta = state.get("active_method_delta")
        delta_evaluation: dict[str, Any] | None = None
        if isinstance(active_delta, Mapping):
            issue_code = str(active_delta.get("issue_code") or "")
            issue_cycles = [
                str(record.get("cycle_id"))
                for record in practice_records
                if issue_code
                in _mapping(record.get("review")).get("method_issue_codes", [])
            ]
            current_occurrences = len(issue_cycles)
            baseline_occurrences = int(active_delta.get("baseline_occurrence_count", 1))
            if current_occurrences == 0:
                disposition = "RETAIN"
            elif current_occurrences < baseline_occurrences:
                disposition = "REVISE"
            else:
                disposition = "REJECT"
            delta_evaluation = {
                "method_delta_id": active_delta.get("method_delta_id"),
                "version": active_delta.get("version"),
                "evaluated_in_review": review_id,
                "evaluation_window": [start_cycle, end_cycle],
                "issue_code": issue_code,
                "baseline_occurrence_count": baseline_occurrences,
                "current_occurrence_count": current_occurrences,
                "evidence_refs": issue_cycles,
                "disposition": disposition,
                "test": active_delta.get("falsification_test"),
                "historical_artifacts_rewritten": False,
            }

        selected_candidate = candidates[0] if candidates else None
        next_active_delta: dict[str, Any] | None
        if (
            isinstance(active_delta, Mapping)
            and isinstance(delta_evaluation, Mapping)
            and delta_evaluation.get("disposition") == "RETAIN"
        ):
            next_active_delta = copy.deepcopy(dict(active_delta))
            next_active_delta["last_evaluated_review"] = review_id
            next_active_delta["effective_from_cycle"] = end_cycle + 1
        elif isinstance(selected_candidate, Mapping):
            prior_version = (
                int(active_delta.get("version", 0))
                if isinstance(active_delta, Mapping)
                else 0
            )
            practice_notes = [
                note
                for record in practice_records
                for note in _mapping(record.get("review")).get(
                    "method_observations",
                    [],
                )
                if isinstance(note, str) and note.strip()
            ]
            next_active_delta = {
                "schema_version": "ActiveMethodDelta.v1",
                "method_delta_id": str(
                    selected_candidate.get("method_candidate_id")
                ),
                "version": prior_version + 1,
                "source_review": review_id,
                "effective_from_cycle": end_cycle + 1,
                "issue_code": selected_candidate.get("issue_code"),
                "baseline_occurrence_count": int(
                    selected_candidate.get("occurrence_count", 1)
                ),
                "proposed_method_delta": (
                    str(selected_candidate.get("proposed_method_delta") or "")
                    + (
                        " Practice-derived check: " + practice_notes[0]
                        if practice_notes
                        else ""
                    )
                ),
                "falsification_test": selected_candidate.get("falsification_test"),
                "practice_note_applied": (
                    practice_notes[0] if practice_notes else None
                ),
                "status": "ACTIVE_FUTURE_ONLY",
                "historical_artifacts_rewritten": False,
            }
        else:
            next_active_delta = None
        primary_delta = [next_active_delta] if next_active_delta is not None else []
        review = {
            "schema_version": "theory-paper-eight-hour-review.v1",
            "review_id": f"review-{review_number:03d}",
            "reviewed_at": iso_utc(now),
            "cycle_range": [start_cycle, end_cycle],
            "theory_integrity": scores["theory_integrity"],
            "method_practice": scores["method_practice"],
            "paper_performance": portfolio_metrics(state["portfolio"], marks),
            "hypothesis_outcome_diagnostics": hypothesis_outcome,
            "method_candidates": candidates,
            "primary_delta_for_future_cycles": primary_delta,
            "prior_method_delta_evaluation": delta_evaluation,
            "cycle_assessments": [
                {
                    "cycle_id": record["cycle_id"],
                    "review": record["review"],
                    "scores": cycle_score,
                }
                for record, cycle_score in zip(practice_records, cycle_scores)
            ],
            "hypothesis_lifecycle_updates": lifecycle_updates,
            "open_hypothesis_count_after_review": len(remaining_open_hypotheses),
            "score_boundary": "PNL_DOES_NOT_CHANGE_THEORY_OR_METHOD_SCORE",
            "claim_boundary": "DESCRIPTIVE_PAPER_REVIEW_NOT_PREDICTIVE_VALIDATION",
        }
        review["review_digest"] = digest_json(review)
        path = root / "reviews" / f"review-{review_number:03d}.json"
        next_state = copy.deepcopy(state)
        next_state["review_count"] = review_number
        next_state["last_review_cycle"] = end_cycle
        next_state["open_hypotheses"] = remaining_open_hypotheses
        next_state["active_method_delta"] = next_active_delta
        method_history = next_state.setdefault("method_delta_history", [])
        if delta_evaluation is not None:
            method_history.append(copy.deepcopy(delta_evaluation))
        if next_active_delta is not None:
            method_history.append(
                {
                    "event": "ACTIVATED_OR_RETAINED_FOR_FUTURE_ONLY",
                    "review_id": review_id,
                    "method_delta": copy.deepcopy(next_active_delta),
                }
            )
        _commit_transaction(
            root,
            transaction_id=f"review-{review_number:03d}",
            post_state=next_state,
            artifacts=[
                {
                    "path": f"reviews/review-{review_number:03d}.json",
                    "value": review,
                }
            ],
            event_type="EIGHT_HOUR_REVIEW_FROZEN",
            event_payload={
                "review_id": review["review_id"],
                "review_digest": review["review_digest"],
                "cycle_range": review["cycle_range"],
            },
            observed_at=iso_utc(now),
        )
        return {
            "created": True,
            "review_path": str(path.resolve()),
            **review,
        }


def inject_manual_emotion_trade(
    run_dir: Path,
    *,
    idempotency_key: str,
    symbol: str,
    side: str,
    notional_usdt: float,
    reason: str,
    injected_at: datetime | None = None,
) -> dict[str, Any]:
    """Add an explicitly exogenous manual paper trade without theory attribution."""
    root = Path(run_dir)
    now = (injected_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise TheoryPaperError("manual chaos idempotency key is required")
    if _secret_shape_paths({"reason": reason, "idempotency_key": idempotency_key}):
        raise TheoryPaperError("manual chaos input contains credential-shaped material")
    request_digest = digest_json(
        {
            "symbol": symbol,
            "side": side,
            "notional_usdt": float(notional_usdt),
            "reason": reason,
        }
    )
    idempotency_digest = digest_json({"idempotency_key": idempotency_key})
    transaction_id = "chaos-manual-" + idempotency_digest[:20]
    artifact_path = root / "manual-chaos" / f"{transaction_id}.json"
    with experiment_lock(root):
        config = _config_for_run(root)
        _require_wall_clock(config, now, "manual chaos time")
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        if artifact_path.exists():
            if not _transaction_is_committed(root, transaction_id):
                raise TheoryPaperError(
                    "manual chaos artifact exists without a committed transaction"
                )
            existing = read_json(artifact_path)
            if existing.get("request_digest") != request_digest:
                raise TheoryPaperError(
                    "manual chaos idempotency key was reused with a different payload"
                )
            return existing
        state = read_json(root / "state.json")
        if state.get("status") != "ACTIVE":
            raise TheoryPaperError("experiment is not active")
        if state.get("pending_decision_cycle") is not None:
            raise TheoryPaperError("manual chaos cannot bypass a pending agent decision")
        if now > parse_utc(state["ends_at"]):
            raise TheoryPaperError("manual chaos is after the experiment window")
        if config.get("chaos_policy", {}).get("manual_injection_enabled") is not True:
            raise TheoryPaperError("manual chaos is disabled by the frozen config")
        chaos_policy = config.get("chaos_policy", {})
        minimum = float(chaos_policy.get("notional_min_usdt", 100.0))
        maximum = float(chaos_policy.get("notional_max_usdt", 250.0))
        if not minimum <= float(notional_usdt) <= maximum:
            raise TheoryPaperError(
                f"manual chaos notional must be between {minimum:g} and {maximum:g} USDT"
            )
        if state.get("cycle_count", 0) < 1:
            raise TheoryPaperError("manual chaos needs at least one frozen market cycle")
        prior_update = state.get("portfolio", {}).get("updated_at")
        if isinstance(prior_update, str) and now < parse_utc(prior_update):
            raise TheoryPaperError("manual chaos time cannot precede the portfolio state")
        market = read_json(_cycle_dir(root, int(state["cycle_count"])) / "market.json")
        market_observed_at = parse_utc(str(market.get("observed_at")))
        _, tolerance = _clock_policy(config)
        freshness_seconds = float(config["analysis_interval_hours"]) * 3600 + tolerance
        age_seconds = (now - market_observed_at).total_seconds()
        if age_seconds < 0 or age_seconds > freshness_seconds:
            raise TheoryPaperError(
                "manual chaos requires a market snapshot no more than one slot old"
            )
        next_state = copy.deepcopy(state)
        result = inject_manual_chaos(
            next_state["portfolio"],
            market,
            symbol=symbol,
            side=side,
            notional_usdt=float(notional_usdt),
            observed_at=iso_utc(now),
            note=reason,
        )
        result["idempotency_key_digest"] = idempotency_digest
        result["request_digest"] = request_digest
        result["transaction_id"] = transaction_id
        _commit_transaction(
            root,
            transaction_id=transaction_id,
            post_state=next_state,
            artifacts=[
                {
                    "path": f"manual-chaos/{transaction_id}.json",
                    "value": result,
                }
            ],
            event_type="MANUAL_EMOTION_INJECTION",
            event_payload=result,
            observed_at=iso_utc(now),
        )
        return result


def status_report(run_dir: Path) -> dict[str, Any]:
    root = Path(run_dir)
    with experiment_lock(root):
        _config_for_run(root)
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        state = read_json(root / "state.json")
        marks: dict[str, float] = {}
        if int(state.get("cycle_count", 0)) > 0:
            latest = read_json(_cycle_dir(root, int(state["cycle_count"])) / "market.json")
            marks = _extract_marks(latest)
        now = datetime.now(timezone.utc)
        return {
            "run_id": state["run_id"],
            "status": state["status"],
            "paper_only": True,
            "clock_mode": state.get("clock_mode"),
            "started_at": state["started_at"],
            "ends_at": state["ends_at"],
            "hours_elapsed": round((now - parse_utc(state["started_at"])).total_seconds() / 3600.0, 3),
            "cycle_count": state["cycle_count"],
            "pending_decision_cycle": state["pending_decision_cycle"],
            "review_count": state["review_count"],
            "valid_hours_without_strategy_fill": state["valid_hours_without_strategy_fill"],
            "active_method_delta": state.get("active_method_delta"),
            "chaos_blinding_status": state.get("chaos_blinding_status"),
            "portfolio": portfolio_metrics(state["portfolio"], marks),
            "ledger": verify_ledger(root),
            "transaction_state": _verify_latest_transaction_state(root),
            "chaos_schedule_commitment": state["chaos_commitment"],
        }


def finalize_experiment(
    run_dir: Path,
    *,
    finalized_at: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Stop new paper risk and seal a descriptive final report."""
    root = Path(run_dir)
    now = (finalized_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with experiment_lock(root):
        config = _config_for_run(root)
        _require_wall_clock(config, now, "finalization time")
        _recover_pending_transactions(root)
        _verify_latest_transaction_state(root)
        state = read_json(root / "state.json")
        final_path = root / "final" / "report.json"
        if final_path.exists():
            if (
                state.get("status") != "FINALIZED"
                or not _transaction_is_committed(root, "experiment-finalize")
            ):
                raise TheoryPaperError(
                    "final report exists without a committed finalized state"
                )
            existing = read_json(final_path)
            return {**existing, "ledger_after_final": verify_ledger(root)}
        if state.get("status") != "ACTIVE":
            raise TheoryPaperError("experiment is not active")
        if state.get("pending_decision_cycle") is not None:
            raise TheoryPaperError("pending decision must be submitted before finalization")
        if int(state["cycle_count"]) == 0:
            raise TheoryPaperError("cannot finalize an experiment with no cycles")
        prior_update = state.get("portfolio", {}).get("updated_at")
        if isinstance(prior_update, str) and now < parse_utc(prior_update):
            raise TheoryPaperError("finalization time cannot precede the portfolio state")

        expected_slots = state.get("expected_hour_slots", [])
        completed_slots = state.get("completed_hour_slots", [])
        if not isinstance(expected_slots, list) or not isinstance(completed_slots, list):
            raise TheoryPaperError("run state has no frozen hourly coverage schedule")
        missing_slots = sorted(set(expected_slots) - set(completed_slots))
        duplicate_or_extra_slots = (
            len(completed_slots) != len(set(completed_slots))
            or bool(set(completed_slots) - set(expected_slots))
        )
        analysis_coverage_failures: list[str] = []
        expected_symbols = set(config["symbols"])
        for number in range(1, int(state["cycle_count"]) + 1):
            cycle_root = _cycle_dir(root, number)
            try:
                analysis = read_json(cycle_root / "analysis.json")
                receipt = read_json(cycle_root / "decision.json")
            except TheoryPaperError:
                analysis_coverage_failures.append(
                    f"{_cycle_name(number)}:MISSING_ANALYSIS_OR_DECISION"
                )
                continue
            observed_symbols = {
                item.get("symbol")
                for item in analysis.get("symbols", [])
                if isinstance(item, Mapping)
            }
            if observed_symbols != expected_symbols:
                analysis_coverage_failures.append(
                    f"{_cycle_name(number)}:SYMBOL_COVERAGE_MISMATCH"
                )
            if receipt.get("cycle_id") != _cycle_name(number):
                analysis_coverage_failures.append(
                    f"{_cycle_name(number)}:DECISION_RECEIPT_MISMATCH"
                )
        required_reviews = int(config["duration_hours"]) // int(
            config["review_interval_hours"]
        )
        missing_review_count = max(
            0,
            required_reviews - int(state.get("review_count", 0)),
        )
        ended = now >= parse_utc(state["ends_at"])
        complete = (
            ended
            and int(state["cycle_count"]) == int(config["duration_hours"])
            and not missing_slots
            and not duplicate_or_extra_slots
            and not analysis_coverage_failures
            and missing_review_count == 0
        )
        if not complete and not force:
            reasons = []
            if not ended:
                reasons.append("EXPERIMENT_END_NOT_REACHED")
            if missing_slots:
                reasons.append(f"MISSING_HOURLY_SLOTS:{len(missing_slots)}")
            if duplicate_or_extra_slots:
                reasons.append("DUPLICATE_OR_EXTRA_HOURLY_SLOTS")
            if analysis_coverage_failures:
                reasons.append(
                    f"ANALYSIS_OR_DECISION_COVERAGE:{len(analysis_coverage_failures)}"
                )
            if missing_review_count:
                reasons.append(f"MISSING_REVIEWS:{missing_review_count}")
            raise TheoryPaperError(
                "72-hour experiment coverage is incomplete: " + "; ".join(reasons)
            )
        market = read_json(_cycle_dir(root, int(state["cycle_count"])) / "market.json")
        marks = _extract_marks(market)
        reviews = [
            read_json(path)
            for path in sorted((root / "reviews").glob("review-*.json"))
        ] if (root / "reviews").exists() else []
        expected_review_ranges = [
            [start, start + int(config["review_interval_hours"]) - 1]
            for start in range(
                1,
                int(config["duration_hours"]) + 1,
                int(config["review_interval_hours"]),
            )
        ]
        observed_review_ranges = [
            item.get("cycle_range")
            for item in reviews
            if isinstance(item, Mapping)
        ]
        exact_review_coverage = (
            observed_review_ranges == expected_review_ranges
            and int(state.get("last_review_cycle", 0))
            == int(config["duration_hours"])
        )
        complete = complete and exact_review_coverage
        if not exact_review_coverage and not force:
            raise TheoryPaperError(
                "72-hour experiment review coverage is not nine exact 8-cycle windows"
            )
        clock_mode, _ = _clock_policy(config)
        result_status = (
            "DESCRIPTIVE_72H_PAPER_PRACTICE"
            if complete and clock_mode == LIVE_CLOCK
            else "SIMULATED_CLOCK_72H_TEST_NOT_MARKET_PRACTICE"
            if complete
            else "INCOMPLETE_RECOVERY_PAPER_PRACTICE"
        )
        final = {
            "schema_version": "theory-paper-final-report.v1",
            "run_id": state["run_id"],
            "finalized_at": iso_utc(now),
            "cycle_count": state["cycle_count"],
            "review_count": state["review_count"],
            "portfolio": portfolio_metrics(state["portfolio"], marks),
            "reviews": [
                {
                    "review_id": item["review_id"],
                    "review_digest": item["review_digest"],
                    "theory_score": item["theory_integrity"].get("score"),
                    "method_score": item["method_practice"].get("score"),
                    "hypothesis_outcome_score": _mapping(
                        item.get("hypothesis_outcome_diagnostics")
                    ).get("score"),
                }
                for item in reviews
            ],
            "method_delta_history": copy.deepcopy(
                state.get("method_delta_history", [])
            ),
            "open_positions_disposition": "FROZEN_MARK_TO_MARKET_NO_NEW_RISK",
            "coverage": {
                "complete": complete,
                "expected_hour_count": len(expected_slots),
                "completed_hour_count": len(completed_slots),
                "missing_hour_slots": missing_slots,
                "duplicate_or_extra_slots": duplicate_or_extra_slots,
                "required_review_count": required_reviews,
                "completed_review_count": int(state.get("review_count", 0)),
                "missing_review_count": missing_review_count,
                "expected_review_ranges": expected_review_ranges,
                "observed_review_ranges": observed_review_ranges,
                "exact_review_coverage": exact_review_coverage,
                "analysis_coverage_failures": analysis_coverage_failures,
                "experiment_end_reached": ended,
            },
            "clock_mode": clock_mode,
            "result_status": result_status,
            "claim_boundary": (
                "PROFIT_OR_LOSS_DOES_NOT_PROVE_CAUSALITY_PREDICTIVE_VALIDITY_"
                "OR_SUSTAINABLE_PROFITABILITY"
            ),
            "chaos_schedule_commitment": state["chaos_commitment"],
            "ledger_before_final": verify_ledger(root),
        }
        final["final_report_digest"] = digest_json(final)
        next_state = copy.deepcopy(state)
        next_state["status"] = "FINALIZED"
        next_state["finalized_at"] = iso_utc(now)
        _commit_transaction(
            root,
            transaction_id="experiment-finalize",
            post_state=next_state,
            artifacts=[{"path": "final/report.json", "value": final}],
            event_type="EXPERIMENT_FINALIZED",
            event_payload={
                "final_report_digest": final["final_report_digest"],
                "cycle_count": next_state["cycle_count"],
                "review_count": next_state["review_count"],
                "result_status": final["result_status"],
            },
            observed_at=iso_utc(now),
        )
        return {**final, "ledger_after_final": verify_ledger(root)}
