from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.theory_paper.inference_v2.domain import (
    HISTORICAL_MODE,
    InferenceV2Error,
    build_cycle_sidecar,
    canonical_digest,
    derive_revision_state,
    validate_framework_config,
    validate_sidecar,
)
from trade_system.theory_paper.inference_v2.infrastructure import (
    load_framework_config,
    preflight_sidecar_write,
    write_sidecar,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "theory_paper_inference_framework.v2.json"


def _iso(hour: int, minute: int = 0) -> str:
    return (
        datetime(2026, 7, 30, hour, minute, tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _frame(
    trend: str,
    change: float,
    *,
    relative_volume: float = 1.3,
) -> dict:
    return {
        "axis_id": "K_TEST",
        "interpretation_boundary": "CLOSED_BAR_MEASURE_NOT_SIGNAL",
        "missing_fields": [],
        "observations": {
            "trend_state": trend,
            "change_1_bar_pct": change,
            "relative_volume20": relative_volume,
            "efficiency_ratio10": 0.6,
        },
        "role": "TEST",
        "source_status": "OBSERVED_CLOSED_BARS",
        "status": "OBSERVED",
    }


def source_envelope(
    *,
    cycle_number: int,
    hour: int,
    d_imbalance: float,
    oi_change: float,
    price_change: float,
) -> dict:
    observed_at = _iso(hour, 50)
    decision_at = _iso(hour, 51)
    raw_digest = canonical_digest(
        {
            "cycle_number": cycle_number,
            "d": d_imbalance,
            "oi": oi_change,
            "price_change": price_change,
        }
    )
    market_digest = canonical_digest(
        {
            "observed_at": observed_at,
            "symbols": [raw_digest],
            "failures": {},
        }
    )
    market = {
        "schema_version": "theory-paper-market-snapshot.v1",
        "observed_at": observed_at,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "observed_at": observed_at,
                "raw_digest": raw_digest,
            }
        ],
        "failures": {},
        "market_snapshot_digest": market_digest,
    }
    measurement = {
        "schema_version": "MeasurementSnapshot.v1-experimental",
        "symbol": "BTCUSDT",
        "venue": "BINANCE_USDM_PUBLIC",
        "observed_at": observed_at,
        "reference_price": 100.0 + cycle_number,
        "source_raw_digest": raw_digest,
        "measurement_snapshot_id": f"MS-{cycle_number}",
        "epistemic_status": "EXPERIMENTAL",
        "data_quality": {
            "coverage_ratio": 0.9333,
            "error_count": 1,
            "errors": {
                "liquidations": (
                    "TheoryPaperError:public market request failed: "
                    "/fapi/v1/allForceOrders"
                )
            },
            "liquidation_zero_certainty": False,
            "strict_resilience_available": False,
        },
        "axes": {
            "D": {
                "axis_id": "D_DIRECTIONAL_PRESSURE",
                "interpretation_boundary": "FLOW_PROXY_NOT_IDENTITY",
                "missing_fields": [],
                "observations": {
                    "signed_taker_imbalance": d_imbalance,
                    "hourly_taker_buy_sell_ratio": 1.1,
                },
                "status": "OBSERVED",
            },
            "L": {
                "axis_id": "L_LEVERAGE",
                "interpretation_boundary": "OI_HAS_NO_DIRECTION_TRUTH_ALONE",
                "missing_fields": [],
                "observations": {
                    "open_interest_contracts": 10000.0,
                    "open_interest_value_1h_change_pct": oi_change,
                },
                "status": "OBSERVED",
            },
            "C": {
                "axis_id": "C_CROWDING",
                "interpretation_boundary": "MULTI_PROXY_NOT_EMOTION",
                "missing_fields": [],
                "observations": {
                    "funding_rate": 0.0002,
                    "basis_bps": 6.0,
                    "global_account_long_short_ratio": 1.2,
                    "top_position_long_short_ratio": 1.1,
                },
                "status": "OBSERVED",
            },
            "F": {
                "axis_id": "F_FORCED_DELEVERAGING",
                "interpretation_boundary": "MISSING_NEVER_MEANS_ZERO",
                "missing_fields": [
                    "event_count_lower_bound",
                    "notional_lower_bound",
                    "window_status",
                ],
                "observations": {
                    "event_count_lower_bound": "UNKNOWN",
                    "notional_lower_bound": "UNKNOWN",
                    "window_status": "UNKNOWN",
                },
                "status": "UNKNOWN",
            },
            "R": {
                "axis_id": "R_LIQUIDITY_RESILIENCE",
                "interpretation_boundary": "ONE_SNAPSHOT_NOT_RESILIENCE",
                "missing_fields": ["strict_resilience_available"],
                "observations": {
                    "spread_bps": 1.0,
                    "top20_imbalance": 0.1,
                    "buy_1000_impact_bps": 2.0,
                    "sell_1000_impact_bps": -2.5,
                    "strict_resilience_available": "UNKNOWN",
                },
                "status": "PARTIAL",
            },
            "K": {
                "axis_id": "K_CLOSED_BAR_TECHNICAL",
                "interpretation_boundary": "ORDERED_ROLES_NO_VOTING",
                "status": "PARTIAL",
                "timeframes": {
                    "15m": _frame("DOWN" if price_change < 0 else "UP", price_change),
                    "1h": _frame("DOWN" if price_change < 0 else "UP", price_change / 2),
                    "4h": _frame("DOWN", -0.4),
                    "1d": _frame("DOWN", -1.0),
                    "1w": {
                        "axis_id": "K_1W",
                        "interpretation_boundary": "INSUFFICIENT_HISTORY",
                        "missing_fields": ["trend_state", "ema200"],
                        "observations": {
                            "trend_state": "UNKNOWN",
                            "ema200": "UNKNOWN",
                        },
                        "role": "BACKGROUND_RISK",
                        "source_status": "UNKNOWN",
                        "status": "UNKNOWN",
                    },
                },
            },
        },
    }
    symbol_analysis = {
        "symbol": "BTCUSDT",
        "symbol_analysis_id": f"SA-{cycle_number}",
        "measurement_snapshot": measurement,
        "news_context": {
            "status": "METADATA_AVAILABLE",
            "boundary": "HEADLINES_ARE_CONTEXT_NOT_CAUSAL_TRUTH",
            "headline_metadata": [],
        },
    }
    analysis = {
        "schema_version": "theory-paper-cycle-analysis.v1",
        "cycle_id": f"cycle-{cycle_number:04d}",
        "decision_at": decision_at,
        "method_status": "EXPERIMENTAL",
        "execution_scope": "PAPER_ONLY",
        "market_snapshot_digest": market_digest,
        "symbols": [symbol_analysis],
        "failed_market_symbols": {},
    }
    analysis["analysis_digest"] = canonical_digest(analysis)
    analysis["theory_integrity_score"] = 90.0
    return {
        "schema_version": "SourceCycleEnvelope.v1",
        "run_id": "test-run",
        "cycle_id": f"cycle-{cycle_number:04d}",
        "mode": HISTORICAL_MODE,
        "market": market,
        "news": {},
        "analysis": analysis,
        "source_committed_at": _iso(hour, 55),
        "source_artifacts": {
            "analysis.json": canonical_digest(analysis),
            "market.json": canonical_digest(market),
        },
    }


class InferenceV2DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_framework_config(CONFIG_PATH)

    def test_framework_config_is_frozen_and_valid(self) -> None:
        verdict = validate_framework_config(self.config)
        self.assertTrue(verdict["valid"])
        self.assertEqual(5, verdict["target_count"])
        self.assertEqual(10, verdict["named_path_template_count"])

    def test_first_cycle_builds_gap_evidence_and_four_path_targets(self) -> None:
        source = source_envelope(
            cycle_number=1,
            hour=1,
            d_imbalance=0.02,
            oi_change=1.0,
            price_change=0.1,
        )
        sidecar = build_cycle_sidecar(source, self.config)
        verdict = validate_sidecar(sidecar, self.config)
        self.assertTrue(verdict["valid"])
        symbol = sidecar["symbols"][0]
        kinds = {item["missing_kind"] for item in symbol["missing_data_register"]}
        self.assertEqual(
            {
                "INTERFACE_FAILURE",
                "NOT_COLLECTED",
                "INSUFFICIENT_HISTORY",
                "PUBLICLY_UNIDENTIFIABLE",
            },
            kinds,
        )
        self.assertEqual(5, len(symbol["inference_targets"]))
        for target in symbol["inference_targets"]:
            paths = target["paths"]
            self.assertEqual(4, len(paths))
            ids = {
                path["path_state"]["path_template_id"] for path in paths
            }
            self.assertTrue({"OTHER_PATH", "UNKNOWN_PATH"}.issubset(ids))
            self.assertEqual(
                "OTHER_OR_UNKNOWN",
                target["residual_nodes"]["reader_union_label"],
            )
            for path in paths:
                state = path["path_state"]
                self.assertNotIn("probability", state)
                self.assertEqual(
                    "FORBIDDEN_NOT_CALIBRATED", state["probability_status"]
                )
                self.assertEqual(
                    "NEW", path["revision"]["revision_state"]
                )

    def test_next_cycle_strengthens_forced_deleveraging_compatibility(self) -> None:
        first = build_cycle_sidecar(
            source_envelope(
                cycle_number=1,
                hour=1,
                d_imbalance=0.02,
                oi_change=1.0,
                price_change=0.1,
            ),
            self.config,
        )
        second = build_cycle_sidecar(
            source_envelope(
                cycle_number=2,
                hour=2,
                d_imbalance=-0.30,
                oi_change=-2.0,
                price_change=-2.0,
            ),
            self.config,
            first,
        )
        validate_sidecar(second, self.config, first)
        forced_target = next(
            target
            for target in second["symbols"][0]["inference_targets"]
            if target["target_id"] == "FORCED_DELEVERAGING_EXPLANATION"
        )
        forced_path = next(
            path
            for path in forced_target["paths"]
            if path["path_state"]["path_template_id"]
            == "F_FORCED_DELEVERAGING_COMPATIBLE"
        )
        self.assertEqual(
            "STRENGTHENED", forced_path["revision"]["revision_state"]
        )
        self.assertEqual(
            {"D_SHORT_WINDOW_FLOW", "L_OPEN_INTEREST", "K_15M_PRICE_RESPONSE"},
            set(forced_path["path_state"]["independent_support_groups"]),
        )
        self.assertEqual(
            "STRONG", forced_path["path_state"]["support_ordinal"]
        )
        self.assertTrue(
            second["symbols"][0]["observation_delta_from_prior_cycle"]
        )

    def test_future_measurement_fails_closed(self) -> None:
        source = source_envelope(
            cycle_number=1,
            hour=1,
            d_imbalance=0.2,
            oi_change=-1.0,
            price_change=-1.0,
        )
        source["analysis"]["symbols"][0]["measurement_snapshot"][
            "observed_at"
        ] = _iso(2, 0)
        candidate = copy.deepcopy(source["analysis"])
        candidate.pop("analysis_digest")
        candidate.pop("theory_integrity_score")
        source["analysis"]["analysis_digest"] = canonical_digest(candidate)
        with self.assertRaisesRegex(InferenceV2Error, "SOURCE_MEASUREMENT_FROM_FUTURE"):
            build_cycle_sidecar(source, self.config)

    def test_revision_state_contract_covers_all_states(self) -> None:
        current = {
            "independent_support_groups": ["A", "B"],
            "independent_contradiction_groups": [],
            "falsifier_state": "NOT_OBSERVED",
            "expires_at": _iso(10),
        }
        self.assertEqual(
            "NEW",
            derive_revision_state(None, current, _iso(2))["revision_state"],
        )

        def prior(
            support: list[str],
            against: list[str],
            *,
            expires_at: str = _iso(10),
        ) -> dict:
            state = {
                "independent_support_groups": support,
                "independent_contradiction_groups": against,
                "falsifier_state": "NOT_OBSERVED",
                "expires_at": expires_at,
            }
            return {"path_state": state, "path_state_digest": canonical_digest(state)}

        self.assertEqual(
            "STRENGTHENED",
            derive_revision_state(prior(["A"], []), current, _iso(2))[
                "revision_state"
            ],
        )
        self.assertEqual(
            "WEAKENED",
            derive_revision_state(
                prior(["A", "B", "C"], []), current, _iso(2)
            )["revision_state"],
        )
        falsified = dict(current, falsifier_state="TRIGGERED")
        self.assertEqual(
            "FALSIFIED",
            derive_revision_state(prior(["A"], []), falsified, _iso(2))[
                "revision_state"
            ],
        )
        self.assertEqual(
            "EXPIRED",
            derive_revision_state(
                prior(["A"], [], expires_at=_iso(1)), current, _iso(2)
            )["revision_state"],
        )
        self.assertEqual(
            "UNCHANGED",
            derive_revision_state(prior(["A", "B"], []), current, _iso(2))[
                "revision_state"
            ],
        )

    def test_config_rejects_missing_other_unknown_contract(self) -> None:
        config = copy.deepcopy(self.config)
        config["invariants"]["required_residual_nodes"] = ["UNKNOWN_PATH"]
        with self.assertRaisesRegex(
            InferenceV2Error, "FRAMEWORK_RESIDUAL_NODES_MISMATCH"
        ):
            validate_framework_config(config)

    def test_write_once_repository_is_idempotent_and_protects_v1_tree(self) -> None:
        sidecar = build_cycle_sidecar(
            source_envelope(
                cycle_number=1,
                hour=1,
                d_imbalance=0.2,
                oi_change=-1.0,
                price_change=-1.0,
            ),
            self.config,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "v1-run"
            source_root.mkdir()
            protected_output = source_root / "successor"
            with self.assertRaisesRegex(
                InferenceV2Error, "OUTPUT_INSIDE_PROTECTED_V1_RUN"
            ):
                preflight_sidecar_write(
                    source_run_dir=source_root,
                    output_dir=protected_output,
                    sidecar=sidecar,
                )

            output = root / "v2-shadow"
            first = write_sidecar(
                source_run_dir=source_root,
                output_dir=output,
                sidecar=sidecar,
            )
            second = write_sidecar(
                source_run_dir=source_root,
                output_dir=output,
                sidecar=sidecar,
            )
            self.assertEqual("CREATED", first["status"])
            self.assertEqual("EXISTING_IDENTICAL", second["status"])

            conflicting = copy.deepcopy(sidecar)
            conflicting["boundaries"] = [*conflicting["boundaries"], "CONFLICT"]
            with self.assertRaisesRegex(InferenceV2Error, "WRITE_CONFLICT"):
                preflight_sidecar_write(
                    source_run_dir=source_root,
                    output_dir=output,
                    sidecar=conflicting,
                )


if __name__ == "__main__":
    unittest.main()
