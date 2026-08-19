"""V3.1.1 current-Codex durable-delivery qualification.

The V3.1 receipt proved that one canonical authoring packet travelled through
the proposal/compile/selection/acceptance chain.  It did not prove that the
V3.1.1 theory addendum and its complete qualification support set were part of
the direct Agent input.  This version therefore keeps the validated V3.1
receipt as a compatibility sub-proof and additionally binds the versioned
Agent input context, its one-attempt durable consumption, the successor commit
material, and the V3.1.1 commit envelope.

This is delivery and durability evidence only.  It is deliberately not a
claim about private cognition, served-model identity, prediction, calibration,
profitability, or execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping

from ..contracts.canonical import self_digest, verify_self_digest
from ..v311_agent_lifecycle_v1 import (
    AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    V311_CURRENT_ROOT_DELIVERY_ORIGIN,
    V311_QUALIFICATION_CONTEXT_PROFILE,
    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
    verify_v311_agent_context_consumption_v1,
    verify_v311_agent_input_context_with_packet_v1,
    verify_v311_successor_commit_envelope_full_v1,
)
from ..v31_agent_transport import V31_AGENT_ID
from ..v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as BASE_COMMIT_DIGEST_FIELD,
    SCHEMA_ID as BASE_COMMIT_SCHEMA_ID,
)
from .v31_successor_qualification_v2 import (
    CODEX_QUALIFICATION_DIGEST_FIELD as BASE_CODEX_DIGEST_FIELD,
    verify_successor_codex_durable_qualification_v2,
)


class V311CodexDurableQualificationV3Error(ValueError):
    """The V3.1.1 direct-context qualification failed closed."""


CODEX_QUALIFICATION_V3_SCHEMA_ID = (
    "theory_paper_v311_codex_durable_delivery_qualification_v3"
)
CODEX_QUALIFICATION_V3_SCHEMA_VERSION = "3.0.0"
CODEX_QUALIFICATION_V3_DIGEST_FIELD = "codex_qualification_v3_digest"

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
_BASE_ARTIFACT_KEYS = frozenset(
    {
        "accepted_state",
        "canonical_packet",
        "compilation_admission",
        "compilation_receipt",
        "postseal_selection_delivery",
        "proposal",
        "transport_evidence",
    }
)
_LIFECYCLE_ARTIFACT_KEYS = frozenset(
    {
        "agent_input_context",
        "agent_context_consumption",
        "base_successor_commit_material",
        "successor_commit_envelope",
    }
)
CODEX_QUALIFICATION_V3_ARTIFACT_KEYS = frozenset(
    _BASE_ARTIFACT_KEYS | _LIFECYCLE_ARTIFACT_KEYS
)

_SUMMARY = {
    "verdict": "QUALIFIED_FOR_V311_SUCCESSOR_CONTEXT_DELIVERY_ONLY",
    "current_root_codex_identity_bound": True,
    "complete_v311_context_selected_for_direct_input": True,
    "single_proposal_context_consumption_durable": True,
    "proposal_compilation_postseal_acceptance_durable": True,
    "v311_commit_envelope_durable": True,
    "fixture_transport_rejected": True,
    "old_run_reuse_rejected": True,
    "v2_only_receipt_rejected": True,
    "chat_memory_substitution_rejected": True,
}
_LIMITATIONS = [
    "DIRECT_INPUT_ARTIFACT_DOES_NOT_PROVE_ATTENTION_OR_COGNITION",
    "ONE_OBSERVED_CURRENT_CODEX_DELIVERY_CHAIN_ONLY",
    "SERVICE_MODEL_IDENTITY_AND_EXACT_TOKEN_BUDGET_ARE_NOT_MACHINE_ATTESTED",
    "DOES_NOT_PROVE_FUTURE_CODEX_AVAILABILITY",
    "DOES_NOT_PROVE_PREDICTION_CALIBRATION_OR_PROFITABILITY",
]
_BOUNDARY = {
    "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
    "external_execution_authority": "NONE_LOCAL_SIMULATION",
    "executable": False,
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_use": False,
    "funds_access": False,
    "portfolio_mutation": False,
    "automation_created": False,
}
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "predecessor_run_id",
        "cycle_index",
        "authority_digest",
        "authority_binding",
        "authority_recorded_at",
        "qualified_at",
        "source_qualification_v2_digest",
        "base_codex_qualification_v2",
        "base_codex_qualification_v2_digest",
        "agent_id",
        "delivery_origin",
        "authoring_purpose",
        "context_profile",
        "canonical_packet_digest",
        "agent_input_context_digest",
        "agent_context_consumption_digest",
        "base_successor_commit_material_digest",
        "successor_commit_envelope_digest",
        "proposal_digest",
        "compilation_receipt_digest",
        "compilation_admission_digest",
        "postseal_selection_delivery_digest",
        "action_selection_digest",
        "accepted_state_digest",
        "transport_evidence_digest",
        "artifact_bindings",
        "qualification_summary",
        "limitations",
        "authority_boundary",
        CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    }
)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V311CodexDurableQualificationV3Error(code)
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311CodexDurableQualificationV3Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311CodexDurableQualificationV3Error(code) from exc
    if parsed.tzinfo is None:
        raise V311CodexDurableQualificationV3Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V311CodexDurableQualificationV3Error(code)
    return normalized


def _binding(
    value: Any,
    code: str,
    *,
    semantic_digest: str | None = None,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V311CodexDurableQualificationV3Error(code)
    result = {field: value.get(field) for field in _BINDING_FIELDS}
    if (
        any(not isinstance(result[name], str) or not result[name] for name in result)
        or _HEX_64.fullmatch(str(result["semantic_digest"])) is None
        or _HEX_64.fullmatch(str(result["physical_sha256"])) is None
        or str(result["relative_ref"]).startswith("/")
        or "\\" in str(result["relative_ref"])
        or any(
            part in {"", ".", ".."}
            for part in str(result["relative_ref"]).split("/")
        )
        or (
            semantic_digest is not None
            and result["semantic_digest"] != semantic_digest
        )
        or (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V311CodexDurableQualificationV3Error(code)
    if any(
        marker in str(result["relative_ref"]).lower()
        for marker in ("fixture", "synthetic", "mock")
    ):
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_FIXTURE_EVIDENCE_FORBIDDEN"
        )
    return {name: str(result[name]) for name in _BINDING_FIELDS}


def _artifact_bindings(
    value: Any,
    *,
    base: Mapping[str, Mapping[str, Any]],
    lifecycle_semantics: Mapping[str, tuple[str, str, str]],
) -> dict[str, dict[str, str]]:
    if (
        not isinstance(value, Mapping)
        or set(value) != CODEX_QUALIFICATION_V3_ARTIFACT_KEYS
        or set(base) != _BASE_ARTIFACT_KEYS
        or set(lifecycle_semantics) != _LIFECYCLE_ARTIFACT_KEYS
    ):
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_ARTIFACT_BINDINGS_INVALID"
        )
    result: dict[str, dict[str, str]] = {}
    for name in sorted(_BASE_ARTIFACT_KEYS):
        candidate = _binding(
            value[name], "V311_CODEX_V3_ARTIFACT_BINDINGS_INVALID"
        )
        if candidate != dict(base[name]):
            raise V311CodexDurableQualificationV3Error(
                "V311_CODEX_V3_BASE_ARTIFACT_BINDING_DRIFT"
            )
        result[name] = candidate
    for name in sorted(_LIFECYCLE_ARTIFACT_KEYS):
        semantic, schema_id, digest_field = lifecycle_semantics[name]
        result[name] = _binding(
            value[name],
            "V311_CODEX_V3_ARTIFACT_BINDINGS_INVALID",
            semantic_digest=semantic,
            schema_id=schema_id,
            digest_field=digest_field,
        )
    return result


def build_successor_codex_durable_qualification_v3(
    *,
    base_codex_qualification_v2: Mapping[str, Any],
    qualified_at: str,
    experiment_contract: Mapping[str, Any],
    canonical_packet: Mapping[str, Any],
    proposal_attempt: Mapping[str, Any],
    proposal_request: Mapping[str, Any],
    proposal_claim: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consume: Mapping[str, Any],
    transport_evidence: Mapping[str, Any],
    agent_input_context: Mapping[str, Any],
    agent_context_consumption: Mapping[str, Any],
    base_successor_commit_material: Mapping[str, Any],
    successor_commit_envelope: Mapping[str, Any],
    artifact_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the strong V3 receipt from one already-durable lifecycle."""

    try:
        base_digest = verify_successor_codex_durable_qualification_v2(
            base_codex_qualification_v2
        )
        context_digest = verify_v311_agent_input_context_with_packet_v1(
            agent_input_context, base_authoring_packet=canonical_packet
        )
        consumption_digest = verify_v311_agent_context_consumption_v1(
            agent_context_consumption,
            agent_input_context=agent_input_context,
            base_authoring_packet=canonical_packet,
            proposal_attempt=proposal_attempt,
            proposal_request=proposal_request,
            proposal_claim=proposal_claim,
            proposal_delivery=proposal_delivery,
            proposal_consume=proposal_consume,
            transport_evidence=transport_evidence,
        )
        commit_envelope_digest = verify_v311_successor_commit_envelope_full_v1(
            successor_commit_envelope,
            base_successor_commit_material=base_successor_commit_material,
            experiment_contract=experiment_contract,
            agent_input_context=agent_input_context,
            agent_context_consumption=agent_context_consumption,
            base_authoring_packet=canonical_packet,
            proposal_attempt=proposal_attempt,
            proposal_request=proposal_request,
            proposal_claim=proposal_claim,
            proposal_delivery=proposal_delivery,
            proposal_consume=proposal_consume,
            transport_evidence=transport_evidence,
        )
        base_commit_digest = verify_self_digest(
            base_successor_commit_material, BASE_COMMIT_DIGEST_FIELD
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311CodexDurableQualificationV3Error):
            raise
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_EVIDENCE_INVALID"
        ) from exc

    base = dict(base_codex_qualification_v2)
    lifecycle_semantics = {
        "agent_input_context": (
            context_digest,
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        ),
        "agent_context_consumption": (
            consumption_digest,
            AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
        ),
        "base_successor_commit_material": (
            base_commit_digest,
            BASE_COMMIT_SCHEMA_ID,
            BASE_COMMIT_DIGEST_FIELD,
        ),
        "successor_commit_envelope": (
            commit_envelope_digest,
            V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
            V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
        ),
    }
    bindings = _artifact_bindings(
        artifact_bindings,
        base=base["artifact_bindings"],
        lifecycle_semantics=lifecycle_semantics,
    )
    qualified = _time(qualified_at, "V311_CODEX_V3_QUALIFIED_AT_INVALID")
    authority_time = _time(
        base["authority_recorded_at"], "V311_CODEX_V3_AUTHORITY_TIME_INVALID"
    )
    base_qualified = _time(
        base["qualified_at"], "V311_CODEX_V3_BASE_QUALIFIED_AT_INVALID"
    )
    context_created = _time(
        agent_input_context.get("created_at"),
        "V311_CODEX_V3_CONTEXT_TIME_INVALID",
    )
    consumed = _time(
        agent_context_consumption.get("consumed_at"),
        "V311_CODEX_V3_CONSUMPTION_TIME_INVALID",
    )
    commit_sealed = _time(
        successor_commit_envelope.get("sealed_at"),
        "V311_CODEX_V3_COMMIT_TIME_INVALID",
    )
    base_bindings = base["artifact_bindings"]
    if (
        agent_input_context.get("context_profile")
        != V311_QUALIFICATION_CONTEXT_PROFILE
        or agent_input_context.get("delivery_purpose")
        != "AUTHORIZED_RESEARCH_CYCLE"
        or agent_input_context.get("current_authority_digest")
        != base.get("authority_digest")
        or agent_input_context.get("current_authority_binding")
        != base.get("authority_binding")
        or agent_input_context.get("base_authoring_packet_digest")
        != base.get("canonical_packet_digest")
        or agent_input_context.get("base_authoring_packet_binding")
        != base_bindings.get("canonical_packet")
        or agent_context_consumption.get("agent_input_context_digest")
        != context_digest
        or agent_context_consumption.get("agent_input_context_binding")
        != bindings["agent_input_context"]
        or agent_context_consumption.get("base_authoring_packet_digest")
        != base.get("canonical_packet_digest")
        or agent_context_consumption.get("transport_evidence_digest")
        != base.get("transport_evidence_digest")
        or agent_context_consumption.get("transport_evidence_binding")
        != base_bindings.get("transport_evidence")
        or successor_commit_envelope.get("agent_input_context_digest")
        != context_digest
        or successor_commit_envelope.get("agent_input_context_binding")
        != bindings["agent_input_context"]
        or successor_commit_envelope.get("agent_context_consumption_digest")
        != consumption_digest
        or successor_commit_envelope.get("agent_context_consumption_binding")
        != bindings["agent_context_consumption"]
        or successor_commit_envelope.get(
            "base_successor_commit_material_digest"
        )
        != base_commit_digest
        or successor_commit_envelope.get(
            "base_successor_commit_material_binding"
        )
        != bindings["base_successor_commit_material"]
        or successor_commit_envelope.get("accepted_state_digest")
        != base.get("accepted_state_digest")
        or successor_commit_envelope.get("transport_evidence_digest")
        != base.get("transport_evidence_digest")
        or base_successor_commit_material.get("active_authority_digest")
        != base.get("authority_digest")
        or base_successor_commit_material.get("transport_evidence_binding")
        != base_bindings.get("transport_evidence")
        or base.get("source_qualification_v2_digest") is None
        or qualified < max(
            authority_time,
            base_qualified,
            context_created,
            consumed,
            commit_sealed,
        )
    ):
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_CROSS_BINDING_INVALID"
        )

    document = {
        "schema_id": CODEX_QUALIFICATION_V3_SCHEMA_ID,
        "schema_version": CODEX_QUALIFICATION_V3_SCHEMA_VERSION,
        "run_id": base["run_id"],
        "predecessor_run_id": base["predecessor_run_id"],
        "cycle_index": base["cycle_index"],
        "authority_digest": base["authority_digest"],
        "authority_binding": dict(base["authority_binding"]),
        "authority_recorded_at": base["authority_recorded_at"],
        "qualified_at": qualified_at,
        "source_qualification_v2_digest": base[
            "source_qualification_v2_digest"
        ],
        "base_codex_qualification_v2": base,
        "base_codex_qualification_v2_digest": base_digest,
        "agent_id": V31_AGENT_ID,
        "delivery_origin": V311_CURRENT_ROOT_DELIVERY_ORIGIN,
        "authoring_purpose": "AUTHORIZED_RESEARCH_CYCLE",
        "context_profile": V311_QUALIFICATION_CONTEXT_PROFILE,
        "canonical_packet_digest": base["canonical_packet_digest"],
        "agent_input_context_digest": context_digest,
        "agent_context_consumption_digest": consumption_digest,
        "base_successor_commit_material_digest": base_commit_digest,
        "successor_commit_envelope_digest": commit_envelope_digest,
        "proposal_digest": base["proposal_digest"],
        "compilation_receipt_digest": base["compilation_receipt_digest"],
        "compilation_admission_digest": base[
            "compilation_admission_digest"
        ],
        "postseal_selection_delivery_digest": base[
            "postseal_selection_delivery_digest"
        ],
        "action_selection_digest": base["action_selection_digest"],
        "accepted_state_digest": base["accepted_state_digest"],
        "transport_evidence_digest": base["transport_evidence_digest"],
        "artifact_bindings": bindings,
        "qualification_summary": dict(_SUMMARY),
        "limitations": list(_LIMITATIONS),
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, CODEX_QUALIFICATION_V3_DIGEST_FIELD)


def verify_successor_codex_durable_qualification_v3(
    document: Mapping[str, Any],
) -> str:
    """Verify the closed receipt; durable replay validates every bound byte."""

    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_QUALIFICATION_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, CODEX_QUALIFICATION_V3_DIGEST_FIELD
        )
        base = document["base_codex_qualification_v2"]
        base_digest = verify_successor_codex_durable_qualification_v2(base)
        qualified = _time(
            document["qualified_at"], "V311_CODEX_V3_QUALIFIED_AT_INVALID"
        )
        base_qualified = _time(
            base["qualified_at"], "V311_CODEX_V3_BASE_QUALIFIED_AT_INVALID"
        )
        lifecycle_semantics = {
            "agent_input_context": (
                _digest(
                    document["agent_input_context_digest"],
                    "V311_CODEX_V3_DIGEST_INVALID",
                ),
                AGENT_INPUT_CONTEXT_SCHEMA_ID,
                AGENT_INPUT_CONTEXT_DIGEST_FIELD,
            ),
            "agent_context_consumption": (
                _digest(
                    document["agent_context_consumption_digest"],
                    "V311_CODEX_V3_DIGEST_INVALID",
                ),
                AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
                AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
            ),
            "base_successor_commit_material": (
                _digest(
                    document["base_successor_commit_material_digest"],
                    "V311_CODEX_V3_DIGEST_INVALID",
                ),
                BASE_COMMIT_SCHEMA_ID,
                BASE_COMMIT_DIGEST_FIELD,
            ),
            "successor_commit_envelope": (
                _digest(
                    document["successor_commit_envelope_digest"],
                    "V311_CODEX_V3_DIGEST_INVALID",
                ),
                V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
                V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
            ),
        }
        bindings = _artifact_bindings(
            document["artifact_bindings"],
            base=base["artifact_bindings"],
            lifecycle_semantics=lifecycle_semantics,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311CodexDurableQualificationV3Error):
            raise
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_QUALIFICATION_INVALID"
        ) from exc
    del bindings
    mirrored = {
        "run_id": "run_id",
        "predecessor_run_id": "predecessor_run_id",
        "cycle_index": "cycle_index",
        "authority_digest": "authority_digest",
        "authority_binding": "authority_binding",
        "authority_recorded_at": "authority_recorded_at",
        "source_qualification_v2_digest": "source_qualification_v2_digest",
        "canonical_packet_digest": "canonical_packet_digest",
        "proposal_digest": "proposal_digest",
        "compilation_receipt_digest": "compilation_receipt_digest",
        "compilation_admission_digest": "compilation_admission_digest",
        "postseal_selection_delivery_digest": (
            "postseal_selection_delivery_digest"
        ),
        "action_selection_digest": "action_selection_digest",
        "accepted_state_digest": "accepted_state_digest",
        "transport_evidence_digest": "transport_evidence_digest",
    }
    if (
        document.get("schema_id") != CODEX_QUALIFICATION_V3_SCHEMA_ID
        or document.get("schema_version")
        != CODEX_QUALIFICATION_V3_SCHEMA_VERSION
        or document.get("base_codex_qualification_v2_digest") != base_digest
        or any(document.get(left) != base.get(right) for left, right in mirrored.items())
        or document.get("agent_id") != V31_AGENT_ID
        or document.get("delivery_origin")
        != V311_CURRENT_ROOT_DELIVERY_ORIGIN
        or document.get("authoring_purpose") != "AUTHORIZED_RESEARCH_CYCLE"
        or document.get("context_profile")
        != V311_QUALIFICATION_CONTEXT_PROFILE
        or document.get("qualification_summary") != _SUMMARY
        or document.get("limitations") != _LIMITATIONS
        or document.get("authority_boundary") != _BOUNDARY
        or qualified < base_qualified
    ):
        raise V311CodexDurableQualificationV3Error(
            "V311_CODEX_V3_QUALIFICATION_INVALID"
        )
    return supplied


__all__ = [
    "CODEX_QUALIFICATION_V3_ARTIFACT_KEYS",
    "CODEX_QUALIFICATION_V3_DIGEST_FIELD",
    "CODEX_QUALIFICATION_V3_SCHEMA_ID",
    "CODEX_QUALIFICATION_V3_SCHEMA_VERSION",
    "V311CodexDurableQualificationV3Error",
    "build_successor_codex_durable_qualification_v3",
    "verify_successor_codex_durable_qualification_v3",
]
