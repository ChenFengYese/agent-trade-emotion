from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v332_hype_data import _json, _seal, _seal_core
from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.attention import (
    AttentionService,
)
from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingError,
    PaperTradingService,
)
from trade_system.theory_paper_v2.application.market_cycle.ports import (
    OutcomeObservation,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import CycleRequest
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PaperCommandV1,
    PaperCostModelV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_authority import (
    SealedCyclePaperDecisionAuthority,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.projections import (
    WorkbenchProjectionService,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    RUN_MANIFEST_RELATIVE_PATH,
    RUN_MANIFEST_SCHEMA_ID,
    RUN_MANIFEST_SCHEMA_VERSION,
    V332_RUNTIME_CONTRACT_IDENTITY,
    FrozenRunManifest,
    V332GoalRegistryGate,
    build_market_cycle_runtime,
    current_implementation_identity,
    initialize_run_identity_seal,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    ORDER_BOOK_PATH,
)
from trade_system.theory_paper_v2.infrastructure.market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from trade_system.theory_paper_v2.presentation.market_workbench import (
    load_hype_data_slices,
)


_ROOT = Path(__file__).resolve().parents[1]
_V332_PACKAGE = _ROOT / "theory" / "versions" / "v3.3.2"
_DECISION_BYTES = (
    b"ACTION=LONG_REFERENCE\n"
    b"POSITION=paper-only 2 contracts; protective actions remain Agent-owned.\n"
)
_DECISION_SHA = hashlib.sha256(_DECISION_BYTES).hexdigest()
_REVIEW_BYTES = (
    b"V3.3.2 review: keep the original hypothesis conditional and retain "
    b"unobserved path facts as UNKNOWN.\n"
)
_V332_THEORY_FILES = (
    "README.md",
    "00_USER_DIRECTED_EXPERIMENTAL_SCOPE.md",
    "01_MARKET_COGNITION.md",
    "02_DYNAMIC_POSITION_MANAGEMENT.md",
    "03_HYPOTHESIS_SYSTEM.md",
    "04_EXECUTION_AND_AGENT.md",
    "05_RISK_AND_BOUNDARIES.md",
    "08_SANDISK_USDT_TEACHING_CASE.md",
    "09_STATE_TRANSITION_AND_EVALUATION.md",
)
_GOAL_THREAD_ID = "019ff5a3-529a-77d2-a3e4-595710406637"
_GOAL_PHYSICAL_ID = f"codex-thread:{_GOAL_THREAD_ID}"


class _FixedRuntimeClock:
    def __init__(self) -> None:
        self.current = "2026-08-13T12:00:15+00:00"

    def __call__(self) -> str:
        return self.current

    def monotonic_ns(self) -> int:
        return 1


class _TypedMissingOutcome:
    def observe(self, request: object) -> OutcomeObservation:
        due_at = getattr(request, "due_at")
        return OutcomeObservation(
            observed_at=due_at,
            effective_at=None,
            available_at=None,
            terminal_status="MISSING",
            value=None,
            unit=None,
            missing_reason="UNKNOWN_OFFLINE_REVIEW_FIXTURE",
            raw_ref=None,
            source_health=(),
        )


def _deliver_goal_result(
    runtime: object,
    cycle_id: str,
    worker_id: str,
    body: bytes,
) -> None:
    with mock.patch.dict(
        os.environ, {"CODEX_THREAD_ID": _GOAL_THREAD_ID}, clear=False
    ):
        if worker_id == "review-v1":
            result = runtime.service.deliver_agent_review(cycle_id, body)
            output_name = "agent-review-delivery.json"
            text_field = "review_text"
        else:
            result = runtime.service.deliver_agent_decision(cycle_id, body)
            output_name = "agent-delivery.json"
            text_field = "decision_text"
    if result != "CREATED":
        raise AssertionError(f"unexpected Agent delivery result: {result}")
    delivery_path = (
        runtime.runtime_root
        / "cycles"
        / cycle_id
        / "transport"
        / output_name
    )
    delivery = loads_json_strict(delivery_path.read_bytes())
    if body.decode("utf-8") != delivery[text_field]:
        raise AssertionError("admitted Goal body changed during delivery")


def _deliver_and_complete_decision(runtime: object, cycle_id: str) -> None:
    _deliver_goal_result(
        runtime, cycle_id, "decision-v1", _DECISION_BYTES
    )


def _deliver_and_complete_review(runtime: object, cycle_id: str) -> None:
    _deliver_goal_result(
        runtime, cycle_id, "review-v1", _REVIEW_BYTES
    )


def _seal_execution_book(store: FileRawCaptureStore, *, cycle_id: str) -> None:
    _seal_core(store, cycle_id=cycle_id)
    _seal(
        store,
        cycle_id=cycle_id,
        capture_id="order-book",
        component_id="ORDER_BOOK",
        path=ORDER_BOOK_PATH,
        query={"instId": "HYPE-USDT-SWAP", "sz": "20"},
        body=_json(
            {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "asks": [["43.13", "10", "0", "1"]],
                        "bids": [["43.12", "8", "0", "1"]],
                        "ts": "1786622465000",
                        "seqId": "101",
                        "prevSeqId": "100",
                    }
                ],
            }
        ),
        start_offset=65,
    )


def _build_offline_runtime(runtime_root: Path) -> tuple[object, FileRawCaptureStore, _FixedRuntimeClock]:
    runtime_root.mkdir()
    raw_store = FileRawCaptureStore(runtime_root)
    manifest_document = {
        "schema_id": RUN_MANIFEST_SCHEMA_ID,
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": runtime_root.name,
        "theory_manifest_sha256": V332_THEORY_IDENTITY.manifest_digest,
        "implementation_sha256": current_implementation_identity(),
        "contract_identity": V332_RUNTIME_CONTRACT_IDENTITY,
        "market_contract_identity": HYPE_OKX_CONTRACT_IDENTITY,
        "experiment_identity": "V332_OFFLINE_SYSTEM_FEASIBILITY",
        "status": "OPEN",
    }
    manifest_raw = canonical_bytes(manifest_document) + b"\n"
    manifest_path = runtime_root / RUN_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(manifest_raw)
    initialize_run_identity_seal(
        runtime_root,
        FrozenRunManifest(
            run_id=runtime_root.name,
            theory_manifest_sha256=V332_THEORY_IDENTITY.manifest_digest,
            implementation_sha256=manifest_document["implementation_sha256"],
            contract_identity=V332_RUNTIME_CONTRACT_IDENTITY,
            market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
            experiment_identity=manifest_document["experiment_identity"],
            status="OPEN",
            raw_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        ),
    )
    clock = _FixedRuntimeClock()
    runtime = build_market_cycle_runtime(
        runtime_root=runtime_root,
        theory_package=_V332_PACKAGE,
        expected_theory_identity=V332_THEORY_IDENTITY,
        clock=clock,
    )
    goal_repository = FileAttentionRepository(runtime_root / "attention")
    AgentSessionService(goal_repository).register(
        AgentRegistry(
            logical_agent_id="offline-hype-paper-goal",
            symbol="HYPE-USDT-SWAP",
            generation=1,
            continuity_nonce="offline-hype-paper-goal-g1",
            physical_task_id=_GOAL_PHYSICAL_ID,
            status="ACTIVE",
            registered_at=clock.current,
        )
    )
    runtime.service._goal_registry_gate = V332GoalRegistryGate(
        runtime_root,
        paper_account_policy={
            "logical_agent_id": "offline-hype-paper-goal",
            "agent_generation": 1,
        },
    )
    return runtime, raw_store, clock


def _v332_request(cycle_id: str) -> CycleRequest:
    return CycleRequest(
        request_id=f"{cycle_id}.request",
        cycle_id=cycle_id,
        requested_at="2026-08-13T12:00:00+00:00",
        venue_id="OKX",
        instrument_id="HYPE-USDT-SWAP",
        contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        analysis_profile="COLD",
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        outcome_horizon_seconds=900,
        outcome_tolerance_seconds=30,
        lawful_actions=(
            "LONG_REFERENCE",
            "SHORT_REFERENCE",
            "WAIT",
            "OTHER_INFORMATION_ACTION",
        ),
        theory_identity=V332_THEORY_IDENTITY,
    )


class V332OfflineEndToEndTests(unittest.TestCase):
    def test_v332_outcome_review_keeps_nine_document_theory_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "v332-review-regression"
            runtime, raw_store, clock = _build_offline_runtime(runtime_root)
            cycle_id = "v332-nine-document-review"
            runtime.service.create(_v332_request(cycle_id))
            _seal_core(raw_store, cycle_id=cycle_id)
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "INPUT_SEALED"
            )
            pending_decision = runtime.service.run_next(cycle_id)
            self.assertFalse(pending_decision.changed)
            self.assertEqual(
                pending_decision.pending_reason, "AGENT_DELIVERY_PENDING"
            )
            _deliver_and_complete_decision(runtime, cycle_id)
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "ANALYZED"
            )
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "PLAN_SEALED"
            )

            plan = runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
            runtime.service._service._outcome = _TypedMissingOutcome()
            clock.current = plan["outcome_due_at"]
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "OUTCOME_DUE"
            )
            outcome_sealed = runtime.service.run_next(cycle_id)
            self.assertEqual(
                outcome_sealed.state.stage,
                "OUTCOME_SEALED",
                outcome_sealed.state.failure_reason,
            )
            pending_review = runtime.service.run_next(cycle_id)
            self.assertFalse(pending_review.changed)
            self.assertEqual(
                pending_review.pending_reason, "AGENT_REVIEW_DELIVERY_PENDING"
            )
            review_request = loads_json_strict(
                (
                    runtime_root
                    / "cycles"
                    / cycle_id
                    / "transport"
                    / "agent-review-request.json"
                ).read_bytes()
            )
            fragments = review_request["packet"]["theory_fragments"]
            self.assertEqual(frozenset(fragments), frozenset(_V332_THEORY_FILES))
            self.assertEqual(len(fragments), 9)
            self.assertEqual(
                review_request["packet"]["theory_identity"],
                V332_THEORY_IDENTITY.to_dict(),
            )

            _deliver_and_complete_review(runtime, cycle_id)
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "REVIEWED"
            )
            self.assertEqual(
                runtime.service.run_next(cycle_id).state.stage, "COMPLETE"
            )
            review = runtime.repository.load_artifact(cycle_id, "Review")
            self.assertEqual(
                review["agent_review_sha256"],
                hashlib.sha256(_REVIEW_BYTES).hexdigest(),
            )
            self.assertEqual(
                review["theory_identity"], V332_THEORY_IDENTITY.to_dict()
            )

    def test_hype_data_two_agents_admission_gated_accounts_and_workbench_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "v332-offline-runtime"
            runtime, raw_store, _ = _build_offline_runtime(runtime_root)
            cycle_id = "v332-offline-hype-cycle"
            profile_service = build_hype_data_profile_service(raw_store=raw_store)
            runtime.service.create(_v332_request(cycle_id))
            _seal_core(raw_store, cycle_id=cycle_id)
            input_result = runtime.service.run_next(cycle_id)
            self.assertEqual(input_result.state.stage, "INPUT_SEALED")
            snapshot = runtime.repository.load_artifact(cycle_id, "InputSnapshot")
            data_slice = profile_service.replay(
                HYPE_OKX_DATA_PROFILE.profile_id,
                cycle_id=cycle_id,
            ).data_slice
            self.assertIsNotNone(data_slice)
            self.assertEqual(snapshot["theory_identity"], V332_THEORY_IDENTITY.to_dict())
            self.assertEqual(snapshot["instrument_id"], "HYPE-USDT-SWAP")
            pending = runtime.service.run_next(cycle_id)
            self.assertFalse(pending.changed)
            self.assertEqual(pending.pending_reason, "AGENT_DELIVERY_PENDING")
            self.assertTrue(
                (runtime_root / "cycles" / cycle_id / "transport" / "agent-request.json").is_file()
            )
            _deliver_and_complete_decision(runtime, cycle_id)
            analyzed = runtime.service.run_next(cycle_id)
            self.assertEqual(analyzed.state.stage, "ANALYZED")
            plan_sealed = runtime.service.run_next(cycle_id)
            self.assertEqual(plan_sealed.state.stage, "PLAN_SEALED")
            hypothesis = runtime.repository.load_artifact(cycle_id, "HypothesisRecord")
            self.assertEqual(hypothesis["agent_decision_sha256"], _DECISION_SHA)

            execution_cycle_id = "v332-offline-hype-execution-slice"
            _seal_execution_book(raw_store, cycle_id=execution_cycle_id)

            attention_repository = FileAttentionRepository(root / "attention")
            sessions = AgentSessionService(attention_repository)
            attention = AttentionService(attention_repository)
            for logical_agent_id, symbol in (
                ("HYPE_TRADER", "HYPE-USDT-SWAP"),
                ("SNDK_TRADER", "SNDK-USDT-SWAP"),
            ):
                sessions.register(
                    AgentRegistry(
                        logical_agent_id=logical_agent_id,
                        symbol=symbol,
                        generation=1,
                        continuity_nonce=f"ctx-{logical_agent_id.casefold()}-g1",
                        physical_task_id=f"task-{logical_agent_id.casefold()}-g1",
                        status="ACTIVE",
                        registered_at="2026-08-13T12:00:00+00:00",
                    )
                )
                attention.submit_request(
                    AttentionRequest(
                        request_id=f"wake-{logical_agent_id.casefold()}-001",
                        logical_agent_id=logical_agent_id,
                        agent_generation=1,
                        continuity_nonce=f"ctx-{logical_agent_id.casefold()}-g1",
                        symbol=symbol,
                        mode="WAKE_AFTER",
                        issued_at="2026-08-13T12:00:01+00:00",
                        continue_until=None,
                        earliest_wake_at="2026-08-13T12:05:00+00:00",
                        latest_useful_at="2026-08-13T12:10:00+00:00",
                        reason_summary="Agent selected a bounded re-check window.",
                        requested_focus="Re-check the Agent-owned path and risk boundary.",
                        hypothesis_or_episode_ref=(
                            cycle_id
                            if logical_agent_id == "HYPE_TRADER"
                            else "sndk-profile-not-admitted"
                        ),
                        position_and_open_order_ref=f"paper-{logical_agent_id.casefold()}",
                        data_cursor=(
                            data_slice.data_cursor
                            if logical_agent_id == "HYPE_TRADER" and data_slice is not None
                            else "sndk-data-not-admitted"
                        ),
                    )
                )

            paper_ledger = FilePaperLedger(root / "paper")
            cost_model = PaperCostModelV1(
                model_id="bounded-public-paper-v1",
                maker_fee_bps="2",
                taker_fee_bps="4",
                market_impact_bps="2",
                funding_status="UNKNOWN",
                borrow_status="UNKNOWN",
            )
            decision_authority = SealedCyclePaperDecisionAuthority(
                sessions=sessions,
                cycle_repository=runtime.repository,
                agent_cycle_bindings={"HYPE_TRADER": (cycle_id,)},
            )
            market_evidence = AdmittedAssetSlicePaperMarketEvidence(
                profiles=profile_service,
                bindings=(
                    PaperAssetEvidenceBinding(
                        symbol="HYPE-USDT-SWAP",
                        profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                        cycle_ids=(cycle_id, execution_cycle_id),
                    ),
                ),
            )
            paper = PaperTradingService(
                paper_ledger,
                cost_models=(cost_model,),
                decision_authority=decision_authority,
                market_evidence=market_evidence,
                carry_evidence=market_evidence,
            )
            hype_instrument_spec = market_evidence.latest_instrument_spec(
                "HYPE-USDT-SWAP",
                "LINEAR_PERP",
                available_by="2026-08-13T12:00:20+00:00",
            )
            self.assertIsNotNone(hype_instrument_spec)
            paper.open_account(
                account_id="hype-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="HYPE_TRADER",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="3",
                initial_balance="10000",
                opened_at="2026-08-13T12:00:20+00:00",
                instrument_spec=hype_instrument_spec,
            )
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_LINEAR_PERP_INSTRUMENT_SPEC_REQUIRED"
            ):
                paper.open_account(
                    account_id="sndk-paper",
                    account_mode="LINEAR_PERP",
                    owner_logical_agent_id="SNDK_TRADER",
                    base_currency="USDT",
                    permitted_symbol="SNDK-USDT-SWAP",
                    max_leverage="3",
                    initial_balance="10000",
                    opened_at="2026-08-13T12:00:20+00:00",
                )

            hype = paper.submit(
                PaperCommandV1(
                    command_id="hype-open-long",
                    account_id="hype-paper",
                    logical_agent_id="HYPE_TRADER",
                    agent_generation=1,
                    decision_cycle_id=cycle_id,
                    decision_sha256=_DECISION_SHA,
                    expected_account_version=1,
                    symbol="HYPE-USDT-SWAP",
                    command_type="MARKET",
                    side="BUY",
                    quantity="2",
                    limit_price=None,
                    trigger_price=None,
                    target_order_id=None,
                    reduce_only=False,
                    time_in_force="GTC",
                    submitted_at="2026-08-13T12:01:00+00:00",
                    expires_at=None,
                    cost_model_id=cost_model.model_id,
                )
            )
            execution_quote = market_evidence.latest_order_book_slice(
                "HYPE-USDT-SWAP"
            )
            self.assertIsNotNone(execution_quote)
            assert execution_quote is not None
            hype = paper.observe(
                account_id="hype-paper",
                expected_account_version=hype.version,
                market=execution_quote,
            )
            with self.assertRaisesRegex(
                PaperTradingError, "PAPER_ACCOUNT_NOT_FOUND"
            ):
                paper.submit(
                    PaperCommandV1(
                        command_id="sndk-limit-long-not-admitted",
                        account_id="sndk-paper",
                        logical_agent_id="SNDK_TRADER",
                        agent_generation=1,
                        decision_cycle_id="sndk-profile-not-admitted",
                        decision_sha256=_DECISION_SHA,
                        expected_account_version=1,
                        symbol="SNDK-USDT-SWAP",
                        command_type="LIMIT",
                        side="BUY",
                        quantity="1",
                        limit_price="100",
                        trigger_price=None,
                        target_order_id=None,
                        reduce_only=False,
                        time_in_force="GTC",
                        submitted_at="2026-08-13T12:01:00+00:00",
                        expires_at=None,
                        cost_model_id=cost_model.model_id,
                    )
            )
            self.assertEqual(hype.positions[0].symbol, "HYPE-USDT-SWAP")
            self.assertEqual(
                hype.instrument_spec.parameter_status, "OBSERVED_RAW_BOUND"
            )
            self.assertEqual(paper_ledger.load_records("sndk-paper"), ())

            projector = WorkbenchProjectionService(
                attention_repository=attention_repository,
                paper_ledger=paper_ledger,
                cycle_repository=runtime.repository,
                valuation_market_evidence=market_evidence,
            )
            first = projector.build(
                logical_agent_ids=("HYPE_TRADER", "SNDK_TRADER"),
                account_ids=("hype-paper",),
                data_slices=(data_slice,),
                cycle_ids=(cycle_id,),
            ).to_dict()
            restarted = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=FilePaperLedger(root / "paper"),
                cycle_repository=FileCycleRepository(
                    runtime_root / "cycles",
                    raw_capture_verifier=FileRawCaptureStore(runtime_root),
                ),
                valuation_market_evidence=AdmittedAssetSlicePaperMarketEvidence(
                    profiles=build_hype_data_profile_service(
                        raw_store=FileRawCaptureStore(runtime_root)
                    ),
                    bindings=(
                        PaperAssetEvidenceBinding(
                            symbol="HYPE-USDT-SWAP",
                            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                            cycle_ids=(cycle_id, execution_cycle_id),
                        ),
                    ),
                ),
            ).build(
                logical_agent_ids=("HYPE_TRADER", "SNDK_TRADER"),
                account_ids=("hype-paper",),
                data_slices=load_hype_data_slices(
                    runtime_root=runtime_root,
                    cycle_ids=(cycle_id,),
                ),
                cycle_ids=(cycle_id,),
            ).to_dict()
            self.assertEqual(first, restarted)
            self.assertEqual(first["portfolio"]["account_count"], 1)
            self.assertEqual(
                first["paper_accounts"][0]["valuation"]["mark"], "43.125"
            )
            self.assertEqual(
                first["paper_accounts"][0]["cost_effect"]["coverage_status"],
                "INCOMPLETE_UNKNOWN_CARRY_COSTS",
            )
            self.assertEqual(
                tuple(first["portfolio"]["symbols"]),
                ("HYPE-USDT-SWAP",),
            )
            self.assertEqual(first["data_coverage"][0]["profile_id"], HYPE_OKX_DATA_PROFILE.profile_id)
            self.assertEqual(
                {item["logical_agent_id"] for item in first["agent_states"]},
                {"HYPE_TRADER", "SNDK_TRADER"},
            )
            self.assertEqual(
                {
                    item["event_type"]
                    for item in first["timeline"]["items"]
                    if item["owner"] == "market_cycle"
                },
                {"InputSnapshot", "HypothesisRecord", "BehaviorPlan"},
            )


if __name__ == "__main__":
    unittest.main()
