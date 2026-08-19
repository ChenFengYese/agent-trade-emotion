from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import inspect
from pathlib import Path
import unittest
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    ANALYSIS_INTERVAL_SECONDS,
    CLOCK_DIGEST_FIELD,
    EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
    MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
    OUTCOME_ADAPTER_DIGEST_FIELD,
    OUTCOME_ADAPTER_ID,
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
    V32RuntimeSupportContractError,
    build_v32_clock_and_tick_policy_v1,
    build_v32_public_outcome_adapter_contract_v1,
    verify_v32_clock_and_tick_policy_v1,
    verify_v32_public_outcome_adapter_contract_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_runtime_clock import (
    V32RuntimeClockError,
    build_v32_system_clock_v1,
)


class V32RuntimeSupportContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = build_v32_clock_and_tick_policy_v1(
            run_scope_id="v32-scope", frozen_at="2026-08-07T00:00:00Z"
        )
        self.adapter = build_v32_public_outcome_adapter_contract_v1(
            run_scope_id="v32-scope", frozen_at="2026-08-07T00:00:00Z"
        )

    def test_round_trip_freezes_exact_clock_and_public_adapter(self) -> None:
        verify_v32_clock_and_tick_policy_v1(self.clock)
        verify_v32_public_outcome_adapter_contract_v1(self.adapter)
        self.assertEqual(self.clock["outcome_clock"]["terminal_schedule_count"], 48)
        self.assertEqual(self.adapter["request"]["requests_per_tick"], 1)
        self.assertEqual(OUTCOME_ADAPTER_ID, self.adapter["adapter_id"])
        self.assertEqual("openapi.okx.com", self.adapter["request"]["host"])
        self.assertTrue(
            self.adapter["request"]["exact_url"].startswith(
                "https://openapi.okx.com/"
            )
        )
        self.assertFalse(self.adapter["semantic_boundary"]["stop_trigger_is_fill"])
        self.assertFalse(self.adapter["executable"])
        analysis = self.clock["analysis_clock"]
        wake = self.clock["wake_boundary_policy"]
        self.assertEqual(
            TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
            sum(analysis["phase_budgets_seconds"].values()),
        )
        self.assertEqual(
            ANALYSIS_INTERVAL_SECONDS,
            analysis["total_phase_budget_seconds"]
            + analysis["earliest_outcome_grace_reserve_seconds"],
        )
        self.assertEqual(
            EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
            analysis["earliest_outcome_grace_reserve_seconds"],
        )
        self.assertEqual(
            1,
            wake["maximum_supervisor_permits_or_high_level_lane_boundaries"],
        )
        self.assertEqual(
            MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
            wake["maximum_append_only_analysis_substages"],
        )
        self.assertFalse(wake["append_only_substage_is_high_level_boundary"])

    def test_redigested_retry_clock_and_endpoint_drift_fail_closed(self) -> None:
        cases = []
        retry = deepcopy(self.adapter)
        retry["request"]["retry_count"] = 1
        cases.append((retry, OUTCOME_ADAPTER_DIGEST_FIELD, verify_v32_public_outcome_adapter_contract_v1))
        endpoint = deepcopy(self.adapter)
        endpoint["request"]["host"] = "example.com"
        cases.append((endpoint, OUTCOME_ADAPTER_DIGEST_FIELD, verify_v32_public_outcome_adapter_contract_v1))
        cadence = deepcopy(self.clock)
        cadence["analysis_clock"]["minimum_decision_spacing_seconds"] = 1
        cases.append((cadence, CLOCK_DIGEST_FIELD, verify_v32_clock_and_tick_policy_v1))
        future = deepcopy(self.clock)
        future["analysis_clock"]["future_outcomes_readable"] = True
        cases.append((future, CLOCK_DIGEST_FIELD, verify_v32_clock_and_tick_policy_v1))
        burst = deepcopy(self.clock)
        burst["wake_boundary_policy"]["maximum_append_only_analysis_substages"] = 65
        cases.append((burst, CLOCK_DIGEST_FIELD, verify_v32_clock_and_tick_policy_v1))
        reserve = deepcopy(self.clock)
        reserve["analysis_clock"]["earliest_outcome_grace_reserve_seconds"] = 0
        cases.append((reserve, CLOCK_DIGEST_FIELD, verify_v32_clock_and_tick_policy_v1))
        for document, digest_field, verifier in cases:
            with self.subTest(digest_field=digest_field):
                resigned = self_digest(document, digest_field)
                with self.assertRaises(V32RuntimeSupportContractError):
                    verifier(resigned)

    def test_canonical_time_and_exact_fields_are_required(self) -> None:
        with self.assertRaises(V32RuntimeSupportContractError):
            build_v32_clock_and_tick_policy_v1(
                run_scope_id="v32-scope",
                frozen_at="2026-08-07T08:00:00+08:00",
            )
        extra = deepcopy(self.adapter)
        extra["api_key"] = "forbidden"
        extra = self_digest(extra, OUTCOME_ADAPTER_DIGEST_FIELD)
        with self.assertRaises(V32RuntimeSupportContractError):
            verify_v32_public_outcome_adapter_contract_v1(extra)

    def test_sealed_failed_www_v1_adapter_is_read_only_legacy_evidence(self) -> None:
        project = Path(__file__).resolve().parents[1]
        paths = (
            project / ".runtime/v32/qualification/support/outcome-adapter.json",
            project
            / ".runtime/v32/qualifications/"
            "v32-qualification-btcusdt-20260808t220933z/"
            "support/outcome-adapter.json",
        )
        if not all(path.is_file() for path in paths):
            self.skipTest("sealed failed qualification is not present")
        for path in paths:
            with self.subTest(path=path):
                legacy = load_json_strict(path)
                self.assertEqual(
                    legacy[OUTCOME_ADAPTER_DIGEST_FIELD],
                    verify_v32_public_outcome_adapter_contract_v1(legacy),
                )
        forged = deepcopy(load_json_strict(paths[-1]))
        forged["run_scope_id"] = "v32-other-target"
        forged = self_digest(forged, OUTCOME_ADAPTER_DIGEST_FIELD)
        with self.assertRaises(V32RuntimeSupportContractError):
            verify_v32_public_outcome_adapter_contract_v1(forged)

    def test_production_clock_factory_has_no_injection_surface(self) -> None:
        self.assertEqual(0, len(inspect.signature(build_v32_system_clock_v1).parameters))
        clock = build_v32_system_clock_v1()
        observed = clock()
        parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)
        self.assertTrue(observed.endswith("Z"))
        self.assertFalse(clock.caller_wall_clock_injection_allowed)
        with self.assertRaises(TypeError):
            build_v32_system_clock_v1(lambda: "2026-08-07T00:00:00Z")  # type: ignore[call-arg]

    def test_production_clock_uses_monotonic_duration_and_rejects_rollback(self) -> None:
        clock = build_v32_system_clock_v1()
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure.v32_runtime_clock.time.monotonic_ns",
            side_effect=[1_000_000_000, 1_007_900_000],
        ):
            started = clock.monotonic_ns()
            self.assertEqual(7, clock.elapsed_milliseconds(started))
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure.v32_runtime_clock.time.monotonic_ns",
            return_value=999,
        ):
            with self.assertRaisesRegex(V32RuntimeClockError, "ROLLBACK"):
                clock.elapsed_milliseconds(1_000)


if __name__ == "__main__":
    unittest.main()
