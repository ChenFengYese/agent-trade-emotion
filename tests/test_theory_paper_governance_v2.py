from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.theory_paper.governance_v2.application import audit_cycles
from trade_system.theory_paper.governance_v2.domain import (
    CARD_SCHEMA,
    FRAMEWORK_ID,
    HISTORICAL_MODE,
    GovernanceV2Error,
    build_legacy_audit_sidecar,
    canonical_digest,
    evaluate_horizon_status,
    require_valid_card,
    validate_framework_config,
    validate_governance_card,
    validate_sidecar,
)
from trade_system.theory_paper.governance_v2.infrastructure import (
    preflight_sidecar_write,
    write_sidecar,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "theory_paper_decision_governance.v2.json"
RUN_DIR = ROOT / ".runtime" / "theory-paper-v1" / "current"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def utc(hour: int) -> str:
    return datetime(2026, 7, 30, hour, tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def minimal_source(
    *,
    cycle_id: str = "cycle-0001",
    decision_at: str = utc(12),
    action: str = "KEEP",
    selected_phi: str = "PHI_DOWNWARD_CONTINUATION",
    parent_4h: str = "DOWN",
) -> dict:
    analysis_digest = "a" * 64
    decision_digest = "d" * 64
    role_states = [
        {
            "timeframe": timeframe,
            "role": role,
            "direction_state": (
                parent_4h
                if timeframe == "4h"
                else "DOWN"
                if timeframe in {"1d", "1h"}
                else "UP"
                if timeframe == "15m"
                else "UNKNOWN"
            ),
            "state_status": "OBSERVED_DERIVED",
        }
        for timeframe, role in (
            ("1w", "BACKGROUND_RISK"),
            ("1d", "STRUCTURAL_CONTEXT"),
            ("4h", "OPERATIONAL_REGIME"),
            ("1h", "SETUP"),
            ("15m", "EVALUATION_TRIGGER"),
        )
    ]
    symbol_decision = {
        "symbol": "BTCUSDT",
        "action": action,
        "selected_phi_id": selected_phi,
        "thesis": "Frozen thesis.",
        "support_predicate": {
            "observable_id": "REFERENCE_PRICE",
            "operator": "GT",
            "value": 100.0,
        },
        "falsifier_predicate": {
            "observable_id": "REFERENCE_PRICE",
            "operator": "LT",
            "value": 90.0,
        },
        "expiry_at": utc(20),
    }
    validated = {
        "cycle_id": cycle_id,
        "decision_at": decision_at,
        "decision_digest": decision_digest,
        "symbol_decisions": [symbol_decision],
        "actions": [],
    }
    return {
        "schema_version": "SourceCycleEnvelope.v1",
        "mode": HISTORICAL_MODE,
        "run_id": "run-test",
        "cycle_id": cycle_id,
        "analysis": {
            "cycle_id": cycle_id,
            "decision_at": decision_at,
            "analysis_digest": analysis_digest,
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "multi_scale_state_belief": {
                        "operational_bias": parent_4h,
                        "role_states": role_states,
                    },
                }
            ],
        },
        "decision": {
            "cycle_id": cycle_id,
            "validated_decision": validated,
            "decision_receipt_digest": "r" * 64,
        },
        "source_envelope_digest": "e" * 64,
        "source_artifacts": {"analysis.json": "a" * 64},
    }


def valid_card(source: dict) -> dict:
    config = load_config()
    decision_at = source["analysis"]["decision_at"]
    decision_time = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
    next_review = (decision_time + timedelta(hours=4)).isoformat().replace(
        "+00:00", "Z"
    )
    horizon_end = (decision_time + timedelta(hours=8)).isoformat().replace(
        "+00:00", "Z"
    )
    source_decision = source["decision"]["validated_decision"]["symbol_decisions"][0]
    card = {
        "schema_version": CARD_SCHEMA,
        "framework_id": FRAMEWORK_ID,
        "framework_config_digest": canonical_digest(config),
        "run_id": source["run_id"],
        "cycle_id": source["cycle_id"],
        "decision_at": decision_at,
        "source_analysis_digest": source["analysis"]["analysis_digest"],
        "source_decision_digest": source["decision"]["validated_decision"][
            "decision_digest"
        ],
        "previous_card_digest": None,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "hypothesis": {
                    "hypothesis_instance_id": "HYP-BTC-001",
                    "selected_phi_id": source_decision["selected_phi_id"],
                    "strategic_direction": "SHORT",
                    "state": "A_VALID",
                    "core_premise_ids": ["P1"],
                    "hard_invalidator_ids": ["I1"],
                    "review_clock": {
                        "strategic_timeframe": "4h",
                        "last_reviewed_at": decision_at,
                        "next_scheduled_review_at": next_review,
                        "current_trigger": "NO_CHANGE",
                        "qualified_event_evidence_ids": [],
                    },
                    "target_horizon": {
                        "horizon_class": "STRATEGIC",
                        "starts_at": decision_at,
                        "ends_at": horizon_end,
                        "evaluation_timeframe": "4h",
                        "minimum_complete_windows": 2,
                    },
                },
                "signals": [
                    {
                        "signal_id": "SIG-4H-1",
                        "available_at": decision_at,
                        "timeframe": "4h",
                        "signal_class": "STRUCTURAL",
                        "affects": "DIRECTION",
                        "changed_core_premise_id": None,
                        "outside_normal_range": False,
                        "persistence_observation_ids": [],
                        "independent_confirmation_group_ids": [],
                        "cause_class": "STRUCTURAL",
                        "source_ref": "analysis:BTCUSDT:4h",
                    }
                ],
                "promotion_receipts": [],
                "state_transition": {
                    "transition_id": "TR-001",
                    "from_state": "A_VALID",
                    "to_state": "A_VALID",
                    "reviewed_at": decision_at,
                    "trigger": "NO_CHANGE",
                    "evidence_signal_ids": ["SIG-4H-1"],
                    "promotion_receipt_ids": [],
                    "changed_core_premise_ids": [],
                    "hard_invalidator_ids": [],
                },
                "behavior": {
                    "action_intent": "HOLD",
                    "changes_strategic_state": False,
                    "v1_action": source_decision["action"],
                    "reentry_contract": None,
                    "evaluation_policy": {
                        "horizon_class": "STRATEGIC",
                        "correctness_eligible_at": horizon_end,
                        "before_eligibility_status": (
                            "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS"
                        ),
                        "evaluate_against_frozen_rules": True,
                        "pnl_is_strategy_validation": False,
                    },
                },
            }
        ],
    }
    card["card_digest"] = canonical_digest(card)
    return card


def redigest(card: dict) -> None:
    card.pop("card_digest", None)
    card["card_digest"] = canonical_digest(card)


class FrameworkContractTests(unittest.TestCase):
    def test_framework_config_is_valid_and_shadow_only(self) -> None:
        verdict = validate_framework_config(load_config())
        self.assertTrue(verdict["valid"])

    def test_framework_rejects_timeframe_voting(self) -> None:
        config = load_config()
        config["timeframe_role_profile"]["timeframe_voting"] = "MAJORITY"
        with self.assertRaisesRegex(
            GovernanceV2Error, "FRAMEWORK_ROLE_AUTHORITY_MISMATCH"
        ):
            validate_framework_config(config)

    def test_framework_rejects_terminal_state_reactivation(self) -> None:
        config = load_config()
        config["strategic_state_machine"]["legal_transitions"]["D_INVALIDATED"] = [
            "A_VALID"
        ]
        with self.assertRaisesRegex(
            GovernanceV2Error, "FRAMEWORK_TERMINAL_STATE_NOT_TERMINAL"
        ):
            validate_framework_config(config)

    def test_framework_rejects_psychology_fact_permission(self) -> None:
        config = load_config()
        config["invariants"]["participant_psychology_inference_as_fact"] = (
            "ALLOWED"
        )
        with self.assertRaisesRegex(
            GovernanceV2Error,
            "participant_psychology_inference_as_fact",
        ):
            validate_framework_config(config)


class LegacyAuditTests(unittest.TestCase):
    def test_legacy_cycle_preserves_unknown_state_and_reports_gaps(self) -> None:
        source = minimal_source(action="EXIT")
        sidecar = build_legacy_audit_sidecar(source, load_config())
        validate_sidecar(sidecar, load_config())
        symbol = sidecar["symbols"][0]
        self.assertEqual(
            symbol["hypothesis_ledger"]["strategic_state"],
            "UNKNOWN_LEGACY_UNDECLARED",
        )
        codes = {item["code"] for item in symbol["violations"]}
        self.assertIn("REENTRY_CONTRACT_UNREPRESENTABLE_IN_V1", codes)
        self.assertIn("EXIT_OR_REDUCTION_INTENT_UNDECLARED", codes)
        self.assertIsNone(symbol["behavior_ledger"]["reentry_contract"])

    def test_path_change_without_transition_is_detected(self) -> None:
        prior = build_legacy_audit_sidecar(minimal_source(), load_config())
        source = minimal_source(
            cycle_id="cycle-0002",
            decision_at=utc(13),
            selected_phi="PHI_RANGE",
        )
        source["analysis"]["symbols"][0]["multi_scale_state_belief"][
            "operational_bias"
        ] = "RANGE"
        sidecar = build_legacy_audit_sidecar(source, load_config(), prior)
        codes = {item["code"] for item in sidecar["symbols"][0]["violations"]}
        self.assertIn("STRATEGIC_PATH_CHANGED_WITHOUT_STATE_TRANSITION", codes)

    @unittest.skipUnless(
        (RUN_DIR / "cycles" / "cycle-0016" / "decision.json").is_file(),
        "real frozen cycle-0016 is not present",
    )
    def test_real_cycle_15_16_replay_is_read_only_and_deterministic(self) -> None:
        protected = [
            RUN_DIR / "cycles" / cycle / name
            for cycle in ("cycle-0015", "cycle-0016")
            for name in ("analysis.json", "agent-decision.json", "decision.json")
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "governance"
            first = audit_cycles(
                run_dir=RUN_DIR,
                output_dir=output,
                config_path=CONFIG_PATH,
                first_cycle="cycle-0015",
                last_cycle="cycle-0016",
            )
            second = audit_cycles(
                run_dir=RUN_DIR,
                output_dir=output,
                config_path=CONFIG_PATH,
                first_cycle="cycle-0015",
                last_cycle="cycle-0016",
            )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected
        }
        self.assertEqual(before, after)
        self.assertEqual(first["v1_mutation"], "NONE_READ_ONLY_SOURCE")
        self.assertTrue(
            all(item["status"] == "CREATED" for item in first["writes"])
        )
        self.assertTrue(
            all(
                item["status"] == "EXISTING_IDENTICAL"
                for item in second["writes"]
            )
        )
        self.assertEqual(
            [item["sidecar_digest"] for item in first["writes"]],
            [item["sidecar_digest"] for item in second["writes"]],
        )


class StrictGovernanceCardTests(unittest.TestCase):
    def test_valid_hold_card_passes(self) -> None:
        source = minimal_source()
        card = valid_card(source)
        verdict = validate_governance_card(card, source, load_config())
        self.assertTrue(verdict["valid"], verdict["errors"])
        require_valid_card(card, source, load_config())

    def test_lower_timeframe_direction_without_promotion_fails(self) -> None:
        source = minimal_source()
        card = valid_card(source)
        signal = card["symbols"][0]["signals"][0]
        signal.update(
            {
                "signal_id": "SIG-15M-1",
                "timeframe": "15m",
                "signal_class": "TACTICAL",
                "outside_normal_range": True,
                "persistence_observation_ids": ["W1"],
                "independent_confirmation_group_ids": ["G1"],
                "changed_core_premise_id": "P1",
            }
        )
        card["symbols"][0]["state_transition"]["evidence_signal_ids"] = [
            "SIG-15M-1"
        ]
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "LOWER_TIMEFRAME_DIRECTION_NOT_PROMOTED" in error
                for error in verdict["errors"]
            )
        )

    def test_parent_override_rejects_self_signed_promotion(self) -> None:
        source = minimal_source(
            action="OPEN_LONG",
            selected_phi="PHI_UPWARD_CONTINUATION",
            parent_4h="DOWN",
        )
        card = valid_card(source)
        symbol = card["symbols"][0]
        symbol["hypothesis"]["strategic_direction"] = "LONG"
        symbol["behavior"]["v1_action"] = "OPEN_LONG"
        symbol["behavior"]["action_intent"] = "STRATEGIC_ENTRY"
        signal = symbol["signals"][0]
        signal.update(
            {
                "signal_id": "SIG-15M-PROMOTED",
                "timeframe": "15m",
                "signal_class": "TACTICAL",
                "outside_normal_range": True,
                "persistence_observation_ids": ["W1", "W2"],
                "independent_confirmation_group_ids": ["FLOW", "STRUCTURE"],
                "changed_core_premise_id": "P1",
                "cause_class": "STRUCTURAL",
            }
        )
        symbol["state_transition"]["evidence_signal_ids"] = [
            "SIG-15M-PROMOTED"
        ]
        redigest(card)
        without = validate_governance_card(card, source, load_config())
        self.assertFalse(without["valid"])
        self.assertTrue(
            any(
                "PARENT_OVERRIDE_REQUIRES_PROMOTION" in error
                for error in without["errors"]
            )
        )

        conditions = load_config()["promotion_contract"][
            "all_conditions_required"
        ]
        symbol["promotion_receipts"] = [
            {
                "promotion_receipt_id": "PROMO-001",
                "signal_ids": ["SIG-15M-PROMOTED"],
                "changed_core_premise_id": "P1",
                "issued_at": source["analysis"]["decision_at"],
                "promoted_to": "STRUCTURAL_EVIDENCE",
                "condition_attestations": conditions,
            }
        ]
        symbol["state_transition"]["promotion_receipt_ids"] = ["PROMO-001"]
        redigest(card)
        with_self_signed_promotion = validate_governance_card(
            card, source, load_config()
        )
        self.assertFalse(with_self_signed_promotion["valid"])
        self.assertTrue(
            any(
                "TRUSTED_EVIDENCE_AUTHORITY_NOT_CONNECTED" in error
                for error in with_self_signed_promotion["errors"]
            )
        )

    def test_risk_exit_requires_reentry_and_trusted_executor(self) -> None:
        source = minimal_source(action="EXIT")
        card = valid_card(source)
        behavior = card["symbols"][0]["behavior"]
        behavior["v1_action"] = "EXIT"
        behavior["action_intent"] = "RISK_EXIT"
        redigest(card)
        rejected = validate_governance_card(card, source, load_config())
        self.assertFalse(rejected["valid"])
        self.assertTrue(
            any("REENTRY_CONTRACT_REQUIRED" in error for error in rejected["errors"])
        )

        behavior["reentry_contract"] = {
            "reentry_contract_id": "REENTRY-001",
            "hypothesis_instance_id": "HYP-BTC-001",
            "created_at": source["analysis"]["decision_at"],
            "default_policy": (
                "SEEK_REENTRY_WHILE_HYPOTHESIS_REMAINS_NOT_INVALIDATED"
            ),
            "minimum_condition_ids": ["RESET-1"],
            "restoration_stages": [
                "MINIMUM_VERIFICATION_POSITION",
                "STRUCTURAL_RECONFIRMATION_POSITION",
                "PLANNED_POSITION_COMPLETION",
            ],
            "price_condition": "Return to registered execution zone.",
            "time_condition": "Reassess at the next scheduled 4H close.",
            "review_by": utc(13),
            "cancel_on_state": "D_INVALIDATED",
        }
        redigest(card)
        blocked_until_executor = validate_governance_card(
            card, source, load_config()
        )
        self.assertFalse(blocked_until_executor["valid"])
        self.assertTrue(
            any(
                "REENTRY_EXECUTION_AUTHORITY_NOT_CONNECTED" in error
                for error in blocked_until_executor["errors"]
            )
        )

    def test_exit_cannot_masquerade_as_hold_to_skip_reentry(self) -> None:
        source = minimal_source(action="EXIT")
        card = valid_card(source)
        behavior = card["symbols"][0]["behavior"]
        behavior["v1_action"] = "EXIT"
        behavior["action_intent"] = "HOLD"
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "ACTION_INTENT_V1_ACTION_MISMATCH" in error
                for error in verdict["errors"]
            )
        )
        self.assertTrue(
            any("REENTRY_CONTRACT_REQUIRED" in error for error in verdict["errors"])
        )

    def test_cycle_after_genesis_requires_prior_card(self) -> None:
        source = minimal_source(cycle_id="cycle-0002")
        card = valid_card(source)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertIn("CARD:PRIOR_CARD_REQUIRED", verdict["errors"])

    def test_hypothesis_id_cannot_reset_without_creation_receipt(self) -> None:
        first_source = minimal_source()
        first_card = valid_card(first_source)
        second_source = minimal_source(
            cycle_id="cycle-0002",
            decision_at=utc(13),
        )
        second_card = valid_card(second_source)
        first_hypothesis = first_card["symbols"][0]["hypothesis"]
        second_hypothesis = second_card["symbols"][0]["hypothesis"]
        second_card["previous_card_digest"] = first_card["card_digest"]
        second_hypothesis["target_horizon"] = copy.deepcopy(
            first_hypothesis["target_horizon"]
        )
        second_hypothesis["review_clock"] = copy.deepcopy(
            first_hypothesis["review_clock"]
        )
        second_card["symbols"][0]["behavior"]["evaluation_policy"][
            "correctness_eligible_at"
        ] = first_hypothesis["target_horizon"]["ends_at"]
        redigest(second_card)
        accepted_continuity = validate_governance_card(
            second_card,
            second_source,
            load_config(),
            first_card,
        )
        self.assertTrue(
            accepted_continuity["valid"], accepted_continuity["errors"]
        )

        second_hypothesis["strategic_direction"] = "LONG"
        redigest(second_card)
        rejected_rewrite = validate_governance_card(
            second_card,
            second_source,
            load_config(),
            first_card,
        )
        self.assertFalse(rejected_rewrite["valid"])
        self.assertTrue(
            any(
                "HYPOTHESIS_IMMUTABLE_FIELD_CHANGED:strategic_direction"
                in error
                for error in rejected_rewrite["errors"]
            )
        )
        second_hypothesis["strategic_direction"] = "SHORT"
        second_hypothesis["hypothesis_instance_id"] = "HYP-BTC-RESET"
        redigest(second_card)
        rejected_reset = validate_governance_card(
            second_card,
            second_source,
            load_config(),
            first_card,
        )
        self.assertFalse(rejected_reset["valid"])
        self.assertTrue(
            any(
                "NEW_HYPOTHESIS_CREATION_RECEIPT_REQUIRED" in error
                for error in rejected_reset["errors"]
            )
        )

    def test_challenged_hypothesis_cannot_recover_on_no_change(self) -> None:
        first_source = minimal_source()
        first_card = valid_card(first_source)
        first_symbol = first_card["symbols"][0]
        first_symbol["hypothesis"]["state"] = "C_CHALLENGED"
        first_symbol["state_transition"]["to_state"] = "C_CHALLENGED"
        redigest(first_card)

        second_source = minimal_source(
            cycle_id="cycle-0002",
            decision_at=utc(13),
        )
        second_card = valid_card(second_source)
        second_symbol = second_card["symbols"][0]
        second_card["previous_card_digest"] = first_card["card_digest"]
        second_symbol["hypothesis"]["target_horizon"] = copy.deepcopy(
            first_symbol["hypothesis"]["target_horizon"]
        )
        second_symbol["hypothesis"]["review_clock"] = copy.deepcopy(
            first_symbol["hypothesis"]["review_clock"]
        )
        second_symbol["state_transition"]["from_state"] = "C_CHALLENGED"
        second_card["symbols"][0]["behavior"]["evaluation_policy"][
            "correctness_eligible_at"
        ] = first_symbol["hypothesis"]["target_horizon"]["ends_at"]
        redigest(second_card)
        verdict = validate_governance_card(
            second_card,
            second_source,
            load_config(),
            first_card,
        )
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "STRATEGIC_TRANSITION_OUTSIDE_REVIEW_CLOCK" in error
                for error in verdict["errors"]
            )
        )
        self.assertTrue(
            any(
                "STRATEGIC_RECOVERY_PREMISE_REQUIRED" in error
                for error in verdict["errors"]
            )
        )

    def test_tactical_transition_cannot_invalidate_strategy(self) -> None:
        source = minimal_source()
        card = valid_card(source)
        symbol = card["symbols"][0]
        symbol["hypothesis"]["state"] = "D_INVALIDATED"
        symbol["hypothesis"]["review_clock"]["current_trigger"] = "TACTICAL_UPDATE"
        transition = symbol["state_transition"]
        transition["to_state"] = "D_INVALIDATED"
        transition["trigger"] = "TACTICAL_UPDATE"
        transition["changed_core_premise_ids"] = ["P1"]
        transition["hard_invalidator_ids"] = ["I1"]
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "STRATEGIC_TRANSITION_OUTSIDE_REVIEW_CLOCK" in error
                for error in verdict["errors"]
            )
        )

    def test_genesis_cannot_self_declare_scheduled_invalidation(self) -> None:
        source = minimal_source(decision_at=utc(13))
        card = valid_card(source)
        symbol = card["symbols"][0]
        symbol["hypothesis"]["state"] = "D_INVALIDATED"
        symbol["hypothesis"]["review_clock"][
            "current_trigger"
        ] = "SCHEDULED_4H_CLOSE"
        transition = symbol["state_transition"]
        transition["to_state"] = "D_INVALIDATED"
        transition["trigger"] = "SCHEDULED_4H_CLOSE"
        transition["changed_core_premise_ids"] = ["P1"]
        transition["hard_invalidator_ids"] = ["I1"]
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "GENESIS_MUST_START_A_VALID_NO_CHANGE" in error
                for error in verdict["errors"]
            )
        )

    def test_behavior_never_owns_strategic_state(self) -> None:
        source = minimal_source()
        card = valid_card(source)
        card["symbols"][0]["behavior"]["changes_strategic_state"] = True
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "BEHAVIOR_MAY_NOT_OWN_STRATEGIC_STATE" in error
                for error in verdict["errors"]
            )
        )


class HorizonEvaluationTests(unittest.TestCase):
    def test_short_result_is_interim_before_declared_horizon(self) -> None:
        self.assertEqual(
            evaluate_horizon_status(
                reviewed_at=utc(13),
                correctness_eligible_at=utc(20),
                complete_windows=1,
                minimum_complete_windows=2,
                frozen_support_matched=True,
                frozen_falsifier_matched=False,
            ),
            "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS",
        )

    def test_falsifier_has_priority_at_declared_horizon(self) -> None:
        self.assertEqual(
            evaluate_horizon_status(
                reviewed_at=utc(20),
                correctness_eligible_at=utc(20),
                complete_windows=2,
                minimum_complete_windows=2,
                frozen_support_matched=True,
                frozen_falsifier_matched=True,
            ),
            "FALSIFIED_AT_DECLARED_HORIZON",
        )

    def test_elapsed_time_without_complete_windows_remains_interim(self) -> None:
        self.assertEqual(
            evaluate_horizon_status(
                reviewed_at=utc(20),
                correctness_eligible_at=utc(20),
                complete_windows=1,
                minimum_complete_windows=2,
                frozen_support_matched=True,
                frozen_falsifier_matched=False,
            ),
            "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS",
        )

    def test_strategic_horizon_cannot_be_one_minute_or_15m(self) -> None:
        source = minimal_source()
        card = valid_card(source)
        horizon = card["symbols"][0]["hypothesis"]["target_horizon"]
        horizon["ends_at"] = "2026-07-30T12:01:00Z"
        horizon["evaluation_timeframe"] = "15m"
        horizon["minimum_complete_windows"] = 99
        policy = card["symbols"][0]["behavior"]["evaluation_policy"]
        policy["correctness_eligible_at"] = horizon["ends_at"]
        redigest(card)
        verdict = validate_governance_card(card, source, load_config())
        self.assertFalse(verdict["valid"])
        self.assertTrue(
            any(
                "HORIZON_CLASS_TIMEFRAME_MISMATCH" in error
                for error in verdict["errors"]
            )
        )
        self.assertTrue(
            any(
                "HORIZON_DURATION_TOO_SHORT" in error
                for error in verdict["errors"]
            )
        )


class WriteOnceTests(unittest.TestCase):
    def test_sidecar_cannot_be_written_inside_v1_run(self) -> None:
        source = minimal_source()
        sidecar = build_legacy_audit_sidecar(source, load_config())
        with self.assertRaisesRegex(
            GovernanceV2Error, "OUTPUT_INSIDE_PROTECTED_V1_RUN"
        ):
            preflight_sidecar_write(
                source_run_dir=RUN_DIR,
                output_dir=RUN_DIR / "forbidden-governance",
                sidecar=sidecar,
            )

    def test_write_once_conflict_fails_closed(self) -> None:
        source = minimal_source()
        sidecar = build_legacy_audit_sidecar(source, load_config())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "governance"
            first = write_sidecar(
                source_run_dir=RUN_DIR,
                output_dir=output,
                sidecar=sidecar,
            )
            self.assertEqual(first["status"], "CREATED")
            second = write_sidecar(
                source_run_dir=RUN_DIR,
                output_dir=output,
                sidecar=sidecar,
            )
            self.assertEqual(second["status"], "EXISTING_IDENTICAL")
            changed = copy.deepcopy(sidecar)
            changed["summary"]["warning_violation_count"] += 1
            changed["sidecar_digest"] = canonical_digest(
                {
                    key: value
                    for key, value in changed.items()
                    if key != "sidecar_digest"
                }
            )
            with self.assertRaisesRegex(GovernanceV2Error, "WRITE_CONFLICT"):
                write_sidecar(
                    source_run_dir=RUN_DIR,
                    output_dir=output,
                    sidecar=changed,
                )

    def test_absolute_cycle_id_cannot_escape_output_root(self) -> None:
        source = minimal_source()
        sidecar = build_legacy_audit_sidecar(source, load_config())
        escaped = copy.deepcopy(sidecar)
        escaped["source"]["cycle_id"] = str(
            RUN_DIR / "injected-governance-dir"
        )
        escaped.pop("sidecar_digest")
        escaped["sidecar_digest"] = canonical_digest(escaped)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                GovernanceV2Error, "SIDECAR_CYCLE_ID_INVALID"
            ):
                preflight_sidecar_write(
                    source_run_dir=RUN_DIR,
                    output_dir=Path(tmp) / "governance",
                    sidecar=escaped,
                )


if __name__ == "__main__":
    unittest.main()
