"""Successor-only qualification contracts for the V3.1 prospective runtime.

These contracts close three different readiness questions without turning any
of them into a prediction, profitability, execution, or production claim:

* a fresh authority-postdating public-source acquisition;
* one current-Codex durable authoring/compile/select/accept delivery;
* the raw-first, absolute-time, one-attempt monitor guarded by the supervisor.

Physical byte replay remains an Application/Infrastructure responsibility.
The pure documents below retain all semantic inputs needed for deterministic
reconstruction and bind every durable artifact by semantic and physical hash.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from ..agent_research_contract import (
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from ..contracts.canonical import (
    self_digest,
    verify_self_digest,
)
from ..v31_agent_transport import (
    V31_AGENT_ID,
    V31_TRANSPORT_EVIDENCE_LEVEL,
    validate_v31_transport_evidence,
)
from ..v31_cycle_authoring import (
    validate_v31_agent_open_analysis_envelope,
    validate_v31_authoring_compilation_admission,
    validate_v31_authoring_compilation_receipt,
    validate_v31_proposal_authoring_packet,
)
from ..v31_outcome_capture_v2 import verify_outcome_clock_policy
from ..v31_source_qualification import (
    OKX_PUBLIC_BASE_URL,
    REQUEST_SPECS,
    verify_v31_source_qualification_completion,
    verify_v31_source_qualification_plan,
)


class V31SuccessorQualificationV2Error(ValueError):
    """A successor qualification was incomplete, stale, or overstated."""


SOURCE_QUALIFICATION_SCHEMA_ID = (
    "theory_paper_v31_successor_public_source_qualification_v2"
)
CODEX_QUALIFICATION_SCHEMA_ID = (
    "theory_paper_v31_successor_codex_durable_delivery_qualification_v2"
)
MONITOR_QUALIFICATION_SCHEMA_ID = (
    "theory_paper_v31_successor_outcome_monitor_qualification_v2"
)
RAW_FIRST_PROBE_SCHEMA_ID = (
    "theory_paper_v31_successor_raw_first_failure_probe_v2"
)
SUPERVISOR_PROBE_SCHEMA_ID = (
    "theory_paper_v31_successor_supervisor_gate_probe_v2"
)
MONITOR_POLICY_SCHEMA_ID = (
    "theory_paper_v31_successor_absolute_monitor_policy_v2"
)
SUCCESSOR_QUALIFICATION_SCHEMA_VERSION = "2.0.0"

SOURCE_QUALIFICATION_DIGEST_FIELD = "source_qualification_v2_digest"
CODEX_QUALIFICATION_DIGEST_FIELD = "codex_qualification_v2_digest"
MONITOR_QUALIFICATION_DIGEST_FIELD = "monitor_qualification_v2_digest"
RAW_FIRST_PROBE_DIGEST_FIELD = "raw_first_probe_digest"
SUPERVISOR_PROBE_DIGEST_FIELD = "supervisor_probe_digest"
MONITOR_POLICY_DIGEST_FIELD = "monitor_policy_digest"

PUBLIC_SOURCE_VALIDITY_SECONDS = 3_600
MONITOR_OUTCOME_HORIZON_SECONDS = 3_600
MONITOR_OUTCOME_GRACE_SECONDS = 900
MONITOR_ENDPOINT = (
    "https://www.okx.com/api/v5/public/mark-price"
    "?instType=SWAP&instId=BTC-USDT-SWAP"
)

RAW_FIRST_FAILURE_CASES = (
    "ATTEMPT_ONLY_CRASH_FAILS_CLOSED_WITHOUT_REFETCH",
    "CLOCK_POLICY_DRIFT_REJECTED_BEFORE_PARSE",
    "CRASH_AFTER_CAPTURE_RECOVERS_LOCALLY_WITHOUT_REFETCH",
    "INVALID_JSON_RAW_PRESERVED_BEFORE_PARSE_FAILURE",
    "RAW_TAMPER_BLOCKS_REPLAY",
    "TRANSPORT_FAILURE_CRASH_BINDS_FAILURE_WITHOUT_REFETCH",
)
SUPERVISOR_GATE_CASES = (
    "COMMIT_INTENT_PRECEDES_ACCEPTED_STATE",
    "FAILED_MONITOR_BLOCKS_NEW_CYCLE",
    "ONE_STATE_CHANGE_BOUNDARY_PER_WAKE",
    "PREVIOUS_DURABLE_OUTCOME_REQUIRED_FOR_NEXT_CYCLE",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_DISALLOWED_EVIDENCE_TOKENS = frozenset(
    {"fixture", "fixtures", "fake", "synthetic", "chat-memory"}
)
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
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
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31SuccessorQualificationV2Error(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SuccessorQualificationV2Error(code)
    return value


def _time(value: Any, code: str) -> datetime:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SuccessorQualificationV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SuccessorQualificationV2Error(code)
    normalized = parsed.astimezone(UTC)
    canonical_values = {
        normalized.isoformat(timespec="seconds").replace("+00:00", "Z"),
        normalized.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        normalized.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
    }
    if value not in canonical_values:
        raise V31SuccessorQualificationV2Error(code)
    return normalized


def _relative_ref(value: Any, code: str) -> str:
    value = _text(value, code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31SuccessorQualificationV2Error(code)
    return value


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V31SuccessorQualificationV2Error(code)
    result = {
        "relative_ref": _relative_ref(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    return result


def _assert_nonfixture_ref(relative_ref: str, code: str) -> None:
    parts = {
        token.lower()
        for part in PurePosixPath(relative_ref).parts
        for token in re.split(r"[^a-zA-Z0-9]+", part)
        if token
    }
    if parts & _DISALLOWED_EVIDENCE_TOKENS:
        raise V31SuccessorQualificationV2Error(code)


def _authority_binding(
    value: Any, *, authority_digest: str
) -> dict[str, str]:
    result = _binding(value, "V31_SUCCESSOR_AUTHORITY_BINDING_INVALID")
    if (
        result["digest_field"] != "authority_digest"
        or result["semantic_digest"] != _digest(
            authority_digest, "V31_SUCCESSOR_AUTHORITY_DIGEST_INVALID"
        )
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_AUTHORITY_BINDING_INVALID"
        )
    _assert_nonfixture_ref(
        result["relative_ref"], "V31_SUCCESSOR_AUTHORITY_FIXTURE_FORBIDDEN"
    )
    return result


def _assert_successor_identity(
    *, run_id: str, predecessor_run_id: str
) -> tuple[str, str]:
    run = _text(run_id, "V31_SUCCESSOR_RUN_ID_INVALID")
    predecessor = _text(
        predecessor_run_id, "V31_SUCCESSOR_PREDECESSOR_RUN_ID_INVALID"
    )
    if run == predecessor:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_OLD_RUN_REUSE_FORBIDDEN"
        )
    lowered = run.lower()
    if any(token in lowered for token in _DISALLOWED_EVIDENCE_TOKENS):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_FIXTURE_RUN_FORBIDDEN"
        )
    return run, predecessor


def _public_url(value: Any, *, expected_path: str) -> str:
    value = _text(value, "V31_SUCCESSOR_PUBLIC_ENDPOINT_INVALID")
    parsed = urlsplit(value)
    try:
        query = parse_qsl(
            parsed.query, keep_blank_values=True, strict_parsing=True
        )
    except ValueError as exc:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_PUBLIC_ENDPOINT_INVALID"
        ) from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.okx.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.fragment
        or len(query) != len(set(query))
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_PUBLIC_ENDPOINT_INVALID"
        )
    return value


def _source_artifact_bindings(value: Any) -> dict[str, dict[str, str]]:
    expected = {"checkpoint", "completion", "plan", "snapshot"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_ARTIFACT_BINDINGS_INVALID"
        )
    result = {
        name: _binding(
            value[name], "V31_SUCCESSOR_SOURCE_ARTIFACT_BINDINGS_INVALID"
        )
        for name in sorted(expected)
    }
    for binding in result.values():
        _assert_nonfixture_ref(
            binding["relative_ref"],
            "V31_SUCCESSOR_SOURCE_FIXTURE_FORBIDDEN",
        )
    return result


def _source_capture_summaries(
    *,
    plan: Mapping[str, Any],
    completion: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], datetime]:
    captures = snapshot.get("source_captures")
    raw_bindings = completion.get("raw_bindings")
    record_digests = completion.get("source_capture_record_digests")
    if (
        not isinstance(captures, list)
        or not captures
        or not isinstance(raw_bindings, Mapping)
        or not isinstance(record_digests, Mapping)
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_CAPTURES_INVALID"
        )
    specs = {
        str(row["request_id"]): dict(row)
        for row in plan.get("request_specs", [])
        if isinstance(row, Mapping)
    }
    if specs != {str(row["request_id"]): dict(row) for row in REQUEST_SPECS}:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_ENDPOINT_SCOPE_INVALID"
        )
    summaries: list[dict[str, Any]] = []
    received_times: list[datetime] = []
    seen: set[str] = set()
    for raw_capture in captures:
        if not isinstance(raw_capture, Mapping):
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_SOURCE_CAPTURES_INVALID"
            )
        request_id = _text(
            raw_capture.get("request_id"),
            "V31_SUCCESSOR_SOURCE_CAPTURE_ID_INVALID",
        )
        spec = specs.get(request_id)
        binding = raw_bindings.get(request_id)
        if (
            request_id in seen
            or spec is None
            or not isinstance(binding, Mapping)
            or raw_capture.get("method") != "GET"
            or raw_capture.get("base_url") != OKX_PUBLIC_BASE_URL
            or raw_capture.get("path") != spec["path"]
            or raw_capture.get("http_status") != 200
            or binding.get("semantic_digest")
            != raw_capture.get("raw_body_sha256")
            or binding.get("physical_sha256")
            != raw_capture.get("raw_body_sha256")
            or binding.get("relative_ref")
            != f"cycles/0001/market/raw/{request_id}.body"
            or record_digests.get(request_id)
            != raw_capture.get("record_digest")
        ):
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_SOURCE_CAPTURE_BINDING_INVALID"
            )
        final_url = _public_url(
            raw_capture.get("final_url"), expected_path=str(spec["path"])
        )
        query_document = raw_capture.get("query")
        if not isinstance(query_document, list) or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "value"}
            or not isinstance(row["name"], str)
            or not isinstance(row["value"], str)
            for row in query_document
        ):
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_PUBLIC_ENDPOINT_QUERY_INVALID"
            )
        observed_query = parse_qsl(
            urlsplit(final_url).query,
            keep_blank_values=True,
            strict_parsing=True,
        )
        expected_query = [
            (str(row["name"]), str(row["value"])) for row in query_document
        ]
        if (
            observed_query != expected_query
            or len({name for name, _value in observed_query})
            != len(observed_query)
        ):
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_PUBLIC_ENDPOINT_QUERY_INVALID"
            )
        received_at = _time(
            raw_capture.get("response_received_at"),
            "V31_SUCCESSOR_SOURCE_CAPTURE_TIME_INVALID",
        )
        received_times.append(received_at)
        seen.add(request_id)
        summaries.append(
            {
                "request_id": request_id,
                "method": "GET",
                "final_url": final_url,
                "response_received_at": raw_capture["response_received_at"],
                "http_status": 200,
                "raw_relative_ref": binding["relative_ref"],
                "raw_body_sha256": binding["semantic_digest"],
                "raw_body_byte_length": raw_capture["raw_body_byte_length"],
                "capture_record_digest": record_digests[request_id],
            }
        )
    if seen != set(raw_bindings) or seen != set(record_digests):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_CAPTURE_SET_MISMATCH"
        )
    return sorted(summaries, key=lambda row: row["request_id"]), max(received_times)


def build_successor_public_source_qualification_v2(
    *,
    run_id: str,
    predecessor_run_id: str,
    authority_digest: str,
    authority_binding: Mapping[str, Any],
    authority_recorded_at: str,
    qualification_root_ref: str,
    qualified_at: str,
    expires_at: str,
    plan: Mapping[str, Any],
    completion: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    artifact_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a fresh public-source receipt only from post-authority raw bytes."""

    run, predecessor = _assert_successor_identity(
        run_id=run_id, predecessor_run_id=predecessor_run_id
    )
    try:
        plan_digest = verify_v31_source_qualification_plan(plan)
        completion_digest = verify_v31_source_qualification_completion(
            completion
        )
        snapshot_digest = verify_self_digest(
            snapshot, "native_market_snapshot_digest"
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_DOCUMENT_INVALID"
        ) from exc
    authority_time = _time(
        authority_recorded_at, "V31_SUCCESSOR_AUTHORITY_TIME_INVALID"
    )
    created = _time(
        plan.get("created_at"), "V31_SUCCESSOR_SOURCE_PLAN_TIME_INVALID"
    )
    completed = _time(
        completion.get("completed_at"),
        "V31_SUCCESSOR_SOURCE_COMPLETION_TIME_INVALID",
    )
    decision = _time(
        completion.get("decision_at"),
        "V31_SUCCESSOR_SOURCE_DECISION_TIME_INVALID",
    )
    qualified = _time(
        qualified_at, "V31_SUCCESSOR_SOURCE_QUALIFIED_AT_INVALID"
    )
    expires = _time(
        expires_at, "V31_SUCCESSOR_SOURCE_EXPIRES_AT_INVALID"
    )
    summaries, fresh = _source_capture_summaries(
        plan=plan, completion=completion, snapshot=snapshot
    )
    bindings = _source_artifact_bindings(artifact_bindings)
    root_ref = _relative_ref(
        qualification_root_ref,
        "V31_SUCCESSOR_SOURCE_QUALIFICATION_ROOT_INVALID",
    )
    _assert_nonfixture_ref(
        root_ref, "V31_SUCCESSOR_SOURCE_FIXTURE_FORBIDDEN"
    )
    expected_semantics = {
        "plan": plan_digest,
        "checkpoint": _digest(
            bindings["checkpoint"]["semantic_digest"],
            "V31_SUCCESSOR_SOURCE_CHECKPOINT_DIGEST_INVALID",
        ),
        "completion": completion_digest,
        "snapshot": snapshot_digest,
    }
    if any(
        bindings[name]["semantic_digest"] != digest
        for name, digest in expected_semantics.items()
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_ARTIFACT_SEMANTIC_MISMATCH"
        )
    if (
        created <= authority_time
        or decision < fresh
        or completed < decision
        or qualified < completed
        or expires <= qualified
        or expires > fresh + timedelta(seconds=PUBLIC_SOURCE_VALIDITY_SECONDS)
        or completion.get("source_qualification_plan_digest") != plan_digest
        or completion.get("snapshot_binding", {}).get("semantic_digest")
        != snapshot_digest
        or completion.get("required_requests_complete") is not True
        or completion.get("raw_bytes_read_back_and_verified") is not True
        or completion.get("attempt_count") != 1
        or completion.get("retry_count") != 0
        or plan.get("attempt_limit") != 1
        or plan.get("retry_count") != 0
        or plan.get("raw_retention")
        != "FULL_RESPONSE_BYTES_WRITE_ONCE_AND_READBACK"
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_FRESHNESS_OR_DURABILITY_INVALID"
        )
    document = {
        "schema_id": SOURCE_QUALIFICATION_SCHEMA_ID,
        "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
        "run_id": run,
        "predecessor_run_id": predecessor,
        "qualification_id": plan["qualification_id"],
        "authority_digest": authority_digest,
        "authority_binding": _authority_binding(
            authority_binding, authority_digest=authority_digest
        ),
        "authority_recorded_at": authority_recorded_at,
        "qualification_root_ref": root_ref,
        "qualified_at": qualified_at,
        "fresh_at": fresh.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at,
        "transport_origin": "REAL_PUBLIC_HTTP_CAPTURE_NONFIXTURE",
        "venue": "OKX",
        "instrument_id": "BTC-USDT-SWAP",
        "request_method": "GET",
        "endpoint_scope": "FIXED_OFFICIAL_PUBLIC_OKX_ONLY",
        "attempt_limit": 1,
        "retry_allowed": False,
        "raw_first_and_readback_verified": True,
        "plan": dict(plan),
        "completion": dict(completion),
        "snapshot": dict(snapshot),
        "capture_summaries": summaries,
        "artifact_bindings": bindings,
        "qualification_summary": {
            "verdict": "QUALIFIED_FOR_SUCCESSOR_SOURCE_ADMISSION_ONLY",
            "authority_postdating": True,
            "fresh_at_expiry_enforced": True,
            "public_only_scope_verified": True,
            "physical_raw_binding_verified": True,
            "fixture_transport_rejected": True,
        },
        "limitations": [
            "POINT_IN_TIME_SOURCE_QUALIFICATION_ONLY",
            "DOES_NOT_PROVE_FUTURE_PROVIDER_AVAILABILITY",
            "DOES_NOT_PROVE_MARKET_PREDICTION_INCREMENT",
            "DOES_NOT_PROVE_PROFITABILITY_OR_PRODUCTION_READINESS",
        ],
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, SOURCE_QUALIFICATION_DIGEST_FIELD)


def verify_successor_public_source_qualification_v2(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, SOURCE_QUALIFICATION_DIGEST_FIELD
        )
        rebuilt = build_successor_public_source_qualification_v2(
            run_id=document["run_id"],
            predecessor_run_id=document["predecessor_run_id"],
            authority_digest=document["authority_digest"],
            authority_binding=document["authority_binding"],
            authority_recorded_at=document["authority_recorded_at"],
            qualification_root_ref=document["qualification_root_ref"],
            qualified_at=document["qualified_at"],
            expires_at=document["expires_at"],
            plan=document["plan"],
            completion=document["completion"],
            snapshot=document["snapshot"],
            artifact_bindings=document["artifact_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorQualificationV2Error):
            raise
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[SOURCE_QUALIFICATION_DIGEST_FIELD]:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _codex_artifact_bindings(
    value: Any, *, semantic_digests: Mapping[str, str]
) -> dict[str, dict[str, str]]:
    expected = {
        "accepted_state",
        "canonical_packet",
        "compilation_admission",
        "compilation_receipt",
        "postseal_selection_delivery",
        "proposal",
        "transport_evidence",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_ARTIFACT_BINDINGS_INVALID"
        )
    result: dict[str, dict[str, str]] = {}
    for name in sorted(expected):
        binding = _binding(
            value[name], "V31_SUCCESSOR_CODEX_ARTIFACT_BINDINGS_INVALID"
        )
        if binding["semantic_digest"] != semantic_digests[name]:
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_CODEX_ARTIFACT_SEMANTIC_MISMATCH"
            )
        _assert_nonfixture_ref(
            binding["relative_ref"],
            "V31_SUCCESSOR_CODEX_FIXTURE_EVIDENCE_FORBIDDEN",
        )
        result[name] = binding
    return result


def build_successor_codex_durable_qualification_v2(
    *,
    run_id: str,
    predecessor_run_id: str,
    cycle_index: int,
    authority_digest: str,
    authority_binding: Mapping[str, Any],
    authority_recorded_at: str,
    qualified_at: str,
    source_qualification_v2_digest: str,
    canonical_packet: Mapping[str, Any],
    agent_authoring_envelope: Mapping[str, Any],
    transport_evidence: Mapping[str, Any],
    inputs_receipt: Mapping[str, Any],
    agent_proposal: Mapping[str, Any],
    compilation_receipt: Mapping[str, Any],
    compilation_admission: Mapping[str, Any],
    postseal_selection_delivery: Mapping[str, Any],
    accepted_state: Mapping[str, Any],
    artifact_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind one real current-Codex formal cycle through durable acceptance."""

    run, predecessor = _assert_successor_identity(
        run_id=run_id, predecessor_run_id=predecessor_run_id
    )
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_CYCLE_INVALID"
        )
    try:
        packet_digest = validate_v31_proposal_authoring_packet(
            canonical_packet
        )
        envelope_digest = validate_v31_agent_open_analysis_envelope(
            agent_authoring_envelope, authoring_packet=canonical_packet
        )
        evidence_digest = validate_v31_transport_evidence(
            transport_evidence
        )
        inputs_digest = verify_v31_inputs_receipt(inputs_receipt)
        proposal_digest = verify_v31_agent_proposal(
            agent_proposal, inputs_receipt=inputs_receipt
        )
        compilation_digest = validate_v31_authoring_compilation_receipt(
            compilation_receipt,
            authoring_packet=canonical_packet,
            authoring_envelope=agent_authoring_envelope,
        )
        admission_digest = validate_v31_authoring_compilation_admission(
            compilation_admission
        )
        selection_digest = verify_self_digest(
            postseal_selection_delivery, "delivery_digest"
        )
        accepted_digest = verify_self_digest(
            accepted_state, "accepted_state_digest"
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_EVIDENCE_INVALID"
        ) from exc
    authority_ref = _authority_binding(
        authority_binding, authority_digest=authority_digest
    )
    qualified = _time(
        qualified_at, "V31_SUCCESSOR_CODEX_QUALIFIED_AT_INVALID"
    )
    authority_time = _time(
        authority_recorded_at, "V31_SUCCESSOR_AUTHORITY_TIME_INVALID"
    )
    selected_at = _time(
        accepted_state.get("selected_at"),
        "V31_SUCCESSOR_CODEX_SELECTED_AT_INVALID",
    )
    selection_payload = postseal_selection_delivery.get("payload")
    if not isinstance(selection_payload, Mapping):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_SELECTION_PAYLOAD_INVALID"
        )
    selection_payload_digest = _digest(
        selection_payload.get("action_selection_digest")
        if isinstance(selection_payload, Mapping)
        else None,
        "V31_SUCCESSOR_CODEX_SELECTION_PAYLOAD_INVALID",
    )
    authority_context = canonical_packet.get("authority_context")
    stage_states = transport_evidence.get("stages")
    semantic_digests = {
        "accepted_state": accepted_digest,
        "canonical_packet": packet_digest,
        "compilation_admission": admission_digest,
        "compilation_receipt": compilation_digest,
        "postseal_selection_delivery": selection_digest,
        "proposal": proposal_digest,
        "transport_evidence": evidence_digest,
    }
    bindings = _codex_artifact_bindings(
        artifact_bindings, semantic_digests=semantic_digests
    )
    if (
        canonical_packet.get("run_id") != run
        or canonical_packet.get("cycle_index") != cycle_index
        or canonical_packet.get("authoring_purpose")
        != "AUTHORIZED_RESEARCH_CYCLE"
        or canonical_packet.get("chat_history_is_authority") is not False
        or canonical_packet.get("qualification_evidence_is_start_authority")
        is not False
        or not isinstance(authority_context, Mapping)
        or authority_context.get("active_authority_binding") != authority_ref
        or authority_context.get("experiment_start_authorized") is not True
        or transport_evidence.get("run_id") != run
        or transport_evidence.get("cycle_index") != cycle_index
        or transport_evidence.get("agent_id") != V31_AGENT_ID
        or transport_evidence.get("evidence_level")
        != V31_TRANSPORT_EVIDENCE_LEVEL
        or transport_evidence.get("proposal_payload_digest")
        != envelope_digest
        or transport_evidence.get("selection_payload_digest")
        != selection_payload_digest
        or not isinstance(stage_states, Mapping)
        or set(stage_states) != {"PROPOSAL", "SELECTION"}
        or inputs_receipt.get("run_id") != run
        or inputs_receipt.get("cycle_index") != cycle_index
        or compilation_receipt.get("authoring_packet_digest") != packet_digest
        or compilation_receipt.get("agent_authoring_envelope_digest")
        != envelope_digest
        or compilation_receipt.get("inputs_receipt_digest") != inputs_digest
        or compilation_receipt.get("agent_proposal_digest") != proposal_digest
        or accepted_state.get("run_id") != run
        or accepted_state.get("cycle_index") != cycle_index
        or accepted_state.get("agent_proposal_digest") != proposal_digest
        or accepted_state.get("action_selection_digest")
        != selection_payload_digest
        or accepted_state.get("status") != "ACCEPTED_RESEARCH_ONLY"
        or accepted_state.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or accepted_state.get("executable") is not False
        or qualified < selected_at
        or selected_at <= authority_time
        or postseal_selection_delivery.get("payload_schema_id")
        != "theory_paper_v2_v31_action_selection"
        or postseal_selection_delivery.get("stage") != "SELECTION"
        or postseal_selection_delivery.get("payload_digest")
        != selection_payload_digest
        or compilation_admission.get("selection_unblocked") is not True
        or compilation_admission.get("selection_performed") is not False
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_CROSS_BINDING_INVALID"
        )
    document = {
        "schema_id": CODEX_QUALIFICATION_SCHEMA_ID,
        "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
        "run_id": run,
        "predecessor_run_id": predecessor,
        "cycle_index": cycle_index,
        "authority_digest": authority_digest,
        "authority_binding": authority_ref,
        "authority_recorded_at": authority_recorded_at,
        "qualified_at": qualified_at,
        "source_qualification_v2_digest": _digest(
            source_qualification_v2_digest,
            "V31_SUCCESSOR_CODEX_SOURCE_QUALIFICATION_DIGEST_INVALID",
        ),
        "agent_id": V31_AGENT_ID,
        "delivery_origin": "CURRENT_ROOT_CODEX_DIRECT_CANONICAL_PACKET",
        "authoring_purpose": "AUTHORIZED_RESEARCH_CYCLE",
        "canonical_packet_digest": packet_digest,
        "proposal_digest": proposal_digest,
        "compilation_receipt_digest": compilation_digest,
        "compilation_admission_digest": admission_digest,
        "postseal_selection_delivery_digest": selection_digest,
        "action_selection_digest": selection_payload_digest,
        "accepted_state_digest": accepted_digest,
        "transport_evidence_digest": evidence_digest,
        "artifact_bindings": bindings,
        "qualification_summary": {
            "verdict": "QUALIFIED_FOR_SUCCESSOR_CODEX_DELIVERY_ONLY",
            "current_codex_identity_bound": True,
            "canonical_packet_delivered_directly": True,
            "proposal_compilation_postseal_acceptance_durable": True,
            "fixture_transport_rejected": True,
            "old_run_reuse_rejected": True,
            "chat_memory_substitution_rejected": True,
        },
        "limitations": [
            "ONE_OBSERVED_CURRENT_CODEX_DELIVERY_CHAIN_ONLY",
            "NO_EXACT_MODEL_OR_TOKEN_BUDGET_ATTESTATION",
            "DOES_NOT_PROVE_FUTURE_CODEX_AVAILABILITY",
            "DOES_NOT_PROVE_PREDICTION_OR_PROFITABILITY",
        ],
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, CODEX_QUALIFICATION_DIGEST_FIELD)


def verify_successor_codex_durable_qualification_v2(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_QUALIFICATION_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, CODEX_QUALIFICATION_DIGEST_FIELD
        )
    except ValueError as exc:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_QUALIFICATION_INVALID"
        ) from exc
    required = {
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
        "agent_id",
        "delivery_origin",
        "authoring_purpose",
        "canonical_packet_digest",
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
        CODEX_QUALIFICATION_DIGEST_FIELD,
    }
    expected_summary = {
        "verdict": "QUALIFIED_FOR_SUCCESSOR_CODEX_DELIVERY_ONLY",
        "current_codex_identity_bound": True,
        "canonical_packet_delivered_directly": True,
        "proposal_compilation_postseal_acceptance_durable": True,
        "fixture_transport_rejected": True,
        "old_run_reuse_rejected": True,
        "chat_memory_substitution_rejected": True,
    }
    expected_limitations = [
        "ONE_OBSERVED_CURRENT_CODEX_DELIVERY_CHAIN_ONLY",
        "NO_EXACT_MODEL_OR_TOKEN_BUDGET_ATTESTATION",
        "DOES_NOT_PROVE_FUTURE_CODEX_AVAILABILITY",
        "DOES_NOT_PROVE_PREDICTION_OR_PROFITABILITY",
    ]
    run, predecessor = _assert_successor_identity(
        run_id=document.get("run_id"),
        predecessor_run_id=document.get("predecessor_run_id"),
    )
    del run, predecessor
    authority_time = _time(
        document.get("authority_recorded_at"),
        "V31_SUCCESSOR_AUTHORITY_TIME_INVALID",
    )
    qualified_time = _time(
        document.get("qualified_at"),
        "V31_SUCCESSOR_CODEX_QUALIFIED_AT_INVALID",
    )
    if qualified_time < authority_time:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_QUALIFICATION_PRECEDES_AUTHORITY"
        )
    authority_ref = _authority_binding(
        document.get("authority_binding"),
        authority_digest=document.get("authority_digest"),
    )
    semantic_names = {
        "accepted_state": "accepted_state_digest",
        "canonical_packet": "canonical_packet_digest",
        "compilation_admission": "compilation_admission_digest",
        "compilation_receipt": "compilation_receipt_digest",
        "postseal_selection_delivery": "postseal_selection_delivery_digest",
        "proposal": "proposal_digest",
        "transport_evidence": "transport_evidence_digest",
    }
    semantics = {
        name: _digest(
            document.get(field), "V31_SUCCESSOR_CODEX_DIGEST_INVALID"
        )
        for name, field in semantic_names.items()
    }
    bindings = _codex_artifact_bindings(
        document.get("artifact_bindings"), semantic_digests=semantics
    )
    del authority_ref, bindings
    if (
        set(document) != required
        or document.get("schema_id") != CODEX_QUALIFICATION_SCHEMA_ID
        or document.get("schema_version")
        != SUCCESSOR_QUALIFICATION_SCHEMA_VERSION
        or document.get("agent_id") != V31_AGENT_ID
        or document.get("delivery_origin")
        != "CURRENT_ROOT_CODEX_DIRECT_CANONICAL_PACKET"
        or document.get("authoring_purpose") != "AUTHORIZED_RESEARCH_CYCLE"
        or document.get("qualification_summary") != expected_summary
        or document.get("limitations") != expected_limitations
        or document.get("authority_boundary") != _BOUNDARY
        or not isinstance(document.get("cycle_index"), int)
        or isinstance(document.get("cycle_index"), bool)
        or not 1 <= document["cycle_index"] <= 8
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_CODEX_QUALIFICATION_INVALID"
        )
    _digest(
        document.get("source_qualification_v2_digest"),
        "V31_SUCCESSOR_CODEX_SOURCE_QUALIFICATION_DIGEST_INVALID",
    )
    return supplied


def build_raw_first_failure_probe_v2(
    *, tested_at: str, clock_policy_digest: str, case_results: Mapping[str, str]
) -> dict[str, Any]:
    _time(tested_at, "V31_SUCCESSOR_RAW_FIRST_TEST_TIME_INVALID")
    if (
        not isinstance(case_results, Mapping)
        or tuple(sorted(case_results)) != RAW_FIRST_FAILURE_CASES
        or any(case_results[name] != "PASS" for name in RAW_FIRST_FAILURE_CASES)
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_RAW_FIRST_CASES_INCOMPLETE"
        )
    return self_digest(
        {
            "schema_id": RAW_FIRST_PROBE_SCHEMA_ID,
            "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
            "tested_at": tested_at,
            "clock_policy_digest": _digest(
                clock_policy_digest,
                "V31_SUCCESSOR_CLOCK_POLICY_DIGEST_INVALID",
            ),
            "case_results": dict(sorted(case_results.items())),
            "test_origin": "LOCAL_FAILURE_INJECTION_NONPRODUCTION",
            "adapter_call_limit_per_cycle": 1,
            "retry_allowed": False,
            "raw_capture_precedes_parse": True,
            "no_refetch_recovery": True,
            "authority_boundary": dict(_BOUNDARY),
        },
        RAW_FIRST_PROBE_DIGEST_FIELD,
    )


def verify_raw_first_failure_probe_v2(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, RAW_FIRST_PROBE_DIGEST_FIELD)
        rebuilt = build_raw_first_failure_probe_v2(
            tested_at=document["tested_at"],
            clock_policy_digest=document["clock_policy_digest"],
            case_results=document["case_results"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorQualificationV2Error):
            raise
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_RAW_FIRST_PROBE_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[RAW_FIRST_PROBE_DIGEST_FIELD]:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_RAW_FIRST_PROBE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_supervisor_gate_probe_v2(
    *, tested_at: str, case_results: Mapping[str, str]
) -> dict[str, Any]:
    _time(tested_at, "V31_SUCCESSOR_SUPERVISOR_TEST_TIME_INVALID")
    if (
        not isinstance(case_results, Mapping)
        or tuple(sorted(case_results)) != SUPERVISOR_GATE_CASES
        or any(case_results[name] != "PASS" for name in SUPERVISOR_GATE_CASES)
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SUPERVISOR_CASES_INCOMPLETE"
        )
    return self_digest(
        {
            "schema_id": SUPERVISOR_PROBE_SCHEMA_ID,
            "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
            "tested_at": tested_at,
            "case_results": dict(sorted(case_results.items())),
            "test_origin": "LOCAL_STATE_MACHINE_FAILURE_INJECTION",
            "new_cycle_requires_supervisor_permit": True,
            "accepted_cycle_requires_commit_intent": True,
            "next_cycle_requires_previous_durable_outcome": True,
            "failed_monitor_is_terminal_for_run": True,
            "authority_boundary": dict(_BOUNDARY),
        },
        SUPERVISOR_PROBE_DIGEST_FIELD,
    )


def verify_supervisor_gate_probe_v2(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, SUPERVISOR_PROBE_DIGEST_FIELD)
        rebuilt = build_supervisor_gate_probe_v2(
            tested_at=document["tested_at"],
            case_results=document["case_results"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorQualificationV2Error):
            raise
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SUPERVISOR_PROBE_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[SUPERVISOR_PROBE_DIGEST_FIELD]:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_SUPERVISOR_PROBE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_absolute_monitor_policy_v2(
    *, clock_policy: Mapping[str, Any]
) -> dict[str, Any]:
    clock_digest = verify_outcome_clock_policy(clock_policy)
    return self_digest(
        {
            "schema_id": MONITOR_POLICY_SCHEMA_ID,
            "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
            "clock_policy_digest": clock_digest,
            "schedule_basis": "ACCEPTED_STATE_DECISION_AT_ABSOLUTE_UTC",
            "outcome_horizon_seconds": MONITOR_OUTCOME_HORIZON_SECONDS,
            "outcome_grace_seconds": MONITOR_OUTCOME_GRACE_SECONDS,
            "outcome_not_before_formula": "decision_at+3600s",
            "expires_at_formula": "outcome_not_before+900s",
            "endpoint": MONITOR_ENDPOINT,
            "request_method": "GET",
            "attempt_limit_per_cycle": 1,
            "retry_allowed": False,
            "same_wake_next_cycle_allowed": False,
            "state_change_boundaries_per_wake": 1,
            "capture_order": [
                "ATTEMPT_RESERVED",
                "RAW_RESPONSE_COMMITTED",
                "RAW_READBACK_VERIFIED",
                "PARSE_RECEIPT_COMMITTED",
                "OUTCOME_RESOLUTION_BOUND",
            ],
            "transport_failure_policy": "TYPED_FAILURE_BINDING_NO_REFETCH",
            "late_or_invalid_policy": "FAIL_CLOSED_NO_RETRY",
            "authority_boundary": dict(_BOUNDARY),
        },
        MONITOR_POLICY_DIGEST_FIELD,
    )


def verify_absolute_monitor_policy_v2(
    document: Mapping[str, Any], *, clock_policy: Mapping[str, Any]
) -> str:
    try:
        supplied = verify_self_digest(document, MONITOR_POLICY_DIGEST_FIELD)
        rebuilt = build_absolute_monitor_policy_v2(clock_policy=clock_policy)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorQualificationV2Error):
            raise
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_POLICY_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[MONITOR_POLICY_DIGEST_FIELD]:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_POLICY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_successor_monitor_qualification_v2(
    *,
    run_id: str,
    predecessor_run_id: str,
    authority_digest: str,
    authority_binding: Mapping[str, Any],
    authority_recorded_at: str,
    qualified_at: str,
    clock_policy: Mapping[str, Any],
    clock_policy_binding: Mapping[str, Any],
    raw_first_probe: Mapping[str, Any],
    raw_first_probe_binding: Mapping[str, Any],
    supervisor_probe: Mapping[str, Any],
    supervisor_probe_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Qualify monitor ordering and durability, not any future outcome."""

    run, predecessor = _assert_successor_identity(
        run_id=run_id, predecessor_run_id=predecessor_run_id
    )
    authority_ref = _authority_binding(
        authority_binding, authority_digest=authority_digest
    )
    authority_time = _time(
        authority_recorded_at, "V31_SUCCESSOR_AUTHORITY_TIME_INVALID"
    )
    qualified = _time(
        qualified_at, "V31_SUCCESSOR_MONITOR_QUALIFIED_AT_INVALID"
    )
    clock_digest = verify_outcome_clock_policy(clock_policy)
    raw_probe_digest = verify_raw_first_failure_probe_v2(raw_first_probe)
    supervisor_probe_digest = verify_supervisor_gate_probe_v2(
        supervisor_probe
    )
    raw_tested_at = _time(
        raw_first_probe.get("tested_at"),
        "V31_SUCCESSOR_RAW_FIRST_TEST_TIME_INVALID",
    )
    supervisor_tested_at = _time(
        supervisor_probe.get("tested_at"),
        "V31_SUCCESSOR_SUPERVISOR_TEST_TIME_INVALID",
    )
    if (
        raw_first_probe.get("clock_policy_digest") != clock_digest
        or qualified < authority_time
        or raw_tested_at < authority_time
        or supervisor_tested_at < authority_time
        or qualified < raw_tested_at
        or qualified < supervisor_tested_at
    ):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_CROSS_BINDING_INVALID"
        )
    binding_specs = {
        "clock_policy": (
            clock_policy_binding,
            "clock_policy_digest",
            clock_digest,
        ),
        "raw_first_probe": (
            raw_first_probe_binding,
            RAW_FIRST_PROBE_DIGEST_FIELD,
            raw_probe_digest,
        ),
        "supervisor_probe": (
            supervisor_probe_binding,
            SUPERVISOR_PROBE_DIGEST_FIELD,
            supervisor_probe_digest,
        ),
    }
    bindings: dict[str, dict[str, str]] = {}
    for name, (raw, digest_field, semantic_digest) in binding_specs.items():
        binding = _binding(
            raw, "V31_SUCCESSOR_MONITOR_ARTIFACT_BINDING_INVALID"
        )
        if (
            binding["digest_field"] != digest_field
            or binding["semantic_digest"] != semantic_digest
        ):
            raise V31SuccessorQualificationV2Error(
                "V31_SUCCESSOR_MONITOR_ARTIFACT_BINDING_INVALID"
            )
        _assert_nonfixture_ref(
            binding["relative_ref"],
            "V31_SUCCESSOR_MONITOR_FIXTURE_EVIDENCE_FORBIDDEN",
        )
        bindings[name] = binding
    monitor_policy = build_absolute_monitor_policy_v2(
        clock_policy=clock_policy
    )
    document = {
        "schema_id": MONITOR_QUALIFICATION_SCHEMA_ID,
        "schema_version": SUCCESSOR_QUALIFICATION_SCHEMA_VERSION,
        "run_id": run,
        "predecessor_run_id": predecessor,
        "authority_digest": authority_digest,
        "authority_binding": authority_ref,
        "authority_recorded_at": authority_recorded_at,
        "qualified_at": qualified_at,
        "clock_policy": dict(clock_policy),
        "monitor_policy": monitor_policy,
        "raw_first_probe": dict(raw_first_probe),
        "supervisor_probe": dict(supervisor_probe),
        "artifact_bindings": bindings,
        "qualification_summary": {
            "verdict": "QUALIFIED_FOR_SUCCESSOR_MONITOR_RUNTIME_ONLY",
            "clock_policy_bound": True,
            "raw_first_failure_injection_passed": True,
            "supervisor_gate_failure_injection_passed": True,
            "absolute_schedule_enforced": True,
            "one_attempt_no_retry_enforced": True,
            "one_state_change_boundary_enforced": True,
        },
        "limitations": [
            "LOCAL_RUNTIME_DURABILITY_AND_ORDERING_QUALIFICATION_ONLY",
            "DOES_NOT_PROVE_FUTURE_NETWORK_OR_PROVIDER_AVAILABILITY",
            "DOES_NOT_READ_OR_PREDICT_ANY_FUTURE_OUTCOME",
            "DOES_NOT_PROVE_PREDICTION_OR_PROFITABILITY",
        ],
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, MONITOR_QUALIFICATION_DIGEST_FIELD)


def verify_successor_monitor_qualification_v2(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_QUALIFICATION_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, MONITOR_QUALIFICATION_DIGEST_FIELD
        )
        rebuilt = build_successor_monitor_qualification_v2(
            run_id=document["run_id"],
            predecessor_run_id=document["predecessor_run_id"],
            authority_digest=document["authority_digest"],
            authority_binding=document["authority_binding"],
            authority_recorded_at=document["authority_recorded_at"],
            qualified_at=document["qualified_at"],
            clock_policy=document["clock_policy"],
            clock_policy_binding=document["artifact_bindings"][
                "clock_policy"
            ],
            raw_first_probe=document["raw_first_probe"],
            raw_first_probe_binding=document["artifact_bindings"][
                "raw_first_probe"
            ],
            supervisor_probe=document["supervisor_probe"],
            supervisor_probe_binding=document["artifact_bindings"][
                "supervisor_probe"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorQualificationV2Error):
            raise
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_QUALIFICATION_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[MONITOR_QUALIFICATION_DIGEST_FIELD]:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_MONITOR_QUALIFICATION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def qualification_summary_v2(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical, non-inflated user-facing qualification summary."""

    schema = document.get("schema_id") if isinstance(document, Mapping) else None
    if schema == SOURCE_QUALIFICATION_SCHEMA_ID:
        digest = verify_successor_public_source_qualification_v2(document)
        digest_field = SOURCE_QUALIFICATION_DIGEST_FIELD
    elif schema == CODEX_QUALIFICATION_SCHEMA_ID:
        digest = verify_successor_codex_durable_qualification_v2(document)
        digest_field = CODEX_QUALIFICATION_DIGEST_FIELD
    elif schema == MONITOR_QUALIFICATION_SCHEMA_ID:
        digest = verify_successor_monitor_qualification_v2(document)
        digest_field = MONITOR_QUALIFICATION_DIGEST_FIELD
    else:
        raise V31SuccessorQualificationV2Error(
            "V31_SUCCESSOR_QUALIFICATION_SCHEMA_UNKNOWN"
        )
    return {
        "schema_id": schema,
        "run_id": document["run_id"],
        "qualified_at": document["qualified_at"],
        "verdict": document["qualification_summary"]["verdict"],
        "digest_field": digest_field,
        "semantic_digest": digest,
        "limitations": list(document["limitations"]),
        "prediction_claim": False,
        "profitability_claim": False,
        "execution_authority": "NONE_LOCAL_SIMULATION",
    }


__all__ = [
    "CODEX_QUALIFICATION_DIGEST_FIELD",
    "CODEX_QUALIFICATION_SCHEMA_ID",
    "MONITOR_POLICY_DIGEST_FIELD",
    "MONITOR_QUALIFICATION_DIGEST_FIELD",
    "MONITOR_QUALIFICATION_SCHEMA_ID",
    "RAW_FIRST_FAILURE_CASES",
    "RAW_FIRST_PROBE_DIGEST_FIELD",
    "SOURCE_QUALIFICATION_DIGEST_FIELD",
    "SOURCE_QUALIFICATION_SCHEMA_ID",
    "SUCCESSOR_QUALIFICATION_SCHEMA_VERSION",
    "SUPERVISOR_GATE_CASES",
    "SUPERVISOR_PROBE_DIGEST_FIELD",
    "V31SuccessorQualificationV2Error",
    "build_absolute_monitor_policy_v2",
    "build_raw_first_failure_probe_v2",
    "build_successor_codex_durable_qualification_v2",
    "build_successor_monitor_qualification_v2",
    "build_successor_public_source_qualification_v2",
    "build_supervisor_gate_probe_v2",
    "qualification_summary_v2",
    "verify_absolute_monitor_policy_v2",
    "verify_raw_first_failure_probe_v2",
    "verify_successor_codex_durable_qualification_v2",
    "verify_successor_monitor_qualification_v2",
    "verify_successor_public_source_qualification_v2",
    "verify_supervisor_gate_probe_v2",
]
