from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from trade_system.theory_paper_v2.application.market_cycle.forecast_qualification import (
    ForecastQualificationError,
    V340ForecastQualificationService,
)
from trade_system.theory_paper_v2.domain.market_cycle.scheduled_strategy import (
    FORECAST_OUTCOME_SCHEMA_ID,
    FORECAST_OUTCOME_SCHEMA_VERSION,
    FORECAST_SCHEMA_ID,
    FORECAST_SCHEMA_VERSION,
    ScheduledStrategyError,
    V340_THEORY_IDENTITY,
    assess_forecast_semantics,
    assess_intra_window_authority,
    build_low_token_context,
    next_committee_at,
    require_committee_slot,
    verify_low_token_context,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.strategic_state_repository import (
    FileStrategicStateRepository,
)


def _forecast(*, state_change: str = "INITIALIZE") -> dict[str, object]:
    return {
        "schema_id": FORECAST_SCHEMA_ID,
        "schema_version": FORECAST_SCHEMA_VERSION,
        "strategic_horizon_hours": 24,
        "directional_bias": "UP",
        "state_change": state_change,
        "trend_phase": "4H_PULLBACK_WITHIN_DAILY_ADVANCE",
        "causal_thesis": "4H demand remains accepted while leverage resets inside the prior expansion.",
        "alternative_thesis": "The pullback is distribution and the daily advance is failing.",
        "if_then_paths": [
            "IF 4H demand is re-accepted THEN price should revisit the prior high before the strategic floor fails.",
            "IF the 4H strategic floor is accepted below THEN the continuation path is invalidated and the alternative strengthens.",
        ],
        "participant_analysis": [
            "Recent longs have unrealized profit to protect while trapped shorts may cover if the prior high is accepted again."
        ],
        "catalyst_analysis": "NONE_OBSERVED in the admitted packet; unexpected news remains UNKNOWN until the next committee.",
        "sentiment_analysis": "Positioning is supportive but proxy-only; participant identity is UNKNOWN.",
        "data_quality_analysis": "Closed bars and price are current; participant identity and full liquidation flow are not observed.",
        "future_space_analysis": "The first upside zone is 108-112; the right tail remains conditional on fresh 4H acceptance.",
        "data_conflicts": ["OI is firm while taker flow is mixed; this may be hedging or opposing cohorts rather than one actor."],
        "next_discriminating_observation": "The next 4H close relative to the strategic floor and prior-high acceptance.",
        "timeframe_zones": {
            "15m": {
                "lower": "98",
                "upper": "101",
                "authority": "EVIDENCE",
                "meaning": "Internal path and execution-resolution zone.",
                "break_effect": "Evidence only; no independent LLM market action.",
            },
            "1h": {
                "lower": "96",
                "upper": "103",
                "authority": "EVIDENCE",
                "meaning": "Internal hypothesis evidence within the 4H decision window.",
                "break_effect": "May weaken the next committee thesis but cannot wake the LLM by itself.",
            },
            "4h": {
                "lower": "94",
                "upper": "108",
                "authority": "DECISION",
                "meaning": "Minimum market-decision authority and CORE thesis range.",
                "break_effect": "The next committee may invalidate or replace the strategic thesis.",
            },
            "1d": {
                "lower": "88",
                "upper": "120",
                "authority": "REGIME",
                "meaning": "Daily regime boundary.",
                "break_effect": "A daily regime change requires strategic rebuild at a committee.",
            },
        },
        "horizons": {
            "4h": {
                "expected_direction": "UP",
                "path": "Hold the pullback floor and recover toward 104-106.",
                "target_lower": "104",
                "target_upper": "106",
                "invalidation_condition": "A valid 4H acceptance below the strategic floor.",
            },
            "12h": {
                "expected_direction": "UP",
                "path": "Continuation should retest the prior expansion high.",
                "target_lower": "108",
                "target_upper": "112",
                "invalidation_condition": "Repeated 4H failure below the reclaimed range.",
            },
            "24h": {
                "expected_direction": "UP",
                "path": "If acceptance persists, the right tail can extend beyond the prior high.",
                "target_lower": "110",
                "target_upper": "118",
                "invalidation_condition": "Daily structure rotates below the strategic range.",
            },
        },
    }


def _outcome() -> dict[str, object]:
    return {
        "schema_id": FORECAST_OUTCOME_SCHEMA_ID,
        "schema_version": FORECAST_OUTCOME_SCHEMA_VERSION,
        "reference_price": "100",
        "source_refs": ["sealed/hype/outcome-24h.json"],
        "horizons": {
            "4h": {"observed_at": "2026-08-17T12:00:00Z", "close": "105", "high": "106", "low": "98"},
            "12h": {"observed_at": "2026-08-17T20:00:00Z", "close": "109", "high": "111", "low": "98"},
            "24h": {"observed_at": "2026-08-18T08:00:00Z", "close": "113", "high": "116", "low": "97"},
        },
    }


class V340ScheduledStrategyTests(unittest.TestCase):
    def test_fixed_four_hour_slots_are_external_time_authority(self) -> None:
        self.assertEqual(require_committee_slot("2026-08-17T08:00:00Z"), "2026-08-17T08:00:00Z")
        self.assertEqual(next_committee_at("2026-08-17T08:00:00Z"), "2026-08-17T12:00:00Z")
        with self.assertRaisesRegex(ScheduledStrategyError, "NOT_FIXED_4H_UTC_SLOT"):
            require_committee_slot("2026-08-17T09:00:00Z")

    def test_forecast_requires_four_hour_or_longer_horizon(self) -> None:
        payload = _forecast()
        payload["strategic_horizon_hours"] = 1
        assessment = assess_forecast_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("strategic_horizon_hours:MUST_BE_INTEGER_AT_LEAST_4", assessment.errors)

    def test_forecast_requires_4h_12h_24h_paths(self) -> None:
        payload = _forecast()
        del payload["horizons"]["12h"]
        assessment = assess_forecast_semantics(payload)
        self.assertFalse(assessment.ready)
        self.assertIn("horizons.12h:REQUIRED_OBJECT", assessment.errors)

    def test_llm_cannot_change_market_position_between_committees(self) -> None:
        denied = assess_intra_window_authority(actor="LLM", action="EXIT")
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "LLM_MARKET_ACTION_DENIED_UNTIL_NEXT_4H_COMMITTEE")
        self.assertTrue(assess_intra_window_authority(actor="LLM", action="HOLD").allowed)

    def test_local_executor_can_only_execute_frozen_committee_actions(self) -> None:
        self.assertTrue(
            assess_intra_window_authority(
                actor="LOCAL_EXECUTOR", action="HARVEST", preauthorized_by_committee=True
            ).allowed
        )
        self.assertFalse(
            assess_intra_window_authority(
                actor="LOCAL_EXECUTOR", action="ADD", preauthorized_by_committee=False
            ).allowed
        )

    def test_safety_system_can_only_de_risk(self) -> None:
        self.assertTrue(
            assess_intra_window_authority(actor="SAFETY_SYSTEM", action="EXIT", emergency=True).allowed
        )
        self.assertFalse(
            assess_intra_window_authority(actor="SAFETY_SYSTEM", action="ADD", emergency=True).allowed
        )

    def test_low_token_context_contains_only_one_previous_state_and_delta(self) -> None:
        packet = build_low_token_context(
            asset_id="BTC-USDT-SWAP",
            committee_slot_at="2026-08-17T08:00:00Z",
            input_cutoff_at="2026-08-17T07:59:59Z",
            reference_price="100",
            theory_identity=V340_THEORY_IDENTITY,
            shared_context_summary={"risk_regime": "RISK_ON"},
            asset_delta_summary={"last_4h": "range expansion"},
            portfolio_summary={"position": "FLAT"},
            previous_state_summary={"committee_slot_at": "2026-08-17T04:00:00Z", "state_change": "KEEP"},
            source_refs=["raw/btc-4h.json"],
        )
        self.assertEqual(packet["mode"], "FORECAST_ONLY")
        self.assertEqual(packet["next_committee_at"], "2026-08-17T12:00:00Z")
        self.assertNotIn("history", packet)
        self.assertLess(packet["context_size_bytes"], 64 * 1024)



    def test_low_token_context_requires_current_theory_identity_and_source_refs(self) -> None:
        kwargs = dict(
            asset_id="BTC-USDT-SWAP",
            committee_slot_at="2026-08-17T08:00:00Z",
            input_cutoff_at="2026-08-17T08:00:00Z",
            reference_price="100",
            shared_context_summary={"risk_regime": "RANGE"},
            asset_delta_summary={"last_4h": "balanced"},
            portfolio_summary={"position": "FLAT"},
            previous_state_summary=None,
        )
        with self.assertRaisesRegex(ScheduledStrategyError, "CURRENT_V340_IDENTITY_REQUIRED"):
            build_low_token_context(theory_identity="wrong", source_refs=["sealed/input.json"], **kwargs)
        with self.assertRaisesRegex(ScheduledStrategyError, "NONEMPTY_VALID_REFS_REQUIRED"):
            build_low_token_context(theory_identity=V340_THEORY_IDENTITY, source_refs=[], **kwargs)

    def test_low_token_context_detects_post_build_mutation(self) -> None:
        packet = build_low_token_context(
            asset_id="BTC-USDT-SWAP",
            committee_slot_at="2026-08-17T08:00:00Z",
            input_cutoff_at="2026-08-17T08:00:00Z",
            reference_price="100",
            theory_identity=V340_THEORY_IDENTITY,
            shared_context_summary={"risk_regime": "RANGE"},
            asset_delta_summary={"last_4h": "balanced"},
            portfolio_summary={"position": "FLAT"},
            previous_state_summary=None,
            source_refs=["sealed/context.json"],
        )
        verify_low_token_context(packet)
        packet["asset_delta_summary"]["last_4h"] = "mutated"
        with self.assertRaisesRegex(ScheduledStrategyError, "MISMATCH"):
            verify_low_token_context(packet)

    def test_low_token_context_fails_closed_when_budget_is_exceeded(self) -> None:
        with self.assertRaisesRegex(ScheduledStrategyError, "BYTE_BUDGET_EXCEEDED"):
            build_low_token_context(
                asset_id="BTC-USDT-SWAP",
                committee_slot_at="2026-08-17T08:00:00Z",
                input_cutoff_at="2026-08-17T08:00:00Z",
                reference_price="100",
                theory_identity=V340_THEORY_IDENTITY,
                shared_context_summary={"blob": "x" * 5000},
                asset_delta_summary={},
                portfolio_summary={},
                previous_state_summary=None,
                source_refs=["sealed/context.json"],
                max_utf8_bytes=4096,
            )


class V340ForecastQualificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = FileStrategicStateRepository(self.root)
        self.service = V340ForecastQualificationService(self.repository)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _context(self, slot: str) -> dict[str, object]:
        return self.service.build_context(
            asset_id="HYPE-USDT-SWAP",
            committee_slot_at=slot,
            input_cutoff_at=slot,
            reference_price="100",
            theory_identity=V340_THEORY_IDENTITY,
            shared_context_summary={"btc_regime": "RANGE"},
            asset_delta_summary={"new_4h": "pullback then recovery"},
            portfolio_summary={"mode": "FORECAST_ONLY", "position": "NONE"},
            source_refs=["sealed/hype/input.json"],
        )


    def test_service_rejects_context_from_another_asset(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        with self.assertRaisesRegex(ForecastQualificationError, "ASSET_ID_MISMATCH"):
            self.service.seal_forecast(
                asset_id="BTC-USDT-SWAP",
                context=context,
                agent_text="wrong asset",
                forecast=_forecast(),
            )

    def test_service_rejects_context_mutated_after_build(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        context["asset_delta_summary"]["new_4h"] = "tampered"
        with self.assertRaisesRegex(ForecastQualificationError, "MISMATCH"):
            self.service.seal_forecast(
                asset_id="HYPE-USDT-SWAP",
                context=context,
                agent_text="tampered context",
                forecast=_forecast(),
            )



    def test_reference_price_is_frozen_inside_context_and_forecast_record(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        self.assertEqual(context["reference_price"], "100")
        record = self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP", context=context, agent_text="reference bound", forecast=_forecast()
        )
        self.assertEqual(record["reference_price"], "100")

    def test_forecast_records_observed_model_token_usage_without_estimating_cost(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        record = self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=context,
            agent_text="measured forecast",
            forecast=_forecast(),
            model_usage={
                "model_id": "provider-model-id",
                "source_ref": "provider/usage/slot-0800.json",
                "input_tokens": 1200,
                "output_tokens": 300,
                "cached_input_tokens": 400,
            },
        )
        self.assertEqual(record["model_usage"]["total_tokens"], 1500)
        self.assertEqual(record["model_usage"]["cached_input_tokens"], 400)

    def test_forecast_keeps_model_usage_unknown_when_provider_usage_is_unavailable(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        record = self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=context,
            agent_text="usage unavailable",
            forecast=_forecast(),
        )
        self.assertEqual(record["model_usage"], {"status": "UNKNOWN"})

    def test_first_forecast_is_durable_and_has_no_execution_authority(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        record = self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=context,
            agent_text="4H scheduled forecast; no execution authority.",
            forecast=_forecast(),
        )
        self.assertEqual(record["execution_authority"], "NONE")
        latest = self.repository.latest_forecast("HYPE-USDT-SWAP")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["committee_slot_at"], "2026-08-17T08:00:00Z")

    def test_second_forecast_must_continue_state_not_reinitialize(self) -> None:
        first_context = self._context("2026-08-17T08:00:00Z")
        self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=first_context,
            agent_text="initial state",
            forecast=_forecast(),
        )
        second_context = self._context("2026-08-17T12:00:00Z")
        with self.assertRaisesRegex(ForecastQualificationError, "INITIALIZE_ONLY_FOR_FIRST_STATE"):
            self.service.seal_forecast(
                asset_id="HYPE-USDT-SWAP",
                context=second_context,
                agent_text="bad reset",
                forecast=_forecast(),
            )
        continued = _forecast(state_change="KEEP")
        record = self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=second_context,
            agent_text="continue prior strategic state",
            forecast=continued,
        )
        self.assertEqual(record["previous_state_ref"]["committee_slot_at"], "2026-08-17T08:00:00Z")


    def test_next_context_carries_complete_strategic_summary_not_only_price_zones(self) -> None:
        first_context = self._context("2026-08-17T08:00:00Z")
        self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP", context=first_context, agent_text="initial", forecast=_forecast()
        )
        second = self._context("2026-08-17T12:00:00Z")
        prior = second["previous_strategic_state"]
        self.assertEqual(prior["participant_analysis"], _forecast()["participant_analysis"])
        self.assertEqual(prior["catalyst_analysis"], _forecast()["catalyst_analysis"])
        self.assertEqual(prior["sentiment_analysis"], _forecast()["sentiment_analysis"])
        self.assertEqual(prior["data_conflicts"], _forecast()["data_conflicts"])
        self.assertEqual(prior["future_space_analysis"], _forecast()["future_space_analysis"])

    def test_service_rejects_non_committee_slot_before_agent_work(self) -> None:
        with self.assertRaisesRegex(ForecastQualificationError, "NOT_FIXED_4H_UTC_SLOT"):
            self._context("2026-08-17T10:00:00Z")


    def test_outcome_must_bind_forecast_reference_and_exact_horizon_times(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP", context=context, agent_text="forecast", forecast=_forecast()
        )
        wrong_reference = _outcome()
        wrong_reference["reference_price"] = "101"
        with self.assertRaisesRegex(ForecastQualificationError, "FORECAST_REFERENCE_MISMATCH"):
            self.service.seal_outcome(
                asset_id="HYPE-USDT-SWAP", committee_slot_at="2026-08-17T08:00:00Z", observed_through_at="2026-08-18T08:00:00Z", outcome=wrong_reference
            )
        wrong_time = _outcome()
        wrong_time["horizons"]["4h"]["observed_at"] = "2026-08-17T12:01:00Z"
        with self.assertRaisesRegex(ForecastQualificationError, "EXPECTED_EXACT_HORIZON"):
            self.service.seal_outcome(
                asset_id="HYPE-USDT-SWAP", committee_slot_at="2026-08-17T08:00:00Z", observed_through_at="2026-08-18T08:00:00Z", outcome=wrong_time
            )

    def test_complete_24h_outcome_produces_objective_forecast_evaluation(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=context,
            agent_text="forecast",
            forecast=_forecast(),
        )
        evaluation = self.service.seal_outcome(
            asset_id="HYPE-USDT-SWAP",
            committee_slot_at="2026-08-17T08:00:00Z",
            observed_through_at="2026-08-18T08:00:00Z",
            outcome=_outcome(),
        )
        results = evaluation["evaluation"]["results"]
        self.assertEqual(results["4h"]["direction_match"], "MATCH")
        self.assertTrue(results["12h"]["target_touched"])
        self.assertEqual(results["24h"]["mfe"], "16")
        self.assertEqual(results["24h"]["mae"], "3")

    def test_outcome_cannot_be_scored_before_full_24h_window(self) -> None:
        context = self._context("2026-08-17T08:00:00Z")
        self.service.seal_forecast(
            asset_id="HYPE-USDT-SWAP",
            context=context,
            agent_text="forecast",
            forecast=_forecast(),
        )
        with self.assertRaisesRegex(ForecastQualificationError, "FULL_24H_OUTCOME_REQUIRED"):
            self.service.seal_outcome(
                asset_id="HYPE-USDT-SWAP",
                committee_slot_at="2026-08-17T08:00:00Z",
                observed_through_at="2026-08-17T12:00:00Z",
                outcome=_outcome(),
            )


if __name__ == "__main__":
    unittest.main()
