from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from tests import test_theory_paper_v2_v32_dynamic_action_plan as action_fixture
from tests import test_theory_paper_v2_v32_public_source_collector as source_fixture
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    build_v32_action_evaluation_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    build_v32_active_authority_projection,
    build_v32_pit_evidence_registry,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_action_plan import (
    build_v32_dynamic_action_plan_v1,
    legal_v32_dynamic_action_keys_v1,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    build_v32_dynamic_research_state_v1,
)
from trade_system.theory_paper_v2.domain.v32_shadow_evaluation import (
    OPPORTUNITY_SET_DIGEST_FIELD,
    OPPORTUNITY_SET_SCHEMA_ID,
    SELECTED_PLAN_DIGEST_FIELD,
    SELECTED_PLAN_SCHEMA_ID,
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    build_v32_shadow_decision_bundle_v1,
    verify_v32_shadow_decision_bundle_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    PIT_DATUM_DIGEST_FIELD,
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_shadow_policy_adapter import (
    V32ShadowPolicyAdapterError,
    build_v32_replayable_shadow_decision_bundle_v1,
    verify_v32_replayable_shadow_decision_bundle_v1,
)


RUN_ID = "v32-test-run"
DECISION_AS_OF = "2026-08-07T00:00:10Z"
EVALUATED_AT = "2026-08-07T00:00:11Z"
CREATED_AT = "2026-08-07T00:00:12Z"


def _binding(
    document: dict,
    *,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
) -> dict[str, str]:
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


def _dynamic_state() -> dict:
    initial = action_fixture._dynamic_state()
    return build_v32_dynamic_research_state_v1(
        run_id=initial["run_id"],
        cycle_index=initial["cycle_index"],
        as_of=DECISION_AS_OF,
        frame_mode=initial["frame_mode"],
        previous_state_digest=initial["previous_state_digest"],
        market_regime_state=initial["market_regime_state"],
        unknowns=initial["unknowns"],
        zones=initial["zones"],
        hypotheses=initial["hypotheses"],
        path_modifiers=initial["path_modifiers"],
        dependency_clusters=initial["dependency_clusters"],
    )


def _risk_arithmetic() -> dict[str, str]:
    return {
        "reference_risk_upper_bound": "1",
        "subjective_plausibility_tier": "HIGH",
        "residual_uncertainty_tier": "LOW",
        "agent_reference_risk_ceiling": "0.5",
        "calculation_policy": (
            "AGENT_CEILING_ONLY_UPPER_BOUND_TIMES_MIN_SUBJECTIVE_TIER_CAP_"
            "AND_COMPLEMENT_OF_RESIDUAL_UNCERTAINTY_TIER_DERIVED_BY_"
            "SEALED_PLAN"
        ),
    }


def _action_evaluation(
    dynamic_state: dict,
    *,
    compiled_state_digest: str | None = None,
    block_selected_action: bool = False,
) -> dict:
    risk = _risk_arithmetic()
    risk_digest = canonical_digest(risk)
    rows = []
    for index, (action, direction) in enumerate(
        legal_v32_dynamic_action_keys_v1("FLAT_RESEARCH_INTENT")
    ):
        blocked = block_selected_action and (action, direction) == (
            "OPEN_PROBE",
            "LONG",
        )
        rows.append(
            {
                "candidate_id": f"evaluation-candidate-{index}",
                "action_kind": action,
                "direction": direction,
                "action_key": f"{action}:{direction}",
                "feasibility": "BLOCKED" if blocked else "ELIGIBLE",
                "block_reasons": ["GEOMETRY"] if blocked else ["NONE"],
                "evidence_refs": [f"evidence:{action.lower()}:{direction.lower()}"],
                "risk_reference_units": (
                    "0"
                    if blocked or action == "WAIT"
                    else "0.2"
                ),
                "risk_arithmetic_digest": risk_digest,
            }
        )
    return build_v32_action_evaluation_v1(
        run_id=RUN_ID,
        cycle_index=1,
        evaluated_at=EVALUATED_AT,
        proposal_consumption_digest="a" * 64,
        compiled_dynamic_state_digest=(
            compiled_state_digest
            or dynamic_state["dynamic_research_state_digest"]
        ),
        reference_context="FLAT_RESEARCH_INTENT",
        risk_arithmetic=risk,
        candidate_rows=rows,
    )


def _resign_arm(arm: dict) -> None:
    arm["derivation_receipt_digest"] = canonical_digest(
        {
            "arm_id": arm["arm_id"],
            "policy_digest": arm["policy_digest"],
            "derivation_status": arm["derivation_status"],
            "derivation_inputs": arm["derivation_inputs"],
            "derivation_input_refs": arm["derivation_input_refs"],
            "action_label": arm["action_label"],
            "direction_label": arm["direction_label"],
        }
    )


def _rebuild_with_arms(bundle: dict, arms: list[dict]) -> dict:
    return build_v32_shadow_decision_bundle_v1(
        bundle_id=bundle["bundle_id"],
        run_id=bundle["run_id"],
        decision_id=bundle["decision_id"],
        cycle_index=bundle["cycle_index"],
        as_of=bundle["as_of"],
        created_at=bundle["created_at"],
        pit_registry_binding=bundle["pit_registry_binding"],
        market_analysis_binding=bundle["market_analysis_binding"],
        opportunity_set_binding=bundle["opportunity_set_binding"],
        selected_plan_binding=bundle["selected_plan_binding"],
        decision_mark_snapshot=bundle["decision_mark_snapshot"],
        arms=arms,
    )


class V32ShadowPolicyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        store = LocalV32CycleSourceAdmissionStore(
            Path(self.temporary.name) / "source"
        )
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=source_fixture.BundleTransport(source_fixture.raw_bundle()),
            clock=source_fixture.SequenceClock(),
            store=store,
        )
        self.source = collector.collect_and_qualify(
            qualification_id="q-shadow-policy-adapter",
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=build_v32_active_authority_projection(
                run_id=RUN_ID,
                recorded_at=source_fixture.ts(source_fixture.BASE),
                experiment_contract_digest="c" * 64,
                governing_authority_binding={
                    "relative_ref": "config/v32/governing-authority.json",
                    "schema_id": AUTHORITY_SCHEMA_ID,
                    "digest_field": AUTHORITY_DIGEST_FIELD,
                    "semantic_digest": "b" * 64,
                    "physical_sha256": "e" * 64,
                },
            ),
        )
        self.dynamic_state = _dynamic_state()
        self.action_evaluation = _action_evaluation(self.dynamic_state)
        self.selected_plan = build_v32_dynamic_action_plan_v1(
            **action_fixture._flat_args(dynamic_state=self.dynamic_state)
        )
        self.upstream = {
            "public_market_analysis_bundle": (
                self.source.public_market_analysis_bundle
            ),
            "public_market_analysis_bundle_binding": (
                self.source.public_market_analysis_bundle_binding
            ),
            "pit_evidence_registry": self.source.pit_registry,
            "pit_evidence_registry_binding": self.source.pit_registry_binding,
            "sealed_action_evaluation": self.action_evaluation,
            "sealed_action_evaluation_binding": _binding(
                self.action_evaluation,
                relative_ref="cycle-0001/action-evaluation.json",
                schema_id=OPPORTUNITY_SET_SCHEMA_ID,
                digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
            ),
            "dynamic_research_state": self.dynamic_state,
            "selected_plan": self.selected_plan,
            "selected_plan_binding": _binding(
                self.selected_plan,
                relative_ref="cycle-0001/dynamic-action-plan.json",
                schema_id=SELECTED_PLAN_SCHEMA_ID,
                digest_field=SELECTED_PLAN_DIGEST_FIELD,
            ),
        }
        self.bundle = build_v32_replayable_shadow_decision_bundle_v1(
            bundle_id="shadow-bundle:adapter:0001",
            decision_id="decision:adapter:0001",
            created_at=CREATED_AT,
            **self.upstream,
        )

    def test_real_public_bundle_replays_all_policy_outputs(self) -> None:
        self.assertEqual(
            self.bundle[SHADOW_DECISION_BUNDLE_DIGEST_FIELD],
            verify_v32_replayable_shadow_decision_bundle_v1(
                self.bundle, **self.upstream
            ),
        )
        arms = {row["arm_id"]: row for row in self.bundle["arms"]}
        selected = arms["V32_SELECTED_PLAN"]
        self.assertEqual(("OPEN_PROBE", "LONG"), (
            selected["action_label"], selected["direction_label"]
        ))
        trend = arms["SIMPLE_15M_TREND"]
        self.assertEqual(("HOLD", "LONG"), (
            trend["action_label"], trend["direction_label"]
        ))
        self.assertIn(
            self.source.public_market_analysis_bundle[
                ANALYSIS_BUNDLE_DIGEST_FIELD
            ],
            self.source.pit_registry["members"],
        )

    def test_self_signed_trend_input_value_tamper_fails_replay(self) -> None:
        arms = deepcopy(self.bundle["arms"])
        trend = next(row for row in arms if row["arm_id"] == "SIMPLE_15M_TREND")
        trend["derivation_inputs"]["previous_close"] = "1"
        trend["derivation_inputs"]["latest_close"] = "2"
        _resign_arm(trend)
        forged = _rebuild_with_arms(self.bundle, arms)
        self.assertEqual(
            forged[SHADOW_DECISION_BUNDLE_DIGEST_FIELD],
            verify_v32_shadow_decision_bundle_v1(forged),
        )
        with self.assertRaisesRegex(
            V32ShadowPolicyAdapterError, "BUNDLE_REPLAY_MISMATCH"
        ):
            verify_v32_replayable_shadow_decision_bundle_v1(
                forged, **self.upstream
            )

    def test_self_signed_selected_policy_action_forgery_fails_replay(self) -> None:
        arms = deepcopy(self.bundle["arms"])
        selected = next(row for row in arms if row["arm_id"] == "V32_SELECTED_PLAN")
        selected["derivation_inputs"]["action_label"] = "WAIT"
        selected["derivation_inputs"]["direction_label"] = "NONE"
        selected["action_label"] = "WAIT"
        selected["direction_label"] = "NONE"
        _resign_arm(selected)
        forged = _rebuild_with_arms(self.bundle, arms)
        self.assertEqual(
            forged[SHADOW_DECISION_BUNDLE_DIGEST_FIELD],
            verify_v32_shadow_decision_bundle_v1(forged),
        )
        with self.assertRaisesRegex(
            V32ShadowPolicyAdapterError, "BUNDLE_REPLAY_MISMATCH"
        ):
            verify_v32_replayable_shadow_decision_bundle_v1(
                forged, **self.upstream
            )

    def test_pit_registry_datum_mismatch_fails_before_policy_replay(self) -> None:
        latest_bar = self.source.public_market_analysis_bundle[
            "closed_bar_series"
        ]["15M"][-1]
        latest_datum = next(
            row
            for row in self.source.public_market_analysis_bundle["datums"]
            if row["datum_id"]
            == f"bar-15m-{latest_bar['open_time_ms']}-close"
        )
        latest_digest = latest_datum[PIT_DATUM_DIGEST_FIELD]
        members = set(self.source.pit_registry["members"])
        replacement = "f" * 64
        self.assertIn(latest_digest, members)
        self.assertNotIn(replacement, members)
        members.remove(latest_digest)
        members.add(replacement)
        mismatched = build_v32_pit_evidence_registry(
            run_id=RUN_ID,
            cycle_index=1,
            as_of=self.source.pit_registry["as_of"],
            members=sorted(members),
            upstream_snapshot_digest=self.source.pit_registry[
                "upstream_semantic_digest"
            ],
            capture_digest=self.source.pit_registry[
                "full_verification_receipt_digest"
            ],
        )
        upstream = dict(self.upstream)
        upstream["pit_evidence_registry"] = mismatched
        upstream["pit_evidence_registry_binding"] = _binding(
            mismatched,
            relative_ref="cycle-0001/mismatched-pit-registry.json",
            schema_id=PIT_REGISTRY_SCHEMA_ID,
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32ShadowPolicyAdapterError, "PIT_REGISTRY_MISMATCH"
        ):
            build_v32_replayable_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:pit-mismatch",
                decision_id="decision:pit-mismatch",
                created_at=CREATED_AT,
                **upstream,
            )

    def test_action_evaluation_must_bind_the_exact_dynamic_state(self) -> None:
        evaluation = _action_evaluation(
            self.dynamic_state, compiled_state_digest="d" * 64
        )
        upstream = dict(self.upstream)
        upstream["sealed_action_evaluation"] = evaluation
        upstream["sealed_action_evaluation_binding"] = _binding(
            evaluation,
            relative_ref="cycle-0001/wrong-state-action-evaluation.json",
            schema_id=OPPORTUNITY_SET_SCHEMA_ID,
            digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32ShadowPolicyAdapterError, "CROSS_BINDING_INVALID"
        ):
            build_v32_replayable_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:wrong-state",
                decision_id="decision:wrong-state",
                created_at=CREATED_AT,
                **upstream,
            )

    def test_selected_action_must_be_eligible_in_sealed_opportunity_set(self) -> None:
        evaluation = _action_evaluation(
            self.dynamic_state, block_selected_action=True
        )
        upstream = dict(self.upstream)
        upstream["sealed_action_evaluation"] = evaluation
        upstream["sealed_action_evaluation_binding"] = _binding(
            evaluation,
            relative_ref="cycle-0001/blocked-action-evaluation.json",
            schema_id=OPPORTUNITY_SET_SCHEMA_ID,
            digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32ShadowPolicyAdapterError, "SELECTED_ACTION_NOT_ELIGIBLE"
        ):
            build_v32_replayable_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:blocked-selection",
                decision_id="decision:blocked-selection",
                created_at=CREATED_AT,
                **upstream,
            )


if __name__ == "__main__":
    unittest.main()
