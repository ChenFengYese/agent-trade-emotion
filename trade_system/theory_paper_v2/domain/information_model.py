"""Pure V3.1 information-layer contracts.

This module separates observable information from interpretations about intent
and audience behaviour.  It owns local invariants, point-in-time admission,
revision-chain validation, and canonical serialization.  It performs no IO,
does not fetch sources, and grants no trading or execution authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

from .contracts.canonical import canonical_digest


class InformationModelError(ValueError):
    """An information-layer contract failed closed."""


class ActorKind(StrEnum):
    INSTITUTION = "INSTITUTION"
    ORGANIZATION = "ORGANIZATION"
    COMPANY = "COMPANY"
    PROTOCOL = "PROTOCOL"
    COLLECTIVE = "COLLECTIVE"
    PERSON = "PERSON"
    MARKET_COHORT = "MARKET_COHORT"
    UNKNOWN = "UNKNOWN"


class ActorRole(StrEnum):
    RULE_AND_SYSTEM_AUTHORITY = "RULE_AND_SYSTEM_AUTHORITY"
    LIQUIDITY_AND_INTERMEDIATION = "LIQUIDITY_AND_INTERMEDIATION"
    ISSUER_MANAGER_GOVERNANCE = "ISSUER_MANAGER_GOVERNANCE"
    POLITICAL_AGENDA_AND_POLICY_SIGNAL = "POLITICAL_AGENDA_AND_POLICY_SIGNAL"
    ATTENTION_NARRATIVE_INFLUENCE = "ATTENTION_NARRATIVE_INFLUENCE"
    ENDOGENOUS_MARKET_PARTICIPANT = "ENDOGENOUS_MARKET_PARTICIPANT"


class RoleAssignmentBasis(StrEnum):
    LEGAL_OR_INSTITUTIONAL_MANDATE = "LEGAL_OR_INSTITUTIONAL_MANDATE"
    SELF_DECLARED_PUBLIC_ROLE = "SELF_DECLARED_PUBLIC_ROLE"
    OBSERVED_MARKET_FUNCTION = "OBSERVED_MARKET_FUNCTION"
    RESEARCH_CLASSIFICATION = "RESEARCH_CLASSIFICATION"


class AudienceKind(StrEnum):
    LONG_HORIZON_FUNDAMENTAL = "LONG_HORIZON_FUNDAMENTAL"
    LEVERAGED_DIRECTIONAL = "LEVERAGED_DIRECTIONAL"
    OPTIONS_AND_VOLATILITY = "OPTIONS_AND_VOLATILITY"
    MARKET_MAKING_ARBITRAGE_AND_INVENTORY = (
        "MARKET_MAKING_ARBITRAGE_AND_INVENTORY"
    )
    PASSIVE_AND_RULE_BASED = "PASSIVE_AND_RULE_BASED"
    RETAIL_AND_ATTENTION_DRIVEN = "RETAIL_AND_ATTENTION_DRIVEN"
    ISSUER_OPERATOR_OR_GOVERNANCE = "ISSUER_OPERATOR_OR_GOVERNANCE"
    REGULATORY_COMPLIANCE_AND_BANKING = "REGULATORY_COMPLIANCE_AND_BANKING"


class InformationScope(StrEnum):
    GLOBAL_MACRO = "GLOBAL_MACRO"
    SECTOR = "SECTOR"
    VENUE = "VENUE"
    ENTITY = "ENTITY"
    INSTRUMENT = "INSTRUMENT"
    PORTFOLIO = "PORTFOLIO"


class InformationForm(StrEnum):
    OBSERVED_ACTION = "OBSERVED_ACTION"
    FORMAL_RULE = "FORMAL_RULE"
    POLICY_DECISION = "POLICY_DECISION"
    FORWARD_GUIDANCE = "FORWARD_GUIDANCE"
    DISCLOSURE = "DISCLOSURE"
    OPINION = "OPINION"
    RUMOR = "RUMOR"
    CORRECTION = "CORRECTION"
    SILENCE_OR_WITHHOLDING_HYPOTHESIS = "SILENCE_OR_WITHHOLDING_HYPOTHESIS"


class InstitutionalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CONSULTATION = "CONSULTATION"
    APPROVED = "APPROVED"
    EFFECTIVE = "EFFECTIVE"
    ENFORCED = "ENFORCED"
    REVERSED = "REVERSED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class InformationNovelty(StrEnum):
    NEW = "NEW"
    CONFIRMATION = "CONFIRMATION"
    REVISION = "REVISION"
    REPETITION = "REPETITION"
    CONTRADICTION = "CONTRADICTION"


class CommitmentLevel(StrEnum):
    NON_BINDING = "NON_BINDING"
    PARTIALLY_BINDING = "PARTIALLY_BINDING"
    BINDING = "BINDING"


class Reversibility(StrEnum):
    REVERSIBLE = "REVERSIBLE"
    COSTLY_TO_REVERSE = "COSTLY_TO_REVERSE"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class PropagationClass(StrEnum):
    PRIMARY = "PRIMARY"
    SYNDICATED = "SYNDICATED"
    COMMENTARY = "COMMENTARY"
    DERIVED_SUMMARY = "DERIVED_SUMMARY"


class InformationChannel(StrEnum):
    OFFICIAL_RELEASE = "OFFICIAL_RELEASE"
    REGULATORY_FILING = "REGULATORY_FILING"
    PRESS_CONFERENCE = "PRESS_CONFERENCE"
    INTERVIEW = "INTERVIEW"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    MARKET_TRANSACTION = "MARKET_TRANSACTION"
    ONCHAIN_ACTION = "ONCHAIN_ACTION"
    CODE_OR_GOVERNANCE = "CODE_OR_GOVERNANCE"
    DATA_FEED = "DATA_FEED"
    OTHER = "OTHER"


class SourceType(StrEnum):
    OFFICIAL_FULL_TEXT = "OFFICIAL_FULL_TEXT"
    DIRECT_PUBLIC_STATEMENT = "DIRECT_PUBLIC_STATEMENT"
    REGULATORY_FILING = "REGULATORY_FILING"
    PRIMARY_MARKET_DATA = "PRIMARY_MARKET_DATA"
    ONCHAIN_RECORD = "ONCHAIN_RECORD"
    SECONDARY_REPORT = "SECONDARY_REPORT"
    SOCIAL_MEDIA_POST = "SOCIAL_MEDIA_POST"
    DERIVED_SUMMARY = "DERIVED_SUMMARY"


class SourceQuality(StrEnum):
    VERIFIED_PRIMARY = "VERIFIED_PRIMARY"
    VERIFIED_SECONDARY = "VERIFIED_SECONDARY"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class SourceCoverage(StrEnum):
    FULL_TEXT = "FULL_TEXT"
    PARTIAL_TEXT = "PARTIAL_TEXT"
    METADATA_ONLY = "METADATA_ONLY"
    UNKNOWN = "UNKNOWN"


class SourceEvidenceBoundary(StrEnum):
    """What the local runtime can actually prove about source acquisition."""

    LOCAL_SYNTHETIC = "LOCAL_SYNTHETIC"
    LOCAL_INPUT_UNATTESTED = "LOCAL_INPUT_UNATTESTED"
    SOURCE_ATTESTED = "SOURCE_ATTESTED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


class SourceAcquisitionMethod(StrEnum):
    LOCAL_SYNTHETIC_FIXTURE = "LOCAL_SYNTHETIC_FIXTURE"
    LOCAL_SNAPSHOT_IMPORT = "LOCAL_SNAPSHOT_IMPORT"
    PUBLIC_HTTP_CAPTURE = "PUBLIC_HTTP_CAPTURE"


class ObservedFactKind(StrEnum):
    PUBLISHED_CONTENT = "PUBLISHED_CONTENT"
    OBSERVABLE_ACTION = "OBSERVABLE_ACTION"
    INSTITUTIONAL_STATUS = "INSTITUTIONAL_STATUS"
    TIMING = "TIMING"
    MARKET_REACTION = "MARKET_REACTION"


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_OBSERVED_FACT_FIELDS = frozenset(
    {
        "inferred_intent",
        "intent",
        "hidden_intent",
        "motive",
        "hidden_motive",
        "true_motive",
        "psychological_state",
    }
)
_OBSERVED_FACT_MAPPING_FIELDS = frozenset(
    {"fact_id", "fact_kind", "statement", "source_artifact_ids", "observed_at", "limitations"}
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InformationModelError(code)
    return value.strip()


def _string_tuple(
    value: Any, code: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise InformationModelError(code)
    if (
        (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise InformationModelError(code)
    return value


def _enum_tuple(value: Any, enum_type: type[StrEnum], code: str) -> tuple[StrEnum, ...]:
    if (
        not isinstance(value, tuple)
        or not value
        or any(not isinstance(item, enum_type) for item in value)
        or len(value) != len(set(value))
    ):
        raise InformationModelError(code)
    return value


def _aware(value: Any, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InformationModelError(code)
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _unique_ids(values: tuple[Any, ...], field: str, code: str) -> set[str]:
    identities = tuple(getattr(value, field, None) for value in values)
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise InformationModelError(code)
    if len(identities) != len(set(identities)):
        raise InformationModelError(code)
    return set(identities)


def _check_refs(refs: tuple[str, ...], allowed: set[str], code: str) -> None:
    if not set(refs).issubset(allowed):
        raise InformationModelError(code)


@dataclass(frozen=True, slots=True)
class SourceAcquisitionReceipt:
    """Replayable acquisition evidence, not a claim that content is true."""

    receipt_id: str
    evidence_boundary: SourceEvidenceBoundary
    acquisition_method: SourceAcquisitionMethod
    source_locator: str
    acquired_at: datetime
    content_sha256: str
    request_ids: tuple[str, ...]
    request_identity_digests: tuple[str, ...]
    response_headers_digests: tuple[str, ...]
    raw_body_sha256s: tuple[str, ...]
    capture_record_digests: tuple[str, ...]
    external_verifier_refs: tuple[str, ...]
    external_verification_digests: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.receipt_id, "SOURCE_ACQUISITION_RECEIPT_ID_INVALID")
        if not isinstance(self.evidence_boundary, SourceEvidenceBoundary):
            raise InformationModelError("SOURCE_EVIDENCE_BOUNDARY_INVALID")
        if not isinstance(self.acquisition_method, SourceAcquisitionMethod):
            raise InformationModelError("SOURCE_ACQUISITION_METHOD_INVALID")
        _text(self.source_locator, "SOURCE_ACQUISITION_LOCATOR_INVALID")
        _aware(self.acquired_at, "SOURCE_ACQUISITION_TIME_INVALID")
        if not isinstance(self.content_sha256, str) or not _HEX_64.fullmatch(
            self.content_sha256
        ):
            raise InformationModelError("SOURCE_ACQUISITION_CONTENT_DIGEST_INVALID")
        _string_tuple(self.request_ids, "SOURCE_ACQUISITION_REQUEST_IDS_INVALID", allow_empty=True)
        for values, code in (
            (self.request_identity_digests, "SOURCE_ACQUISITION_REQUEST_DIGESTS_INVALID"),
            (self.response_headers_digests, "SOURCE_ACQUISITION_HEADER_DIGESTS_INVALID"),
            (self.raw_body_sha256s, "SOURCE_ACQUISITION_RAW_DIGESTS_INVALID"),
            (self.capture_record_digests, "SOURCE_ACQUISITION_RECORD_DIGESTS_INVALID"),
            (self.external_verification_digests, "SOURCE_EXTERNAL_VERIFICATION_DIGESTS_INVALID"),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or _HEX_64.fullmatch(value) is None
                for value in values
            ):
                raise InformationModelError(code)
        _string_tuple(
            self.external_verifier_refs,
            "SOURCE_EXTERNAL_VERIFIER_REFS_INVALID",
            allow_empty=True,
        )
        _string_tuple(self.limitations, "SOURCE_ACQUISITION_LIMITATIONS_INVALID")
        transport_lengths = {
            len(self.request_ids),
            len(self.request_identity_digests),
            len(self.response_headers_digests),
            len(self.raw_body_sha256s),
            len(self.capture_record_digests),
        }
        transport_present = any(transport_lengths)
        external_present = bool(
            self.external_verifier_refs or self.external_verification_digests
        )
        if self.evidence_boundary is SourceEvidenceBoundary.LOCAL_SYNTHETIC:
            if (
                self.acquisition_method
                is not SourceAcquisitionMethod.LOCAL_SYNTHETIC_FIXTURE
                or transport_present
                or external_present
            ):
                raise InformationModelError("SOURCE_SYNTHETIC_EVIDENCE_OVERCLAIM")
        elif self.evidence_boundary is SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED:
            if (
                self.acquisition_method
                is not SourceAcquisitionMethod.LOCAL_SNAPSHOT_IMPORT
                or transport_present
                or external_present
            ):
                raise InformationModelError("SOURCE_UNATTESTED_EVIDENCE_OVERCLAIM")
        else:
            if (
                self.acquisition_method
                is not SourceAcquisitionMethod.PUBLIC_HTTP_CAPTURE
                or transport_lengths == {0}
                or len(transport_lengths) != 1
            ):
                raise InformationModelError("SOURCE_ATTESTED_CAPTURE_EVIDENCE_INVALID")
            if self.evidence_boundary is SourceEvidenceBoundary.SOURCE_ATTESTED:
                if external_present:
                    raise InformationModelError("SOURCE_ATTESTED_EXTERNAL_PROOF_FORBIDDEN")
            elif (
                not self.external_verifier_refs
                or len(self.external_verifier_refs)
                != len(self.external_verification_digests)
            ):
                raise InformationModelError("SOURCE_EXTERNAL_VERIFICATION_REQUIRED")


@dataclass(frozen=True, slots=True)
class InformationActor:
    actor_id: str
    display_name: str
    actor_kind: ActorKind
    jurisdictions: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.actor_id, "INFORMATION_ACTOR_ID_INVALID")
        _text(self.display_name, "INFORMATION_ACTOR_NAME_INVALID")
        if not isinstance(self.actor_kind, ActorKind):
            raise InformationModelError("INFORMATION_ACTOR_KIND_INVALID")
        _string_tuple(
            self.jurisdictions, "INFORMATION_ACTOR_JURISDICTIONS_INVALID", allow_empty=True
        )
        _string_tuple(self.provenance_refs, "INFORMATION_ACTOR_PROVENANCE_INVALID")
        _string_tuple(self.limitations, "INFORMATION_ACTOR_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class ActorRoleAssignment:
    assignment_id: str
    actor_id: str
    role: ActorRole
    basis: RoleAssignmentBasis
    authority_scope: tuple[str, ...]
    valid_from: datetime
    valid_to: datetime | None
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.assignment_id, "ACTOR_ROLE_ASSIGNMENT_ID_INVALID")
        _text(self.actor_id, "ACTOR_ROLE_ACTOR_ID_INVALID")
        if not isinstance(self.role, ActorRole):
            raise InformationModelError("ACTOR_ROLE_INVALID")
        if not isinstance(self.basis, RoleAssignmentBasis):
            raise InformationModelError("ACTOR_ROLE_BASIS_INVALID")
        _string_tuple(self.authority_scope, "ACTOR_ROLE_AUTHORITY_SCOPE_INVALID")
        valid_from = _aware(self.valid_from, "ACTOR_ROLE_TIME_INVALID")
        if self.valid_to is not None:
            valid_to = _aware(self.valid_to, "ACTOR_ROLE_TIME_INVALID")
            if valid_to <= valid_from:
                raise InformationModelError("ACTOR_ROLE_TIME_ORDER_INVALID")
        _string_tuple(self.evidence_refs, "ACTOR_ROLE_EVIDENCE_INVALID")
        _string_tuple(self.limitations, "ACTOR_ROLE_LIMITATIONS_INVALID")

    def is_active_at(self, supplied_time: datetime) -> bool:
        instant = _aware(supplied_time, "ACTOR_ROLE_QUERY_TIME_INVALID")
        start = self.valid_from.astimezone(UTC)
        end = self.valid_to.astimezone(UTC) if self.valid_to is not None else None
        return start <= instant and (end is None or instant < end)


@dataclass(frozen=True, slots=True)
class AudienceSegment:
    segment_id: str
    label: str
    audience_kinds: tuple[AudienceKind, ...]
    market_scopes: tuple[str, ...]
    constraints: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.segment_id, "AUDIENCE_SEGMENT_ID_INVALID")
        _text(self.label, "AUDIENCE_SEGMENT_LABEL_INVALID")
        _enum_tuple(self.audience_kinds, AudienceKind, "AUDIENCE_SEGMENT_KIND_INVALID")
        _string_tuple(self.market_scopes, "AUDIENCE_SEGMENT_SCOPE_INVALID")
        _string_tuple(self.constraints, "AUDIENCE_SEGMENT_CONSTRAINTS_INVALID")
        _string_tuple(self.provenance_refs, "AUDIENCE_SEGMENT_PROVENANCE_INVALID")
        _string_tuple(self.limitations, "AUDIENCE_SEGMENT_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class SourceArtifactRef:
    artifact_id: str
    publisher_actor_id: str
    locator: str
    source_type: SourceType
    channel: InformationChannel
    propagation_class: PropagationClass
    quality: SourceQuality
    coverage: SourceCoverage
    content_sha256: str
    language: str
    published_at: datetime
    observed_at: datetime
    available_at: datetime
    provenance_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence_boundary: SourceEvidenceBoundary = (
        SourceEvidenceBoundary.LOCAL_INPUT_UNATTESTED
    )
    acquisition_receipt: SourceAcquisitionReceipt | None = None

    def __post_init__(self) -> None:
        _text(self.artifact_id, "SOURCE_ARTIFACT_ID_INVALID")
        _text(self.publisher_actor_id, "SOURCE_ARTIFACT_PUBLISHER_INVALID")
        _text(self.locator, "SOURCE_ARTIFACT_LOCATOR_INVALID")
        if not isinstance(self.source_type, SourceType):
            raise InformationModelError("SOURCE_ARTIFACT_TYPE_INVALID")
        if not isinstance(self.channel, InformationChannel):
            raise InformationModelError("SOURCE_ARTIFACT_CHANNEL_INVALID")
        if not isinstance(self.propagation_class, PropagationClass):
            raise InformationModelError("SOURCE_ARTIFACT_PROPAGATION_INVALID")
        if not isinstance(self.quality, SourceQuality):
            raise InformationModelError("SOURCE_ARTIFACT_QUALITY_INVALID")
        if not isinstance(self.evidence_boundary, SourceEvidenceBoundary):
            raise InformationModelError("SOURCE_EVIDENCE_BOUNDARY_INVALID")
        if not isinstance(self.coverage, SourceCoverage):
            raise InformationModelError("SOURCE_ARTIFACT_COVERAGE_INVALID")
        if not isinstance(self.content_sha256, str) or not _HEX_64.fullmatch(
            self.content_sha256
        ):
            raise InformationModelError("SOURCE_ARTIFACT_DIGEST_INVALID")
        _text(self.language, "SOURCE_ARTIFACT_LANGUAGE_INVALID")
        published = _aware(self.published_at, "SOURCE_ARTIFACT_TIME_INVALID")
        observed = _aware(self.observed_at, "SOURCE_ARTIFACT_TIME_INVALID")
        available = _aware(self.available_at, "SOURCE_ARTIFACT_TIME_INVALID")
        if not published <= observed <= available:
            raise InformationModelError("SOURCE_ARTIFACT_TIME_ORDER_INVALID")
        receipt = self.acquisition_receipt
        if receipt is not None:
            if not isinstance(receipt, SourceAcquisitionReceipt):
                raise InformationModelError("SOURCE_ACQUISITION_RECEIPT_INVALID")
            if (
                receipt.evidence_boundary is not self.evidence_boundary
                or receipt.source_locator != self.locator
                or receipt.content_sha256 != self.content_sha256
                or receipt.acquired_at.astimezone(UTC) > observed
            ):
                raise InformationModelError("SOURCE_ACQUISITION_BINDING_INVALID")
        elif self.evidence_boundary in {
            SourceEvidenceBoundary.SOURCE_ATTESTED,
            SourceEvidenceBoundary.EXTERNALLY_VERIFIED,
        }:
            raise InformationModelError("SOURCE_ATTESTED_RECEIPT_REQUIRED")
        if self.quality in {
            SourceQuality.VERIFIED_PRIMARY,
            SourceQuality.VERIFIED_SECONDARY,
        }:
            if self.evidence_boundary not in {
                SourceEvidenceBoundary.SOURCE_ATTESTED,
                SourceEvidenceBoundary.EXTERNALLY_VERIFIED,
            }:
                # A caller-supplied quality label cannot unlock verification.
                object.__setattr__(
                    self,
                    "quality",
                    (
                        SourceQuality.PARTIAL
                        if self.evidence_boundary
                        is SourceEvidenceBoundary.LOCAL_SYNTHETIC
                        else SourceQuality.UNVERIFIED
                    ),
                )
            elif receipt is None:  # guarded above; retained as an explicit invariant
                raise InformationModelError("SOURCE_VERIFIED_RECEIPT_REQUIRED")
        if self.quality is SourceQuality.VERIFIED_PRIMARY and (
            self.source_type
            not in {
                SourceType.OFFICIAL_FULL_TEXT,
                SourceType.DIRECT_PUBLIC_STATEMENT,
                SourceType.REGULATORY_FILING,
                SourceType.PRIMARY_MARKET_DATA,
                SourceType.ONCHAIN_RECORD,
            }
            or self.propagation_class is not PropagationClass.PRIMARY
        ):
            raise InformationModelError("SOURCE_VERIFIED_PRIMARY_TYPE_INVALID")
        _string_tuple(self.provenance_refs, "SOURCE_ARTIFACT_PROVENANCE_INVALID")
        _string_tuple(self.limitations, "SOURCE_ARTIFACT_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class ObservedInformationFact:
    """A source-bound observation, never an assertion about hidden mental state."""

    fact_id: str
    fact_kind: ObservedFactKind
    statement: str
    source_artifact_ids: tuple[str, ...]
    observed_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.fact_id, "OBSERVED_INFORMATION_FACT_ID_INVALID")
        if not isinstance(self.fact_kind, ObservedFactKind):
            raise InformationModelError("OBSERVED_FACT_KIND_INVALID")
        _text(self.statement, "OBSERVED_INFORMATION_FACT_STATEMENT_INVALID")
        _string_tuple(
            self.source_artifact_ids, "OBSERVED_INFORMATION_FACT_SOURCES_INVALID"
        )
        _aware(self.observed_at, "OBSERVED_INFORMATION_FACT_TIME_INVALID")
        _string_tuple(
            self.limitations, "OBSERVED_INFORMATION_FACT_LIMITATIONS_INVALID"
        )


@dataclass(frozen=True, slots=True)
class IntentInference:
    """An explicit, contestable interpretation; it is not an observed fact."""

    inference_id: str
    subject_actor_id: str
    proposition: str
    evidence_refs: tuple[str, ...]
    competing_explanations: tuple[str, ...]
    falsifiers: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.inference_id, "INTENT_INFERENCE_ID_INVALID")
        _text(self.subject_actor_id, "INTENT_INFERENCE_ACTOR_INVALID")
        _text(self.proposition, "INTENT_INFERENCE_PROPOSITION_INVALID")
        _string_tuple(self.evidence_refs, "INTENT_INFERENCE_EVIDENCE_INVALID")
        _string_tuple(
            self.competing_explanations,
            "INTENT_INFERENCE_COMPETING_EXPLANATIONS_REQUIRED",
        )
        _string_tuple(self.falsifiers, "INTENT_INFERENCE_FALSIFIERS_REQUIRED")
        _string_tuple(self.limitations, "INTENT_INFERENCE_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class BehaviorResponseHypothesis:
    hypothesis_id: str
    audience_segment_ids: tuple[str, ...]
    trigger_fact_ids: tuple[str, ...]
    if_conditions: tuple[str, ...]
    then_expected_behaviors: tuple[str, ...]
    observable_intermediates: tuple[str, ...]
    mechanism: str
    horizon: str
    evidence_refs: tuple[str, ...]
    competing_explanations: tuple[str, ...]
    falsifiers: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.hypothesis_id, "BEHAVIOR_RESPONSE_ID_INVALID")
        _string_tuple(
            self.audience_segment_ids, "BEHAVIOR_RESPONSE_AUDIENCE_INVALID"
        )
        _string_tuple(self.trigger_fact_ids, "BEHAVIOR_RESPONSE_TRIGGERS_INVALID")
        _string_tuple(self.if_conditions, "BEHAVIOR_RESPONSE_IF_INVALID")
        _string_tuple(
            self.then_expected_behaviors, "BEHAVIOR_RESPONSE_THEN_INVALID"
        )
        _string_tuple(
            self.observable_intermediates, "BEHAVIOR_RESPONSE_INTERMEDIATES_INVALID"
        )
        _text(self.mechanism, "BEHAVIOR_RESPONSE_MECHANISM_INVALID")
        _text(self.horizon, "BEHAVIOR_RESPONSE_HORIZON_INVALID")
        _string_tuple(self.evidence_refs, "BEHAVIOR_RESPONSE_EVIDENCE_INVALID")
        _string_tuple(
            self.competing_explanations,
            "BEHAVIOR_RESPONSE_COMPETING_EXPLANATIONS_REQUIRED",
        )
        _string_tuple(self.falsifiers, "BEHAVIOR_RESPONSE_FALSIFIERS_REQUIRED")
        _string_tuple(self.limitations, "BEHAVIOR_RESPONSE_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class InformationEvent:
    event_id: str
    revision: int
    previous_revision_digest: str | None
    primary_actor_id: str
    actors: tuple[InformationActor, ...]
    actor_role_assignments: tuple[ActorRoleAssignment, ...]
    scopes: tuple[InformationScope, ...]
    information_form: InformationForm
    institutional_status: InstitutionalStatus
    channel: InformationChannel
    audiences: tuple[AudienceSegment, ...]
    observable_message_or_action: str
    novelty: InformationNovelty
    commitment: CommitmentLevel
    reversibility: Reversibility
    propagation_class: PropagationClass
    published_at: datetime
    observed_at: datetime
    available_at: datetime
    effective_at: datetime
    revised_at: datetime | None
    source_artifacts: tuple[SourceArtifactRef, ...]
    observed_facts: tuple[ObservedInformationFact, ...]
    intent_hypotheses: tuple[IntentInference, ...]
    behavior_response_hypotheses: tuple[BehaviorResponseHypothesis, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.event_id, "INFORMATION_EVENT_ID_INVALID")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise InformationModelError("INFORMATION_EVENT_REVISION_INVALID")
        if self.revision == 1:
            if self.previous_revision_digest is not None or self.revised_at is not None:
                raise InformationModelError("INFORMATION_EVENT_GENESIS_REVISION_INVALID")
        elif (
            not isinstance(self.previous_revision_digest, str)
            or not _HEX_64.fullmatch(self.previous_revision_digest)
            or self.revised_at is None
        ):
            raise InformationModelError("INFORMATION_EVENT_REVISION_LINK_INVALID")
        _text(self.primary_actor_id, "INFORMATION_EVENT_PRIMARY_ACTOR_INVALID")
        if not isinstance(self.actors, tuple) or not self.actors:
            raise InformationModelError("INFORMATION_EVENT_ACTORS_INVALID")
        actor_ids = _unique_ids(self.actors, "actor_id", "INFORMATION_EVENT_ACTORS_INVALID")
        if self.primary_actor_id not in actor_ids:
            raise InformationModelError("INFORMATION_EVENT_PRIMARY_ACTOR_UNKNOWN")
        if not isinstance(self.actor_role_assignments, tuple) or not self.actor_role_assignments:
            raise InformationModelError("INFORMATION_EVENT_ROLES_INVALID")
        _unique_ids(
            self.actor_role_assignments,
            "assignment_id",
            "INFORMATION_EVENT_ROLE_IDS_INVALID",
        )
        if any(role.actor_id not in actor_ids for role in self.actor_role_assignments):
            raise InformationModelError("INFORMATION_EVENT_ROLE_ACTOR_UNKNOWN")
        _enum_tuple(self.scopes, InformationScope, "INFORMATION_EVENT_SCOPES_INVALID")
        if not isinstance(self.information_form, InformationForm):
            raise InformationModelError("INFORMATION_EVENT_FORM_INVALID")
        if not isinstance(self.institutional_status, InstitutionalStatus):
            raise InformationModelError("INFORMATION_EVENT_STATUS_INVALID")
        if not isinstance(self.channel, InformationChannel):
            raise InformationModelError("INFORMATION_EVENT_CHANNEL_INVALID")
        if not isinstance(self.audiences, tuple) or not self.audiences:
            raise InformationModelError("INFORMATION_EVENT_AUDIENCES_INVALID")
        audience_ids = _unique_ids(
            self.audiences, "segment_id", "INFORMATION_EVENT_AUDIENCE_IDS_INVALID"
        )
        _text(
            self.observable_message_or_action,
            "INFORMATION_EVENT_OBSERVABLE_CONTENT_INVALID",
        )
        for value, expected_type, code in (
            (self.novelty, InformationNovelty, "INFORMATION_EVENT_NOVELTY_INVALID"),
            (self.commitment, CommitmentLevel, "INFORMATION_EVENT_COMMITMENT_INVALID"),
            (self.reversibility, Reversibility, "INFORMATION_EVENT_REVERSIBILITY_INVALID"),
            (self.propagation_class, PropagationClass, "INFORMATION_EVENT_PROPAGATION_INVALID"),
        ):
            if not isinstance(value, expected_type):
                raise InformationModelError(code)

        published = _aware(self.published_at, "INFORMATION_EVENT_TIME_INVALID")
        observed = _aware(self.observed_at, "INFORMATION_EVENT_TIME_INVALID")
        available = _aware(self.available_at, "INFORMATION_EVENT_TIME_INVALID")
        _aware(self.effective_at, "INFORMATION_EVENT_EFFECTIVE_TIME_INVALID")
        if not published <= observed <= available:
            raise InformationModelError("INFORMATION_EVENT_TIME_ORDER_INVALID")
        if self.revised_at is not None:
            revised = _aware(self.revised_at, "INFORMATION_EVENT_REVISED_TIME_INVALID")
            if not published <= revised <= observed:
                raise InformationModelError("INFORMATION_EVENT_REVISED_TIME_ORDER_INVALID")

        for role in self.actor_role_assignments:
            if not role.is_active_at(published):
                raise InformationModelError("INFORMATION_EVENT_ROLE_NOT_ACTIVE")

        if not isinstance(self.source_artifacts, tuple) or not self.source_artifacts:
            raise InformationModelError("INFORMATION_EVENT_SOURCES_INVALID")
        artifact_ids = _unique_ids(
            self.source_artifacts,
            "artifact_id",
            "INFORMATION_EVENT_SOURCE_IDS_INVALID",
        )
        if any(source.publisher_actor_id not in actor_ids for source in self.source_artifacts):
            raise InformationModelError("INFORMATION_EVENT_SOURCE_ACTOR_UNKNOWN")
        if any(source.available_at.astimezone(UTC) > available for source in self.source_artifacts):
            raise InformationModelError("INFORMATION_EVENT_PREMATURE_AVAILABILITY")
        for role in self.actor_role_assignments:
            _check_refs(role.evidence_refs, artifact_ids, "INFORMATION_EVENT_ROLE_EVIDENCE_UNKNOWN")

        if not isinstance(self.observed_facts, tuple) or not self.observed_facts:
            raise InformationModelError("INFORMATION_EVENT_FACTS_INVALID")
        fact_ids = _unique_ids(
            self.observed_facts, "fact_id", "INFORMATION_EVENT_FACT_IDS_INVALID"
        )
        for fact in self.observed_facts:
            _check_refs(
                fact.source_artifact_ids,
                artifact_ids,
                "INFORMATION_EVENT_FACT_SOURCE_UNKNOWN",
            )
            if fact.observed_at.astimezone(UTC) > available:
                raise InformationModelError("INFORMATION_EVENT_FACT_FROM_FUTURE")

        if not isinstance(self.intent_hypotheses, tuple):
            raise InformationModelError("INFORMATION_EVENT_INTENT_HYPOTHESES_INVALID")
        intent_ids = _unique_ids(
            self.intent_hypotheses,
            "inference_id",
            "INFORMATION_EVENT_INTENT_IDS_INVALID",
        )
        inferential_evidence = artifact_ids | fact_ids
        for hypothesis in self.intent_hypotheses:
            if hypothesis.subject_actor_id not in actor_ids:
                raise InformationModelError("INFORMATION_EVENT_INTENT_ACTOR_UNKNOWN")
            _check_refs(
                hypothesis.evidence_refs,
                inferential_evidence,
                "INFORMATION_EVENT_INTENT_EVIDENCE_UNKNOWN",
            )

        if not isinstance(self.behavior_response_hypotheses, tuple):
            raise InformationModelError("INFORMATION_EVENT_BEHAVIOR_HYPOTHESES_INVALID")
        _unique_ids(
            self.behavior_response_hypotheses,
            "hypothesis_id",
            "INFORMATION_EVENT_BEHAVIOR_IDS_INVALID",
        )
        behavior_evidence = inferential_evidence | intent_ids
        for hypothesis in self.behavior_response_hypotheses:
            _check_refs(
                hypothesis.audience_segment_ids,
                audience_ids,
                "INFORMATION_EVENT_BEHAVIOR_AUDIENCE_UNKNOWN",
            )
            _check_refs(
                hypothesis.trigger_fact_ids,
                fact_ids,
                "INFORMATION_EVENT_BEHAVIOR_TRIGGER_UNKNOWN",
            )
            _check_refs(
                hypothesis.evidence_refs,
                behavior_evidence,
                "INFORMATION_EVENT_BEHAVIOR_EVIDENCE_UNKNOWN",
            )
        _string_tuple(self.limitations, "INFORMATION_EVENT_LIMITATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class AdmittedInformationEvent:
    event: InformationEvent
    decision_at: datetime
    information_event_digest: str

    def __post_init__(self) -> None:
        _aware(self.decision_at, "INFORMATION_EVENT_DECISION_TIME_INVALID")
        if not _HEX_64.fullmatch(self.information_event_digest):
            raise InformationModelError("INFORMATION_EVENT_DIGEST_INVALID")


def observed_fact_from_mapping(raw: Mapping[str, Any]) -> ObservedInformationFact:
    """Strict ingress helper that rejects mind-reading fields and schema drift."""

    if not isinstance(raw, Mapping):
        raise InformationModelError("OBSERVED_FACT_PAYLOAD_INVALID")
    forbidden = set(raw) & _FORBIDDEN_OBSERVED_FACT_FIELDS
    if forbidden:
        raise InformationModelError("OBSERVED_FACT_MIND_READING_FIELD_FORBIDDEN")
    if set(raw) != _OBSERVED_FACT_MAPPING_FIELDS:
        raise InformationModelError("OBSERVED_FACT_SCHEMA_INVALID")
    try:
        kind = ObservedFactKind(raw["fact_kind"])
    except (TypeError, ValueError) as exc:
        raise InformationModelError("OBSERVED_FACT_KIND_INVALID") from exc
    observed_at = raw["observed_at"]
    if isinstance(observed_at, str):
        try:
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InformationModelError("OBSERVED_INFORMATION_FACT_TIME_INVALID") from exc
    source_ids = raw["source_artifact_ids"]
    limitations = raw["limitations"]
    if isinstance(source_ids, list):
        source_ids = tuple(source_ids)
    if isinstance(limitations, list):
        limitations = tuple(limitations)
    return ObservedInformationFact(
        fact_id=raw["fact_id"],
        fact_kind=kind,
        statement=raw["statement"],
        source_artifact_ids=source_ids,
        observed_at=observed_at,
        limitations=limitations,
    )


def _canonical_time_from_document(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise InformationModelError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InformationModelError(code) from exc
    if parsed.tzinfo is None or _timestamp(parsed) != value:
        raise InformationModelError(code)
    return parsed.astimezone(UTC)


def information_event_from_canonical_dict(
    document: Mapping[str, Any],
) -> InformationEvent:
    """Rehydrate one exact current V3.1 event document.

    This is a strict read boundary for durable public-source artifacts.  It
    intentionally rejects the historical ``NONE_E0`` spelling: those sealed
    qualification records remain auditable, but cannot be admitted into a new
    V3.1 cycle or silently re-signed under a different authority label.
    """

    if (
        not isinstance(document, Mapping)
        or document.get("schema_version")
        != "theory-agent-v3.1-information-event.v1"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("inferred_intent_is_observed_fact") is not False
    ):
        if isinstance(document, Mapping) and document.get(
            "external_execution_authority"
        ) == "NONE_E0":
            raise InformationModelError(
                "INFORMATION_EVENT_LEGACY_AUTHORITY_LABEL_NOT_CYCLE_ADMISSIBLE"
            )
        raise InformationModelError("INFORMATION_EVENT_CANONICAL_DOCUMENT_INVALID")
    try:
        actors = tuple(
            InformationActor(
                actor_id=row["actor_id"],
                display_name=row["display_name"],
                actor_kind=ActorKind(row["actor_kind"]),
                jurisdictions=tuple(row["jurisdictions"]),
                provenance_refs=tuple(row["provenance_refs"]),
                limitations=tuple(row["limitations"]),
            )
            for row in document["actors"]
        )
        roles = tuple(
            ActorRoleAssignment(
                assignment_id=row["assignment_id"],
                actor_id=row["actor_id"],
                role=ActorRole(row["role"]),
                basis=RoleAssignmentBasis(row["basis"]),
                authority_scope=tuple(row["authority_scope"]),
                valid_from=_canonical_time_from_document(
                    row["valid_from"], "ACTOR_ROLE_TIME_INVALID"
                ),
                valid_to=(
                    None
                    if row["valid_to"] is None
                    else _canonical_time_from_document(
                        row["valid_to"], "ACTOR_ROLE_TIME_INVALID"
                    )
                ),
                evidence_refs=tuple(row["evidence_refs"]),
                limitations=tuple(row["limitations"]),
            )
            for row in document["actor_role_assignments"]
        )
        audiences = tuple(
            AudienceSegment(
                segment_id=row["segment_id"],
                label=row["label"],
                audience_kinds=tuple(
                    AudienceKind(value) for value in row["audience_kinds"]
                ),
                market_scopes=tuple(row["market_scopes"]),
                constraints=tuple(row["constraints"]),
                provenance_refs=tuple(row["provenance_refs"]),
                limitations=tuple(row["limitations"]),
            )
            for row in document["audiences"]
        )
        sources: list[SourceArtifactRef] = []
        for row in document["source_artifacts"]:
            receipt_row = row["acquisition_receipt"]
            receipt = (
                None
                if receipt_row is None
                else SourceAcquisitionReceipt(
                    receipt_id=receipt_row["receipt_id"],
                    evidence_boundary=SourceEvidenceBoundary(
                        receipt_row["evidence_boundary"]
                    ),
                    acquisition_method=SourceAcquisitionMethod(
                        receipt_row["acquisition_method"]
                    ),
                    source_locator=receipt_row["source_locator"],
                    acquired_at=_canonical_time_from_document(
                        receipt_row["acquired_at"],
                        "SOURCE_ACQUISITION_TIME_INVALID",
                    ),
                    content_sha256=receipt_row["content_sha256"],
                    request_ids=tuple(receipt_row["request_ids"]),
                    request_identity_digests=tuple(
                        receipt_row["request_identity_digests"]
                    ),
                    response_headers_digests=tuple(
                        receipt_row["response_headers_digests"]
                    ),
                    raw_body_sha256s=tuple(receipt_row["raw_body_sha256s"]),
                    capture_record_digests=tuple(
                        receipt_row["capture_record_digests"]
                    ),
                    external_verifier_refs=tuple(
                        receipt_row["external_verifier_refs"]
                    ),
                    external_verification_digests=tuple(
                        receipt_row["external_verification_digests"]
                    ),
                    limitations=tuple(receipt_row["limitations"]),
                )
            )
            sources.append(
                SourceArtifactRef(
                    artifact_id=row["artifact_id"],
                    publisher_actor_id=row["publisher_actor_id"],
                    locator=row["locator"],
                    source_type=SourceType(row["source_type"]),
                    channel=InformationChannel(row["channel"]),
                    propagation_class=PropagationClass(
                        row["propagation_class"]
                    ),
                    quality=SourceQuality(row["quality"]),
                    evidence_boundary=SourceEvidenceBoundary(
                        row["evidence_boundary"]
                    ),
                    coverage=SourceCoverage(row["coverage"]),
                    content_sha256=row["content_sha256"],
                    language=row["language"],
                    published_at=_canonical_time_from_document(
                        row["published_at"], "SOURCE_ARTIFACT_TIME_INVALID"
                    ),
                    observed_at=_canonical_time_from_document(
                        row["observed_at"], "SOURCE_ARTIFACT_TIME_INVALID"
                    ),
                    available_at=_canonical_time_from_document(
                        row["available_at"], "SOURCE_ARTIFACT_TIME_INVALID"
                    ),
                    provenance_refs=tuple(row["provenance_refs"]),
                    acquisition_receipt=receipt,
                    limitations=tuple(row["limitations"]),
                )
            )
        facts = tuple(
            observed_fact_from_mapping(
                {
                    "fact_id": row["fact_id"],
                    "fact_kind": row["fact_kind"],
                    "statement": row["statement"],
                    "source_artifact_ids": tuple(row["source_artifact_ids"]),
                    "observed_at": row["observed_at"],
                    "limitations": tuple(row["limitations"]),
                }
            )
            for row in document["observed_facts"]
        )
        intents = tuple(
            IntentInference(
                inference_id=row["inference_id"],
                subject_actor_id=row["subject_actor_id"],
                proposition=row["proposition"],
                evidence_refs=tuple(row["evidence_refs"]),
                competing_explanations=tuple(row["competing_explanations"]),
                falsifiers=tuple(row["falsifiers"]),
                limitations=tuple(row["limitations"]),
            )
            for row in document["intent_hypotheses"]
        )
        behaviors = tuple(
            BehaviorResponseHypothesis(
                hypothesis_id=row["hypothesis_id"],
                audience_segment_ids=tuple(row["audience_segment_ids"]),
                trigger_fact_ids=tuple(row["trigger_fact_ids"]),
                if_conditions=tuple(row["if_conditions"]),
                then_expected_behaviors=tuple(row["then_expected_behaviors"]),
                observable_intermediates=tuple(row["observable_intermediates"]),
                mechanism=row["mechanism"],
                horizon=row["horizon"],
                evidence_refs=tuple(row["evidence_refs"]),
                competing_explanations=tuple(row["competing_explanations"]),
                falsifiers=tuple(row["falsifiers"]),
                limitations=tuple(row["limitations"]),
            )
            for row in document["behavior_response_hypotheses"]
        )
        event = InformationEvent(
            event_id=document["event_id"],
            revision=document["revision"],
            previous_revision_digest=document["previous_revision_digest"],
            primary_actor_id=document["primary_actor_id"],
            actors=actors,
            actor_role_assignments=roles,
            scopes=tuple(InformationScope(value) for value in document["scopes"]),
            information_form=InformationForm(document["information_form"]),
            institutional_status=InstitutionalStatus(
                document["institutional_status"]
            ),
            channel=InformationChannel(document["channel"]),
            audiences=audiences,
            observable_message_or_action=document["observable_message_or_action"],
            novelty=InformationNovelty(document["novelty"]),
            commitment=CommitmentLevel(document["commitment"]),
            reversibility=Reversibility(document["reversibility"]),
            propagation_class=PropagationClass(document["propagation_class"]),
            published_at=_canonical_time_from_document(
                document["published_at"], "INFORMATION_EVENT_TIME_INVALID"
            ),
            observed_at=_canonical_time_from_document(
                document["observed_at"], "INFORMATION_EVENT_TIME_INVALID"
            ),
            available_at=_canonical_time_from_document(
                document["available_at"], "INFORMATION_EVENT_TIME_INVALID"
            ),
            effective_at=_canonical_time_from_document(
                document["effective_at"], "INFORMATION_EVENT_TIME_INVALID"
            ),
            revised_at=(
                None
                if document["revised_at"] is None
                else _canonical_time_from_document(
                    document["revised_at"], "INFORMATION_EVENT_REVISED_TIME_INVALID"
                )
            ),
            source_artifacts=tuple(sources),
            observed_facts=facts,
            intent_hypotheses=intents,
            behavior_response_hypotheses=behaviors,
            limitations=tuple(document["limitations"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InformationModelError):
            raise
        raise InformationModelError(
            "INFORMATION_EVENT_CANONICAL_DOCUMENT_INVALID"
        ) from exc
    if information_event_to_canonical_dict(event) != dict(document):
        raise InformationModelError("INFORMATION_EVENT_CANONICAL_DOCUMENT_DRIFT")
    return event


def _actor_document(actor: InformationActor) -> dict[str, Any]:
    return {
        "actor_id": actor.actor_id,
        "display_name": actor.display_name,
        "actor_kind": actor.actor_kind.value,
        "jurisdictions": list(actor.jurisdictions),
        "provenance_refs": list(actor.provenance_refs),
        "limitations": list(actor.limitations),
    }


def _role_document(role: ActorRoleAssignment) -> dict[str, Any]:
    return {
        "assignment_id": role.assignment_id,
        "actor_id": role.actor_id,
        "role": role.role.value,
        "basis": role.basis.value,
        "authority_scope": list(role.authority_scope),
        "valid_from": _timestamp(role.valid_from),
        "valid_to": _timestamp(role.valid_to) if role.valid_to is not None else None,
        "evidence_refs": list(role.evidence_refs),
        "limitations": list(role.limitations),
    }


def _audience_document(audience: AudienceSegment) -> dict[str, Any]:
    return {
        "segment_id": audience.segment_id,
        "label": audience.label,
        "audience_kinds": [kind.value for kind in audience.audience_kinds],
        "market_scopes": list(audience.market_scopes),
        "constraints": list(audience.constraints),
        "provenance_refs": list(audience.provenance_refs),
        "limitations": list(audience.limitations),
    }


def source_acquisition_receipt_to_canonical_dict(
    receipt: SourceAcquisitionReceipt,
) -> dict[str, Any]:
    if not isinstance(receipt, SourceAcquisitionReceipt):
        raise InformationModelError("SOURCE_ACQUISITION_RECEIPT_OBJECT_INVALID")
    return {
        "receipt_id": receipt.receipt_id,
        "evidence_boundary": receipt.evidence_boundary.value,
        "acquisition_method": receipt.acquisition_method.value,
        "source_locator": receipt.source_locator,
        "acquired_at": _timestamp(receipt.acquired_at),
        "content_sha256": receipt.content_sha256,
        "request_ids": list(receipt.request_ids),
        "request_identity_digests": list(receipt.request_identity_digests),
        "response_headers_digests": list(receipt.response_headers_digests),
        "raw_body_sha256s": list(receipt.raw_body_sha256s),
        "capture_record_digests": list(receipt.capture_record_digests),
        "external_verifier_refs": list(receipt.external_verifier_refs),
        "external_verification_digests": list(
            receipt.external_verification_digests
        ),
        "limitations": list(receipt.limitations),
        "truth_of_content_verified": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def source_acquisition_receipt_digest(receipt: SourceAcquisitionReceipt) -> str:
    return canonical_digest(source_acquisition_receipt_to_canonical_dict(receipt))


def source_artifact_to_canonical_dict(source: SourceArtifactRef) -> dict[str, Any]:
    if not isinstance(source, SourceArtifactRef):
        raise InformationModelError("SOURCE_ARTIFACT_OBJECT_INVALID")
    return {
        "artifact_id": source.artifact_id,
        "publisher_actor_id": source.publisher_actor_id,
        "locator": source.locator,
        "source_type": source.source_type.value,
        "channel": source.channel.value,
        "propagation_class": source.propagation_class.value,
        "quality": source.quality.value,
        "evidence_boundary": source.evidence_boundary.value,
        "coverage": source.coverage.value,
        "content_sha256": source.content_sha256,
        "language": source.language,
        "published_at": _timestamp(source.published_at),
        "observed_at": _timestamp(source.observed_at),
        "available_at": _timestamp(source.available_at),
        "provenance_refs": list(source.provenance_refs),
        "acquisition_receipt": (
            None
            if source.acquisition_receipt is None
            else source_acquisition_receipt_to_canonical_dict(
                source.acquisition_receipt
            )
        ),
        "acquisition_receipt_digest": (
            None
            if source.acquisition_receipt is None
            else source_acquisition_receipt_digest(source.acquisition_receipt)
        ),
        "limitations": list(source.limitations),
    }


def source_artifact_digest(source: SourceArtifactRef) -> str:
    return canonical_digest(source_artifact_to_canonical_dict(source))


def _fact_document(fact: ObservedInformationFact) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "fact_kind": fact.fact_kind.value,
        "statement": fact.statement,
        "source_artifact_ids": list(fact.source_artifact_ids),
        "observed_at": _timestamp(fact.observed_at),
        "limitations": list(fact.limitations),
    }


def _intent_document(intent: IntentInference) -> dict[str, Any]:
    return {
        "inference_id": intent.inference_id,
        "epistemic_status": "INFERRED_NOT_OBSERVED",
        "subject_actor_id": intent.subject_actor_id,
        "proposition": intent.proposition,
        "evidence_refs": list(intent.evidence_refs),
        "competing_explanations": list(intent.competing_explanations),
        "falsifiers": list(intent.falsifiers),
        "limitations": list(intent.limitations),
    }


def _behavior_document(hypothesis: BehaviorResponseHypothesis) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "epistemic_status": "HYPOTHESIS_NOT_FACT",
        "audience_segment_ids": list(hypothesis.audience_segment_ids),
        "trigger_fact_ids": list(hypothesis.trigger_fact_ids),
        "if_conditions": list(hypothesis.if_conditions),
        "then_expected_behaviors": list(hypothesis.then_expected_behaviors),
        "observable_intermediates": list(hypothesis.observable_intermediates),
        "mechanism": hypothesis.mechanism,
        "horizon": hypothesis.horizon,
        "evidence_refs": list(hypothesis.evidence_refs),
        "competing_explanations": list(hypothesis.competing_explanations),
        "falsifiers": list(hypothesis.falsifiers),
        "limitations": list(hypothesis.limitations),
    }


def information_event_to_canonical_dict(event: InformationEvent) -> dict[str, Any]:
    """Return the complete deterministic event document without a self digest."""

    if not isinstance(event, InformationEvent):
        raise InformationModelError("INFORMATION_EVENT_OBJECT_INVALID")
    return {
        "schema_version": "theory-agent-v3.1-information-event.v1",
        "event_id": event.event_id,
        "revision": event.revision,
        "previous_revision_digest": event.previous_revision_digest,
        "primary_actor_id": event.primary_actor_id,
        "actors": [_actor_document(actor) for actor in event.actors],
        "actor_role_assignments": [
            _role_document(role) for role in event.actor_role_assignments
        ],
        "scopes": [scope.value for scope in event.scopes],
        "information_form": event.information_form.value,
        "institutional_status": event.institutional_status.value,
        "channel": event.channel.value,
        "audiences": [_audience_document(audience) for audience in event.audiences],
        "observable_message_or_action": event.observable_message_or_action,
        "novelty": event.novelty.value,
        "commitment": event.commitment.value,
        "reversibility": event.reversibility.value,
        "propagation_class": event.propagation_class.value,
        "published_at": _timestamp(event.published_at),
        "observed_at": _timestamp(event.observed_at),
        "available_at": _timestamp(event.available_at),
        "effective_at": _timestamp(event.effective_at),
        "revised_at": _timestamp(event.revised_at) if event.revised_at is not None else None,
        "source_artifacts": [
            source_artifact_to_canonical_dict(source) for source in event.source_artifacts
        ],
        "observed_facts": [_fact_document(fact) for fact in event.observed_facts],
        "intent_hypotheses": [
            _intent_document(hypothesis) for hypothesis in event.intent_hypotheses
        ],
        "behavior_response_hypotheses": [
            _behavior_document(hypothesis)
            for hypothesis in event.behavior_response_hypotheses
        ],
        "limitations": list(event.limitations),
        "inferred_intent_is_observed_fact": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def information_event_digest(event: InformationEvent) -> str:
    return canonical_digest(information_event_to_canonical_dict(event))


def admit_information_event(
    event: InformationEvent,
    *,
    decision_at: datetime,
    prior_revision: InformationEvent | None = None,
) -> AdmittedInformationEvent:
    """Admit one event at a supplied decision cutoff and verify its revision chain."""

    if not isinstance(event, InformationEvent):
        raise InformationModelError("INFORMATION_EVENT_OBJECT_INVALID")
    cutoff = _aware(decision_at, "INFORMATION_EVENT_DECISION_TIME_INVALID")
    if event.available_at.astimezone(UTC) > cutoff:
        raise InformationModelError("INFORMATION_EVENT_PIT_FUTURE_AVAILABLE")
    if any(source.available_at.astimezone(UTC) > cutoff for source in event.source_artifacts):
        raise InformationModelError("INFORMATION_EVENT_PIT_SOURCE_FROM_FUTURE")
    if any(fact.observed_at.astimezone(UTC) > cutoff for fact in event.observed_facts):
        raise InformationModelError("INFORMATION_EVENT_PIT_FACT_FROM_FUTURE")

    if event.revision == 1:
        if prior_revision is not None:
            raise InformationModelError("INFORMATION_EVENT_GENESIS_FORBIDS_PRIOR")
    else:
        if prior_revision is None:
            raise InformationModelError("INFORMATION_EVENT_PRIOR_REVISION_REQUIRED")
        if (
            prior_revision.event_id != event.event_id
            or event.revision != prior_revision.revision + 1
        ):
            raise InformationModelError("INFORMATION_EVENT_REVISION_SEQUENCE_INVALID")
        if event.previous_revision_digest != information_event_digest(prior_revision):
            raise InformationModelError("INFORMATION_EVENT_REVISION_DIGEST_MISMATCH")
        revised = event.revised_at
        if revised is None or revised.astimezone(UTC) < prior_revision.available_at.astimezone(UTC):
            raise InformationModelError("INFORMATION_EVENT_REVISION_TIME_INVALID")
        if event.available_at.astimezone(UTC) <= prior_revision.available_at.astimezone(UTC):
            raise InformationModelError("INFORMATION_EVENT_REVISION_AVAILABILITY_INVALID")

    digest = information_event_digest(event)
    return AdmittedInformationEvent(
        event=event,
        decision_at=cutoff,
        information_event_digest=digest,
    )


_INFORMATION_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "previous_registry_digest",
        "known_event_ids",
        "latest_revisions",
        "current_cycle_event_digests",
        "history_retention",
        "external_execution_authority",
        "executable",
        "information_revision_registry_digest",
    }
)


def _registry_time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise InformationModelError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InformationModelError(code) from exc
    if parsed.tzinfo is None:
        raise InformationModelError(code)
    return parsed.astimezone(UTC)


def _verify_information_registry(
    registry: Mapping[str, Any], *, expected_run_id: str | None = None
) -> str:
    if (
        not isinstance(registry, Mapping)
        or set(registry) != _INFORMATION_REGISTRY_FIELDS
        or registry.get("schema_id")
        != "theory_paper_v2_v31_information_revision_registry"
        or registry.get("schema_version") != "1.0.0"
        or registry.get("history_retention") != "ALL_KNOWN_IDS_LATEST_REVISION_ONLY"
        or registry.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or registry.get("executable") is not False
        or not isinstance(registry.get("run_id"), str)
        or not registry["run_id"]
        or (
            expected_run_id is not None
            and registry.get("run_id") != expected_run_id
        )
        or isinstance(registry.get("cycle_index"), bool)
        or not isinstance(registry.get("cycle_index"), int)
        or registry["cycle_index"] < 1
    ):
        raise InformationModelError("INFORMATION_REGISTRY_SCHEMA_INVALID")
    _registry_time(registry.get("decision_at"), "INFORMATION_REGISTRY_TIME_INVALID")
    supplied = registry.get("information_revision_registry_digest")
    payload = dict(registry)
    payload.pop("information_revision_registry_digest", None)
    if (
        not isinstance(supplied, str)
        or _HEX_64.fullmatch(supplied) is None
        or canonical_digest(payload) != supplied
    ):
        raise InformationModelError("INFORMATION_REGISTRY_DIGEST_INVALID")
    known = registry.get("known_event_ids")
    latest = registry.get("latest_revisions")
    current = registry.get("current_cycle_event_digests")
    if (
        not isinstance(known, list)
        or known != sorted(known)
        or len(known) != len(set(known))
        or any(not isinstance(value, str) or not value for value in known)
        or not isinstance(latest, list)
        or not isinstance(current, list)
        or len(current) != len(set(current))
        or any(not isinstance(value, str) or _HEX_64.fullmatch(value) is None for value in current)
    ):
        raise InformationModelError("INFORMATION_REGISTRY_CONTENT_INVALID")
    latest_ids: list[str] = []
    for row in latest:
        if not isinstance(row, Mapping) or set(row) != {
            "event_id",
            "revision",
            "event_digest",
            "available_at",
        }:
            raise InformationModelError("INFORMATION_REGISTRY_LATEST_INVALID")
        event_id = row.get("event_id")
        revision = row.get("revision")
        if (
            not isinstance(event_id, str)
            or not event_id
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or not isinstance(row.get("event_digest"), str)
            or _HEX_64.fullmatch(row["event_digest"]) is None
        ):
            raise InformationModelError("INFORMATION_REGISTRY_LATEST_INVALID")
        _registry_time(row.get("available_at"), "INFORMATION_REGISTRY_TIME_INVALID")
        latest_ids.append(event_id)
    if latest_ids != sorted(latest_ids) or latest_ids != known:
        raise InformationModelError("INFORMATION_REGISTRY_KNOWN_IDS_NOT_RETAINED")
    previous_digest = registry.get("previous_registry_digest")
    if registry["cycle_index"] == 1:
        if previous_digest is not None:
            raise InformationModelError("INFORMATION_REGISTRY_GENESIS_INVALID")
    elif not isinstance(previous_digest, str) or _HEX_64.fullmatch(previous_digest) is None:
        raise InformationModelError("INFORMATION_REGISTRY_PREDECESSOR_INVALID")
    return supplied


def build_information_event_revision_registry(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: datetime,
    admissions: tuple[AdmittedInformationEvent, ...],
    previous_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Accumulate every known event ID while advancing only exact revisions."""

    identity_run = _text(run_id, "INFORMATION_REGISTRY_RUN_ID_INVALID")
    cutoff = _aware(decision_at, "INFORMATION_REGISTRY_TIME_INVALID")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or not isinstance(admissions, tuple)
        or not admissions
    ):
        raise InformationModelError("INFORMATION_REGISTRY_INPUT_INVALID")
    latest: dict[str, dict[str, Any]] = {}
    previous_digest: str | None = None
    if previous_registry is None:
        if cycle_index != 1:
            raise InformationModelError("INFORMATION_REGISTRY_PREDECESSOR_REQUIRED")
    else:
        previous_digest = _verify_information_registry(
            previous_registry, expected_run_id=identity_run
        )
        if (
            cycle_index != previous_registry["cycle_index"] + 1
            or _registry_time(
                previous_registry["decision_at"],
                "INFORMATION_REGISTRY_TIME_INVALID",
            )
            >= cutoff
        ):
            raise InformationModelError("INFORMATION_REGISTRY_PREDECESSOR_INVALID")
        latest = {
            str(row["event_id"]): dict(row)
            for row in previous_registry["latest_revisions"]
        }
    grouped: dict[str, list[AdmittedInformationEvent]] = {}
    for admission in admissions:
        if not isinstance(admission, AdmittedInformationEvent):
            raise InformationModelError("INFORMATION_REGISTRY_ADMISSION_INVALID")
        event = admission.event
        digest = information_event_digest(event)
        if (
            admission.information_event_digest != digest
            or admission.decision_at.astimezone(UTC) != cutoff
            or event.available_at.astimezone(UTC) > cutoff
        ):
            raise InformationModelError("INFORMATION_REGISTRY_ADMISSION_INVALID")
        grouped.setdefault(event.event_id, []).append(admission)
    current_digests: list[str] = []
    for event_id, rows in sorted(grouped.items()):
        prior = latest.get(event_id)
        for admission in sorted(rows, key=lambda item: item.event.revision):
            event = admission.event
            digest = admission.information_event_digest
            if prior is None:
                if event.revision != 1 or event.previous_revision_digest is not None:
                    raise InformationModelError("INFORMATION_REGISTRY_GENESIS_INVALID")
            else:
                if (
                    event.revision != prior["revision"] + 1
                    or event.previous_revision_digest != prior["event_digest"]
                    or event.revised_at is None
                    or event.revised_at.astimezone(UTC)
                    < _registry_time(
                        prior["available_at"],
                        "INFORMATION_REGISTRY_TIME_INVALID",
                    )
                    or event.available_at.astimezone(UTC)
                    <= _registry_time(
                        prior["available_at"], "INFORMATION_REGISTRY_TIME_INVALID"
                    )
                ):
                    raise InformationModelError("INFORMATION_REGISTRY_REVISION_INVALID")
            prior = {
                "event_id": event_id,
                "revision": event.revision,
                "event_digest": digest,
                "available_at": _timestamp(event.available_at),
            }
            latest[event_id] = prior
            current_digests.append(digest)
    document = {
        "schema_id": "theory_paper_v2_v31_information_revision_registry",
        "schema_version": "1.0.0",
        "run_id": identity_run,
        "cycle_index": cycle_index,
        "decision_at": _timestamp(cutoff),
        "previous_registry_digest": previous_digest,
        "known_event_ids": sorted(latest),
        "latest_revisions": [latest[event_id] for event_id in sorted(latest)],
        "current_cycle_event_digests": sorted(current_digests),
        "history_retention": "ALL_KNOWN_IDS_LATEST_REVISION_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    document["information_revision_registry_digest"] = canonical_digest(document)
    _verify_information_registry(document, expected_run_id=identity_run)
    return document
