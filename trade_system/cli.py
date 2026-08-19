"""Small operational CLI. All commands are local and paper-only."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .episode import EpisodeMachine
from .episode_policy import EpisodePolicy
from .binance import BinanceCaptureSession
from .event_store import EventStore
from .features import FeatureEngine
from .order_book import BookGapError, OrderBook
from .paper import PaperBroker
from .paper_audit import (
    PaperAuditTrail,
    audit_paper_trail,
    verify_paper_recovery_report,
    write_paper_recovery_report,
)
from .protocol import ResearchProtocol, V2_SCHEMA_VERSION
from .protocol_finalizer import finalize_research_protocol
from .market_runtime import BinancePublicMarketRuntime, stream_urls
from .labeling import generate_labels, load_actions, load_feature_prices, write_label_rows
from .costs import CostScenario, evaluate_cost_pressure
from .coverage import build_coverage_report
from .g1_acceptance import G1AcceptancePolicy, validate_g1_data, validate_g1_stores
from .source_registry import SourceRegistry
from .account_telemetry import (
    AccountTelemetryContract,
    audit_normalized_telemetry,
    write_recovery_telemetry_reconciliation_report,
)
from .account_telemetry_normalizer import normalize_sanitized_telemetry
from .holdout_ledger import (
    consume_final_holdout_release,
    open_final_holdout,
    verify_final_holdout_release,
)
from .paper_run_contract import (
    PaperRunContract,
    seal_paper_run,
    verify_paper_run_binding,
    verify_paper_run_evidence,
)
from .risk_gate_profile import RiskGateProfile
from .g1_report import load_passed_g1_report, write_g1_report
from .state_classifier import StateClassifier
from .research_report import sha256_file, write_research_report
from .capture_plan import ForwardCapturePlan
from .capture_status import inspect_forward_capture_plan
from .capture_supervisor import decide_capture_slot
from .collection_sealing import seal_collection
from .planned_capture import PlannedCaptureRequest, public_configured_streams, run_planned_capture
from .software_identity import collector_software_binding
from .collection_inventory import inventory_collections
from .feature_describe import describe_sealed_features
from .readiness import build_research_readiness
from .feature_bundle import build_feature_bundle, build_role_feature_bundle
from .evidence_archive import archive_sealed_collection, verify_evidence_archive, verify_hot_cold_equivalence
from .data_acceptance import write_data_acceptance_report
from .research_evidence_admission import (
    ResearchEvidenceAdmissionError,
    admit_research_evidence,
    load_verified_research_evidence_admission,
)
from .g2_protocol import evaluate_protocol_g2
from .label_bundle import build_label_bundle
from .state_label_bundle import build_state_label_bundle, load_verified_state_label_bundle_manifest
from .action_bundle import build_action_bundle
from .action_policy import ResearchActionPolicy
from .historical_audit import HistoricalAuditPlan, audit_plan, write_audit_report
from .binance_archive_overlap import BinanceArchiveOverlapPlan, audit_binance_aggtrade_overlap
from .binance_cm_historical_mechanism import (
    HistoricalMechanismError,
    HistoricalMechanismPlan,
    run_historical_mechanism_experiment,
    write_historical_mechanism_report,
)
from .historical_evidence_ledger import HistoricalEvidenceLedgerError, verify_historical_evidence_ledger
from .binance_cm_historical_diagnostic import HistoricalDiagnosticError, HistoricalDiagnosticPlan, execute_frozen_before_download
from .historical_diagnostic_development import HistoricalDevelopmentError, build_january_development_artifacts, finalize_january_development_artifacts
from .historical_diagnostic_application import HistoricalDiagnosticApplicationError, execute_authorized_fresh_diagnostic, verify_receipt_bound_application
from .decision import ConservativePolicy, ExecutionForecast, OutcomeForecast
from .research import (
    LabeledObservation,
    MarketOutcome,
    assess_state_coverage,
    run_final_holdout_baseline,
    run_walk_forward_baseline,
)
from .types import parse_utc
from .pipeline import FeaturePipeline, write_feature_rows
from .live_shadow import LiveFeatureObserver, verify_live_feature_artifact
from .shadow import compare_decision_artifacts, compare_feature_artifacts, compare_feature_row_maps, load_feature_rows
from .decision_provenance import verify_shadow_decision_artifact
from .replay import DeterministicReplay
from .risk import OrderManager, RiskEngine, RiskLimits
from .types import (
    AvailabilityKind,
    AvailabilityRecord,
    GateLevel,
    OrderIntent,
    PositionStage,
    Side,
    SystemHealth,
    TradePrint,
    iso_utc,
    utc_now,
)
from .theory_paper import (
    finalize_experiment as finalize_theory_paper_experiment,
    initialize_experiment as initialize_theory_paper_experiment,
    run_hourly_cycle as run_theory_paper_hourly_cycle,
    run_review as run_theory_paper_review,
    status_report as theory_paper_status_report,
    submit_agent_decision as submit_theory_paper_agent_decision,
)
from .theory_paper.experiment import inject_manual_emotion_trade


DEFAULT_SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "source_registry.v3.json"
DEFAULT_ACCOUNT_TELEMETRY_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "config" / "account_telemetry_contract.v1.json"
DEFAULT_RISK_GATE_PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "risk_gate_profile.paper.v1.json"
DEFAULT_OKX_AUDIT_PLAN_PATH = Path(__file__).resolve().parents[1] / "config" / "okx_historical_audit.template.json"
DEFAULT_BINANCE_ARCHIVE_OVERLAP_PLAN_PATH = Path(__file__).resolve().parents[1] / "config" / "binance_aggtrade_overlap.frozen.template.json"
DEFAULT_BINANCE_CM_HISTORICAL_MECHANISM_PLAN_PATH = Path(__file__).resolve().parents[1] / "config" / "binance_cm_historical_mechanism.v1.json"
DEFAULT_BINANCE_CM_HISTORICAL_LEDGER_PATH = Path(__file__).resolve().parents[1] / "config" / "binance_cm_historical_evidence_ledger.v1.json"
DEFAULT_BINANCE_CM_HISTORICAL_DIAGNOSTIC_PATH = Path(__file__).resolve().parents[1] / "config" / "binance_cm_historical_diagnostic.v2.frozen_before_download.json"
DEFAULT_BINANCE_CM_HISTORICAL_JAN_DIAGNOSTIC_PATH = Path(__file__).resolve().parents[1] / "config" / "binance_cm_historical_diagnostic.v2.jan_development.json"
DEFAULT_G1_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "g1_data_acceptance.v1.json"
DEFAULT_RESEARCH_PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "config" / "research_protocol.v2.draft.json"


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _append_actual(store: EventStore, connection_id: str, ingest_seq: int, normalized: Dict[str, Any]) -> None:
    received = utc_now()
    raw = store.append_raw(
        source="SYNTHETIC",
        venue="BINANCE_USDM",
        instrument="BTCUSDT",
        stream=normalized["kind"],
        connection_id=connection_id,
        ingest_seq=ingest_seq,
        payload={"demo": True, "normalized": normalized},
        receive_time=received,
        exchange_event_time=received,
    )
    derived = utc_now()
    store.append_availability(
        raw,
        AvailabilityRecord(
            event_id=raw.event_id,
            schema_version="synthetic-v1",
            derived_at=derived,
            available_at=derived,
            availability_kind=AvailabilityKind.ACTUAL,
            normalized=normalized,
        ),
    )


def _demo_events() -> Iterable[Dict[str, Any]]:
    return (
        {"kind": "snapshot", "last_update_id": 100, "bids": [["99", "3"], ["98", "4"]], "asks": [["101", "3"], ["102", "4"]]},
        {"kind": "oi", "value": "1000"},
        {"kind": "trade", "price": "100", "quantity": "2", "side": "SELL"},
        {"kind": "delta", "U": 101, "u": 101, "pu": 100, "bids": [["99", "4"]], "asks": []},
        {"kind": "oi", "value": "980"},
        {"kind": "liquidation", "price": "100", "quantity": "1", "side": "SELL", "censored": True},
        {"kind": "trade", "price": "100", "quantity": "0.2", "side": "SELL"},
        {"kind": "delta", "U": 102, "u": 102, "pu": 101, "bids": [["99", "5"]], "asks": [["101", "2"]]},
        {"kind": "trade", "price": "101", "quantity": "1", "side": "BUY"},
    )


def _run_research_path(store: EventStore) -> Tuple[Dict[str, Any], OrderBook]:
    replay = DeterministicReplay(store)
    book = OrderBook()
    engine = FeatureEngine()
    episode_machine = EpisodeMachine()
    latest_snapshot = None
    event_count = 0
    for event in replay.events():
        event_count += 1
        data = event.availability.normalized
        kind = data["kind"]
        if kind == "snapshot":
            book.reset_snapshot(last_update_id=data["last_update_id"], bids=data["bids"], asks=data["asks"])
        elif kind == "delta":
            book.apply_delta(
                first_update_id=data["U"],
                final_update_id=data["u"],
                previous_final_update_id=data.get("pu"),
                bids=data["bids"],
                asks=data["asks"],
            )
        elif kind == "trade":
            engine.add_trade(
                TradePrint(
                    available_at=event.availability.available_at,
                    price=_decimal(data["price"]),
                    quantity=_decimal(data["quantity"]),
                    aggressor_side=Side(data["side"]),
                )
            )
        elif kind == "oi":
            engine.update_open_interest(_decimal(data["value"]))
        elif kind == "liquidation":
            engine.add_liquidation(
                event.availability.available_at,
                Side(data["side"]),
                _decimal(data["price"]),
                _decimal(data["quantity"]),
                bool(data["censored"]),
            )
        if book.health.value == "VALID":
            latest_snapshot = engine.snapshot(
                available_at=event.availability.available_at,
                book=book,
                availability_kind=event.availability.availability_kind,
            )
            if episode_machine.active is None:
                episode_machine.observe_extreme(
                    now=event.availability.available_at,
                    price=latest_snapshot.values["mid_price"],
                    reversal_side=Side.BUY,
                )
            episode_machine.advance(latest_snapshot)
    if latest_snapshot is None:
        raise RuntimeError("demo did not produce a valid feature snapshot")
    episode = episode_machine.active
    return (
        {
            "replay_events": event_count,
            "replay_digest": replay.digest(),
            "book_checksum": book.checksum(),
            "book_health": book.health.value,
            "episode_id": episode.episode_id if episode else None,
            "episode_state": episode.state.value if episode else None,
            "features": {key: str(value) for key, value in latest_snapshot.values.items()},
            "quality_flags": latest_snapshot.quality_flags,
        },
        book,
    )


def command_demo(args: argparse.Namespace) -> int:
    root = Path(args.data_dir)
    store = EventStore(root)
    connection_id = "demo-" + uuid.uuid4().hex
    for index, event in enumerate(_demo_events(), start=1):
        _append_actual(store, connection_id, index, event)
    summary, book = _run_research_path(store)

    risk = RiskEngine(
        RiskLimits(
            max_episode_loss=Decimal("100"),
            max_total_notional=Decimal("1000"),
            max_single_order_quantity=Decimal("2"),
            tail_cost_per_unit=Decimal("1"),
            max_unprotected_duration=timedelta(seconds=1),
        )
    )
    risk.set_health(SystemHealth.READY)
    audit_trail = None
    if args.paper_audit:
        audit_trail = PaperAuditTrail(
            Path(args.paper_audit),
            run_id="demo-" + connection_id,
            context={"scope": "SYNTHETIC_DEMO_ONLY", "event_store": str(root), "model_version": "synthetic-v1", "policy_version": "paper-v1"},
        )
    manager = OrderManager(risk, audit_trail=audit_trail)
    now = utc_now()
    intent = OrderIntent(
        intent_id="demo-intent-" + uuid.uuid4().hex,
        episode_id=summary["episode_id"] or "demo-episode",
        side=Side.BUY,
        stage=PositionStage.ENTER_PROBE,
        quantity=Decimal("1"),
        limit_price=Decimal("101"),
        stop_price=Decimal("98"),
        created_at=now,
        model_version="synthetic-v1",
        policy_version="paper-v1",
    )
    order = manager.submit_intent(intent)
    fills = PaperBroker(Decimal("0.0005")).execute_ioc(manager, intent.intent_id, book, utc_now())
    if fills:
        manager.confirm_protection(intent.intent_id, abs(manager.position_quantity), utc_now())
    summary["paper"] = {
        "order_status": manager.orders_by_intent[intent.intent_id].status.value,
        "filled_quantity": str(manager.orders_by_intent[intent.intent_id].filled_quantity),
        "effective_protected_quantity": str(manager.effective_protected_quantity),
        "protection_valid": manager.verify_protection(utc_now()),
        "halt_reasons": sorted(manager.halt_reasons),
    }
    if audit_trail is not None:
        audit_trail.finalize(manager.audit_state(), observed_at=utc_now())
        summary["paper"]["audit"] = audit_trail.summary()
    valid, issues, audit_digest = store.audit()
    summary["store"] = {"valid": valid, "issues": issues, "audit_digest": audit_digest}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if valid and not manager.halt_reasons else 1


def command_verify(args: argparse.Namespace) -> int:
    store = EventStore(Path(args.data_dir))
    valid, issues, digest = store.audit()
    output = {"valid": valid, "issues": issues, "audit_digest": digest, "replay_digest": DeterministicReplay(store).digest()}
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if valid else 1


def command_replay(args: argparse.Namespace) -> int:
    store = EventStore(Path(args.data_dir))
    replay = DeterministicReplay(store, allow_reconstructed=args.allow_reconstructed)
    count = sum(1 for _ in replay.events())
    print(json.dumps({"events": count, "digest": replay.digest(), "allow_reconstructed": args.allow_reconstructed}, indent=2))
    return 0


def command_ingest(args: argparse.Namespace) -> int:
    """Read newline-delimited {stream, payload} envelopes from stdin."""
    store = EventStore(Path(args.data_dir))
    session = BinanceCaptureSession(store, args.connection_id, instrument=args.instrument)
    written = 0
    parse_errors = []
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        try:
            envelope = json.loads(line)
            result = session.ingest(envelope["stream"], envelope["payload"])
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            print("input error at line %d: %s" % (line_number, exc), file=sys.stderr)
            return 2
        if result.availability_written:
            written += 1
        else:
            parse_errors.append({"event_id": result.raw.event_id, "error": result.parse_error})
    print(json.dumps({"raw_captured": session.ingest_count, "availability_written": written, "parse_errors": parse_errors}, ensure_ascii=False, indent=2))
    return 0


def command_validate_protocol(args: argparse.Namespace) -> int:
    protocol = ResearchProtocol.load(Path(args.protocol))
    print(json.dumps({
        "protocol_id": protocol.protocol_id,
        "status": protocol.status,
        "frozen_for_research": protocol.is_frozen_for_research,
        "digest": protocol.digest,
    }, ensure_ascii=False, indent=2))
    return 0


def command_finalize_research_protocol(args: argparse.Namespace) -> int:
    report = finalize_research_protocol(
        Path(args.preregistered_protocol),
        g1_report_path=Path(args.g1_report),
        output_path=Path(args.output),
        supersession_guard_path=Path(args.supersession_guard),
        frozen_at=args.frozen_at,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _source_observation_samples(store: EventStore, registry: SourceRegistry, instrument: str, configured_streams: list) -> Dict[str, Any]:
    samples = {}
    for source in registry.selected_sources(instrument, configured_streams):
        allowed_streams = set(source.resolved_channels(instrument))
        raw = next((item for item in store.iter_raw() if item.stream in allowed_streams), None)
        if raw is not None:
            samples[source.source_id] = {
                "first_payload_sha256": raw.payload_hash,
                "first_receive_time": iso_utc(raw.receive_time),
                "stream": raw.stream,
            }
    return samples


def _collect_public(args: argparse.Namespace) -> Tuple[Dict[str, Any], int]:
    """Forward public market capture only; no credentials and no trade path."""
    configured_streams = public_configured_streams(args.instrument)
    registry = SourceRegistry.load(Path(args.source_registry))
    registry_binding = registry.manifest_binding(args.instrument, configured_streams)
    software_binding = collector_software_binding()
    capture_plan_binding = None
    if bool(args.capture_plan) != bool(args.capture_slot):
        raise ValueError("--capture-plan and --capture-slot must be supplied together")
    if args.capture_plan:
        plan = ForwardCapturePlan.load(Path(args.capture_plan))
        capture_plan_binding = plan.bind_slot(
            slot_id=args.capture_slot,
            now=utc_now(),
            requested_duration_seconds=args.duration_seconds,
            instrument=args.instrument,
            registry_id=registry.registry_id,
            registry_sha256=registry.sha256,
            collector_software_sha256=software_binding["package_source_sha256"],
        )
    store = EventStore(Path(args.data_dir))
    live_feature_observer = None
    episode_policy = None
    requested_episode_policy = getattr(args, "episode_policy", "")
    if requested_episode_policy:
        episode_policy = EpisodePolicy.load(Path(requested_episode_policy))
    requested_live_feature_output = getattr(args, "live_feature_output", "")
    if requested_live_feature_output:
        live_feature_observer = LiveFeatureObserver(Path(requested_live_feature_output), evidence_root=store.root, episode_policy=episode_policy)
    depth = BinanceCaptureSession(store, args.connection_id + "-depth", instrument=args.instrument.upper())
    market = BinanceCaptureSession(store, args.connection_id + "-market", instrument=args.instrument.upper())
    oi = BinanceCaptureSession(store, args.connection_id + "-oi", instrument=args.instrument.upper())
    metadata = BinanceCaptureSession(store, args.connection_id + "-metadata", instrument=args.instrument.upper())
    runtime = BinancePublicMarketRuntime(
        depth_session=depth,
        market_session=market,
        oi_session=oi,
        metadata_session=metadata,
        snapshot_limit=args.snapshot_limit,
        open_interest_interval_seconds=args.oi_poll_seconds,
        metadata_interval_seconds=args.metadata_poll_seconds,
        feature_observer=live_feature_observer.observe if live_feature_observer is not None else None,
    )
    interrupted_signal = None
    previous_handlers = {}

    def _interrupt(signum, _frame):
        nonlocal interrupted_signal
        interrupted_signal = signum
        raise KeyboardInterrupt

    # A collector may be stopped deliberately by a supervisor.  Convert the
    # catchable termination signals into a terminal, explicitly unqualified
    # manifest rather than leaving a plausible-looking raw directory with no
    # collection outcome. SIGKILL remains inherently uncatchable.
    termination_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        termination_signals.append(signal.SIGHUP)
    for candidate in termination_signals:
        previous_handlers[candidate] = signal.signal(candidate, _interrupt)
    interrupted = False
    runtime_failure = None
    try:
        asyncio.run(runtime.run(duration_seconds=args.duration_seconds))
    except KeyboardInterrupt:
        interrupted = True
    except Exception as exc:
        runtime_failure = "%s: %s" % (type(exc).__name__, exc)
    finally:
        for candidate, handler in previous_handlers.items():
            signal.signal(candidate, handler)
    stats = runtime.stats
    health = runtime.quality.evaluate(utc_now())
    audit_valid, audit_issues, audit_digest = store.audit()
    replay_digest = DeterministicReplay(store).digest()
    urls = stream_urls(args.instrument)
    source_samples = _source_observation_samples(store, registry, args.instrument, configured_streams)
    collection_raw = [raw for raw in store.iter_raw() if raw.connection_id.startswith(args.connection_id + "-")]
    raw_ids = {raw.event_id for raw in collection_raw}
    collection_availability = [record for record in store.iter_availability() if record.event_id in raw_ids]
    errors = list(stats.errors)
    if interrupted:
        reason = "capture interrupted by signal %s" % interrupted_signal if interrupted_signal is not None else "capture interrupted by KeyboardInterrupt"
        errors.append(reason)
    if runtime_failure is not None:
        errors.append("capture runtime failure: %s" % runtime_failure)
    succeeded = not interrupted and runtime_failure is None and (
        runtime.book.health.value == "VALID"
        and health == SystemHealth.READY
        and not stats.book_gaps
        and not stats.parse_errors
        and not stats.errors
        and audit_valid
    )
    live_feature_artifact: Dict[str, Any] = {"status": "NOT_REQUESTED"}
    if live_feature_observer is not None:
        if succeeded:
            try:
                live_feature_artifact = live_feature_observer.finalize().to_dict()
            except Exception as exc:
                errors.append("live feature artifact failure: %s: %s" % (type(exc).__name__, exc))
                live_feature_artifact = live_feature_observer.abandon()
                succeeded = False
        else:
            live_feature_artifact = live_feature_observer.abandon()
    manifest = store.write_collection_manifest(args.connection_id, {
        "schema_version": "collection-manifest-v1",
        "instrument": args.instrument.upper(),
        "venue": "BINANCE_USDM",
        "transport_urls": urls,
        "configured_streams": configured_streams,
        "source_registry": registry_binding,
        "capture_plan": capture_plan_binding,
        "collector_software": software_binding,
        "source_observation_samples": source_samples,
        "duration_seconds": args.duration_seconds,
        "snapshot_limit": args.snapshot_limit,
        "oi_poll_seconds": args.oi_poll_seconds,
        "metadata_poll_seconds": args.metadata_poll_seconds,
        "collection_result": "QUALIFIED_SMOKE" if succeeded else "UNQUALIFIED",
        # Persisted evidence is authoritative at an interruption boundary;
        # in-memory counters only describe normal runtime progress.
        "raw_captured": len(collection_raw),
        "availability_written": len(collection_availability),
        "parse_errors": stats.parse_errors,
        "book_gaps": stats.book_gaps,
        "snapshot_fetches": stats.snapshot_fetches,
        "open_interest_polls": stats.open_interest_polls,
        "exchange_info_fetches": stats.exchange_info_fetches,
        "exchange_info_status": stats.exchange_info_status,
        "exchange_info_filter_count": stats.exchange_info_filter_count,
        "connection_attempts": stats.connection_attempts,
        "reconnects": stats.reconnects,
        "discarded_stale_snapshots": stats.discarded_stale_snapshots,
        "errors": errors,
        "book_health": runtime.book.health.value,
        "data_health": health.value,
        "audit_valid": audit_valid,
        "audit_issues": audit_issues,
        "audit_digest": audit_digest,
        "replay_digest": replay_digest,
        "live_feature_artifact": live_feature_artifact,
        "episode_policy": ({"policy_id": episode_policy.policy_id, "sha256": episode_policy.digest} if episode_policy is not None else {"status": "DEVELOPMENT_DEFAULT_UNBOUND"}),
    })
    summary = {
        "raw_captured": len(collection_raw),
        "availability_written": len(collection_availability),
        "parse_errors": stats.parse_errors,
        "book_gaps": stats.book_gaps,
        "snapshot_fetches": stats.snapshot_fetches,
        "open_interest_polls": stats.open_interest_polls,
        "exchange_info_fetches": stats.exchange_info_fetches,
        "exchange_info_status": stats.exchange_info_status,
        "exchange_info_filter_count": stats.exchange_info_filter_count,
        "connection_attempts": stats.connection_attempts,
        "reconnects": stats.reconnects,
        "discarded_stale_snapshots": stats.discarded_stale_snapshots,
        "errors": errors,
        "book_health": runtime.book.health.value,
        "data_health": health.value,
        "audit_valid": audit_valid,
        "collection_manifest": str(manifest),
        "configured_streams": configured_streams,
        "source_registry": registry_binding,
        "collector_software": software_binding,
        "live_feature_artifact": live_feature_artifact,
        "episode_policy": ({"policy_id": episode_policy.policy_id, "sha256": episode_policy.digest} if episode_policy is not None else {"status": "DEVELOPMENT_DEFAULT_UNBOUND"}),
    }
    return summary, (0 if succeeded else (130 if interrupted else 1))


def command_collect_public(args: argparse.Namespace) -> int:
    summary, result = _collect_public(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def command_collect_planned_public(args: argparse.Namespace) -> int:
    """Compatibility adapter for one explicitly selected frozen slot."""
    report, result = run_planned_capture(
        PlannedCaptureRequest(
            capture_plan_path=Path(args.capture_plan),
            capture_slot=args.capture_slot,
            data_root=Path(args.data_root),
            source_registry_path=Path(args.source_registry),
            duration_seconds=args.duration_seconds,
            snapshot_limit=args.snapshot_limit,
            oi_poll_seconds=args.oi_poll_seconds,
            metadata_poll_seconds=args.metadata_poll_seconds,
            live_feature_output=args.live_feature_output,
            episode_policy=args.episode_policy,
        ),
        collector=_collect_public,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def command_supervise_capture_once(args: argparse.Namespace) -> int:
    """Run at most one due slot; otherwise return a cheap scheduling decision."""
    plan = ForwardCapturePlan.load(Path(args.capture_plan))
    registry = SourceRegistry.load(Path(args.source_registry))
    if registry.registry_id != plan.source_registry_id or registry.sha256 != plan.source_registry_sha256:
        raise ValueError("capture supervisor source registry does not match frozen plan")
    decision = decide_capture_slot(plan, data_root=Path(args.data_root), now=utc_now())
    if decision.action != "RUN_SLOT":
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if decision.action in {"RESOURCE_BLOCKED", "PLAN_EXHAUSTED"} else 0
    report, result = run_planned_capture(
        PlannedCaptureRequest(
            capture_plan_path=Path(args.capture_plan),
            capture_slot=str(decision.slot_id),
            data_root=Path(args.data_root),
            source_registry_path=Path(args.source_registry),
            snapshot_limit=args.snapshot_limit,
            oi_poll_seconds=args.oi_poll_seconds,
            metadata_poll_seconds=args.metadata_poll_seconds,
            live_feature_output=args.live_feature_output,
            episode_policy=args.episode_policy,
        ),
        collector=_collect_public,
        now=decision.decided_at,
    )
    print(json.dumps({"supervisor": decision.to_dict(), "capture": report}, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def command_recover_interrupted_collection(args: argparse.Namespace) -> int:
    """Terminally mark already-stopped orphan raw evidence as unqualified.

    This is intentionally a recovery record, not a way to manufacture a
    qualified collection after a process died before writing its own manifest.
    The operator must separately seal the stopped raw segment before auditing.
    """
    if not args.confirm_stopped:
        raise ValueError("recovery requires --confirm-stopped after verifying the collector is no longer writing")
    store = EventStore(Path(args.data_dir))
    registry = SourceRegistry.load(Path(args.source_registry))
    configured_streams = public_configured_streams(args.instrument)
    binding = registry.manifest_binding(args.instrument, configured_streams)
    raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(args.connection_id + "-")]
    if not raws:
        raise ValueError("no raw records found for collection prefix: %s" % args.connection_id)
    event_ids = {raw.event_id for raw in raws}
    all_availability = list(store.iter_availability())
    availability = [record for record in all_availability if record.event_id in event_ids]
    orphaned_availability = [
        record.event_id for record in all_availability
        if ("/" + args.connection_id + "-") in record.event_id and record.event_id not in event_ids
    ]
    # A stopped-process acknowledgement is necessary but not sufficient: make
    # two local consistency observations before creating an immutable recovery
    # record.  If a writer is still active, ask the operator to stop it rather
    # than snapshotting a moving target into a terminal manifest.
    second_raw_ids = {
        raw.event_id for raw in store.iter_raw()
        if raw.connection_id.startswith(args.connection_id + "-")
    }
    if orphaned_availability or second_raw_ids != event_ids:
        raise ValueError("collection evidence changed or is inconsistent during recovery; verify the collector has stopped before retrying")
    metadata = [record for record in availability if record.normalized.get("kind") == "exchange_info"]
    latest_metadata = metadata[-1].normalized if metadata else {}
    audit_valid, audit_issues, audit_digest = store.audit()
    try:
        replay_digest = DeterministicReplay(store).digest()
    except ValueError as exc:
        raise ValueError("collection evidence is not stable enough to recover") from exc
    duration = max(raw.receive_time for raw in raws) - min(raw.receive_time for raw in raws)
    manifest = store.write_collection_manifest(args.connection_id, {
        "schema_version": "collection-manifest-v1",
        "instrument": args.instrument.upper(),
        "venue": "BINANCE_USDM",
        "transport_urls": stream_urls(args.instrument),
        "configured_streams": configured_streams,
        "source_registry": binding,
        "source_observation_samples": _source_observation_samples(store, registry, args.instrument, configured_streams),
        "duration_seconds": duration.total_seconds(),
        "collection_result": "UNQUALIFIED",
        "raw_captured": len(raws),
        "availability_written": len(availability),
        "parse_errors": len(raws) - len(availability),
        "book_gaps": 0,
        "snapshot_fetches": sum(raw.stream == "snapshot" for raw in raws),
        "open_interest_polls": sum(raw.stream == "openInterest" for raw in raws),
        "exchange_info_fetches": len(metadata),
        "exchange_info_status": latest_metadata.get("status"),
        "exchange_info_filter_count": len(latest_metadata.get("filters", [])),
        "connection_attempts": {},
        "reconnects": {},
        "discarded_stale_snapshots": 0,
        "errors": ["RECOVERED_AFTER_ABNORMAL_TERMINATION: %s" % args.reason],
        "book_health": "UNKNOWN_AFTER_ABNORMAL_TERMINATION",
        "data_health": "HALTED",
        "audit_valid": audit_valid,
        "audit_issues": audit_issues,
        "audit_digest": audit_digest,
        "replay_digest": replay_digest,
        "recovery": {
            "status": "RECOVERED_UNQUALIFIED",
            "operator_confirmed_stopped": True,
            "limitations": [
                "runtime counters, reconnects and book-gap status cannot be reconstructed from orphan raw evidence",
                "this manifest cannot qualify for G1, even if the recovered raw segment is later sealed",
            ],
        },
    })
    print(json.dumps({
        "collection_manifest": str(manifest),
        "collection_result": "UNQUALIFIED",
        "raw_captured": len(raws),
        "availability_written": len(availability),
        "audit_valid": audit_valid,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1


def _emit_research_report(args: argparse.Namespace, report: Dict[str, Any], *, protocol, classifier, g1_report, state_label_manifest=None, emit: bool = True) -> Dict[str, Any]:
    """Emit stdout and optionally persist a write-once research artifact."""
    output = dict(report)
    if args.require_frozen_protocol:
        output["evidence_binding"] = {
            "input_path": str(args.input),
            "input_sha256": sha256_file(Path(args.input)),
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": protocol.digest,
            "g1_report_sha256": g1_report["report_sha256"],
            "state_classifier_id": classifier.classifier_id,
            "state_classifier_sha256": classifier.digest,
            "state_label_manifest_sha256": state_label_manifest["manifest_sha256"],
            "label_bundle_manifest_sha256": state_label_manifest["label_bundle_manifest_sha256"],
        }
    if args.output:
        persisted = write_research_report(Path(args.output), output)
        output["research_report_path"] = str(args.output)
        output["research_report_sha256"] = persisted["report_sha256"]
    if emit:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return output


def command_research_baseline(args: argparse.Namespace) -> int:
    protocol = None
    classifier = None
    passed_g1_report = None
    state_label_manifest = None
    effective_folds = args.folds if args.folds is not None else 3
    effective_embargo_seconds = args.embargo_seconds if args.embargo_seconds is not None else 60
    if args.protocol:
        protocol = ResearchProtocol.load(Path(args.protocol))
        if args.require_frozen_protocol:
            protocol.assert_frozen_for_research()
            if not args.g1_report:
                raise ValueError("--require-frozen-protocol also requires --g1-report")
            if not args.output:
                raise ValueError("--require-frozen-protocol also requires --output")
            eligibility = protocol.g1_qualification
            passed_g1_report = load_passed_g1_report(
                Path(args.g1_report),
                policy_id=str(eligibility["required_g1_policy_id"]),
                expected_sha256=str(eligibility["required_g1_report_sha256"]),
                expected_policy_sha256=str(eligibility.get("required_g1_policy_sha256", "")),
            )
            if not args.state_classifier:
                raise ValueError("--require-frozen-protocol also requires --state-classifier")
            classifier = StateClassifier.load(Path(args.state_classifier))
            state_policy = protocol.raw["state_coverage_policy"]
            if classifier.classifier_id != state_policy["classifier_id"] or classifier.digest != state_policy["classifier_digest"]:
                raise ValueError("state classifier does not match frozen protocol")
            if set(classifier.state_ids) != set(state_policy["required_state_ids"]):
                raise ValueError("state classifier state IDs do not match frozen protocol")
            if not args.labels_manifest:
                raise ValueError("--require-frozen-protocol also requires --labels-manifest")
            state_label_manifest = load_verified_state_label_bundle_manifest(
                Path(args.labels_manifest), labels_path=Path(args.input), classifier=classifier,
            )
            if protocol.raw.get("schema_version") == V2_SCHEMA_VERSION:
                if not args.evidence_admission:
                    raise ValueError("frozen protocol v2 development research requires --evidence-admission")
                try:
                    load_verified_research_evidence_admission(
                        Path(args.evidence_admission), state_labels_path=Path(args.input), protocol=protocol, role="DEVELOPMENT",
                        state_label_manifest_sha256=state_label_manifest["manifest_sha256"],
                    )
                except ResearchEvidenceAdmissionError as exc:
                    raise ValueError(str(exc)) from exc
            else:
                if state_label_manifest["g1_policy_id"] != eligibility["required_g1_policy_id"]:
                    raise ValueError("state-label bundle G1 policy does not match frozen protocol")
                if state_label_manifest["g1_report_sha256"] != passed_g1_report["report_sha256"]:
                    raise ValueError("state-label bundle G1 report does not match frozen protocol")
            split_policy = protocol.raw["split_policy"]
            frozen_folds = int(split_policy["folds"])
            frozen_embargo_seconds = int(float(split_policy["embargo_seconds"]))
            if args.folds is not None and args.folds != frozen_folds:
                raise ValueError("--folds does not match frozen protocol")
            if args.embargo_seconds is not None and args.embargo_seconds != frozen_embargo_seconds:
                raise ValueError("--embargo-seconds does not match frozen protocol")
            effective_folds = frozen_folds
            effective_embargo_seconds = frozen_embargo_seconds
    rows = []
    input_rows = 0
    excluded_rows = 0
    with Path(args.input).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                input_rows += 1
                # A no-fill is an execution observation, while a censored
                # path has no valid market outcome. Neither may be converted
                # to a timeout just to make a classifier accept the row.
                if value.get("censored") or value.get("outcome") is None:
                    excluded_rows += 1
                    continue
                features = {key: float(item) for key, item in value["features"].items()}
                state_id = str(value.get("state_id", "UNASSIGNED"))
                if classifier is not None:
                    if value.get("state_classifier_id") != classifier.classifier_id or value.get("state_classifier_sha256") != classifier.digest:
                        raise ValueError("research row at line %d is not bound to the frozen state classifier" % line_number)
                    if classifier.classify(features) != state_id:
                        raise ValueError("research row at line %d state assignment does not match the frozen classifier" % line_number)
                rows.append(LabeledObservation(
                    episode_id=str(value["episode_id"]),
                    decision_at=parse_utc(value["decision_at"]),
                    label_end_at=parse_utc(value["label_end_at"]),
                    features=features,
                    outcome=MarketOutcome(value["outcome"]),
                    state_id=state_id,
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("invalid research row at line %d: %s" % (line_number, exc)) from exc
    if args.features:
        feature_names = tuple(name.strip() for name in args.features.split(",") if name.strip())
    else:
        feature_names = tuple(sorted({name for row in rows for name in row.features}))
    if not rows:
        raise ValueError("no eligible filled, uncensored research rows")
    if protocol is not None and protocol.is_frozen_for_research:
        holdout = protocol.raw["split_policy"]["final_holdout"]
        holdout_start = parse_utc(str(holdout["start"]))
        unsafe_rows = [row.episode_id for row in rows if row.label_end_at > holdout_start]
        if unsafe_rows:
            raise ValueError(
                "frozen baseline input contains final-holdout, overlapping, or post-holdout labels; "
                "keep development research strictly pre-holdout and open the holdout through its one-time ledger"
            )
        coverage_policy = protocol.raw["state_coverage_policy"]
        coverage = assess_state_coverage(
            rows,
            required_state_ids=coverage_policy["required_state_ids"],
            min_effective_episodes_per_state=int(coverage_policy["min_effective_episodes_per_state"]),
        )
        if not coverage.passed:
            _emit_research_report(args, {
                "input_rows": input_rows,
                "eligible_observations": len(rows),
                "excluded_execution_or_censored": excluded_rows,
                "protocol_id": protocol.protocol_id,
                "protocol_status": protocol.status,
                "frozen_for_research": True,
                "research_status": "INCONCLUSIVE/WAIT_DATA",
                "state_coverage": {
                    "required_state_ids": coverage.required_state_ids,
                    "observations_by_state": coverage.observations_by_state,
                    "min_effective_episodes_per_state": coverage.min_effective_episodes_per_state,
                    "missing_state_ids": coverage.missing_state_ids,
                    "unexpected_state_ids": coverage.unexpected_state_ids,
                    "passed": False,
                },
            }, protocol=protocol, classifier=classifier, g1_report=passed_g1_report, state_label_manifest=state_label_manifest)
            return 1
        minimum_effective_episodes = int(protocol.raw["evaluation_policy"]["min_effective_episodes"])
        if len(rows) < minimum_effective_episodes:
            _emit_research_report(args, {
                "input_rows": input_rows,
                "eligible_observations": len(rows),
                "excluded_execution_or_censored": excluded_rows,
                "protocol_id": protocol.protocol_id,
                "protocol_status": protocol.status,
                "frozen_for_research": True,
                "research_status": "INCONCLUSIVE/WAIT_DATA",
                "reason": "effective episode count below frozen protocol minimum",
                "minimum_effective_episodes": minimum_effective_episodes,
                "state_coverage": {
                    "required_state_ids": coverage.required_state_ids,
                    "observations_by_state": coverage.observations_by_state,
                    "min_effective_episodes_per_state": coverage.min_effective_episodes_per_state,
                    "missing_state_ids": coverage.missing_state_ids,
                    "unexpected_state_ids": coverage.unexpected_state_ids,
                    "passed": True,
                },
            }, protocol=protocol, classifier=classifier, g1_report=passed_g1_report, state_label_manifest=state_label_manifest)
            return 1
    report = run_walk_forward_baseline(
        rows,
        feature_names=feature_names,
        folds=effective_folds,
        embargo=timedelta(seconds=effective_embargo_seconds),
    )
    _emit_research_report(args, {
        "input_rows": input_rows,
        "eligible_observations": len(rows),
        "excluded_execution_or_censored": excluded_rows,
        "features": feature_names,
        "fold_count": effective_folds,
        "embargo_seconds": effective_embargo_seconds,
        "folds": [item.__dict__ for item in report.folds],
        "mean_log_loss": report.mean_log_loss,
        "mean_brier": report.mean_brier,
        "protocol_id": protocol.protocol_id if protocol else None,
        "protocol_status": protocol.status if protocol else "UNSPECIFIED_DEVELOPMENT_RUN",
        "frozen_for_research": protocol.is_frozen_for_research if protocol else False,
        "research_status": "EVALUATED_DEVELOPMENT" if not protocol or not protocol.is_frozen_for_research else "EVALUATED_FROZEN_PROTOCOL",
    }, protocol=protocol, classifier=classifier, g1_report=passed_g1_report, state_label_manifest=state_label_manifest)
    return 0


def command_evaluate_final_holdout(args: argparse.Namespace) -> int:
    """Score the fixed baseline once on an already-opened final holdout."""
    protocol = ResearchProtocol.load(Path(args.protocol))
    protocol.assert_frozen_for_research()
    if not args.output:
        raise ValueError("final holdout evaluation requires --output")
    eligibility = protocol.g1_qualification
    passed_g1_report = load_passed_g1_report(
        Path(args.g1_report),
        policy_id=str(eligibility["required_g1_policy_id"]),
        expected_sha256=str(eligibility["required_g1_report_sha256"]),
        expected_policy_sha256=str(eligibility.get("required_g1_policy_sha256", "")),
    )
    classifier = StateClassifier.load(Path(args.state_classifier))
    state_policy = protocol.raw["state_coverage_policy"]
    if classifier.classifier_id != state_policy["classifier_id"] or classifier.digest != state_policy["classifier_digest"]:
        raise ValueError("state classifier does not match frozen protocol")
    state_label_manifest = load_verified_state_label_bundle_manifest(
        Path(args.labels_manifest), labels_path=Path(args.input), classifier=classifier,
    )
    holdout_admission = development_admission = None
    if protocol.raw.get("schema_version") == V2_SCHEMA_VERSION:
        if not args.holdout_evidence_admission or not args.development_evidence_admission or not args.development_input:
            raise ValueError("protocol v2 final evaluation requires holdout/development evidence admissions and --development-input")
        try:
            holdout_admission = load_verified_research_evidence_admission(
                Path(args.holdout_evidence_admission), state_labels_path=Path(args.input), protocol=protocol, role="HOLDOUT",
                state_label_manifest_sha256=state_label_manifest["manifest_sha256"],
            )
            if not args.development_labels_manifest:
                raise ValueError("protocol v2 final evaluation requires --development-labels-manifest")
            development_manifest = load_verified_state_label_bundle_manifest(
                Path(args.development_labels_manifest), labels_path=Path(args.development_input), classifier=classifier,
            )
            development_admission = load_verified_research_evidence_admission(
                Path(args.development_evidence_admission), state_labels_path=Path(args.development_input), protocol=protocol, role="DEVELOPMENT",
                state_label_manifest_sha256=development_manifest["manifest_sha256"],
            )
        except ResearchEvidenceAdmissionError as exc:
            raise ValueError(str(exc)) from exc
    elif state_label_manifest["g1_policy_id"] != eligibility["required_g1_policy_id"] or state_label_manifest["g1_report_sha256"] != passed_g1_report["report_sha256"]:
        raise ValueError("state-label bundle does not match frozen G1 evidence")
    release_verification = verify_final_holdout_release(
        protocol=protocol, labels_path=Path(args.input), registry_dir=Path(args.holdout_registry), release_path=Path(args.holdout_release), evidence_admission=holdout_admission,
    )
    if not release_verification["valid"]:
        raise ValueError("final-holdout release does not match protocol, registry and exact labels input")
    holdout = protocol.raw["split_policy"]["final_holdout"]
    start, end = parse_utc(str(holdout["start"])), parse_utc(str(holdout["end"]))
    training, held_out = [], []
    input_rows = excluded_rows = 0
    sources = (("HOLDOUT", Path(args.input)),) if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION else (("DEVELOPMENT", Path(args.development_input)), ("HOLDOUT", Path(args.input)))
    for source_role, source_path in sources:
        with source_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    input_rows += 1
                    if value.get("censored") or value.get("outcome") is None:
                        excluded_rows += 1
                        continue
                    features = {key: float(item) for key, item in value["features"].items()}
                    state_id = str(value.get("state_id", "UNASSIGNED"))
                    if value.get("state_classifier_id") != classifier.classifier_id or value.get("state_classifier_sha256") != classifier.digest:
                        raise ValueError("row is not bound to frozen state classifier")
                    if classifier.classify(features) != state_id:
                        raise ValueError("row state assignment does not match frozen classifier")
                    row = LabeledObservation(
                        episode_id=str(value["episode_id"]), decision_at=parse_utc(value["decision_at"]),
                        label_end_at=parse_utc(value["label_end_at"]), features=features,
                        outcome=MarketOutcome(value["outcome"]), state_id=state_id,
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError("invalid %s row at line %d: %s" % (source_role.lower(), line_number, exc)) from exc
                if source_role == "DEVELOPMENT":
                    if row.label_end_at > start:
                        raise ValueError("DEVELOPMENT evidence contains final-holdout, overlapping, or post-holdout labels")
                    training.append(row)
                elif protocol.raw.get("schema_version") == V2_SCHEMA_VERSION:
                    if not (row.decision_at >= start and row.label_end_at <= end):
                        raise ValueError("HOLDOUT evidence contains pre-holdout, overlapping, or post-holdout eligible rows")
                    held_out.append(row)
                elif row.label_end_at <= start:
                    training.append(row)
                elif row.decision_at >= start and row.label_end_at <= end:
                    held_out.append(row)
                else:
                    raise ValueError("final-holdout input contains an overlapping or post-holdout eligible row")
    if not training or not held_out:
        raise ValueError("final-holdout evaluation needs both pre-holdout training rows and released holdout rows")
    feature_names = tuple(name.strip() for name in args.features.split(",") if name.strip()) if args.features else tuple(sorted({name for row in training for name in row.features}))
    training_coverage = assess_state_coverage(
        training, required_state_ids=state_policy["required_state_ids"],
        min_effective_episodes_per_state=int(state_policy["min_effective_episodes_per_state"]),
    )
    holdout_coverage = assess_state_coverage(
        held_out, required_state_ids=state_policy["required_state_ids"],
        min_effective_episodes_per_state=int(state_policy["min_effective_episodes_per_state"]),
    )
    minimum = int(protocol.raw["evaluation_policy"]["min_effective_episodes"])
    eligible_for_score = training_coverage.passed and holdout_coverage.passed and len(training) >= minimum and len(held_out) >= minimum
    report: Dict[str, Any] = {
        "input_rows": input_rows,
        "excluded_execution_or_censored": excluded_rows,
        "pre_holdout_eligible_observations": len(training),
        "holdout_eligible_observations": len(held_out),
        "features": feature_names,
        "protocol_id": protocol.protocol_id,
        "protocol_status": protocol.status,
        "frozen_for_research": True,
        "final_holdout_release_path": str(args.holdout_release),
        "final_holdout_registry": str(args.holdout_registry),
        "final_holdout_release_verified": True,
        "minimum_effective_episodes": minimum,
        "training_state_coverage": {"observations_by_state": training_coverage.observations_by_state, "missing_state_ids": training_coverage.missing_state_ids, "unexpected_state_ids": training_coverage.unexpected_state_ids, "passed": training_coverage.passed},
        "holdout_state_coverage": {"observations_by_state": holdout_coverage.observations_by_state, "missing_state_ids": holdout_coverage.missing_state_ids, "unexpected_state_ids": holdout_coverage.unexpected_state_ids, "passed": holdout_coverage.passed},
        "research_status": "FINAL_HOLDOUT_EVALUATION_REQUIRES_LEDGER_CONSUMPTION",
    }
    if eligible_for_score:
        final = run_final_holdout_baseline(training, held_out, feature_names=feature_names)
        report["final_holdout_metrics"] = final.metrics.__dict__
        report["final_holdout_baseline"] = {"training_observations": final.training_observations, "holdout_observations": final.holdout_observations}
        result_code = 0
    else:
        report["reason"] = "final holdout lacks frozen minimum or state coverage; receipt is still consumed because holdout labels were opened"
        result_code = 1
    emitted = _emit_research_report(
        args, report, protocol=protocol, classifier=classifier, g1_report=passed_g1_report,
        state_label_manifest=state_label_manifest, emit=False,
    )
    consumption = consume_final_holdout_release(
        protocol=protocol, labels_path=Path(args.input), registry_dir=Path(args.holdout_registry), release_path=Path(args.holdout_release),
        evaluation_report_path=Path(args.output), evaluation_report_sha256=sha256_file(Path(args.output)), evidence_admission=holdout_admission,
    )
    emitted["final_holdout_consumption"] = consumption
    print(json.dumps(emitted, ensure_ascii=False, indent=2, sort_keys=True))
    return result_code


def command_build_features(args: argparse.Namespace) -> int:
    store = EventStore(Path(args.data_dir))
    episode_policy = EpisodePolicy.load(Path(args.episode_policy)) if args.episode_policy else None
    rows = FeaturePipeline(episode_policy).replay(store, allow_reconstructed=args.allow_reconstructed)
    count = write_feature_rows(Path(args.output), rows)
    print(json.dumps({"feature_rows": count, "output": args.output, "allow_reconstructed": args.allow_reconstructed}, ensure_ascii=False, indent=2))
    return 0


def command_build_features_g1_bundle(args: argparse.Namespace) -> int:
    report = build_feature_bundle(
        data_dirs=tuple(Path(item) for item in args.data_dir),
        g1_report_path=Path(args.g1_report),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
        bundle_id=args.bundle_id,
        episode_policy_path=Path(args.episode_policy),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_write_data_acceptance_report(args: argparse.Namespace) -> int:
    policy = G1AcceptancePolicy.load(Path(args.acceptance_policy))
    plan = ForwardCapturePlan.load(Path(args.capture_plan))
    report = write_data_acceptance_report(
        Path(args.output), report_id=args.report_id, role=args.role, policy=policy, plan=plan,
        data_dirs=tuple(Path(item) for item in args.data_dir),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_build_features_role_bundle(args: argparse.Namespace) -> int:
    report = build_role_feature_bundle(
        protocol_path=Path(args.protocol), role=args.role, capture_plan_path=Path(args.capture_plan),
        acceptance_policy_path=Path(args.acceptance_policy), acceptance_report_path=Path(args.acceptance_report),
        baseline_g1_policy_path=Path(args.baseline_g1_policy), data_dirs=tuple(Path(item) for item in args.data_dir),
        output_path=Path(args.output), manifest_path=Path(args.manifest), bundle_id=args.bundle_id, episode_policy_path=Path(args.episode_policy),
        context_policy_path=Path(args.context_policy) if args.context_policy else None,
        role_window_path=Path(args.role_window) if args.role_window else None,
        context_output_path=Path(args.context_output) if args.context_output else None,
        context_manifest_path=Path(args.context_manifest) if args.context_manifest else None,
        archive_receipt_paths=tuple(Path(item) for item in args.archive_receipt),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_archive_sealed_collection(args: argparse.Namespace) -> int:
    store = EventStore(Path(args.data_dir), create=False)
    report = archive_sealed_collection(store=store, collection_id=args.collection_id, cold_root=Path(args.cold_root), archive_id=args.archive_id)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_verify_evidence_archive(args: argparse.Namespace) -> int:
    print(json.dumps(verify_evidence_archive(Path(args.receipt)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_verify_hot_cold_evidence(args: argparse.Namespace) -> int:
    store = EventStore(Path(args.data_dir), create=False)
    report = verify_hot_cold_equivalence(store=store, collection_id=args.collection_id, receipt_path=Path(args.receipt))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_admit_research_evidence(args: argparse.Namespace) -> int:
    report = admit_research_evidence(
        protocol_path=Path(args.protocol), role=args.role, capture_plan_path=Path(args.capture_plan), acceptance_policy_path=Path(args.acceptance_policy),
        acceptance_report_path=Path(args.acceptance_report), baseline_g1_policy_path=Path(args.baseline_g1_policy), g1_report_path=Path(args.g1_report),
        feature_path=Path(args.features), feature_manifest_path=Path(args.feature_manifest), actions_path=Path(args.actions), action_manifest_path=Path(args.action_manifest),
        labels_path=Path(args.labels), label_manifest_path=Path(args.label_manifest), state_labels_path=Path(args.state_labels), state_manifest_path=Path(args.state_manifest),
        classifier_path=Path(args.classifier), output_path=Path(args.output), admission_id=args.admission_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_evaluate_g2_protocol(args: argparse.Namespace) -> int:
    report = evaluate_protocol_g2(
        protocol_path=Path(args.protocol), evidence_admission_path=Path(args.evidence_admission),
        state_labels_path=Path(args.state_labels), state_manifest_path=Path(args.state_manifest),
        classifier_path=Path(args.state_classifier), feature_path=Path(args.features), feature_manifest_path=Path(args.feature_manifest), output_path=Path(args.output), as_of=args.as_of,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["overall_status"] == "G2_PASS" else 1


def command_seal_raw(args: argparse.Namespace) -> int:
    manifest = EventStore(Path(args.data_dir)).seal_raw_segment(args.segment)
    print(json.dumps({"sealed_manifest": str(manifest)}, ensure_ascii=False, indent=2))
    return 0


def command_seal_collection(args: argparse.Namespace) -> int:
    """Manually seal an already-stopped collection after checking writers."""
    if not args.confirm_no_other_writers:
        raise ValueError("sealing a collection requires --confirm-no-other-writers")
    result = seal_collection(EventStore(Path(args.data_dir)), args.collection_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_compare_shadow(args: argparse.Namespace) -> int:
    comparison = compare_feature_artifacts(Path(args.offline), Path(args.online))
    print(json.dumps({
        "passed": comparison.passed,
        "matched_rows": comparison.matched_rows,
        "missing_online": comparison.missing_online,
        "missing_offline": comparison.missing_offline,
        "version_mismatches": comparison.version_mismatches,
        "context_mismatches": comparison.context_mismatches,
        "value_mismatches": comparison.value_mismatches,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if comparison.passed else 1


def command_verify_live_feature_shadow(args: argparse.Namespace) -> int:
    """Recompute one sealed collection and compare it to its live artifact.

    This verifier is intentionally read-only.  It is narrower than G3: it
    proves only same-input feature/episode reproducibility for one sealed,
    isolated collection, not model quality, account state, or trade behavior.
    """
    store = EventStore(Path(args.data_dir), create=False)
    manifest_path = store.collection_manifest_root / (args.collection_id + ".json")
    try:
        collection = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot load collection manifest") from exc
    if not isinstance(collection, dict) or collection.get("record_type") != "collection_manifest" or collection.get("collection_id") != args.collection_id:
        raise ValueError("invalid collection manifest")
    if collection.get("collection_result") != "QUALIFIED_SMOKE":
        raise ValueError("live shadow requires a qualified collection")
    audit_valid, audit_issues, audit_digest = store.audit()
    if not audit_valid:
        raise ValueError("event-store audit failed: %s" % "; ".join(audit_issues))
    replay_digest = DeterministicReplay(store).digest()
    if collection.get("audit_digest") != audit_digest or collection.get("replay_digest") != replay_digest:
        raise ValueError("collection evidence has changed since its terminal manifest")
    raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(args.collection_id + "-")]
    if not raws:
        raise ValueError("collection has no raw evidence")
    sealed = {item.stem for item in store.manifest_root.glob("*.json")}
    if any(Path(raw.raw_segment).stem not in sealed for raw in raws):
        raise ValueError("live shadow requires every collection raw segment to be sealed")
    policy_binding = collection.get("episode_policy", {"status": "DEVELOPMENT_DEFAULT_UNBOUND"})
    episode_policy = EpisodePolicy.load(Path(args.episode_policy)) if args.episode_policy else None
    if policy_binding.get("status") == "DEVELOPMENT_DEFAULT_UNBOUND":
        if episode_policy is not None:
            raise ValueError("collection used the development episode default, not the supplied policy")
    elif episode_policy is None or policy_binding.get("policy_id") != episode_policy.policy_id or policy_binding.get("sha256") != episode_policy.digest:
        raise ValueError("supplied episode policy does not match collection manifest")
    artifact = verify_live_feature_artifact(Path(args.live_features), collection.get("live_feature_artifact"))
    offline = {row.event_id: row.to_dict() for row in FeaturePipeline(episode_policy).replay_collection(store, args.collection_id)}
    comparison = compare_feature_row_maps(offline, load_feature_rows(Path(args.live_features)))
    output = {
        "collection_id": args.collection_id,
        "audit_digest": audit_digest,
        "replay_digest": replay_digest,
        "live_feature_artifact": artifact,
        "episode_policy": policy_binding,
        "passed": comparison.passed and comparison.matched_rows > 0,
        "matched_rows": comparison.matched_rows,
        "missing_online": comparison.missing_online,
        "missing_offline": comparison.missing_offline,
        "version_mismatches": comparison.version_mismatches,
        "context_mismatches": comparison.context_mismatches,
        "value_mismatches": comparison.value_mismatches,
        "limitation": "This checks one sealed collection's local feature/episode replay equivalence only; it is not G3, model validation, account reconciliation, or trading authorization.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if output["passed"] else 1


def command_verify_shadow_decision_artifact(args: argparse.Namespace) -> int:
    report = verify_shadow_decision_artifact(
        decisions_path=Path(args.decisions),
        features_path=Path(args.features),
        model_artifact_path=Path(args.model_artifact),
        action_policy_path=Path(args.action_policy),
        risk_gate_profile_path=Path(args.risk_gate_profile),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_inventory_collections(args: argparse.Namespace) -> int:
    report = inventory_collections(tuple(Path(item) for item in args.data_root))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_describe_sealed_features(args: argparse.Namespace) -> int:
    report = describe_sealed_features(tuple(Path(item) for item in args.data_root))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_research_readiness(args: argparse.Namespace) -> int:
    report = build_research_readiness(
        tuple(Path(item) for item in args.data_root),
        g1_policy_path=Path(args.g1_policy),
        research_protocol_path=Path(args.research_protocol),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["readiness"] == "READY_FOR_G1_BUNDLE_VERIFICATION" else 1


def command_compare_shadow_decisions(args: argparse.Namespace) -> int:
    comparison = compare_decision_artifacts(Path(args.offline), Path(args.online))
    print(json.dumps({
        "passed": comparison.passed,
        "matched_rows": comparison.matched_rows,
        "missing_online": comparison.missing_online,
        "missing_offline": comparison.missing_offline,
        "version_mismatches": comparison.version_mismatches,
        "decision_mismatches": comparison.decision_mismatches,
        "value_mismatches": comparison.value_mismatches,
        "limitation": "This compares supplied local decision artifacts; it does not prove forward duration, market coverage, account reconciliation, or exchange execution.",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if comparison.passed else 1


def command_audit_paper_run(args: argparse.Namespace) -> int:
    report = audit_paper_trail(Path(args.input))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_validate_paper_run_contract(args: argparse.Namespace) -> int:
    contract = PaperRunContract.load(Path(args.contract))
    print(json.dumps(contract.summary(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_verify_paper_run_binding(args: argparse.Namespace) -> int:
    contract = PaperRunContract.load(Path(args.contract))
    report = verify_paper_run_binding(Path(args.audit), contract)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_verify_paper_run_evidence(args: argparse.Namespace) -> int:
    contract = PaperRunContract.load(Path(args.contract))
    report = verify_paper_run_evidence(
        contract,
        model_artifact_path=Path(args.model_artifact),
        action_policy_path=Path(args.action_policy),
        risk_gate_profile_path=Path(args.risk_gate_profile),
        source_registry_path=Path(args.source_registry),
        state_classifier_path=Path(args.state_classifier),
        input_evidence_path=Path(args.input_evidence),
        input_evidence_id=args.input_evidence_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_seal_paper_run(args: argparse.Namespace) -> int:
    contract = PaperRunContract.load(Path(args.contract))
    report = seal_paper_run(Path(args.audit), contract, Path(args.output))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_recover_paper_run(args: argparse.Namespace) -> int:
    report = write_paper_recovery_report(
        Path(args.input),
        Path(args.output),
        confirm_process_stopped=args.confirm_process_stopped,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1


def command_verify_paper_recovery(args: argparse.Namespace) -> int:
    report = verify_paper_recovery_report(Path(args.input), Path(args.audit))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_label_actions(args: argparse.Namespace) -> int:
    actions = load_actions(Path(args.actions))
    points = load_feature_prices(Path(args.features), allow_reconstructed=args.allow_reconstructed)
    rows = generate_labels(actions, points)
    count = write_label_rows(Path(args.output), rows)
    summary = {
        "labels_written": count,
        "output": args.output,
        "market_path_source": "FEATURE_MID_PRICE",
        "allow_reconstructed": args.allow_reconstructed,
        "market_labeled": sum(1 for row in rows if row["outcome"] is not None),
        "censored": sum(1 for row in rows if row["censored"]),
        "no_fill": sum(1 for row in rows if row.get("execution_outcome") == "NO_FILL" or row.get("fill_fraction") == "0"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_label_actions_g1_bundle(args: argparse.Namespace) -> int:
    report = build_label_bundle(
        actions_path=Path(args.actions),
        action_manifest_path=Path(args.action_manifest),
        feature_path=Path(args.features),
        feature_manifest_path=Path(args.feature_manifest),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
        labels_id=args.labels_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_build_actions_g1_bundle(args: argparse.Namespace) -> int:
    report = build_action_bundle(
        feature_path=Path(args.features),
        feature_manifest_path=Path(args.feature_manifest),
        policy_path=Path(args.action_policy),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
        actions_id=args.actions_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_assign_states(args: argparse.Namespace) -> int:
    """Write a new label artifact with deterministic state assignments."""
    classifier = StateClassifier.load(Path(args.classifier))
    output = Path(args.output)
    if output.exists():
        raise ValueError("state-assigned label artifact already exists: %s" % output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with Path(args.input).open("r", encoding="utf-8") as source, output.open("x", encoding="utf-8") as destination:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get("features"), dict):
                    raise ValueError("label row needs a feature object")
                features = {key: float(value) for key, value in row["features"].items()}
                row["state_id"] = classifier.classify(features)
                row["state_classifier_id"] = classifier.classifier_id
                row["state_classifier_sha256"] = classifier.digest
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("invalid label row at line %d: %s" % (line_number, exc)) from exc
            destination.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    print(json.dumps({
        "labels_written": count,
        "output": str(output),
        "classifier_id": classifier.classifier_id,
        "classifier_sha256": classifier.digest,
        "state_ids": classifier.state_ids,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_assign_states_g1_bundle(args: argparse.Namespace) -> int:
    report = build_state_label_bundle(
        labels_path=Path(args.input),
        label_manifest_path=Path(args.label_manifest),
        classifier_path=Path(args.classifier),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
        state_labels_id=args.state_labels_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_cost_pressure(args: argparse.Namespace) -> int:
    """Evaluate frozen forecast assumptions across declared cost scenarios."""
    with Path(args.input).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    try:
        outcome = OutcomeForecast(
            _decimal(raw["outcome"]["tp"]),
            _decimal(raw["outcome"]["sl"]),
            _decimal(raw["outcome"]["structure_exit"]),
            _decimal(raw["outcome"]["timeout"]),
        )
        execution = ExecutionForecast(
            _decimal(raw["execution"]["fill_probability"]),
            _decimal(raw["execution"]["expected_fill_fraction"]),
            Decimal("0"),
            Decimal("0"),
        )
        scenarios = tuple(CostScenario(
            scenario_id=str(item["scenario_id"]),
            entry_fee_rate=_decimal(item["entry_fee_rate"]),
            exit_fee_rate=_decimal(item["exit_fee_rate"]),
            spread_bps=_decimal(item["spread_bps"]),
            conditional_slippage_bps=_decimal(item["conditional_slippage_bps"]),
            funding_bps=_decimal(item["funding_bps"]),
            tail_execution_bps=_decimal(item["tail_execution_bps"]),
            submit_cost=_decimal(item.get("submit_cost", 0)),
            no_fill_cost=_decimal(item.get("no_fill_cost", 0)),
        ) for item in raw["scenarios"])
        results = evaluate_cost_pressure(
            scenarios=scenarios,
            policy=ConservativePolicy(_decimal(raw["minimum_submit_ev"])),
            entry_price=_decimal(raw["entry_price"]),
            quantity=_decimal(raw["quantity"]),
            outcome=outcome,
            execution=execution,
            gain_if_tp=_decimal(raw["gain_if_tp"]),
            loss_if_sl=_decimal(raw["loss_if_sl"]),
            expected_structure_return=_decimal(raw["expected_structure_return"]),
            expected_timeout_return=_decimal(raw["expected_timeout_return"]),
            gate_level=GateLevel[raw.get("gate_level", "OPEN")],
            data_healthy=bool(raw.get("data_healthy", True)),
            model_applicable=bool(raw.get("model_applicable", True)),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cost-pressure input: %s" % exc) from exc
    print(json.dumps({
        "input": args.input,
        "results": [{
            "scenario_id": item.scenario_id,
            "cost": {
                "fee": str(item.cost.fee),
                "spread": str(item.cost.spread),
                "conditional_slippage": str(item.cost.conditional_slippage),
                "funding": str(item.cost.funding),
                "tail_execution": str(item.cost.tail_execution),
                "total": str(item.cost.total),
            },
            "decision": {
                "trade": item.decision.trade,
                "reason": item.decision.reason,
                "ev_fill": str(item.decision.ev_fill),
                "ev_submit": str(item.decision.ev_submit),
            },
        } for item in results],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_coverage(args: argparse.Namespace) -> int:
    report = build_coverage_report(EventStore(Path(args.data_dir)))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["audit_valid"] else 1


def command_validate_g1(args: argparse.Namespace) -> int:
    policy = G1AcceptancePolicy.load(Path(args.policy))
    report = validate_g1_data(EventStore(Path(args.data_dir)), policy)
    if args.output:
        persisted = write_g1_report(Path(args.output), report)
        report = dict(report)
        report["g1_report_path"] = str(args.output)
        report["g1_report_sha256"] = persisted["report_sha256"]
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def command_validate_g1_bundle(args: argparse.Namespace) -> int:
    policy = G1AcceptancePolicy.load(Path(args.policy))
    report = validate_g1_stores(tuple(EventStore(Path(data_dir)) for data_dir in args.data_dir), policy)
    if args.output:
        persisted = write_g1_report(Path(args.output), report)
        report = dict(report)
        report["g1_report_path"] = str(args.output)
        report["g1_report_sha256"] = persisted["report_sha256"]
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def command_validate_source_registry(args: argparse.Namespace) -> int:
    registry = SourceRegistry.load(Path(args.source_registry))
    result: Dict[str, Any] = {
        "registry_id": registry.registry_id,
        "schema_version": registry.schema_version,
        "status": registry.status,
        "frozen_at": registry.frozen_at,
        "sha256": registry.sha256,
        "source_ids": [source.source_id for source in registry.sources],
    }
    if args.configured_stream:
        result["capture_binding"] = registry.manifest_binding(args.instrument, args.configured_stream)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_validate_account_telemetry_contract(args: argparse.Namespace) -> int:
    contract = AccountTelemetryContract.load(Path(args.contract))
    print(json.dumps(contract.summary(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_audit_account_telemetry(args: argparse.Namespace) -> int:
    contract = AccountTelemetryContract.load(Path(args.contract))
    report = audit_normalized_telemetry(Path(args.input), contract)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_normalize_account_telemetry(args: argparse.Namespace) -> int:
    contract = AccountTelemetryContract.load(Path(args.contract))
    report = normalize_sanitized_telemetry(Path(args.input), Path(args.output), contract)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_open_final_holdout(args: argparse.Namespace) -> int:
    protocol = ResearchProtocol.load(Path(args.protocol))
    admission = None
    if protocol.raw.get("schema_version") == V2_SCHEMA_VERSION:
        if not args.evidence_admission or not args.labels_manifest or not args.state_classifier:
            raise ValueError("protocol v2 final holdout requires --evidence-admission, --labels-manifest and --state-classifier")
        try:
            state_manifest = load_verified_state_label_bundle_manifest(
                Path(args.labels_manifest), labels_path=Path(args.labels), classifier=StateClassifier.load(Path(args.state_classifier)),
            )
            admission = load_verified_research_evidence_admission(
                Path(args.evidence_admission), state_labels_path=Path(args.labels), protocol=protocol, role="HOLDOUT",
                state_label_manifest_sha256=state_manifest["manifest_sha256"],
            )
        except ResearchEvidenceAdmissionError as exc:
            raise ValueError(str(exc)) from exc
    report = open_final_holdout(
        protocol=protocol,
        labels_path=Path(args.labels),
        registry_dir=Path(args.registry_dir),
        output_path=Path(args.output),
        confirm_release_candidate=args.confirm_release_candidate,
        confirm_no_other_writers=args.confirm_no_other_writers,
        evidence_admission=admission,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_verify_final_holdout(args: argparse.Namespace) -> int:
    protocol = ResearchProtocol.load(Path(args.protocol))
    admission = None
    if protocol.raw.get("schema_version") == V2_SCHEMA_VERSION:
        if not args.evidence_admission or not args.labels_manifest or not args.state_classifier:
            raise ValueError("protocol v2 final holdout requires --evidence-admission, --labels-manifest and --state-classifier")
        try:
            state_manifest = load_verified_state_label_bundle_manifest(
                Path(args.labels_manifest), labels_path=Path(args.labels), classifier=StateClassifier.load(Path(args.state_classifier)),
            )
            admission = load_verified_research_evidence_admission(
                Path(args.evidence_admission), state_labels_path=Path(args.labels), protocol=protocol, role="HOLDOUT",
                state_label_manifest_sha256=state_manifest["manifest_sha256"],
            )
        except ResearchEvidenceAdmissionError as exc:
            raise ValueError(str(exc)) from exc
    report = verify_final_holdout_release(
        protocol=protocol,
        labels_path=Path(args.labels),
        registry_dir=Path(args.registry_dir),
        release_path=Path(args.input),
        evidence_admission=admission,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def command_reconcile_paper_recovery_telemetry(args: argparse.Namespace) -> int:
    verification = verify_paper_recovery_report(Path(args.recovery_report), Path(args.paper_audit))
    if not verification["valid"]:
        raise ValueError("recovery report does not match the supplied interrupted paper audit")
    try:
        recovery_report = json.loads(Path(args.recovery_report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot load verified recovery report") from exc
    contract = AccountTelemetryContract.load(Path(args.contract))
    report = write_recovery_telemetry_reconciliation_report(
        Path(args.output),
        recovery_report_path=Path(args.recovery_report),
        recovery_report=recovery_report,
        telemetry_path=Path(args.telemetry),
        contract=contract,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    # Even a local match cannot clear the frozen/manual recovery gate.
    return 1


def command_validate_risk_gate_profile(args: argparse.Namespace) -> int:
    profile = RiskGateProfile.load(Path(args.profile))
    print(json.dumps(profile.summary(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_validate_state_classifier(args: argparse.Namespace) -> int:
    classifier = StateClassifier.load(Path(args.classifier))
    print(json.dumps({
        "classifier_id": classifier.classifier_id,
        "status": classifier.status,
        "sha256": classifier.digest,
        "state_ids": classifier.state_ids,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_validate_action_policy(args: argparse.Namespace) -> int:
    policy = ResearchActionPolicy.load(Path(args.policy))
    print(json.dumps({
        "policy_id": policy.policy_id,
        "frozen_at": policy.frozen_at,
        "sha256": policy.digest,
        "feature_bundle_manifest_sha256": policy.feature_bundle_manifest_sha256,
        "min_seconds_between_actions": str(policy.min_seconds_between_actions),
        "rules": [rule.rule_id for rule in policy.rules],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_validate_capture_plan(args: argparse.Namespace) -> int:
    plan = ForwardCapturePlan.load(Path(args.plan))
    print(json.dumps({
        "plan_id": plan.plan_id,
        "frozen_at": plan.frozen_at.isoformat(),
        "instrument": plan.instrument,
        "source_registry": {"registry_id": plan.source_registry_id, "sha256": plan.source_registry_sha256},
        "sha256": plan.digest,
        "slots": [{
            "slot_id": slot.slot_id,
            "start": slot.start.isoformat(),
            "end": slot.end.isoformat(),
            "min_duration_seconds": slot.min_duration_seconds,
            "coverage_intent": slot.coverage_intent,
        } for slot in plan.slots],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_capture_plan_status(args: argparse.Namespace) -> int:
    plan = ForwardCapturePlan.load(Path(args.plan))
    now = parse_utc(args.now) if args.now else utc_now()
    report = inspect_forward_capture_plan(plan, data_root=Path(args.data_root), now=now)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not args.require_all_sealed or report["all_slots_sealed"] else 1


def command_audit_okx_historical(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = HistoricalAuditPlan.load(plan_path)
    base_dir = Path(args.base_dir) if args.base_dir else plan_path.parent
    report = audit_plan(plan, base_dir=base_dir, sample_limit=args.sample_limit)
    report_path = write_audit_report(Path(args.output), report)
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


def command_audit_binance_aggtrade_overlap(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = BinanceArchiveOverlapPlan.load(plan_path)
    base_dir = Path(args.base_dir) if args.base_dir else plan_path.parent
    report = audit_binance_aggtrade_overlap(
        plan,
        base_dir=base_dir,
        source_registry_path=Path(args.source_registry),
    )
    try:
        report_path = write_audit_report(Path(args.output), report)
    except FileExistsError:
        print("error: overlap audit output already exists; reports are write-once", file=sys.stderr)
        return 2
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


def command_run_binance_cm_historical_mechanism(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    if output_path.exists():
        print("error: historical mechanism output already exists; reports are write-once", file=sys.stderr)
        return 2
    try:
        plan = HistoricalMechanismPlan.load(Path(args.plan))
        report = run_historical_mechanism_experiment(plan, input_root=Path(args.input_root))
        report_path = write_historical_mechanism_report(output_path, report)
    except (HistoricalMechanismError, FileExistsError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_verify_binance_cm_historical_ledger(args: argparse.Namespace) -> int:
    try:
        report = verify_historical_evidence_ledger(Path(args.ledger), workspace_root=Path(args.workspace_root))
    except HistoricalEvidenceLedgerError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_run_binance_cm_historical_diagnostic(args: argparse.Namespace) -> int:
    try:
        plan = HistoricalDiagnosticPlan.load(Path(args.plan))
        execute_frozen_before_download(plan)
    except HistoricalDiagnosticError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 2


def command_build_binance_cm_january_diagnostic(args: argparse.Namespace) -> int:
    try:
        plan = HistoricalDiagnosticPlan.load(Path(args.plan))
        report = build_january_development_artifacts(
            plan=plan, input_root=Path(args.input_root), workspace_root=Path(args.workspace_root),
            rows_path=Path(args.rows), manifest_path=Path(args.manifest), model_path=Path(args.model),
        )
    except (HistoricalDiagnosticError, HistoricalDevelopmentError, HistoricalEvidenceLedgerError, FileExistsError) as exc:
        print("error: %s" % exc, file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def command_finalize_binance_cm_january_diagnostic(args: argparse.Namespace) -> int:
    try:
        plan = HistoricalDiagnosticPlan.load(Path(args.plan))
        report = finalize_january_development_artifacts(
            plan=plan, workspace_root=Path(args.workspace_root), rows_path=Path(args.rows),
            manifest_path=Path(args.manifest), model_path=Path(args.model),
        )
    except (HistoricalDiagnosticError, HistoricalDevelopmentError, HistoricalEvidenceLedgerError, FileExistsError) as exc:
        print("error: %s" % exc, file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def command_verify_binance_cm_diagnostic_application(args: argparse.Namespace) -> int:
    try:
        report = verify_receipt_bound_application(
            plan_path=Path(args.plan), contract_path=Path(args.contract) if args.contract else None,
            receipt_path=Path(args.receipt) if args.receipt else None, workspace_root=Path(args.workspace_root),
        )
    except HistoricalDiagnosticApplicationError as exc:
        print("error: %s" % exc, file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def command_execute_binance_cm_fresh_diagnostic(args: argparse.Namespace) -> int:
    try:
        report = execute_authorized_fresh_diagnostic(plan_path=Path(args.plan), contract_path=Path(args.contract), receipt_path=Path(args.receipt), acquisition_path=Path(args.acquisition), registry_path=Path(args.registry), workspace_root=Path(args.workspace_root), report_path=Path(args.output), scoring_attempt_id=args.scoring_attempt_id)
    except HistoricalDiagnosticApplicationError as exc:
        print("error: %s" % exc, file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def command_theory_paper_init(args: argparse.Namespace) -> int:
    report = initialize_theory_paper_experiment(
        Path(args.config),
        Path(args.run_dir),
        started_at=parse_utc(args.at) if args.at else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_theory_paper_cycle(args: argparse.Namespace) -> int:
    report = run_theory_paper_hourly_cycle(
        Path(args.run_dir),
        decision_at=parse_utc(args.at) if args.at else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_theory_paper_submit(args: argparse.Namespace) -> int:
    report = submit_theory_paper_agent_decision(
        Path(args.run_dir),
        Path(args.decision) if args.decision else None,
        decided_at=parse_utc(args.at) if args.at else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_theory_paper_review(args: argparse.Namespace) -> int:
    report = run_theory_paper_review(
        Path(args.run_dir),
        reviewed_at=parse_utc(args.at) if args.at else None,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_theory_paper_status(args: argparse.Namespace) -> int:
    print(json.dumps(
        theory_paper_status_report(Path(args.run_dir)),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


def command_theory_paper_manual_chaos(args: argparse.Namespace) -> int:
    report = inject_manual_emotion_trade(
        Path(args.run_dir),
        idempotency_key=args.idempotency_key,
        symbol=args.symbol,
        side=args.side,
        notional_usdt=args.notional_usdt,
        reason=args.reason,
        injected_at=parse_utc(args.at) if args.at else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_theory_paper_finalize(args: argparse.Namespace) -> int:
    report = finalize_theory_paper_experiment(
        Path(args.run_dir),
        finalized_at=parse_utc(args.at) if args.at else None,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trade-system", description="Local, paper-only trading research runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="run fixed synthetic end-to-end demo")
    demo.add_argument("--data-dir", required=True, help="new or append-only runtime directory")
    demo.add_argument("--paper-audit", default="", help="optional new paper audit NDJSON; synthetic demo only")
    demo.set_defaults(handler=command_demo)
    verify = subparsers.add_parser("verify", help="audit append-only runtime records")
    verify.add_argument("--data-dir", required=True)
    verify.set_defaults(handler=command_verify)
    replay = subparsers.add_parser("replay", help="hash point-in-time replay output")
    replay.add_argument("--data-dir", required=True)
    replay.add_argument("--allow-reconstructed", action="store_true")
    replay.set_defaults(handler=command_replay)
    ingest = subparsers.add_parser("ingest", help="capture Binance public envelopes from stdin; no network client or credentials")
    ingest.add_argument("--data-dir", required=True)
    ingest.add_argument("--connection-id", required=True)
    ingest.add_argument("--instrument", default="BTCUSDT")
    ingest.set_defaults(handler=command_ingest)
    protocol = subparsers.add_parser("validate-protocol", help="validate a frozen research-protocol JSON file")
    protocol.add_argument("--protocol", required=True)
    protocol.set_defaults(handler=command_validate_protocol)
    finalize_protocol = subparsers.add_parser("finalize-research-protocol", help="bind a preregistered protocol to one verified immutable PASS G1 report")
    finalize_protocol.add_argument("--preregistered-protocol", required=True)
    finalize_protocol.add_argument("--g1-report", required=True)
    finalize_protocol.add_argument("--supersession-guard", required=True, help="frozen guard that rejects retired preregistrations")
    finalize_protocol.add_argument("--output", required=True, help="new write-once frozen protocol JSON")
    finalize_protocol.add_argument("--frozen-at", default="", help="optional explicit UTC timestamp; defaults to current UTC")
    finalize_protocol.set_defaults(handler=command_finalize_research_protocol)
    collect = subparsers.add_parser("collect-public", help="forward Binance USD-M public capture; requires optional market extra")
    collect.add_argument("--data-dir", required=True)
    collect.add_argument("--connection-id", required=True)
    collect.add_argument("--instrument", default="BTCUSDT")
    collect.add_argument("--duration-seconds", type=float, default=60.0)
    collect.add_argument("--snapshot-limit", type=int, default=1000)
    collect.add_argument("--oi-poll-seconds", type=float, default=5.0)
    collect.add_argument("--metadata-poll-seconds", type=float, default=300.0, help="exchangeInfo polling interval; non-TRADING status fails the collection")
    collect.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH), help="frozen source-contract registry to bind into evidence")
    collect.add_argument("--capture-plan", default="", help="optional frozen forward-capture plan to bind before any collection writes")
    collect.add_argument("--capture-slot", default="", help="declared slot ID from --capture-plan")
    collect.add_argument("--live-feature-output", default="", help="optional new .ndjson path relative to this evidence store; only atomically published for a qualified collection")
    collect.add_argument("--episode-policy", default="", help="optional frozen episode policy for derived live features; its binding is recorded in the collection manifest")
    collect.set_defaults(handler=command_collect_public)
    planned_collect = subparsers.add_parser("collect-planned-public", help="run and seal one predeclared public-only slot in an isolated evidence directory")
    planned_collect.add_argument("--capture-plan", required=True, help="frozen forward-capture plan")
    planned_collect.add_argument("--capture-slot", required=True, help="slot ID to run now; external scheduling chooses when to invoke")
    planned_collect.add_argument("--data-root", required=True, help="parent directory; a new <plan-id>/<slot-id> evidence store is atomically reserved")
    planned_collect.add_argument("--duration-seconds", type=float, default=None, help="defaults to the slot minimum; cannot be shorter than the frozen minimum")
    planned_collect.add_argument("--snapshot-limit", type=int, default=1000)
    planned_collect.add_argument("--oi-poll-seconds", type=float, default=5.0)
    planned_collect.add_argument("--metadata-poll-seconds", type=float, default=300.0)
    planned_collect.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH))
    planned_collect.add_argument("--live-feature-output", default="", help="optional new .ndjson path relative to the isolated planned evidence store")
    planned_collect.add_argument("--episode-policy", default="", help="optional frozen episode policy for derived live features")
    planned_collect.set_defaults(handler=command_collect_planned_public)
    supervisor = subparsers.add_parser("supervise-capture-once", help="run at most one currently due frozen public slot; safe for periodic launchd invocation")
    supervisor.add_argument("--capture-plan", required=True, help="frozen forward-capture plan")
    supervisor.add_argument("--data-root", required=True, help="parent directory for isolated plan/slot evidence stores")
    supervisor.add_argument("--snapshot-limit", type=int, default=1000)
    supervisor.add_argument("--oi-poll-seconds", type=float, default=5.0)
    supervisor.add_argument("--metadata-poll-seconds", type=float, default=300.0)
    supervisor.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH))
    supervisor.add_argument("--live-feature-output", default="", help="optional relative output inside each isolated evidence store")
    supervisor.add_argument("--episode-policy", default="", help="optional frozen episode policy used only when live features are requested")
    supervisor.set_defaults(handler=command_supervise_capture_once)
    recover = subparsers.add_parser("recover-interrupted-collection", help="write an UNQUALIFIED terminal manifest for already-stopped orphan public-capture raw evidence")
    recover.add_argument("--data-dir", required=True)
    recover.add_argument("--connection-id", required=True)
    recover.add_argument("--instrument", default="BTCUSDT")
    recover.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH))
    recover.add_argument("--reason", required=True, help="operator-supplied interruption reason; preserved in the manifest")
    recover.add_argument("--confirm-stopped", action="store_true", help="required acknowledgement that no process can still append to this collection")
    recover.set_defaults(handler=command_recover_interrupted_collection)
    research = subparsers.add_parser("research-baseline", help="run purged walk-forward multinomial baseline over labeled JSONL")
    research.add_argument("--input", required=True)
    research.add_argument("--features", default="")
    research.add_argument("--folds", type=int, default=None, help="development run only; frozen protocol uses its registered value")
    research.add_argument("--embargo-seconds", type=int, default=None, help="development run only; frozen protocol uses its registered value")
    research.add_argument("--protocol", default="", help="versioned research protocol; metadata is emitted with the report")
    research.add_argument("--require-frozen-protocol", action="store_true", help="reject non-frozen/synthetic protocol profiles")
    research.add_argument("--g1-report", default="", help="immutable PASS G1 report required together with --require-frozen-protocol")
    research.add_argument("--state-classifier", default="", help="frozen deterministic state-classifier artifact required together with --require-frozen-protocol")
    research.add_argument("--labels-manifest", default="", help="verified state-label bundle manifest required together with --require-frozen-protocol")
    research.add_argument("--evidence-admission", default="", help="v2: verified DEVELOPMENT research-evidence admission")
    research.add_argument("--output", default="", help="new write-once research report path; required with --require-frozen-protocol")
    research.set_defaults(handler=command_research_baseline)
    final_holdout = subparsers.add_parser("evaluate-final-holdout", help="score the fixed baseline once on a verified final-holdout release; consumes its receipt even when coverage is inconclusive")
    final_holdout.add_argument("--input", required=True, help="exact frozen state-label artifact bound by the release receipt")
    final_holdout.add_argument("--features", default="")
    final_holdout.add_argument("--protocol", required=True)
    final_holdout.add_argument("--g1-report", required=True)
    final_holdout.add_argument("--state-classifier", required=True)
    final_holdout.add_argument("--labels-manifest", required=True)
    final_holdout.add_argument("--development-input", default="", help="v2: exact DEVELOPMENT state-label artifact; never train on holdout labels")
    final_holdout.add_argument("--development-labels-manifest", default="", help="v2: verified DEVELOPMENT state-label manifest")
    final_holdout.add_argument("--development-evidence-admission", default="", help="v2: verified DEVELOPMENT evidence admission")
    final_holdout.add_argument("--holdout-evidence-admission", default="", help="v2: verified HOLDOUT evidence admission")
    final_holdout.add_argument("--holdout-release", required=True)
    final_holdout.add_argument("--holdout-registry", required=True)
    final_holdout.add_argument("--output", required=True, help="new write-once final-holdout evaluation report")
    final_holdout.set_defaults(handler=command_evaluate_final_holdout, require_frozen_protocol=True)
    labels = subparsers.add_parser("label-actions", help="generate action-specific competing-risk labels from replayed feature artifacts")
    labels.add_argument("--actions", required=True, help="append-only action-record JSONL")
    labels.add_argument("--features", required=True, help="feature artifact JSONL with mid_price")
    labels.add_argument("--output", required=True, help="new label artifact JSONL")
    labels.add_argument("--allow-reconstructed", action="store_true")
    labels.set_defaults(handler=command_label_actions)
    bundle_labels = subparsers.add_parser("label-actions-g1-bundle", help="label actions only against their own verified G1 feature-bundle evidence path")
    bundle_labels.add_argument("--actions", required=True, help="action JSONL; every row must declare an evidence_id from the feature bundle")
    bundle_labels.add_argument("--action-manifest", required=True)
    bundle_labels.add_argument("--features", required=True)
    bundle_labels.add_argument("--feature-manifest", required=True)
    bundle_labels.add_argument("--output", required=True)
    bundle_labels.add_argument("--manifest", required=True)
    bundle_labels.add_argument("--labels-id", required=True)
    bundle_labels.set_defaults(handler=command_label_actions_g1_bundle)
    bundle_actions = subparsers.add_parser("build-actions-g1-bundle", help="generate research-only counterfactual actions from a frozen policy and verified G1 features")
    bundle_actions.add_argument("--features", required=True)
    bundle_actions.add_argument("--feature-manifest", required=True)
    bundle_actions.add_argument("--action-policy", required=True)
    bundle_actions.add_argument("--output", required=True)
    bundle_actions.add_argument("--manifest", required=True)
    bundle_actions.add_argument("--actions-id", required=True)
    bundle_actions.set_defaults(handler=command_build_actions_g1_bundle)
    assign_states = subparsers.add_parser("assign-states", help="write a new label artifact with deterministic frozen state-classifier assignments")
    assign_states.add_argument("--input", required=True)
    assign_states.add_argument("--classifier", required=True)
    assign_states.add_argument("--output", required=True)
    assign_states.set_defaults(handler=command_assign_states)
    state_bundle = subparsers.add_parser("assign-states-g1-bundle", help="assign frozen states while preserving a verified G1 label-bundle provenance chain")
    state_bundle.add_argument("--input", required=True)
    state_bundle.add_argument("--label-manifest", required=True)
    state_bundle.add_argument("--classifier", required=True)
    state_bundle.add_argument("--output", required=True)
    state_bundle.add_argument("--manifest", required=True)
    state_bundle.add_argument("--state-labels-id", required=True)
    state_bundle.set_defaults(handler=command_assign_states_g1_bundle)
    state_classifier = subparsers.add_parser("validate-state-classifier", help="validate a frozen deterministic state-classifier artifact")
    state_classifier.add_argument("--classifier", required=True)
    state_classifier.set_defaults(handler=command_validate_state_classifier)
    action_policy = subparsers.add_parser("validate-action-policy", help="validate a frozen research-only candidate-action policy")
    action_policy.add_argument("--policy", required=True)
    action_policy.set_defaults(handler=command_validate_action_policy)
    capture_plan = subparsers.add_parser("validate-capture-plan", help="validate a frozen forward-capture plan before collection")
    capture_plan.add_argument("--plan", required=True)
    capture_plan.set_defaults(handler=command_validate_capture_plan)
    capture_status = subparsers.add_parser("capture-plan-status", help="read only planned-slot status; creates no evidence directories")
    capture_status.add_argument("--plan", required=True)
    capture_status.add_argument("--data-root", required=True)
    capture_status.add_argument("--now", default="", help="optional UTC ISO-8601 inspection time for deterministic supervision")
    capture_status.add_argument("--require-all-sealed", action="store_true", help="return nonzero unless every declared slot is qualified and sealed")
    capture_status.set_defaults(handler=command_capture_plan_status)
    inventory = subparsers.add_parser("inventory-collections", help="read-only inventory of terminal public collection evidence below one or more roots")
    inventory.add_argument("--data-root", action="append", required=True, help="repeatable existing directory to scan; command creates no files")
    inventory.set_defaults(handler=command_inventory_collections)
    describe_features = subparsers.add_parser("describe-sealed-features", help="read-only pre-freeze feature distribution summary over SEALED_CURRENT collections")
    describe_features.add_argument("--data-root", action="append", required=True, help="repeatable existing directory to scan; command creates no files")
    describe_features.set_defaults(handler=command_describe_sealed_features)
    readiness = subparsers.add_parser("research-readiness", help="read-only summary of forward evidence, G1 policy and frozen research-protocol blockers")
    readiness.add_argument("--data-root", action="append", required=True, help="repeatable existing directory to scan; command creates no files")
    readiness.add_argument("--g1-policy", default=str(DEFAULT_G1_POLICY_PATH))
    readiness.add_argument("--research-protocol", default=str(DEFAULT_RESEARCH_PROTOCOL_PATH))
    readiness.set_defaults(handler=command_research_readiness)
    costs = subparsers.add_parser("cost-pressure", help="recalculate a frozen forecast under explicit cost scenarios")
    costs.add_argument("--input", required=True, help="cost-pressure JSON config")
    costs.set_defaults(handler=command_cost_pressure)
    coverage = subparsers.add_parser("coverage", help="report locally observed data coverage and evidence gaps")
    coverage.add_argument("--data-dir", required=True)
    coverage.set_defaults(handler=command_coverage)
    g1 = subparsers.add_parser("validate-g1", help="evaluate forward-data readiness against a frozen G1 acceptance policy")
    g1.add_argument("--data-dir", required=True)
    g1.add_argument("--policy", required=True)
    g1.add_argument("--output", default="", help="optional new write-once G1 validation report path")
    g1.set_defaults(handler=command_validate_g1)
    g1_bundle = subparsers.add_parser("validate-g1-bundle", help="evaluate separately sealed forward evidence stores under one frozen G1 policy without copying raw data")
    g1_bundle.add_argument("--data-dir", action="append", required=True, help="repeat for each independently sealed evidence directory")
    g1_bundle.add_argument("--policy", required=True)
    g1_bundle.add_argument("--output", default="", help="optional new write-once G1 validation report path")
    g1_bundle.set_defaults(handler=command_validate_g1_bundle)
    source_registry = subparsers.add_parser("validate-source-registry", help="validate a frozen source registry and optional capture stream binding")
    source_registry.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH))
    source_registry.add_argument("--instrument", default="BTCUSDT")
    source_registry.add_argument("--configured-stream", action="append", default=[])
    source_registry.set_defaults(handler=command_validate_source_registry)
    telemetry = subparsers.add_parser("validate-account-telemetry-contract", help="validate the paper/testnet-only private-account telemetry contract")
    telemetry.add_argument("--contract", default=str(DEFAULT_ACCOUNT_TELEMETRY_CONTRACT_PATH))
    telemetry.set_defaults(handler=command_validate_account_telemetry_contract)
    telemetry_audit = subparsers.add_parser("audit-account-telemetry", help="validate a normalized credential-free private telemetry artifact offline")
    telemetry_audit.add_argument("--input", required=True)
    telemetry_audit.add_argument("--contract", default=str(DEFAULT_ACCOUNT_TELEMETRY_CONTRACT_PATH))
    telemetry_audit.set_defaults(handler=command_audit_account_telemetry)
    telemetry_normalize = subparsers.add_parser("normalize-account-telemetry", help="convert a sanitized local Binance USD-M private-event export into a contract-bound credential-free artifact")
    telemetry_normalize.add_argument("--input", required=True, help="sanitized local source JSONL; no credentials or network transport")
    telemetry_normalize.add_argument("--output", required=True, help="new write-once normalized telemetry JSONL")
    telemetry_normalize.add_argument("--contract", default=str(DEFAULT_ACCOUNT_TELEMETRY_CONTRACT_PATH))
    telemetry_normalize.set_defaults(handler=command_normalize_account_telemetry)
    holdout_open = subparsers.add_parser("open-final-holdout", help="record the one-time local opening of a frozen protocol's final holdout; no model evaluation or trading")
    holdout_open.add_argument("--protocol", required=True)
    holdout_open.add_argument("--labels", required=True, help="exact frozen state-label artifact to bind")
    holdout_open.add_argument("--registry-dir", required=True, help="controlled local registry directory that enforces one release per protocol/holdout ID")
    holdout_open.add_argument("--output", required=True, help="new write-once final-holdout release receipt")
    holdout_open.add_argument("--confirm-release-candidate", action="store_true", help="required acknowledgement that model/policy/cost versions are frozen")
    holdout_open.add_argument("--confirm-no-other-writers", action="store_true", help="required acknowledgement that no other process can write this registry")
    holdout_open.add_argument("--evidence-admission", default="", help="v2: verified HOLDOUT research-evidence admission")
    holdout_open.add_argument("--labels-manifest", default="", help="v2: verified HOLDOUT state-label manifest")
    holdout_open.add_argument("--state-classifier", default="", help="v2: classifier for --labels-manifest")
    holdout_open.set_defaults(handler=command_open_final_holdout)
    holdout_verify = subparsers.add_parser("verify-final-holdout", help="verify a local final-holdout receipt against its registry and exact labels artifact")
    holdout_verify.add_argument("--input", required=True, help="final-holdout release receipt")
    holdout_verify.add_argument("--protocol", required=True)
    holdout_verify.add_argument("--labels", required=True)
    holdout_verify.add_argument("--registry-dir", required=True)
    holdout_verify.add_argument("--evidence-admission", default="", help="v2: verified HOLDOUT research-evidence admission")
    holdout_verify.add_argument("--labels-manifest", default="", help="v2: verified HOLDOUT state-label manifest")
    holdout_verify.add_argument("--state-classifier", default="", help="v2: classifier for --labels-manifest")
    holdout_verify.set_defaults(handler=command_verify_final_holdout)
    recovery_telemetry = subparsers.add_parser("reconcile-paper-recovery-telemetry", help="compare a verified fail-closed paper recovery handoff with normalized read-only telemetry")
    recovery_telemetry.add_argument("--recovery-report", required=True)
    recovery_telemetry.add_argument("--paper-audit", required=True)
    recovery_telemetry.add_argument("--telemetry", required=True)
    recovery_telemetry.add_argument("--contract", default=str(DEFAULT_ACCOUNT_TELEMETRY_CONTRACT_PATH))
    recovery_telemetry.add_argument("--output", required=True, help="new write-once local reconciliation report")
    recovery_telemetry.set_defaults(handler=command_reconcile_paper_recovery_telemetry)
    gate_profile = subparsers.add_parser("validate-risk-gate-profile", help="validate the frozen paper/synthetic reason-level risk-gate profile")
    gate_profile.add_argument("--profile", default=str(DEFAULT_RISK_GATE_PROFILE_PATH))
    gate_profile.set_defaults(handler=command_validate_risk_gate_profile)
    historical = subparsers.add_parser("audit-okx-historical", help="audit local OKX historical files for replay-only coverage evidence")
    historical.add_argument("--plan", default=str(DEFAULT_OKX_AUDIT_PLAN_PATH))
    historical.add_argument("--base-dir", default="", help="base directory for plan-relative files; defaults to the plan directory")
    historical.add_argument("--output", required=True, help="new write-once JSON report path")
    historical.add_argument("--sample-limit", type=int, default=1000)
    historical.set_defaults(handler=command_audit_okx_historical)
    binance_archive = subparsers.add_parser("audit-binance-aggtrade-overlap", help="compare one pinned official USD-M aggTrade archive with an exact sealed forward collection")
    binance_archive.add_argument("--plan", default=str(DEFAULT_BINANCE_ARCHIVE_OVERLAP_PLAN_PATH))
    binance_archive.add_argument("--base-dir", default="", help="base directory for plan-relative archive and evidence paths; defaults to the plan directory")
    binance_archive.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH), help="exact frozen source registry bound by the overlap plan")
    binance_archive.add_argument("--output", required=True, help="new write-once JSON audit report path")
    binance_archive.set_defaults(handler=command_audit_binance_aggtrade_overlap)
    historical_mechanism = subparsers.add_parser("run-binance-cm-historical-mechanism", help="run a frozen, isolated Binance COIN-M historical mechanism experiment")
    historical_mechanism.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_MECHANISM_PLAN_PATH))
    historical_mechanism.add_argument("--input-root", required=True, help="directory containing official daily ZIP and .CHECKSUM files")
    historical_mechanism.add_argument("--output", required=True, help="new write-once JSON report path")
    historical_mechanism.set_defaults(handler=command_run_binance_cm_historical_mechanism)
    historical_ledger = subparsers.add_parser("verify-binance-cm-historical-ledger", help="reverify the bounded historical v1 evidence ledger without adjudicating hypotheses")
    historical_ledger.add_argument("--ledger", default=str(DEFAULT_BINANCE_CM_HISTORICAL_LEDGER_PATH))
    historical_ledger.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    historical_ledger.set_defaults(handler=command_verify_binance_cm_historical_ledger)
    historical_diagnostic = subparsers.add_parser("run-binance-cm-historical-diagnostic", help="refuse execution of the frozen-before-download v2 historical diagnostic")
    historical_diagnostic.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_DIAGNOSTIC_PATH))
    historical_diagnostic.set_defaults(handler=command_run_binance_cm_historical_diagnostic)
    january_diagnostic = subparsers.add_parser("build-binance-cm-january-diagnostic", help="build immutable January-only seen-development v2 rows, model, and evaluation")
    january_diagnostic.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_JAN_DIAGNOSTIC_PATH))
    january_diagnostic.add_argument("--input-root", required=True)
    january_diagnostic.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    january_diagnostic.add_argument("--rows", required=True)
    january_diagnostic.add_argument("--manifest", required=True)
    january_diagnostic.add_argument("--model", required=True)
    january_diagnostic.set_defaults(handler=command_build_binance_cm_january_diagnostic)
    january_finalize = subparsers.add_parser("finalize-binance-cm-january-diagnostic", help="finish models/manifest from an existing immutable January v2 row artifact")
    january_finalize.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_JAN_DIAGNOSTIC_PATH))
    january_finalize.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    january_finalize.add_argument("--rows", required=True)
    january_finalize.add_argument("--manifest", required=True)
    january_finalize.add_argument("--model", required=True)
    january_finalize.set_defaults(handler=command_finalize_binance_cm_january_diagnostic)
    application = subparsers.add_parser("verify-binance-cm-diagnostic-application", help="verify an explicit receipt-bound February application contract without reading fresh data")
    application.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_DIAGNOSTIC_PATH))
    application.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    application.add_argument("--contract", default="")
    application.add_argument("--receipt", default="")
    application.set_defaults(handler=command_verify_binance_cm_diagnostic_application)
    fresh_application = subparsers.add_parser("execute-authorized-binance-cm-fresh-diagnostic", help="execute only a receipt-bound, acquisition-validated February fresh-score handoff")
    fresh_application.add_argument("--plan", default=str(DEFAULT_BINANCE_CM_HISTORICAL_DIAGNOSTIC_PATH)); fresh_application.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    fresh_application.add_argument("--contract", required=True); fresh_application.add_argument("--receipt", required=True); fresh_application.add_argument("--acquisition", required=True); fresh_application.add_argument("--registry", required=True); fresh_application.add_argument("--output", required=True); fresh_application.add_argument("--scoring-attempt-id", required=True)
    fresh_application.set_defaults(handler=command_execute_binance_cm_fresh_diagnostic)
    features = subparsers.add_parser("build-features", help="derive append-only feature artifact from replay evidence")
    features.add_argument("--data-dir", required=True)
    features.add_argument("--output", required=True)
    features.add_argument("--allow-reconstructed", action="store_true")
    features.add_argument("--episode-policy", default="", help="optional frozen episode trigger policy; omitted only for development artifacts")
    features.set_defaults(handler=command_build_features)
    feature_bundle = subparsers.add_parser("build-features-g1-bundle", help="build isolated, provenance-bound features from every qualified collection in a PASS G1 report")
    feature_bundle.add_argument("--data-dir", action="append", required=True, help="repeat for exactly the qualified G1 evidence roots")
    feature_bundle.add_argument("--g1-report", required=True)
    feature_bundle.add_argument("--output", required=True, help="new feature NDJSON artifact")
    feature_bundle.add_argument("--manifest", required=True, help="new immutable feature-bundle manifest")
    feature_bundle.add_argument("--bundle-id", required=True)
    feature_bundle.add_argument("--episode-policy", required=True, help="frozen episode policy required for G1 feature construction")
    feature_bundle.set_defaults(handler=command_build_features_g1_bundle)
    acceptance = subparsers.add_parser("write-data-acceptance-report", help="write a role-specific immutable PASS acceptance report from validated collections")
    acceptance.add_argument("--role", choices=("DEVELOPMENT", "HOLDOUT"), required=True)
    acceptance.add_argument("--acceptance-policy", required=True)
    acceptance.add_argument("--capture-plan", required=True)
    acceptance.add_argument("--data-dir", action="append", required=True, help="repeat exact stores to revalidate; external PASS reports are not trusted")
    acceptance.add_argument("--report-id", required=True)
    acceptance.add_argument("--output", required=True)
    acceptance.set_defaults(handler=command_write_data_acceptance_report)
    role_features = subparsers.add_parser("build-features-role-bundle", help="build an ACTUAL-only feature bundle for one frozen role")
    role_features.add_argument("--protocol", required=True)
    role_features.add_argument("--role", choices=("DEVELOPMENT", "HOLDOUT"), required=True)
    role_features.add_argument("--capture-plan", required=True)
    role_features.add_argument("--acceptance-policy", required=True)
    role_features.add_argument("--acceptance-report", required=True)
    role_features.add_argument("--baseline-g1-policy", required=True)
    role_features.add_argument("--data-dir", action="append", required=True)
    role_features.add_argument("--episode-policy", required=True)
    role_features.add_argument("--output", required=True)
    role_features.add_argument("--manifest", required=True)
    role_features.add_argument("--bundle-id", required=True)
    role_features.add_argument("--context-policy", default="", help="frozen ACTUAL-only 4H context policy; requires all context/archive options")
    role_features.add_argument("--role-window", default="", help="frozen warmup/decision/label-tail window bound to this role")
    role_features.add_argument("--context-output", default="", help="new context NDJSON artifact")
    role_features.add_argument("--context-manifest", default="", help="new context artifact manifest")
    role_features.add_argument("--archive-receipt", action="append", default=[], help="repeat one verified non-destructive archive receipt per accepted collection")
    role_features.set_defaults(handler=command_build_features_role_bundle)
    g2 = subparsers.add_parser("evaluate-g2-protocol", help="run frozen v2 DEVELOPMENT-only counterfactual G2 gates from verified evidence")
    g2.add_argument("--protocol", required=True)
    g2.add_argument("--evidence-admission", required=True)
    g2.add_argument("--state-labels", required=True)
    g2.add_argument("--state-manifest", required=True)
    g2.add_argument("--state-classifier", required=True)
    g2.add_argument("--features", required=True)
    g2.add_argument("--feature-manifest", required=True)
    g2.add_argument("--as-of", required=True, help="UTC cutoff; rows after this time are rejected")
    g2.add_argument("--output", required=True, help="new write-once G2 report")
    g2.set_defaults(handler=command_evaluate_g2_protocol)
    admission = subparsers.add_parser("admit-research-evidence", help="write one verified role wrapper around the feature-action-label-state chain")
    admission.add_argument("--protocol", required=True)
    admission.add_argument("--role", choices=("DEVELOPMENT", "HOLDOUT"), required=True)
    admission.add_argument("--capture-plan", required=True)
    admission.add_argument("--acceptance-policy", required=True)
    admission.add_argument("--acceptance-report", required=True)
    admission.add_argument("--baseline-g1-policy", required=True)
    admission.add_argument("--g1-report", required=True)
    admission.add_argument("--features", required=True)
    admission.add_argument("--feature-manifest", required=True)
    admission.add_argument("--actions", required=True)
    admission.add_argument("--action-manifest", required=True)
    admission.add_argument("--labels", required=True)
    admission.add_argument("--label-manifest", required=True)
    admission.add_argument("--state-labels", required=True)
    admission.add_argument("--state-manifest", required=True)
    admission.add_argument("--classifier", required=True)
    admission.add_argument("--admission-id", required=True)
    admission.add_argument("--output", required=True)
    admission.set_defaults(handler=command_admit_research_evidence)
    seal = subparsers.add_parser("seal-raw", help="seal a completed raw YYYY-MM-DD segment with an immutable checksum manifest")
    seal.add_argument("--data-dir", required=True)
    seal.add_argument("--segment", required=True)
    seal.set_defaults(handler=command_seal_raw)
    seal_collection = subparsers.add_parser("seal-collection", help="safely seal every date segment of a terminal collection, including UTC-midnight boundaries")
    seal_collection.add_argument("--data-dir", required=True)
    seal_collection.add_argument("--collection-id", required=True)
    seal_collection.add_argument("--confirm-no-other-writers", action="store_true", help="required acknowledgement after verifying no unrelated collector can write the same date segment")
    seal_collection.set_defaults(handler=command_seal_collection)
    archive = subparsers.add_parser("archive-sealed-collection", help="write a non-destructive gzip sidecar for one terminal isolated collection")
    archive.add_argument("--data-dir", required=True)
    archive.add_argument("--collection-id", required=True)
    archive.add_argument("--cold-root", required=True, help="separate cold-sidecar root; hot evidence is never deleted")
    archive.add_argument("--archive-id", required=True)
    archive.set_defaults(handler=command_archive_sealed_collection)
    archive_verify = subparsers.add_parser("verify-evidence-archive", help="verify archived bytes and deterministic replay without hot I/O")
    archive_verify.add_argument("--receipt", required=True)
    archive_verify.set_defaults(handler=command_verify_evidence_archive)
    hot_cold = subparsers.add_parser("verify-hot-cold-evidence", help="verify a sealed hot collection exactly matches its cold sidecar")
    hot_cold.add_argument("--data-dir", required=True)
    hot_cold.add_argument("--collection-id", required=True)
    hot_cold.add_argument("--receipt", required=True)
    hot_cold.set_defaults(handler=command_verify_hot_cold_evidence)
    shadow = subparsers.add_parser("compare-shadow", help="compare offline and online feature artifacts for M5 evidence")
    shadow.add_argument("--offline", required=True)
    shadow.add_argument("--online", required=True)
    shadow.set_defaults(handler=command_compare_shadow)
    live_shadow = subparsers.add_parser("verify-live-feature-shadow", help="verify a sealed collection's atomically published live feature artifact against deterministic replay")
    live_shadow.add_argument("--data-dir", required=True)
    live_shadow.add_argument("--collection-id", required=True)
    live_shadow.add_argument("--live-features", required=True)
    live_shadow.add_argument("--episode-policy", default="", help="required when the collection manifest binds a frozen episode policy")
    live_shadow.set_defaults(handler=command_verify_live_feature_shadow)
    decision_provenance = subparsers.add_parser("verify-shadow-decision-artifact", help="verify a local M5 decision artifact is bound to exact ACTUAL features and frozen model/policy/risk inputs")
    decision_provenance.add_argument("--decisions", required=True)
    decision_provenance.add_argument("--features", required=True)
    decision_provenance.add_argument("--model-artifact", required=True)
    decision_provenance.add_argument("--action-policy", required=True)
    decision_provenance.add_argument("--risk-gate-profile", required=True)
    decision_provenance.set_defaults(handler=command_verify_shadow_decision_artifact)
    shadow_decisions = subparsers.add_parser("compare-shadow-decisions", help="compare offline and online decision artifacts for M5 evidence")
    shadow_decisions.add_argument("--offline", required=True)
    shadow_decisions.add_argument("--online", required=True)
    shadow_decisions.set_defaults(handler=command_compare_shadow_decisions)
    paper_audit = subparsers.add_parser("audit-paper-run", help="verify a finalized local paper audit trail")
    paper_audit.add_argument("--input", required=True)
    paper_audit.set_defaults(handler=command_audit_paper_run)
    paper_contract = subparsers.add_parser("validate-paper-run-contract", help="validate a frozen credential-free provenance contract for one local paper run")
    paper_contract.add_argument("--contract", required=True)
    paper_contract.set_defaults(handler=command_validate_paper_run_contract)
    paper_binding = subparsers.add_parser("verify-paper-run-binding", help="verify a finalized paper audit begins with the exact frozen paper run contract context")
    paper_binding.add_argument("--audit", required=True)
    paper_binding.add_argument("--contract", required=True)
    paper_binding.set_defaults(handler=command_verify_paper_run_binding)
    paper_evidence = subparsers.add_parser("verify-paper-run-evidence", help="match every frozen paper run binding to the exact supplied local artifact files")
    paper_evidence.add_argument("--contract", required=True)
    paper_evidence.add_argument("--model-artifact", required=True)
    paper_evidence.add_argument("--action-policy", required=True)
    paper_evidence.add_argument("--risk-gate-profile", required=True)
    paper_evidence.add_argument("--source-registry", required=True)
    paper_evidence.add_argument("--state-classifier", required=True)
    paper_evidence.add_argument("--input-evidence", required=True)
    paper_evidence.add_argument("--input-evidence-id", required=True)
    paper_evidence.set_defaults(handler=command_verify_paper_run_evidence)
    paper_seal = subparsers.add_parser("seal-paper-run", help="write a new immutable manifest for a finalized paper audit bound to a frozen run contract")
    paper_seal.add_argument("--audit", required=True)
    paper_seal.add_argument("--contract", required=True)
    paper_seal.add_argument("--output", required=True)
    paper_seal.set_defaults(handler=command_seal_paper_run)
    paper_recovery = subparsers.add_parser("recover-paper-run", help="write a fail-closed handoff for an interrupted local paper audit trail")
    paper_recovery.add_argument("--input", required=True, help="unfinalized local paper audit NDJSON")
    paper_recovery.add_argument("--output", required=True, help="new write-once recovery report path")
    paper_recovery.add_argument("--confirm-process-stopped", action="store_true", help="required acknowledgement that no process can append to the audit trail")
    paper_recovery.set_defaults(handler=command_recover_paper_run)
    verify_paper_recovery = subparsers.add_parser("verify-paper-recovery", help="verify a recovery report against its unchanged interrupted audit trail")
    verify_paper_recovery.add_argument("--input", required=True, help="paper recovery report")
    verify_paper_recovery.add_argument("--audit", required=True, help="the exact interrupted paper audit trail")
    verify_paper_recovery.set_defaults(handler=command_verify_paper_recovery)
    theory_init = subparsers.add_parser(
        "theory-paper-init",
        help="initialize the credential-free 72-hour new-theory paper experiment",
    )
    theory_init.add_argument("--config", required=True)
    theory_init.add_argument("--run-dir", required=True)
    theory_init.add_argument("--at", default="", help="optional deterministic UTC timestamp")
    theory_init.set_defaults(handler=command_theory_paper_init)
    theory_cycle = subparsers.add_parser(
        "theory-paper-cycle",
        help="freeze one hourly six-market observation and experimental theory analysis",
    )
    theory_cycle.add_argument("--run-dir", required=True)
    theory_cycle.add_argument("--at", default="", help="optional deterministic UTC timestamp")
    theory_cycle.set_defaults(handler=command_theory_paper_cycle)
    theory_review = subparsers.add_parser(
        "theory-paper-review",
        help="freeze the due eight-hour theory, method, and paper-performance review",
    )
    theory_review.add_argument("--run-dir", required=True)
    theory_review.add_argument("--at", default="", help="optional deterministic UTC timestamp")
    theory_review.add_argument("--force", action="store_true", help="test or recovery use only")
    theory_review.set_defaults(handler=command_theory_paper_review)
    theory_status = subparsers.add_parser(
        "theory-paper-status",
        help="verify the local experiment ledger and show portfolio status",
    )
    theory_status.add_argument("--run-dir", required=True)
    theory_status.set_defaults(handler=command_theory_paper_status)
    theory_finalize = subparsers.add_parser(
        "theory-paper-finalize",
        help="stop new risk and seal the descriptive 72-hour paper report",
    )
    theory_finalize.add_argument("--run-dir", required=True)
    theory_finalize.add_argument("--at", default="", help="optional deterministic UTC timestamp")
    theory_finalize.add_argument("--force", action="store_true", help="test or recovery use only")
    theory_finalize.set_defaults(handler=command_theory_paper_finalize)
    return parser


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (BookGapError, RuntimeError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
