from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    DIGEST_FIELD,
    HYPOTHESIS_TYPES,
    PATH_MODIFIER_TYPES,
    UNKNOWN_BEHAVIOR_EFFECT,
    UNKNOWN_TYPES,
    V32DynamicResearchError,
    ZONE_PATH_ROLES,
    build_v32_dynamic_research_state_v1,
    verify_v32_dynamic_research_state_v1,
)


INSTRUMENT = "BTC-USDT-SWAP"
AS_OF = "2026-08-07T00:00:00Z"
EXPIRES = "2026-08-07T04:00:00Z"


def _hypothesis(
    hypothesis_id: str,
    hypothesis_type: str,
    direction: str,
    tier: str,
    dependency_group: str,
    *,
    opposition_ids: list[str] | None = None,
    alternative_ids: list[str] | None = None,
    horizon_seconds: int = 3600,
) -> dict[str, object]:
    independent_group = f"{dependency_group}:independent"
    high_family_pairs = {
        "dep:state": (
            "OBSERVABLE_FAMILY:POSITIONING",
            "OBSERVABLE_FAMILY:TRADE_FLOW",
        ),
        "dep:zone": (
            "OBSERVABLE_FAMILY:PRICE_ACTION",
            "OBSERVABLE_FAMILY:FUNDING_CROWDING",
        ),
    }
    dependency_groups = {dependency_group, independent_group}
    if dependency_group in high_family_pairs:
        dependency_groups.update(
            {
                f"REQUEST:FIXTURE:{dependency_group}",
                f"REQUEST:FIXTURE:{independent_group}",
                *high_family_pairs[dependency_group],
            }
        )
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_type": hypothesis_type,
        "direction": direction,
        "scope": INSTRUMENT,
        "regime_scope": ["INTRADAY", "RANGE_TRANSITION"],
        "mechanism": f"mechanism:{hypothesis_id}",
        "horizon_seconds": horizon_seconds,
        "source_refs": [
            f"source:{hypothesis_id}",
            f"source-independent:{hypothesis_id}",
        ],
        "dependency_groups": sorted(dependency_groups),
        "supporting_refs": [
            f"support:{hypothesis_id}",
            f"support-independent:{hypothesis_id}",
        ],
        "opposing_refs": [f"contrary:{hypothesis_id}"],
        "opposition_ids": opposition_ids or [],
        "alternative_ids": alternative_ids or [],
        "hard_falsifiers": [f"falsifier:{hypothesis_id}"],
        "soft_contradictions": [f"soft:{hypothesis_id}"],
        "path_modifier_ids": [],
        "next_observation": f"observe:{hypothesis_id}",
        "expires_at": EXPIRES,
        "previous_expires_at": None,
        "renewal_evidence_refs": [],
        "parent_revision_digest": None,
        "status": "ACTIVE",
        "subjective_plausibility_tier": tier,
        "previous_subjective_plausibility_tier": None,
        "tier_update_refs": [],
        "lineage_id": hypothesis_id,
        "lineage_revision": 1,
        "predecessor_id": None,
        "predecessor_fingerprint": None,
        "semantic_fingerprint": None,
    }


def _hypotheses() -> list[dict[str, object]]:
    rows = [
        _hypothesis(
            "state-long",
            "STATE",
            "LONG",
            "HIGH",
            "dep:state",
            opposition_ids=["state-short"],
            alternative_ids=["state-short", "hypothesis-unknown"],
        ),
        _hypothesis(
            "state-short",
            "STATE",
            "SHORT",
            "LOW",
            "dep:state",
            opposition_ids=["state-long"],
            alternative_ids=["state-long", "hypothesis-unknown"],
        ),
        _hypothesis(
            "attribution-neutral",
            "ATTRIBUTION",
            "NEUTRAL",
            "LOW",
            "dep:attribution",
            alternative_ids=["hypothesis-unknown"],
        ),
        _hypothesis(
            "forecast-rejection",
            "FORECAST_PATH",
            "SHORT",
            "LOW",
            "dep:zone",
            opposition_ids=["forecast-absorption"],
            alternative_ids=[
                "forecast-absorption",
                "forecast-false-break",
                "forecast-other",
            ],
        ),
        _hypothesis(
            "forecast-absorption",
            "FORECAST_PATH",
            "LONG",
            "HIGH",
            "dep:zone",
            opposition_ids=["forecast-false-break", "forecast-rejection"],
            alternative_ids=[
                "forecast-false-break",
                "forecast-other",
                "forecast-rejection",
            ],
        ),
        _hypothesis(
            "forecast-false-break",
            "FORECAST_PATH",
            "SHORT",
            "LOW",
            "dep:zone",
            opposition_ids=["forecast-absorption"],
            alternative_ids=[
                "forecast-absorption",
                "forecast-other",
                "forecast-rejection",
            ],
        ),
        _hypothesis(
            "forecast-other",
            "FORECAST_PATH",
            "OTHER",
            "LOW",
            "dep:zone-other",
            alternative_ids=[
                "forecast-absorption",
                "forecast-false-break",
                "forecast-rejection",
            ],
        ),
        _hypothesis(
            "action-long",
            "ACTION_THESIS",
            "LONG",
            "LOW",
            "dep:action",
            opposition_ids=["action-short"],
            alternative_ids=["action-short", "hypothesis-unknown"],
        ),
        _hypothesis(
            "action-short",
            "ACTION_THESIS",
            "SHORT",
            "LOW",
            "dep:action",
            opposition_ids=["action-long"],
            alternative_ids=["action-long", "hypothesis-unknown"],
        ),
        _hypothesis(
            "hypothesis-unknown",
            "ATTRIBUTION",
            "UNKNOWN",
            "LOW",
            "dep:unknown",
            alternative_ids=["attribution-neutral"],
        ),
    ]
    _row(rows, "hypothesis_id", "state-long")["path_modifier_ids"] = [
        "modifier-venue"
    ]
    for hypothesis_id in ("forecast-rejection", "forecast-false-break"):
        _row(rows, "hypothesis_id", hypothesis_id)["path_modifier_ids"] = [
            "modifier-stop-hunt"
        ]
    return rows


def _clusters() -> list[dict[str, object]]:
    return [
        _cluster("cluster-state-long", ["state-long"], "LONG", "dep:state", "HIGH"),
        _cluster(
            "cluster-state-short", ["state-short"], "SHORT", "dep:state", "LOW"
        ),
        _cluster(
            "cluster-attribution",
            ["attribution-neutral"],
            "NEUTRAL",
            "dep:attribution",
            "LOW",
        ),
        _cluster(
            "cluster-zone-short",
            ["forecast-false-break", "forecast-rejection"],
            "SHORT",
            "dep:zone",
            "LOW",
        ),
        _cluster(
            "cluster-zone-long",
            ["forecast-absorption"],
            "LONG",
            "dep:zone",
            "HIGH",
        ),
        _cluster(
            "cluster-action-long", ["action-long"], "LONG", "dep:action", "LOW"
        ),
        _cluster(
            "cluster-action-short", ["action-short"], "SHORT", "dep:action", "LOW"
        ),
    ]


def _cluster(
    cluster_id: str,
    members: list[str],
    direction: str,
    dependency_group: str,
    tier: str,
) -> dict[str, object]:
    return {
        "cluster_id": cluster_id,
        "member_hypothesis_ids": members,
        "direction": direction,
        "shared_dependency_groups": [dependency_group],
        "aggregate_tier": tier,
        "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
    }


def _zone() -> dict[str, object]:
    return {
        "zone_id": "resistance-1300",
        "instrument": INSTRUMENT,
        "role": "RESISTANCE",
        "lower_bound": "1295.00",
        "upper_bound": "1305.00",
        "construction_method": "MULTI_SOURCE_COMPOSITE",
        "created_at": "2026-08-06T20:00:00Z",
        "available_at": "2026-08-06T20:01:00Z",
        "expires_at": EXPIRES,
        "evidence_refs": ["bar-ledger", "volume-profile"],
        "dependency_groups": ["dep:zone"],
        "touch_count": 2,
        "touch_refs": ["touch-1", "touch-2"],
        "reaction_refs": ["reaction-1", "reaction-2"],
        "volume_at_price_refs": ["volume-profile"],
        "dwell_time_refs": ["dwell-ledger"],
        "round_number_refs": ["round-number-1300"],
        "orderbook_flow_refs": ["flow-snapshot"],
        "leverage_refs": ["oi-datum"],
        "options_refs": [],
        "quality": "MEDIUM",
        "alternative_zone_ids": [],
        "path_modifier_ids": ["modifier-stop-hunt"],
        # JSON object order is not semantic; the builder must canonicalize it.
        "path_hypothesis_ids": {
            "ZONE_NO_EFFECT_OTHER": "forecast-other",
            "FALSE_BREAK_REVERSION": "forecast-false-break",
            "ZONE_ABSORPTION_BREAK": "forecast-absorption",
            "ZONE_REJECTION": "forecast-rejection",
        },
        "lineage_id": "resistance-1300",
        "lineage_revision": 1,
        "predecessor_id": None,
        "predecessor_fingerprint": None,
        "semantic_fingerprint": None,
    }


def _path_modifiers() -> list[dict[str, object]]:
    return [
        {
            "modifier_id": "modifier-stop-hunt",
            "modifier_type": "FALSE_BREAK_STOP_RUN",
            "scope": INSTRUMENT,
            "effect": "SUPPORTS_PATH",
            "mechanism": "stop activation without sustained follow-through",
            "source_refs": ["flow-snapshot", "touch-2"],
            "dependency_groups": ["dep:zone"],
            "affected_hypothesis_ids": [
                "forecast-false-break",
                "forecast-rejection",
            ],
            "affected_zone_ids": ["resistance-1300"],
            "affected_action_kinds": [
                "OPEN_PROBE",
                "ADD",
                "REENTER",
                "REVERSE",
            ],
            "conditions": ["price crosses the zone then reclaims it"],
            "trigger_effect": "REQUIRE_RECLAIM_CONFIRMATION",
            "protection_effect": "REQUIRE_EXIT_REENTRY_SEPARATION",
            "invalidators": ["acceptance outside the zone"],
            "created_at": "2026-08-06T23:45:00Z",
            "available_at": "2026-08-06T23:46:00Z",
            "expires_at": "2026-08-07T00:30:00Z",
            "status": "ACTIVE",
            "lineage_id": "modifier-stop-hunt",
            "lineage_revision": 1,
            "predecessor_id": None,
            "predecessor_fingerprint": None,
            "semantic_fingerprint": None,
        },
        {
            "modifier_id": "modifier-venue",
            "modifier_type": "CROSS_VENUE_DISLOCATION",
            "scope": "cross-venue BTC-USDT",
            "effect": "OPPOSES_PATH",
            "mechanism": "one venue is not confirmed by peer venues",
            "source_refs": ["cross-venue-spread"],
            "dependency_groups": ["dep:state"],
            "affected_hypothesis_ids": ["state-long"],
            "affected_zone_ids": [],
            "affected_action_kinds": [
                "OPEN_PROBE",
                "ADD",
                "REENTER",
                "REVERSE",
            ],
            "conditions": ["peer venue confirmation is absent"],
            "trigger_effect": "DELAY_TRIGGER",
            "protection_effect": "WIDEN_STRESS_BUFFER",
            "invalidators": ["peer venues confirm the move"],
            "created_at": "2026-08-06T23:50:00Z",
            "available_at": "2026-08-06T23:51:00Z",
            "expires_at": "2026-08-07T00:30:00Z",
            "status": "ACTIVE",
            "lineage_id": "modifier-venue",
            "lineage_revision": 1,
            "predecessor_id": None,
            "predecessor_fingerprint": None,
            "semantic_fingerprint": None,
        },
    ]


def _unknowns() -> list[dict[str, object]]:
    return [
        {
            "unknown_id": f"unknown-{unknown_type.lower()}",
            "unknown_type": unknown_type,
            "scope": INSTRUMENT,
            "dependency_refs": [f"datum:{unknown_type}"],
            "behavior_effect": UNKNOWN_BEHAVIOR_EFFECT[unknown_type],
            "explanation": f"typed meaning:{unknown_type}",
        }
        for unknown_type in UNKNOWN_TYPES
    ]


def _kwargs() -> dict[str, object]:
    return {
        "run_id": "v32-test-run",
        "cycle_index": 1,
        "as_of": AS_OF,
        "frame_mode": "FULL_CONTEXT",
        "previous_state_digest": None,
        "market_regime_state": {
            "regime": "TREND_UP",
            "evidence_refs": ["source:state-long"],
            "counter_evidence_refs": ["contrary:state-long"],
            "regime_feature_assessments": [],
            "expires_at": EXPIRES,
            "previous_regime": None,
            "transition_evidence_refs": [],
        },
        "unknowns": _unknowns(),
        "zones": [_zone()],
        "hypotheses": _hypotheses(),
        "path_modifiers": _path_modifiers(),
        "dependency_clusters": _clusters(),
    }


def _regime_feature_assessments(regime: str) -> list[dict[str, object]]:
    if regime == "CHOPPY":
        return [
            {
                "feature_type": "DIRECTIONAL_PERSISTENCE",
                "feature_state": "LOW",
                "evidence_refs": ["regime:price-persistence"],
            },
            {
                "feature_type": "REVERSAL_FREQUENCY",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:price-reversals"],
            },
            {
                "feature_type": "EXECUTION_CHURN_PRESSURE",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:trade-churn"],
            },
        ]
    if regime == "VOLATILITY_WITHOUT_DIRECTION":
        return [
            {
                "feature_type": "DIRECTIONAL_PERSISTENCE",
                "feature_state": "LOW",
                "evidence_refs": ["regime:price-persistence"],
            },
            {
                "feature_type": "REALIZED_VOLATILITY",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:price-volatility"],
            },
            {
                "feature_type": "DIRECTIONAL_IMBALANCE",
                "feature_state": "BALANCED",
                "evidence_refs": ["regime:flow-balance"],
            },
        ]
    return []


def _set_regime_features(values: dict[str, object], regime: str) -> None:
    assessments = _regime_feature_assessments(regime)
    market_regime = values["market_regime_state"]
    market_regime["regime"] = regime
    market_regime["regime_feature_assessments"] = assessments
    market_regime["evidence_refs"] = [
        "source:state-long",
        *[
            evidence_ref
            for assessment in assessments
            for evidence_ref in assessment["evidence_refs"]
        ],
    ]


def _row(
    rows: list[dict[str, object]], key: str, value: str
) -> dict[str, object]:
    return next(row for row in rows if row[key] == value)


def _cycle_two_kwargs() -> tuple[dict[str, object], dict[str, object]]:
    first = build_v32_dynamic_research_state_v1(**_kwargs())
    values = _kwargs()
    values.update(
        {
            "cycle_index": 2,
            "as_of": "2026-08-07T00:15:00Z",
            "frame_mode": "DELTA_UPDATE",
            "previous_state_digest": first[DIGEST_FIELD],
        }
    )
    values["market_regime_state"]["previous_regime"] = "TREND_UP"
    for hypothesis in values["hypotheses"]:
        hypothesis["parent_revision_digest"] = first[DIGEST_FIELD]
        hypothesis["previous_subjective_plausibility_tier"] = hypothesis[
            "subjective_plausibility_tier"
        ]
        hypothesis["previous_expires_at"] = hypothesis["expires_at"]
    rejection = _row(values["hypotheses"], "hypothesis_id", "forecast-rejection")
    rejection["subjective_plausibility_tier"] = "HIGH"
    rejection["tier_update_refs"] = [
        "closed-15m-rejection-delta",
        "fresh-independent-rejection-flow",
    ]
    rejection["supporting_refs"].extend(rejection["tier_update_refs"])
    rejection["dependency_groups"] = sorted(
        {
            *rejection["dependency_groups"],
            "REQUEST:FIXTURE:dep:zone",
            "REQUEST:FIXTURE:dep:zone:independent",
            "OBSERVABLE_FAMILY:PRICE_ACTION",
            "OBSERVABLE_FAMILY:FUNDING_CROWDING",
        }
    )
    cluster = _row(
        values["dependency_clusters"], "cluster_id", "cluster-zone-short"
    )
    cluster["aggregate_tier"] = "HIGH"
    return first, values


class V32DynamicResearchTests(unittest.TestCase):
    def test_choppy_and_directionless_volatility_require_typed_feature_combinations(
        self,
    ) -> None:
        for regime in ("CHOPPY", "VOLATILITY_WITHOUT_DIRECTION"):
            with self.subTest(regime=regime):
                values = _kwargs()
                _set_regime_features(values, regime)
                document = build_v32_dynamic_research_state_v1(**values)
                self.assertEqual(regime, document["market_regime_state"]["regime"])
                self.assertEqual(
                    3,
                    len(
                        document["market_regime_state"][
                            "regime_feature_assessments"
                        ]
                    ),
                )

        missing = _kwargs()
        _set_regime_features(missing, "CHOPPY")
        missing["market_regime_state"]["regime_feature_assessments"].pop()
        self.assert_build_error(
            missing, "V32_MARKET_REGIME_FEATURE_COMBINATION_INVALID"
        )

        one_ref = _kwargs()
        _set_regime_features(one_ref, "CHOPPY")
        for assessment in one_ref["market_regime_state"][
            "regime_feature_assessments"
        ]:
            assessment["evidence_refs"] = ["regime:single-unrelated"]
        one_ref["market_regime_state"]["evidence_refs"] = [
            "source:state-long",
            "regime:single-unrelated",
        ]
        self.assert_build_error(
            one_ref, "V32_MARKET_REGIME_FEATURE_EVIDENCE_INVALID"
        )

        _, transition = _cycle_two_kwargs()
        _set_regime_features(transition, "CHOPPY")
        transition["market_regime_state"]["transition_evidence_refs"] = [
            "regime:price-persistence"
        ]
        self.assert_build_error(
            transition,
            "V32_MARKET_REGIME_FEATURE_TRANSITION_BINDING_INVALID",
        )

    def test_total_durable_object_limits_fail_closed_without_truncation(self) -> None:
        values = _kwargs()
        values["unknowns"] = [deepcopy(values["unknowns"][0]) for _ in range(33)]
        with self.assertRaisesRegex(
            V32DynamicResearchError,
            "V32_STATE_DURABLE_OBJECT_LIMIT_EXCEEDED",
        ):
            build_v32_dynamic_research_state_v1(**values)

    def test_terminal_hypothesis_is_excluded_from_cluster_support(self) -> None:
        values = _kwargs()
        hypothesis = _row(values["hypotheses"], "hypothesis_id", "action-long")
        hypothesis["status"] = "FALSIFIED"
        hypothesis["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
        cluster = _row(
            values["dependency_clusters"], "cluster_id", "cluster-action-long"
        )
        cluster["aggregate_tier"] = "EXTREME_UNCERTAINTY"

        document = build_v32_dynamic_research_state_v1(**values)

        sealed = _row(
            document["dependency_clusters"], "cluster_id", "cluster-action-long"
        )
        self.assertEqual("EXTREME_UNCERTAINTY", sealed["aggregate_tier"])
        self.assertEqual(
            "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
            sealed["aggregation_method"],
        )

    def assert_build_error(self, values: dict[str, object], error: str) -> None:
        with self.assertRaisesRegex(V32DynamicResearchError, error):
            build_v32_dynamic_research_state_v1(**values)

    def test_round_trip_and_static_claim_boundaries(self) -> None:
        document = build_v32_dynamic_research_state_v1(**_kwargs())

        self.assertEqual(
            verify_v32_dynamic_research_state_v1(document), document[DIGEST_FIELD]
        )
        self.assertEqual(
            {row["unknown_type"] for row in document["unknowns"]},
            set(UNKNOWN_TYPES),
        )
        self.assertEqual(
            {row["hypothesis_type"] for row in document["hypotheses"]},
            set(HYPOTHESIS_TYPES),
        )
        self.assertEqual(
            [
                row["direction"]
                for row in document["hypotheses"]
                if row["direction"] in {"OTHER", "UNKNOWN"}
            ],
            ["OTHER", "UNKNOWN"],
        )
        self.assertEqual(
            document["probability_claim"],
            "NONE_UNCALIBRATED_SUBJECTIVE_SUPPORT_ONLY",
        )
        self.assertFalse(document["brier_ece_allowed"])
        self.assertFalse(document["expected_value_allowed"])
        self.assertEqual(
            document["external_execution_authority"], "NONE_LOCAL_SIMULATION"
        )
        self.assertFalse(document["executable"])
        self.assertIn("NO_AUTOMATIC_TIER_DECAY", document["expiry_policy"])
        self.assertEqual(
            document["modifier_policy"],
            "TYPED_CONDITIONS_TRIGGER_RISK_PROTECTION_INVALIDATORS_"
            "BIDIRECTIONAL_ZONE_HYPOTHESIS_SCOPE_NO_GLOBAL_BROADCAST",
        )
        zone = document["zones"][0]
        self.assertEqual(zone["lower_bound"], "1295")
        self.assertEqual(list(zone["path_hypothesis_ids"]), list(ZONE_PATH_ROLES))

    def test_each_unknown_type_requires_exact_behavior_effect(self) -> None:
        for unknown_type in UNKNOWN_TYPES:
            with self.subTest(unknown_type=unknown_type):
                values = _kwargs()
                unknown = _row(values["unknowns"], "unknown_type", unknown_type)
                unknown["behavior_effect"] = "WAIT_FOR_CONFIRMATION"
                self.assert_build_error(
                    values, "V32_UNKNOWN_BEHAVIOR_EFFECT_INVALID"
                )

    def test_normal_market_unknowns_allow_bounded_probe(self) -> None:
        document = build_v32_dynamic_research_state_v1(**_kwargs())
        effects = {
            row["unknown_type"]: row["behavior_effect"]
            for row in document["unknowns"]
        }

        self.assertEqual(effects["UNKNOWN_DIRECTION"], "ALLOW_BOUNDED_PROBE")
        self.assertEqual(
            effects["UNKNOWN_CAUSE"], "DOES_NOT_BLOCK_BOUNDED_PROBE"
        )
        self.assertEqual(
            effects["UNKNOWN_FUTURE"], "NORMAL_MARKET_UNCERTAINTY"
        )
        self.assertEqual(
            effects["UNKNOWN_FACT_INTEGRITY"], "BLOCK_DEPENDENT_ACTIONS"
        )
        self.assertEqual(
            effects["UNKNOWN_MAX_LOSS"], "BLOCK_FUTURE_EXECUTION"
        )

    def test_all_four_hypothesis_types_are_required(self) -> None:
        values = _kwargs()
        for hypothesis in values["hypotheses"]:
            if hypothesis["hypothesis_type"] == "ACTION_THESIS":
                hypothesis["hypothesis_type"] = "STATE"
        self.assert_build_error(values, "V32_HYPOTHESIS_TYPE_SET_INCOMPLETE")

    def test_exactly_one_other_and_unknown_are_required(self) -> None:
        for residual in ("OTHER", "UNKNOWN"):
            with self.subTest(residual=residual):
                values = _kwargs()
                hypothesis = next(
                    row
                    for row in values["hypotheses"]
                    if row["direction"] == residual
                )
                hypothesis["direction"] = "NEUTRAL"
                self.assert_build_error(
                    values, "V32_HYPOTHESIS_RESIDUAL_SET_INVALID"
                )

    def test_directional_opposition_is_symmetric_and_comparable(self) -> None:
        values = _kwargs()
        _row(values["hypotheses"], "hypothesis_id", "state-long")[
            "opposition_ids"
        ] = []
        self.assert_build_error(values, "V32_DIRECTIONAL_OPPOSITION_REQUIRED")

        values = _kwargs()
        _row(values["hypotheses"], "hypothesis_id", "state-short")[
            "horizon_seconds"
        ] = 7200
        self.assert_build_error(values, "V32_HYPOTHESIS_OPPOSITION_INVALID")

    def test_opposite_candidate_may_be_extreme_uncertainty_and_weakened(self) -> None:
        values = _kwargs()
        short = _row(values["hypotheses"], "hypothesis_id", "action-short")
        short["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
        short["status"] = "WEAKENED"
        cluster = _row(
            values["dependency_clusters"], "cluster_id", "cluster-action-short"
        )
        cluster["aggregate_tier"] = "EXTREME_UNCERTAINTY"

        document = build_v32_dynamic_research_state_v1(**values)
        self.assertIn(
            "NO_ACTIONABILITY_OR_POSITIVE_WEIGHT_REQUIREMENT",
            document["opposing_direction_policy"],
        )

    def test_subjective_tier_is_strict_and_extra_numeric_field_is_rejected(self) -> None:
        values = _kwargs()
        _row(values["hypotheses"], "hypothesis_id", "state-long")[
            "subjective_plausibility_tier"
        ] = "LOW"
        _row(values["dependency_clusters"], "cluster_id", "cluster-state-long")[
            "aggregate_tier"
        ] = "LOW"
        document = build_v32_dynamic_research_state_v1(**values)
        self.assertEqual(
            "LOW",
            _row(document["hypotheses"], "hypothesis_id", "state-long")[
                "subjective_plausibility_tier"
            ],
        )

        values = _kwargs()
        row = _row(values["hypotheses"], "hypothesis_id", "state-long")
        row["subjective_plausibility_tier"] = "MEDIUM"
        self.assert_build_error(values, "V32_HYPOTHESIS_TIER_INVALID")

        values = _kwargs()
        row = _row(values["hypotheses"], "hypothesis_id", "state-long")
        row["subjective_confidence_number"] = 55
        self.assert_build_error(values, "V32_HYPOTHESIS_ROW_INVALID")

    def test_cycle_one_cannot_claim_revision_or_renewal(self) -> None:
        values = _kwargs()
        hypothesis = _row(values["hypotheses"], "hypothesis_id", "state-long")
        hypothesis["parent_revision_digest"] = "a" * 64
        hypothesis["previous_subjective_plausibility_tier"] = "LOW"
        hypothesis["previous_expires_at"] = EXPIRES
        hypothesis["tier_update_refs"] = ["not-a-cycle-one-update"]
        hypothesis["renewal_evidence_refs"] = ["not-a-cycle-one-renewal"]
        self.assert_build_error(values, "V32_INITIAL_TIER_BINDING_INVALID")

    def test_cycle_two_binds_previous_tier_and_change_evidence(self) -> None:
        first, values = _cycle_two_kwargs()
        second = build_v32_dynamic_research_state_v1(**values)

        self.assertEqual(second["previous_state_digest"], first[DIGEST_FIELD])
        rejection = _row(
            second["hypotheses"], "hypothesis_id", "forecast-rejection"
        )
        self.assertEqual(rejection["previous_subjective_plausibility_tier"], "LOW")
        self.assertEqual(rejection["subjective_plausibility_tier"], "HIGH")
        self.assertEqual(
            rejection["tier_update_refs"],
            [
                "closed-15m-rejection-delta",
                "fresh-independent-rejection-flow",
            ],
        )
        self.assertEqual(
            verify_v32_dynamic_research_state_v1(second), second[DIGEST_FIELD]
        )

    def test_cycle_two_rejects_wrong_parent_direct_jump_and_missing_evidence(
        self,
    ) -> None:
        _, values = _cycle_two_kwargs()
        rejection = _row(
            values["hypotheses"], "hypothesis_id", "forecast-rejection"
        )
        rejection["parent_revision_digest"] = "b" * 64
        self.assert_build_error(
            values, "V32_REVISED_HYPOTHESIS_TIER_BINDING_INVALID"
        )

    def test_high_tier_requires_dual_declared_evidence_and_counter(self) -> None:
        values = _kwargs()
        row = _row(values["hypotheses"], "hypothesis_id", "state-long")
        row["dependency_groups"] = ["dep:state"]
        self.assert_build_error(
            values, "V32_HIGH_TIER_DUAL_EVIDENCE_AND_COUNTER_REQUIRED"
        )

        values = _kwargs()
        row = _row(values["hypotheses"], "hypothesis_id", "state-long")
        row["opposing_refs"] = []
        self.assert_build_error(
            values, "V32_HIGH_TIER_DUAL_EVIDENCE_AND_COUNTER_REQUIRED"
        )

    def test_low_to_high_requires_two_update_evidence_refs(self) -> None:
        _, values = _cycle_two_kwargs()
        row = _row(values["hypotheses"], "hypothesis_id", "forecast-rejection")
        row["tier_update_refs"] = ["closed-15m-rejection-delta"]
        self.assert_build_error(
            values, "V32_LOW_TO_HIGH_DUAL_EVIDENCE_AND_COUNTER_REQUIRED"
        )

        _, values = _cycle_two_kwargs()
        state_long = _row(values["hypotheses"], "hypothesis_id", "state-long")
        state_long["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
        state_long["tier_update_refs"] = ["fresh-collapse"]
        self.assert_build_error(
            values, "V32_HYPOTHESIS_TIER_JUMP_FORBIDDEN"
        )

        _, values = _cycle_two_kwargs()
        rejection = _row(
            values["hypotheses"], "hypothesis_id", "forecast-rejection"
        )
        rejection["tier_update_refs"] = []
        self.assert_build_error(
            values, "V32_HYPOTHESIS_TIER_UPDATE_EVIDENCE_REQUIRED"
        )

    def test_cycle_two_requires_previous_state_digest(self) -> None:
        _, values = _cycle_two_kwargs()
        values["previous_state_digest"] = None
        self.assert_build_error(values, "V32_STATE_PREVIOUS_BINDING_INVALID")

    def test_expiry_renewal_requires_parent_old_expiry_and_new_bound_evidence(
        self,
    ) -> None:
        _, values = _cycle_two_kwargs()
        state_long = _row(values["hypotheses"], "hypothesis_id", "state-long")
        state_long["expires_at"] = "2026-08-07T05:00:00Z"
        self.assert_build_error(
            values, "V32_HYPOTHESIS_RENEWAL_EVIDENCE_REQUIRED"
        )

        _, values = _cycle_two_kwargs()
        state_long = _row(values["hypotheses"], "hypothesis_id", "state-long")
        state_long["expires_at"] = "2026-08-07T05:00:00Z"
        state_long["renewal_evidence_refs"] = ["fresh-renewal-observation"]
        self.assert_build_error(
            values, "V32_HYPOTHESIS_RENEWAL_EVIDENCE_REQUIRED"
        )

        _, values = _cycle_two_kwargs()
        state_long = _row(values["hypotheses"], "hypothesis_id", "state-long")
        state_long["expires_at"] = "2026-08-07T05:00:00Z"
        state_long["supporting_refs"].append("fresh-renewal-observation")
        state_long["renewal_evidence_refs"] = ["fresh-renewal-observation"]
        document = build_v32_dynamic_research_state_v1(**values)
        renewed = _row(document["hypotheses"], "hypothesis_id", "state-long")
        self.assertEqual(renewed["subjective_plausibility_tier"], "HIGH")
        self.assertEqual(renewed["tier_update_refs"], [])

    def test_false_renewal_claim_without_expiry_extension_is_rejected(self) -> None:
        _, values = _cycle_two_kwargs()
        state_long = _row(values["hypotheses"], "hypothesis_id", "state-long")
        state_long["supporting_refs"].append("fresh-renewal-observation")
        state_long["renewal_evidence_refs"] = ["fresh-renewal-observation"]
        self.assert_build_error(values, "V32_HYPOTHESIS_FALSE_RENEWAL_INVALID")

    def test_cluster_max_intersection_and_no_same_direction_split(self) -> None:
        values = _kwargs()
        cluster = _row(
            values["dependency_clusters"], "cluster_id", "cluster-zone-short"
        )
        cluster["aggregate_tier"] = "EXTREME_UNCERTAINTY"
        self.assert_build_error(values, "V32_CLUSTER_AGGREGATION_INVALID")

        values = _kwargs()
        false_break = _row(
            values["hypotheses"], "hypothesis_id", "forecast-false-break"
        )
        false_break["dependency_groups"] = ["dep:false-break-only"]
        false_break["path_modifier_ids"] = []
        modifier = _row(
            values["path_modifiers"], "modifier_id", "modifier-stop-hunt"
        )
        modifier["affected_hypothesis_ids"] = ["forecast-rejection"]
        self.assert_build_error(values, "V32_CLUSTER_DEPENDENCY_INVALID")

        values = _kwargs()
        values["dependency_clusters"] = [
            cluster
            for cluster in values["dependency_clusters"]
            if cluster["cluster_id"] != "cluster-zone-short"
        ]
        values["dependency_clusters"].extend(
            [
                _cluster(
                    "cluster-rejection-only",
                    ["forecast-rejection"],
                    "SHORT",
                    "dep:zone",
                    "LOW",
                ),
                _cluster(
                    "cluster-false-break-only",
                    ["forecast-false-break"],
                    "SHORT",
                    "dep:zone",
                    "LOW",
                ),
            ]
        )
        self.assert_build_error(
            values, "V32_SAME_DIRECTION_CLUSTER_DEPENDENCY_OVERLAP"
        )

    def test_cluster_requires_exact_aggregate_tier(self) -> None:
        values = _kwargs()
        neutral = _row(
            values["hypotheses"], "hypothesis_id", "attribution-neutral"
        )
        neutral["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
        cluster = _row(
            values["dependency_clusters"], "cluster_id", "cluster-attribution"
        )
        cluster["aggregate_tier"] = False
        self.assert_build_error(values, "V32_CLUSTER_ROW_INVALID")

    def test_zone_paths_are_distinct_typed_competing_forecasts(self) -> None:
        values = _kwargs()
        zone = values["zones"][0]
        zone["path_hypothesis_ids"][
            "ZONE_NO_EFFECT_OTHER"
        ] = "hypothesis-unknown"
        self.assert_build_error(values, "V32_ZONE_PATH_TYPE_INVALID")

        values = _kwargs()
        zone = values["zones"][0]
        zone["path_hypothesis_ids"][
            "FALSE_BREAK_REVERSION"
        ] = "forecast-rejection"
        self.assert_build_error(values, "V32_ZONE_PATH_SET_INVALID")

        values = _kwargs()
        other = _row(values["hypotheses"], "hypothesis_id", "forecast-other")
        other["horizon_seconds"] = 7200
        self.assert_build_error(values, "V32_ZONE_PATH_COMPARABILITY_INVALID")

    def test_zone_geometry_time_touch_and_alternative_bindings(self) -> None:
        cases = (
            ("bounds", "V32_ZONE_BOUNDS_INVALID"),
            ("future_available", "V32_ZONE_TIME_INVALID"),
            ("touch_ledger", "V32_ZONE_TOUCH_LEDGER_INVALID"),
            ("alternative", "V32_ZONE_ALTERNATIVE_INVALID"),
        )
        for mutation, error in cases:
            with self.subTest(mutation=mutation):
                values = _kwargs()
                zone = values["zones"][0]
                if mutation == "bounds":
                    zone["upper_bound"] = zone["lower_bound"]
                elif mutation == "future_available":
                    zone["available_at"] = "2026-08-07T00:00:01Z"
                elif mutation == "touch_ledger":
                    zone["touch_count"] = 3
                else:
                    zone["alternative_zone_ids"] = ["missing-zone"]
                self.assert_build_error(values, error)

    def test_expired_zone_remains_admissible_as_an_audit_tombstone(self) -> None:
        values = _kwargs()
        values["zones"][0]["expires_at"] = "2026-08-06T23:59:00Z"

        document = build_v32_dynamic_research_state_v1(**values)

        self.assertLessEqual(document["zones"][0]["expires_at"], document["as_of"])

    def test_due_hypothesis_and_modifier_must_be_terminal(self) -> None:
        values = _kwargs()
        _row(values["hypotheses"], "hypothesis_id", "state-long")[
            "expires_at"
        ] = "2026-08-06T23:59:00Z"
        self.assert_build_error(values, "V32_HYPOTHESIS_EXPIRY_INVALID")

        values = _kwargs()
        _row(
            values["path_modifiers"], "modifier_id", "modifier-venue"
        )["expires_at"] = "2026-08-06T23:59:00Z"
        self.assert_build_error(values, "V32_PATH_MODIFIER_TIME_INVALID")

        values = _kwargs()
        hypothesis = _row(
            values["hypotheses"], "hypothesis_id", "state-long"
        )
        hypothesis["expires_at"] = "2026-08-06T23:59:00Z"
        hypothesis["status"] = "EXPIRED"
        hypothesis["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
        _row(
            values["dependency_clusters"], "cluster_id", "cluster-state-long"
        )["aggregate_tier"] = "EXTREME_UNCERTAINTY"
        modifier = _row(
            values["path_modifiers"], "modifier_id", "modifier-venue"
        )
        modifier["expires_at"] = "2026-08-06T23:59:00Z"
        modifier["status"] = "EXPIRED"
        document = build_v32_dynamic_research_state_v1(**values)
        self.assertEqual(
            "EXPIRED",
            _row(document["hypotheses"], "hypothesis_id", "state-long")[
                "status"
            ],
        )

    def test_path_modifiers_are_typed_dependency_scoped_and_reverse_bound(self) -> None:
        document = build_v32_dynamic_research_state_v1(**_kwargs())
        modifier = _row(
            document["path_modifiers"], "modifier_id", "modifier-stop-hunt"
        )
        self.assertTrue(
            {
                "FALSE_BREAK_STOP_RUN",
                "LIQUIDITY_VACUUM",
                "CROSS_VENUE_DISLOCATION",
            }.issubset(PATH_MODIFIER_TYPES)
        )
        self.assertEqual(
            modifier["affected_hypothesis_ids"],
            ["forecast-false-break", "forecast-rejection"],
        )

        values = _kwargs()
        modifier = _row(
            values["path_modifiers"], "modifier_id", "modifier-stop-hunt"
        )
        modifier["dependency_groups"] = ["dep:unrelated"]
        self.assert_build_error(
            values, "V32_PATH_MODIFIER_DEPENDENCY_BINDING_INVALID"
        )

        values = _kwargs()
        action = _row(values["hypotheses"], "hypothesis_id", "action-long")
        action["path_modifier_ids"] = ["modifier-venue"]
        self.assert_build_error(
            values, "V32_HYPOTHESIS_PATH_MODIFIER_BINDING_INVALID"
        )

    def test_modifier_cannot_broadcast_to_every_non_residual_hypothesis(self) -> None:
        values = _kwargs()
        modifier = _row(
            values["path_modifiers"], "modifier_id", "modifier-stop-hunt"
        )
        modifier["affected_hypothesis_ids"] = [
            row["hypothesis_id"]
            for row in values["hypotheses"]
            if row["direction"] not in {"OTHER", "UNKNOWN"}
        ]
        self.assert_build_error(values, "V32_PATH_MODIFIER_AFFECTED_SET_INVALID")

    def test_zone_modifier_must_share_zone_dependency_and_affect_a_zone_path(
        self,
    ) -> None:
        values = _kwargs()
        values["zones"][0]["path_modifier_ids"] = ["modifier-venue"]
        self.assert_build_error(values, "V32_PATH_MODIFIER_ZONE_BINDING_INVALID")

    def test_verifier_rejects_digest_tamper_and_recomputed_policy_drift(self) -> None:
        document = build_v32_dynamic_research_state_v1(**_kwargs())
        tampered = deepcopy(document)
        tampered["probability_claim"] = "CALIBRATED_70_PERCENT"
        with self.assertRaisesRegex(
            V32DynamicResearchError, "V32_STATE_DOCUMENT_INVALID"
        ):
            verify_v32_dynamic_research_state_v1(tampered)

        tampered = deepcopy(document)
        tampered["probability_claim"] = "CALIBRATED_70_PERCENT"
        tampered = self_digest(tampered, DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicResearchError, "V32_STATE_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_dynamic_research_state_v1(tampered)


if __name__ == "__main__":
    unittest.main()
