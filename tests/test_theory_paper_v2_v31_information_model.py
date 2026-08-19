from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

from trade_system.theory_paper_v2.domain.information_model import (
    ActorKind,
    ActorRole,
    ActorRoleAssignment,
    AudienceKind,
    AudienceSegment,
    BehaviorResponseHypothesis,
    CommitmentLevel,
    InformationActor,
    InformationChannel,
    InformationEvent,
    InformationForm,
    InformationModelError,
    InformationNovelty,
    InformationScope,
    InstitutionalStatus,
    IntentInference,
    ObservedFactKind,
    ObservedInformationFact,
    PropagationClass,
    Reversibility,
    RoleAssignmentBasis,
    SourceArtifactRef,
    SourceAcquisitionMethod,
    SourceAcquisitionReceipt,
    SourceCoverage,
    SourceEvidenceBoundary,
    SourceQuality,
    SourceType,
    admit_information_event,
    build_information_event_revision_registry,
    information_event_digest,
    information_event_to_canonical_dict,
    observed_fact_from_mapping,
    source_artifact_digest,
    source_artifact_to_canonical_dict,
)


class V31InformationModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.published = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        self.observed = self.published + timedelta(minutes=1)
        self.available = self.published + timedelta(minutes=2)

    def actor(self) -> InformationActor:
        return InformationActor(
            actor_id="actor:authority",
            display_name="Fixture Monetary Authority",
            actor_kind=ActorKind.INSTITUTION,
            jurisdictions=("fixture-jurisdiction",),
            provenance_refs=("registry:actor:authority",),
            limitations=("synthetic fixture identity",),
        )

    def source(
        self,
        *,
        artifact_id: str = "source:statement:v1",
        published_at: datetime | None = None,
        observed_at: datetime | None = None,
        available_at: datetime | None = None,
        content_sha256: str = "a" * 64,
        locator: str | None = None,
        quality: SourceQuality = SourceQuality.VERIFIED_PRIMARY,
        evidence_boundary: SourceEvidenceBoundary = (
            SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED
        ),
        acquisition_receipt: SourceAcquisitionReceipt | None = None,
    ) -> SourceArtifactRef:
        return SourceArtifactRef(
            artifact_id=artifact_id,
            publisher_actor_id="actor:authority",
            locator=locator or f"fixture://{artifact_id}",
            source_type=SourceType.OFFICIAL_FULL_TEXT,
            channel=InformationChannel.OFFICIAL_RELEASE,
            propagation_class=PropagationClass.PRIMARY,
            quality=quality,
            coverage=SourceCoverage.FULL_TEXT,
            content_sha256=content_sha256,
            language="en",
            published_at=published_at or self.published,
            observed_at=observed_at or self.observed,
            available_at=available_at or self.available,
            provenance_refs=(f"receipt:{artifact_id}",),
            limitations=("synthetic fixture content",),
            evidence_boundary=evidence_boundary,
            acquisition_receipt=acquisition_receipt,
        )

    def acquisition_receipt(
        self,
        *,
        locator: str,
        content_sha256: str = "a" * 64,
    ) -> SourceAcquisitionReceipt:
        return SourceAcquisitionReceipt(
            receipt_id="acquisition:statement:v1",
            evidence_boundary=SourceEvidenceBoundary.SOURCE_ATTESTED,
            acquisition_method=SourceAcquisitionMethod.PUBLIC_HTTP_CAPTURE,
            source_locator=locator,
            acquired_at=self.observed,
            content_sha256=content_sha256,
            request_ids=("request:statement",),
            request_identity_digests=("1" * 64,),
            response_headers_digests=("2" * 64,),
            raw_body_sha256s=(content_sha256,),
            capture_record_digests=("3" * 64,),
            external_verifier_refs=(),
            external_verification_digests=(),
            limitations=(
                "The receipt attests acquisition lineage, not truth of content.",
            ),
        )

    def roles(
        self, source_id: str = "source:statement:v1"
    ) -> tuple[ActorRoleAssignment, ...]:
        common = {
            "actor_id": "actor:authority",
            "basis": RoleAssignmentBasis.LEGAL_OR_INSTITUTIONAL_MANDATE,
            "authority_scope": ("monetary-policy",),
            "valid_from": self.published - timedelta(days=365),
            "valid_to": self.published + timedelta(days=365),
            "evidence_refs": (source_id,),
            "limitations": ("role applies only within the stated authority scope",),
        }
        return (
            ActorRoleAssignment(
                assignment_id="role:rule",
                role=ActorRole.RULE_AND_SYSTEM_AUTHORITY,
                **common,
            ),
            ActorRoleAssignment(
                assignment_id="role:signal",
                role=ActorRole.ATTENTION_NARRATIVE_INFLUENCE,
                **common,
            ),
        )

    def audience(self) -> AudienceSegment:
        return AudienceSegment(
            segment_id="audience:leveraged",
            label="Leveraged directional traders",
            audience_kinds=(AudienceKind.LEVERAGED_DIRECTIONAL,),
            market_scopes=("BTCUSDT",),
            constraints=("margin capacity", "short decision horizon"),
            provenance_refs=("taxonomy:audience:v1",),
            limitations=("cohort membership is not individually observed",),
        )

    def fact(
        self,
        *,
        fact_id: str = "fact:statement:v1",
        source_id: str = "source:statement:v1",
        observed_at: datetime | None = None,
    ) -> ObservedInformationFact:
        return ObservedInformationFact(
            fact_id=fact_id,
            fact_kind=ObservedFactKind.PUBLISHED_CONTENT,
            statement="The authority published a conditional policy-path statement.",
            source_artifact_ids=(source_id,),
            observed_at=observed_at or self.observed,
            limitations=("publication is observed; sincerity is not observed",),
        )

    def intent(
        self, *, fact_id: str = "fact:statement:v1"
    ) -> IntentInference:
        return IntentInference(
            inference_id="intent:path-guidance",
            subject_actor_id="actor:authority",
            proposition="The communication may seek to coordinate expectations.",
            evidence_refs=(fact_id,),
            competing_explanations=(
                "The statement may only restate the existing reaction function.",
            ),
            falsifiers=(
                "Subsequent official actions systematically contradict the stated path.",
            ),
            limitations=("intent is inferred and is never treated as an observed fact",),
        )

    def behavior(
        self, *, fact_id: str = "fact:statement:v1"
    ) -> BehaviorResponseHypothesis:
        return BehaviorResponseHypothesis(
            hypothesis_id="behavior:deleveraging",
            audience_segment_ids=("audience:leveraged",),
            trigger_fact_ids=(fact_id,),
            if_conditions=("the statement is interpreted as a tighter future path",),
            then_expected_behaviors=("reduce leveraged long exposure",),
            observable_intermediates=("negative futures flow", "wider basis dispersion"),
            mechanism="belief revision interacts with binding margin constraints",
            horizon="next two closed one-hour bars",
            evidence_refs=(fact_id,),
            competing_explanations=(
                "positioning was already defensive and produces little additional flow",
            ),
            falsifiers=(
                "leverage and directional flow rise without an offsetting information event",
            ),
            limitations=("cohort-level response does not identify individual traders",),
        )

    def event(self) -> InformationEvent:
        source = self.source()
        fact = self.fact()
        return InformationEvent(
            event_id="information-event:fixture-policy",
            revision=1,
            previous_revision_digest=None,
            primary_actor_id="actor:authority",
            actors=(self.actor(),),
            actor_role_assignments=self.roles(),
            scopes=(InformationScope.GLOBAL_MACRO, InformationScope.INSTRUMENT),
            information_form=InformationForm.FORWARD_GUIDANCE,
            institutional_status=InstitutionalStatus.APPROVED,
            channel=InformationChannel.OFFICIAL_RELEASE,
            audiences=(self.audience(),),
            observable_message_or_action=(
                "A full-text conditional policy-path statement was published."
            ),
            novelty=InformationNovelty.NEW,
            commitment=CommitmentLevel.NON_BINDING,
            reversibility=Reversibility.REVERSIBLE,
            propagation_class=PropagationClass.PRIMARY,
            published_at=self.published,
            observed_at=self.observed,
            available_at=self.available,
            effective_at=self.published + timedelta(days=30),
            revised_at=None,
            source_artifacts=(source,),
            observed_facts=(fact,),
            intent_hypotheses=(self.intent(),),
            behavior_response_hypotheses=(self.behavior(),),
            limitations=("synthetic contract fixture; no market-direction claim",),
        )

    def revised_event(self, prior: InformationEvent) -> InformationEvent:
        revised_at = self.published + timedelta(minutes=4)
        observed_at = self.published + timedelta(minutes=5)
        available_at = self.published + timedelta(minutes=6)
        source_id = "source:statement:v2"
        fact_id = "fact:statement:v2"
        return InformationEvent(
            event_id=prior.event_id,
            revision=2,
            previous_revision_digest=information_event_digest(prior),
            primary_actor_id=prior.primary_actor_id,
            actors=prior.actors,
            actor_role_assignments=self.roles(source_id),
            scopes=prior.scopes,
            information_form=InformationForm.CORRECTION,
            institutional_status=prior.institutional_status,
            channel=prior.channel,
            audiences=prior.audiences,
            observable_message_or_action="The authority published a correction.",
            novelty=InformationNovelty.REVISION,
            commitment=prior.commitment,
            reversibility=prior.reversibility,
            propagation_class=prior.propagation_class,
            published_at=prior.published_at,
            observed_at=observed_at,
            available_at=available_at,
            effective_at=prior.effective_at,
            revised_at=revised_at,
            source_artifacts=(
                self.source(
                    artifact_id=source_id,
                    published_at=revised_at,
                    observed_at=observed_at,
                    available_at=available_at,
                    content_sha256="b" * 64,
                ),
            ),
            observed_facts=(
                self.fact(
                    fact_id=fact_id,
                    source_id=source_id,
                    observed_at=observed_at,
                ),
            ),
            intent_hypotheses=(self.intent(fact_id=fact_id),),
            behavior_response_hypotheses=(self.behavior(fact_id=fact_id),),
            limitations=prior.limitations,
        )

    def test_legal_event_is_immutable_canonical_and_point_in_time(self) -> None:
        event = self.event()
        admitted = admit_information_event(
            event, decision_at=self.available + timedelta(seconds=1)
        )
        document = information_event_to_canonical_dict(event)

        self.assertEqual(information_event_digest(event), admitted.information_event_digest)
        self.assertEqual("2026-08-06T12:02:00Z", document["available_at"])
        self.assertFalse(document["inferred_intent_is_observed_fact"])
        self.assertEqual(
            "INFERRED_NOT_OBSERVED",
            document["intent_hypotheses"][0]["epistemic_status"],
        )
        self.assertEqual(
            source_artifact_digest(event.source_artifacts[0]),
            source_artifact_digest(event.source_artifacts[0]),
        )
        with self.assertRaises(FrozenInstanceError):
            event.revision = 2  # type: ignore[misc]

    def test_verified_primary_requires_replayable_acquisition_evidence(self) -> None:
        self_reported = self.source()
        self.assertEqual(SourceQuality.UNVERIFIED, self_reported.quality)
        self.assertEqual(
            "LOCAL_INPUT_UNATTESTED",
            source_artifact_to_canonical_dict(self_reported)["evidence_boundary"],
        )

        locator = "https://authority.example/statement/v1"
        receipt = self.acquisition_receipt(locator=locator)
        attested = self.source(
            locator=locator,
            evidence_boundary=SourceEvidenceBoundary.SOURCE_ATTESTED,
            acquisition_receipt=receipt,
        )
        self.assertEqual(SourceQuality.VERIFIED_PRIMARY, attested.quality)
        document = source_artifact_to_canonical_dict(attested)
        self.assertEqual("SOURCE_ATTESTED", document["evidence_boundary"])
        self.assertEqual(64, len(document["acquisition_receipt_digest"]))
        self.assertFalse(document["acquisition_receipt"]["truth_of_content_verified"])

        with self.assertRaisesRegex(
            InformationModelError, "SOURCE_ATTESTED_RECEIPT_REQUIRED"
        ):
            self.source(
                locator=locator,
                evidence_boundary=SourceEvidenceBoundary.SOURCE_ATTESTED,
            )
        with self.assertRaisesRegex(
            InformationModelError, "SOURCE_ACQUISITION_BINDING_INVALID"
        ):
            self.source(
                locator=locator,
                content_sha256="b" * 64,
                evidence_boundary=SourceEvidenceBoundary.SOURCE_ATTESTED,
                acquisition_receipt=receipt,
            )

    def test_overlapping_temporal_roles_are_allowed(self) -> None:
        event = self.event()
        self.assertEqual(2, len(event.actor_role_assignments))
        self.assertTrue(
            all(role.is_active_at(event.published_at) for role in event.actor_role_assignments)
        )
        roles = {
            row["role"]
            for row in information_event_to_canonical_dict(event)[
                "actor_role_assignments"
            ]
        }
        self.assertEqual(
            {
                "RULE_AND_SYSTEM_AUTHORITY",
                "ATTENTION_NARRATIVE_INFLUENCE",
            },
            roles,
        )

    def test_future_availability_and_invalid_clock_order_fail_closed(self) -> None:
        event = replace(
            self.event(),
            observed_at=self.available + timedelta(minutes=7),
            available_at=self.available + timedelta(minutes=8),
        )
        with self.assertRaisesRegex(
            InformationModelError, "INFORMATION_EVENT_PIT_FUTURE_AVAILABLE"
        ):
            admit_information_event(
                event, decision_at=self.available + timedelta(minutes=1)
            )

        with self.assertRaisesRegex(
            InformationModelError, "SOURCE_ARTIFACT_TIME_ORDER_INVALID"
        ):
            self.source(
                observed_at=self.published - timedelta(seconds=1),
            )

    def test_revision_chain_is_digest_and_time_bound(self) -> None:
        prior = self.event()
        revised = self.revised_event(prior)
        admitted = admit_information_event(
            revised,
            prior_revision=prior,
            decision_at=revised.available_at + timedelta(seconds=1),
        )
        self.assertEqual(2, admitted.event.revision)

        with self.assertRaisesRegex(
            InformationModelError, "INFORMATION_EVENT_PRIOR_REVISION_REQUIRED"
        ):
            admit_information_event(
                revised,
                decision_at=revised.available_at + timedelta(seconds=1),
            )

        tampered = replace(revised, previous_revision_digest="f" * 64)
        with self.assertRaisesRegex(
            InformationModelError, "INFORMATION_EVENT_REVISION_DIGEST_MISMATCH"
        ):
            admit_information_event(
                tampered,
                prior_revision=prior,
                decision_at=revised.available_at + timedelta(seconds=1),
            )

    def test_cumulative_registry_retains_omitted_id_and_blocks_resurrection(self) -> None:
        first_event = self.event()
        cycle_1_at = self.available + timedelta(minutes=8)
        cycle_2_at = cycle_1_at + timedelta(minutes=10)
        cycle_3_at = cycle_2_at + timedelta(minutes=10)
        first = admit_information_event(first_event, decision_at=cycle_1_at)
        registry_1 = build_information_event_revision_registry(
            run_id="run:information-registry",
            cycle_index=1,
            decision_at=cycle_1_at,
            admissions=(first,),
        )

        other_event = replace(
            first_event,
            event_id="information-event:unrelated",
        )
        other = admit_information_event(other_event, decision_at=cycle_2_at)
        registry_2 = build_information_event_revision_registry(
            run_id="run:information-registry",
            cycle_index=2,
            decision_at=cycle_2_at,
            admissions=(other,),
            previous_registry=registry_1,
        )
        self.assertIn(first_event.event_id, registry_2["known_event_ids"])
        self.assertNotIn(
            first.information_event_digest,
            registry_2["current_cycle_event_digests"],
        )

        resurrected = admit_information_event(first_event, decision_at=cycle_3_at)
        with self.assertRaisesRegex(
            InformationModelError, "INFORMATION_REGISTRY_REVISION_INVALID"
        ):
            build_information_event_revision_registry(
                run_id="run:information-registry",
                cycle_index=3,
                decision_at=cycle_3_at,
                admissions=(resurrected,),
                previous_registry=registry_2,
            )

        revised_event = self.revised_event(first_event)
        revised = admit_information_event(
            revised_event,
            prior_revision=first_event,
            decision_at=cycle_3_at,
        )
        registry_3 = build_information_event_revision_registry(
            run_id="run:information-registry",
            cycle_index=3,
            decision_at=cycle_3_at,
            admissions=(revised,),
            previous_registry=registry_2,
        )
        latest = {
            row["event_id"]: row for row in registry_3["latest_revisions"]
        }
        self.assertEqual(2, latest[first_event.event_id]["revision"])

    def test_mind_reading_cannot_enter_observed_fact(self) -> None:
        raw = {
            "fact_id": "fact:raw",
            "fact_kind": "PUBLISHED_CONTENT",
            "statement": "The source published the quoted sentence.",
            "source_artifact_ids": ["source:statement:v1"],
            "observed_at": "2026-08-06T12:01:00Z",
            "limitations": ["the truth of the quoted belief is not observed"],
            "inferred_intent": "the speaker secretly intended to move price",
        }
        with self.assertRaisesRegex(
            InformationModelError, "OBSERVED_FACT_MIND_READING_FIELD_FORBIDDEN"
        ):
            observed_fact_from_mapping(raw)

        with self.assertRaisesRegex(InformationModelError, "OBSERVED_FACT_KIND_INVALID"):
            ObservedInformationFact(
                fact_id="fact:mind-reading",
                fact_kind="INFERRED_INTENT",  # type: ignore[arg-type]
                statement="The source secretly intended to move price.",
                source_artifact_ids=("source:statement:v1",),
                observed_at=self.observed,
                limitations=("not observable",),
            )

        with self.assertRaisesRegex(
            InformationModelError, "INTENT_INFERENCE_COMPETING_EXPLANATIONS_REQUIRED"
        ):
            IntentInference(
                inference_id="intent:unsupported",
                subject_actor_id="actor:authority",
                proposition="The source intended to move price.",
                evidence_refs=("fact:statement:v1",),
                competing_explanations=(),
                falsifiers=("a discriminating observation",),
                limitations=("inferred only",),
            )


if __name__ == "__main__":
    unittest.main()
