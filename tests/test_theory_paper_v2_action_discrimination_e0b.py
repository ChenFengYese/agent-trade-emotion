from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.domain.action_discrimination.engine import (
    EQUITY,
    FEE_RATE,
    SLIPPAGE_RATE,
)
from trade_system.theory_paper_v2.domain.action_discrimination.evaluation import (
    _simulate,
    terminal_result,
)
from trade_system.theory_paper_v2.domain.action_discrimination.model import (
    E0B_FINANCIAL_CONTRACT,
    E0B_SAMPLE_INDICES,
    OUTPUT_SPECS,
    PATH_SLOTS,
    SELECTION_AXES,
    ActionDiscriminationError,
    ActionId,
)
from trade_system.theory_paper_v2.domain.action_discrimination.validation import (
    arm_preoutcome_score,
    validate_semantic_output,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.application.action_discrimination_experiment import (
    role_packet,
)
from trade_system.theory_paper_v2.infrastructure.action_discrimination_store import (
    EXPECTED_ROLE_KEYS,
    ActionExperimentStoreError,
    FrozenOutcomeDatasetAdapter,
    load_frozen_action_context,
    prepare_action_experiment,
    record_action_case,
    verify_action_experiment,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = (
    ROOT
    / ".runtime"
    / "theory-paper-v2"
    / "formal-e0-batches"
    / "formal-e0-btcusdt-20260731T103131Z"
)
CONFIG = ROOT / "config" / "theory_agent_v2.action_discrimination_e0b.v2.json"
DESIGN = ROOT / "archive/experiments/THEORY_AGENT_V2_ACTION_DISCRIMINATION_EXPERIMENT_v0_2.md"
MISMATCHED_SOURCE_RUN = (
    ROOT
    / ".runtime"
    / "theory-paper-v2"
    / "formal-e0-batches"
    / "formal-e0-btcusdt-20260731T102754Z"
)


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def _semantic(role_key: str, context: dict, *, selected_offset: int = 0) -> dict:
    choice = list(context["candidate_calculations"]["selector_choice_set"])
    evidence = list(context["allowed_evidence_ids"])
    output_kind = OUTPUT_SPECS[role_key]
    dedicated_review = output_kind in {"SELF_REVIEW", "CHALLENGE_BLIND"}
    ranking = choice[selected_offset:] + choice[:selected_offset]
    return {
        "schema_id": "action_discrimination_semantic_output",
        "schema_version": "1.0.0",
        "output_kind": output_kind,
        "context_digest": context["context_digest"],
        "state_digest": context["state"]["state_digest"],
        "paths": [
            {
                "slot": slot,
                "path_id": path_id,
                "summary": f"Frozen {slot} path.",
                "evidence_ids": evidence[:2] if slot != "OTHER_OR_UNKNOWN" else [],
                "hard_falsifier_refs": [],
                "unknowns": ["path_probabilities"] if slot == "OTHER_OR_UNKNOWN" else [],
            }
            for slot, path_id in zip(
                PATH_SLOTS,
                (
                    "NORMAL_REBOUND_TO_T1",
                    "FAILURE_TO_STOP",
                    "EXHAUSTION_T1_THEN_RETURN",
                    "UNKNOWN",
                ),
                strict=True,
            )
        ],
        "action_assessments": [
            {
                "action_id": action_id,
                "ordinal": "PREFERRED" if action_id == ranking[0] else "VIABLE",
                "rationale": "Compared under the frozen E0B contract.",
                "evidence_ids": evidence[:2],
            }
            for action_id in choice
        ],
        "challenge_claims": (
            [
                {
                    "category": "PATH_PAYOFF_MISMATCH",
                    "materiality": "MATERIAL",
                    "claim": "Dedicated review checks path and transition coherence.",
                    "evidence_ids": evidence[:2],
                    "affected_action_ids": choice,
                }
            ]
            if dedicated_review
            else []
        ),
        "selected_action": ranking[0] if output_kind == "SELECTION" else None,
        "ranked_action_ids": ranking if output_kind == "SELECTION" else [],
        "selection_axes": [
            {
                "axis": axis,
                "status": "APPLIED",
                "rationale": "Applied symmetrically to the frozen context.",
            }
            for axis in SELECTION_AXES
        ],
        "numeric_probability_status": "NOT_CLAIMED",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def _receipts(
    *,
    run_root: Path,
    sample_index: int,
    outputs: dict[str, dict],
) -> dict[str, dict]:
    packets = {
        "single-proposal": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="single-strong-bundle",
        ),
        "single-self-review": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="single-strong-bundle",
        ),
        "single-selection": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="single-strong-bundle",
        ),
        "cluster-proposal": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="cluster-proposal",
        ),
        "cluster-challenge": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="cluster-challenge",
        ),
        "cluster-selection": role_packet(
            run_root=run_root,
            sample_index=sample_index,
            role="cluster-selection",
            proposal=outputs["cluster-proposal"],
            challenge=outputs["cluster-challenge"],
        ),
    }
    task_ids = {
        "single-proposal": f"single-{sample_index}",
        "single-self-review": f"single-{sample_index}",
        "single-selection": f"single-{sample_index}",
        "cluster-proposal": f"proposal-{sample_index}",
        "cluster-challenge": f"challenge-{sample_index}",
        "cluster-selection": f"selector-{sample_index}",
    }
    context_digest = outputs["single-proposal"]["context_digest"]
    return {
        role_key: {
            "role_key": role_key,
            "agent_task_id": task_ids[role_key],
            "delivery_protocol": "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1",
            "fork_turns": "none",
            "packet_digest": packet["packet_digest"],
            "packet_byte_length": len(canonical_bytes(packet)),
            "context_digest": context_digest,
            "tool_use_status": "NO_TOOL_CALL_OBSERVED",
            "external_data_status": "NO_EXTERNAL_DATA_OBSERVED",
            "served_model_attestation": "UNATTESTED",
            "token_budget_attestation": "UNATTESTED",
            "formal_role_call": True,
            "response_json_only": True,
        }
        for role_key, packet in packets.items()
    }


@unittest.skipUnless(SOURCE_RUN.exists(), "frozen E0 authority is required")
class ActionDiscriminationE0BTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_root = prepare_action_experiment(
            runtime_root=Path(self.temp.name),
            run_id="action-e0b-test",
            source_run_root=SOURCE_RUN,
            config_path=CONFIG,
            design_path=DESIGN,
            frozen_at="2026-08-01T10:00:00Z",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _context(self, sample_index: int) -> dict:
        return load_json_strict(
            self.run_root
            / "frozen"
            / "contexts"
            / f"sample-{sample_index:03d}.json"
        )

    def test_window_contract_and_preoutcome_gate_are_frozen(self) -> None:
        config = load_json_strict(CONFIG)
        verify_self_digest(config, "config_digest")
        manifest = load_json_strict(self.run_root / "frozen" / "manifest.json")
        self.assertEqual(manifest["decision_indices_inclusive"], [160, 191])
        self.assertEqual(
            manifest["financial_contract_version"], E0B_FINANCIAL_CONTRACT
        )
        self.assertTrue(set(E0B_SAMPLE_INDICES).isdisjoint(range(128, 160)))
        self.assertEqual(sorted(manifest["profile_counts"].values()), [4] * 8)
        status = verify_action_experiment(self.run_root)
        self.assertEqual(status["next_sample_index"], 160)
        self.assertFalse(status["terminal"])
        with self.assertRaises(ActionExperimentStoreError):
            FrozenOutcomeDatasetAdapter(SOURCE_RUN, self.run_root)

    def test_all_failure_rows_reconcile_to_per_lot_registered_stops(self) -> None:
        exit_rate = FEE_RATE + SLIPPAGE_RATE
        for sample_index in E0B_SAMPLE_INDICES:
            context = self._context(sample_index)
            mark = _d(context["geometry"]["mark"])
            candidates = {
                row["action_id"]: row
                for row in context["candidate_calculations"]["candidate_rows"]
            }
            for row in context["path_payoff_matrix"]["rows"]:
                if row["path_id"] != "FAILURE_TO_STOP":
                    continue
                self.assertIsNone(row["terminal_reference"])
                self.assertEqual(
                    row["terminal_policy"],
                    "EACH_POST_ACTION_LOT_AT_REGISTERED_STOP",
                )
                candidate = candidates[row["action_id"]]
                immediate_cost = (
                    _d(candidate["immediate_transaction_cost_fraction"]) * EQUITY
                )
                expected = -immediate_cost
                for lot in row["lot_exit_references"]:
                    quantity = _d(lot["quantity"])
                    exit_price = _d(lot["exit_price"])
                    expected += quantity * (exit_price - mark)
                    expected -= quantity * exit_price * exit_rate
                    self.assertEqual(
                        _d(lot["exit_cost"]), quantity * exit_price * exit_rate
                    )
                self.assertLessEqual(
                    abs(_d(row["net_account_change"]) - expected),
                    Decimal("1e-20"),
                )

    def test_transition_contract_matches_partial_exit_reentry_and_trail(self) -> None:
        context = self._context(163)  # CORE_PLUS_TACTICAL
        rows = {
            row["action_id"]: row
            for row in context["candidate_calculations"]["candidate_rows"]
        }
        partial = rows["PARTIAL_TAKE_PROFIT"]["action_transition_contract"]
        original = {lot["lot_id"]: _d(lot["quantity"]) for lot in context["state"]["lots"]}
        self.assertEqual(set(original), {row["lot_id"] for row in partial["closed_lots"]})
        for row in partial["closed_lots"]:
            self.assertEqual(_d(row["closed_quantity"]), original[row["lot_id"]] / 2)
        reentry = rows["EXIT_WITH_REENTRY"]["action_transition_contract"][
            "reentry_obligation_created"
        ]
        self.assertFalse(reentry["execution_in_current_action"])
        self.assertIsNone(reentry["future_fill_price"])
        trail = rows["HOLD_CORE_TRAIL"]["action_transition_contract"][
            "trail_contract"
        ]
        self.assertEqual(
            trail["ohlc_ambiguity_policy"],
            "OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR",
        )
        self.assertFalse(trail["same_bar_new_stop_execution"])
        exhaustion = next(
            row
            for row in context["path_payoff_matrix"]["rows"]
            if row["action_id"] == "HOLD_CORE_TRAIL"
            and row["path_id"] == "EXHAUSTION_T1_THEN_RETURN"
        )
        self.assertIsNone(exhaustion["net_account_change"])
        self.assertEqual(
            exhaustion["terminal_policy"],
            "UNKNOWN_T1_RETURN_SEQUENCE_NEXT_BAR_TRAIL",
        )
        flat = self._context(160)
        wait = next(
            row
            for row in flat["candidate_calculations"]["candidate_rows"]
            if row["action_id"] == "WAIT_WITH_REVIEW"
        )["action_transition_contract"]
        self.assertEqual(wait["review_obligation_after"]["status"], "OPEN")
        self.assertEqual(
            wait["review_obligation_after"]["review_deadline"],
            "NEXT_CLOSED_1H_OR_EARLIER_HARD_RISK_EVENT",
        )
        self.assertFalse(
            wait["review_obligation_after"]["execution_in_current_action"]
        )
        mark = _d(flat["geometry"]["mark"])
        flat_bars = [
            {
                "open": str(mark),
                "low": str(mark),
                "high": str(mark),
                "close": str(mark),
            },
            {
                "open": str(mark),
                "low": str(mark),
                "high": str(mark),
                "close": str(mark),
            },
        ]
        overdue = _simulate(
            context=flat,
            action=ActionId.WAIT_WITH_REVIEW,
            bars=flat_bars,
        )
        self.assertEqual(
            overdue["review_obligation_source"],
            "FROZEN_ACTION_TRANSITION_CONTRACT",
        )
        self.assertFalse(
            overdue["contract_comparable_for_terminal_advantage"]
        )
        missing_review = deepcopy(flat)
        wait_row = next(
            row
            for row in missing_review["candidate_calculations"][
                "candidate_rows"
            ]
            if row["action_id"] == "WAIT_WITH_REVIEW"
        )
        wait_row["action_transition_contract"][
            "review_obligation_after"
        ] = None
        with self.assertRaisesRegex(
            ActionDiscriminationError,
            "OUTCOME_REVIEW_OBLIGATION_ACTION_MISMATCH",
        ):
            _simulate(
                context=missing_review,
                action=ActionId.WAIT_WITH_REVIEW,
                bars=flat_bars,
            )

    def test_trail_is_effective_next_bar_and_ledger_reconciles(self) -> None:
        context = self._context(164)  # TARGET_REVIEW_ACTIVE
        mark = _d(context["geometry"]["mark"])
        target1 = _d(context["geometry"]["normal_target"])
        old_stop = _d(context["state"]["lots"][0]["stop"])
        new_trail = target1 - (mark - _d(context["geometry"]["stop_new"]))
        self.assertGreater(new_trail, old_stop)
        first_low = (old_stop + new_trail) / 2
        bars = [
            {
                "open": str(mark),
                "low": str(first_low),
                "high": str(target1),
                "close": str(mark),
            },
            {
                "open": str(mark),
                "low": str(first_low),
                "high": str(target1),
                "close": str(mark),
            },
        ]
        result_one = _simulate(
            context=context,
            action=ActionId.HOLD_CORE_TRAIL,
            bars=bars[:1],
        )
        result_two = _simulate(
            context=context,
            action=ActionId.HOLD_CORE_TRAIL,
            bars=bars,
        )
        self.assertEqual(result_one["remaining_lot_count"], 1)
        self.assertEqual(result_two["remaining_lot_count"], 0)
        self.assertEqual(result_one["trailing_armed_bar_offset"], 1)
        self.assertEqual(
            _d(result_two["predecision_embedded_gross_pnl"]),
            _d(result_two["embedded_pnl_realized_immediately"])
            + _d(result_two["embedded_pnl_remaining_at_decision"]),
        )

    def test_gap_fill_and_true_peak_to_trough_drawdown_are_conservative(self) -> None:
        context = self._context(161)  # CORE_ACTIVE
        mark = _d(context["geometry"]["mark"])
        stop = _d(context["state"]["lots"][0]["stop"])
        gap_open = stop * Decimal("0.99")
        gap_result = _simulate(
            context=context,
            action=ActionId.HOLD_CORE,
            bars=[
                {
                    "open": str(gap_open),
                    "low": str(gap_open),
                    "high": str(gap_open),
                    "close": str(gap_open),
                }
            ],
        )
        self.assertEqual(gap_result["gap_through_stop_count"], 1)
        quantity = _d(context["state"]["lots"][0]["quantity"])
        self.assertEqual(
            _d(gap_result["decision_incremental_realized_pnl"]),
            quantity * (gap_open - mark),
        )

        high = mark * Decimal("1.08")
        low = mark * Decimal("1.02")
        drawdown_result = _simulate(
            context=context,
            action=ActionId.HOLD_CORE,
            bars=[
                {
                    "open": str(mark),
                    "low": str(low),
                    "high": str(high),
                    "close": str(low),
                }
            ],
        )
        self.assertEqual(
            _d(drawdown_result["maximum_adverse_excursion_from_decision"]),
            ZERO,
        )
        self.assertGreater(
            _d(drawdown_result["maximum_drawdown_from_decision"]), ZERO
        )

    def test_manifest_context_binding_rejects_self_rehashed_replacement(self) -> None:
        path = (
            self.run_root
            / "frozen"
            / "contexts"
            / "sample-160.json"
        )
        value = load_json_strict(path)
        value["typed_unknowns"] = list(value["typed_unknowns"]) + [
            "tampered_unknown"
        ]
        value.pop("context_digest")
        value["context_digest"] = canonical_digest(value)
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ActionExperimentStoreError):
            load_frozen_action_context(self.run_root, 160)

    def test_receipts_bind_exact_packets_and_clean_role_topology(self) -> None:
        context = self._context(160)
        outputs = {
            role_key: _semantic(role_key, context)
            for role_key in EXPECTED_ROLE_KEYS
        }
        receipts = _receipts(
            run_root=self.run_root,
            sample_index=160,
            outputs=outputs,
        )
        bad = {key: dict(value) for key, value in receipts.items()}
        bad["cluster-selection"]["packet_byte_length"] += 1
        with self.assertRaises(ActionExperimentStoreError):
            record_action_case(
                run_root=self.run_root,
                sample_index=160,
                semantic_outputs=outputs,
                invocation_receipts=bad,
            )
        event = record_action_case(
            run_root=self.run_root,
            sample_index=160,
            semantic_outputs=outputs,
            invocation_receipts=receipts,
        )
        self.assertEqual(event["sample_index"], 160)
        self.assertEqual(
            verify_action_experiment(self.run_root)["next_sample_index"], 161
        )

    def test_transport_preflight_child_cannot_be_reused_as_formal_role(self) -> None:
        context = self._context(160)
        outputs = {
            role_key: _semantic(role_key, context)
            for role_key in EXPECTED_ROLE_KEYS
        }
        receipts = _receipts(
            run_root=self.run_root,
            sample_index=160,
            outputs=outputs,
        )
        for role_key in (
            "single-proposal",
            "single-self-review",
            "single-selection",
        ):
            receipts[role_key]["agent_task_id"] = (
                "/root/e0b_transport_preflight_v2"
            )
        with self.assertRaisesRegex(
            ActionExperimentStoreError,
            "INVOCATION_RECEIPT_TASK_REUSED_ACROSS_SAMPLES",
        ):
            record_action_case(
                run_root=self.run_root,
                sample_index=160,
                semantic_outputs=outputs,
                invocation_receipts=receipts,
            )

    def test_partial_write_recovers_only_with_identical_case_bytes(self) -> None:
        context = self._context(160)
        outputs = {
            role_key: _semantic(role_key, context)
            for role_key in EXPECTED_ROLE_KEYS
        }
        receipts = _receipts(
            run_root=self.run_root,
            sample_index=160,
            outputs=outputs,
        )
        call_count = 0

        def fail_during_output_bundle(path: Path, value: dict) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise OSError("synthetic crash before event")
            return write_once_json(path, value)

        with patch(
            "trade_system.theory_paper_v2.infrastructure."
            "action_discrimination_store.write_once_json",
            side_effect=fail_during_output_bundle,
        ):
            with self.assertRaisesRegex(OSError, "synthetic crash"):
                record_action_case(
                    run_root=self.run_root,
                    sample_index=160,
                    semantic_outputs=outputs,
                    invocation_receipts=receipts,
                )
        interrupted = verify_action_experiment(self.run_root)
        self.assertEqual(interrupted["completed_count"], 0)
        self.assertEqual(interrupted["next_sample_index"], 160)
        self.assertFalse(
            (self.run_root / "events" / "sample-160.json").exists()
        )

        event = record_action_case(
            run_root=self.run_root,
            sample_index=160,
            semantic_outputs=outputs,
            invocation_receipts=receipts,
        )
        self.assertEqual(event["sample_index"], 160)
        resumed = verify_action_experiment(self.run_root)
        self.assertEqual(resumed["completed_count"], 1)
        self.assertEqual(resumed["next_sample_index"], 161)

    def test_clean_agent_task_id_cannot_be_reused_across_samples(self) -> None:
        first_context = self._context(160)
        first_outputs = {
            role_key: _semantic(role_key, first_context)
            for role_key in EXPECTED_ROLE_KEYS
        }
        record_action_case(
            run_root=self.run_root,
            sample_index=160,
            semantic_outputs=first_outputs,
            invocation_receipts=_receipts(
                run_root=self.run_root,
                sample_index=160,
                outputs=first_outputs,
            ),
        )

        second_context = self._context(161)
        second_outputs = {
            role_key: _semantic(role_key, second_context)
            for role_key in EXPECTED_ROLE_KEYS
        }
        reused = _receipts(
            run_root=self.run_root,
            sample_index=161,
            outputs=second_outputs,
        )
        reused["cluster-proposal"]["agent_task_id"] = "proposal-160"
        with self.assertRaisesRegex(
            ActionExperimentStoreError,
            "INVOCATION_RECEIPT_TASK_REUSED_ACROSS_SAMPLES",
        ):
            record_action_case(
                run_root=self.run_root,
                sample_index=161,
                semantic_outputs=second_outputs,
                invocation_receipts=reused,
            )

    def test_terminal_outcome_reader_rejects_different_source_run_binding(self) -> None:
        for sample_index in E0B_SAMPLE_INDICES:
            context = self._context(sample_index)
            outputs = {
                role_key: _semantic(role_key, context)
                for role_key in EXPECTED_ROLE_KEYS
            }
            record_action_case(
                run_root=self.run_root,
                sample_index=sample_index,
                semantic_outputs=outputs,
                invocation_receipts=_receipts(
                    run_root=self.run_root,
                    sample_index=sample_index,
                    outputs=outputs,
                ),
            )
        self.assertTrue(verify_action_experiment(self.run_root)["terminal"])
        with self.assertRaises(ActionExperimentStoreError):
            FrozenOutcomeDatasetAdapter(MISMATCHED_SOURCE_RUN, self.run_root)

    def test_e0b_config_policy_drift_fails_closed(self) -> None:
        value = load_json_strict(CONFIG)
        value["account_policy"] = dict(value["account_policy"])
        value["account_policy"]["maximum_stop_risk_fraction"] = "0.02"
        value = self_digest(value, "config_digest")
        drifted = Path(self.temp.name) / "drifted-config.json"
        write_once_json(drifted, value)
        with self.assertRaises(ActionExperimentStoreError):
            prepare_action_experiment(
                runtime_root=Path(self.temp.name),
                run_id="drifted-e0b",
                source_run_root=SOURCE_RUN,
                config_path=drifted,
                design_path=DESIGN,
                frozen_at="2026-08-01T10:10:00Z",
            )

        autonomy_drift = load_json_strict(CONFIG)
        autonomy_drift["agent_autonomy"] = dict(
            autonomy_drift["agent_autonomy"]
        )
        autonomy_drift["agent_autonomy"]["agent_owned"] = [
            "PATH_INTERPRETATION"
        ]
        autonomy_drift = self_digest(autonomy_drift, "config_digest")
        autonomy_path = Path(self.temp.name) / "drifted-autonomy.json"
        write_once_json(autonomy_path, autonomy_drift)
        with self.assertRaises(ActionExperimentStoreError):
            prepare_action_experiment(
                runtime_root=Path(self.temp.name),
                run_id="drifted-autonomy-e0b",
                source_run_root=SOURCE_RUN,
                config_path=autonomy_path,
                design_path=DESIGN,
                frozen_at="2026-08-01T10:15:00Z",
            )

    def test_transport_preflight_must_bind_current_packet_bytes(self) -> None:
        value = load_json_strict(CONFIG)
        value["role_contract"] = dict(value["role_contract"])
        preflight = dict(value["role_contract"]["transport_preflight"])
        preflight["packet_byte_length"] += 1
        value["role_contract"]["transport_preflight"] = preflight
        value = self_digest(value, "config_digest")
        drifted = Path(self.temp.name) / "drifted-preflight.json"
        write_once_json(drifted, value)
        rejected_run = Path(self.temp.name) / "drifted-preflight-e0b"
        with self.assertRaisesRegex(
            ActionExperimentStoreError,
            "E0B_TRANSPORT_PREFLIGHT_PACKET_BINDING_INVALID",
        ):
            prepare_action_experiment(
                runtime_root=Path(self.temp.name),
                run_id="drifted-preflight-e0b",
                source_run_root=SOURCE_RUN,
                config_path=drifted,
                design_path=DESIGN,
                frozen_at="2026-08-01T10:20:00Z",
            )
        self.assertFalse(
            (rejected_run / "frozen" / "contexts" / "sample-160.json").exists()
        )

    def test_dedicated_review_scoring_is_topology_symmetric(self) -> None:
        context = self._context(160)
        validations = {
            role_key: validate_semantic_output(
                role_key=role_key,
                output=_semantic(role_key, context),
                context=context,
            )
            for role_key in EXPECTED_ROLE_KEYS
        }
        single = arm_preoutcome_score(
            arm="SINGLE_STRONG",
            validations=tuple(
                validations[key]
                for key in (
                    "single-proposal",
                    "single-self-review",
                    "single-selection",
                )
            ),
        )
        cluster = arm_preoutcome_score(
            arm="BLIND_THREE_ROLE_CLUSTER",
            validations=tuple(
                validations[key]
                for key in (
                    "cluster-proposal",
                    "cluster-challenge",
                    "cluster-selection",
                )
            ),
        )
        self.assertEqual(
            single["preoutcome_quality_score"],
            cluster["preoutcome_quality_score"],
        )
        self.assertEqual(
            single["preoutcome_quality_maximum"],
            cluster["preoutcome_quality_maximum"],
        )

    def test_validator_rejects_invented_refs_duplicate_paths_and_ordinal_conflict(self) -> None:
        context = self._context(160)
        valid = _semantic("cluster-selection", context)

        invented_ref = deepcopy(valid)
        invented_ref["paths"][0]["hard_falsifier_refs"] = [
            "INVENTED-HARD-FALSIFIER"
        ]
        with self.assertRaisesRegex(
            ActionDiscriminationError,
            "SEMANTIC_HARD_FALSIFIER_REFS_INVALID",
        ):
            validate_semantic_output(
                role_key="cluster-selection",
                output=invented_ref,
                context=context,
            )

        duplicate_paths = deepcopy(valid)
        for row in duplicate_paths["paths"][:3]:
            row["path_id"] = "NORMAL_REBOUND_TO_T1"
        with self.assertRaisesRegex(
            ActionDiscriminationError,
            "SEMANTIC_KNOWN_PATH_SLOTS_NOT_DISTINCT",
        ):
            validate_semantic_output(
                role_key="cluster-selection",
                output=duplicate_paths,
                context=context,
            )

        ordinal_conflict = deepcopy(valid)
        selected = ordinal_conflict["selected_action"]
        for row in ordinal_conflict["action_assessments"]:
            row["ordinal"] = (
                "AVOID" if row["action_id"] == selected else "PREFERRED"
            )
        with self.assertRaisesRegex(
            ActionDiscriminationError,
            "SELECTOR_RANKING_ORDINAL_INCONSISTENT",
        ):
            validate_semantic_output(
                role_key="cluster-selection",
                output=ordinal_conflict,
                context=context,
            )

        hard_control = self._context(167)
        registered_ref = _semantic("cluster-selection", hard_control)
        registered_ref["paths"][0]["hard_falsifier_refs"] = [
            "HARD-CONTROL-REGISTERED"
        ]
        validate_semantic_output(
            role_key="cluster-selection",
            output=registered_ref,
            context=hard_control,
        )

    def test_one_hour_advantage_cannot_override_24_hour_disadvantage(self) -> None:
        events = [
            {
                "sample_index": sample_index,
                "selected_actions": {"single": "HOLD_CORE", "cluster": "EXIT_WITH_REENTRY"},
                "single_arm_score": {"preoutcome_quality_score": 42},
                "cluster_arm_score": {"preoutcome_quality_score": 42},
            }
            for sample_index in E0B_SAMPLE_INDICES
        ]
        diagnostics = []
        for sample_index in E0B_SAMPLE_INDICES:
            horizons = []
            for horizon in (1, 4, 8, 24):
                cluster_net = Decimal("1") if horizon == 1 else (
                    Decimal("-1") if horizon == 24 else ZERO
                )
                single_net = ZERO
                best = max(cluster_net, single_net)
                arms = {}
                for arm, net in (("single", single_net), ("cluster", cluster_net)):
                    arms[arm] = {
                        "decision_incremental_realized_pnl": str(net),
                        "decision_incremental_unrealized_pnl": "0",
                        "transaction_cost": "0",
                        "net_account_value_change": str(net),
                        "opportunity_loss": str(best - net),
                        "maximum_drawdown_fraction": "0",
                        "contract_comparable_for_terminal_advantage": True,
                    }
                horizons.append({"horizon_hours": horizon, "arms": arms})
            diagnostics.append(
                {
                    "sample_index": sample_index,
                    "financial_contract_version": E0B_FINANCIAL_CONTRACT,
                    "horizons": horizons,
                }
            )
        result = terminal_result(
            run_id="e0b-terminal-fixture",
            manifest_digest="a" * 64,
            event_head_digest="b" * 64,
            events=events,
            diagnostics=diagnostics,
        )
        self.assertEqual(
            result["terminal_verdict"], "INCONCLUSIVE_ACTION_TRADEOFF"
        )
        self.assertIsNone(
            result["primary_kpis"]["beneficial_intervention_count"]
        )

    def test_review_dependent_disagreement_cannot_claim_multi_horizon_advantage(self) -> None:
        events = []
        diagnostics = []
        for sample_index in E0B_SAMPLE_INDICES:
            events.append(
                {
                    "sample_index": sample_index,
                    "selected_actions": {
                        "single": "WAIT_WITH_REVIEW",
                        "cluster": "OPEN_CORE",
                    },
                    "single_arm_score": {"preoutcome_quality_score": 42},
                    "cluster_arm_score": {"preoutcome_quality_score": 42},
                }
            )
            horizons = []
            for horizon in (1, 4, 8, 24):
                arms = {}
                for arm, net in (("single", ZERO), ("cluster", Decimal("1"))):
                    arms[arm] = {
                        "decision_incremental_realized_pnl": str(net),
                        "decision_incremental_unrealized_pnl": "0",
                        "transaction_cost": "0",
                        "net_account_value_change": str(net),
                        "opportunity_loss": str(Decimal("1") - net),
                        "maximum_drawdown_fraction": "0",
                        "contract_comparable_for_terminal_advantage": (
                            not (arm == "single" and horizon > 1)
                        ),
                    }
                horizons.append({"horizon_hours": horizon, "arms": arms})
            diagnostics.append(
                {
                    "sample_index": sample_index,
                    "financial_contract_version": E0B_FINANCIAL_CONTRACT,
                    "horizons": horizons,
                }
            )
        result = terminal_result(
            run_id="e0b-review-fixture",
            manifest_digest="a" * 64,
            event_head_digest="b" * 64,
            events=events,
            diagnostics=diagnostics,
        )
        self.assertEqual(
            result["terminal_verdict"],
            "INCONCLUSIVE_SEQUENTIAL_CONTRACT_NOT_PROVEN",
        )


ZERO = Decimal("0")


if __name__ == "__main__":
    unittest.main()
