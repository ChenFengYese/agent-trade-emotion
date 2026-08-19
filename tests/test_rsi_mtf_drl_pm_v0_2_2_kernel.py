from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import unittest
from pathlib import Path

import trade_system.rsi_mtf_drl_pm_v0_2_2 as package
from trade_system.rsi_mtf_drl_pm_v0_2_2.contract import serialize_contract
from trade_system.rsi_mtf_drl_pm_v0_2_2.kernel import (
    _FIXED_EVENT_RANK,
    _REDUCER_KINDS,
    _STOP_ACK_RANK_PREDICATE,
    _causality_violation,
    _coverage_shape_valid,
    _event_priority,
    _label_bindings,
    _matching_sufficient_stop_ack,
    _select_closed_mark_bar_slot,
    _source_payload_valid,
    calculate_decision,
    encode_ledger,
    first_hit_label,
    reduce_event_array,
    validate_bundle,
)
from trade_system.rsi_mtf_drl_pm_v0_2_2.model import (
    BundleValidationFailure,
    FrozenMapping,
    KernelValidationError,
    ValidatedBundle,
    canonical_json,
    freeze,
    materialize,
    sha256_json,
    stable_id,
    validate_decimal,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json"
MODEL_PATH = ROOT / "trade_system/rsi_mtf_drl_pm_v0_2_2/model.py"
KERNEL_PATH = ROOT / "trade_system/rsi_mtf_drl_pm_v0_2_2/kernel.py"
LANE = "E0_SYNTHETIC_CANONICAL_V0_2_2"
ZERO_SHA = "0" * 64
ANCHOR_US = 1_700_000_000_000_000
COMPOSITE_THEORY_ID = (
    "3e7ecf5e257d8a2dbf5cc826c1da1240283a2379de710e4be90f7bcfdb8118ea"
)


def _id(name: str) -> str:
    return stable_id("b2-kernel-test-id/v0.2.2", {"name": name})


def _without(value: dict[str, object], *keys: str) -> dict[str, object]:
    return {key: child for key, child in value.items() if key not in keys}


def _priority_policy() -> dict[str, object]:
    ranks: dict[str, object] = dict(_FIXED_EVENT_RANK)
    ranks["STOP_ACK"] = {"MATCHING_SUFFICIENT": 5, "OTHERWISE": 10}
    policy: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.reducer-priority-policy.v0.2.2",
        "event_rank": ranks,
        "stop_ack_rank_predicate": _STOP_ACK_RANK_PREDICATE,
        "tie_break": [
            "event_time_us",
            "priority_rank",
            "source_sequence",
            "source_event_id",
        ],
        "unknown_event_action": "REJECT_BUNDLE",
        "policy_sha256": ZERO_SHA,
    }
    policy["policy_sha256"] = stable_id(
        "reducer-priority-policy/v0.2.2",
        _without(policy, "policy_sha256"),
    )
    return policy


def _wrapper(
    schema_id: str,
    payload: dict[str, object],
    artifact_scope_id: str | None,
    available_at_us: int | None,
) -> dict[str, object]:
    payload_sha = sha256_json(payload)
    wrapper: dict[str, object] = {
        "artifact_id": ZERO_SHA,
        "artifact_scope_id": artifact_scope_id,
        "schema_id": schema_id,
        "available_at_us": available_at_us,
        "payload_sha256": payload_sha,
        "payload": payload,
    }
    wrapper["artifact_id"] = stable_id(
        "synthetic-artifact/v0.2.2",
        {
            "artifact_scope_id": artifact_scope_id,
            "schema_id": schema_id,
            "available_at_us": available_at_us,
            "payload_sha256": payload_sha,
        },
    )
    return wrapper


def _identity(control_id: str) -> dict[str, object]:
    return {
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "account_scope_id": "synthetic-account",
        "role": "SYNTHETIC",
        "episode_id": _id(f"episode-{control_id}"),
        "opportunity_id": _id("opportunity"),
        "control_id": control_id,
        "candidate_id": _id("candidate"),
    }


def _policy_bindings(priority_sha: str) -> dict[str, str]:
    result = {
        "u_policy_sha256": _id("u-policy"),
        "entry_policy_sha256": _id("entry-policy"),
        "exit_policy_template_sha256": _id("exit-policy-template"),
        "cost_policy_sha256": _id("cost-policy"),
        "risk_policy_sha256": _id("risk-policy"),
        "label_policy_sha256": _id("label-policy"),
        "data_role_sha256": _id("data-role"),
        "estimator_policy_sha256": _id("estimator-policy"),
        "source_selector_policy_sha256": _id("source-selector-policy"),
        "reducer_priority_policy_sha256": priority_sha,
        "policy_bundle_sha256": _id("policy-bundle"),
    }
    return result


def _seed(
    identity: dict[str, object],
    priority_sha: str,
    side: str,
) -> dict[str, object]:
    seed: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.frozen-ledger-seed.v0.2.2",
        "opportunity_id": identity["opportunity_id"],
        "control_id": identity["control_id"],
        "candidate_id": identity["candidate_id"],
        "side": side,
        "anchor_at_us": ANCHOR_US,
        "anchor_status": "UNKNOWN" if side == "NONE" else "VALID",
        "anchor_price": None if side == "NONE" else "100",
        "cost_basis": {
            "fee_bps_per_side": "5",
            "worst_slippage_bps_per_side": "10",
            "funding_buffer_bps": "5",
            "tail_bps": "10",
        },
        "policy_bindings": _policy_bindings(priority_sha),
        "master_u_receipt_sha256": _id("master-u-receipt"),
        "seed_sha256": ZERO_SHA,
    }
    seed["seed_sha256"] = stable_id(
        "frozen-ledger-seed/v0.2.2", _without(seed, "seed_sha256")
    )
    return seed


def _ledger_bindings(
    contract: dict[str, object],
    seed: dict[str, object],
    code_sha256: str,
) -> dict[str, str]:
    source = contract["source_authority"]
    assert isinstance(source, dict)
    return {
        "core_raw_sha256": str(source["core_theory_raw_sha256"]),
        "v0_2_contract_canonical_sha256": str(
            source["legacy_v0_2_contract_canonical_sha256"]
        ),
        "v0_2_1_addendum_raw_sha256": str(
            source["v0_2_1_addendum_raw_sha256"]
        ),
        "v0_2_2_delta_raw_sha256": str(source["semantic_source_raw_sha256"]),
        "v0_2_2_contract_sha256": sha256_json(contract),
        "composite_theory_id": str(contract["composite_theory_id"]),
        "policy_bundle_sha256": str(
            seed["policy_bindings"]["policy_bundle_sha256"]  # type: ignore[index]
        ),
        "code_sha256": code_sha256,
        "data_or_fixture_sha256": _id("synthetic-fixture-family"),
        "ledger_seed_sha256": str(seed["seed_sha256"]),
    }


def _abstain_context(
    seed: dict[str, object], action_at_us: int
) -> dict[str, object]:
    context: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.frozen-action-context.v0.2.2",
        "ledger_seed_sha256": seed["seed_sha256"],
        "decision_kind": "ABSTAIN",
        "action_at_us": action_at_us,
        "entry_mode": "NONE",
        "shared_entry_action_sha256": None,
        "initial_levels": {
            "anchor": None,
            "p_limit": None,
            "i0": None,
            "g0": None,
            "s0": None,
            "t0": None,
            "h0_us": None,
            "tcap": None,
        },
        "risk_basis": {
            "submitted_qty": "0",
            "r_unit_usdt": "0",
            "r_episode_max_usdt": "0",
            "pending_existing_at_action_usdt": "0",
        },
        "decision_input_binding_artifact_id": None,
        "decision_input_binding_sha256": None,
        "decision_result_sha256": None,
        "action_context_sha256": ZERO_SHA,
    }
    context["action_context_sha256"] = stable_id(
        "frozen-action-context/v0.2.2",
        _without(context, "action_context_sha256"),
    )
    return context


def _event(
    identity: dict[str, object],
    bundle_scope_id: str,
    *,
    event_kind: str,
    event_time_us: int,
    priority_rank: int,
    source_sequence: int,
    payload: dict[str, object],
    predecessors: list[str] | None = None,
    artifact_ids: list[str] | None = None,
    economic_event_time_us: int | None = None,
    shared_entry_event_id: str | None = None,
    request_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, object]:
    predecessor_ids = sorted(predecessors or [])
    input_artifact_ids = sorted(artifact_ids or [])
    payload_sha = sha256_json(payload)
    event: dict[str, object] = {
        "event_kind": event_kind,
        "venue_id": identity["venue_id"],
        "instrument_id": identity["instrument_id"],
        "episode_id": identity["episode_id"],
        "opportunity_id": identity["opportunity_id"],
        "control_id": identity["control_id"],
        "candidate_id": identity["candidate_id"],
        "event_time_us": event_time_us,
        "lane_available_at_us": event_time_us,
        "economic_event_time_us": economic_event_time_us,
        "priority_rank": priority_rank,
        "source_sequence": source_sequence,
        "source_event_id": ZERO_SHA,
        "predecessor_event_ids": predecessor_ids,
        "input_artifact_ids": input_artifact_ids,
        "shared_entry_event_id": shared_entry_event_id,
        "request_id": request_id,
        "order_id": order_id,
        "payload_sha256": payload_sha,
        "payload": payload,
    }
    event["source_event_id"] = stable_id(
        "canonical-synthetic-event/v0.2.2",
        {
            "bundle_scope_id": bundle_scope_id,
            **{
                key: event[key]
                for key in (
                    "event_kind",
                    "event_time_us",
                    "lane_available_at_us",
                    "economic_event_time_us",
                    "priority_rank",
                    "source_sequence",
                    "predecessor_event_ids",
                    "input_artifact_ids",
                    "shared_entry_event_id",
                    "request_id",
                    "order_id",
                    "payload_sha256",
                )
            },
        },
    )
    return event


def _bundle(
    contract: dict[str, object],
    *,
    control_id: str = "C0",
    code_sha256: str | None = None,
) -> tuple[dict[str, object], int]:
    code = code_sha256 or _id("kernel-code")
    identity = _identity(control_id)
    priority = _priority_policy()
    seed = _seed(identity, str(priority["policy_sha256"]), "NONE" if control_id == "C0" else "LONG")
    bindings = _ledger_bindings(contract, seed, code)
    scope_id = stable_id(
        "canonical-synthetic-bundle-scope/v0.2.2",
        {
            "ledger_identity": identity,
            "ledger_seed_sha256": seed["seed_sha256"],
            "policy_bundle_sha256": bindings["policy_bundle_sha256"],
        },
    )
    artifacts: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    action_context: dict[str, object] | None = None
    finalized_at_us = ANCHOR_US
    if control_id != "C0":
        priority_wrapper = _wrapper(
            "REDUCER_PRIORITY_POLICY", priority, None, None
        )
        artifacts.append(priority_wrapper)
        finalized_at_us = ANCHOR_US + 1_000_000
        action_context = _abstain_context(seed, finalized_at_us)
        events.append(
            _event(
                identity,
                scope_id,
                event_kind="KILL",
                event_time_us=finalized_at_us,
                priority_rank=1,
                source_sequence=0,
                payload={
                    "reason_code": "SYNTHETIC_PRE_SUBMIT_KILL",
                    "details_sha256": _id("fatal-details"),
                },
                artifact_ids=[],
            )
        )
    artifacts.sort(key=lambda item: str(item["artifact_id"]))
    event_set = stable_id("canonical-synthetic-event-set/v0.2.2", events)
    artifact_set = stable_id(
        "canonical-synthetic-artifact-set/v0.2.2", artifacts
    )
    expected = [] if control_id == "C0" else [finalized_at_us]
    coverage: dict[str, object] = {
        "status": "COMPLETE",
        "window_start_exclusive_us": ANCHOR_US,
        "window_end_inclusive_us": finalized_at_us,
        "expected_grid_times_us": expected,
        "observed_grid_times_us": expected,
        "missing_grid_times_us": [],
        "event_count": len(events),
        "artifact_count": len(artifacts),
        "event_set_sha256": event_set,
        "artifact_set_sha256": artifact_set,
        "coverage_sha256": ZERO_SHA,
    }
    coverage["coverage_sha256"] = stable_id(
        "canonical-synthetic-coverage/v0.2.2",
        _without(coverage, "coverage_sha256"),
    )
    result: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.2",
        "bundle_scope_id": scope_id,
        "ledger_bindings": bindings,
        "ledger_identity": identity,
        "ledger_seed": seed,
        "action_context": action_context,
        "entry_execution_binding": None,
        "artifacts": artifacts,
        "coverage": coverage,
        "event_array": events,
        "finalized_at_us": finalized_at_us,
        "event_set_sha256": event_set,
        "bundle_sha256": ZERO_SHA,
    }
    result["bundle_sha256"] = stable_id(
        "canonical-synthetic-event-bundle/v0.2.2",
        _without(result, "bundle_sha256"),
    )
    return result, finalized_at_us


def _reseal_bundle(bundle: dict[str, object]) -> None:
    seed = bundle["ledger_seed"]
    identity = bundle["ledger_identity"]
    bindings = bundle["ledger_bindings"]
    assert isinstance(seed, dict)
    assert isinstance(identity, dict)
    assert isinstance(bindings, dict)
    seed["seed_sha256"] = stable_id(
        "frozen-ledger-seed/v0.2.2", _without(seed, "seed_sha256")
    )
    bindings["ledger_seed_sha256"] = seed["seed_sha256"]
    bindings["policy_bundle_sha256"] = seed["policy_bindings"][  # type: ignore[index]
        "policy_bundle_sha256"
    ]
    original_scope = bundle["bundle_scope_id"]
    bundle["bundle_scope_id"] = stable_id(
        "canonical-synthetic-bundle-scope/v0.2.2",
        {
            "ledger_identity": identity,
            "ledger_seed_sha256": seed["seed_sha256"],
            "policy_bundle_sha256": bindings["policy_bundle_sha256"],
        },
    )
    if bundle["bundle_scope_id"] != original_scope:
        assert not bundle["event_array"], "test resealer cannot rewrite causal event IDs"
    artifacts = bundle["artifacts"]
    events = bundle["event_array"]
    coverage = bundle["coverage"]
    assert isinstance(artifacts, list)
    assert isinstance(events, list)
    assert isinstance(coverage, dict)
    artifacts.sort(key=lambda item: str(item["artifact_id"]))
    event_set = stable_id("canonical-synthetic-event-set/v0.2.2", events)
    artifact_set = stable_id(
        "canonical-synthetic-artifact-set/v0.2.2", artifacts
    )
    bundle["event_set_sha256"] = event_set
    coverage["event_count"] = len(events)
    coverage["artifact_count"] = len(artifacts)
    coverage["event_set_sha256"] = event_set
    coverage["artifact_set_sha256"] = artifact_set
    coverage["coverage_sha256"] = stable_id(
        "canonical-synthetic-coverage/v0.2.2",
        _without(coverage, "coverage_sha256"),
    )
    bundle["bundle_sha256"] = stable_id(
        "canonical-synthetic-event-bundle/v0.2.2",
        _without(bundle, "bundle_sha256"),
    )


def _coverage_seal_payload(
    *,
    gaps: list[dict[str, object]],
    complete: bool,
    window_start_us: int = ANCHOR_US,
    window_end_us: int = ANCHOR_US + 1_000_000,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2",
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
        "source_id": "synthetic-book",
        "source_schema_version": "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
        "covered_object_kind": "BOOK_SNAPSHOT",
        "window_start_exclusive_us": window_start_us,
        "window_end_inclusive_us": window_end_us,
        "lane_available_at_us": window_end_us,
        "generation_ranges": [],
        "covered_event_ids": [],
        "covered_event_set_sha256": ZERO_SHA,
        "event_count": 0,
        "observed_gap_intervals": gaps,
        "complete": complete,
        "seal_sha256": ZERO_SHA,
    }
    payload["covered_event_set_sha256"] = stable_id(
        "coverage-covered-event-set/v0.2.2",
        {
            "venue_id": payload["venue_id"],
            "instrument_id": payload["instrument_id"],
            "lane_id": payload["lane_id"],
            "availability_kind": payload["availability_kind"],
            "source_id": payload["source_id"],
            "source_schema_version": payload["source_schema_version"],
            "covered_object_kind": payload["covered_object_kind"],
            "window_start_exclusive_us": window_start_us,
            "window_end_inclusive_us": window_end_us,
            "covered_event_ids": [],
        },
    )
    payload["seal_sha256"] = stable_id(
        "source-coverage-seal/v0.2.2", _without(payload, "seal_sha256")
    )
    return payload


def _account_payload(*, venue_id: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
        "account_scope_id": "other-account",
        "venue_id": venue_id,
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
        "source_id": "synthetic-account-source",
        "effective_at_us": ANCHOR_US,
        "lane_available_at_us": ANCHOR_US,
        "equity_usdt": "1000",
        "available_balance_usdt": "1000",
        "existing_initial_margin_usdt": "0",
        "open_order_reserve_usdt": "0",
        "pending_fee_reserve_usdt": "0",
        "position_qty_base": "0",
        "position_vwap": None,
        "open_order_ids": [],
        "quality": "VALID",
        "payload_sha256": ZERO_SHA,
        "snapshot_id": ZERO_SHA,
    }
    payload["payload_sha256"] = sha256_json(
        _without(payload, "payload_sha256", "snapshot_id")
    )
    payload["snapshot_id"] = stable_id(
        "account-risk-snapshot/v0.2.2",
        _without(payload, "snapshot_id"),
    )
    return payload


def _fixture_manifest_payload(
    diagnostic_artifact_ids: list[str],
    source_artifact_ids: list[str] | None = None,
) -> dict[str, object]:
    scope = {
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
    }
    schemas = {
        "closed_mark_bar_15m": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        "closed_mark_bar_4h": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        "book": "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
        "agg_trade": "rsi-mtf-drl-pm.agg-trade.v0.2.2",
        "open_interest": "rsi-mtf-drl-pm.open-interest.v0.2.2",
    }
    source_queries: dict[str, object] = {
        key: {
            **scope,
            "source_id": f"synthetic-{key}",
            "source_schema_version": schema,
        }
        for key, schema in schemas.items()
    }
    source_queries["account"] = {
        "account_scope_id": "synthetic-account",
        **scope,
        "source_id": "synthetic-account-source",
        "source_schema_version": "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
    }
    generator_policy: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.synthetic-fixture-generator-policy.v0.2.2",
        "composite_theory_id": COMPOSITE_THEORY_ID,
        "generator_kind": "DETERMINISTIC_HAND_AUTHORED_E0_FIXTURE",
        "randomness_rule": "FORBIDDEN",
        "wall_clock_rule": "FORBIDDEN",
        "outcome_access_rule": "DECISION_INPUTS_CAUSAL_ONLY_FUTURE_EVENTS_PREDECLARED_NOT_READ",
        "source_schema_versions": [
            "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
            "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
            "rsi-mtf-drl-pm.agg-trade.v0.2.2",
            "rsi-mtf-drl-pm.open-interest.v0.2.2",
            "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2",
            "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2",
            "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
            "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2",
            "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2",
        ],
        "policy_sha256": ZERO_SHA,
    }
    generator_policy["policy_sha256"] = stable_id(
        "synthetic-fixture-generator-policy/v0.2.2",
        _without(generator_policy, "policy_sha256"),
    )
    source_ids = sorted(source_artifact_ids or [])
    diagnostic_ids = sorted(diagnostic_artifact_ids)
    payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.synthetic-fixture-manifest.v0.2.2",
        "composite_theory_id": COMPOSITE_THEORY_ID,
        "role": "SYNTHETIC",
        **scope,
        "generator_policy": generator_policy,
        "generator_policy_sha256": generator_policy["policy_sha256"],
        "source_queries": source_queries,
        "source_artifact_ids": source_ids,
        "diagnostic_artifact_ids": diagnostic_ids,
        "source_artifact_set_sha256": ZERO_SHA,
        "manifest_sha256": ZERO_SHA,
    }
    payload["source_artifact_set_sha256"] = stable_id(
        "synthetic-fixture-artifact-set/v0.2.2",
        {
            **scope,
            "source_queries": source_queries,
            "source_artifact_ids": source_ids,
            "diagnostic_artifact_ids": diagnostic_ids,
        },
    )
    payload["manifest_sha256"] = stable_id(
        "synthetic-fixture-manifest/v0.2.2",
        _without(payload, "manifest_sha256"),
    )
    return payload


def _closed_bar_payload(*, closed_at_us: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
        "source_id": "synthetic-bars",
        "stream_generation_id": _id("bar-generation"),
        "period_seconds": 900,
        "bar_open_at_us": 0,
        "bar_close_at_us": 900_000_000,
        "closed_at_us": closed_at_us,
        "lane_available_at_us": 900_000_000,
        "close_price": "100",
        "source_sequence": 0,
        "quality": "VALID",
        "payload_sha256": ZERO_SHA,
        "stable_bar_id": ZERO_SHA,
    }
    payload["payload_sha256"] = sha256_json(
        _without(payload, "payload_sha256", "stable_bar_id")
    )
    payload["stable_bar_id"] = stable_id(
        "closed-mark-bar/v0.2.2", _without(payload, "stable_bar_id")
    )
    return payload


def _cross_scope_diagnostic_bundle(
    contract: dict[str, object],
    *,
    reason_code: str = "SNAPSHOT_SCOPE_MISMATCH",
    inject_authority_use: bool = False,
) -> tuple[dict[str, object], int]:
    bundle, as_of_us = _bundle(contract, control_id="C1")
    identity = bundle["ledger_identity"]
    assert isinstance(identity, dict)
    account_payload = _account_payload(venue_id="OTHER")
    account_scope = stable_id(
        "synthetic-artifact-scope/v0.2.2",
        {
            key: account_payload[key]
            for key in (
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
            )
        },
    )
    account_wrapper = _wrapper(
        "ACCOUNT_RISK_SNAPSHOT",
        account_payload,
        account_scope,
        ANCHOR_US,
    )
    manifest = _fixture_manifest_payload(
        [str(account_wrapper["artifact_id"])]
    )
    manifest_wrapper = _wrapper(
        "SYNTHETIC_FIXTURE_MANIFEST",
        manifest,
        stable_id(
            "synthetic-artifact-scope/v0.2.2",
            {
                key: manifest[key]
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                )
            },
        ),
        None,
    )
    artifacts = bundle["artifacts"]
    assert isinstance(artifacts, list)
    artifacts.extend((account_wrapper, manifest_wrapper))
    payload = {
        "reason_code": reason_code,
        "details_sha256": _id("scope-mismatch-details"),
        "observed_position_qty": None,
        "observed_position_vwap": None,
        "snapshot_id": None,
        "account_scope_id": None,
    }
    bundle["event_array"] = [
        _event(
            identity,
            str(bundle["bundle_scope_id"]),
            event_kind="ACCOUNT_MISMATCH",
            event_time_us=as_of_us,
            priority_rank=1,
            source_sequence=0,
            payload=payload,
            artifact_ids=[str(account_wrapper["artifact_id"])],
        )
    ]
    if inject_authority_use:
        bundle["entry_execution_binding"] = {
            "diagnostic_snapshot_artifact_id": account_wrapper["artifact_id"]
        }
    _reseal_bundle(bundle)
    return bundle, as_of_us


def _sealed_policy(
    schema_version: str,
    domain: str,
    **fields: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        **fields,
        "policy_sha256": ZERO_SHA,
    }
    payload["policy_sha256"] = stable_id(
        domain, _without(payload, "policy_sha256")
    )
    return payload


def _policy_registry_payload() -> dict[str, object]:
    parameter_set: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.parameter-set.v0.2.2",
        "variant_kind": "BASELINE",
        "challenged_key": None,
        "adverse_pressure_min_consecutive_seconds": 5,
        "k_threshold": "1.5",
        "abs_d_threshold": "0.1",
        "r_threshold": "0.6",
        "l_upper_threshold": "-0.0005",
        "responding_bps": "5",
        "u_active_seconds": 1800,
        "u_cooldown_seconds": 900,
        "ev_min_n": 30,
        "synthetic_barrier_ack_latency_seconds": 1,
        "parameter_set_sha256": ZERO_SHA,
    }
    parameter_set["parameter_set_sha256"] = stable_id(
        "candidate-parameter-set/v0.2.2",
        _without(parameter_set, "parameter_set_sha256"),
    )
    common = {
        "composite_theory_id": COMPOSITE_THEORY_ID,
        "parameter_set_sha256": parameter_set["parameter_set_sha256"],
        "stage_role": "SYNTHETIC",
    }
    u_policy = _sealed_policy(
        "rsi-mtf-drl-pm.u-policy.v0.2.2",
        "u-policy/v0.2.2",
        **common,
        v0_2_controls_sha256=(
            "80f0c203f7ce02ffc5ef65c9a85e541e8bacdcbb44c8e7e34f33fa4e07e7d436"
        ),
        partition_rule="UTC_HALF_OPEN_CYCLES_FROM_UNIX_EPOCH",
        master_selection_rule="FIRST_VALID_GATE_NEUTRAL_U_ON_CLOSED_15M_GRID",
        dedup_rule="ONE_MASTER_OPPORTUNITY_PER_CYCLE",
        cooldown_rule="SUPPRESS_NEW_MASTER_UNTIL_MASTER_PLUS_ACTIVE_PLUS_COOLDOWN",
        u_active_seconds=1800,
        u_cooldown_seconds=900,
    )
    source_selector_policy = _sealed_policy(
        "rsi-mtf-drl-pm.source-selector-policy.v0.2.2",
        "source-selector-policy/v0.2.2",
        book_selector="MAX_EVENT_TIME_THEN_MIN_LANE_SEQUENCE_ID",
        open_interest_selector="MAX_EVENT_TIME_THEN_MIN_LANE_SEQUENCE_ID",
        venue_selector="MAX_EFFECTIVE_THEN_FINGERPRINT_CONFLICT_ELSE_MIN_ID",
        account_selector="MAX_EFFECTIVE_THEN_PAYLOAD_CONFLICT_ELSE_MIN_ID",
        bar_selector="EXACT_SLOT_SINGLETON",
        trade_window_selector="EXACT_COVERED_EVENT_SET",
        grid_rule="UTC_ONE_SECOND_SELECT_BOOK_AGE_LE_ONE_SECOND",
        coverage_rule="ONE_EXPLICIT_COMPLETE_V0_2_2_SEAL_NO_LEX_FALLBACK",
    )
    entry_policy = _sealed_policy(
        "rsi-mtf-drl-pm.entry-policy.v0.2.2",
        "entry-policy/v0.2.2",
        **common,
        v0_2_entry_contract_sha256=(
            "fef9822cc1cc504ac8bc93b8f6f7a9bc951f658549508bba9c215d36e46f47e0"
        ),
        formula_scope="V0_2_1_SECTIONS_3_TO_8_AS_OVERRIDDEN_BY_V0_2_2",
        source_selector_policy_sha256=source_selector_policy["policy_sha256"],
        decision_proof_required=True,
    )
    exit_policy = _sealed_policy(
        "rsi-mtf-drl-pm.exit-policy-template.v0.2.2",
        "exit-policy-template/v0.2.2",
        **common,
        formula_scope="V0_2_1_SECTIONS_9_10_12_AS_OVERRIDDEN_BY_V0_2_2",
        pi_exit_policy_sha256=_id("pi-exit-policy"),
        reducer_priority_policy_sha256=_priority_policy()["policy_sha256"],
        source_selector_policy_sha256=source_selector_policy["policy_sha256"],
    )
    cost_policy = _sealed_policy(
        "rsi-mtf-drl-pm.cost-policy.v0.2.2",
        "cost-policy/v0.2.2",
        **common,
        v0_2_risk_execution_contract_sha256=(
            "77db59ac12a17ae650457751523f459e3cbe0adad8bed465480d442e79332b36"
        ),
        fee_bps_per_side="5",
        worst_slippage_bps_per_side="10",
        funding_buffer_bps="5",
        tail_bps="10",
        accounting_rule="V0_2_1_SECTION_8_AND_11_CURRENT_INVENTORY_BASIS_NO_DOUBLE_COUNT",
    )
    risk_policy = _sealed_policy(
        "rsi-mtf-drl-pm.risk-policy.v0.2.2",
        "risk-policy/v0.2.2",
        **common,
        v0_2_risk_execution_contract_sha256=(
            "77db59ac12a17ae650457751523f459e3cbe0adad8bed465480d442e79332b36"
        ),
        risk_formula_scope="V0_2_1_SECTIONS_8_9_11_AS_OVERRIDDEN_BY_V0_2_2",
        pending_deadline_seconds=2,
        rule_snapshot_change_action="PRE_SUBMIT_ABSTAIN_POST_SUBMIT_DATA_HEALTH_INVALID",
    )
    label_policy = _sealed_policy(
        "rsi-mtf-drl-pm.label-policy-binding.v0.2.2",
        "label-policy-binding/v0.2.2",
        **common,
        v0_2_label_contract_sha256=(
            "7171baca5be3047494a91c9e2292c786cfe1a28aea9db1b7d1f2b6e3f5c68019"
        ),
        first_hit_label_policy_sha256=_id("first-hit-label-policy"),
        label_scope="V0_2_1_SECTION_12_5_AS_OVERRIDDEN_BY_V0_2_2",
    )
    data_role_policy = _sealed_policy(
        "rsi-mtf-drl-pm.data-role-policy.v0.2.2",
        "data-role-policy/v0.2.2",
        **common,
        allowed_ledger_roles=["SYNTHETIC"],
        allowed_evidence_roles=["SYNTHETIC"],
        allowed_availability_kinds=["SYNTHETIC"],
        required_lane_id=LANE,
        fixture_manifest_required=True,
        real_source_adapter_authorized=False,
    )
    estimator_policy = _sealed_policy(
        "rsi-mtf-drl-pm.estimator-policy.v0.2.2",
        "estimator-policy/v0.2.2",
        **common,
        estimator_kind="HOEFFDING_SUPPORT_WIDTH_4_ONE_SIDED_95_LCB",
        lcb_confidence="0.95",
        minimum_n=30,
        y_r_lower="-1",
        y_r_upper="3",
        sample_window_rule="EXACT_MATCH_BUCKET_EXPANDING_PAST_ONLY",
        chronology_rule="TERMINAL_PLUS_LABEL_TAIL_NOT_AFTER_SAMPLE_END",
    )
    policy_bundle: dict[str, object] = {
        "u_policy_sha256": u_policy["policy_sha256"],
        "entry_policy_sha256": entry_policy["policy_sha256"],
        "exit_policy_template_sha256": exit_policy["policy_sha256"],
        "cost_policy_sha256": cost_policy["policy_sha256"],
        "risk_policy_sha256": risk_policy["policy_sha256"],
        "label_policy_sha256": label_policy["policy_sha256"],
        "data_role_sha256": data_role_policy["policy_sha256"],
        "estimator_policy_sha256": estimator_policy["policy_sha256"],
        "policy_bundle_sha256": ZERO_SHA,
    }
    policy_bundle["policy_bundle_sha256"] = stable_id(
        "candidate-policy-bundle/v0.2.2",
        _without(policy_bundle, "policy_bundle_sha256"),
    )
    candidate_id = stable_id(
        "rsi-mtf-drl-pm-candidate/v0.2.2",
        {
            "composite_theory_id": COMPOSITE_THEORY_ID,
            "parameter_set_sha256": parameter_set["parameter_set_sha256"],
            "policy_bundle_sha256": policy_bundle["policy_bundle_sha256"],
        },
    )
    registry: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.policy-registry.v0.2.2",
        "composite_theory_id": COMPOSITE_THEORY_ID,
        "v0_2_controls_sha256": (
            "80f0c203f7ce02ffc5ef65c9a85e541e8bacdcbb44c8e7e34f33fa4e07e7d436"
        ),
        "v0_2_entry_contract_sha256": (
            "fef9822cc1cc504ac8bc93b8f6f7a9bc951f658549508bba9c215d36e46f47e0"
        ),
        "v0_2_risk_execution_contract_sha256": (
            "77db59ac12a17ae650457751523f459e3cbe0adad8bed465480d442e79332b36"
        ),
        "v0_2_label_contract_sha256": (
            "7171baca5be3047494a91c9e2292c786cfe1a28aea9db1b7d1f2b6e3f5c68019"
        ),
        "parameter_set": parameter_set,
        "u_policy": u_policy,
        "entry_policy": entry_policy,
        "exit_policy_template": exit_policy,
        "cost_policy": cost_policy,
        "risk_policy": risk_policy,
        "label_policy": label_policy,
        "data_role_policy": data_role_policy,
        "estimator_policy": estimator_policy,
        "source_selector_policy": source_selector_policy,
        "policy_bundle": policy_bundle,
        "candidate_id": candidate_id,
        "registry_sha256": ZERO_SHA,
    }
    registry["registry_sha256"] = stable_id(
        "policy-registry/v0.2.2",
        _without(registry, "registry_sha256"),
    )
    return registry


def _decision_binding(
    *,
    decision_at_us: int = ANCHOR_US,
    reason_code: str = "ANCHOR_UNKNOWN",
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    scope = {
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
    }
    scope_id = stable_id("synthetic-artifact-scope/v0.2.2", scope)
    registry = _policy_registry_payload()
    registry_wrapper = _wrapper("POLICY_REGISTRY", registry, None, None)
    policy_bundle = registry["policy_bundle"]
    assert isinstance(policy_bundle, dict)
    u_policy = registry["u_policy"]
    assert isinstance(u_policy, dict)
    grid_close_us = decision_at_us - (decision_at_us % 900_000_000)
    bar_payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        **scope,
        "source_id": "synthetic-closed_mark_bar_15m",
        "stream_generation_id": _id("decision-bar-generation"),
        "period_seconds": 900,
        "bar_open_at_us": grid_close_us - 900_000_000,
        "bar_close_at_us": grid_close_us,
        "closed_at_us": grid_close_us,
        "lane_available_at_us": grid_close_us,
        "close_price": "100",
        "source_sequence": 0,
        "quality": "VALID",
        "payload_sha256": ZERO_SHA,
        "stable_bar_id": ZERO_SHA,
    }
    bar_payload["payload_sha256"] = sha256_json(
        _without(bar_payload, "payload_sha256", "stable_bar_id")
    )
    bar_payload["stable_bar_id"] = stable_id(
        "closed-mark-bar/v0.2.2",
        _without(bar_payload, "stable_bar_id"),
    )
    bar_wrapper = _wrapper(
        "CLOSED_MARK_BAR", bar_payload, scope_id, grid_close_us
    )
    cycle_start_us = grid_close_us
    opportunity_id = stable_id(
        "master-opportunity/v0.2.2",
        {
            "u_policy_sha256": u_policy["policy_sha256"],
            "venue_id": "SYNTH",
            "instrument_id": "BTCUSDT",
            "lane_id": LANE,
            "availability_kind": "SYNTHETIC",
            "role": "SYNTHETIC",
            "cycle_start_us": cycle_start_us,
        },
    )
    master_payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2",
        "event_kind": "MASTER_CREATED",
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "role": "SYNTHETIC",
        "cycle_start_us": cycle_start_us,
        "grid_close_us": grid_close_us,
        "evaluation_at_us": decision_at_us,
        "master_opportunity_id": opportunity_id,
        "parent_master_receipt_id": None,
        "u_policy_sha256": u_policy["policy_sha256"],
        "input_bar_id": bar_wrapper["artifact_id"],
        "receipt_sha256": ZERO_SHA,
    }
    master_payload["receipt_sha256"] = stable_id(
        "u-observation-receipt/v0.2.2",
        _without(master_payload, "receipt_sha256"),
    )
    master_wrapper = _wrapper(
        "U_OBSERVATION_RECEIPT",
        master_payload,
        scope_id,
        decision_at_us,
    )
    manifest = _fixture_manifest_payload(
        [],
        [
            str(bar_wrapper["artifact_id"]),
            str(master_wrapper["artifact_id"]),
        ],
    )
    manifest_wrapper = _wrapper(
        "SYNTHETIC_FIXTURE_MANIFEST", manifest, scope_id, None
    )
    levels = {
        "anchor": None,
        "p_limit": None,
        "i0": None,
        "g0": None,
        "s0": None,
        "t0": None,
        "h0_us": None,
        "tcap": None,
    }
    risk = {
        "submitted_qty": "0",
        "r_unit_usdt": "0",
        "r_episode_max_usdt": "0",
        "pending_existing_at_action_usdt": "0",
    }
    result = {
        "decision_kind": "ABSTAIN",
        "action_at_us": decision_at_us,
        "reason_code": reason_code,
        "initial_levels": levels,
        "risk_basis": risk,
    }
    named = {
        "anchor_venue_snapshot_artifact_id": None,
        "action_venue_snapshot_artifact_id": None,
        "anchor_account_snapshot_artifact_id": None,
        "action_account_snapshot_artifact_id": None,
        "submit_ev_evidence_artifact_id": None,
        "master_u_receipt_artifact_id": master_wrapper["artifact_id"],
        "policy_registry_artifact_id": registry_wrapper["artifact_id"],
        "fixture_manifest_artifact_id": manifest_wrapper["artifact_id"],
    }
    selectors = {
        "anchor_account_max_age_us": 1_000_000,
        "action_account_max_age_us": 1_000_000,
        "submit_ev_selection_key_sha256": None,
    }
    source_ids = sorted(
        [
            str(bar_wrapper["artifact_id"]),
            str(master_wrapper["artifact_id"]),
            str(registry_wrapper["artifact_id"]),
            str(manifest_wrapper["artifact_id"]),
        ]
    )
    binding: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.decision-input-binding.v0.2.2",
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
        "opportunity_id": opportunity_id,
        "control_id": "C1",
        "side": "LONG",
        "candidate_id": registry["candidate_id"],
        "decision_kind": "ABSTAIN",
        "decision_at_us": decision_at_us,
        "named_artifact_bindings": named,
        "selector_bindings": selectors,
        "source_artifact_ids": source_ids,
        "source_artifact_set_sha256": ZERO_SHA,
        "calculator_policy_bundle_sha256": policy_bundle["policy_bundle_sha256"],
        "decision_result_sha256": stable_id("decision-result/v0.2.2", result),
        "proof_sha256": ZERO_SHA,
    }
    binding["source_artifact_set_sha256"] = stable_id(
        "decision-source-artifact-set/v0.2.2",
        {
            **{
                key: binding[key]
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                    "opportunity_id",
                    "control_id",
                    "side",
                    "candidate_id",
                    "decision_at_us",
                )
            },
            "named_artifact_bindings": named,
            "selector_bindings": selectors,
            "source_artifact_ids": source_ids,
        },
    )
    binding["proof_sha256"] = stable_id(
        "decision-input-binding/v0.2.2",
        _without(binding, "proof_sha256"),
    )
    catalog = {
        "artifacts": sorted(
            [bar_wrapper, master_wrapper, registry_wrapper, manifest_wrapper],
            key=lambda item: str(item["artifact_id"]),
        )
    }
    return binding, result, catalog


def _seal_decision_binding(binding: dict[str, object]) -> None:
    named = binding["named_artifact_bindings"]
    selectors = binding["selector_bindings"]
    source_ids = binding["source_artifact_ids"]
    assert isinstance(named, dict)
    assert isinstance(selectors, dict)
    assert isinstance(source_ids, list)
    binding["source_artifact_set_sha256"] = stable_id(
        "decision-source-artifact-set/v0.2.2",
        {
            **{
                key: binding[key]
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                    "opportunity_id",
                    "control_id",
                    "side",
                    "candidate_id",
                    "decision_at_us",
                )
            },
            "named_artifact_bindings": named,
            "selector_bindings": selectors,
            "source_artifact_ids": source_ids,
        },
    )
    binding["proof_sha256"] = stable_id(
        "decision-input-binding/v0.2.2",
        _without(binding, "proof_sha256"),
    )


def _extend_decision_fixture(
    binding: dict[str, object],
    catalog: dict[str, object],
    extra_source_wrappers: list[dict[str, object]],
) -> None:
    artifacts = catalog["artifacts"]
    named = binding["named_artifact_bindings"]
    assert isinstance(artifacts, list)
    assert isinstance(named, dict)
    old_manifest_id = named["fixture_manifest_artifact_id"]
    old_manifest_wrapper = next(
        item
        for item in artifacts
        if item["artifact_id"] == old_manifest_id
    )
    old_manifest = old_manifest_wrapper["payload"]
    assert isinstance(old_manifest, dict)
    registry_id = named["policy_registry_artifact_id"]
    fixture_source_ids = [
        str(item["artifact_id"])
        for item in artifacts
        if item["artifact_id"] not in (registry_id, old_manifest_id)
    ]
    fixture_source_ids.extend(
        str(item["artifact_id"]) for item in extra_source_wrappers
    )
    manifest = _fixture_manifest_payload([], fixture_source_ids)
    scope_id = stable_id(
        "synthetic-artifact-scope/v0.2.2",
        {
            key: manifest[key]
            for key in (
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
            )
        },
    )
    manifest_wrapper = _wrapper(
        "SYNTHETIC_FIXTURE_MANIFEST", manifest, scope_id, None
    )
    artifacts[:] = [
        item for item in artifacts if item["artifact_id"] != old_manifest_id
    ]
    artifacts.extend(extra_source_wrappers)
    artifacts.append(manifest_wrapper)
    artifacts.sort(key=lambda item: str(item["artifact_id"]))
    named["fixture_manifest_artifact_id"] = manifest_wrapper["artifact_id"]
    binding["source_artifact_ids"] = sorted(
        str(item["artifact_id"]) for item in artifacts
    )
    _seal_decision_binding(binding)


def _oi_chain(*, complete: bool) -> list[dict[str, object]]:
    scope = {
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
    }
    scope_id = stable_id("synthetic-artifact-scope/v0.2.2", scope)
    generation_id = _id("decision-oi-generation")
    wrappers: list[dict[str, object]] = []
    for sequence, (event_time_us, oi_base) in enumerate(
        (
            (ANCHOR_US - 959_999_999, "100"),
            (ANCHOR_US, "101"),
        )
    ):
        payload: dict[str, object] = {
            "schema_version": "rsi-mtf-drl-pm.open-interest.v0.2.2",
            **scope,
            "source_id": "synthetic-open_interest",
            "stream_generation_id": generation_id,
            "event_time_us": event_time_us,
            "lane_available_at_us": event_time_us,
            "source_sequence": sequence,
            "oi_base": oi_base,
            "quality": "VALID",
            "payload_sha256": ZERO_SHA,
            "event_id": ZERO_SHA,
        }
        payload["payload_sha256"] = sha256_json(
            _without(payload, "payload_sha256", "event_id")
        )
        payload["event_id"] = stable_id(
            "open-interest/v0.2.2", _without(payload, "event_id")
        )
        wrappers.append(
            _wrapper(
                "OPEN_INTEREST",
                payload,
                scope_id,
                event_time_us,
            )
        )
    event_ids = [
        str(wrapper["payload"]["event_id"])  # type: ignore[index]
        for wrapper in wrappers
    ]
    gaps = (
        []
        if complete
        else [
            {
                "start_exclusive_us": ANCHOR_US - 500_000_000,
                "end_inclusive_us": ANCHOR_US - 499_000_000,
                "reason": "CONNECTION_GAP",
            }
        ]
    )
    seal: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2",
        **scope,
        "source_id": "synthetic-open_interest",
        "source_schema_version": "rsi-mtf-drl-pm.open-interest.v0.2.2",
        "covered_object_kind": "OPEN_INTEREST",
        "window_start_exclusive_us": ANCHOR_US - 960_000_000,
        "window_end_inclusive_us": ANCHOR_US,
        "lane_available_at_us": ANCHOR_US,
        "generation_ranges": [
            {
                "generation_id": generation_id,
                "first_source_sequence": 0,
                "last_source_sequence": 1,
                "event_count": 2,
            }
        ],
        "covered_event_ids": event_ids,
        "covered_event_set_sha256": ZERO_SHA,
        "event_count": 2,
        "observed_gap_intervals": gaps,
        "complete": complete,
        "seal_sha256": ZERO_SHA,
    }
    seal["covered_event_set_sha256"] = stable_id(
        "coverage-covered-event-set/v0.2.2",
        {
            **scope,
            "source_id": seal["source_id"],
            "source_schema_version": seal["source_schema_version"],
            "covered_object_kind": seal["covered_object_kind"],
            "window_start_exclusive_us": seal["window_start_exclusive_us"],
            "window_end_inclusive_us": seal["window_end_inclusive_us"],
            "covered_event_ids": event_ids,
        },
    )
    seal["seal_sha256"] = stable_id(
        "source-coverage-seal/v0.2.2",
        _without(seal, "seal_sha256"),
    )
    wrappers.append(
        _wrapper(
            "SOURCE_COVERAGE_SEAL",
            seal,
            scope_id,
            ANCHOR_US,
        )
    )
    return wrappers


def _venue_wrapper() -> dict[str, object]:
    scope = {
        "venue_id": "SYNTH",
        "instrument_id": "BTCUSDT",
        "lane_id": LANE,
        "availability_kind": "SYNTHETIC",
    }
    payload: dict[str, object] = {
        "schema_version": "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2",
        **scope,
        "contract_kind": "LINEAR_USDT_PERPETUAL",
        "effective_at_us": ANCHOR_US,
        "lane_available_at_us": ANCHOR_US,
        "tick_size": "0.1",
        "lot_step": "0.001",
        "min_qty": "0.001",
        "max_qty": "1000",
        "min_notional_usdt": "5",
        "max_notional_usdt": "1000000",
        "max_leverage": "20",
        "initial_margin_rate": "0.05",
        "fee_bps_per_side": "5",
        "rule_fingerprint_sha256": ZERO_SHA,
        "quality": "VALID",
        "payload_sha256": ZERO_SHA,
        "snapshot_id": ZERO_SHA,
    }
    payload["rule_fingerprint_sha256"] = stable_id(
        "venue-rule-fingerprint/v0.2.2",
        {
            key: payload[key]
            for key in (
                "contract_kind",
                "tick_size",
                "lot_step",
                "min_qty",
                "max_qty",
                "min_notional_usdt",
                "max_notional_usdt",
                "max_leverage",
                "initial_margin_rate",
                "fee_bps_per_side",
            )
        },
    )
    payload["payload_sha256"] = sha256_json(
        _without(payload, "payload_sha256", "snapshot_id")
    )
    payload["snapshot_id"] = stable_id(
        "venue-instrument-snapshot/v0.2.2",
        _without(payload, "snapshot_id"),
    )
    return _wrapper(
        "VENUE_INSTRUMENT_SNAPSHOT",
        payload,
        stable_id("synthetic-artifact-scope/v0.2.2", scope),
        ANCHOR_US,
    )


class KernelB2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_bytes())

    def assert_kernel_error(self, code: str, callable_: object) -> None:
        assert callable(callable_)
        with self.assertRaises(KernelValidationError) as caught:
            callable_()  # type: ignore[operator]
        self.assertEqual(caught.exception.error_code, code)
        self.assertEqual(caught.exception.args, (code,))
        self.assertIsNone(caught.exception.__cause__)

    def test_c0_validate_reduce_encode_label_is_deterministic_and_immutable(self) -> None:
        bundle, as_of_us = _bundle(self.contract)
        outcome = validate_bundle(
            self.contract, bundle, as_of_us, "SYNTHETIC"
        )
        self.assertIsInstance(outcome, ValidatedBundle)
        assert isinstance(outcome, ValidatedBundle)
        self.assertIsInstance(outcome.bundle, FrozenMapping)
        with self.assertRaises((AttributeError, TypeError)):
            outcome.bundle["bundle_sha256"] = ZERO_SHA  # type: ignore[index]
        trace_a = reduce_event_array(
            self.contract, outcome, as_of_us, "SYNTHETIC"
        )
        trace_b = reduce_event_array(
            self.contract, outcome, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(canonical_json(trace_a), canonical_json(trace_b))
        self.assertEqual(len(trace_a), 1)
        self.assertEqual(trace_a[0]["event_kind"], "GENESIS")
        encoded = encode_ledger(
            self.contract, trace_a[0], as_of_us, "SYNTHETIC"
        )
        self.assertEqual(encoded, canonical_json(trace_a[0]))
        label = first_hit_label(
            self.contract, outcome, trace_a, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(label["control_id"], "C0")
        self.assertEqual(label["submission_label"], "NO_ACTION")
        self.assertEqual(label["observation_status"], "NOT_APPLICABLE")
        self.assertIsNone(label["terminal_event_id"])

    def test_non_c0_pre_submit_fatal_closes_and_copies_code_binding(self) -> None:
        code_sha = _id("non-c0-code")
        bundle, as_of_us = _bundle(
            self.contract, control_id="C1", code_sha256=code_sha
        )
        outcome = validate_bundle(
            self.contract, bundle, as_of_us, "SYNTHETIC"
        )
        self.assertIsInstance(outcome, ValidatedBundle)
        assert isinstance(outcome, ValidatedBundle)
        trace = reduce_event_array(
            self.contract, outcome, as_of_us, "SYNTHETIC"
        )
        self.assertEqual([record["event_kind"] for record in trace], ["GENESIS", "KILL"])
        self.assertEqual(trace[-1]["state_after"], "CLOSED")
        self.assertTrue(
            all(record["bindings"]["code_sha256"] == code_sha for record in trace)
        )
        label = first_hit_label(
            self.contract, outcome, trace, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(label["control_id"], "C1")
        self.assertEqual(label["submission_label"], "NO_ACTION")
        entry_sha = stable_id(
            "no-entry-execution/v0.2.2",
            {
                "opportunity_id": bundle["ledger_identity"]["opportunity_id"],  # type: ignore[index]
                "control_id": "C1",
            },
        )
        label_bindings = _label_bindings(outcome.bundle, trace, entry_sha)
        self.assertEqual(label_bindings["code_sha256"], code_sha)

    def test_abstain_decision_is_recomputed_from_digest(self) -> None:
        binding, expected, catalog = _decision_binding()
        actual = calculate_decision(
            self.contract,
            binding,
            catalog,
            ANCHOR_US,
            "SYNTHETIC",
        )
        self.assertEqual(materialize(actual), expected)
        tampered = copy.deepcopy(binding)
        tampered["decision_result_sha256"] = _id("not-a-result")
        tampered["proof_sha256"] = stable_id(
            "decision-input-binding/v0.2.2",
            _without(tampered, "proof_sha256"),
        )
        self.assert_kernel_error(
            "E_KERNEL_BINDING_INVALID",
            lambda: calculate_decision(
                self.contract,
                tampered,
                catalog,
                ANCHOR_US,
                "SYNTHETIC",
            ),
        )

    def test_c11_requires_exact_oi_window_endpoints_and_complete_seal(self) -> None:
        binding, expected, catalog = _decision_binding()
        _extend_decision_fixture(binding, catalog, _oi_chain(complete=True))
        self.assertEqual(
            materialize(
                calculate_decision(
                    self.contract,
                    binding,
                    catalog,
                    ANCHOR_US,
                    "SYNTHETIC",
                )
            ),
            expected,
        )
        gap_binding, _, gap_catalog = _decision_binding()
        _extend_decision_fixture(
            gap_binding, gap_catalog, _oi_chain(complete=False)
        )
        self.assert_kernel_error(
            "E_C11_OI_SEAL_INCOMPLETE",
            lambda: calculate_decision(
                self.contract,
                gap_binding,
                gap_catalog,
                ANCHOR_US,
                "SYNTHETIC",
            ),
        )

    def test_public_failure_carriers_and_fail_first_order(self) -> None:
        bundle, as_of_us = _bundle(self.contract)
        bad_contract = copy.deepcopy(self.contract)
        bad_contract["contract_id"] = "wrong"
        failure = validate_bundle(
            bad_contract, bundle, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(
            materialize(failure),
            {"status": "INVALID", "error_code": "E_KERNEL_CONTRACT_INVALID"},
        )
        self.assertIsInstance(failure, BundleValidationFailure)
        invalid_role = validate_bundle(
            self.contract, bundle, as_of_us, "DEVELOPMENT"
        )
        self.assertEqual(
            invalid_role.error_code, "E_C18_ROLE_NOT_SYNTHETIC"
        )
        binding, _, catalog = _decision_binding()
        binding["extra"] = "forbidden"
        binding["proof_sha256"] = stable_id(
            "decision-input-binding/v0.2.2",
            _without(binding, "proof_sha256"),
        )
        self.assert_kernel_error(
            "E_C12_DECISION_PROOF_INVALID",
            lambda: calculate_decision(
                self.contract,
                binding,
                catalog,
                ANCHOR_US,
                "SYNTHETIC",
            ),
        )

    def test_validated_carrier_is_revalidated_not_nominally_trusted(self) -> None:
        bundle, as_of_us = _bundle(self.contract)
        outcome = validate_bundle(
            self.contract, bundle, as_of_us, "SYNTHETIC"
        )
        assert isinstance(outcome, ValidatedBundle)
        mutated = materialize(outcome.bundle)
        mutated["ledger_bindings"]["code_sha256"] = _id("tampered-code")
        frozen_mutated = freeze(mutated)
        assert isinstance(frozen_mutated, FrozenMapping)
        forged = ValidatedBundle(
            "VALID",
            frozen_mutated,
            outcome.bundle_sha256,
            as_of_us,
            "SYNTHETIC",
        )
        self.assert_kernel_error(
            "E_KERNEL_BINDING_INVALID",
            lambda: reduce_event_array(
                self.contract, forged, as_of_us, "SYNTHETIC"
            ),
        )

    def test_decimal34_canonical_family_and_json_no_float(self) -> None:
        accepted = ("0", "1", "-1", "0.01", "-0.01", "999999999999999999")
        rejected = ("-0", "+1", "01", "1.0", "1e2", "NaN", "Infinity", "")
        for value in accepted:
            self.assertTrue(validate_decimal("DecimalString", value), value)
        for value in rejected:
            self.assertFalse(validate_decimal("DecimalString", value), value)
        self.assertTrue(validate_decimal("Price", "0.0001"))
        self.assertFalse(validate_decimal("Price", "0"))
        with self.assertRaises(TypeError):
            canonical_json({"value": 1.0})
        self.assertEqual(
            canonical_json({"中文": "值", "a": 1}),
            '{"a":1,"中文":"值"}'.encode(),
        )

    def test_c03_gap_schema_order_window_and_overlap_are_closed(self) -> None:
        valid_gap = {
            "start_exclusive_us": ANCHOR_US,
            "end_inclusive_us": ANCHOR_US + 500_000,
            "reason": "IMPORT_GAP",
        }
        valid_payload = _coverage_seal_payload(
            gaps=[valid_gap], complete=False
        )
        self.assertTrue(_coverage_shape_valid(valid_payload))
        bundle, as_of_us = _bundle(self.contract, control_id="C1")
        scope_id = stable_id(
            "synthetic-artifact-scope/v0.2.2",
            {
                key: valid_payload[key]
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                )
            },
        )
        seal_wrapper = _wrapper(
            "SOURCE_COVERAGE_SEAL",
            valid_payload,
            scope_id,
            as_of_us,
        )
        bundle["artifacts"].append(seal_wrapper)  # type: ignore[union-attr]
        _reseal_bundle(bundle)
        self.assertIsInstance(
            validate_bundle(
                self.contract, bundle, as_of_us, "SYNTHETIC"
            ),
            ValidatedBundle,
        )
        invalid_gap_sets = (
            [{"junk": 1}],
            [
                {
                    "start_exclusive_us": ANCHOR_US + 500_000,
                    "end_inclusive_us": ANCHOR_US + 900_000,
                    "reason": "IMPORT_GAP",
                },
                {
                    "start_exclusive_us": ANCHOR_US,
                    "end_inclusive_us": ANCHOR_US + 100_000,
                    "reason": "CONNECTION_GAP",
                },
            ],
            [
                {
                    "start_exclusive_us": ANCHOR_US,
                    "end_inclusive_us": ANCHOR_US + 700_000,
                    "reason": "IMPORT_GAP",
                },
                {
                    "start_exclusive_us": ANCHOR_US + 600_000,
                    "end_inclusive_us": ANCHOR_US + 900_000,
                    "reason": "CONNECTION_GAP",
                },
            ],
            [
                {
                    "start_exclusive_us": ANCHOR_US - 1,
                    "end_inclusive_us": ANCHOR_US + 1,
                    "reason": "IMPORT_GAP",
                }
            ],
        )
        for gaps in invalid_gap_sets:
            with self.subTest(gaps=gaps):
                candidate = copy.deepcopy(bundle)
                bad_payload = _coverage_seal_payload(
                    gaps=gaps, complete=False
                )
                bad_wrapper = _wrapper(
                    "SOURCE_COVERAGE_SEAL",
                    bad_payload,
                    scope_id,
                    as_of_us,
                )
                candidate["artifacts"] = [
                    bad_wrapper
                    if item["schema_id"] == "SOURCE_COVERAGE_SEAL"
                    else item
                    for item in candidate["artifacts"]
                ]
                _reseal_bundle(candidate)
                outcome = validate_bundle(
                    self.contract, candidate, as_of_us, "SYNTHETIC"
                )
                self.assertEqual(
                    outcome.error_code, "E_C03_COVERAGE_SET_INVALID"
                )

    def test_c02_cross_scope_diagnostic_is_narrow_and_non_authoritative(self) -> None:
        bundle, as_of_us = _cross_scope_diagnostic_bundle(self.contract)
        self.assertIsInstance(
            validate_bundle(
                self.contract, bundle, as_of_us, "SYNTHETIC"
            ),
            ValidatedBundle,
        )
        wrong_reason, _ = _cross_scope_diagnostic_bundle(
            self.contract, reason_code="POSITION_VS_FILL_PROJECTION"
        )
        wrong_reason_outcome = validate_bundle(
            self.contract, wrong_reason, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(
            wrong_reason_outcome.error_code, "E_C02_SCOPE_MISMATCH"
        )
        authority_use, _ = _cross_scope_diagnostic_bundle(
            self.contract, inject_authority_use=True
        )
        authority_outcome = validate_bundle(
            self.contract, authority_use, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(
            authority_outcome.error_code, "E_C02_SCOPE_MISMATCH"
        )

    def test_c0_is_the_unique_complete_none_side_empty_branch(self) -> None:
        bundle, as_of_us = _bundle(self.contract)
        self.assertIsInstance(
            validate_bundle(
                self.contract, bundle, as_of_us, "SYNTHETIC"
            ),
            ValidatedBundle,
        )
        wrong_side = copy.deepcopy(bundle)
        wrong_side["ledger_seed"]["side"] = "LONG"
        _reseal_bundle(wrong_side)
        side_outcome = validate_bundle(
            self.contract, wrong_side, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(side_outcome.error_code, "E_KERNEL_SCHEMA_INVALID")
        censored = copy.deepcopy(bundle)
        censored["coverage"]["status"] = "CENSORED"
        _reseal_bundle(censored)
        coverage_outcome = validate_bundle(
            self.contract, censored, as_of_us, "SYNTHETIC"
        )
        self.assertEqual(
            coverage_outcome.error_code, "E_KERNEL_SCHEMA_INVALID"
        )

    def test_closed_mark_bar_helper_enforces_full_causal_clock(self) -> None:
        query = {
            "venue_id": "SYNTH",
            "instrument_id": "BTCUSDT",
            "lane_id": LANE,
            "availability_kind": "SYNTHETIC",
            "source_id": "synthetic-bars",
            "source_schema_version": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        }
        valid = _closed_bar_payload(closed_at_us=900_000_000)
        valid_wrapper = {
            "schema_id": "CLOSED_MARK_BAR",
            "payload": valid,
        }
        selected = _select_closed_mark_bar_slot(
            {"artifacts": [valid_wrapper]},
            query,
            900,
            0,
            900_000_000,
        )
        self.assertIsInstance(selected, FrozenMapping)
        invalid = _closed_bar_payload(closed_at_us=899_999_999)
        invalid_wrapper = {
            "schema_id": "CLOSED_MARK_BAR",
            "payload": invalid,
        }
        self.assertFalse(_source_payload_valid("CLOSED_MARK_BAR", invalid))
        self.assertEqual(
            _select_closed_mark_bar_slot(
                {"artifacts": [invalid_wrapper]},
                query,
                900,
                0,
                900_000_000,
            ),
            "UNKNOWN",
        )

    def test_all_34_priority_kinds_and_stop_ack_complement(self) -> None:
        self.assertEqual(len(_REDUCER_KINDS), 34)
        self.assertEqual(set(_FIXED_EVENT_RANK) | {"STOP_ACK"}, set(_REDUCER_KINDS))
        fixed_events = [
            {"event_kind": kind}
            for kind in _REDUCER_KINDS
            if kind != "STOP_ACK"
        ]
        for event in fixed_events:
            self.assertEqual(
                _event_priority(event, [], []),
                _FIXED_EVENT_RANK[event["event_kind"]],
            )
        request = {
            "event_kind": "STOP_REQUEST",
            "request_id": "request",
            "order_id": "stop-order",
            "payload": {
                "price": "99",
                "qty": "1",
                "order_side": "SELL",
                "reduce_only": True,
                "replaces_order_id": None,
                "stop_role": "INITIAL_PROTECTION",
            },
        }
        fill = {
            "event_kind": "FILL_CUMULATIVE",
            "request_id": "entry-request",
            "order_id": "entry-order",
            "payload": {"cum_qty": "1", "cum_quote_notional": "100"},
        }
        ack = {
            "event_kind": "STOP_ACK",
            "request_id": "request",
            "order_id": "stop-order",
            "input_artifact_ids": [],
            "payload": {
                **request["payload"],
                "status": "ACKED",
            },
        }
        self.assertTrue(_matching_sufficient_stop_ack(ack, [fill, request], []))
        self.assertEqual(_event_priority(ack, [fill, request], []), 5)
        insufficient = copy.deepcopy(ack)
        insufficient["payload"]["qty"] = "0.5"
        self.assertFalse(
            _matching_sufficient_stop_ack(insufficient, [fill, request], [])
        )
        self.assertEqual(_event_priority(insufficient, [fill, request], []), 10)

    def test_c16_requires_entry_lifecycle_to_be_submission_descendant(self) -> None:
        submit = {
            "event_kind": "ENTRY_SUBMIT",
            "source_event_id": _id("submit"),
            "event_time_us": 10,
            "lane_available_at_us": 10,
            "economic_event_time_us": None,
            "predecessor_event_ids": [],
            "source_sequence": 0,
        }
        orphan_ack = {
            "event_kind": "ENTRY_ACK",
            "source_event_id": _id("orphan-ack"),
            "event_time_us": 11,
            "lane_available_at_us": 11,
            "economic_event_time_us": None,
            "predecessor_event_ids": [],
            "source_sequence": 0,
        }
        self.assertTrue(
            _causality_violation(
                {"event_array": [submit, orphan_ack], "artifacts": []}
            )
        )
        child_ack = copy.deepcopy(orphan_ack)
        child_ack["predecessor_event_ids"] = [submit["source_event_id"]]
        self.assertFalse(
            _causality_violation(
                {"event_array": [submit, child_ack], "artifacts": []}
            )
        )

    def test_model_and_kernel_have_no_runtime_capability_imports(self) -> None:
        self.assertEqual(
            package.__all__,
            (
                "serialize_contract",
                "validate_bundle",
                "calculate_decision",
                "reduce_event_array",
                "encode_ledger",
                "first_hit_label",
            ),
        )
        for name in package.__all__:
            self.assertTrue(callable(getattr(package, name)))
        forbidden_roots = {
            "asyncio",
            "http",
            "os",
            "pathlib",
            "random",
            "requests",
            "secrets",
            "socket",
            "subprocess",
            "tempfile",
            "threading",
            "time",
            "urllib",
        }
        for path in (MODEL_PATH, KERNEL_PATH):
            tree = ast.parse(path.read_text())
            roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".", 1)[0])
            self.assertFalse(roots & forbidden_roots, path.name)
        public = {
            name: inspect.signature(value)
            for name, value in {
                "validate_bundle": validate_bundle,
                "calculate_decision": calculate_decision,
                "reduce_event_array": reduce_event_array,
                "encode_ledger": encode_ledger,
                "first_hit_label": first_hit_label,
            }.items()
        }
        self.assertEqual(
            list(public["validate_bundle"].parameters),
            ["contract", "bundle", "as_of_us", "role"],
        )
        self.assertEqual(
            list(public["calculate_decision"].parameters),
            ["contract", "binding", "artifacts", "as_of_us", "role"],
        )

    def test_frozen_b1_authorities_are_unchanged(self) -> None:
        expected = {
            CONTRACT_PATH: (
                23_636,
                "26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc",
            ),
            ROOT / "trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py": (
                34_460,
                "ec301735ed867022f1ac0c92c68caaad8bfc9cf0a939c9063f36acf514a1b554",
            ),
        }
        for path, (size, digest) in expected.items():
            raw = path.read_bytes()
            self.assertEqual(len(raw), size, path.name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, path.name)
        self.assertEqual(serialize_contract(self.contract), CONTRACT_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
