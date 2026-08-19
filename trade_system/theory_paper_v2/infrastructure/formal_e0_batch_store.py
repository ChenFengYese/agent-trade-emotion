"""Write-once frozen bindings and resumable artifact access for formal E0.

The store deliberately has no mutable ``latest`` pointer.  Resume is derived
from immutable per-sample artifacts; an existing incomplete generative session
is identified and reported, never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from ..application.generative_topology_run import (
    FORMAL_CONTRACT_DIGEST,
    ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA,
)
from ..domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.formal_e0_replay import ALL_ACTION_IDS


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MUTABLE = {"current", "latest"}


class FormalE0BatchStoreError(ValueError):
    """A frozen-input or write-once artifact violation."""


@dataclass(frozen=True, slots=True)
class PreparedFormalE0Run:
    run_id: str
    run_root: Path
    formal_contract_path: Path
    dataset_bundle_root: Path
    dataset_manifest_path: Path
    dataset_path: Path
    scoring_policy_path: Path
    cost_policy_path: Path
    initial_account_path: Path
    termination_policy_path: Path
    reasoning_instructions_path: Path
    run_bindings_path: Path
    dataset_manifest_digest: str
    dataset_payload_digest: str
    scoring_policy_digest: str
    cost_policy_digest: str
    initial_account_digest: str
    termination_policy_digest: str
    reasoning_instructions_digest: str
    run_bindings_digest: str


def _safe_id(value: str, code: str) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_ID.fullmatch(value) is None
        or value.casefold() in _MUTABLE
    ):
        raise FormalE0BatchStoreError(code)
    return value


def _reject_mutable_path(path: Path) -> None:
    if any(part.casefold() in _MUTABLE for part in Path(path).parts):
        raise FormalE0BatchStoreError("MUTABLE_PATH_FORBIDDEN")


def _artifact_digest(
    manifest: Mapping[str, Any], relative_path: str
) -> str:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise FormalE0BatchStoreError("DATASET_MANIFEST_ARTIFACTS_INVALID")
    matches = [
        item
        for item in artifacts
        if isinstance(item, Mapping)
        and item.get("relative_path") == relative_path
    ]
    if (
        len(matches) != 1
        or not isinstance(matches[0].get("sha256"), str)
    ):
        raise FormalE0BatchStoreError("DATASET_ARTIFACT_BINDING_MISSING")
    return str(matches[0]["sha256"])


def _verify_physical(path: Path, expected_digest: str, code: str) -> None:
    try:
        payload = path.read_bytes()
    except FileNotFoundError as exc:
        raise FormalE0BatchStoreError(code) from exc
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise FormalE0BatchStoreError(code)


def _scoring_policy() -> dict[str, Any]:
    value = {
        "schema_id": "formal_e0_scoring_policy",
        "schema_version": "1.0.0",
        "policy_id": "TA2-FORMAL-E0-SCORING-V1",
        "candidate_components": [
            "PRIMARY",
            "ALTERNATIVE",
            "NULL",
            "OTHER_OR_UNKNOWN",
        ],
        "challenge_categories": [
            "STATE_CONTINUITY",
            "TIME_SCALE_OVERREACH",
            "EXIT_REENTRY_ASYMMETRY",
            "UNKNOWN_COERCION",
            "ACTION_SPACE_COLLAPSE",
            "ROLE_OVERREACH",
        ],
        "action_quality_components": [
            "SCHEMA_VALIDITY",
            "PIT_VALIDITY",
            "STATE_CONTINUITY",
            "ACTION_FEASIBILITY",
            "RISK_BUDGET_VALIDITY",
            "REENTRY_SYMMETRY",
            "OPPORTUNITY_COST_CONSIDERATION",
        ],
        "opportunity_cost_rule": (
            "PASS_WHEN_AT_LEAST_THREE_OF_FOUR_CANDIDATE_COMPONENTS_ARE_PRESENT"
        ),
        "qualification_minimum_action_components": 6,
        "qualification_hard_error_maximum": 0,
        "qualification_state_continuity_error_maximum": 0,
        "qualification_safety_failure_maximum": 0,
        "selected_action_rule": (
            "FINAL_SELECTION_SELECTED_ACTION_MUST_EXACTLY_EQUAL_ONE_"
            "PRE_REGISTERED_FEASIBLE_ACTION_ID"
        ),
        "non_selector_action_rule": "SELECTED_ACTION_MUST_BE_NULL",
        "reproducibility_rule": (
            "RECOMPUTE_DETERMINISTIC_SCORE_AND_COMPARE_CANONICAL_DIGEST"
        ),
        "primary_path_capture_rule": (
            "IF_NEXT_1H_CLOSE_IS_ABOVE_DECISION_CLOSE_THEN_"
            "POST_ACTION_MARKED_GROSS_DIVIDED_BY_FROZEN_MAX_GROSS_"
            "CAPPED_AT_ONE_ELSE_ZERO"
        ),
        "primary_path_capture_input_authority": (
            "EVALUATION_ONLY_NEXT_CLOSED_1H_BAR_NEVER_ROLE_VISIBLE_INPUT"
        ),
        "role_market_projection": {
            "one_hour_window_bars": 96,
            "one_hour_window_rule": (
                "VALIDATE_FULL_DECISION_SLOT_HISTORY_BINDING_THEN_PROJECT_"
                "MOST_RECENT_96_CLOSED_BARS"
            ),
            "earlier_visible_rows": (
                "COUNT_AND_REASON_RECORDED_BUT_VALUES_NOT_ROLE_PROJECTED"
            ),
            "bar_encoding": "ORDERED_FIELDS_AND_ROWS_V1",
            "source_metadata_location": (
                "FROZEN_DATASET_AND_DECISION_SLOT_AUTHORITY_NOT_PER_BAR"
            ),
        },
        "strategic_analysis_continuity": {
            "sequential_handoff": (
                "PREVIOUS_ACCEPTED_SELECTOR_SEMANTIC_PLUS_CALCULATION_AND_"
                "GOVERNANCE_SUMMARIES_BOUND_TO_PREVIOUS_RECEIPT_CONTEXT_"
                "TRANSITION_HEAD_AND_STATE_DIGEST"
            ),
            "cohort_genesis": "EXPLICIT_GENESIS_NO_PRIOR_ANALYSIS",
            "selection_reference": (
                "ONE_PRE_FROZEN_MODEL_INDEPENDENT_REFERENCE_HANDOFF_SHARED_"
                "BY_ALL_THREE_ARMS"
            ),
            "natural_language_authority": (
                "NEXT_ROUND_REVIEW_EVIDENCE_ONLY_NO_MARKET_FACT_ORDER_OR_"
                "STATE_MUTATION_AUTHORITY"
            ),
            "chain_failure_disposition": "HARD_FAIL_BEFORE_MODEL_CALL",
        },
        "unidentified_metric_disposition": "UNKNOWN_NOT_ZERO",
        "natural_language_state_authority": "NONE",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "policy_digest")


def _cost_policy() -> dict[str, Any]:
    value = {
        "schema_id": "formal_e0_cost_policy",
        "schema_version": "1.0.0",
        "policy_id": "TA2-FORMAL-E0-COST-V1",
        "taker_fee_bps": "5",
        "taker_fee_rate": "0.0005",
        "adverse_slippage_bps": "2",
        "adverse_slippage_rate": "0.0002",
        "entry_cost_rule": "TAKER_FEE_PLUS_ADVERSE_BUY_SLIPPAGE",
        "exit_cost_rule": "TAKER_FEE_PLUS_ADVERSE_SELL_SLIPPAGE",
        "hard_stop_cost_rule": "STOP_REFERENCE_PLUS_ADVERSE_SELL_SLIPPAGE",
        "funding": None,
        "funding_status": "UNKNOWN_EXCLUDED",
        "funding_reason": "NO_FROZEN_FUNDING_SOURCE_IN_DATASET",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "policy_digest")


def _initial_account() -> dict[str, Any]:
    value = {
        "schema_id": "formal_e0_initial_account",
        "schema_version": "1.0.0",
        "account_id": "TA2-FORMAL-E0-ACCOUNT-V1",
        "initial_equity": "10000",
        "currency": "USDT",
        "long_only": True,
        "short_actions_registered": False,
        "core_fraction": "0.0625",
        "stage_fraction": "0.03125",
        "maximum_stage_count": 2,
        "max_gross_fraction": "0.125",
        "max_gross_measurement_basis": "MARK_TO_MARKET_AT_EACH_DECISION",
        "marked_gross_breach_disposition": (
            "HOLD_AND_ADD_NOT_FEASIBLE_TRIM_OR_EXIT_REQUIRED"
        ),
        "hard_stop_fraction": "0.10",
        "maximum_open_risk_fraction_at_registered_stop": "0.0125",
        "pre_registered_action_ids": list(ALL_ACTION_IDS),
        "cross_cohort_state_inheritance": "FORBIDDEN",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "account_digest")


def _termination_policy() -> dict[str, Any]:
    value = {
        "schema_id": "formal_e0_termination_policy",
        "schema_version": "1.0.0",
        "policy_id": "TA2-FORMAL-E0-TERMINATION-V1",
        "cohort_state_isolation": {
            "TOPOLOGY_SELECTION": (
                "PRE_FROZEN_REFERENCE_STATE_CHAIN_SAME_FOR_ALL_THREE_ARMS"
            ),
            "POLICY_QUALIFICATION": (
                "INDEPENDENT_QUALIFICATION_GENESIS_NO_SELECTION_POSITION_INHERITANCE"
            ),
            "FORMAL_EXPERIMENT": (
                "NEW_GENESIS_AT_INDEX_160_NO_QUALIFICATION_POSITION_OR_PNL_INHERITANCE"
            ),
        },
        "formal_sequential_update_range_inclusive": [160, 191],
        "selection_range_inclusive": [96, 127],
        "qualification_range_inclusive": [128, 159],
        "formal_range_inclusive": [160, 191],
        "formal_terminal_outcome_horizon_hours": 1,
        "future_input_disposition": "HARD_FAIL",
        "exit_while_thesis_survives": (
            "ATOMically_OPEN_REENTRY_IN_SAME_DETERMINISTIC_TRANSITION"
        ),
        "hard_stop": (
            "TEN_PERCENT_BELOW_WEIGHTED_ENTRY_THEN_OPEN_REENTRY_IF_THESIS_ACTIVE"
        ),
        "invalid_selected_action": "NO_CHANGE_FAIL_CLOSED_AND_COUNT_HARD_ERROR",
        "incomplete_existing_session": (
            "READ_ONLY_IDENTIFY_NEVER_OVERWRITE_USE_NEW_RUN_ID_FOR_RETRY"
        ),
        "formal_transport_admission": {
            "served_model_attestation_required": True,
            "hard_generation_limit_mechanism_required": True,
            "hard_generation_limit_adapter_attestation": (
                "CODEX_EXEC_GENERATIVE_TRANSPORT:"
                "1.1.0-ROLLOUT-BUDGET-ATTESTED"
            ),
            "token_budget_feature_alone_is_hard_cap": False,
            "unknown_served_model_disposition": "NO_GO_NOT_FORMAL_EVIDENCE",
            "unverified_token_budget_disposition": "NO_GO_NOT_FORMAL_EVIDENCE",
        },
        "round2_101_percent_account_creation": "FORBIDDEN_IN_THIS_RUN",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "policy_digest")


_INSTRUCTION_TEXTS = {
    "SINGLE_STRONG": (
        "You are the single strong decision analyst. Preserve the supplied "
        "strategic state across time scales. Enumerate primary, alternative, "
        "null and other-or-unknown paths where evidence permits. Challenge "
        "state continuity, time-scale overreach, exit/reentry asymmetry, "
        "unknown coercion, action-space collapse and role overreach. Only in "
        "the SELECTION phase, selected_action must be exactly one action_id "
        "from feasible_actions; otherwise selected_action must be null. "
        "Natural-language statements have no state authority."
    ),
    "PROPOSER": (
        "You are the proposal analyst. Use only the supplied point-in-time "
        "context. Preserve typed unknowns and prior strategic state. Produce "
        "competing paths. selected_action must be null because the proposer "
        "has no action-selection authority."
    ),
    "CHALLENGER": (
        "You are the independent challenger. Use only the supplied point-in-"
        "time context and visible prior envelope, if any. Seek material "
        "defects using only registered challenge categories. selected_action "
        "must be null because the challenger has no action authority."
    ),
    "SELECTOR": (
        "You are the bounded selector. Reconcile proposal and challenge "
        "without inventing data. selected_action must exactly equal one "
        "action_id in feasible_actions. Do not output an action description, "
        "synonym, quantity, price or prose in selected_action."
    ),
}


def _reasoning_instructions() -> dict[str, Any]:
    rows = []
    for instruction_id in (
        "SINGLE_STRONG",
        "PROPOSER",
        "CHALLENGER",
        "SELECTOR",
    ):
        text = _INSTRUCTION_TEXTS[instruction_id]
        raw = text.encode("utf-8")
        rows.append(
            {
                "instruction_id": instruction_id,
                "instruction_text": text,
                "instruction_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    value = {
        "schema_id": "formal_e0_reasoning_instruction_set",
        "schema_version": "1.0.0",
        "instruction_set_id": "TA2-FORMAL-E0-INSTRUCTIONS-V1",
        "instructions": rows,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "instruction_set_digest")


def _parse_frozen_at(value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FormalE0BatchStoreError("FROZEN_AT_INVALID")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FormalE0BatchStoreError("FROZEN_AT_INVALID") from exc
    return value


def prepare_formal_e0_run(
    *,
    runtime_root: Path,
    run_id: str,
    formal_contract_path: Path,
    dataset_bundle_root: Path,
    frozen_at: str,
) -> PreparedFormalE0Run:
    """Materialize all scoring/cost/account/termination bindings pre-call."""

    run_id = _safe_id(run_id, "FORMAL_E0_RUN_ID_INVALID")
    frozen_at = _parse_frozen_at(frozen_at)
    runtime_root = Path(runtime_root).resolve()
    formal_contract_path = Path(formal_contract_path).resolve()
    dataset_bundle_root = Path(dataset_bundle_root).resolve()
    for path in (runtime_root, formal_contract_path, dataset_bundle_root):
        _reject_mutable_path(path)
    contract = load_json_strict(formal_contract_path)
    if verify_self_digest(contract, "contract_digest") != FORMAL_CONTRACT_DIGEST:
        raise FormalE0BatchStoreError("FORMAL_CONTRACT_DIGEST_MISMATCH")
    manifest_path = dataset_bundle_root / "manifest.json"
    dataset_path = dataset_bundle_root / "normalized" / "dataset.json"
    manifest = load_json_strict(manifest_path)
    manifest_digest = verify_self_digest(manifest, "manifest_digest")
    if (
        manifest.get("quality_status") != "PASS"
        or manifest.get("replay_admissibility_status") != "PASS"
        or manifest.get("experiment_contract_digest")
        != FORMAL_CONTRACT_DIGEST
        or manifest.get("decision_indices_inclusive") != [96, 191]
        or manifest.get("requested_closed_bar_count") != 256
        or manifest.get("executable") is not False
    ):
        raise FormalE0BatchStoreError("DATASET_MANIFEST_NOT_ADMISSIBLE")
    dataset_payload_digest = _artifact_digest(
        manifest, "normalized/dataset.json"
    )
    _verify_physical(
        dataset_path,
        dataset_payload_digest,
        "DATASET_PAYLOAD_PHYSICAL_DIGEST_MISMATCH",
    )
    run_root = runtime_root / run_id
    frozen_root = run_root / "frozen"
    sessions_root = run_root / "sessions"
    bindings_path = frozen_root / "run-bindings.json"
    if not bindings_path.exists() and sessions_root.exists() and any(
        sessions_root.iterdir()
    ):
        raise FormalE0BatchStoreError(
            "POLICIES_MUST_BE_FROZEN_BEFORE_FIRST_GENERATIVE_CALL"
        )

    scoring = _scoring_policy()
    cost = _cost_policy()
    account = _initial_account()
    termination = _termination_policy()
    instructions = _reasoning_instructions()
    scoring_path = frozen_root / "scoring-policy.v1.json"
    cost_path = frozen_root / "cost-policy.v1.json"
    account_path = frozen_root / "initial-account.v1.json"
    termination_path = frozen_root / "termination-policy.v1.json"
    instructions_path = frozen_root / "reasoning-instructions.v1.json"
    write_once_json(scoring_path, scoring)
    write_once_json(cost_path, cost)
    write_once_json(account_path, account)
    write_once_json(termination_path, termination)
    write_once_json(instructions_path, instructions)
    dataset_ref = self_digest(
        {
            "schema_id": "formal_e0_dataset_manifest_ref",
            "schema_version": "1.0.0",
            "dataset_id": manifest["bundle_id"],
            "dataset_manifest_digest": manifest_digest,
            "dataset_payload_digest": dataset_payload_digest,
            "quality_verdict": manifest["quality_status"],
            "replay_admissibility_verdict": manifest[
                "replay_admissibility_status"
            ],
            "decision_slot_count": 96,
            "transport_contract_verdict": "PASS",
            "transport_schema_digest": canonical_digest(
                ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
            ),
            "physical_capture_status": manifest["physical_capture_status"],
            "contemporaneous_agent_input_status": manifest[
                "contemporaneous_agent_input_status"
            ],
        },
        "reference_digest",
    )
    dataset_ref_path = frozen_root / "dataset-manifest-ref.v1.json"
    write_once_json(dataset_ref_path, dataset_ref)
    policy_set_digest = canonical_digest(
        {
            "scoring_policy_digest": scoring["policy_digest"],
            "cost_policy_digest": cost["policy_digest"],
            "initial_account_digest": account["account_digest"],
            "termination_policy_digest": termination["policy_digest"],
            "reasoning_instructions_digest": instructions[
                "instruction_set_digest"
            ],
        }
    )
    bindings = self_digest(
        {
            "schema_id": "formal_e0_frozen_run_bindings",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "frozen_at": frozen_at,
            "frozen_before_first_generative_call": True,
            "formal_contract_id": contract["contract_id"],
            "formal_contract_digest": FORMAL_CONTRACT_DIGEST,
            "dataset_id": manifest["bundle_id"],
            "dataset_manifest_digest": manifest_digest,
            "dataset_payload_digest": dataset_payload_digest,
            "role_input_transport_schema_digest": canonical_digest(
                ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
            ),
            "scoring_policy_digest": scoring["policy_digest"],
            "cost_policy_digest": cost["policy_digest"],
            "initial_account_digest": account["account_digest"],
            "termination_policy_digest": termination["policy_digest"],
            "reasoning_instructions_digest": instructions[
                "instruction_set_digest"
            ],
            "policy_set_digest": policy_set_digest,
            "cohort_state_isolation": (
                "SELECTION_REFERENCE_ONLY_QUALIFICATION_NEW_GENESIS_"
                "FORMAL_NEW_GENESIS_AT_160"
            ),
            "served_model_attestation_required": True,
            "hard_generation_limit_mechanism_required": True,
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "bindings_digest",
    )
    write_once_json(bindings_path, bindings)
    # Bind the source paths without copying or mutating the frozen bundle.
    source_paths = self_digest(
        {
            "schema_id": "formal_e0_source_path_receipt",
            "schema_version": "1.0.0",
            "formal_contract_path": str(formal_contract_path),
            "dataset_bundle_root": str(dataset_bundle_root),
            "dataset_manifest_path": str(manifest_path),
            "dataset_path": str(dataset_path),
            "formal_contract_digest": FORMAL_CONTRACT_DIGEST,
            "dataset_manifest_digest": manifest_digest,
            "dataset_payload_digest": dataset_payload_digest,
        },
        "receipt_digest",
    )
    write_once_json(frozen_root / "source-path-receipt.json", source_paths)
    return PreparedFormalE0Run(
        run_id=run_id,
        run_root=run_root,
        formal_contract_path=formal_contract_path,
        dataset_bundle_root=dataset_bundle_root,
        dataset_manifest_path=manifest_path,
        dataset_path=dataset_path,
        scoring_policy_path=scoring_path,
        cost_policy_path=cost_path,
        initial_account_path=account_path,
        termination_policy_path=termination_path,
        reasoning_instructions_path=instructions_path,
        run_bindings_path=bindings_path,
        dataset_manifest_digest=manifest_digest,
        dataset_payload_digest=dataset_payload_digest,
        scoring_policy_digest=str(scoring["policy_digest"]),
        cost_policy_digest=str(cost["policy_digest"]),
        initial_account_digest=str(account["account_digest"]),
        termination_policy_digest=str(termination["policy_digest"]),
        reasoning_instructions_digest=str(
            instructions["instruction_set_digest"]
        ),
        run_bindings_digest=str(bindings["bindings_digest"]),
    )


def load_prepared_formal_e0_run(run_root: Path) -> PreparedFormalE0Run:
    run_root = Path(run_root).resolve()
    _reject_mutable_path(run_root)
    bindings_path = run_root / "frozen" / "run-bindings.json"
    sources_path = run_root / "frozen" / "source-path-receipt.json"
    bindings = load_json_strict(bindings_path)
    sources = load_json_strict(sources_path)
    verify_self_digest(bindings, "bindings_digest")
    verify_self_digest(sources, "receipt_digest")
    if (
        bindings.get("formal_contract_digest") != FORMAL_CONTRACT_DIGEST
        or bindings.get("frozen_before_first_generative_call") is not True
        or bindings.get("external_execution_authority") != "NONE_E0"
        or bindings.get("executable") is not False
    ):
        raise FormalE0BatchStoreError("FROZEN_RUN_BINDINGS_INVALID")
    formal_contract_path = Path(str(sources["formal_contract_path"]))
    bundle_root = Path(str(sources["dataset_bundle_root"]))
    prepared = PreparedFormalE0Run(
        run_id=_safe_id(str(bindings["run_id"]), "FORMAL_E0_RUN_ID_INVALID"),
        run_root=run_root,
        formal_contract_path=formal_contract_path,
        dataset_bundle_root=bundle_root,
        dataset_manifest_path=Path(str(sources["dataset_manifest_path"])),
        dataset_path=Path(str(sources["dataset_path"])),
        scoring_policy_path=run_root
        / "frozen"
        / "scoring-policy.v1.json",
        cost_policy_path=run_root / "frozen" / "cost-policy.v1.json",
        initial_account_path=run_root
        / "frozen"
        / "initial-account.v1.json",
        termination_policy_path=run_root
        / "frozen"
        / "termination-policy.v1.json",
        reasoning_instructions_path=run_root
        / "frozen"
        / "reasoning-instructions.v1.json",
        run_bindings_path=bindings_path,
        dataset_manifest_digest=str(bindings["dataset_manifest_digest"]),
        dataset_payload_digest=str(bindings["dataset_payload_digest"]),
        scoring_policy_digest=str(bindings["scoring_policy_digest"]),
        cost_policy_digest=str(bindings["cost_policy_digest"]),
        initial_account_digest=str(bindings["initial_account_digest"]),
        termination_policy_digest=str(
            bindings["termination_policy_digest"]
        ),
        reasoning_instructions_digest=str(
            bindings["reasoning_instructions_digest"]
        ),
        run_bindings_digest=str(bindings["bindings_digest"]),
    )
    for path, expected, field in (
        (
            prepared.scoring_policy_path,
            prepared.scoring_policy_digest,
            "policy_digest",
        ),
        (
            prepared.cost_policy_path,
            prepared.cost_policy_digest,
            "policy_digest",
        ),
        (
            prepared.initial_account_path,
            prepared.initial_account_digest,
            "account_digest",
        ),
        (
            prepared.termination_policy_path,
            prepared.termination_policy_digest,
            "policy_digest",
        ),
        (
            prepared.reasoning_instructions_path,
            prepared.reasoning_instructions_digest,
            "instruction_set_digest",
        ),
    ):
        value = load_json_strict(path)
        if verify_self_digest(value, field) != expected:
            raise FormalE0BatchStoreError("FROZEN_POLICY_DIGEST_MISMATCH")
    _verify_physical(
        prepared.dataset_path,
        prepared.dataset_payload_digest,
        "DATASET_PAYLOAD_PHYSICAL_DIGEST_MISMATCH",
    )
    return prepared


def write_resume_json(path: Path, value: Mapping[str, Any]) -> str:
    """Idempotent immutable write used by per-sample batch artifacts."""

    _reject_mutable_path(Path(path))
    return write_once_json(Path(path), dict(value))


__all__ = [
    "FormalE0BatchStoreError",
    "PreparedFormalE0Run",
    "load_prepared_formal_e0_run",
    "prepare_formal_e0_run",
    "write_resume_json",
]
