"""Pure validation for synthetic OFF or SHADOW slow-context snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

from .types import iso_utc, parse_utc


UTC = timezone.utc
ALLOWED_MODES = ("OFF", "SHADOW")
_SNAPSHOT_FIELDS = {
    "snapshot_id", "schema_version", "instrument_id", "context_horizon", "source_cutoff_at", "generated_at", "validated_at",
    "available_at", "expires_at", "facts", "inferences", "hypotheses", "unknowns", "conflicts", "provenance", "revision", "snapshot_sha256",
}
_EVIDENCE_FIELDS = {
    "evidence_id", "source_id", "source_owner", "source_url", "authority_grade", "published_at", "retrieved_at",
    "received_at", "source_available_at", "observed_value", "unit", "methodology", "limitations", "content_sha256",
    "source_kind", "source_revision_id",
}
_CLAIM_FIELDS = {"claim_id", "statement", "evidence_ids"}
_UNKNOWN_FIELDS = {"unknown_id", "statement"}
_CONFLICT_FIELDS = {"conflict_id", "statement", "evidence_ids"}
_REVISION_FIELDS = {"revision_id", "revision_ordinal", "supersedes_snapshot_sha256"}
_DOMAIN = b"msta-hed/slow-context-snapshot/v1\x00"


class SlowContextError(ValueError):
    """Raised when a slow-context snapshot violates the static P0 contract."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strict_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SlowContextError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> Any:
    raise SlowContextError("nonfinite JSON value: %s" % token)


def loads_snapshot_json(raw: str | bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_json_object, parse_constant=_reject_nonfinite)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SlowContextError("snapshot JSON is invalid") from exc
    if not isinstance(value, dict):
        raise SlowContextError("snapshot JSON must be an object")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SlowContextError("%s must be a non-empty string" % field)
    return value


def _sha256(value: Any, field: str) -> str:
    result = _string(value, field)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise SlowContextError("%s must be lower-case SHA-256" % field)
    return result


def _document_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise SlowContextError("%s must be canonical UTC ISO-8601 Z string" % field)
    try:
        parsed = parse_utc(value)
    except ValueError as exc:
        raise SlowContextError("%s must be canonical UTC ISO-8601 Z string" % field) from exc
    if not value.endswith("Z") or iso_utc(parsed) != value:
        raise SlowContextError("%s must be canonical UTC ISO-8601 Z string" % field)
    return parsed


def _decision_time(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SlowContextError("%s must include timezone" % field)
        return value.astimezone(UTC)
    return _document_time(value, field)


def _exact_mapping(value: Any, fields: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise SlowContextError("%s schema is invalid" % field)
    return value


def _string_list(value: Any, field: str) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise SlowContextError("%s must be a list" % field)
    parsed = tuple(_string(item, field) for item in value)
    if len(set(parsed)) != len(parsed):
        raise SlowContextError("%s must not repeat values" % field)
    return parsed


@dataclass(frozen=True)
class SourceEvidence:
    evidence_id: str
    source_id: str
    source_owner: str
    source_url: str
    authority_grade: str
    published_at: datetime
    retrieved_at: datetime
    received_at: datetime
    source_available_at: datetime
    observed_value: str
    unit: str
    methodology: str
    limitations: str
    content_sha256: str
    source_kind: str
    source_revision_id: str

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceEvidence":
        row = _exact_mapping(value, _EVIDENCE_FIELDS, "provenance item")
        return cls(
            evidence_id=_string(row["evidence_id"], "evidence_id"),
            source_id=_string(row["source_id"], "source_id"),
            source_owner=_string(row["source_owner"], "source_owner"),
            source_url=_string(row["source_url"], "source_url"),
            authority_grade=_string(row["authority_grade"], "authority_grade"),
            published_at=_document_time(row["published_at"], "published_at"),
            retrieved_at=_document_time(row["retrieved_at"], "retrieved_at"),
            received_at=_document_time(row["received_at"], "received_at"),
            source_available_at=_document_time(row["source_available_at"], "source_available_at"),
            observed_value=_string(row["observed_value"], "observed_value"),
            unit=_string(row["unit"], "unit"),
            methodology=_string(row["methodology"], "methodology"),
            limitations=_string(row["limitations"], "limitations"),
            content_sha256=_sha256(row["content_sha256"], "content_sha256"),
            source_kind=_string(row["source_kind"], "source_kind"),
            source_revision_id=_string(row["source_revision_id"], "source_revision_id"),
        )

    def __post_init__(self) -> None:
        if self.authority_grade not in {"A", "B", "C", "D", "E"}:
            raise SlowContextError("authority_grade must be A through E")
        if not (self.published_at <= self.retrieved_at <= self.received_at <= self.source_available_at):
            raise SlowContextError("source evidence PIT times are not causal")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id, "source_id": self.source_id, "source_owner": self.source_owner,
            "source_url": self.source_url, "authority_grade": self.authority_grade,
            "published_at": iso_utc(self.published_at), "retrieved_at": iso_utc(self.retrieved_at),
            "received_at": iso_utc(self.received_at), "source_available_at": iso_utc(self.source_available_at),
            "observed_value": self.observed_value, "unit": self.unit, "methodology": self.methodology,
            "limitations": self.limitations, "content_sha256": self.content_sha256,
            "source_kind": self.source_kind, "source_revision_id": self.source_revision_id,
        }


@dataclass(frozen=True)
class ContextClaim:
    claim_id: str
    statement: str
    evidence_ids: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Any, field: str, evidence_ids: set[str]) -> "ContextClaim":
        row = _exact_mapping(value, _CLAIM_FIELDS, field)
        references = _string_list(row["evidence_ids"], "%s.evidence_ids" % field)
        if not references or any(item not in evidence_ids for item in references):
            raise SlowContextError("%s references unknown evidence" % field)
        return cls(_string(row["claim_id"], "%s.claim_id" % field), _string(row["statement"], "%s.statement" % field), references)

    def to_dict(self) -> dict[str, Any]:
        return {"claim_id": self.claim_id, "statement": self.statement, "evidence_ids": list(self.evidence_ids)}


@dataclass(frozen=True)
class ContextUnknown:
    unknown_id: str
    statement: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ContextUnknown":
        row = _exact_mapping(value, _UNKNOWN_FIELDS, "unknown item")
        return cls(_string(row["unknown_id"], "unknown_id"), _string(row["statement"], "unknown.statement"))

    def to_dict(self) -> dict[str, Any]:
        return {"unknown_id": self.unknown_id, "statement": self.statement}


@dataclass(frozen=True)
class ContextConflict:
    conflict_id: str
    statement: str
    evidence_ids: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Any, evidence_ids: set[str]) -> "ContextConflict":
        row = _exact_mapping(value, _CONFLICT_FIELDS, "conflict item")
        references = _string_list(row["evidence_ids"], "conflict.evidence_ids")
        if not references or any(item not in evidence_ids for item in references):
            raise SlowContextError("conflict references unknown evidence")
        return cls(_string(row["conflict_id"], "conflict_id"), _string(row["statement"], "conflict.statement"), references)

    def to_dict(self) -> dict[str, Any]:
        return {"conflict_id": self.conflict_id, "statement": self.statement, "evidence_ids": list(self.evidence_ids)}


@dataclass(frozen=True)
class ContextRevision:
    revision_id: str
    revision_ordinal: int
    supersedes_snapshot_sha256: Optional[str]

    @classmethod
    def from_mapping(cls, value: Any) -> "ContextRevision":
        row = _exact_mapping(value, _REVISION_FIELDS, "revision")
        ordinal = row["revision_ordinal"]
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise SlowContextError("revision_ordinal must be positive integer")
        parent = row["supersedes_snapshot_sha256"]
        if parent is not None:
            parent = _sha256(parent, "supersedes_snapshot_sha256")
        if ordinal == 1 and parent is not None:
            raise SlowContextError("initial revision must not supersede")
        if ordinal > 1 and parent is None:
            raise SlowContextError("later revision must supersede")
        return cls(_string(row["revision_id"], "revision_id"), ordinal, parent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id, "revision_ordinal": self.revision_ordinal,
            "supersedes_snapshot_sha256": self.supersedes_snapshot_sha256,
        }


def snapshot_sha256(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise SlowContextError("snapshot must be an object")
    body = dict(document)
    body.pop("snapshot_sha256", None)
    return hashlib.sha256(_DOMAIN + _canonical(body)).hexdigest()


def seal_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(document)
    if "snapshot_sha256" in body:
        raise SlowContextError("unsealed snapshot must not provide snapshot_sha256")
    body["snapshot_sha256"] = snapshot_sha256(body)
    return SlowContextSnapshot.from_mapping(body).to_dict()


@dataclass(frozen=True)
class SlowContextSnapshot:
    snapshot_id: str
    schema_version: str
    instrument_id: str
    context_horizon: str
    source_cutoff_at: datetime
    generated_at: datetime
    validated_at: datetime
    available_at: datetime
    expires_at: datetime
    facts: Tuple[ContextClaim, ...]
    inferences: Tuple[ContextClaim, ...]
    hypotheses: Tuple[ContextClaim, ...]
    unknowns: Tuple[ContextUnknown, ...]
    conflicts: Tuple[ContextConflict, ...]
    provenance: Tuple[SourceEvidence, ...]
    revision: ContextRevision
    snapshot_sha256: str

    @classmethod
    def from_mapping(cls, value: Any) -> "SlowContextSnapshot":
        row = _exact_mapping(value, _SNAPSHOT_FIELDS, "snapshot")
        if row["schema_version"] != "slow-context.v1":
            raise SlowContextError("schema_version must equal slow-context.v1")
        provenance_raw = row["provenance"]
        if not isinstance(provenance_raw, list) or not provenance_raw:
            raise SlowContextError("provenance must be a non-empty list")
        provenance = tuple(SourceEvidence.from_mapping(item) for item in provenance_raw)
        evidence_ids = {item.evidence_id for item in provenance}
        if len(evidence_ids) != len(provenance):
            raise SlowContextError("provenance repeats evidence_id")
        parsed_claims = {}
        for field in ("facts", "inferences", "hypotheses"):
            raw_claims = row[field]
            if not isinstance(raw_claims, list):
                raise SlowContextError("%s must be a list" % field)
            parsed_claims[field] = tuple(ContextClaim.from_mapping(item, field, evidence_ids) for item in raw_claims)
        claim_ids = [claim.claim_id for field in ("facts", "inferences", "hypotheses") for claim in parsed_claims[field]]
        if len(set(claim_ids)) != len(claim_ids):
            raise SlowContextError("claims must not repeat claim_id across layers")
        unknown_raw = row["unknowns"]
        conflict_raw = row["conflicts"]
        if not isinstance(unknown_raw, list) or not isinstance(conflict_raw, list):
            raise SlowContextError("unknowns and conflicts must be lists")
        unknowns = tuple(ContextUnknown.from_mapping(item) for item in unknown_raw)
        conflicts = tuple(ContextConflict.from_mapping(item, evidence_ids) for item in conflict_raw)
        if len({item.unknown_id for item in unknowns}) != len(unknowns):
            raise SlowContextError("unknowns repeat unknown_id")
        if len({item.conflict_id for item in conflicts}) != len(conflicts):
            raise SlowContextError("conflicts repeat conflict_id")
        snapshot = cls(
            snapshot_id=_string(row["snapshot_id"], "snapshot_id"),
            schema_version=_string(row["schema_version"], "schema_version"),
            instrument_id=_string(row["instrument_id"], "instrument_id"),
            context_horizon=_string(row["context_horizon"], "context_horizon"),
            source_cutoff_at=_document_time(row["source_cutoff_at"], "source_cutoff_at"),
            generated_at=_document_time(row["generated_at"], "generated_at"),
            validated_at=_document_time(row["validated_at"], "validated_at"),
            available_at=_document_time(row["available_at"], "available_at"),
            expires_at=_document_time(row["expires_at"], "expires_at"),
            facts=parsed_claims["facts"], inferences=parsed_claims["inferences"], hypotheses=parsed_claims["hypotheses"],
            unknowns=unknowns, conflicts=conflicts, provenance=provenance,
            revision=ContextRevision.from_mapping(row["revision"]), snapshot_sha256=_sha256(row["snapshot_sha256"], "snapshot_sha256"),
        )
        max_evidence = max(item.source_available_at for item in snapshot.provenance)
        if not (max_evidence <= snapshot.source_cutoff_at <= snapshot.generated_at <= snapshot.validated_at <= snapshot.available_at < snapshot.expires_at):
            raise SlowContextError("snapshot PIT times are not causal")
        if snapshot.available_at != max(max_evidence, snapshot.validated_at):
            raise SlowContextError("available_at must equal evidence/validation maximum")
        if snapshot.expires_at <= snapshot.available_at:
            raise SlowContextError("expires_at must follow available_at")
        if snapshot.snapshot_sha256 != snapshot_sha256(row):
            raise SlowContextError("snapshot_sha256 does not match canonical content")
        return snapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id, "schema_version": self.schema_version, "instrument_id": self.instrument_id,
            "context_horizon": self.context_horizon, "source_cutoff_at": iso_utc(self.source_cutoff_at),
            "generated_at": iso_utc(self.generated_at), "validated_at": iso_utc(self.validated_at),
            "available_at": iso_utc(self.available_at), "expires_at": iso_utc(self.expires_at),
            "facts": [item.to_dict() for item in self.facts], "inferences": [item.to_dict() for item in self.inferences],
            "hypotheses": [item.to_dict() for item in self.hypotheses], "unknowns": [item.to_dict() for item in self.unknowns],
            "conflicts": [item.to_dict() for item in self.conflicts], "provenance": [item.to_dict() for item in self.provenance],
            "revision": self.revision.to_dict(), "snapshot_sha256": self.snapshot_sha256,
        }


def validate_revision_chain(snapshots: Sequence[SlowContextSnapshot]) -> Tuple[SlowContextSnapshot, ...]:
    parsed = tuple(SlowContextSnapshot.from_mapping(item.to_dict()) if isinstance(item, SlowContextSnapshot) else SlowContextSnapshot.from_mapping(item) for item in snapshots)
    by_digest = {item.snapshot_sha256: item for item in parsed}
    if len(by_digest) != len(parsed) or len({item.snapshot_id for item in parsed}) != len(parsed):
        raise SlowContextError("snapshot identities must be unique")
    by_revision = {}
    for snapshot in parsed:
        key = (snapshot.instrument_id, snapshot.revision.revision_id)
        by_revision.setdefault(key, []).append(snapshot)
    for items in by_revision.values():
        ordered = sorted(items, key=lambda item: item.revision.revision_ordinal)
        expected = 1
        parent = None
        for item in ordered:
            if item.revision.revision_ordinal != expected or item.revision.supersedes_snapshot_sha256 != parent:
                raise SlowContextError("revision chain is gapped or forked")
            if parent is not None:
                prior = by_digest.get(parent)
                if prior is None or item.available_at < prior.available_at:
                    raise SlowContextError("revision chain has missing parent or retroactive availability")
            parent = item.snapshot_sha256
            expected += 1
    return parsed


@dataclass(frozen=True)
class SlowContextView:
    mode: str
    eligible: bool
    reason_code: str
    snapshot_id: Optional[str]
    snapshot_sha256: Optional[str]
    hot_path_effect: str = "ZERO"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "eligible": self.eligible, "reason_code": self.reason_code,
            "snapshot_id": self.snapshot_id, "snapshot_sha256": self.snapshot_sha256,
            "hot_path_effect": self.hot_path_effect,
        }


def select_context(mode: str, decision_at: datetime, snapshot: Optional[SlowContextSnapshot]) -> SlowContextView:
    """Expose provenance eligibility only; P0 context has zero hot-path effect."""

    if mode not in ALLOWED_MODES:
        raise SlowContextError("only OFF and SHADOW modes are allowed")
    decision = _decision_time(decision_at, "decision_at")
    if mode == "OFF":
        return SlowContextView(mode="OFF", eligible=False, reason_code="CONTEXT_DISABLED", snapshot_id=None, snapshot_sha256=None)
    if snapshot is None:
        return SlowContextView(mode="SHADOW", eligible=False, reason_code="CONTEXT_MISSING", snapshot_id=None, snapshot_sha256=None)
    snapshot = SlowContextSnapshot.from_mapping(snapshot.to_dict()) if isinstance(snapshot, SlowContextSnapshot) else SlowContextSnapshot.from_mapping(snapshot)
    if not snapshot.facts:
        return SlowContextView("SHADOW", False, "CONTEXT_MISSING_FACTS", snapshot.snapshot_id, snapshot.snapshot_sha256)
    if snapshot.unknowns:
        return SlowContextView("SHADOW", False, "CONTEXT_UNKNOWN", snapshot.snapshot_id, snapshot.snapshot_sha256)
    if snapshot.conflicts:
        return SlowContextView("SHADOW", False, "CONTEXT_CONFLICTED", snapshot.snapshot_id, snapshot.snapshot_sha256)
    if decision < snapshot.available_at:
        return SlowContextView("SHADOW", False, "CONTEXT_FUTURE", snapshot.snapshot_id, snapshot.snapshot_sha256)
    if decision >= snapshot.expires_at:
        return SlowContextView("SHADOW", False, "CONTEXT_EXPIRED", snapshot.snapshot_id, snapshot.snapshot_sha256)
    return SlowContextView("SHADOW", True, "CONTEXT_ELIGIBLE_SHADOW_ONLY", snapshot.snapshot_id, snapshot.snapshot_sha256)


__all__ = [
    "ALLOWED_MODES", "ContextClaim", "ContextConflict", "ContextRevision", "ContextUnknown", "SlowContextError",
    "SlowContextSnapshot", "SlowContextView", "SourceEvidence", "loads_snapshot_json", "seal_snapshot", "select_context",
    "snapshot_sha256", "validate_revision_chain",
]
