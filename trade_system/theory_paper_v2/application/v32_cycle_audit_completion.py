"""Post-acceptance V3.2 audit completion and next-cycle gate.

The human-readable Chinese narrative is derived after the typed analysis
acceptance has been sealed.  This module binds that derived bundle back to the
accepted receipt without making the narrative an authority source.  A later
analysis cycle may start only when the latest accepted cycle has one matching
completion receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    DIRECTORY_SCHEMA_ID,
    POLICY_DIGEST_FIELD,
    SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID,
    verify_v32_cycle_audit_narrative_bundle_v1,
    verify_v32_cycle_audit_policy_v1,
)
from ..domain.v32_tick_supervisor import (
    V32TickSupervisorError,
    verify_v32_tick_supervisor_checkpoint,
)
from .v32_cycle_acceptance import (
    DIGEST_FIELD as ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ACCEPTANCE_SCHEMA_ID,
)


class V32CycleAuditCompletionError(ValueError):
    """The post-acceptance narrative or next-cycle audit gate is invalid."""


SCHEMA_ID = "theory_paper_v32_cycle_audit_completion_receipt_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "cycle_audit_completion_receipt_digest"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "completion_id",
        "run_id",
        "cycle_index",
        "completed_at",
        "cycle_audit_policy_digest",
        "analysis_acceptance_binding",
        "analysis_acceptance_digest",
        "narrative_directory_binding",
        "narrative_directory_digest",
        "narrative_shard_bindings",
        "narrative_shard_digests",
        "narrative_shard_count",
        "audit_bundle_fully_replayed",
        "post_acceptance_only",
        "next_cycle_permit_gate_satisfied",
        "narrative_is_authority",
        "typed_acceptance_remains_authoritative",
        "private_chain_of_thought_recorded",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CycleAuditCompletionError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32CycleAuditCompletionError(code)
    return value


def _time(value: Any, code: str) -> str:
    candidate = _text(value, code)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CycleAuditCompletionError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
        != candidate
    ):
        raise V32CycleAuditCompletionError(code)
    return candidate


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _binding(
    value: Any,
    *,
    document: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32CycleAuditCompletionError(code)
    relative_ref = _text(value.get("relative_ref"), code)
    path = PurePosixPath(relative_ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise V32CycleAuditCompletionError(code)
    result = {
        "relative_ref": relative_ref,
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if (
        result["schema_id"] != schema_id
        or result["digest_field"] != digest_field
        or result["semantic_digest"] != semantic_digest
        or result["physical_sha256"] != _physical(document)
    ):
        raise V32CycleAuditCompletionError(code)
    return result


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "order_submission": False,
    }


def _verify_intrinsic(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        _text(document.get("completion_id"), "V32_AUDIT_COMPLETION_INVALID")
        _text(document.get("run_id"), "V32_AUDIT_COMPLETION_INVALID")
        cycle = document.get("cycle_index")
        if isinstance(cycle, bool) or not isinstance(cycle, int) or not 1 <= cycle <= 16:
            raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
        _time(document.get("completed_at"), "V32_AUDIT_COMPLETION_INVALID")
        _digest(
            document.get("cycle_audit_policy_digest"),
            "V32_AUDIT_COMPLETION_INVALID",
        )
        _digest(
            document.get("analysis_acceptance_digest"),
            "V32_AUDIT_COMPLETION_INVALID",
        )
        _digest(
            document.get("narrative_directory_digest"),
            "V32_AUDIT_COMPLETION_INVALID",
        )
        for value in (
            document.get("analysis_acceptance_binding"),
            document.get("narrative_directory_binding"),
        ):
            if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
                raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
            for field in _BINDING_FIELDS:
                _text(value.get(field), "V32_AUDIT_COMPLETION_INVALID")
            _digest(value["semantic_digest"], "V32_AUDIT_COMPLETION_INVALID")
            _digest(value["physical_sha256"], "V32_AUDIT_COMPLETION_INVALID")
        bindings = document.get("narrative_shard_bindings")
        digests = document.get("narrative_shard_digests")
        count = document.get("narrative_shard_count")
        if (
            not isinstance(bindings, list)
            or not isinstance(digests, list)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or len(bindings) != count
            or len(digests) != count
        ):
            raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
        for row, digest_value in zip(bindings, digests, strict=True):
            if not isinstance(row, Mapping) or set(row) != _BINDING_FIELDS:
                raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
            _digest(digest_value, "V32_AUDIT_COMPLETION_INVALID")
            if row.get("semantic_digest") != digest_value:
                raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
        if len(set(digests)) != len(digests):
            raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleAuditCompletionError):
            raise
        raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID") from exc
    if (
        document.get("schema_id") != SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("audit_bundle_fully_replayed") is not True
        or document.get("post_acceptance_only") is not True
        or document.get("next_cycle_permit_gate_satisfied") is not True
        or document.get("narrative_is_authority") is not False
        or document.get("typed_acceptance_remains_authoritative") is not True
        or document.get("private_chain_of_thought_recorded") is not False
        or any(document.get(key) != value for key, value in _boundary().items())
    ):
        raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_INVALID")
    return supplied


def build_v32_cycle_audit_completion_receipt_v1(
    *,
    completion_id: str,
    cycle_audit_policy: Mapping[str, Any],
    analysis_acceptance: Mapping[str, Any],
    analysis_acceptance_binding: Mapping[str, Any],
    narrative_directory: Mapping[str, Any],
    narrative_directory_binding: Mapping[str, Any],
    narrative_shards: Sequence[Mapping[str, Any]],
    narrative_shard_bindings: Sequence[Mapping[str, Any]],
    completed_at: str,
) -> dict[str, Any]:
    """Replay one complete narrative bundle and bind it to one acceptance."""

    try:
        policy_digest = verify_v32_cycle_audit_policy_v1(cycle_audit_policy)
        acceptance_digest = verify_self_digest(
            analysis_acceptance, ACCEPTANCE_DIGEST_FIELD
        )
        directory_digest = verify_v32_cycle_audit_narrative_bundle_v1(
            narrative_directory, narrative_shards
        )
    except (TypeError, ValueError) as exc:
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_COMPLETION_REPLAY_INVALID"
        ) from exc
    if (
        analysis_acceptance.get("schema_id") != ACCEPTANCE_SCHEMA_ID
        or analysis_acceptance.get("acceptance_status")
        != "ACCEPTED_SINGLE_ANALYSIS_CYCLE_WRITE_ONCE_REQUIRED"
    ):
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_COMPLETION_ACCEPTANCE_INVALID"
        )
    run_id = _text(
        analysis_acceptance.get("run_id"), "V32_AUDIT_COMPLETION_SCOPE_INVALID"
    )
    cycle_index = analysis_acceptance.get("cycle_index")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
        or narrative_directory.get("run_id") != run_id
        or narrative_directory.get("cycle_index") != cycle_index
        or narrative_directory.get("boundary_type") != "ACCEPTANCE"
        or cycle_audit_policy.get("run_scope_id") != run_id
        or narrative_directory.get("max_text_part_utf8_bytes")
        != cycle_audit_policy.get("max_text_part_utf8_bytes")
        or narrative_directory.get("max_shard_canonical_bytes")
        != cycle_audit_policy.get("max_shard_canonical_bytes")
    ):
        raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_SCOPE_INVALID")
    completed = _time(completed_at, "V32_AUDIT_COMPLETION_TIME_INVALID")
    if not (
        _moment(analysis_acceptance.get("accepted_at"), "V32_AUDIT_COMPLETION_TIME_INVALID")
        <= _moment(narrative_directory.get("generated_at"), "V32_AUDIT_COMPLETION_TIME_INVALID")
        <= _moment(completed, "V32_AUDIT_COMPLETION_TIME_INVALID")
    ):
        raise V32CycleAuditCompletionError("V32_AUDIT_COMPLETION_TIME_INVALID")
    acceptance_ref = _binding(
        analysis_acceptance_binding,
        document=analysis_acceptance,
        schema_id=ACCEPTANCE_SCHEMA_ID,
        digest_field=ACCEPTANCE_DIGEST_FIELD,
        semantic_digest=acceptance_digest,
        code="V32_AUDIT_COMPLETION_ACCEPTANCE_BINDING_INVALID",
    )
    directory_ref = _binding(
        narrative_directory_binding,
        document=narrative_directory,
        schema_id=DIRECTORY_SCHEMA_ID,
        digest_field=DIRECTORY_DIGEST_FIELD,
        semantic_digest=directory_digest,
        code="V32_AUDIT_COMPLETION_DIRECTORY_BINDING_INVALID",
    )
    if (
        isinstance(narrative_shards, (str, bytes))
        or not isinstance(narrative_shards, Sequence)
        or isinstance(narrative_shard_bindings, (str, bytes))
        or not isinstance(narrative_shard_bindings, Sequence)
        or len(narrative_shards) != len(narrative_shard_bindings)
        or not narrative_shards
    ):
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_COMPLETION_SHARD_SET_INVALID"
        )
    shard_refs = [
        _binding(
            supplied_binding,
            document=shard,
            schema_id=SHARD_SCHEMA_ID,
            digest_field=SHARD_DIGEST_FIELD,
            semantic_digest=shard[SHARD_DIGEST_FIELD],
            code="V32_AUDIT_COMPLETION_SHARD_BINDING_INVALID",
        )
        for shard, supplied_binding in zip(
            narrative_shards, narrative_shard_bindings, strict=True
        )
    ]
    source_bindings = [
        source
        for entry in narrative_directory["section_entries"]
        for source in entry["source_bindings"]
    ]
    if not any(
        source.get("schema_id") == ACCEPTANCE_SCHEMA_ID
        and source.get("digest_field") == ACCEPTANCE_DIGEST_FIELD
        and source.get("semantic_digest") == acceptance_digest
        and source.get("physical_sha256") == acceptance_ref["physical_sha256"]
        for source in source_bindings
    ):
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_COMPLETION_NARRATIVE_ACCEPTANCE_UNBOUND"
        )
    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "completion_id": _text(
            completion_id, "V32_AUDIT_COMPLETION_ID_INVALID"
        ),
        "run_id": run_id,
        "cycle_index": cycle_index,
        "completed_at": completed,
        "cycle_audit_policy_digest": policy_digest,
        "analysis_acceptance_binding": acceptance_ref,
        "analysis_acceptance_digest": acceptance_digest,
        "narrative_directory_binding": directory_ref,
        "narrative_directory_digest": directory_digest,
        "narrative_shard_bindings": shard_refs,
        "narrative_shard_digests": [
            shard[SHARD_DIGEST_FIELD] for shard in narrative_shards
        ],
        "narrative_shard_count": len(narrative_shards),
        "audit_bundle_fully_replayed": True,
        "post_acceptance_only": True,
        "next_cycle_permit_gate_satisfied": True,
        "narrative_is_authority": False,
        "typed_acceptance_remains_authoritative": True,
        "private_chain_of_thought_recorded": False,
        **_boundary(),
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_cycle_audit_completion_receipt_v1(
    document: Mapping[str, Any],
    *,
    cycle_audit_policy: Mapping[str, Any],
    analysis_acceptance: Mapping[str, Any],
    narrative_directory: Mapping[str, Any],
    narrative_shards: Sequence[Mapping[str, Any]],
) -> str:
    supplied = _verify_intrinsic(document)
    rebuilt = build_v32_cycle_audit_completion_receipt_v1(
        completion_id=document["completion_id"],
        cycle_audit_policy=cycle_audit_policy,
        analysis_acceptance=analysis_acceptance,
        analysis_acceptance_binding=document["analysis_acceptance_binding"],
        narrative_directory=narrative_directory,
        narrative_directory_binding=document["narrative_directory_binding"],
        narrative_shards=narrative_shards,
        narrative_shard_bindings=document["narrative_shard_bindings"],
        completed_at=document["completed_at"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_COMPLETION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def verify_v32_latest_cycle_audit_gate_v1(
    *,
    supervisor_checkpoint: Mapping[str, Any],
    latest_audit_completion: Mapping[str, Any] | None,
) -> str | None:
    """Require the latest accepted cycle's audit before another analysis permit."""

    try:
        verify_v32_tick_supervisor_checkpoint(supervisor_checkpoint)
    except V32TickSupervisorError as exc:
        raise V32CycleAuditCompletionError(
            "V32_AUDIT_GATE_SUPERVISOR_INVALID"
        ) from exc
    accepted = supervisor_checkpoint["accepted_analysis_cycles"]
    if accepted == 0:
        if latest_audit_completion is not None:
            raise V32CycleAuditCompletionError(
                "V32_AUDIT_GATE_GENESIS_COMPLETION_FORBIDDEN"
            )
        return None
    if latest_audit_completion is None:
        raise V32CycleAuditCompletionError("V32_AUDIT_GATE_COMPLETION_REQUIRED")
    digest = _verify_intrinsic(latest_audit_completion)
    if (
        latest_audit_completion.get("run_id") != supervisor_checkpoint["run_id"]
        or latest_audit_completion.get("cycle_index") != accepted
        or latest_audit_completion.get("analysis_acceptance_digest")
        != supervisor_checkpoint["accepted_state_digests"][-1]
    ):
        raise V32CycleAuditCompletionError("V32_AUDIT_GATE_CHAIN_INVALID")
    return digest


__all__ = [
    "DIGEST_FIELD",
    "SCHEMA_ID",
    "V32CycleAuditCompletionError",
    "build_v32_cycle_audit_completion_receipt_v1",
    "verify_v32_cycle_audit_completion_receipt_v1",
    "verify_v32_latest_cycle_audit_gate_v1",
]
