from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import unittest

from trade_system.theory_paper_v2.domain.market_cycle.strategic_control import (
    assess_strategic_semantics,
)


ROOT = Path(__file__).resolve().parents[1]


def _payload(*, action: str = "OPEN", role: str = "CORE") -> dict[str, object]:
    return {
        "schema_id": "agent-trade-emotion.v340-strategic-semantics",
        "schema_version": "1.1.0",
        "strategic_horizon_hours": 12,
        "action": action,
        "position_role": role,
        "trend_phase": "PULLBACK_WITHIN_4H_ADVANCE",
        "causal_thesis": "4H demand remains accepted while 1H pullback resets leverage.",
        "alternative_thesis": "The apparent reset is distribution before a 4H reversal.",
        "if_then_paths": [
            "IF 1H reclaims the pullback pivot THEN continuation toward the 4H target remains live.",
            "IF 4H closes below strategic support THEN the CORE thesis is invalidated.",
        ],
        "participant_analysis": [
            "Recent longs may harvest at the prior high; trapped shorts may cover on renewed 4H acceptance."
        ],
        "catalyst_analysis": "UNKNOWN: no admitted event source changes the current thesis.",
        "sentiment_analysis": "Attention is elevated but is only a positioning proxy, not participant truth.",
        "data_quality_analysis": "Price and bar data are current; participant identity remains UNKNOWN and proxy-only.",
        "future_space_analysis": "Primary target is 115; right-tail extension remains conditional on fresh 4H acceptance rather than assumed.",
        "data_conflicts": ["NONE_OBSERVED_WITHIN_ADMITTED_DATA"],
        "pnl": {
            "realized": "2.5",
            "unrealized": "-0.5",
            "realization_effect_of_selected_action": "Opening a new tranche does not realize the current reference PnL.",
        },
        "timeframe_zones": {
            "15m": {
                "lower": "99",
                "upper": "101",
                "authority": "EVIDENCE",
                "meaning": "Local activation and execution zone.",
                "break_effect": "Local warning only unless higher frames confirm.",
            },
            "1h": {
                "lower": "96",
                "upper": "102",
                "authority": "EVIDENCE",
                "meaning": "Pullback and continuation decision zone.",
                "break_effect": "Damage continuation thesis and freeze ADD pending 4H confirmation.",
            },
            "4h": {
                "lower": "94",
                "upper": "106",
                "authority": "DECISION",
                "meaning": "CORE strategic corridor.",
                "break_effect": "A valid close below support can invalidate the CORE thesis.",
            },
            "1d": {
                "lower": "88",
                "upper": "120",
                "authority": "REGIME",
                "meaning": "Daily regime and tail-risk boundary.",
                "break_effect": "Rebuild the strategic episode if the daily regime changes.",
            },
        },
        "action_comparison": {
            "WAIT": "Inferior if 1H reclaim is already confirmed; otherwise valid.",
            "HOLD": "Applicable to existing CORE only.",
            "ADD": "Only on fresh 1H/4H confirmation with recomputed episode risk.",
            "REDUCE": "Valid if 1H damage increases while 4H remains intact.",
            "HARVEST": "Valid after a material target or when continuation weakens with profit available.",
            "EXIT": "Reserved for 4H invalidation or a separately declared emergency.",
        },
        "position_plan": {
            "plan_revision_policy": "FROZEN_UNTIL_NEXT_4H_COMMITTEE",
            "intra_window_execution_policy": "Only the local executor may carry out these already-declared conditions; the LLM cannot revise them before the next 4H committee.",
            "add_condition": "Fresh 1H reclaim confirmed by 4H continuation evidence.",
            "add_quantity": "0.5",
            "reduce_condition": "1H thesis damage while 4H support remains intact.",
            "reduce_quantity": "0.5",
            "harvest_condition": "Primary extension is reached while right-tail evidence remains live.",
            "harvest_quantity": "0.5",
            "runner_quantity": "1",
        },
        "management_matrix": {
            "15m": {
                "response": "REVIEW",
                "emergency": False,
                "reason": "Local warning only.",
                "size_effect": "No CORE quantity change.",
                "risk_if_waiting": "Remain inside the predeclared 1H/4H risk envelope.",
            },
            "1h": {
                "response": "FREEZE_ADD",
                "emergency": False,
                "reason": "Wait for 4H if continuation is damaged.",
                "size_effect": "Freeze ADD; optionally reduce the declared 0.5 tranche if damage persists.",
                "risk_if_waiting": "Accept only the remaining risk to the 4H strategic invalidation.",
            },
            "4h": {
                "response": "EXIT_CORE",
                "emergency": False,
                "reason": "Strategic invalidation owns ordinary CORE exit.",
                "size_effect": "Exit the remaining CORE quantity.",
                "risk_if_waiting": "Waiting beyond this close would exceed the declared strategic thesis boundary.",
            },
            "1d": {
                "response": "REBUILD",
                "emergency": False,
                "reason": "Daily regime break requires a new episode.",
                "size_effect": "No legacy CORE is carried through an unreviewed regime break.",
                "risk_if_waiting": "Tail risk becomes unbounded by the old episode assumptions.",
            },
        },
        "attention": {
            "scheduler_policy": "FIXED_4H_UTC",
            "next_observation": "Observe 1H/15m internally, but the next LLM market decision is the fixed 4H committee.",
            "high_value_windows": ["4H close", "first retest of strategic support"],
            "low_value_conditions": ["15m chop away from strategic zones with no event"],
            "activity_windows": [
                {
                    "window": "UTC 12:00-16:00",
                    "weight": "HIGH",
                    "basis": "Example PIT activity profile shows larger recent range/volume in this window; re-estimate when regime changes.",
                },
                {
                    "window": "UTC 02:00-05:00",
                    "weight": "LOW",
                    "basis": "Example profile is lower-information unless a strategic zone or event overrides it.",
                },
            ],
        },
        "payoff": {
            "side": "LONG",
            "entry_price": "100",
            "strategic_invalidation_price": "95",
            "catastrophic_protection_price": "94",
            "maximum_adverse_price_before_next_committee": "96",
            "primary_target_price": "115",
            "quantity": "2",
            "contract_multiplier": "1",
            "round_trip_cost_stress": "1",
            "gap_impact_stress": "0.5",
            "maximum_loss_budget": "14",
        },
    }


class V340StrategicControlTests(unittest.TestCase):
    def test_ready_open_keeps_realized_and_unrealized_separate_and_recomputes_payoff(self) -> None:
        assessment = assess_strategic_semantics(_payload())
        self.assertTrue(assessment.ready)
        self.assertEqual(assessment.metrics["realized_pnl"], "2.5")
        self.assertEqual(assessment.metrics["unrealized_pnl"], "-0.5")
        self.assertEqual(assessment.metrics["marked_pnl"], "2.0")
        self.assertEqual(assessment.metrics["gross_risk"], "10")
        self.assertEqual(assessment.metrics["gross_reward"], "30")
        self.assertEqual(assessment.metrics["strategic_net_risk_stress"], "11.5")
        self.assertEqual(assessment.metrics["catastrophic_risk_stress"], "13.5")
        self.assertEqual(assessment.metrics["wait_to_next_committee_risk_stress"], "9.5")
        self.assertEqual(assessment.metrics["net_reward_reference"], "29")
        self.assertEqual(assessment.metrics["reward_risk_ratio"], "2.521739")

    def test_open_requires_four_timeframe_zones(self) -> None:
        payload = _payload()
        del payload["timeframe_zones"]["1d"]
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("timeframe_zones.1d:REQUIRED_OBJECT", assessment.errors)

    def test_core_cannot_use_ordinary_15m_exit_all(self) -> None:
        payload = _payload()
        payload["management_matrix"]["15m"] = {
            "response": "EXIT_ALL",
            "emergency": False,
            "reason": "One 15m support broke.",
            "size_effect": "Exit all CORE quantity.",
            "risk_if_waiting": "The local move alone does not establish higher-frame risk.",
        }
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "management_matrix.15m:CORE_EXIT_REQUIRES_EMERGENCY_OR_4H_COMMITTEE",
            assessment.errors,
        )

    def test_emergency_15m_exit_is_distinct_and_allowed(self) -> None:
        payload = _payload(action="EXIT")
        payload["management_matrix"]["15m"] = {
            "response": "EXIT_ALL",
            "emergency": True,
            "reason": "Predeclared catastrophic risk condition, not an ordinary market break.",
            "size_effect": "Exit all exposure under the emergency contract.",
            "risk_if_waiting": "Waiting violates the predeclared catastrophic loss boundary.",
        }
        assessment = assess_strategic_semantics(payload)
        self.assertTrue(assessment.ready)


    def test_core_cannot_use_ordinary_1h_exit_all(self) -> None:
        payload = _payload()
        payload["management_matrix"]["1h"] = {
            "response": "EXIT_ALL",
            "emergency": False,
            "reason": "One 1H range broke.",
            "size_effect": "Exit all CORE quantity.",
            "risk_if_waiting": "This remains evidence until the next 4H committee.",
        }
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "management_matrix.1h:CORE_EXIT_REQUIRES_EMERGENCY_OR_4H_COMMITTEE",
            assessment.errors,
        )

    def test_exposure_plan_is_frozen_until_next_committee(self) -> None:
        payload = _payload()
        payload["position_plan"]["plan_revision_policy"] = "AGENT_MAY_REVISE_ANYTIME"
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "position_plan.plan_revision_policy:EXPECTED_FROZEN_UNTIL_NEXT_4H_COMMITTEE",
            assessment.errors,
        )

    def test_catastrophic_and_wait_to_committee_risk_must_fit_budget(self) -> None:
        payload = _payload()
        payload["payoff"]["catastrophic_protection_price"] = "90"
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("payoff:CATASTROPHIC_RISK_EXCEEDS_MAXIMUM_LOSS_BUDGET", assessment.errors)

    def test_exposure_increase_below_four_hour_horizon_is_not_ready(self) -> None:
        payload = _payload()
        payload["strategic_horizon_hours"] = 1
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "strategic_horizon_hours:MUST_BE_INTEGER_AT_LEAST_4",
            assessment.errors,
        )

    def test_exposure_increase_rejects_risk_above_declared_budget(self) -> None:
        payload = _payload()
        payload["payoff"]["maximum_loss_budget"] = "11"
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("payoff:STRATEGIC_NET_RISK_EXCEEDS_MAXIMUM_LOSS_BUDGET", assessment.errors)

    def test_wait_can_be_semantically_ready_without_trade_payoff(self) -> None:
        payload = _payload(action="WAIT", role="CASH")
        payload.pop("payoff")
        payload["pnl"]["realization_effect_of_selected_action"] = "No position is being realized."
        assessment = assess_strategic_semantics(payload)
        self.assertTrue(assessment.ready)
        self.assertNotIn("gross_risk", assessment.metrics)

    def test_action_comparison_cannot_silently_drop_harvest_or_reduce(self) -> None:
        payload = deepcopy(_payload())
        del payload["action_comparison"]["HARVEST"]
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "action_comparison.HARVEST:REQUIRED_NONEMPTY_TEXT",
            assessment.errors,
        )

    def test_data_quality_and_future_space_cannot_be_implicit(self) -> None:
        payload = _payload()
        payload["data_quality_analysis"] = ""
        payload["future_space_analysis"] = ""
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("data_quality_analysis:REQUIRED_NONEMPTY_TEXT", assessment.errors)
        self.assertIn("future_space_analysis:REQUIRED_NONEMPTY_TEXT", assessment.errors)

    def test_exposure_requires_conditional_tranche_plan(self) -> None:
        payload = _payload()
        del payload["position_plan"]
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("position_plan:REQUIRED_OBJECT", assessment.errors)

    def test_management_requires_size_effect_and_waiting_risk(self) -> None:
        payload = _payload()
        del payload["management_matrix"]["1h"]["size_effect"]
        del payload["management_matrix"]["1h"]["risk_if_waiting"]
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "management_matrix.1h.size_effect:REQUIRED_NONEMPTY_TEXT",
            assessment.errors,
        )
        self.assertIn(
            "management_matrix.1h.risk_if_waiting:REQUIRED_NONEMPTY_TEXT",
            assessment.errors,
        )

    def test_activity_profile_is_required_for_interaction_weighting(self) -> None:
        payload = _payload()
        del payload["attention"]["activity_windows"]
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("attention.activity_windows:REQUIRED_NONEMPTY_ARRAY", assessment.errors)

    def test_harvest_and_runner_quantities_cannot_exceed_position_quantity(self) -> None:
        payload = _payload()
        payload["position_plan"]["runner_quantity"] = "2.5"
        assessment = assess_strategic_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn(
            "position_plan.runner_quantity:CANNOT_EXCEED_PAYOFF_QUANTITY",
            assessment.errors,
        )

    def test_v340_manifest_binds_exact_overlay_documents(self) -> None:
        manifest_path = ROOT / "theory" / "versions" / "v3.4.0" / "MANIFEST.json"
        raw = manifest_path.read_bytes()
        self.assertEqual(len(raw), 4328)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "1e7c3512c0cbd7de07d0b4c648bb65a9e668c27917297ee2ddc1c6b62a7bfe56",
        )
        manifest = json.loads(raw)
        self.assertEqual(manifest["document_count"], 7)
        for document in manifest["documents"]:
            doc_raw = manifest_path.parent.joinpath(document["path"]).read_bytes()
            self.assertEqual(len(doc_raw), document["size_bytes"])
            self.assertEqual(hashlib.sha256(doc_raw).hexdigest(), document["sha256"])


if __name__ == "__main__":
    unittest.main()
