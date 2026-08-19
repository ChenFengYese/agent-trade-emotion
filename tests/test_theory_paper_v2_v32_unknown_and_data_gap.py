from __future__ import annotations

import hashlib
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    PIT_REGISTRY_DIGEST_FIELD,
    build_v32_pit_evidence_registry,
)
from trade_system.theory_paper_v2.domain.v32_data_gap_escalation import (
    ESCALATION_DIGEST_FIELD,
    V32DataGapEscalationError,
    build_v32_data_gap_escalation_v1,
    build_v32_data_gap_manual_policy_v1,
    build_v32_manual_public_evidence_revision_v1,
    verify_v32_data_gap_escalation_v1,
    verify_v32_data_gap_manual_policy_v1,
    verify_v32_manual_public_evidence_revision_v1,
)
from trade_system.theory_paper_v2.domain.v32_unknown_assessment import (
    ASSESSMENT_DIGEST_FIELD,
    EVIDENCE_REGISTRY_DIGEST_FIELD,
    OBJECTIVE_DIGEST_FIELD,
    V32UnknownAssessmentError,
    build_v32_objective_unknown_v1,
    build_v32_unknown_assessment_evidence_registry_v1,
    build_v32_unknown_subjective_assessment_v1,
    build_v32_unknown_subjective_policy_v1,
    verify_v32_objective_unknown_v1,
    verify_v32_unknown_assessment_evidence_registry_v1,
    verify_v32_unknown_subjective_assessment_v1,
    verify_v32_unknown_subjective_policy_v1,
)


RUN_ID = "v32-authorized-revision-test"
T0 = "2026-08-08T01:00:00Z"
T1 = "2026-08-08T01:01:00Z"
T2 = "2026-08-08T02:00:00Z"
FACT = "1" * 64


def _physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


def _binding(document: dict, digest_field: str, relative_ref: str) -> dict:
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": _physical(document),
    }


def _opaque_binding(name: str, digest_value: str) -> dict:
    return {
        "relative_ref": f"manual/{name}.json",
        "schema_id": f"test_{name}_v1",
        "digest_field": f"{name}_digest",
        "semantic_digest": digest_value,
        "physical_sha256": ("a" if name == "raw" else "b") * 64,
    }


def _pit_pair() -> tuple[dict, dict]:
    pit = build_v32_pit_evidence_registry(
        run_id=RUN_ID,
        cycle_index=1,
        as_of=T0,
        members=[FACT],
        upstream_snapshot_digest="2" * 64,
        capture_digest="3" * 64,
    )
    availability = self_digest(
        {
            "schema_id": "theory_paper_v32_pit_evidence_availability_registry_v1",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "as_of": T0,
            "entries": [{"evidence_ref": FACT, "available_at": T0}],
            "pit_evidence_registry_digest": pit[PIT_REGISTRY_DIGEST_FIELD],
            "public_market_analysis_bundle_digest": "4" * 64,
            "availability_policy": "FIRST_PUBLIC_AVAILABILITY_NOT_AFTER_DECISION",
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "pit_evidence_availability_registry_digest",
    )
    return pit, availability


def _unknown_objects() -> tuple[dict, dict, dict, dict, dict]:
    pit, availability = _pit_pair()
    objective = build_v32_objective_unknown_v1(
        unknown_id="unknown-order-owner",
        run_id=RUN_ID,
        cycle_index=1,
        field_path="liquidity.owner_type",
        as_of=T0,
        detected_at=T0,
        missingness_reason="public order book does not identify owner",
        source_request_refs=["okx-books"],
        impact="cannot classify institutional absorption",
        claim_ceiling="owner identity remains unknown",
    )
    registry = build_v32_unknown_assessment_evidence_registry_v1(
        registry_id="unknown-evidence-registry",
        pit_evidence_registry=pit,
        pit_evidence_registry_binding=_binding(
            pit, PIT_REGISTRY_DIGEST_FIELD, "pit/registry.json"
        ),
        pit_evidence_availability_registry=availability,
        pit_evidence_availability_registry_binding=_binding(
            availability,
            "pit_evidence_availability_registry_digest",
            "pit/availability.json",
        ),
        registered_mechanisms=[
            {
                "reference_id": "m-liquidity",
                "semantic_digest": "5" * 64,
                "available_at": T0,
                "dependency_group": "liquidity-path",
                "direction": "LONG",
            }
        ],
        registered_opposite_branches=[
            {
                "reference_id": "b-trap",
                "semantic_digest": "6" * 64,
                "available_at": T0,
                "dependency_group": "liquidity-path",
                "direction": "SHORT",
            }
        ],
        created_at=T0,
    )
    assessment = build_v32_unknown_subjective_assessment_v1(
        assessment_id="assessment-owner",
        objective_unknown=objective,
        objective_unknown_binding=_binding(
            objective, OBJECTIVE_DIGEST_FIELD, "unknown/objective.json"
        ),
        evidence_registry=registry,
        evidence_registry_binding=_binding(
            registry,
            EVIDENCE_REGISTRY_DIGEST_FIELD,
            "unknown/registry.json",
        ),
        assessed_at=T1,
        expires_at=T2,
        evidence_reference_ids=["MECHANISM:m-liquidity"],
        rationale="历史磁区可能吸引条件单，但所有者仍不可观察",
        opposite_branch_id="b-trap",
        opposite_interpretation="集中止损可能使磁区成为陷阱",
        falsifier="跌破后持续无承接",
        dependency_group="liquidity-path",
        directional_view="LONG",
        subjective_plausibility_tier="LOW",
    )
    return pit, availability, objective, registry, assessment


def _gap() -> dict:
    return build_v32_data_gap_escalation_v1(
        gap_id="gap-liquidation-owner",
        run_id=RUN_ID,
        cycle_index=1,
        request={
            "request_id": "request-1",
            "source_id": "okx-public",
            "method": "GET",
            "endpoint": "/api/v5/public/liquidation-orders",
            "field_path": "liquidations.owner_type",
        },
        requested_at=T0,
        failed_at=T1,
        error_code="PUBLIC_FIELD_UNAVAILABLE",
        error_message_digest="7" * 64,
        impact="liquidity-owner classification unavailable",
        claim_ceiling="owner remains UNKNOWN",
        allowed_official_public_sources=[
            {
                "source_id": "okx-public",
                "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
                "url": "https://www.okx.com/docs-v5/en/",
            }
        ],
    )


class UnknownDualTrackTests(unittest.TestCase):
    def test_current_pit_registry_resolves_but_objective_stays_unknown(self) -> None:
        pit, availability, objective, registry, assessment = _unknown_objects()
        self.assertEqual(
            verify_v32_objective_unknown_v1(objective),
            objective[OBJECTIVE_DIGEST_FIELD],
        )
        self.assertEqual(
            verify_v32_unknown_assessment_evidence_registry_v1(
                registry,
                pit_evidence_registry=pit,
                pit_evidence_availability_registry=availability,
            ),
            registry[EVIDENCE_REGISTRY_DIGEST_FIELD],
        )
        self.assertEqual(
            verify_v32_unknown_subjective_assessment_v1(
                assessment,
                objective_unknown=objective,
                evidence_registry=registry,
            ),
            assessment[ASSESSMENT_DIGEST_FIELD],
        )
        self.assertEqual(assessment["objective_status_after_assessment"], "UNKNOWN")
        self.assertIsNone(assessment["objective_value_after_assessment"])
        self.assertFalse(assessment["calibrated_probability_claim"])
        self.assertEqual(assessment["subjective_plausibility_tier"], "LOW")

    def test_unregistered_reference_opposite_direction_and_ttl_fail(self) -> None:
        _, _, objective, registry, _ = _unknown_objects()
        base = {
            "assessment_id": "assessment-negative",
            "objective_unknown": objective,
            "objective_unknown_binding": _binding(
                objective, OBJECTIVE_DIGEST_FIELD, "unknown/objective.json"
            ),
            "evidence_registry": registry,
            "evidence_registry_binding": _binding(
                registry,
                EVIDENCE_REGISTRY_DIGEST_FIELD,
                "unknown/registry.json",
            ),
            "assessed_at": T1,
            "expires_at": T2,
            "evidence_reference_ids": ["MECHANISM:not-registered"],
            "rationale": "有条件但不可视为事实",
            "opposite_branch_id": "b-trap",
            "opposite_interpretation": "相反路径",
            "falsifier": "条件失效",
            "dependency_group": "liquidity-path",
            "directional_view": "LONG",
            "subjective_plausibility_tier": "LOW",
        }
        with self.assertRaises(V32UnknownAssessmentError):
            build_v32_unknown_subjective_assessment_v1(**base)
        base["evidence_reference_ids"] = ["MECHANISM:m-liquidity"]
        base["directional_view"] = "SHORT"
        with self.assertRaises(V32UnknownAssessmentError):
            build_v32_unknown_subjective_assessment_v1(**base)
        base["directional_view"] = "LONG"
        base["expires_at"] = "2026-08-10T01:01:01Z"
        with self.assertRaises(V32UnknownAssessmentError):
            build_v32_unknown_subjective_assessment_v1(**base)

    def test_no_evidence_must_remain_unknown_at_extreme_uncertainty(self) -> None:
        _, _, objective, registry, _ = _unknown_objects()
        with self.assertRaises(V32UnknownAssessmentError):
            build_v32_unknown_subjective_assessment_v1(
                assessment_id="unsupported",
                objective_unknown=objective,
                objective_unknown_binding=_binding(
                    objective, OBJECTIVE_DIGEST_FIELD, "unknown/objective.json"
                ),
                evidence_registry=registry,
                evidence_registry_binding=_binding(
                    registry,
                    EVIDENCE_REGISTRY_DIGEST_FIELD,
                    "unknown/registry.json",
                ),
                assessed_at=T1,
                expires_at=T2,
                evidence_reference_ids=[],
                rationale="没有证据",
                opposite_branch_id=None,
                opposite_interpretation="没有方向",
                falsifier="没有方向",
                dependency_group="none",
                directional_view="LONG",
                subjective_plausibility_tier="LOW",
            )

    def test_unknown_policy_rejects_resigned_semantic_change(self) -> None:
        policy = build_v32_unknown_subjective_policy_v1(
            policy_id="unknown-policy", run_scope_id=RUN_ID, frozen_at=T0
        )
        self.assertEqual(
            verify_v32_unknown_subjective_policy_v1(policy),
            policy["unknown_subjective_policy_digest"],
        )
        policy["objective_zero_imputation_allowed"] = True
        policy = self_digest(policy, "unknown_subjective_policy_digest")
        with self.assertRaises(V32UnknownAssessmentError):
            verify_v32_unknown_subjective_policy_v1(policy)


class DataGapTests(unittest.TestCase):
    def test_gap_and_future_only_manual_revision_round_trip(self) -> None:
        gap = _gap()
        self.assertEqual(
            verify_v32_data_gap_escalation_v1(gap),
            gap[ESCALATION_DIGEST_FIELD],
        )
        revision = build_v32_manual_public_evidence_revision_v1(
            revision_id="manual-revision-1",
            escalation=gap,
            escalation_binding=_binding(
                gap, ESCALATION_DIGEST_FIELD, "gaps/gap.json"
            ),
            future_cycle_index=2,
            future_cycle_decision_time="2026-08-08T02:05:00Z",
            official_source_id="okx-public",
            raw_evidence_binding=_opaque_binding("raw", "8" * 64),
            capture_evidence_binding=_opaque_binding("capture", "9" * 64),
            observed_at=T0,
            available_at=T0,
            captured_at=T1,
            verified_at=T2,
        )
        self.assertEqual(
            verify_v32_manual_public_evidence_revision_v1(
                revision, escalation=gap
            ),
            revision["manual_public_evidence_revision_digest"],
        )
        self.assertFalse(revision["historical_backfill_performed"])

    def test_insecure_source_same_cycle_and_bad_time_fail_closed(self) -> None:
        with self.assertRaises(V32DataGapEscalationError):
            build_v32_data_gap_escalation_v1(
                gap_id="bad-source",
                run_id=RUN_ID,
                cycle_index=1,
                request={
                    "request_id": "r",
                    "source_id": "bad",
                    "method": "GET",
                    "endpoint": "/x",
                    "field_path": "x",
                },
                requested_at=T0,
                failed_at=T1,
                error_code="FAIL",
                error_message_digest="7" * 64,
                impact="missing",
                claim_ceiling="unknown",
                allowed_official_public_sources=[
                    {
                        "source_id": "bad",
                        "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
                        "url": "http://example.com",
                    }
                ],
            )
        gap = _gap()
        args = {
            "revision_id": "bad-cycle",
            "escalation": gap,
            "escalation_binding": _binding(
                gap, ESCALATION_DIGEST_FIELD, "gaps/gap.json"
            ),
            "future_cycle_index": 1,
            "future_cycle_decision_time": "2026-08-08T02:05:00Z",
            "official_source_id": "okx-public",
            "raw_evidence_binding": _opaque_binding("raw", "8" * 64),
            "capture_evidence_binding": _opaque_binding("capture", "9" * 64),
            "observed_at": T0,
            "available_at": T0,
            "captured_at": T1,
            "verified_at": T2,
        }
        with self.assertRaises(V32DataGapEscalationError):
            build_v32_manual_public_evidence_revision_v1(**args)
        args["future_cycle_index"] = 2
        args["observed_at"] = T2
        with self.assertRaises(V32DataGapEscalationError):
            build_v32_manual_public_evidence_revision_v1(**args)

    def test_data_gap_policy_is_exact(self) -> None:
        policy = build_v32_data_gap_manual_policy_v1(
            policy_id="gap-policy", run_scope_id=RUN_ID, frozen_at=T0
        )
        self.assertEqual(
            verify_v32_data_gap_manual_policy_v1(policy),
            policy["data_gap_manual_policy_digest"],
        )
        policy["historical_backfill_allowed"] = True
        policy = self_digest(policy, "data_gap_manual_policy_digest")
        with self.assertRaises(V32DataGapEscalationError):
            verify_v32_data_gap_manual_policy_v1(policy)


if __name__ == "__main__":
    unittest.main()
