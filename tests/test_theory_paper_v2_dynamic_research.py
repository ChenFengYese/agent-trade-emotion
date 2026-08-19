from __future__ import annotations

import unittest

from trade_system.theory_paper_v2.domain.dynamic_research import (
    MARKET_CATEGORIES,
    SENTIMENT_AXES,
    DynamicResearchError,
    build_market_information_snapshot,
    build_sentiment_state,
    build_sentiment_state_change,
    migrate_legacy_sentiment_state_to_v31,
    reduce_expectation_ledger,
    reduce_hypothesis_registry,
    verify_sentiment_state,
    verify_sentiment_state_change,
)


def market_fact(category: str, index: int, *, missing: bool = False) -> dict:
    return {
        "fact_id": f"fact:{index}",
        "kind": "RAW_FACT",
        "category": category,
        "metric": f"metric_{index}",
        "value": None if missing else str(index + 1),
        "unit": "INDEX",
        "symbol": "SYNTHUSDT",
        "timeframe": "1h",
        "window": "closed-1h",
        "source_ref": f"fixture:source:{index}",
        "raw_ref": f"raw/cycle-0001/{index}.json",
        "raw_sha256": None if missing else f"{index:x}" * 64,
        "observed_at": "2026-08-06T00:00:00Z",
        "available_at": "2026-08-06T00:01:00Z",
        "quality": "UNKNOWN" if missing else "GOOD",
        "coverage": "0" if missing else "1",
        "dependency_group": f"group:{index}",
        "lineage": [],
        "transform": None,
        "limitations": "synthetic fixture only",
        "missing_reason": "FIXTURE_UNAVAILABLE" if missing else None,
    }


def market_snapshot() -> dict:
    facts = [
        market_fact(category, index, missing=category == "LIQUIDATION")
        for index, category in enumerate(MARKET_CATEGORIES)
    ]
    return build_market_information_snapshot(
        run_id="run",
        cycle_index=1,
        symbol="SYNTHUSDT",
        as_of="2026-08-06T01:00:00Z",
        facts=facts,
    )


def sentiment_inputs() -> list[dict]:
    rows = []
    for index, axis in enumerate(SENTIMENT_AXES):
        usable = index != 6
        rows.append(
            {
                "axis": axis,
                "required_dependency_groups": [
                    f"group:{index}",
                    f"group:required-extra:{index}",
                ],
                "contributors": (
                    [
                        {
                            "fact_id": f"fact:{index}",
                            "ordinal_contribution": 1,
                            "rule": "fixture observed value supports positive axis state",
                            "direction": "POSITIVE",
                        }
                    ]
                    if usable
                    else []
                ),
                "timeframe_states": {"1h": 1 if usable else None},
                "agent_interpretation": "fixture interpretation with explicit evidence",
                "limitations": "synthetic values cannot validate market meaning",
                "next_discriminating_observation": "observe the next closed fixture bar",
            }
        )
    return rows


def hypothesis(
    hypothesis_id: str,
    *,
    family: str,
    state: str = "ACTIVE",
    revision: int = 1,
    created_at: str = "2026-08-06T00:00:00Z",
    updated_at: str = "2026-08-06T00:00:00Z",
    parents: list[str] | None = None,
    dedup: str | None = None,
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "revision": revision,
        "hypothesis_type": "PATH",
        "directional_bias": "BIDIRECTIONAL",
        "family_label": family,
        "deduplication_key": dedup or f"dedup:{family}",
        "state": state,
        "parent_hypothesis_ids": parents or [],
        "supersedes_ids": parents or [],
        "derived_from_expectation_ids": [],
        "created_at": created_at,
        "updated_at": updated_at,
        "horizon": "next four closed 1h bars",
        "timeframe_scope": ["4h", "1h"],
        "premises": ["observed structure persists"],
        "expected_sequence": ["liquidity is tested", "price response distinguishes paths"],
        "support_rules": ["closed-bar response confirms the mechanism"],
        "oppose_rules": ["response fails to persist"],
        "hard_falsifiers": [f"falsifier:{hypothesis_id}"],
        "expiry": "2026-08-07T00:00:00Z",
        "trade_triggers": [],
        "forbidden_conditions": [],
        "active_evidence_ids": ["fact:0"],
        "active_evidence_bindings": {"fact:0": "a" * 64},
        "support_level": "PLAUSIBLE",
        "limitations": ["synthetic fixture"],
        "novelty_reason": "distinct process and evidence sequence",
        "agent_rationale": "retain this path until the registered observation resolves it",
    }


def hypothesis_delta(
    delta_id: str,
    operation: str,
    *,
    targets: list[str],
    replacements: list[dict],
    at: str = "2026-08-06T01:00:00Z",
    evidence: list[str] | None = None,
    falsifier: str | None = None,
) -> dict:
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_hypothesis_ids": targets,
        "replacement_hypotheses": replacements,
        "evidence_ids": ["fact:0"] if evidence is None else evidence,
        "evidence_bindings": {
            ref: "a" * 64
            for ref in (["fact:0"] if evidence is None else evidence)
        },
        "matched_hard_falsifier": falsifier,
        "agent_rationale": "explicit fixture lifecycle transition",
    }


def expectation(
    expectation_id: str,
    *,
    status: str = "OPEN",
    revision: int = 1,
    updated_at: str = "2026-08-06T01:00:00Z",
    closed_at: str | None = None,
    results: list[str] | None = None,
) -> dict:
    return {
        "expectation_id": expectation_id,
        "revision": revision,
        "hypothesis_id": "hypothesis:base",
        "parent_expectation_id": None,
        "deduplication_key": "dedup:base:next-four-hours",
        "created_at": "2026-08-06T01:00:00Z",
        "updated_at": updated_at,
        "observation_start": "2026-08-06T01:00:00Z",
        "observation_deadline": "2026-08-06T05:00:00Z",
        "if_conditions": ["price remains above fixture support"],
        "expected_observations": [
            {
                "metric": "close",
                "direction_or_range": "above fixture support",
                "timeframe": "1h",
                "source_requirement": "closed synthetic bar",
            }
        ],
        "falsifying_observations": [
            {
                "metric": "close",
                "direction_or_range": "below fixture invalidation",
                "timeframe": "1h",
                "source_requirement": "closed synthetic bar",
            }
        ],
        "evidence_sufficiency": "LOW",
        "status": status,
        "result_evidence_refs": results or [],
        "result_evidence_bindings": {
            ref: "a" * 64 for ref in (results or [])
        },
        "closed_at": closed_at,
        "result_note": "fixture result" if closed_at else None,
    }


def expectation_delta(
    delta_id: str,
    operation: str,
    document: dict,
    *,
    target: str | None,
    at: str,
) -> dict:
    return {
        "delta_id": delta_id,
        "operation": operation,
        "occurred_at": at,
        "target_expectation_id": target,
        "expectation": document,
        "agent_rationale": "fixture expectation transition based on admitted fact",
    }


class DynamicResearchTests(unittest.TestCase):
    def test_market_snapshot_preserves_unknown_and_sentiment_has_no_total(self) -> None:
        snapshot = market_snapshot()
        liquidation = snapshot["category_status"]["LIQUIDATION"]
        self.assertEqual("UNKNOWN", liquidation["status"])
        self.assertFalse(snapshot["missing_values_are_zero"])
        sentiment = build_sentiment_state(
            market_snapshot=snapshot,
            dimension_inputs=sentiment_inputs(),
            operational_synthesis="mixed coverage requires conditional waiting",
        )
        self.assertIsNone(sentiment["overall_numeric_score"])
        volatility = next(
            row for row in sentiment["dimensions"] if row["axis"] == "VOLATILITY_STRESS"
        )
        self.assertIsNone(volatility["ordinal_value"])
        self.assertEqual("UNKNOWN", volatility["conflict_state"])

        broken = [market_fact(category, index) for index, category in enumerate(MARKET_CATEGORIES)]
        broken[0] = {**broken[0], "value": None, "quality": "UNKNOWN", "coverage": "0", "missing_reason": "MISSING", "raw_sha256": "0" * 64}
        with self.assertRaisesRegex(DynamicResearchError, "UNKNOWN_SEMANTICS"):
            build_market_information_snapshot(
                run_id="run",
                cycle_index=1,
                symbol="SYNTHUSDT",
                as_of="2026-08-06T01:00:00Z",
                facts=broken,
            )

    def test_contradictory_axes_cannot_produce_strong_direction(self) -> None:
        snapshot = market_snapshot()
        rows = sentiment_inputs()
        contributors = [
            {
                "fact_id": f"fact:{index}",
                "ordinal_contribution": value,
                "rule": "fixture contributor for deterministic conflict aggregation",
                "direction": "POSITIVE" if value > 0 else "NEGATIVE",
            }
            for index, value in enumerate((1, 1, 1, -1))
        ]
        required_groups = [f"group:{index}" for index in range(4)]

        coherence = next(
            row for row in rows if row["axis"] == "TIMEFRAME_COHERENCE"
        )
        coherence["required_dependency_groups"] = required_groups
        coherence["contributors"] = contributors
        coherence["timeframe_states"] = {
            "15m": 1,
            "1h": 1,
            "4h": 1,
            "1d": -1,
        }
        result = build_sentiment_state(
            market_snapshot=snapshot,
            dimension_inputs=rows,
            operational_synthesis="mixed timeframes do not establish coherence",
        )
        coherence_state = next(
            row
            for row in result["dimensions"]
            if row["axis"] == "TIMEFRAME_COHERENCE"
        )
        self.assertEqual(0, coherence_state["ordinal_value"])
        self.assertEqual("CONTRADICTORY", coherence_state["conflict_state"])

        rows = sentiment_inputs()
        directional = next(
            row for row in rows if row["axis"] == "PRICE_DIRECTIONAL_PRESSURE"
        )
        directional["required_dependency_groups"] = required_groups
        directional["contributors"] = contributors
        directional["timeframe_states"] = {
            "15m": 1,
            "1h": 1,
            "4h": 1,
            "1d": -1,
        }
        result = build_sentiment_state(
            market_snapshot=snapshot,
            dimension_inputs=rows,
            operational_synthesis="the directional axis is positive but contradictory",
        )
        directional_state = next(
            row
            for row in result["dimensions"]
            if row["axis"] == "PRICE_DIRECTIONAL_PRESSURE"
        )
        self.assertEqual(1, directional_state["ordinal_value"])
        self.assertEqual("CONTRADICTORY", directional_state["conflict_state"])

    def test_sentiment_change_preserves_unknown_without_total_probability(self) -> None:
        prior_snapshot = market_snapshot()
        prior = build_sentiment_state(
            market_snapshot=prior_snapshot,
            dimension_inputs=sentiment_inputs(),
            operational_synthesis="prior mixed ordinal vector",
        )
        current_snapshot = build_market_information_snapshot(
            run_id="run",
            cycle_index=2,
            symbol="SYNTHUSDT",
            as_of="2026-08-06T02:00:00Z",
            facts=prior_snapshot["facts"],
        )
        current = build_sentiment_state(
            market_snapshot=current_snapshot,
            dimension_inputs=sentiment_inputs(),
            operational_synthesis="current mixed ordinal vector",
        )
        change = build_sentiment_state_change(
            previous_sentiment_state=prior,
            current_sentiment_state=current,
            changed_at="2026-08-06T02:00:00Z",
        )
        self.assertEqual(
            current["sentiment_state_digest"], verify_sentiment_state(current)
        )
        self.assertEqual(
            change["sentiment_change_digest"],
            verify_sentiment_state_change(
                change,
                previous_sentiment_state=prior,
                current_sentiment_state=current,
            ),
        )
        volatility = next(
            row
            for row in change["axis_changes"]
            if row["axis"] == "VOLATILITY_STRESS"
        )
        self.assertEqual("UNKNOWN_UNCHANGED", volatility["change_label"])
        self.assertIsNone(change["overall_numeric_score"])

    def test_legacy_ten_axes_are_explicitly_mapped_to_v31_twelve_axes(self) -> None:
        snapshot = market_snapshot()
        legacy = build_sentiment_state(
            market_snapshot=snapshot,
            dimension_inputs=sentiment_inputs(),
            operational_synthesis="legacy vector requires explicit migration",
        )
        bindings = {
            contributor["fact_id"]: {
                "evidence_ref": f"datum:{contributor['fact_id']}",
                "evidence_digest": f"{index + 1:x}" * 64,
                "admissibility_level": "INFERENCE_ADMISSIBLE",
            }
            for index, dimension in enumerate(legacy["dimensions"])
            for contributor in dimension["contributors"]
        }
        migrated = migrate_legacy_sentiment_state_to_v31(
            legacy_sentiment_state=legacy,
            market_information_snapshot=snapshot,
            pit_dataset_digest="f" * 64,
            sentiment_evidence_bindings=bindings,
            downstream_scope="PATH_ACTION",
        )
        self.assertEqual(
            "LEGACY_V1_INPUT_MAPPED_TO_V31", migrated["migration_status"]
        )
        self.assertEqual(12, len(migrated["dimensions"]))
        self.assertEqual(
            [
                "FORCED_DELEVERAGING_PRESSURE",
                "ATTENTION_AND_AUDIENCE_RESPONSE",
            ],
            migrated["unmapped_axes"],
        )
        for row in migrated["dimensions"]:
            self.assertIn("alternative_explanations", row)
            self.assertIn("quality", row)
            self.assertIn("change", row)
        for axis in migrated["unmapped_axes"]:
            row = next(item for item in migrated["dimensions"] if item["axis"] == axis)
            self.assertIsNone(row["ordinal_value"])
            self.assertEqual("UNKNOWN", row["conflict_state"])

    def test_hypothesis_registry_accepts_novel_direction_and_topology(self) -> None:
        initial = reduce_hypothesis_registry(
            previous_registry=None,
            deltas=[
                hypothesis_delta(
                    "delta:create-base",
                    "CREATE",
                    targets=[],
                    replacements=[hypothesis("hypothesis:base", family="range-recovery")],
                )
            ],
            decision_at="2026-08-06T01:00:00Z",
        )
        novel = hypothesis(
            "hypothesis:novel-liquidity-vacuum",
            family="event-liquidity-vacuum-reversal",
            state="WATCH",
            created_at="2026-08-06T02:00:00Z",
            updated_at="2026-08-06T02:00:00Z",
        )
        second = reduce_hypothesis_registry(
            previous_registry=initial,
            deltas=[
                hypothesis_delta(
                    "delta:create-novel",
                    "CREATE",
                    targets=[],
                    replacements=[novel],
                    at="2026-08-06T02:00:00Z",
                )
            ],
            decision_at="2026-08-06T02:00:00Z",
        )
        self.assertIn("hypothesis:novel-liquidity-vacuum", second["known_hypothesis_ids"])
        self.assertIsNone(second["semantic_family_whitelist"])

        split_a = hypothesis(
            "hypothesis:split-a",
            family="range-recovery-fast",
            state="WATCH",
            created_at="2026-08-06T03:00:00Z",
            updated_at="2026-08-06T03:00:00Z",
            parents=["hypothesis:base"],
        )
        split_b = hypothesis(
            "hypothesis:split-b",
            family="range-recovery-slow",
            state="WATCH",
            created_at="2026-08-06T03:00:00Z",
            updated_at="2026-08-06T03:00:00Z",
            parents=["hypothesis:base"],
        )
        third = reduce_hypothesis_registry(
            previous_registry=second,
            deltas=[
                hypothesis_delta(
                    "delta:split",
                    "SPLIT",
                    targets=["hypothesis:base"],
                    replacements=[split_a, split_b],
                    at="2026-08-06T03:00:00Z",
                )
            ],
            decision_at="2026-08-06T03:00:00Z",
        )
        by_id = {row["hypothesis_id"]: row for row in third["hypotheses"]}
        self.assertEqual("SUPERSEDED", by_id["hypothesis:base"]["state"])
        self.assertTrue(
            {"hypothesis:split-a", "hypothesis:split-b"}.issubset(
                {row["hypothesis_id"] for row in third["hypotheses"] if row["state"] == "WATCH"}
            )
        )

        duplicate = hypothesis(
            "hypothesis:duplicate",
            family="duplicate-label-does-not-matter",
            state="WATCH",
            created_at="2026-08-06T04:00:00Z",
            updated_at="2026-08-06T04:00:00Z",
            dedup="dedup:event-liquidity-vacuum-reversal",
        )
        with self.assertRaisesRegex(DynamicResearchError, "DUPLICATE_HYPOTHESIS"):
            reduce_hypothesis_registry(
                previous_registry=third,
                deltas=[hypothesis_delta("delta:duplicate", "CREATE", targets=[], replacements=[duplicate], at="2026-08-06T04:00:00Z")],
                decision_at="2026-08-06T04:00:00Z",
            )

    def test_expectation_ledger_updates_and_closes_without_overwrite(self) -> None:
        first = reduce_expectation_ledger(
            previous_ledger=None,
            deltas=[
                expectation_delta(
                    "delta:expectation-create",
                    "CREATE",
                    expectation("expectation:1"),
                    target=None,
                    at="2026-08-06T01:00:00Z",
                )
            ],
            decision_at="2026-08-06T01:00:00Z",
            valid_hypothesis_ids=["hypothesis:base"],
        )
        closed = expectation(
            "expectation:1",
            status="FULFILLED",
            revision=2,
            updated_at="2026-08-06T04:00:00Z",
            closed_at="2026-08-06T04:00:00Z",
            results=["fact:result:1"],
        )
        second = reduce_expectation_ledger(
            previous_ledger=first,
            deltas=[
                expectation_delta(
                    "delta:expectation-close",
                    "CLOSE",
                    closed,
                    target="expectation:1",
                    at="2026-08-06T04:00:00Z",
                )
            ],
            decision_at="2026-08-06T04:00:00Z",
            valid_hypothesis_ids=["hypothesis:base"],
        )
        self.assertEqual([], second["open_expectation_ids"])
        self.assertEqual("FULFILLED", second["expectations"][0]["status"])
        self.assertEqual(2, len(second["known_delta_ids"]))
        self.assertEqual("OPEN", second["revision_history"][0]["expectation"]["status"])

        with self.assertRaisesRegex(DynamicResearchError, "DUPLICATE_EXPECTATION"):
            reduce_expectation_ledger(
                previous_ledger=second,
                deltas=[
                    expectation_delta(
                        "delta:expectation-duplicate",
                        "CREATE",
                        {**expectation("expectation:2"), "created_at": "2026-08-06T05:00:00Z", "updated_at": "2026-08-06T05:00:00Z", "observation_start": "2026-08-06T05:00:00Z", "observation_deadline": "2026-08-06T09:00:00Z"},
                        target=None,
                        at="2026-08-06T05:00:00Z",
                    )
                ],
                decision_at="2026-08-06T05:00:00Z",
                valid_hypothesis_ids=["hypothesis:base"],
            )

    def test_hypothesis_and_expectation_parent_graphs_reject_self_and_cycles(self) -> None:
        self_parent = hypothesis("hypothesis:self", family="self-parent")
        self_parent["parent_hypothesis_ids"] = ["hypothesis:self"]
        with self.assertRaisesRegex(
            DynamicResearchError,
            "HYPOTHESIS_PARENT_SELF_REFERENCE_FORBIDDEN",
        ):
            reduce_hypothesis_registry(
                previous_registry=None,
                deltas=[
                    hypothesis_delta(
                        "delta:create-self",
                        "CREATE",
                        targets=[],
                        replacements=[self_parent],
                    )
                ],
                decision_at="2026-08-06T01:00:00Z",
            )

        hypothesis_a = hypothesis("hypothesis:a", family="cycle-a")
        hypothesis_b = hypothesis(
            "hypothesis:b",
            family="cycle-b",
            parents=["hypothesis:a"],
        )
        hypothesis_b["premises"] = ["a distinct premise for cycle-b"]
        initial_registry = reduce_hypothesis_registry(
            previous_registry=None,
            deltas=[
                hypothesis_delta(
                    "delta:create-a",
                    "CREATE",
                    targets=[],
                    replacements=[hypothesis_a],
                ),
                hypothesis_delta(
                    "delta:create-b",
                    "CREATE",
                    targets=[],
                    replacements=[hypothesis_b],
                ),
            ],
            decision_at="2026-08-06T01:00:00Z",
        )
        revised_a = hypothesis(
            "hypothesis:a",
            family="cycle-a",
            revision=2,
            updated_at="2026-08-06T02:00:00Z",
            parents=["hypothesis:b"],
        )
        with self.assertRaisesRegex(
            DynamicResearchError, "HYPOTHESIS_PARENT_CYCLE"
        ):
            reduce_hypothesis_registry(
                previous_registry=initial_registry,
                deltas=[
                    hypothesis_delta(
                        "delta:revise-a",
                        "REVISE",
                        targets=["hypothesis:a"],
                        replacements=[revised_a],
                        at="2026-08-06T02:00:00Z",
                    )
                ],
                decision_at="2026-08-06T02:00:00Z",
            )

        self_expectation = expectation("expectation:self")
        self_expectation["parent_expectation_id"] = "expectation:self"
        with self.assertRaisesRegex(
            DynamicResearchError,
            "EXPECTATION_PARENT_SELF_REFERENCE_FORBIDDEN",
        ):
            reduce_expectation_ledger(
                previous_ledger=None,
                deltas=[
                    expectation_delta(
                        "delta:create-self-expectation",
                        "CREATE",
                        self_expectation,
                        target=None,
                        at="2026-08-06T01:00:00Z",
                    )
                ],
                decision_at="2026-08-06T01:00:00Z",
                valid_hypothesis_ids=["hypothesis:base"],
            )

        expectation_a = expectation("expectation:a")
        expectation_b = {
            **expectation("expectation:b"),
            "parent_expectation_id": "expectation:a",
            "deduplication_key": "dedup:cycle-b",
        }
        initial_ledger = reduce_expectation_ledger(
            previous_ledger=None,
            deltas=[
                expectation_delta(
                    "delta:create-expectation-a",
                    "CREATE",
                    expectation_a,
                    target=None,
                    at="2026-08-06T01:00:00Z",
                ),
                expectation_delta(
                    "delta:create-expectation-b",
                    "CREATE",
                    expectation_b,
                    target=None,
                    at="2026-08-06T01:00:00Z",
                ),
            ],
            decision_at="2026-08-06T01:00:00Z",
            valid_hypothesis_ids=["hypothesis:base"],
        )
        revised_expectation_a = {
            **expectation(
                "expectation:a",
                revision=2,
                updated_at="2026-08-06T02:00:00Z",
            ),
            "parent_expectation_id": "expectation:b",
        }
        with self.assertRaisesRegex(
            DynamicResearchError, "EXPECTATION_PARENT_CYCLE"
        ):
            reduce_expectation_ledger(
                previous_ledger=initial_ledger,
                deltas=[
                    expectation_delta(
                        "delta:revise-expectation-a",
                        "REVISE",
                        revised_expectation_a,
                        target="expectation:a",
                        at="2026-08-06T02:00:00Z",
                    )
                ],
                decision_at="2026-08-06T02:00:00Z",
                valid_hypothesis_ids=["hypothesis:base"],
            )

    def test_merge_invalidate_archive_restore_and_expire_are_replayable(self) -> None:
        initial = reduce_hypothesis_registry(
            previous_registry=None,
            deltas=[
                hypothesis_delta(
                    "delta:create-a",
                    "CREATE",
                    targets=[],
                    replacements=[hypothesis("hypothesis:a", family="mechanism-a")],
                ),
                hypothesis_delta(
                    "delta:create-b",
                    "CREATE",
                    targets=[],
                    replacements=[hypothesis("hypothesis:b", family="mechanism-b")],
                ),
            ],
            decision_at="2026-08-06T01:00:00Z",
        )
        merged = hypothesis(
            "hypothesis:merged",
            family="merged-mechanism",
            state="WATCH",
            created_at="2026-08-06T02:00:00Z",
            updated_at="2026-08-06T02:00:00Z",
            parents=["hypothesis:a", "hypothesis:b"],
        )
        state = reduce_hypothesis_registry(
            previous_registry=initial,
            deltas=[
                hypothesis_delta(
                    "delta:merge",
                    "MERGE",
                    targets=["hypothesis:a", "hypothesis:b"],
                    replacements=[merged],
                    at="2026-08-06T02:00:00Z",
                )
            ],
            decision_at="2026-08-06T02:00:00Z",
        )
        state = reduce_hypothesis_registry(
            previous_registry=state,
            deltas=[
                hypothesis_delta(
                    "delta:invalidate",
                    "INVALIDATE",
                    targets=["hypothesis:merged"],
                    replacements=[],
                    at="2026-08-06T03:00:00Z",
                    evidence=["fact:hard-falsifier"],
                    falsifier="falsifier:hypothesis:merged",
                )
            ],
            decision_at="2026-08-06T03:00:00Z",
        )
        invalidated = {row["hypothesis_id"]: row for row in state["hypotheses"]}[
            "hypothesis:merged"
        ]
        restored = {
            **invalidated,
            "revision": 2,
            "state": "WATCH",
            "updated_at": "2026-08-06T04:00:00Z",
            "agent_rationale": "new independent evidence justifies a visible restoration",
        }
        state = reduce_hypothesis_registry(
            previous_registry=state,
            deltas=[
                hypothesis_delta(
                    "delta:restore-1",
                    "RESTORE",
                    targets=["hypothesis:merged"],
                    replacements=[restored],
                    at="2026-08-06T04:00:00Z",
                    evidence=["fact:restore"],
                )
            ],
            decision_at="2026-08-06T04:00:00Z",
        )
        state = reduce_hypothesis_registry(
            previous_registry=state,
            deltas=[
                hypothesis_delta(
                    "delta:archive",
                    "ARCHIVE",
                    targets=["hypothesis:merged"],
                    replacements=[],
                    at="2026-08-06T05:00:00Z",
                    evidence=[],
                )
            ],
            decision_at="2026-08-06T05:00:00Z",
        )
        archived = {row["hypothesis_id"]: row for row in state["hypotheses"]}[
            "hypothesis:merged"
        ]
        restored_again = {
            **archived,
            "revision": 3,
            "state": "WATCH",
            "updated_at": "2026-08-06T06:00:00Z",
            "agent_rationale": "restore the archived hypothesis without deleting archive history",
        }
        state = reduce_hypothesis_registry(
            previous_registry=state,
            deltas=[
                hypothesis_delta(
                    "delta:restore-2",
                    "RESTORE",
                    targets=["hypothesis:merged"],
                    replacements=[restored_again],
                    at="2026-08-06T06:00:00Z",
                    evidence=["fact:restore-2"],
                )
            ],
            decision_at="2026-08-06T06:00:00Z",
        )
        expired = reduce_hypothesis_registry(
            previous_registry=state,
            deltas=[
                hypothesis_delta(
                    "delta:expire",
                    "EXPIRE",
                    targets=["hypothesis:merged"],
                    replacements=[],
                    at="2026-08-07T01:00:00Z",
                    evidence=[],
                )
            ],
            decision_at="2026-08-07T01:00:00Z",
        )
        by_id = {row["hypothesis_id"]: row for row in expired["hypotheses"]}
        self.assertEqual("SUPERSEDED", by_id["hypothesis:a"]["state"])
        self.assertEqual("SUPERSEDED", by_id["hypothesis:b"]["state"])
        self.assertEqual("EXPIRED", by_id["hypothesis:merged"]["state"])
        self.assertTrue(
            any(
                row["hypothesis"]["state"] == "INVALIDATED"
                for row in expired["revision_history"]
            )
        )
        self.assertEqual(
            8,
            len(expired["known_delta_ids"]),
        )


if __name__ == "__main__":
    unittest.main()
