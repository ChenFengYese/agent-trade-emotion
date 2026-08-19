from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.native_market_pilot import (
    NativeMarketPilotWorkflowError,
    _validate_proposal_grounding,
    advance_native_market_pilot,
    claim_native_market_request,
    initialize_native_market_pilot,
    native_market_pilot_status,
    submit_native_market_delivery,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.native_market_cycle import (
    SENTIMENT_DIMENSIONS,
    SENTIMENT_REQUIRED_DEPENDENCY_GROUPS,
    NativeMarketCycleError,
    build_shadow_action_evaluation,
)
from trade_system.theory_paper_v2.domain.native_agent_transport import (
    NativeAgentTransportError,
)
from trade_system.theory_paper_v2.domain.dynamic_research import (
    MARKET_CATEGORIES,
    build_market_information_snapshot,
)
from trade_system.theory_paper_v2.infrastructure.native_market_pilot_store import (
    LocalNativeMarketPilotStore,
    NativeMarketPilotStoreError,
)
from trade_system.theory_paper_v2.infrastructure.native_market_collector import (
    NativeMarketCollectionError,
    _cross_cycle_open_interest_fact,
    _verified_prior_open_interest,
)
from trade_system.theory_paper_v2.presentation.native_market_pilot_cli import (
    _verify_current_authority,
)


THEORY_SHA = "2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d"


def _config(run_id: str) -> dict:
    return self_digest(
        {
            "schema_id": "native_codex_market_pilot_config",
            "schema_version": "1.0.0",
            "config_id": "native-btc-four-cycle-test",
            "run_id": run_id,
            "theory_authority_path": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
            "theory_authority_sha256": THEORY_SHA,
            "candidate_theory_status": "DRAFT_NOT_AUTHORITY",
            "sentiment_standard_path": "theory/history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_2.md",
            "sentiment_standard_sha256": "b67bc8fc24e5c5bef1f47a25eca31be7e994e9b7cc2354a6b1fb31dc0348a4ea",
            "agent_id": "CURRENT_CODEX_TASK",
            "evidence_level": "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT",
            "instrument_id": "BTC-USDT-SWAP",
            "data_scope": "OFFICIAL_PUBLIC_MARKET_ONLY",
            "total_cycles": 4,
            "cadence_seconds": 3600,
            "first_due_at": "2026-08-06T00:00:00Z",
            "sentiment_dimensions": list(SENTIMENT_DIMENSIONS),
            "sentiment_required_dependency_groups": {
                axis: list(groups)
                for axis, groups in SENTIMENT_REQUIRED_DEPENDENCY_GROUPS.items()
            },
            "probe_notional_usdt": "250",
            "fee_rate": "0.0005",
            "slippage_rate": "0.001",
            "max_probe_risk_usdt": "10",
            "min_net_rr": "1.5",
            "max_output_bytes": 262144,
            "api_key_required": False,
            "sub_agents_allowed": False,
            "account_access": False,
            "order_submission": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "native_market_pilot_config_digest",
    )


def _authority(run_id: str, template_sha: str) -> tuple[dict, dict]:
    authority_id = "test-native-market-authority"
    receipt = self_digest(
        {
            "schema_id": "theory_paper_v2_research_authorization_receipt",
            "schema_version": "1.0.0",
            "authority_id": authority_id,
            "issued_at": "2026-08-06T00:00:00Z",
            "current_theory_sha256": THEORY_SHA,
            "authorized_operations": ["RUN_NATIVE_MARKET_PILOT"],
            "authorized_run_ids": [run_id],
            "authorized_template_sha256s": [template_sha],
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authorization_receipt_digest",
    )
    authority = {
        "schema_id": "theory_paper_v2_current_research_authority",
        "schema_version": "1.0.0",
        "authority_id": authority_id,
        "recorded_at": "2026-08-06T00:00:00Z",
        "status": "ACTIVE_FROZEN_RESEARCH",
        "reason": "Explicit test authority for one non-executable market pilot.",
        "current_theory": {
            "path": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
            "version": "2.1",
            "review_status": "FROZEN_APPROVED",
            "physical_sha256": THEORY_SHA,
        },
        "candidate_theory": {
            "path": "theory/history/RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md",
            "version": "3.0-draft",
            "review_status": "DRAFT_FOR_USER_REVIEW",
            "physical_sha256": "b353274dc90ae7af1493577b872032b00a845553db6f2512d6cce709cbaa86ef",
        },
        "experiment_start_authorized": True,
        "authorized_operations": ["RUN_NATIVE_MARKET_PILOT"],
        "authorized_run_ids": [run_id],
        "authorized_template_sha256s": [template_sha],
        "authorization_receipt_path": "config/test-receipt.json",
        "authorization_receipt_digest": receipt["authorization_receipt_digest"],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return authority, receipt


def _phase_b() -> dict:
    return self_digest(
        {
            "schema_id": "native_codex_transport_completion_receipt",
            "schema_version": "1.0.0",
            "run_id": "phase-b-test",
            "cycle_index": 1,
            "completed_at": "2026-08-06T00:00:00Z",
            "accepted_state_digest": "a" * 64,
            "durable_boundaries_verified": [
                "PROPOSAL",
                "DELIBERATION",
                "POST_ACCEPT_TAIL",
            ],
            "proposal_reinvocation_count_after_consume": 0,
            "deliberation_reinvocation_count_after_consume": 0,
            "postaccept_agent_invocation_count": 0,
            "market_data_accessed": False,
            "model_api_called": False,
            "evidence_level": "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_transport_completion_receipt_digest",
    )


def _initialize(root: Path) -> LocalNativeMarketPilotStore:
    run_id = root.name
    config = _config(run_id)
    raw = __import__(
        "trade_system.theory_paper_v2.domain.contracts.canonical",
        fromlist=["canonical_bytes"],
    ).canonical_bytes(config) + b"\n"
    template_sha = hashlib.sha256(raw).hexdigest()
    authority, receipt = _authority(run_id, template_sha)
    phase_b = _phase_b()
    store = LocalNativeMarketPilotStore(root)
    initialize_native_market_pilot(
        store=store,
        run_id=run_id,
        created_at="2026-08-06T00:00:00Z",
        config=config,
        config_physical_sha256=template_sha,
        authority=authority,
        authorization_receipt=receipt,
        phase_b_completion=phase_b,
        phase_b_completion_binding={
            "relative_ref": "phase-b.json",
            "semantic_digest": phase_b["native_transport_completion_receipt_digest"],
            "physical_sha256": "f" * 64,
        },
        implementation_bindings={
            "pilot.py": {"relative_ref": "pilot.py", "physical_sha256": "1" * 64}
        },
    )
    return store


def _snapshot(run_id: str, cycle_index: int) -> tuple[dict, dict[str, bytes]]:
    raw = b'{"code":"0","data":[{"markPx":"100"}]}'
    sha = hashlib.sha256(raw).hexdigest()
    facts = [
        {
            "fact_id": "mark-price",
            "status": "OBSERVED",
            "value": "100",
            "unit": "USDT_PER_BTC",
            "source_request_id": "fixture-public",
            "source_raw_body_sha256": sha,
            "available_at": "2026-08-06T00:00:00Z",
            "observed_at": "1785974400000",
            "unknown_reason": None,
        },
        {
            "fact_id": "open-interest-btc",
            "status": "OBSERVED",
            "value": "1000",
            "unit": "BTC",
            "source_request_id": "fixture-public",
            "source_raw_body_sha256": sha,
            "available_at": "2026-08-06T00:00:00Z",
            "observed_at": "1785974400000",
            "unknown_reason": None,
        },
        {
            "fact_id": "open-interest-change-pct",
            "status": "UNKNOWN",
            "value": None,
            "unit": None,
            "source_request_id": None,
            "source_raw_body_sha256": None,
            "available_at": None,
            "observed_at": None,
            "unknown_reason": "FIRST_CYCLE_HAS_NO_PRIOR_OPEN_INTEREST",
        },
        {
            "fact_id": "news-cross-market",
            "status": "UNKNOWN",
            "value": None,
            "unit": None,
            "source_request_id": None,
            "source_raw_body_sha256": None,
            "available_at": None,
            "observed_at": None,
            "unknown_reason": "NOT_AUTHORIZED",
        },
    ]
    dynamic_facts = []
    for index, category in enumerate(MARKET_CATEGORIES):
        observed = index == 0 or category == "OPEN_INTEREST_AND_LEVERAGE"
        unknown_id = (
            "news-cross-market"
            if category == "NEWS_EVENTS_AND_REACTION"
            else f"unknown-{index}"
        )
        fact_id = (
            "mark-price"
            if index == 0
            else "open-interest-btc"
            if category == "OPEN_INTEREST_AND_LEVERAGE"
            else unknown_id
        )
        observed_value = "100" if index == 0 else "1000"
        observed_unit = "USDT_PER_BTC" if index == 0 else "BTC"
        observed_group = "MARK_PRICE" if index == 0 else "OPEN_INTEREST"
        dynamic_facts.append(
            {
                "fact_id": fact_id,
                "kind": "RAW_FACT",
                "category": category,
                "metric": fact_id if observed else "unavailable",
                "value": observed_value if observed else None,
                "unit": observed_unit if observed else "UNAVAILABLE",
                "symbol": "BTC-USDT-SWAP",
                "timeframe": "SNAPSHOT",
                "window": "CURRENT_CAPTURE",
                "source_ref": "fixture-public" if observed else "NO_SOURCE",
                "raw_ref": "cycles/0001/market/raw/fixture-public.body" if observed else "UNAVAILABLE",
                "raw_sha256": sha if observed else None,
                "observed_at": "2026-08-06T00:00:00Z",
                "available_at": "2026-08-06T00:00:00Z",
                "quality": "GOOD" if observed else "UNKNOWN",
                "coverage": "1" if observed else "0",
                "dependency_group": observed_group if observed else f"UNKNOWN_{index}",
                "lineage": [],
                "transform": None,
                "limitations": "Fixture fact.",
                "missing_reason": None if observed else "NO_SOURCE",
            }
        )
    dynamic_facts.append(
        {
            "fact_id": "open-interest-change-pct",
            "kind": "RAW_FACT",
            "category": "OPEN_INTEREST_AND_LEVERAGE",
            "metric": "open-interest-change-pct",
            "value": None,
            "unit": "UNAVAILABLE",
            "symbol": "BTC-USDT-SWAP",
            "timeframe": "CROSS_CYCLE",
            "window": "PREVIOUS_ACCEPTED_CYCLE_TO_CURRENT_CAPTURE",
            "source_ref": "NO_SOURCE",
            "raw_ref": "UNAVAILABLE",
            "raw_sha256": None,
            "observed_at": "2026-08-06T00:00:00Z",
            "available_at": "2026-08-06T00:00:00Z",
            "quality": "UNKNOWN",
            "coverage": "0",
            "dependency_group": "OPEN_INTEREST_CHANGE",
            "lineage": [],
            "transform": None,
            "limitations": "First cycle has no prior open interest.",
            "missing_reason": "FIRST_CYCLE_HAS_NO_PRIOR_OPEN_INTEREST",
        }
    )
    for timeframe, value, dependency_group in (
        ("15m", "1", "CANDLE_15M"),
        ("1h", "2", "CANDLE_1H"),
        ("4h", "3", "CANDLE_4H"),
        ("1d", "-1", "CANDLE_1D"),
    ):
        dynamic_facts.append(
            {
                "fact_id": f"candle-{timeframe}-return-pct",
                "kind": "DERIVED_FEATURE",
                "category": "PRICE_AND_RETURNS",
                "metric": "closed-candle-return-pct",
                "value": value,
                "unit": "PERCENT",
                "symbol": "BTC-USDT-SWAP",
                "timeframe": timeframe,
                "window": "LATEST_CLOSED_CANDLE",
                "source_ref": "fixture-public",
                "raw_ref": f"cycles/{cycle_index:04d}/market/raw/fixture-public.body",
                "raw_sha256": sha,
                "observed_at": "2026-08-06T00:00:00Z",
                "available_at": "2026-08-06T00:00:00Z",
                "quality": "GOOD",
                "coverage": "1",
                "dependency_group": dependency_group,
                "lineage": ["mark-price"],
                "transform": "fixture closed-candle return",
                "limitations": "Fixture fact for sign grounding.",
                "missing_reason": None,
            }
        )
    market_information = build_market_information_snapshot(
        run_id=run_id,
        cycle_index=cycle_index,
        symbol="BTC-USDT-SWAP",
        as_of="2026-08-06T00:00:00Z",
        facts=dynamic_facts,
    )
    snapshot = self_digest(
        {
            "schema_id": "native_btc_public_market_snapshot",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "instrument_id": "BTC-USDT-SWAP",
            "server_time_ms": 1785974400000,
            "captured_through": "2026-08-06T00:00:00Z",
            "mark_price": "100",
            "facts": facts,
            "market_information_snapshot": market_information,
            "prior_market_snapshot_digest": None,
            "source_captures": [
                {
                    "request_id": "fixture-public",
                    "raw_body_sha256": sha,
                }
            ],
            "required_request_ids": ["fixture-public"],
            "optional_failures": {},
            "data_scope": "OFFICIAL_PUBLIC_MARKET_ONLY",
            "point_in_time": True,
            "missing_is_zero": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_market_snapshot_digest",
    )
    return snapshot, {"fixture-public": raw}


def _proposal(store: LocalNativeMarketPilotStore, cycle_index: int = 1) -> dict:
    request = store.read_document(
        relative_ref=f"cycles/{cycle_index:04d}/mailbox/requests/proposal.json",
        digest_field="native_agent_request_digest",
    )
    dimensions = []
    for dimension in SENTIMENT_DIMENSIONS:
        if dimension == "TIMEFRAME_COHERENCE":
            signs = {"15m": 1, "1h": 1, "4h": 1, "1d": -1}
            contributors = [
                {
                    "fact_id": f"candle-{timeframe}-return-pct",
                    "ordinal_contribution": sign,
                    "rule": "Exact sign of the bound closed-candle return.",
                    "direction": "POSITIVE" if sign > 0 else "NEGATIVE",
                }
                for timeframe, sign in signs.items()
            ]
            timeframe_states = signs
        else:
            contributors = []
            timeframe_states = {"SNAPSHOT": None}
        dimensions.append(
            {
                "axis": dimension,
                "required_dependency_groups": list(
                    SENTIMENT_REQUIRED_DEPENDENCY_GROUPS[dimension]
                ),
                "contributors": contributors,
                "timeframe_states": timeframe_states,
                "agent_interpretation": "Fixture state is unknown.",
                "limitations": "Fixture only.",
                "next_discriminating_observation": "Observe the next fixture.",
            }
        )
    hypotheses = [
        {
            "hypothesis_id": identifier,
            "operation": "CREATE",
            "status": "WATCH",
            "thesis": thesis,
            "falsifier": "A closed-bar break invalidates this path.",
            "expiry": "NEXT_CYCLE",
            "next_observation": "Observe the next closed bar and public mark.",
            "evidence_refs": ["mark-price"],
        }
        for identifier, thesis in (
            ("h-range", "Price remains in a range."),
            ("h-up", "Price resolves upward."),
            ("h-down", "Price resolves downward."),
        )
    ]
    candidates = [
        {
            "candidate_id": "candidate-wait",
            "action_class": "WAIT",
            "thesis": "Wait for a closed-bar resolution.",
            "hypothesis_id": "h-range",
            "evidence_refs": ["mark-price"],
            "reason": "Evidence is incomplete.",
            "opportunity_cost": "A fast breakout could be missed.",
            "next_review_condition": "Review at the next cycle.",
            "entry_reference_price": None,
            "stop_price": None,
            "target_price": None,
            "notional_usdt": None,
        },
        {
            "candidate_id": "candidate-long",
            "action_class": "OPEN_LONG",
            "thesis": "Shadow a bullish resolution.",
            "hypothesis_id": "h-up",
            "evidence_refs": ["mark-price"],
            "entry_reference_price": "100",
            "stop_price": "98",
            "target_price": "106",
            "notional_usdt": "250",
        },
        {
            "candidate_id": "candidate-short",
            "action_class": "OPEN_SHORT",
            "thesis": "Shadow a bearish resolution.",
            "hypothesis_id": "h-down",
            "evidence_refs": ["mark-price"],
            "entry_reference_price": "100",
            "stop_price": "102",
            "target_price": "94",
            "notional_usdt": "250",
        },
    ]
    return {
        "schema_id": "native_codex_market_proposal_payload",
        "schema_version": "1.0.0",
        "run_id": request["run_id"],
        "cycle_index": cycle_index,
        "input_digest": request["input_binding"]["semantic_digest"],
        "market_snapshot_digest": request["market_snapshot_digest"],
        "sentiment_dimension_inputs": dimensions,
        "operational_synthesis": "Fixture synthesis remains neutral and non-executable.",
        "public_inference_claims": [
            {
                "claim_id": "claim-range",
                "statement": "The current snapshot alone does not establish direction.",
                "financial_mechanism": "Unresolved direction increases adverse-selection risk.",
                "hypothesis_impact": "Range remains lead; directional paths remain open.",
                "action_implication": "WAIT is legal while both shadow directions remain compared.",
                "falsifier": "A confirmed directional break with participation.",
                "limitations": "Only the current frozen public snapshot is used.",
                "next_observation": "Next closed bar and updated participation.",
                "supporting_evidence_refs": ["mark-price"],
                "counter_evidence_refs": ["news-cross-market"],
            }
        ],
        "hypothesis_updates": hypotheses,
        "expectation_updates": [
            {
                "expectation_id": "e-range-review",
                "operation": "CREATE",
                "status": "OPEN",
                "statement": "Review whether the range persists.",
                "condition": "Next public snapshot is available.",
                "expiry": "NEXT_CYCLE",
                "next_observation": "Compare the next mark and closed bar.",
                "hypothesis_id": "h-range",
                "evidence_refs": ["mark-price"],
            }
        ],
        "path_competition": {
            "lead_path_id": "h-range",
            "runner_up_path_id": "h-up",
            "other_path_id": "h-down",
            "ranking_basis": "Incomplete direction evidence favors the range path.",
            "switch_condition": "A confirmed directional break changes the lead.",
        },
        "candidate_proposals": candidates,
        "private_chain_of_thought_recorded": False,
    }


def _deliberation(store: LocalNativeMarketPilotStore, cycle_index: int = 1) -> dict:
    request = store.read_document(
        relative_ref=f"cycles/{cycle_index:04d}/mailbox/requests/deliberation.json",
        digest_field="native_agent_request_digest",
    )
    return {
        "schema_id": "native_codex_market_deliberation_payload",
        "schema_version": "1.0.0",
        "run_id": request["run_id"],
        "cycle_index": cycle_index,
        "input_digest": request["input_binding"]["semantic_digest"],
        "evaluation_digest": request["evaluation_digest"],
        "selected_candidate_id": "candidate-wait",
        "ranked_alternative_ids": ["candidate-long", "candidate-short"],
        "why_not_selected": {
            "candidate-long": "Direction evidence is incomplete.",
            "candidate-short": "Direction evidence is incomplete.",
        },
        "selection_rationale": "WAIT preserves risk while retaining both paths.",
        "next_review_condition": "Review at the next due public snapshot.",
        "private_chain_of_thought_recorded": False,
    }


class NativeMarketPilotTests(unittest.TestCase):
    def test_numeric_sign_and_timeframe_coherence_are_snapshot_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "native-market-numeric-grounding"
            store = _initialize(root)
            snapshot, raws = _snapshot(root.name, 1)
            advance_native_market_pilot(
                store=store,
                run_id=root.name,
                now="2026-08-06T00:00:01Z",
                snapshot=snapshot,
                raw_body_by_request_id=raws,
            )

            sign_drift = _proposal(store)
            directional = next(
                row
                for row in sign_drift["sentiment_dimension_inputs"]
                if row["axis"] == "PRICE_DIRECTIONAL_PRESSURE"
            )
            directional["contributors"] = [
                {
                    "fact_id": "candle-15m-return-pct",
                    "ordinal_contribution": -1,
                    "rule": "Intentionally inverted fixture sign.",
                    "direction": "NEGATIVE",
                }
            ]
            with self.assertRaisesRegex(
                NativeMarketPilotWorkflowError,
                "NATIVE_MARKET_SENTIMENT_NUMERIC_SIGN_MISMATCH",
            ):
                _validate_proposal_grounding(
                    proposal=sign_drift,
                    snapshot=snapshot,
                    prior=None,
                )

            missing_timeframe = _proposal(store)
            coherence = next(
                row
                for row in missing_timeframe["sentiment_dimension_inputs"]
                if row["axis"] == "TIMEFRAME_COHERENCE"
            )
            coherence["contributors"] = coherence["contributors"][:-1]
            with self.assertRaisesRegex(
                NativeMarketPilotWorkflowError,
                "NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID",
            ):
                _validate_proposal_grounding(
                    proposal=missing_timeframe,
                    snapshot=snapshot,
                    prior=None,
                )

            wrong_state = _proposal(store)
            coherence = next(
                row
                for row in wrong_state["sentiment_dimension_inputs"]
                if row["axis"] == "TIMEFRAME_COHERENCE"
            )
            coherence["timeframe_states"]["1d"] = 1
            with self.assertRaisesRegex(
                NativeMarketPilotWorkflowError,
                "NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID",
            ):
                _validate_proposal_grounding(
                    proposal=wrong_state,
                    snapshot=snapshot,
                    prior=None,
                )

    def test_sentiment_contract_rejects_semantic_and_coverage_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "native-market-semantic-gate"
            store = _initialize(root)
            snapshot, raws = _snapshot(root.name, 1)
            advance_native_market_pilot(
                store=store,
                run_id=root.name,
                now="2026-08-06T00:00:01Z",
                snapshot=snapshot,
                raw_body_by_request_id=raws,
            )
            claim_native_market_request(
                store=store,
                run_id=root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T00:00:02Z",
            )
            semantic_drift = _proposal(store)
            participation = next(
                row
                for row in semantic_drift["sentiment_dimension_inputs"]
                if row["axis"] == "PARTICIPATION_AND_FLOW"
            )
            participation["contributors"] = [
                {
                    "fact_id": "candle-15m-volume-vs-20bar-median",
                    "ordinal_contribution": -1,
                    "rule": "Invalidly treats low volume as seller direction.",
                    "direction": "NEGATIVE",
                }
            ]
            with self.assertRaisesRegex(
                NativeAgentTransportError,
                "NATIVE_MARKET_PARTICIPATION_VOLUME_DIRECTION_FORBIDDEN",
            ):
                submit_native_market_delivery(
                    store=store,
                    run_id=root.name,
                    stage="PROPOSAL",
                    payload=semantic_drift,
                    delivered_at="2026-08-06T00:00:03Z",
                )
            coverage_drift = _proposal(store)
            coverage_drift["sentiment_dimension_inputs"][0][
                "required_dependency_groups"
            ] = ["CANDLE_15M"]
            with self.assertRaisesRegex(
                NativeAgentTransportError,
                "NATIVE_MARKET_SENTIMENT_REQUIRED_GROUPS_DRIFTED",
            ):
                submit_native_market_delivery(
                    store=store,
                    run_id=root.name,
                    stage="PROPOSAL",
                    payload=coverage_drift,
                    delivered_at="2026-08-06T00:00:03Z",
                )

    def test_cross_cycle_open_interest_requires_bound_prior_snapshot(self) -> None:
        prior, _ = _snapshot("native-market-oi-lineage", 1)
        prior_fact = _verified_prior_open_interest(
            run_id="native-market-oi-lineage",
            cycle_index=2,
            prior_market_snapshot=prior,
        )
        self.assertEqual("1000", prior_fact["value"])
        current = {
            "fact_id": "open-interest-btc",
            "status": "OBSERVED",
            "value": "1005",
            "unit": "BTC",
            "source_request_id": "fixture-public-current",
            "source_raw_body_sha256": "a" * 64,
            "available_at": "2026-08-06T01:00:00Z",
            "observed_at": "1785978000000",
            "unknown_reason": None,
        }
        change = _cross_cycle_open_interest_fact(
            cycle_index=2,
            current_fact=current,
            prior_open_interest=prior_fact,
        )
        self.assertEqual("0.5", change["value"])
        self.assertEqual("PERCENT", change["unit"])
        with self.assertRaisesRegex(
            NativeMarketCollectionError,
            "NATIVE_MARKET_PRIOR_SNAPSHOT_REQUIRED",
        ):
            _verified_prior_open_interest(
                run_id="native-market-oi-lineage",
                cycle_index=2,
                prior_market_snapshot=None,
            )
        tampered = dict(prior)
        tampered["cycle_index"] = 9
        with self.assertRaisesRegex(
            NativeMarketCollectionError,
            "NATIVE_MARKET_PRIOR_SNAPSHOT_DIGEST_INVALID",
        ):
            _verified_prior_open_interest(
                run_id="native-market-oi-lineage",
                cycle_index=2,
                prior_market_snapshot=tampered,
            )

    def test_current_authority_revocation_stops_every_later_cli_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "runtime" / "native-market-authority"
            store = _initialize(root)
            envelope = store.read_document(
                relative_ref="frozen/current-research-authority.json",
                digest_field="native_market_frozen_authority_digest",
            )
            config_root = base / "project" / "config"
            config_root.mkdir(parents=True)
            current_path = (
                config_root
                / "theory_paper_v2.current_research_authority.v1.json"
            )
            current_path.write_text(
                json.dumps(envelope["authority"]), encoding="utf-8"
            )
            _verify_current_authority(project_root=base / "project", store=store)
            revoked = dict(envelope["authority"])
            revoked["status"] = "SUSPENDED_USER_REVIEW_REQUIRED"
            revoked["experiment_start_authorized"] = False
            current_path.write_text(json.dumps(revoked), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "NATIVE_MARKET_CURRENT_AUTHORITY_REVOKED_OR_DRIFTED"
            ):
                _verify_current_authority(
                    project_root=base / "project", store=store
                )

    def test_first_cycle_crosses_agent_and_postaccept_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "native-market-test"
            store = _initialize(root)
            snapshot, raws = _snapshot(root.name, 1)
            first = advance_native_market_pilot(
                store=store,
                run_id=root.name,
                now="2026-08-06T00:00:01Z",
                snapshot=snapshot,
                raw_body_by_request_id=raws,
            )
            self.assertEqual("WAITING_FOR_PROPOSAL", first["status"])
            claim_native_market_request(
                store=store,
                run_id=root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T00:00:02Z",
            )
            submit_native_market_delivery(
                store=store,
                run_id=root.name,
                stage="PROPOSAL",
                payload=_proposal(store),
                delivered_at="2026-08-06T00:00:03Z",
            )
            second = advance_native_market_pilot(
                store=LocalNativeMarketPilotStore(root),
                run_id=root.name,
                now="2026-08-06T00:00:04Z",
            )
            self.assertEqual("WAITING_FOR_DELIBERATION", second["status"])
            next_store = LocalNativeMarketPilotStore(root)
            claim_native_market_request(
                store=next_store,
                run_id=root.name,
                stage="DELIBERATION",
                claimed_at="2026-08-06T00:00:05Z",
            )
            submit_native_market_delivery(
                store=next_store,
                run_id=root.name,
                stage="DELIBERATION",
                payload=_deliberation(next_store),
                delivered_at="2026-08-06T00:00:06Z",
            )
            third = advance_native_market_pilot(
                store=LocalNativeMarketPilotStore(root),
                run_id=root.name,
                now="2026-08-06T00:00:07Z",
            )
            self.assertEqual("POST_ACCEPT_PENDING", third["status"])
            fourth = advance_native_market_pilot(
                store=LocalNativeMarketPilotStore(root),
                run_id=root.name,
                now="2026-08-06T00:00:08Z",
            )
            self.assertEqual("READY_FOR_CYCLE", fourth["status"])
            self.assertEqual(2, fourth["cycle_index"])
            self.assertEqual("WAIT_UNTIL_DUE", fourth["next_action"])
            self.assertTrue((root / "cycles/0001/report/cycle-report.json").is_file())

    def test_wrong_cycle_raw_and_checkpoint_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "native-market-tamper"
            store = _initialize(root)
            snapshot, raws = _snapshot(root.name, 2)
            with self.assertRaisesRegex(
                NativeMarketPilotWorkflowError, "NATIVE_MARKET_SNAPSHOT_INVALID"
            ):
                advance_native_market_pilot(
                    store=store,
                    run_id=root.name,
                    now="2026-08-06T00:00:01Z",
                    snapshot=snapshot,
                    raw_body_by_request_id=raws,
                )
            path = root / "market-checkpoint.json"
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace('"revision":0', '"revision":9'), encoding="utf-8")
            with self.assertRaisesRegex(
                NativeMarketPilotStoreError, "NATIVE_MARKET_CHECKPOINT_DIGEST_INVALID"
            ):
                native_market_pilot_status(
                    store=LocalNativeMarketPilotStore(root),
                    run_id=root.name,
                    now="2026-08-06T00:00:02Z",
                )

    def test_financial_kernel_vetoes_wrong_mark_and_uncalibrated_probability(self) -> None:
        candidate = {
            "candidate_id": "long",
            "action_class": "OPEN_LONG",
            "hypothesis_id": "h",
            "evidence_refs": ["mark-price"],
            "entry_reference_price": "99",
            "stop_price": "98",
            "target_price": "106",
            "notional_usdt": "250",
        }
        wait = {
            "candidate_id": "wait",
            "action_class": "WAIT",
            "hypothesis_id": "h",
            "evidence_refs": ["mark-price"],
            "opportunity_cost": "move",
            "next_review_condition": "next",
        }
        short = {
            "candidate_id": "short",
            "action_class": "OPEN_SHORT",
            "hypothesis_id": "h",
            "evidence_refs": ["mark-price"],
            "entry_reference_price": "100",
            "stop_price": "102",
            "target_price": "94",
            "notional_usdt": "250",
        }
        result = build_shadow_action_evaluation(
            run_id="run",
            cycle_index=1,
            market_snapshot_digest="a" * 64,
            mark_price="100",
            valid_evidence_refs=["mark-price"],
            candidate_proposals=[wait, candidate, short],
            notional_usdt="250",
            fee_rate="0.0005",
            slippage_rate="0.001",
            max_probe_risk_usdt="10",
            min_net_rr="1.5",
        )
        long_row = next(row for row in result["candidates"] if row["candidate_id"] == "long")
        self.assertFalse(long_row["feasible"])
        self.assertIn("ENTRY_REFERENCE_NOT_CURRENT_MARK", long_row["hard_vetoes"])


if __name__ == "__main__":
    unittest.main()
