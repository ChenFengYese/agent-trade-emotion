from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    AGENT_OUTPUT_INCOMPLETE,
    ArtifactRef,
    BehaviorPlan,
    CycleRequest,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
    snapshot_bound_memory_context,
    verified_memory_context,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    CURRENT_THEORY_IDENTITY,
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
    MarketCycleRepositoryError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.controller_state import (
    ControllerStateError,
    FileControllerState,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    AGENT_FIRST_CONTRACT_IDENTITY,
    V332_RUNTIME_CONTRACT_IDENTITY,
    CYCLE_RUN_BINDING_RELATIVE_PATH,
    FrozenRunManifest,
    MEMORY_CONTEXT_RELATIVE_PATH,
    MEMORY_CONTEXT_SCHEMA_ID,
    MEMORY_CONTEXT_SCHEMA_VERSION,
    RUN_CLOSURE_RELATIVE_PATH,
    RUN_CLOSURE_SCHEMA_ID,
    RUN_CLOSURE_SCHEMA_VERSION,
    RUN_MANIFEST_RELATIVE_PATH,
    RUN_MANIFEST_SCHEMA_ID,
    RUN_MANIFEST_SCHEMA_VERSION,
    ManifestBoundCycleService,
    MarketCycleRuntimeError,
    RunManifestGate,
    _read_run_manifest,
    build_market_cycle_runtime,
    current_implementation_identity,
    initialize_run_identity_seal,
    load_verified_memory_context,
    run_identity_seal_path,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.theory_package import (
    FileTheoryPackageLoader,
    TheoryPackageError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
)


_ROOT = Path(__file__).resolve().parents[1]
_THEORY_PACKAGE = _ROOT / "theory" / "versions" / "v3.3.1"
_V332_THEORY_PACKAGE = _ROOT / "theory" / "versions" / "v3.3.2"


class _MutableControllerClock:
    def __init__(self, current: str) -> None:
        self.current = current

    def __call__(self) -> str:
        return self.current

    def monotonic_ns(self) -> int:
        return 1


def _request(
    cycle_id: str = "cycle-btc-001",
    *,
    requested_at: str = "2026-08-11T00:00:00+00:00",
) -> CycleRequest:
    return CycleRequest(
        request_id="request-btc-001",
        cycle_id=cycle_id,
        requested_at=requested_at,
        venue_id="OKX",
        instrument_id="BTC-USDT-SWAP",
        contract_identity="OKX:BTC-USDT-SWAP:SWAP",
        analysis_profile="COLD",
        data_profile="BASELINE_PRICE",
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
    )


def _snapshot(
    cycle_id: str = "cycle-btc-001",
    *,
    snapshot_id: str = "snapshot-btc-001",
    raw_ref: ArtifactRef | None = None,
) -> InputSnapshot:
    raw_reference = raw_ref or ArtifactRef(
        artifact_type="RawCapture",
        artifact_id="raw-okx-001",
        path="raw/raw-okx-001.json",
        size_bytes=1,
        sha256="a" * 64,
    )
    raw_sha256 = raw_reference.sha256
    available_at = "2026-08-11T00:00:01+00:00"

    def observation(value: object) -> dict[str, object]:
        return {
            "value": value,
            "available_at": available_at,
            "raw_sha256": raw_sha256,
        }

    closed_bars = observation([])
    closed_bars["last_closed_at"] = "2026-08-11T00:00:00+00:00"
    return InputSnapshot(
        snapshot_id=snapshot_id,
        cycle_id=cycle_id,
        request_id="request-btc-001",
        source_cutoff_at="2026-08-11T00:00:01+00:00",
        decision_at="2026-08-11T00:00:01+00:00",
        sealed_at="2026-08-11T00:00:02+00:00",
        venue_id="OKX",
        instrument_id="BTC-USDT-SWAP",
        contract_identity="OKX:BTC-USDT-SWAP:SWAP",
        analysis_profile="COLD",
        data_profile="BASELINE_PRICE",
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
        core_observations={
            "server_time": observation("2026-08-11T00:00:01+00:00"),
            "instrument": observation("BTC-USDT-SWAP"),
            "mark_price": observation("120000.0"),
            "closed_15m_bars": closed_bars,
        },
        optional_observations={},
        unknowns=("liquidations",),
        raw_refs=(raw_reference,),
        source_health=(),
    )


def _raw_reference(
    *,
    cycle_id: str = "cycle-btc-001",
    capture_id: str,
    payload: bytes,
) -> ArtifactRef:
    return ArtifactRef(
        artifact_type="RawCapture",
        artifact_id=f"{cycle_id}.{capture_id}.raw",
        path=f"raw/{capture_id}/body.bin",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _seal_raw_reference(
    store: FileRawCaptureStore,
    *,
    cycle_id: str = "cycle-btc-001",
    capture_id: str,
    payload: bytes,
) -> ArtifactRef:
    return ArtifactRef.from_dict(
        store.seal_response(
            cycle_id=cycle_id,
            capture_id=capture_id,
            payload=payload,
            summary={"component_id": "repository-owning-test"},
        )
    )


def _hypothesis_record(snapshot_ref: ArtifactRef) -> HypothesisRecord:
    decision_text = (
        "# Agent decision\n\n"
        "WAIT while the next closed bar remains unresolved.\n\n"
        "Position management: no executable quantity; preserve optionality.\n"
    )
    decision_raw = decision_text.encode("utf-8")
    return HypothesisRecord(
        record_id="hypothesis-record-btc-001",
        cycle_id="cycle-btc-001",
        input_snapshot_ref=snapshot_ref,
        decision_at="2026-08-11T00:00:01+00:00",
        agent_delivered_at="2026-08-11T00:00:03+00:00",
        sealed_at="2026-08-11T00:00:03+00:00",
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        agent_request_sha256="b" * 64,
        agent_delivery_path="transport/agent-delivery.json",
        agent_delivery_sha256="c" * 64,
        agent_decision_text=decision_text,
        agent_decision_size_bytes=len(decision_raw),
        agent_decision_sha256=hashlib.sha256(decision_raw).hexdigest(),
        projection_status="UNKNOWN",
        projection_reason=AGENT_OUTPUT_INCOMPLETE,
        hypothesis_index=(),
        agent_action_text=None,
        agent_position_text=None,
        lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
        unresolved_unknowns=("liquidations", AGENT_OUTPUT_INCOMPLETE),
    )


def _behavior_plan(hypothesis_ref: ArtifactRef) -> BehaviorPlan:
    record = _hypothesis_record(
        ArtifactRef(
            artifact_type="InputSnapshot",
            artifact_id="snapshot-btc-001",
            path="artifacts/InputSnapshot.json",
            size_bytes=1,
            sha256="1" * 64,
        )
    )
    return BehaviorPlan(
        plan_id="behavior-plan-btc-001",
        cycle_id="cycle-btc-001",
        hypothesis_record_ref=hypothesis_ref,
        decision_at="2026-08-11T00:00:01+00:00",
        agent_delivered_at=record.agent_delivered_at,
        sealed_at=record.agent_delivered_at,
        risk_mode="REFERENCE",
        execution_mapping="NOT_READY",
        executable_quantity=None,
        agent_request_sha256=record.agent_request_sha256,
        agent_delivery_path=record.agent_delivery_path,
        agent_delivery_sha256=record.agent_delivery_sha256,
        agent_decision_text=record.agent_decision_text,
        agent_decision_size_bytes=record.agent_decision_size_bytes,
        agent_decision_sha256=record.agent_decision_sha256,
        projection_status=record.projection_status,
        projection_reason=record.projection_reason,
        hypothesis_index=record.hypothesis_index,
        agent_action_text=record.agent_action_text,
        agent_position_text=record.agent_position_text,
        outcome_due_at="2026-08-11T01:00:01+00:00",
        outcome_tolerance_seconds=60,
    )


def _typed_missing_outcome(plan_ref: ArtifactRef) -> Outcome:
    return Outcome(
        outcome_id="outcome-btc-001",
        cycle_id="cycle-btc-001",
        behavior_plan_ref=plan_ref,
        due_at="2026-08-11T01:00:01+00:00",
        tolerance_seconds=60,
        observed_at="2026-08-11T01:01:01+00:00",
        sealed_at="2026-08-11T01:01:02+00:00",
        terminal_status="TYPED_MISSING",
        endpoint_observation=None,
        typed_missing="UNKNOWN_COVERAGE_LOSS",
        path_observations={},
        raw_refs=(),
    )


def _observed_outcome(plan_ref: ArtifactRef, raw_ref: ArtifactRef) -> Outcome:
    return Outcome(
        outcome_id="outcome-btc-observed-001",
        cycle_id="cycle-btc-001",
        behavior_plan_ref=plan_ref,
        due_at="2026-08-11T01:00:01+00:00",
        tolerance_seconds=60,
        observed_at="2026-08-11T01:01:01+00:00",
        sealed_at="2026-08-11T01:01:02+00:00",
        terminal_status="OBSERVED",
        endpoint_observation={
            "value": "121000.0",
            "unit": "USDT",
            "price_field": "MARK_PRICE",
            "effective_at": "2026-08-11T01:00:01+00:00",
            "available_at": "2026-08-11T01:00:02+00:00",
            "raw_sha256": raw_ref.sha256,
        },
        typed_missing=None,
        path_observations={},
        raw_refs=(raw_ref,),
    )


def _review(plan_ref: ArtifactRef, outcome_ref: ArtifactRef) -> Review:
    decision_text = (
        "# Agent decision\n\n"
        "WAIT while the next closed bar remains unresolved.\n\n"
        "Position management: no executable quantity; preserve optionality.\n"
    )
    review_text = (
        "# Agent review\n\n"
        "Outcome coverage is missing, so the original WAIT decision remains "
        "unevaluable rather than confirmed.\n"
    )
    review_raw = review_text.encode("utf-8")
    return Review(
        review_id="review-btc-001",
        cycle_id="cycle-btc-001",
        behavior_plan_ref=plan_ref,
        outcome_ref=outcome_ref,
        reviewed_at="2026-08-11T01:01:03+00:00",
        outcome_status="TYPED_MISSING",
        agent_decision_sha256=hashlib.sha256(
            decision_text.encode("utf-8")
        ).hexdigest(),
        projection_status="UNKNOWN",
        projection_reason=AGENT_OUTPUT_INCOMPLETE,
        system_facts={
            "outcome_status": "TYPED_MISSING",
            "typed_missing": "UNKNOWN_COVERAGE_LOSS",
            "endpoint_observation": None,
            "path_observations": {},
            "outcome_raw_refs": [],
        },
        agent_review_delivered_at="2026-08-11T01:01:03+00:00",
        agent_review_request_sha256="d" * 64,
        agent_review_delivery_path="transport/agent-review-delivery.json",
        agent_review_delivery_sha256="e" * 64,
        agent_review_text=review_text,
        agent_review_size_bytes=len(review_raw),
        agent_review_sha256=hashlib.sha256(review_raw).hexdigest(),
        theory_writeback=False,
    )


class TheoryPackageLoaderTests(unittest.TestCase):
    def test_loads_readme_and_seven_separately_named_verified_fragments(self) -> None:
        package = FileTheoryPackageLoader(_THEORY_PACKAGE).load(
            CURRENT_THEORY_IDENTITY
        )

        self.assertEqual(package.identity, CURRENT_THEORY_IDENTITY)
        self.assertEqual(package.ordered_paths[0], "README.md")
        self.assertEqual(len(package.ordered_paths), 8)
        self.assertEqual(tuple(package.fragments), package.ordered_paths[1:])
        self.assertNotIn("README.md", package.fragments)
        self.assertEqual(
            tuple(package.hot_path_fragments),
            (
                "README.md",
                "01_MARKET_COGNITION.md",
                "02_DYNAMIC_POSITION_MANAGEMENT.md",
                "03_HYPOTHESIS_SYSTEM.md",
                "04_EXECUTION_AND_AGENT.md",
                "05_RISK_AND_BOUNDARIES.md",
            ),
        )
        self.assertNotIn(
            "06_HISTORY_FAILURES_AND_CHANGES.md", package.hot_path_fragments
        )
        self.assertNotIn(
            "07_NEW_MECHANISMS_AND_RESOLVED_ISSUES.md",
            package.hot_path_fragments,
        )
        self.assertEqual(
            len(package.manifest_raw_bytes),
            CURRENT_THEORY_IDENTITY.manifest_size_bytes,
        )
        self.assertEqual(
            hashlib.sha256(package.manifest_raw_bytes).hexdigest(),
            CURRENT_THEORY_IDENTITY.manifest_digest,
        )
        self.assertIn("V3.3.1", package.readme)
        self.assertIn("01_MARKET_COGNITION.md", package.fragments)

        v332_package = FileTheoryPackageLoader(_V332_THEORY_PACKAGE).load(
            V332_THEORY_IDENTITY
        )
        self.assertEqual(v332_package.identity, V332_THEORY_IDENTITY)
        self.assertEqual(len(v332_package.ordered_paths), 9)
        self.assertEqual(
            tuple(v332_package.fragments), v332_package.ordered_paths[1:]
        )
        self.assertEqual(
            v332_package.ordered_paths,
            (
                "README.md",
                "00_USER_DIRECTED_EXPERIMENTAL_SCOPE.md",
                "01_MARKET_COGNITION.md",
                "02_DYNAMIC_POSITION_MANAGEMENT.md",
                "03_HYPOTHESIS_SYSTEM.md",
                "04_EXECUTION_AND_AGENT.md",
                "05_RISK_AND_BOUNDARIES.md",
                "08_SANDISK_USDT_TEACHING_CASE.md",
                "09_STATE_TRANSITION_AND_EVALUATION.md",
            ),
        )
        self.assertEqual(
            tuple(v332_package.hot_path_fragments),
            v332_package.ordered_paths,
        )
        self.assertEqual(
            hashlib.sha256(v332_package.manifest_raw_bytes).hexdigest(),
            V332_THEORY_IDENTITY.manifest_digest,
        )
        with self.assertRaisesRegex(
            TheoryPackageError, "THEORY_MANIFEST_SIZE_MISMATCH"
        ):
            FileTheoryPackageLoader(_THEORY_PACKAGE).load(V332_THEORY_IDENTITY)
        with self.assertRaisesRegex(
            TheoryPackageError, "THEORY_MANIFEST_SIZE_MISMATCH"
        ):
            FileTheoryPackageLoader(_V332_THEORY_PACKAGE).load(
                CURRENT_THEORY_IDENTITY
            )

    def test_rejects_manifest_raw_byte_drift_before_document_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "v3.3.1"
            shutil.copytree(_THEORY_PACKAGE, copied)
            manifest = copied / "MANIFEST.json"
            manifest.write_bytes(manifest.read_bytes() + b"\n")

            with self.assertRaisesRegex(
                TheoryPackageError, "THEORY_MANIFEST_SIZE_MISMATCH"
            ):
                FileTheoryPackageLoader(copied).load(CURRENT_THEORY_IDENTITY)

    def test_rejects_document_raw_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "v3.3.1"
            shutil.copytree(_THEORY_PACKAGE, copied)
            owner = copied / "01_MARKET_COGNITION.md"
            owner.write_bytes(owner.read_bytes() + b"\n")

            with self.assertRaisesRegex(
                TheoryPackageError, "THEORY_DOCUMENT_SIZE_MISMATCH"
            ):
                FileTheoryPackageLoader(copied).load(CURRENT_THEORY_IDENTITY)

    def test_rejects_unlisted_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "v3.3.1"
            shutil.copytree(_THEORY_PACKAGE, copied)
            (copied / "EXTRA.md").write_text("not bound\n", encoding="utf-8")

            with self.assertRaisesRegex(
                TheoryPackageError, "THEORY_MARKDOWN_SET_MISMATCH"
            ):
                FileTheoryPackageLoader(copied).load(CURRENT_THEORY_IDENTITY)

    def test_rejects_symlinked_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "v3.3.1"
            shutil.copytree(_THEORY_PACKAGE, copied)
            owner = copied / "01_MARKET_COGNITION.md"
            owner.unlink()
            try:
                owner.symlink_to(_THEORY_PACKAGE / "01_MARKET_COGNITION.md")
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            with self.assertRaisesRegex(TheoryPackageError, "SYMLINK"):
                FileTheoryPackageLoader(copied).load(CURRENT_THEORY_IDENTITY)


class _RepositoryBackedService:
    def __init__(self, repository: FileCycleRepository) -> None:
        self.repository = repository
        self.run_next_calls = 0
        self.delivery_calls = 0
        self.controller_calls = 0

    def create(self, request: CycleRequest):  # noqa: ANN201
        return self.repository.create(request)

    def status(self, cycle_id: str):  # noqa: ANN201
        return self.repository.load_state(cycle_id)

    def run_next(self, cycle_id: str):  # noqa: ANN201, ARG002
        self.run_next_calls += 1
        raise AssertionError("manifest gate delegated a blocked recovery/advance")

    def deliver_agent_decision(  # noqa: ANN201, ARG002
        self, cycle_id: str, decision_bytes: bytes, *, media_type: str
    ):
        self.delivery_calls += 1
        raise AssertionError("manifest gate delegated a blocked decision")

    def deliver_agent_review(  # noqa: ANN201, ARG002
        self, cycle_id: str, review_bytes: bytes, *, media_type: str
    ):
        self.delivery_calls += 1
        raise AssertionError("manifest gate delegated a blocked review")

    def controller_status(self):  # noqa: ANN201
        return {"schema_version": "2.0.0", "run_status": "STALE_RAW_OPEN"}

    def controller_prepare_worker(  # noqa: ANN201, ARG002
        self,
        cycle_id: str,
        worker_id: str,
        task_path: str | Path,
        *,
        next_slot_at: str | None = None,
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked dispatch")

    def controller_mark_worker_spawn_requested(  # noqa: ANN201, ARG002
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked dispatch")

    def controller_acknowledge_worker_spawn(  # noqa: ANN201, ARG002
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        execution_ref: str,
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked dispatch")

    def controller_complete_worker(  # noqa: ANN201, ARG002
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        output_sha256: str,
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked dispatch")

    def controller_recover_worker(  # noqa: ANN201, ARG002
        self, cycle_id: str, worker_id: str
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked recovery")

    def controller_expire_worker(  # noqa: ANN201, ARG002
        self, cycle_id: str, worker_id: str
    ):
        self.controller_calls += 1
        raise AssertionError("manifest gate delegated a blocked expiry")


class ControllerStateTests(unittest.TestCase):
    @staticmethod
    def _store(
        runtime_root: Path,
        clock: _MutableControllerClock,
        *,
        implementation_sha256: str = "4" * 64,
        allow_initialize: bool = True,
    ) -> FileControllerState:
        return FileControllerState(
            runtime_root,
            run_id=runtime_root.name,
            run_manifest_identity_sha256="1" * 64,
            run_manifest_raw_sha256="2" * 64,
            theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
            implementation_sha256=implementation_sha256,
            contract_identity=AGENT_FIRST_CONTRACT_IDENTITY,
            market_contract_identity="OKX:BTC-USDT-SWAP:SWAP",
            experiment_identity="V331_OFFLINE_CONTROLLER_TEST@" + "5" * 64,
            clock=clock,
            allow_initialize=allow_initialize,
        )

    @staticmethod
    def _write_task(
        runtime_root: Path,
        cycle_id: str,
        worker_id: str,
        *,
        created_at: str,
        deadline_at: str,
    ) -> Path:
        specs = {
            "daily-deep-v1": (
                "DAILY_DEEP",
                "INPUT_SEALED",
                "V331_DAILY_DEEP_READABLE_BASIS_V1",
                "agent-request.json",
                "agent_trade_emotion_market_cycle_agent_decision_request",
                "agent_request_and_non_authoritative_calculations",
            ),
            "decision-v1": (
                "DECISION",
                "INPUT_SEALED",
                "V331_AGENT_FIRST_DECISION_READABLE_V1",
                "agent-request.json",
                "agent_trade_emotion_market_cycle_agent_decision_request",
                "agent_request_and_non_authoritative_calculations",
            ),
            "review-v1": (
                "REVIEW",
                "OUTCOME_SEALED",
                "V331_AGENT_FIRST_REVIEW_READABLE_V1",
                "agent-review-request.json",
                "agent_trade_emotion_market_cycle_agent_review_request",
                "review_request",
            ),
        }
        task_kind, stage, worker_contract, request_name, request_schema, role = specs[
            worker_id
        ]
        request_path = (
            runtime_root
            / "cycles"
            / cycle_id
            / "transport"
            / request_name
        )
        request_path.parent.mkdir(parents=True, exist_ok=True)
        packet = {
            "cycle_id": cycle_id,
            "request_id": f"{cycle_id}.request",
            "time_budget_seconds": 600,
            "theory_identity": CURRENT_THEORY_IDENTITY.to_dict(),
        }
        if worker_id == "review-v1":
            packet["review_due_at"] = deadline_at
            packet["review_requested_at"] = created_at
            packet["behavior_plan_ref"] = {"sha256": "b" * 64}
            packet["outcome_ref"] = {"sha256": "c" * 64}
        else:
            packet["decision_deadline_at"] = deadline_at
            packet["input_snapshot"] = {
                "cycle_id": cycle_id,
                "sealed_at": created_at,
            }
        packet_raw = canonical_bytes(packet)
        request = {
            "schema_id": request_schema,
            "schema_version": "1.0.0",
            "cycle_id": cycle_id,
            "request_id": f"{cycle_id}.request",
            "packet_sha256": hashlib.sha256(packet_raw).hexdigest(),
            "packet_size_bytes": len(packet_raw),
            "packet": packet,
            "instructions": [],
        }
        request_path.write_bytes(canonical_bytes(request) + b"\n")
        worker_root = runtime_root / "agents" / f"{cycle_id}--{worker_id}"
        worker_root.mkdir(parents=True)
        task_path = worker_root / "task.json"
        task = {
            "schema_id": "agent_trade_emotion_v331_worker_task",
            "schema_version": "1.0.0",
            "worker_contract_identity": worker_contract,
            "run_id": runtime_root.name,
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_kind": task_kind,
            "stage": stage,
            "identities": {
                "theory_manifest_sha256": CURRENT_THEORY_IDENTITY.manifest_digest,
                "implementation_sha256": "4" * 64,
                "run_manifest_sha256": "2" * 64,
                "experiment_contract_sha256": "5" * 64,
                "agent_contract_identity": AGENT_FIRST_CONTRACT_IDENTITY,
            },
            "experiment_identity": "V331_OFFLINE_CONTROLLER_TEST@" + "5" * 64,
            "timing": {
                "created_at": created_at,
                "not_before_at": created_at,
                "frozen_deadline_at": deadline_at,
                "hard_stop_seconds": 1800 if worker_id == "daily-deep-v1" else 600,
            },
            "input_refs": [
                {
                    "role": role,
                    "path": str(request_path.resolve(strict=True)),
                    "sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
                    "available_at": created_at,
                }
            ],
            "write_boundary": {
                "worker_root": str(worker_root.resolve(strict=True)),
                "events_path": str((worker_root / "events.jsonl").resolve()),
                "result_path": str((worker_root / "result.json").resolve()),
                "worker_may_write_only": ["events.jsonl", "result.json"],
            },
        }
        task_path.write_bytes(canonical_bytes(task) + b"\n")
        return task_path

    @staticmethod
    def _write_worker_output(
        runtime_root: Path,
        cycle_id: str,
        worker_id: str,
        *,
        completed_at: str,
    ) -> str:
        worker_root = runtime_root / "agents" / f"{cycle_id}--{worker_id}"
        task = loads_json_strict((worker_root / "task.json").read_bytes())
        request_name = (
            "agent-review-request.json"
            if worker_id == "review-v1"
            else "agent-request.json"
        )
        request_path = runtime_root / "cycles" / cycle_id / "transport" / request_name
        request = loads_json_strict(request_path.read_bytes())
        if worker_id == "daily-deep-v1":
            path = worker_root / "result.json"
            document = {
                "schema_id": "agent_trade_emotion_v331_worker_result",
                "schema_version": "1.0.0",
                "run_id": runtime_root.name,
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "status": "COMPLETED",
                "started_at": task["timing"]["created_at"],
                "completed_at": completed_at,
                "elapsed_seconds": 1,
                "input_refs": task["input_refs"],
                "body_markdown": "# Daily Deep\n\nReadable basis only.\n",
            }
        else:
            is_review = worker_id == "review-v1"
            path = (
                runtime_root
                / "cycles"
                / cycle_id
                / "transport"
                / ("agent-review-delivery.json" if is_review else "agent-delivery.json")
            )
            body = "Agent review remains UNKNOWN.\n" if is_review else "WAIT\n"
            body_raw = body.encode("utf-8")
            document = {
                "schema_id": (
                    "agent_trade_emotion_market_cycle_agent_review_delivery"
                    if is_review
                    else "agent_trade_emotion_market_cycle_agent_decision_delivery"
                ),
                "schema_version": "1.0.0",
                "cycle_id": cycle_id,
                "request_sha256": request["packet_sha256"],
                "theory_identity": CURRENT_THEORY_IDENTITY.to_dict(),
                "delivered_at": completed_at,
                "encoding": "UTF-8",
                "media_type": "text/plain",
                (
                    "review_size_bytes" if is_review else "decision_size_bytes"
                ): len(body_raw),
                ("review_sha256" if is_review else "decision_sha256"): hashlib.sha256(
                    body_raw
                ).hexdigest(),
                ("review_text" if is_review else "decision_text"): body,
            }
            if is_review:
                packet = request["packet"]
                document["behavior_plan_sha256"] = packet["behavior_plan_ref"][
                    "sha256"
                ]
                document["outcome_sha256"] = packet["outcome_ref"]["sha256"]
            result_document = {
                "schema_id": "agent_trade_emotion_v331_worker_result",
                "schema_version": "1.0.0",
                "run_id": runtime_root.name,
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "status": "COMPLETED",
                "started_at": task["timing"]["created_at"],
                "completed_at": completed_at,
                "elapsed_seconds": 1,
                "input_refs": [
                    {
                        field: item[field]
                        for field in ("role", "path", "sha256")
                    }
                    for item in task["input_refs"]
                ],
                "body_markdown": body,
            }
            (worker_root / "result.json").write_bytes(
                canonical_bytes(result_document) + b"\n"
            )
        raw = canonical_bytes(document) + b"\n"
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_controller_state_persists_earliest_wake_dispatch_recovery_and_safe_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "run-controller-state"
            runtime_root.mkdir()
            clock = _MutableControllerClock("2026-08-11T00:01:01+00:00")
            store = self._store(runtime_root, clock)
            cycle_id = "controller-cycle"

            next_slot_status = store.schedule_event(
                "next-slot-003",
                "NEXT_SLOT",
                "2026-08-11T00:30:00+00:00",
                cycle_id,
            )
            hard_stop_status = store.schedule_event(
                "worker-hard-stop-003",
                "WORKER_HARD_STOP",
                "2026-08-11T00:11:01+00:00",
                cycle_id,
            )
            next_slot = next_slot_status["events"]["next-slot-003"]
            hard_stop = hard_stop_status["events"]["worker-hard-stop-003"]
            self.assertEqual(next_slot["status"], "PENDING")
            self.assertEqual(
                store.status()["earliest_next_event"]["event_id"],
                hard_stop["event_id"],
            )
            wake_status = store.acknowledge_wake(
                hard_stop["event_id"],
                "scheduler:wake-003",
                hard_stop["due_at"],
            )
            self.assertEqual(
                wake_status["events"][hard_stop["event_id"]]["wake_ack"][
                    "scheduler_ref"
                ],
                "scheduler:wake-003",
            )
            self.assertEqual(
                store.acknowledge_wake(
                    hard_stop["event_id"],
                    "scheduler:wake-003",
                    hard_stop["due_at"],
                ),
                wake_status,
            )
            with self.assertRaises(ControllerStateError):
                store.acknowledge_wake(
                    hard_stop["event_id"],
                    "scheduler:conflict",
                    hard_stop["due_at"],
                )
            store.resolve_event(hard_stop["event_id"])
            self.assertEqual(
                store.status()["earliest_next_event"]["event_id"],
                next_slot["event_id"],
            )

            tuples = (
                (
                    "controller-daily",
                    "daily-deep-v1",
                    "2026-08-11T00:01:01+00:00",
                    "2026-08-11T00:31:01+00:00",
                    "2026-08-11T00:01:02+00:00",
                ),
                (
                    "controller-decision",
                    "decision-v1",
                    "2026-08-11T00:12:01+00:00",
                    "2026-08-11T00:22:01+00:00",
                    "2026-08-11T00:12:02+00:00",
                ),
                (
                    "controller-review",
                    "review-v1",
                    "2026-08-11T00:23:01+00:00",
                    "2026-08-11T00:33:01+00:00",
                    "2026-08-11T00:23:02+00:00",
                ),
            )
            last_task_path: Path | None = None
            for worker_cycle, worker_id, created_at, deadline_at, output_at in tuples:
                with self.subTest(worker_id=worker_id):
                    clock.current = created_at
                    task_path = self._write_task(
                        runtime_root,
                        worker_cycle,
                        worker_id,
                        created_at=created_at,
                        deadline_at=deadline_at,
                    )
                    last_task_path = task_path
                    prepared = store.prepare_worker(
                        worker_cycle,
                        worker_id,
                        task_path,
                        next_slot_at=(
                            "2026-08-11T00:40:00+00:00"
                            if worker_id == "decision-v1"
                            else None
                        ),
                    )
                    self.assertEqual(prepared["status"], "PREPARED")
                    dispatch_id = prepared["dispatch_id"]
                    self.assertEqual(
                        store.recover_worker(worker_cycle, worker_id)[
                            "recovery_action"
                        ],
                        "RECOVER_PREPARED",
                    )
                    requested = store.mark_spawn_requested(
                        worker_cycle, worker_id, dispatch_id
                    )
                    self.assertEqual(requested["status"], "SPAWN_REQUESTED")
                    self.assertEqual(
                        store.recover_worker(worker_cycle, worker_id)[
                            "recovery_action"
                        ],
                        "RECONCILE_SPAWN",
                    )
                    dispatched = store.acknowledge_spawn(
                        worker_cycle,
                        worker_id,
                        dispatch_id,
                        f"codex-worker:{worker_cycle}",
                    )
                    self.assertEqual(dispatched["status"], "DISPATCHED")
                    self.assertEqual(
                        store.recover_worker(worker_cycle, worker_id)[
                            "recovery_action"
                        ],
                        "WAIT_FOR_OUTPUT",
                    )
                    clock.current = output_at
                    output_sha256 = self._write_worker_output(
                        runtime_root,
                        worker_cycle,
                        worker_id,
                        completed_at=output_at,
                    )
                    if worker_id in {"decision-v1", "review-v1"}:
                        result_path = (
                            runtime_root
                            / "agents"
                            / f"{worker_cycle}--{worker_id}"
                            / "result.json"
                        )
                        result_raw = result_path.read_bytes()
                        result_path.unlink()
                        with self.assertRaisesRegex(
                            ControllerStateError,
                            "CONTROLLER_WORKER_RESULT_INVALID",
                        ):
                            store.complete_worker(
                                worker_cycle,
                                worker_id,
                                dispatch_id,
                                output_sha256,
                            )
                        self.assertEqual(
                            store.recover_worker(worker_cycle, worker_id)[
                                "recovery_action"
                            ],
                            "COMPLETE_OUTPUT",
                        )
                        result_path.write_bytes(result_raw)
                        mismatched_ref = loads_json_strict(result_raw)
                        mismatched_ref["input_refs"][0]["available_at"] = (
                            "2099-01-01T00:00:00+00:00"
                        )
                        result_path.write_bytes(
                            canonical_bytes(mismatched_ref) + b"\n"
                        )
                        with self.assertRaisesRegex(
                            ControllerStateError,
                            "CONTROLLER_WORKER_RESULT_INVALID",
                        ):
                            store.complete_worker(
                                worker_cycle,
                                worker_id,
                                dispatch_id,
                                output_sha256,
                            )
                        for field, value in (
                            ("role", "wrong-role"),
                            ("path", "/wrong/path"),
                            ("sha256", "0" * 64),
                        ):
                            with self.subTest(
                                result_ref_worker=worker_id,
                                mismatched_field=field,
                            ):
                                mismatched_ref = loads_json_strict(result_raw)
                                mismatched_ref["input_refs"][0][field] = value
                                result_path.write_bytes(
                                    canonical_bytes(mismatched_ref) + b"\n"
                                )
                                with self.assertRaisesRegex(
                                    ControllerStateError,
                                    "CONTROLLER_WORKER_RESULT_INVALID",
                                ):
                                    store.complete_worker(
                                        worker_cycle,
                                        worker_id,
                                        dispatch_id,
                                        output_sha256,
                                    )
                                missing_ref = loads_json_strict(result_raw)
                                del missing_ref["input_refs"][0][field]
                                result_path.write_bytes(
                                    canonical_bytes(missing_ref) + b"\n"
                                )
                                with self.assertRaisesRegex(
                                    ControllerStateError,
                                    "CONTROLLER_WORKER_RESULT_INVALID",
                                ):
                                    store.complete_worker(
                                        worker_cycle,
                                        worker_id,
                                        dispatch_id,
                                        output_sha256,
                                    )
                        result_path.write_bytes(result_raw)
                        mismatched = loads_json_strict(result_raw)
                        mismatched["body_markdown"] += "Primary replacement.\n"
                        result_path.write_bytes(canonical_bytes(mismatched) + b"\n")
                        with self.assertRaisesRegex(
                            ControllerStateError,
                            "CONTROLLER_WORKER_RESULT_DELIVERY_MISMATCH",
                        ):
                            store.complete_worker(
                                worker_cycle,
                                worker_id,
                                dispatch_id,
                                output_sha256,
                            )
                        self.assertEqual(
                            store.recover_worker(worker_cycle, worker_id)[
                                "recovery_action"
                            ],
                            "COMPLETE_OUTPUT",
                        )
                        result_path.write_bytes(result_raw)
                    completed = store.complete_worker(
                        worker_cycle,
                        worker_id,
                        dispatch_id,
                        output_sha256,
                    )
                    self.assertEqual(completed["status"], "COMPLETED")
                    self.assertEqual(
                        store.complete_worker(
                            worker_cycle,
                            worker_id,
                            dispatch_id,
                            output_sha256,
                        ),
                        completed,
                    )
                    with self.assertRaises(ControllerStateError):
                        store.complete_worker(
                            worker_cycle, worker_id, dispatch_id, "0" * 64
                        )

            ack_loss_tuples = (
                (
                    "ack-loss-daily",
                    "daily-deep-v1",
                    "2026-08-11T00:34:01+00:00",
                    "2026-08-11T01:04:01+00:00",
                    "2026-08-11T01:03:59+00:00",
                    "2026-08-11T01:04:01+00:00",
                ),
                (
                    "ack-loss-decision",
                    "decision-v1",
                    "2026-08-11T01:05:01+00:00",
                    "2026-08-11T01:15:01+00:00",
                    "2026-08-11T01:14:59+00:00",
                    "2026-08-11T01:15:01+00:00",
                ),
                (
                    "ack-loss-review",
                    "review-v1",
                    "2026-08-11T01:16:01+00:00",
                    "2026-08-11T01:26:01+00:00",
                    "2026-08-11T01:25:59+00:00",
                    "2026-08-11T01:26:01+00:00",
                ),
            )
            for (
                worker_cycle,
                worker_id,
                created_at,
                deadline_at,
                output_at,
                recovered_at,
            ) in ack_loss_tuples:
                with self.subTest(ack_loss_worker=worker_id):
                    clock.current = created_at
                    task_path = self._write_task(
                        runtime_root,
                        worker_cycle,
                        worker_id,
                        created_at=created_at,
                        deadline_at=deadline_at,
                    )
                    prepared = store.prepare_worker(
                        worker_cycle, worker_id, task_path
                    )
                    dispatch_id = prepared["dispatch_id"]
                    store.mark_spawn_requested(
                        worker_cycle, worker_id, dispatch_id
                    )
                    output_sha256 = self._write_worker_output(
                        runtime_root,
                        worker_cycle,
                        worker_id,
                        completed_at=output_at,
                    )
                    clock.current = recovered_at
                    self.assertEqual(
                        store.recover_worker(worker_cycle, worker_id)[
                            "recovery_action"
                        ],
                        "RECONCILE_SPAWN",
                    )
                    self.assertEqual(
                        store.acknowledge_spawn(
                            worker_cycle,
                            worker_id,
                            dispatch_id,
                            f"codex-worker:{worker_cycle}",
                        )["status"],
                        "DISPATCHED",
                    )
                    self.assertEqual(
                        store.complete_worker(
                            worker_cycle,
                            worker_id,
                            dispatch_id,
                            output_sha256,
                        )["status"],
                        "COMPLETED",
                    )

            request_only_cycle = "controller-request-only"
            clock.current = "2026-08-11T01:27:01+00:00"
            self._write_task(
                runtime_root,
                request_only_cycle,
                "decision-v1",
                created_at="2026-08-11T01:27:01+00:00",
                deadline_at="2026-08-11T01:37:01+00:00",
            )
            request_only = store.decision_deadline(request_only_cycle)
            self.assertEqual(request_only["status"], "REQUEST_ONLY")
            self.assertIsNone(request_only["dispatch_id"])
            with self.assertRaisesRegex(
                ControllerStateError, "CONTROLLER_WORKER_DEADLINE_NOT_EXPIRED"
            ):
                store.require_worker_deadline_expired(
                    request_only_cycle, "decision-v1"
                )
            clock.current = "2026-08-11T01:37:01+00:00"
            self.assertEqual(
                store.require_worker_deadline_expired(
                    request_only_cycle, "decision-v1"
                )["status"],
                "REQUEST_ONLY",
            )

            reloaded = self._store(runtime_root, clock)
            self.assertEqual(
                reloaded.recover_worker("controller-review", "review-v1")[
                    "recovery_action"
                ],
                "COMPLETED",
            )
            closed_process = self._store(
                runtime_root, clock, allow_initialize=False
            )
            self.assertEqual(closed_process.status()["schema_version"], "2.0.0")
            never_opened = Path(temporary) / "closed-never-opened"
            never_opened.mkdir()
            with self.assertRaisesRegex(
                ControllerStateError, "CONTROLLER_STATE_NOT_INITIALIZED_BEFORE_CLOSE"
            ):
                self._store(never_opened, clock, allow_initialize=False)
            self.assertFalse(
                (never_opened / "controller" / "wake-dispatch.json").exists()
            )
            state_path = runtime_root / "controller" / "wake-dispatch.json"
            state_raw = state_path.read_bytes()
            state_path.unlink()
            with self.assertRaisesRegex(
                ControllerStateError,
                "CONTROLLER_STATE_MISSING_AFTER_INITIALIZATION",
            ):
                self._store(runtime_root, clock)
            state_path.write_bytes(state_raw)
            (runtime_root / "controller" / "wake-dispatch.initialized.json").unlink()
            state_path.unlink()
            with self.assertRaisesRegex(
                ControllerStateError,
                "CONTROLLER_STATE_MISSING_AFTER_INITIALIZATION",
            ):
                self._store(runtime_root, clock)
            state_path.write_bytes(state_raw)
            with self.assertRaises(ControllerStateError):
                self._store(
                    runtime_root, clock, implementation_sha256="9" * 64
                ).status()

            state_document = loads_json_strict(state_path.read_bytes())
            first_dispatch = next(iter(state_document["worker_dispatches"].values()))
            first_dispatch["status"] = "CORRUPT"
            state_path.write_bytes(canonical_bytes(state_document) + b"\n")
            with self.assertRaisesRegex(
                ControllerStateError, "CONTROLLER_WORKER_DISPATCH_INVALID"
            ):
                self._store(runtime_root, clock)
            state_path.write_bytes(state_raw)

            assert last_task_path is not None
            outside = Path(temporary) / "outside-task.json"
            outside.write_bytes(last_task_path.read_bytes())
            with self.assertRaises(ControllerStateError):
                store.prepare_worker("outside-cycle", "decision-v1", outside)
            with self.assertRaisesRegex(
                ControllerStateError, "CONTROLLER_CYCLE_ID_INVALID"
            ):
                store.prepare_worker("../escape", "decision-v1", last_task_path)
            symlinked_task = (
                runtime_root / "agents" / "symlink-cycle--decision-v1" / "task.json"
            )
            symlinked_task.parent.mkdir()
            try:
                symlinked_task.symlink_to(outside)
            except OSError:
                pass
            else:
                with self.assertRaises(ControllerStateError):
                    store.prepare_worker(
                        "symlink-cycle", "decision-v1", symlinked_task
                    )


class MarketCycleRuntimeBoundaryTests(unittest.TestCase):
    def test_implementation_identity_includes_durable_and_canonical_safety_dependencies(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            implementation_directories = (
                "trade_system/theory_paper_v2/application/market_cycle",
                "trade_system/theory_paper_v2/domain/market_cycle",
                "trade_system/theory_paper_v2/infrastructure/market_cycle",
                "trade_system/theory_paper_v2/infrastructure/market_data",
            )
            for relative in implementation_directories:
                directory = project_root / relative
                directory.mkdir(parents=True)
                (directory / "owner.py").write_text("OWNER = 1\n", encoding="utf-8")
            safety_files = (
                "trade_system/theory_paper_v2/presentation/market_cycle.py",
                "trade_system/theory_paper_v2/presentation/paper_agent.py",
                "trade_system/theory_paper_v2/domain/contracts/canonical.py",
                "trade_system/theory_paper_v2/v32_durable_json.py",
            )
            for relative in safety_files:
                path = project_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("VALUE = 1\n", encoding="utf-8")

            baseline = current_implementation_identity(project_root)
            for relative in safety_files[1:]:
                with self.subTest(relative=relative):
                    path = project_root / relative
                    path.write_text("VALUE = 2\n", encoding="utf-8")
                    self.assertNotEqual(
                        current_implementation_identity(project_root), baseline
                    )
                    path.write_text("VALUE = 1\n", encoding="utf-8")

    market_contract_identity = "OKX:BTC-USDT-SWAP:SWAP"

    @staticmethod
    def _manifest_document(
        runtime_root: Path,
        *,
        status: str = "OPEN",
        **overrides: str,
    ) -> dict[str, str]:
        document = {
            "schema_id": RUN_MANIFEST_SCHEMA_ID,
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": runtime_root.name,
            "theory_manifest_sha256": CURRENT_THEORY_IDENTITY.manifest_digest,
            "implementation_sha256": current_implementation_identity(),
            "contract_identity": AGENT_FIRST_CONTRACT_IDENTITY,
            "market_contract_identity": (
                MarketCycleRuntimeBoundaryTests.market_contract_identity
            ),
            "experiment_identity": "V331_OFFLINE_AGENT_FIRST_ACCEPTANCE",
            "status": status,
        }
        document.update(overrides)
        return document

    @staticmethod
    def _write_manifest(runtime_root: Path, document: dict[str, str]) -> bytes:
        path = runtime_root / RUN_MANIFEST_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical_bytes(document) + b"\n"
        path.write_bytes(raw)
        return raw

    @staticmethod
    def _write_identity_seal(
        runtime_root: Path, document: dict[str, str]
    ) -> bytes:
        manifest_raw = canonical_bytes(document) + b"\n"
        manifest = FrozenRunManifest(
            run_id=document["run_id"],
            theory_manifest_sha256=document["theory_manifest_sha256"],
            implementation_sha256=document["implementation_sha256"],
            contract_identity=document["contract_identity"],
            market_contract_identity=document["market_contract_identity"],
            experiment_identity=document["experiment_identity"],
            status=document["status"],
            raw_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        )
        initialize_run_identity_seal(runtime_root, manifest)
        return run_identity_seal_path(runtime_root).read_bytes()

    @staticmethod
    def _write_closure(runtime_root: Path, identity_sha256: str) -> bytes:
        document = {
            "schema_id": RUN_CLOSURE_SCHEMA_ID,
            "schema_version": RUN_CLOSURE_SCHEMA_VERSION,
            "run_id": runtime_root.name,
            "run_manifest_identity_sha256": identity_sha256,
            "status": "CLOSED",
        }
        raw = canonical_bytes(document) + b"\n"
        (runtime_root / RUN_CLOSURE_RELATIVE_PATH).write_bytes(raw)
        return raw

    def _bound_service(
        self, runtime_root: Path, *, status: str = "OPEN"
    ) -> tuple[
        ManifestBoundCycleService,
        FileCycleRepository,
        _RepositoryBackedService,
    ]:
        document = self._manifest_document(runtime_root, status=status)
        self._write_manifest(runtime_root, document)
        self._write_identity_seal(runtime_root, document)
        implementation = current_implementation_identity()
        manifest = _read_run_manifest(
            runtime_root,
            theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
            implementation_sha256=implementation,
        )
        repository = FileCycleRepository(runtime_root / "cycles")
        delegate = _RepositoryBackedService(repository)
        service = ManifestBoundCycleService(
            service=delegate,  # type: ignore[arg-type]
            repository=repository,
            gate=RunManifestGate(runtime_root, manifest),
        )
        return service, repository, delegate

    def test_run_manifest_requires_exact_frozen_theory_code_and_contract_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "run-manifest-contract"
            runtime_root.mkdir()
            (runtime_root / "controller").mkdir()
            with self.assertRaisesRegex(MarketCycleRuntimeError, "RUN_MANIFEST_MISSING"):
                _read_run_manifest(
                    runtime_root,
                    theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
                    implementation_sha256=current_implementation_identity(),
                )

            variants = (
                (
                    "theory",
                    {"theory_manifest_sha256": "0" * 64},
                    "RUN_MANIFEST_THEORY_IDENTITY_MISMATCH",
                ),
                (
                    "implementation",
                    {"implementation_sha256": "0" * 64},
                    "RUN_MANIFEST_IMPLEMENTATION_IDENTITY_MISMATCH",
                ),
                (
                    "contract",
                    {"contract_identity": "V330_STRICT_SCHEMA"},
                    "RUN_MANIFEST_CONTRACT_IDENTITY_MISMATCH",
                ),
            )
            for name, changes, code in variants:
                with self.subTest(name=name):
                    document = self._manifest_document(runtime_root, **changes)
                    self._write_manifest(runtime_root, document)
                    with self.assertRaisesRegex(MarketCycleRuntimeError, code):
                        _read_run_manifest(
                            runtime_root,
                            theory_manifest_sha256=(
                                CURRENT_THEORY_IDENTITY.manifest_digest
                            ),
                            implementation_sha256=current_implementation_identity(),
                        )

            valid = self._manifest_document(runtime_root)
            self._write_manifest(runtime_root, valid)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_IDENTITY_SEAL_MISSING"
            ):
                _read_run_manifest(
                    runtime_root,
                    theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
                    implementation_sha256=current_implementation_identity(),
                )
            seal_raw = self._write_identity_seal(runtime_root, valid)
            self.assertEqual(
                loads_json_strict(seal_raw)["run_id"], runtime_root.name
            )
            self.assertEqual(
                loads_json_strict(seal_raw)["run_root_canonical_path"],
                str(runtime_root.resolve(strict=True)),
            )
            self.assertNotIn(
                runtime_root,
                run_identity_seal_path(runtime_root).parents,
            )
            manifest = _read_run_manifest(
                runtime_root,
                theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
                implementation_sha256=current_implementation_identity(),
            )
            self.assertEqual(manifest.contract_identity, AGENT_FIRST_CONTRACT_IDENTITY)
            self.assertEqual(
                manifest.market_contract_identity, self.market_contract_identity
            )
            self.assertEqual(manifest.experiment_identity, valid["experiment_identity"])
            default_runtime = build_market_cycle_runtime(runtime_root=runtime_root)
            self.assertEqual(default_runtime.identity, CURRENT_THEORY_IDENTITY)
            self.assertEqual(
                default_runtime.run_manifest.theory_manifest_sha256,
                CURRENT_THEORY_IDENTITY.manifest_digest,
            )

            v332_root = Path(temporary) / "run-manifest-v332"
            v332_root.mkdir()
            v332_document = self._manifest_document(
                v332_root,
                theory_manifest_sha256=V332_THEORY_IDENTITY.manifest_digest,
                contract_identity=V332_RUNTIME_CONTRACT_IDENTITY,
                market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
                experiment_identity="V332_GATE0_IDENTITY_COMPOSITION",
            )
            self._write_manifest(v332_root, v332_document)
            self._write_identity_seal(v332_root, v332_document)
            v332_runtime = build_market_cycle_runtime(
                runtime_root=v332_root,
                theory_package=_V332_THEORY_PACKAGE,
                expected_theory_identity=V332_THEORY_IDENTITY,
            )
            self.assertEqual(v332_runtime.identity, V332_THEORY_IDENTITY)
            self.assertEqual(
                v332_runtime.run_manifest.theory_manifest_sha256,
                V332_THEORY_IDENTITY.manifest_digest,
            )
            v332_request = replace(
                _request(cycle_id="v332-bound-cycle"),
                instrument_id="HYPE-USDT-SWAP",
                contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
                data_profile="BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
                theory_identity=V332_THEORY_IDENTITY,
            )
            self.assertEqual(v332_runtime.service.create(v332_request).stage, "REQUESTED")
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_MANIFEST_CREATE_THEORY_MISMATCH"
            ):
                v332_runtime.service.create(
                    replace(
                        _request(cycle_id="v331-request-on-v332-runtime"),
                        instrument_id="HYPE-USDT-SWAP",
                        contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
                        data_profile="BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
                    )
                )

    def test_open_binding_blocks_identity_drift_missing_binding_and_copied_cycle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "run-open-one"
            first_root.mkdir()
            service, repository, delegate = self._bound_service(first_root)
            request = _request(cycle_id="bound-cycle")
            self.assertEqual(service.create(request).stage, "REQUESTED")
            binding_path = (
                first_root
                / "cycles"
                / request.cycle_id
                / CYCLE_RUN_BINDING_RELATIVE_PATH
            )
            binding = loads_json_strict(binding_path.read_bytes())
            self.assertEqual(binding["cycle_id"], request.cycle_id)
            self.assertEqual(binding["run_id"], first_root.name)
            self.assertEqual(
                binding["contract_identity"], AGENT_FIRST_CONTRACT_IDENTITY
            )
            self.assertEqual(
                binding["market_contract_identity"], self.market_contract_identity
            )
            self.assertEqual(
                binding["implementation_sha256"], current_implementation_identity()
            )
            self.assertEqual(
                binding["experiment_identity"],
                "V331_OFFLINE_AGENT_FIRST_ACCEPTANCE",
            )
            self.assertEqual(len(binding["run_manifest_identity_sha256"]), 64)
            self.assertEqual(service.create(request).stage, "REQUESTED")
            self.assertEqual(loads_json_strict(binding_path.read_bytes()), binding)
            self.assertEqual(service.status(request.cycle_id).stage, "REQUESTED")

            wrong_contract = replace(
                _request(cycle_id="wrong-market-contract"),
                contract_identity="OTHER:CONTRACT",
            )
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_MANIFEST_CREATE_CONTRACT_MISMATCH"
            ):
                service.create(wrong_contract)
            self.assertFalse(
                (first_root / "cycles" / wrong_contract.cycle_id).exists()
            )

            missing = _request(cycle_id="missing-binding")
            repository.create(missing)
            with self.assertRaisesRegex(MarketCycleRuntimeError, "RUN_BINDING_MISSING"):
                service.create(missing)
            with self.assertRaisesRegex(MarketCycleRuntimeError, "RUN_BINDING_MISSING"):
                service.status(missing.cycle_id)
            with self.assertRaisesRegex(MarketCycleRuntimeError, "RUN_BINDING_MISSING"):
                service.run_next(missing.cycle_id)
            with self.assertRaisesRegex(MarketCycleRuntimeError, "RUN_BINDING_MISSING"):
                service.controller_expire_worker(missing.cycle_id, "decision-v1")
            self.assertEqual(delegate.run_next_calls, 0)
            self.assertEqual(delegate.controller_calls, 0)

            with mock.patch(
                "trade_system.theory_paper_v2.infrastructure.market_cycle.runtime.current_implementation_identity",
                return_value="0" * 64,
            ):
                with self.assertRaisesRegex(
                    MarketCycleRuntimeError,
                    "RUN_MANIFEST_IMPLEMENTATION_IDENTITY_MISMATCH",
                ):
                    service.status(request.cycle_id)
                with self.assertRaisesRegex(
                    MarketCycleRuntimeError,
                    "RUN_MANIFEST_IMPLEMENTATION_IDENTITY_MISMATCH",
                ):
                    service.controller_expire_worker(
                        request.cycle_id, "decision-v1"
                    )
            self.assertEqual(delegate.run_next_calls, 0)
            self.assertEqual(delegate.controller_calls, 0)

            original_manifest = self._manifest_document(first_root)
            changed_experiment = dict(original_manifest)
            changed_experiment["experiment_identity"] = "OTHER_EXPERIMENT"
            self._write_manifest(first_root, changed_experiment)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_IDENTITY_SEAL_MISMATCH"
            ):
                service.run_next(request.cycle_id)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_IDENTITY_SEAL_MISMATCH"
            ):
                service.controller_expire_worker(request.cycle_id, "decision-v1")
            self.assertEqual(delegate.run_next_calls, 0)
            self.assertEqual(delegate.controller_calls, 0)
            self._write_manifest(first_root, original_manifest)

            cross_process_rewrites = (
                (
                    "experiment",
                    {"experiment_identity": "OTHER_EXPERIMENT"},
                    CURRENT_THEORY_IDENTITY.manifest_digest,
                    current_implementation_identity(),
                ),
                (
                    "market_contract",
                    {"market_contract_identity": "OKX:ETH-USDT-SWAP:SWAP"},
                    CURRENT_THEORY_IDENTITY.manifest_digest,
                    current_implementation_identity(),
                ),
                (
                    "implementation",
                    {"implementation_sha256": "0" * 64},
                    CURRENT_THEORY_IDENTITY.manifest_digest,
                    "0" * 64,
                ),
                (
                    "theory",
                    {"theory_manifest_sha256": "1" * 64},
                    "1" * 64,
                    current_implementation_identity(),
                ),
            )
            for name, changes, expected_theory, expected_implementation in (
                cross_process_rewrites
            ):
                with self.subTest(cross_process_rewrite=name):
                    rewritten = dict(original_manifest)
                    rewritten.update(changes)
                    self._write_manifest(first_root, rewritten)
                    with self.assertRaises(CanonicalContractError):
                        self._write_identity_seal(first_root, rewritten)

                    def fresh_process_create() -> object:
                        observed_manifest = _read_run_manifest(
                            first_root,
                            theory_manifest_sha256=expected_theory,
                            implementation_sha256=expected_implementation,
                        )
                        fresh_repository = FileCycleRepository(
                            first_root / "cycles"
                        )
                        fresh_service = ManifestBoundCycleService(
                            service=_RepositoryBackedService(fresh_repository),  # type: ignore[arg-type]
                            repository=fresh_repository,
                            gate=RunManifestGate(first_root, observed_manifest),
                        )
                        return fresh_service.create(
                            _request(cycle_id=f"rewritten-{name}")
                        )

                    with self.assertRaisesRegex(
                        MarketCycleRuntimeError, "RUN_IDENTITY_SEAL_MISMATCH"
                    ):
                        fresh_process_create()
                    self.assertFalse(
                        (first_root / "cycles" / f"rewritten-{name}").exists()
                    )
            self._write_manifest(first_root, original_manifest)

            manifest_path = first_root / RUN_MANIFEST_RELATIVE_PATH
            manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
            with self.assertRaises(MarketCycleRuntimeError):
                service.status(request.cycle_id)
            self._write_manifest(first_root, original_manifest)

            second_root = base / "run-open-two"
            second_root.mkdir()
            second_service, _, _ = self._bound_service(second_root)
            shutil.copytree(
                first_root / "cycles" / request.cycle_id,
                second_root / "cycles" / request.cycle_id,
                dirs_exist_ok=True,
            )
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_BINDING_IDENTITY_MISMATCH"
            ):
                second_service.status(request.cycle_id)

            registry_anchor = run_identity_seal_path(first_root)
            anchored_bytes = registry_anchor.read_bytes()
            shutil.rmtree(first_root)
            first_root.mkdir()
            replacement = dict(original_manifest)
            replacement["experiment_identity"] = "REPLACED_ROOT_EXPERIMENT"
            self._write_manifest(first_root, replacement)
            fake_root_seal = first_root / "controller" / "run-identity.json"
            fake_root_seal.write_bytes(
                canonical_bytes(
                    {
                        "run_id": first_root.name,
                        "experiment_identity": "REPLACED_ROOT_EXPERIMENT",
                    }
                )
                + b"\n"
            )
            self.assertEqual(registry_anchor.read_bytes(), anchored_bytes)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_IDENTITY_SEAL_MISMATCH"
            ):
                observed = _read_run_manifest(
                    first_root,
                    theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
                    implementation_sha256=current_implementation_identity(),
                )
                replacement_repository = FileCycleRepository(first_root / "cycles")
                ManifestBoundCycleService(
                    service=_RepositoryBackedService(replacement_repository),  # type: ignore[arg-type]
                    repository=replacement_repository,
                    gate=RunManifestGate(first_root, observed),
                ).create(_request(cycle_id="replacement-root-new-cycle"))
            self.assertFalse(
                (first_root / "cycles" / "replacement-root-new-cycle").exists()
            )

    def test_closed_run_allows_bound_reads_but_blocks_all_active_and_recovery_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "run-close-transition"
            runtime_root.mkdir()
            service, _, delegate = self._bound_service(runtime_root)
            request = _request(cycle_id="closed-readable")
            self.assertEqual(service.create(request).stage, "REQUESTED")
            binding = loads_json_strict(
                (
                    runtime_root
                    / "cycles"
                    / request.cycle_id
                    / CYCLE_RUN_BINDING_RELATIVE_PATH
                ).read_bytes()
            )

            closed = self._manifest_document(runtime_root, status="CLOSED")
            self._write_manifest(runtime_root, closed)
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_CLOSURE_MARKER_MISSING"
            ):
                service.status(request.cycle_id)
            closure_raw = self._write_closure(
                runtime_root, binding["run_manifest_identity_sha256"]
            )
            self.assertEqual(
                loads_json_strict(closure_raw),
                {
                    "schema_id": RUN_CLOSURE_SCHEMA_ID,
                    "schema_version": RUN_CLOSURE_SCHEMA_VERSION,
                    "run_id": runtime_root.name,
                    "run_manifest_identity_sha256": binding[
                        "run_manifest_identity_sha256"
                    ],
                    "status": "CLOSED",
                },
            )
            self.assertEqual(service.status(request.cycle_id).stage, "REQUESTED")
            self.assertEqual(
                service.verify_cycle_read(request.cycle_id).status, "CLOSED"
            )
            closed_controller = service.controller_status()
            self.assertEqual(closed_controller["run_status"], "CLOSED")
            self.assertEqual(closed_controller["controller_mode"], "READ_ONLY_CLOSED")
            self.assertFalse(closed_controller["mutations_allowed"])

            fresh_manifest = _read_run_manifest(
                runtime_root,
                theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
                implementation_sha256=current_implementation_identity(),
            )
            fresh_repository = FileCycleRepository(runtime_root / "cycles")
            fresh_closed = ManifestBoundCycleService(
                service=_RepositoryBackedService(fresh_repository),  # type: ignore[arg-type]
                repository=fresh_repository,
                gate=RunManifestGate(runtime_root, fresh_manifest),
            )
            self.assertEqual(
                fresh_closed.status(request.cycle_id).stage, "REQUESTED"
            )
            self.assertEqual(
                fresh_closed.controller_status()["run_status"], "CLOSED"
            )

            self._write_manifest(runtime_root, self._manifest_document(runtime_root))
            with self.assertRaisesRegex(
                MarketCycleRuntimeError, "RUN_CLOSURE_RECOVERY_REQUIRED"
            ):
                service.status(request.cycle_id)
            self._write_manifest(runtime_root, closed)

            active_calls = (
                lambda: service.create(_request(cycle_id="closed-new")),
                lambda: service.run_next(request.cycle_id),
                lambda: service.deliver_agent_decision(request.cycle_id, b"WAIT\n"),
                lambda: service.deliver_agent_review(request.cycle_id, b"review\n"),
                lambda: service.controller_prepare_worker(
                    request.cycle_id,
                    "decision-v1",
                ),
                lambda: service.controller_expire_worker(
                    request.cycle_id, "decision-v1"
                ),
            )
            for call in active_calls:
                with self.assertRaisesRegex(
                    MarketCycleRuntimeError, "RUN_MANIFEST_NOT_OPEN"
                ):
                    call()
            self.assertEqual(delegate.run_next_calls, 0)
            self.assertEqual(delegate.delivery_calls, 0)
            self.assertEqual(delegate.controller_calls, 0)

    def test_memory_descriptor_is_all_or_nothing_verified_and_absence_is_unknown(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime_root = base / "run-memory"
            (runtime_root / "controller").mkdir(parents=True)
            missing = load_verified_memory_context(runtime_root)
            self.assertEqual(missing, ())
            self.assertEqual(verified_memory_context(missing)["status"], "UNKNOWN")

            source_run_id = runtime_root.name
            source_root = runtime_root
            raw_store = FileRawCaptureStore(source_root)
            source_repository = FileCycleRepository(
                source_root / "cycles", raw_capture_verifier=raw_store
            )

            def create_source(
                cycle_id: str,
                *,
                instrument_id: str,
                contract_identity: str,
                source_cutoff_at: str,
                sealed_at: str,
            ) -> tuple[InputSnapshot, ArtifactRef]:
                request = CycleRequest(
                    request_id=f"{cycle_id}.request",
                    cycle_id=cycle_id,
                    requested_at="2026-08-10T23:59:00+00:00",
                    venue_id="OKX",
                    instrument_id=instrument_id,
                    contract_identity=contract_identity,
                    analysis_profile="COLD",
                    data_profile="BASELINE_PRICE",
                    outcome_horizon_seconds=3600,
                    outcome_tolerance_seconds=60,
                    lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
                )
                requested = source_repository.create(request)
                raw_ref = _seal_raw_reference(
                    raw_store,
                    cycle_id=cycle_id,
                    capture_id=f"{cycle_id}-baseline",
                    payload=f"{cycle_id}-raw".encode(),
                )
                observation = {
                    "available_at": source_cutoff_at,
                    "raw_sha256": raw_ref.sha256,
                }
                bars = {**observation, "value": [], "last_closed_at": source_cutoff_at}
                snapshot = InputSnapshot.seal(
                    request,
                    snapshot_id=f"{cycle_id}.snapshot",
                    source_cutoff_at=source_cutoff_at,
                    decision_at=source_cutoff_at,
                    sealed_at=sealed_at,
                    core_observations={
                        "server_time": {**observation, "value": source_cutoff_at},
                        "instrument": {**observation, "value": instrument_id},
                        "mark_price": {**observation, "value": "120000.0"},
                        "closed_15m_bars": bars,
                    },
                    optional_observations={},
                    unknowns=("OPTIONAL_CONTEXT:UNKNOWN",),
                    raw_refs=(raw_ref,),
                    source_health=(),
                )
                sealed = source_repository.transition(
                    expected=requested,
                    artifacts=(snapshot,),
                    next_stage="INPUT_SEALED",
                    next_action="ANALYZE",
                )
                return snapshot, sealed.artifact_refs[0]

            eligible_snapshot, eligible_ref = create_source(
                "prior-eligible",
                instrument_id="BTC-USDT-SWAP",
                contract_identity="OKX:BTC-USDT-SWAP:SWAP",
                source_cutoff_at="2026-08-10T23:59:59+00:00",
                sealed_at="2026-08-11T00:00:00+00:00",
            )
            future_snapshot, future_ref = create_source(
                "prior-future",
                instrument_id="BTC-USDT-SWAP",
                contract_identity="OKX:BTC-USDT-SWAP:SWAP",
                source_cutoff_at="2026-08-11T00:00:01+00:00",
                sealed_at="2026-08-11T00:00:02+00:00",
            )
            _, other_ref = create_source(
                "prior-other-instrument",
                instrument_id="ETH-USDT-SWAP",
                contract_identity="OKX:ETH-USDT-SWAP:SWAP",
                source_cutoff_at="2026-08-10T23:59:59+00:00",
                sealed_at="2026-08-11T00:00:00+00:00",
            )
            descriptors = [
                {
                    "kind": "RECENT_FULL_DAILY",
                    "source_run_id": source_run_id,
                    "source_cycle_id": "prior-eligible",
                    "source_ref": eligible_ref.to_dict(),
                },
                {
                    "kind": "RECENT_FULL_DAILY",
                    "source_run_id": source_run_id,
                    "source_cycle_id": "prior-future",
                    "source_ref": future_ref.to_dict(),
                },
            ]
            descriptor = {
                "schema_id": MEMORY_CONTEXT_SCHEMA_ID,
                "schema_version": MEMORY_CONTEXT_SCHEMA_VERSION,
                "items": descriptors,
            }
            descriptor_path = runtime_root / MEMORY_CONTEXT_RELATIVE_PATH
            descriptor_path.write_bytes(canonical_bytes(descriptor) + b"\n")
            verified = load_verified_memory_context(runtime_root)
            self.assertEqual(len(verified), 2)
            self.assertEqual(
                [item.verbatim_text for item in verified],
                [
                    canonical_bytes(eligible_snapshot.to_dict()).decode(),
                    canonical_bytes(future_snapshot.to_dict()).decode(),
                ],
            )
            self.assertEqual(
                [item.source_sha256 for item in verified],
                [eligible_ref.sha256, future_ref.sha256],
            )
            self.assertEqual(
                [item.source_cycle_id for item in verified],
                ["prior-eligible", "prior-future"],
            )
            self.assertTrue(
                all(
                    item.contract_identity == "OKX:BTC-USDT-SWAP:SWAP"
                    and item.availability_basis == "SEALED_AT"
                    for item in verified
                )
            )

            filtered = snapshot_bound_memory_context(
                _snapshot(cycle_id="current-cycle"), verified
            )
            self.assertEqual(filtered["typed_unknown"], "MEMORY_CONTEXT_PARTIAL")
            self.assertIn("verbatim_text", filtered["items"][0])
            self.assertNotIn("verbatim_text", filtered["items"][1])
            self.assertEqual(
                filtered["items"][1]["typed_unknown"],
                "MEMORY_SOURCE_AFTER_SNAPSHOT_CUTOFF",
            )

            other_descriptor = {
                **descriptor,
                "items": [
                    {
                        "kind": "RECENT_FULL_DAILY",
                        "source_run_id": source_run_id,
                        "source_cycle_id": "prior-other-instrument",
                        "source_ref": other_ref.to_dict(),
                    }
                ],
            }
            descriptor_path.write_bytes(canonical_bytes(other_descriptor) + b"\n")
            other_verified = load_verified_memory_context(runtime_root)
            other_filtered = snapshot_bound_memory_context(
                _snapshot(cycle_id="current-cycle"), other_verified
            )
            self.assertEqual(
                other_filtered["typed_unknown"],
                "MEMORY_CONTEXT_NO_ELIGIBLE_ITEMS",
            )
            self.assertNotIn("verbatim_text", other_filtered["items"][0])
            self.assertEqual(
                other_filtered["items"][0]["typed_unknown"],
                "MEMORY_SOURCE_INSTRUMENT_MISMATCH",
            )

            (base / "other-run").mkdir()
            for unsafe_source_run_id in (
                str(runtime_root),
                "../run-memory",
                "other-run",
            ):
                with self.subTest(source_run_id=unsafe_source_run_id):
                    unsafe = {
                        **descriptor,
                        "items": [
                            {
                                **descriptors[0],
                                "source_run_id": unsafe_source_run_id,
                            }
                        ],
                    }
                    descriptor_path.write_bytes(
                        canonical_bytes(unsafe) + b"\n"
                    )
                    rejected_source = load_verified_memory_context(runtime_root)
                    self.assertEqual(rejected_source, ())
                    rejected_context = verified_memory_context(rejected_source)
                    self.assertEqual(rejected_context["status"], "UNKNOWN")
                    self.assertEqual(rejected_context["items"], [])
                    self.assertNotIn("verbatim_text", repr(rejected_context))

            corrupt = dict(descriptor)
            corrupt["items"] = [dict(item) for item in descriptors]
            corrupt["items"][1]["source_ref"] = dict(
                corrupt["items"][1]["source_ref"]
            )
            corrupt["items"][1]["source_ref"]["sha256"] = "0" * 64
            descriptor_path.write_bytes(canonical_bytes(corrupt) + b"\n")
            rejected_group = load_verified_memory_context(runtime_root)
            self.assertEqual(rejected_group, ())
            self.assertEqual(
                verified_memory_context(rejected_group)["typed_unknown"],
                "MEMORY_CONTEXT_NOT_PROVIDED",
            )


class FileCycleRepositoryTests(unittest.TestCase):
    def test_missing_status_and_reads_do_not_create_repository_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)

            self.assertIsNone(repository.status("missing-cycle"))
            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "STATE_HEAD_MISSING"
            ):
                repository.load_state("missing-cycle")
            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "REQUEST_MISSING"
            ):
                repository.load_request("missing-cycle")
            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "STATE_HEAD_MISSING"
            ):
                repository.load_artifact("missing-cycle", "InputSnapshot")
            self.assertFalse(root.exists())

    def test_create_freezes_request_and_revision_zero_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            request = _request()

            first = repository.create(request)
            second = repository.create(request)

            self.assertEqual(first, second)
            self.assertEqual(first.stage, "REQUESTED")
            self.assertEqual(first.revision, 0)
            self.assertEqual(repository.load_request(request.cycle_id), request)
            request_raw = (root / request.cycle_id / "request.json").read_bytes()
            self.assertEqual(request_raw, canonical_bytes(request.to_dict()))
            head = root / request.cycle_id / "state" / "head.json"
            history = (
                root
                / request.cycle_id
                / "state"
                / "history"
                / "00000000.json"
            )
            self.assertEqual(head.read_bytes(), history.read_bytes())

    def test_create_is_invisible_before_publish_and_new_request_can_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            request = _request()
            cycle_root = root / request.cycle_id

            def crash_before_publish(staging: Path, target: Path) -> None:
                self.assertEqual(target, cycle_root)
                self.assertFalse(target.exists())
                self.assertEqual(
                    (staging / "state/history/00000000.json").read_bytes(),
                    (staging / "state/head.json").read_bytes(),
                )
                self.assertEqual(
                    (staging / "request.json").read_bytes(),
                    canonical_bytes(request.to_dict()),
                )
                raise RuntimeError("simulated crash before cycle publication")

            with mock.patch(
                "trade_system.theory_paper_v2.infrastructure.market_cycle."
                "repository._publish_cycle_directory",
                side_effect=crash_before_publish,
            ), mock.patch(
                "trade_system.theory_paper_v2.infrastructure.market_cycle."
                "repository._discard_staging_directory",
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    repository.create(request)

            self.assertFalse(cycle_root.exists())
            self.assertEqual(
                len(list(root.glob(f".create-{request.cycle_id}.*.tmp"))),
                1,
            )
            replacement = _request(requested_at="2026-08-11T00:00:01+00:00")
            created = repository.create(replacement)
            self.assertEqual(created.stage, "REQUESTED")
            self.assertEqual(repository.load_request(request.cycle_id), replacement)

    def test_published_cycle_rejects_a_different_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            request = _request()
            initial = repository.create(request)

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "CREATE_REQUEST_CONFLICT"
            ):
                repository.create(
                    _request(requested_at="2026-08-11T00:00:01+00:00")
                )

            self.assertEqual(repository.load_request(request.cycle_id), request)
            self.assertEqual(repository.load_state(request.cycle_id), initial)

    def test_transition_writes_one_canonical_artifact_ref_and_cas_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())
            snapshot = _snapshot()

            current = repository.transition(
                expected=initial,
                artifacts=(snapshot,),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )

            self.assertEqual(current.revision, 1)
            self.assertEqual(len(current.artifact_refs), 1)
            reference = current.artifact_refs[0]
            self.assertEqual(reference.artifact_type, "InputSnapshot")
            self.assertEqual(reference.artifact_id, snapshot.snapshot_id)
            self.assertEqual(reference.path, "artifacts/InputSnapshot.json")
            artifact_raw = (root / current.cycle_id / reference.path).read_bytes()
            self.assertEqual(artifact_raw, canonical_bytes(snapshot.to_dict()))
            self.assertEqual(reference.size_bytes, len(artifact_raw))
            self.assertEqual(reference.sha256, hashlib.sha256(artifact_raw).hexdigest())
            self.assertEqual(
                repository.load_artifact(current.cycle_id, "InputSnapshot"),
                snapshot.to_dict(),
            )
            self.assertEqual(repository.load_state(current.cycle_id), current)
            self.assertEqual(
                (
                    root
                    / current.cycle_id
                    / "state"
                    / "history"
                    / "00000001.json"
                ).read_bytes(),
                (root / current.cycle_id / "state" / "head.json").read_bytes(),
            )
            intent_raw = (
                root
                / current.cycle_id
                / "state"
                / "intents"
                / "00000001.json"
            ).read_bytes()
            intent = loads_json_strict(intent_raw)
            self.assertEqual(canonical_bytes(intent), intent_raw)
            self.assertEqual(intent["current_state"], current.to_dict())
            self.assertEqual(
                intent["current_state_sha256"],
                hashlib.sha256(canonical_bytes(current.to_dict())).hexdigest(),
            )
            self.assertEqual(
                intent["expected_head"]["sha256"],
                hashlib.sha256(canonical_bytes(initial.to_dict())).hexdigest(),
            )
            self.assertEqual(intent["artifacts"][0]["ref"], reference.to_dict())
            self.assertEqual(intent["artifacts"][0]["payload"], snapshot.to_dict())

    def test_transition_rejects_missing_nested_input_raw_capture_before_intent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            raw_store = FileRawCaptureStore(runtime_root)
            repository = FileCycleRepository(
                runtime_root / "cycles",
                raw_capture_verifier=raw_store,
            )
            initial = repository.create(_request())
            missing_payload = b"missing-input-response"
            snapshot = _snapshot(
                raw_ref=_raw_reference(
                    capture_id="input-missing-001",
                    payload=missing_payload,
                )
            )

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "RAW_CAPTURE_MISSING"
            ):
                repository.transition(
                    expected=initial,
                    artifacts=(snapshot,),
                    next_stage="INPUT_SEALED",
                    next_action="ANALYZE",
                )

            cycle_root = runtime_root / "cycles" / initial.cycle_id
            self.assertFalse((cycle_root / "artifacts/InputSnapshot.json").exists())
            self.assertFalse((cycle_root / "state/intents/00000001.json").exists())
            self.assertEqual(repository.load_state(initial.cycle_id), initial)

    def test_recovery_rejects_pending_snapshot_when_nested_raw_capture_is_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            raw_store = FileRawCaptureStore(runtime_root)
            repository = FileCycleRepository(
                runtime_root / "cycles",
                raw_capture_verifier=raw_store,
            )
            initial = repository.create(_request())
            capture_id = "input-recovery-001"
            raw_ref = _seal_raw_reference(
                raw_store,
                capture_id=capture_id,
                payload=b"sealed-recovery-response",
            )

            with mock.patch.object(
                FileCycleRepository,
                "_apply_transition_intent",
                side_effect=RuntimeError("simulated crash after intent fsync"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    repository.transition(
                        expected=initial,
                        artifacts=(_snapshot(raw_ref=raw_ref),),
                        next_stage="INPUT_SEALED",
                        next_action="ANALYZE",
                    )

            cycle_root = runtime_root / "cycles" / initial.cycle_id
            shutil.rmtree(cycle_root / "raw" / capture_id)
            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "RAW_CAPTURE_MISSING"
            ):
                repository.recover_pending(initial.cycle_id)

            self.assertFalse((cycle_root / "artifacts/InputSnapshot.json").exists())
            self.assertFalse((cycle_root / "state/history/00000001.json").exists())
            self.assertEqual(
                (cycle_root / "state/head.json").read_bytes(),
                canonical_bytes(initial.to_dict()),
            )

    def test_corrupt_nested_input_raw_capture_blocks_load_and_continuation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            raw_store = FileRawCaptureStore(runtime_root)
            repository = FileCycleRepository(
                runtime_root / "cycles",
                raw_capture_verifier=raw_store,
            )
            initial = repository.create(_request())
            raw_ref = _seal_raw_reference(
                raw_store,
                capture_id="input-core-001",
                payload=b"sealed-input-response",
            )
            current = repository.transition(
                expected=initial,
                artifacts=(_snapshot(raw_ref=raw_ref),),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            cycle_root = runtime_root / "cycles" / current.cycle_id
            raw_body = cycle_root / raw_ref.path
            raw_body.write_bytes(b"corrupt-input-response")

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "RAW_CAPTURE_INVALID"
            ):
                repository.load_state(current.cycle_id)
            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "RAW_CAPTURE_INVALID"
            ):
                repository.transition(
                    expected=current,
                    artifacts=(_hypothesis_record(current.artifact_refs[-1]),),
                    next_stage="ANALYZED",
                    next_action="COPY_AGENT_DECISION_TO_PLAN",
                )

            self.assertFalse((cycle_root / "artifacts/HypothesisRecord.json").exists())
            self.assertFalse((cycle_root / "state/intents/00000002.json").exists())
            self.assertEqual(
                (cycle_root / "state/head.json").read_bytes(),
                canonical_bytes(current.to_dict()),
            )

    def test_transition_rejects_missing_nested_observed_outcome_raw_capture(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            raw_store = FileRawCaptureStore(runtime_root)
            repository = FileCycleRepository(
                runtime_root / "cycles",
                raw_capture_verifier=raw_store,
            )
            state = repository.create(_request())
            input_ref = _seal_raw_reference(
                raw_store,
                capture_id="input-core-001",
                payload=b"sealed-input-response",
            )
            state = repository.transition(
                expected=state,
                artifacts=(_snapshot(raw_ref=input_ref),),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            hypotheses = _hypothesis_record(state.artifact_refs[-1])
            state = repository.transition(
                expected=state,
                artifacts=(hypotheses,),
                next_stage="ANALYZED",
                next_action="COPY_AGENT_DECISION_TO_PLAN",
            )
            plan = _behavior_plan(state.artifact_refs[-1])
            state = repository.transition(
                expected=state,
                artifacts=(plan,),
                next_stage="PLAN_SEALED",
                next_action="WAIT_FOR_OUTCOME",
            )
            state = repository.transition(
                expected=state,
                artifacts=(),
                next_stage="OUTCOME_DUE",
                next_action="CAPTURE_OUTCOME",
            )
            missing_payload = b"missing-outcome-response"
            missing_ref = _raw_reference(
                capture_id="outcome-missing-001",
                payload=missing_payload,
            )

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "RAW_CAPTURE_MISSING"
            ):
                repository.transition(
                    expected=state,
                    artifacts=(
                        _observed_outcome(state.artifact_refs[-1], missing_ref),
                    ),
                    next_stage="OUTCOME_SEALED",
                    next_action="REVIEW",
                )

            cycle_root = runtime_root / "cycles" / state.cycle_id
            self.assertFalse((cycle_root / "artifacts/Outcome.json").exists())
            self.assertFalse((cycle_root / "state/intents/00000005.json").exists())
            self.assertEqual(repository.load_state(state.cycle_id), state)

    def test_status_and_load_do_not_apply_a_durable_pending_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())
            cycle_root = root / initial.cycle_id
            intent_path = cycle_root / "state/intents/00000001.json"
            artifact_path = cycle_root / "artifacts/InputSnapshot.json"
            history_path = cycle_root / "state/history/00000001.json"

            with mock.patch.object(
                FileCycleRepository,
                "_apply_transition_intent",
                side_effect=RuntimeError("simulated crash after intent fsync"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    repository.transition(
                        expected=initial,
                        artifacts=(_snapshot(),),
                        next_stage="INPUT_SEALED",
                        next_action="ANALYZE",
                    )

            intent_before = intent_path.read_bytes()
            self.assertFalse(artifact_path.exists())
            self.assertFalse(history_path.exists())
            self.assertEqual(repository.status(initial.cycle_id), initial)
            self.assertEqual(repository.load_state(initial.cycle_id), initial)
            self.assertFalse(artifact_path.exists())
            self.assertFalse(history_path.exists())

            recovered = repository.recover_pending(initial.cycle_id)

            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered.stage, "INPUT_SEALED")
            self.assertEqual(recovered.revision, 1)
            self.assertEqual(intent_path.read_bytes(), intent_before)
            self.assertTrue(artifact_path.is_file())
            self.assertEqual(
                history_path.read_bytes(), canonical_bytes(recovered.to_dict())
            )
            self.assertEqual(repository.load_state(initial.cycle_id), recovered)
            self.assertIsNone(repository.recover_pending(initial.cycle_id))

    def test_recovery_finishes_artifact_and_history_left_before_head_cas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())
            cycle_root = root / initial.cycle_id
            artifact_path = cycle_root / "artifacts/InputSnapshot.json"
            history_path = cycle_root / "state/history/00000001.json"
            head_path = cycle_root / "state/head.json"

            with mock.patch(
                "trade_system.theory_paper_v2.infrastructure.market_cycle."
                "repository._atomic_compare_and_replace",
                side_effect=RuntimeError("simulated crash before head CAS"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    repository.transition(
                        expected=initial,
                        artifacts=(_snapshot(),),
                        next_stage="INPUT_SEALED",
                        next_action="ANALYZE",
                    )

            self.assertTrue(artifact_path.is_file())
            history_before = history_path.read_bytes()
            self.assertEqual(head_path.read_bytes(), canonical_bytes(initial.to_dict()))

            recovered = repository.recover_pending(initial.cycle_id)

            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(history_path.read_bytes(), history_before)
            self.assertEqual(head_path.read_bytes(), history_before)
            self.assertEqual(repository.load_state(initial.cycle_id), recovered)

    def test_stale_expected_state_cannot_overwrite_artifact_or_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())
            snapshot = _snapshot()
            current = repository.transition(
                expected=initial,
                artifacts=(snapshot,),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            artifact_path = root / current.cycle_id / "artifacts/InputSnapshot.json"
            head_path = root / current.cycle_id / "state/head.json"
            artifact_before = artifact_path.read_bytes()
            head_before = head_path.read_bytes()

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "STATE_CAS_CONFLICT"
            ):
                repository.transition(
                    expected=initial,
                    artifacts=(
                        _snapshot(snapshot_id="snapshot-conflicting-002"),
                    ),
                    next_stage="INPUT_SEALED",
                    next_action="ANALYZE",
                )

            self.assertEqual(artifact_path.read_bytes(), artifact_before)
            self.assertEqual(head_path.read_bytes(), head_before)

    def test_different_bytes_cannot_replace_an_interrupted_create_only_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())
            artifact_path = root / initial.cycle_id / "artifacts/InputSnapshot.json"
            artifact_path.parent.mkdir()
            original = canonical_bytes(_snapshot().to_dict())
            artifact_path.write_bytes(original)
            head_path = root / initial.cycle_id / "state/head.json"
            head_before = head_path.read_bytes()

            with self.assertRaisesRegex(
                MarketCycleRepositoryError, "WRITE_ONCE_CONFLICT"
            ):
                repository.transition(
                    expected=initial,
                    artifacts=(
                        _snapshot(snapshot_id="snapshot-conflicting-002"),
                    ),
                    next_stage="INPUT_SEALED",
                    next_action="ANALYZE",
                )

            self.assertEqual(artifact_path.read_bytes(), original)
            self.assertEqual(head_path.read_bytes(), head_before)
            resumed = repository.transition(
                expected=initial,
                artifacts=(_snapshot(),),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            self.assertEqual(
                resumed.artifact_refs[0].sha256,
                hashlib.sha256(original).hexdigest(),
            )

    def test_illegal_transition_is_rejected_before_any_artifact_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            initial = repository.create(_request())

            with self.assertRaises(ValueError):
                repository.transition(
                    expected=initial,
                    artifacts=(_snapshot(),),
                    next_stage="ANALYZED",
                    next_action="COPY_AGENT_DECISION_TO_PLAN",
                )

            self.assertFalse(
                (root / initial.cycle_id / "artifacts/InputSnapshot.json").exists()
            )
            self.assertFalse(
                (
                    root
                    / initial.cycle_id
                    / "state"
                    / "history"
                    / "00000001.json"
                ).exists()
            )
            self.assertFalse(
                (
                    root
                    / initial.cycle_id
                    / "state"
                    / "intents"
                    / "00000001.json"
                ).exists()
            )
            self.assertEqual(repository.load_state(initial.cycle_id), initial)

    def test_cycle_lock_is_reentrant_and_excludes_a_second_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = FileCycleRepository(Path(temporary) / "runtime")
            first_acquired = threading.Event()
            second_attempted = threading.Event()
            second_acquired = threading.Event()
            release_first = threading.Event()

            def hold_first() -> None:
                with repository.locked("cycle-lock-001"):
                    with repository.locked("cycle-lock-001"):
                        first_acquired.set()
                        release_first.wait(timeout=5)

            def acquire_second() -> None:
                first_acquired.wait(timeout=5)
                second_attempted.set()
                with repository.locked("cycle-lock-001"):
                    second_acquired.set()

            first_thread = threading.Thread(target=hold_first)
            second_thread = threading.Thread(target=acquire_second)
            first_thread.start()
            second_thread.start()
            self.assertTrue(first_acquired.wait(timeout=5))
            self.assertTrue(second_attempted.wait(timeout=5))
            self.assertFalse(second_acquired.is_set())
            release_first.set()
            first_thread.join(timeout=5)
            second_thread.join(timeout=5)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertTrue(second_acquired.is_set())

    def test_all_five_business_artifacts_use_one_create_only_path_each(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            repository = FileCycleRepository(root)
            state = repository.create(_request())

            snapshot = _snapshot()
            state = repository.transition(
                expected=state,
                artifacts=(snapshot,),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            hypothesis_record = _hypothesis_record(state.artifact_refs[-1])
            with self.assertRaisesRegex(
                RuntimeError,
                "MARKET_CYCLE_HYPOTHESIS_SNAPSHOT_CONTENT_MISMATCH",
            ):
                repository.transition(
                    expected=state,
                    artifacts=(
                        replace(
                            hypothesis_record,
                            unresolved_unknowns=(AGENT_OUTPUT_INCOMPLETE,),
                        ),
                    ),
                    next_stage="ANALYZED",
                    next_action="COPY_AGENT_DECISION_TO_PLAN",
                )
            state = repository.transition(
                expected=state,
                artifacts=(hypothesis_record,),
                next_stage="ANALYZED",
                next_action="COPY_AGENT_DECISION_TO_PLAN",
            )
            plan = _behavior_plan(state.artifact_refs[-1])
            changed_text = "System must not rewrite this Agent decision.\n"
            changed_raw = changed_text.encode("utf-8")
            with self.assertRaisesRegex(
                RuntimeError,
                "MARKET_CYCLE_PLAN_AGENT_DECISION_CONTENT_MISMATCH",
            ):
                repository.transition(
                    expected=state,
                    artifacts=(
                        replace(
                            plan,
                            agent_decision_text=changed_text,
                            agent_decision_size_bytes=len(changed_raw),
                            agent_decision_sha256=hashlib.sha256(
                                changed_raw
                            ).hexdigest(),
                        ),
                    ),
                    next_stage="PLAN_SEALED",
                    next_action="WAIT_FOR_OUTCOME",
                )
            state = repository.transition(
                expected=state,
                artifacts=(plan,),
                next_stage="PLAN_SEALED",
                next_action="WAIT_FOR_OUTCOME",
            )
            state = repository.transition(
                expected=state,
                artifacts=(),
                next_stage="OUTCOME_DUE",
                next_action="CAPTURE_OUTCOME",
            )
            outcome = _typed_missing_outcome(state.artifact_refs[-1])
            with self.assertRaisesRegex(
                RuntimeError,
                "MARKET_CYCLE_OUTCOME_PLAN_CONTENT_MISMATCH",
            ):
                repository.transition(
                    expected=state,
                    artifacts=(replace(outcome, tolerance_seconds=61),),
                    next_stage="OUTCOME_SEALED",
                    next_action="REVIEW",
                )
            state = repository.transition(
                expected=state,
                artifacts=(outcome,),
                next_stage="OUTCOME_SEALED",
                next_action="REVIEW",
            )
            review = _review(state.artifact_refs[2], state.artifact_refs[-1])
            drifted_facts = dict(review.system_facts)
            drifted_facts["typed_missing"] = "DIFFERENT_MISSING_REASON"
            with self.assertRaisesRegex(
                RuntimeError,
                "MARKET_CYCLE_REVIEW_SOURCE_CONTENT_MISMATCH",
            ):
                repository.transition(
                    expected=state,
                    artifacts=(replace(review, system_facts=drifted_facts),),
                    next_stage="REVIEWED",
                    next_action="COMPLETE",
                )
            state = repository.transition(
                expected=state,
                artifacts=(review,),
                next_stage="REVIEWED",
                next_action="COMPLETE",
            )
            state = repository.transition(
                expected=state,
                artifacts=(),
                next_stage="COMPLETE",
                next_action=None,
                terminal=True,
            )

            self.assertTrue(state.terminal)
            self.assertEqual(
                tuple(reference.artifact_type for reference in state.artifact_refs),
                (
                    "InputSnapshot",
                    "HypothesisRecord",
                    "BehaviorPlan",
                    "Outcome",
                    "Review",
                ),
            )
            for reference in state.artifact_refs:
                self.assertEqual(
                    reference.path,
                    f"artifacts/{reference.artifact_type}.json",
                )
                self.assertEqual(
                    len(list((root / state.cycle_id / "artifacts").glob(
                        f"{reference.artifact_type}.json"
                    ))),
                    1,
                )
                repository.load_artifact(state.cycle_id, reference.artifact_type)


if __name__ == "__main__":
    unittest.main()
