"""Concrete, recoverable V3.2 analysis lane for the local Supervisor.

The lane deliberately owns no model and never manufactures an Agent answer.
It advances the already-frozen V3.2 contracts from durable state, one logical
substage per call.  Proposal and Selection stop at the current-root mailbox
until an external Codex delivery has been claimed, submitted, and sealed.

The source collector, clocks, market stores, mailbox, outcome store, and the
small amount of run-specific proposal material are injected.  All financial,
PIT, graph, Agent, continuity, shadow, commit, and acceptance semantics are
replayed by their existing owning contracts; this adapter only composes them.
There is no account, credential, order, fill, position, portfolio mutation, or
PnL interface in this module.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Mapping, Protocol, Sequence
import weakref

from ..application.v32_action_plan_continuity import (
    compose_v32_action_plan_continuity_v1,
    verify_v32_action_plan_continuity_v1,
)
from ..application.v32_agent_market_graph_view import (
    build_v32_agent_market_graph_view_v1,
    verify_v32_agent_market_graph_view_v1,
)
from ..application.v32_agent_semantic_compiler import (
    compile_v32_proposal_delivery_v1,
    compile_v32_selection_delivery_v1,
    verify_v32_proposal_semantic_compile_receipt_v1,
    verify_v32_proposal_semantic_output_v1,
    verify_v32_selection_semantic_compile_receipt_v1,
    verify_v32_selection_semantic_output_v1,
)
from ..application.v32_authorized_revision_orchestration import (
    verify_v32_authorized_revision_cycle_registry_v1,
)
from ..application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
    verify_durable_v32_cycle_source_admission,
)
from ..application.v32_cycle_acceptance import (
    DIGEST_FIELD as ANALYSIS_ACCEPTANCE_DIGEST_FIELD,
)
from ..application.v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD as SOURCE_REPLAY_DIGEST_FIELD,
    compose_and_persist_v32_durable_source_replay_receipt,
    durable_source_replay_receipt_ref,
    verify_durable_v32_source_replay_receipt,
)
from ..application.v32_dynamic_state_continuity import (
    build_v32_verified_pit_evidence_availability_registry_v1,
    compose_v32_dynamic_state_continuity_v1,
    verify_v32_dynamic_state_continuity_v1,
    verify_v32_verified_pit_evidence_availability_registry_v1,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.v32_agent_lifecycle import (
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    COMMIT_ENVELOPE_DIGEST_FIELD,
    PROPOSAL_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_DIGEST_FIELD,
    build_v32_agent_input_context_v1,
    build_v32_selection_canonical_packet_v1,
    build_v32_two_stage_commit_envelope_v1,
    v32_lifecycle_verification_scope_v1,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_v1,
    verify_v32_proposal_canonical_packet_v1,
    verify_v32_selection_canonical_packet_v1,
    verify_v32_two_stage_commit_envelope_v1,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    MAX_SOURCE_AGE_SECONDS,
    SOURCE_ADMISSION_DIGEST_FIELD,
    cycle_source_admission_ref,
    verify_v32_active_authority_projection,
)
from ..domain.v32_dynamic_action_plan import (
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    verify_v32_dynamic_action_plan_v1,
)
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    verify_v32_dynamic_research_state_v1,
)
from ..domain.v32_data_gap_escalation import (
    MANUAL_CAPTURE_STEPS,
    build_v32_data_gap_escalation_v1,
)
from ..domain.v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    verify_v32_outcome_schedule_set,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
)
from ..domain.v32_timeframe_cache import (
    DIGEST_FIELD as TIMEFRAME_DIGEST_FIELD,
    verify_v32_timeframe_invalidation_bindings_v1,
    verify_v32_timeframe_payload_bindings_v1,
    verify_v32_timeframe_production_policy_v1,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_transition_v1,
)
from .v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from .v32_cycle_source_admission_store import LocalV32CycleSourceAdmissionStore
from .v32_dynamic_store import (
    CHECKPOINT_DIGEST_FIELD as RESEARCH_CHECKPOINT_DIGEST_FIELD,
    LocalV32DynamicStore,
    STORE_ROOT as RESEARCH_STORE_ROOT,
    V32DynamicStoreError,
)
from .v32_outcome_tick_store import LocalV32OutcomeTickStore
from .v32_public_market_graph_projection import (
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_REGISTRY_DIGEST_FIELD,
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
)
from .v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    V32RawFirstOkxPublicBundleCollector,
    verify_durable_v32_public_source_qualification,
)
from .v32_public_evidence_verifier import V32InfrastructurePublicEvidenceVerifier
from .v32_shadow_policy_adapter import (
    build_v32_replayable_shadow_decision_bundle_v1,
    verify_v32_replayable_shadow_decision_bundle_v1,
)


STORE_ROOT = "v32-local-analysis-lane-v1"
SCHEMA_VERSION = "1.0.0"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
FAILURE_EVIDENCE_SCHEMA_ID = "theory_paper_v32_local_analysis_failure_evidence_v1"
FAILURE_EVIDENCE_DIGEST_FIELD = "local_analysis_failure_evidence_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_FORMAL_LANE_CONSTRUCTION_GUARD = threading.Lock()
_FORMAL_LANE_CONSTRUCTION_REGISTRY: weakref.WeakKeyDictionary[
    object, LocalV32DynamicStore
] = weakref.WeakKeyDictionary()
_PUBLIC_BINDING_FIELDS = (
    "relative_ref",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
)
_COMPLETION_FIELDS = frozenset(
    {
        "permit_digest",
        "analysis_acceptance_digest",
        "shadow_decision_bundle_digest",
        "durable_source_replay_receipt_digest",
        "public_market_analysis_bundle_digest",
        "public_market_graph_projection_digest",
        "graph_delta_digest",
        "graph_dependency_registry_digest",
        "public_market_analysis_bundle",
        "public_market_graph_projection",
        "previous_public_market_graph_projection",
        "graph_dependency_registry",
        "durable_source_replay_receipt",
        "analysis_acceptance",
        "shadow_decision_bundle",
        "completion",
    }
)
_FAILURE_FIELDS = frozenset(
    {
        "permit_digest",
        "failure_code",
        "failure_summary",
        "failure_evidence_digest",
        "occurred_at",
    }
)
_FAILURE_EVIDENCE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "permit_digest",
        "failure_class",
        "failure_message",
        "research_checkpoint_digest",
        "outcome_checkpoint_digest",
        "mailbox_checkpoint_digest",
        "occurred_at",
        "retry_allowed",
        "resume_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        FAILURE_EVIDENCE_DIGEST_FIELD,
    }
)
_REVISION_MATERIAL_FIELDS = frozenset(
    {
        "cycle_registry",
        "proposal_context",
        "selection_context",
        "unknown_tracks",
        "data_gap_entries",
        "manual_evidence_entries",
        "environment_conformance",
        "recovery_traces",
        "revision_input_state",
    }
)


class V32LocalAnalysisLaneError(ValueError):
    """The concrete local analysis lane failed closed."""


@contextmanager
def _formally_constructing_local_v32_analysis_lane(
    *, owner: object, store: LocalV32DynamicStore
):
    """Temporarily attest that ``owner`` passed this module's constructor.

    The marker exists only around the Store claim.  It is a trusted-process
    component boundary, not protection against malicious monkeypatching or
    Python private-memory introspection.
    """

    if type(owner) is not LocalV32AnalysisLane:
        raise V32LocalAnalysisLaneError(
            "V32_LOCAL_ANALYSIS_CONSTRUCTION_OWNER_INVALID"
        )
    with _FORMAL_LANE_CONSTRUCTION_GUARD:
        if owner in _FORMAL_LANE_CONSTRUCTION_REGISTRY:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_CONSTRUCTION_ALREADY_REGISTERED"
            )
        _FORMAL_LANE_CONSTRUCTION_REGISTRY[owner] = store
    try:
        yield
    finally:
        with _FORMAL_LANE_CONSTRUCTION_GUARD:
            if _FORMAL_LANE_CONSTRUCTION_REGISTRY.get(owner) is store:
                del _FORMAL_LANE_CONSTRUCTION_REGISTRY[owner]


def _is_formally_constructing_local_v32_analysis_lane(
    *, owner: object, store: LocalV32DynamicStore
) -> bool:
    """Return whether the exact Lane is inside its verified claim boundary."""

    with _FORMAL_LANE_CONSTRUCTION_GUARD:
        return (
            type(owner) is LocalV32AnalysisLane
            and _FORMAL_LANE_CONSTRUCTION_REGISTRY.get(owner) is store
        )


class V32AnalysisClockPort(Protocol):
    """Return one canonical UTC timestamp for a named deterministic boundary."""

    def timestamp(
        self, *, boundary: str, permit: Mapping[str, Any]
    ) -> str: ...


class V32AnalysisMaterialPort(Protocol):
    """Run-specific semantic material that is not a market or model adapter.

    Implementations provide frozen support documents and deterministic build
    choices.  They cannot submit Agent output; Proposal and Selection always
    arrive through :class:`LocalV32CurrentRootAgentMailbox`.
    """

    def build_timeframe_context(
        self,
        *,
        permit: Mapping[str, Any],
        public_market_analysis_bundle: Mapping[str, Any],
        previous_timeframe_context: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]: ...

    def build_proposal_packet(
        self,
        *,
        permit: Mapping[str, Any],
        active_authority_projection: Mapping[str, Any],
        current_artifacts: Mapping[str, Mapping[str, Any]],
        current_bindings: Mapping[str, Mapping[str, Any]],
        previous_artifacts: Mapping[str, Mapping[str, Any] | None],
        previous_bindings: Mapping[str, Mapping[str, Any] | None],
        matured_outcome_receipts: Sequence[Mapping[str, Any]],
        matured_outcome_receipt_bindings: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...

    def lossless_context_package(
        self,
        *,
        stage: str,
        canonical_packet: Mapping[str, Any],
        canonical_packet_binding: Mapping[str, Any],
    ) -> Mapping[str, Any] | None: ...

    def build_authorized_revision_cycle_registry(
        self,
        *,
        permit: Mapping[str, Any],
        proposal_packet: Mapping[str, Any],
        proposal_context_package: Mapping[str, Any] | None,
        selection_packet: Mapping[str, Any],
        selection_context_package: Mapping[str, Any] | None,
        required_data_gap_escalations: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Return the registry and all seven inputs required for full replay."""
        ...

    def build_outcome_schedule_set(
        self,
        *,
        permit: Mapping[str, Any],
        final_dynamic_action_plan: Mapping[str, Any],
        proposal_packet: Mapping[str, Any],
        decision_sealed_at: str,
    ) -> Mapping[str, Any]: ...


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32LocalAnalysisLaneError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32LocalAnalysisLaneError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32LocalAnalysisLaneError(code) from exc
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat().replace(
        "+00:00", "Z"
    ) != text:
        raise V32LocalAnalysisLaneError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _public_binding(binding: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(binding, Mapping) or any(
        not isinstance(binding.get(field), str) or not binding[field]
        for field in _PUBLIC_BINDING_FIELDS
    ):
        raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_BINDING_INVALID")
    return {field: str(binding[field]) for field in _PUBLIC_BINDING_FIELDS}


def build_v32_required_data_gap_escalations_v1(
    *,
    public_market_analysis_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Map every objective UNKNOWN in one source bundle to an exact escalation.

    Coverage includes both a failed/absent source component and every typed
    objective datum derived as UNKNOWN from that component.  Axis-level UNKNOWN
    rows are intentionally not substitutes for these field-level records.
    """

    verifier = V32InfrastructurePublicEvidenceVerifier()
    verifier.verify_public_market_analysis_bundle(public_market_analysis_bundle)
    run_id = _text(
        public_market_analysis_bundle.get("run_id"),
        "V32_LOCAL_ANALYSIS_DATA_GAP_BUNDLE_INVALID",
    )
    cycle = public_market_analysis_bundle.get("cycle_index")
    if isinstance(cycle, bool) or not isinstance(cycle, int):
        raise V32LocalAnalysisLaneError(
            "V32_LOCAL_ANALYSIS_DATA_GAP_BUNDLE_INVALID"
        )
    requests = {
        row["component_id"]: row
        for row in public_market_analysis_bundle["request_raw_bindings"]
    }
    specs: list[tuple[str, str, Mapping[str, Any], str]] = []
    for component_id, request in sorted(requests.items()):
        if request["status"] == "UNKNOWN":
            specs.append(
                (
                    f"source-component-{component_id.lower().replace('_', '-')}",
                    f"request_raw_bindings.{component_id}",
                    request,
                    f"objective source component {component_id} is unavailable",
                )
            )
    for datum in sorted(
        public_market_analysis_bundle["datums"], key=lambda row: row["datum_id"]
    ):
        if datum["status"] != "UNKNOWN":
            continue
        component_id = datum["source_component_id"]
        request = requests.get(component_id)
        if request is None or request["status"] != "UNKNOWN":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DATA_GAP_SOURCE_LINK_INVALID"
            )
        specs.append(
            (
                f"datum-{datum['datum_id']}",
                f"datums.{datum['datum_id']}",
                request,
                f"objective datum {datum['metric_kind']} is unavailable",
            )
        )
    result: list[dict[str, Any]] = []
    qualification_id = public_market_analysis_bundle["qualification_id"]
    for suffix, field_path, request, impact in specs:
        error_code = request.get("error_code") or "PUBLIC_OBJECTIVE_FIELD_UNAVAILABLE"
        error_digest = canonical_digest(
            {
                "qualification_id": qualification_id,
                "component_id": request["component_id"],
                "field_path": field_path,
                "error_code": error_code,
                "status": "UNKNOWN",
            }
        )
        result.append(
            build_v32_data_gap_escalation_v1(
                gap_id=f"gap:{qualification_id}:{suffix}",
                run_id=run_id,
                cycle_index=cycle,
                request={
                    "request_id": request["request_id"],
                    "source_id": "okx-official-public",
                    "method": request["method"],
                    "endpoint": request["path"],
                    "field_path": field_path,
                },
                requested_at=request["request_started_at"],
                failed_at=request["response_received_at"],
                error_code=error_code,
                error_message_digest=error_digest,
                impact=impact,
                claim_ceiling=(
                    f"{field_path} remains UNKNOWN; no objective directional, "
                    "liquidity-owner, or execution-quality claim"
                ),
                allowed_official_public_sources=[
                    {
                        "source_id": "okx-official-public",
                        "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
                        "url": "https://www.okx.com/docs-v5/en/",
                    }
                ],
            )
        )
    okx_source = {
        "source_id": "okx-official-public",
        "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
        "url": "https://www.okx.com/docs-v5/en/",
    }
    event_sources = [
        {
            "source_id": "cftc-official-releases",
            "source_kind": "OFFICIAL_REGULATOR",
            "url": "https://www.cftc.gov/PressRoom/PressReleases",
        },
        {
            "source_id": "federal-reserve-official-news",
            "source_kind": "OFFICIAL_CENTRAL_BANK",
            "url": "https://www.federalreserve.gov/newsevents.htm",
        },
        {
            "source_id": "sec-official-news",
            "source_kind": "OFFICIAL_REGULATOR",
            "url": "https://www.sec.gov/newsroom",
        },
        {
            "source_id": "treasury-official-press",
            "source_kind": "OFFICIAL_PUBLIC_STATISTICS",
            "url": "https://home.treasury.gov/news/press-releases",
        },
    ]
    cross_market_sources = [
        {
            "source_id": "cme-official-market-data",
            "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
            "url": "https://www.cmegroup.com/market-data.html",
        },
        okx_source,
    ]
    attention_sources = [
        {
            "source_id": "okx-official-announcements",
            "source_kind": "OFFICIAL_EXCHANGE_PUBLIC",
            "url": "https://www.okx.com/help/section/announcements-latest-announcements",
        }
    ]
    for axis in sorted(
        public_market_analysis_bundle["axis_source_evidence"],
        key=lambda row: row["axis_id"],
    ):
        if axis["status"] != "UNKNOWN":
            continue
        axis_id = axis["axis_id"]
        reason = axis["reason_code"]
        component_ids = sorted(axis["source_component_ids"])
        source_request = next(
            (requests[item] for item in component_ids if item in requests), None
        )
        if axis_id == "EVENT_AND_NARRATIVE_REACTION":
            sources = event_sources
        elif axis_id == "ATTENTION_AND_AUDIENCE_RESPONSE":
            sources = attention_sources
        elif axis_id == "CROSS_MARKET_RISK_APPETITE_AND_REGIME":
            sources = cross_market_sources
        else:
            sources = [okx_source]
        error_code = (
            "MANUAL_PUBLIC_SOURCE_NOT_PREQUALIFIED"
            if axis_id == "ATTENTION_AND_AUDIENCE_RESPONSE"
            else reason
        )
        field_path = f"axis_source_evidence.{axis_id}"
        requested_at = (
            public_market_analysis_bundle["available_at"]
            if source_request is None
            else source_request["request_started_at"]
        )
        failed_at = (
            public_market_analysis_bundle["available_at"]
            if source_request is None
            else source_request["response_received_at"]
        )
        result.append(
            build_v32_data_gap_escalation_v1(
                gap_id=f"gap:{qualification_id}:axis-{axis_id.lower().replace('_', '-')}",
                run_id=run_id,
                cycle_index=cycle,
                request={
                    "request_id": f"manual-gap:{qualification_id}:{axis_id}",
                    "source_id": sources[0]["source_id"],
                    "method": "GET",
                    "endpoint": (
                        f"/manual-public-evidence/{axis_id.lower()}"
                        if source_request is None
                        else source_request["path"]
                    ),
                    "field_path": field_path,
                },
                requested_at=requested_at,
                failed_at=failed_at,
                error_code=error_code,
                error_message_digest=canonical_digest(
                    {
                        "qualification_id": qualification_id,
                        "axis_id": axis_id,
                        "reason_code": reason,
                        "status": "UNKNOWN",
                        "manual_source_prequalified": False,
                    }
                ),
                impact=(
                    f"objective axis {axis_id} is unavailable because {reason}; "
                    "axis direction cannot be materialized"
                ),
                claim_ceiling=(
                    f"{axis_id} remains UNKNOWN; manual public evidence is only "
                    "eligible for a new future-cycle revision"
                ),
                allowed_official_public_sources=sources,
            )
        )
    result.sort(key=lambda row: row["gap_id"])
    if any(
        row["objective_status"] != "UNKNOWN"
        or row["zero_imputed"] is not False
        or row["manual_capture_steps"] != list(MANUAL_CAPTURE_STEPS)
        or row["future_cycle_readmission_required"] is not True
        or row["historical_cycle_backfill_forbidden"] is not True
        for row in result
    ):
        raise V32LocalAnalysisLaneError(
            "V32_LOCAL_ANALYSIS_DATA_GAP_POLICY_INVALID"
        )
    return result


class LocalV32AnalysisLane:
    """Concrete ``V32AnalysisLanePort`` backed by the existing V3.2 stores."""

    def __init__(
        self,
        *,
        dynamic_store: LocalV32DynamicStore,
        outcome_store: LocalV32OutcomeTickStore,
        source_store: LocalV32CycleSourceAdmissionStore,
        admitted_source_store: LocalV32CycleSourceAdmissionStore,
        source_collector: V32RawFirstOkxPublicBundleCollector,
        mailbox: LocalV32CurrentRootAgentMailbox,
        active_authority_projection: Mapping[str, Any],
        qualification_id_factory: Any,
        clock: V32AnalysisClockPort,
        material_port: V32AnalysisMaterialPort,
        public_evidence_verifier: Any | None = None,
    ) -> None:
        if not isinstance(dynamic_store, LocalV32DynamicStore):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_STORE_INVALID")
        if not isinstance(outcome_store, LocalV32OutcomeTickStore):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_OUTCOME_STORE_INVALID")
        if not isinstance(source_store, LocalV32CycleSourceAdmissionStore) or not isinstance(
            admitted_source_store, LocalV32CycleSourceAdmissionStore
        ):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_SOURCE_STORE_INVALID")
        if not isinstance(mailbox, LocalV32CurrentRootAgentMailbox):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_MAILBOX_INVALID")
        if not callable(getattr(source_collector, "collect_and_qualify", None)):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SOURCE_COLLECTOR_INVALID"
            )
        if not callable(qualification_id_factory):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_QUALIFICATION_ID_FACTORY_INVALID"
            )
        if not callable(getattr(clock, "timestamp", None)):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_CLOCK_INVALID")
        required_material_methods = (
            "build_timeframe_context",
            "build_proposal_packet",
            "lossless_context_package",
            "build_authorized_revision_cycle_registry",
            "build_outcome_schedule_set",
        )
        if any(
            not callable(getattr(material_port, method_name, None))
            for method_name in required_material_methods
        ):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_MATERIAL_PORT_INVALID")
        public_verifier = (
            public_evidence_verifier
            if public_evidence_verifier is not None
            else V32InfrastructurePublicEvidenceVerifier()
        )
        required_public_verifier_methods = (
            "verification_scope",
            "verify_graph_dependency_registry",
            "verify_public_market_analysis_bundle",
            "verify_public_market_graph_projection",
        )
        if any(
            not callable(getattr(public_verifier, method_name, None))
            for method_name in required_public_verifier_methods
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PUBLIC_VERIFIER_INVALID"
            )
        if not isinstance(active_authority_projection, Mapping):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_AUTHORITY_INVALID")
        authority = deepcopy(dict(active_authority_projection))
        try:
            verify_v32_active_authority_projection(authority)
        except (KeyError, TypeError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_AUTHORITY_INVALID"
            ) from exc
        run_root = Path(dynamic_store.run_root).absolute()
        if (
            not run_root.is_dir()
            or run_root.is_symlink()
            or run_root.resolve(strict=True)
            != Path(dynamic_store.run_root).resolve(strict=True)
        ):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_ROOT_INVALID")
        self._dynamic = dynamic_store
        self._outcome = outcome_store
        self._source = source_store
        self._admitted_source = admitted_source_store
        self._collector = source_collector
        self._mailbox = mailbox
        self._authority = authority
        self._qualification_id_factory = qualification_id_factory
        self._clock = clock
        self._material = material_port
        self._public = public_verifier
        self.run_root = run_root
        self._physical_root = self.run_root.resolve(strict=True)
        # Claim only after every constructor input/root check succeeds.  A
        # rejected partial lane must not consume the store's sole writer.
        try:
            with _formally_constructing_local_v32_analysis_lane(
                owner=self, store=dynamic_store
            ):
                self._artifact_writer = (
                    dynamic_store._claim_local_analysis_lane_artifact_writer(
                        owner=self
                    )
                )
        except V32DynamicStoreError as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_ARTIFACT_WRITER_UNAVAILABLE"
            ) from exc

    def _safe_path(self, relative_ref: str) -> Path:
        lexical = PurePosixPath(relative_ref)
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
            or not isinstance(relative_ref, str)
            or not relative_ref
            or "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or len(lexical.parts) < 2
            or lexical.parts[0] != STORE_ROOT
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32LocalAnalysisLaneError("V32_LOCAL_ANALYSIS_PATH_INVALID")
        candidate = self.run_root.joinpath(*lexical.parts)
        try:
            candidate.resolve(strict=False).relative_to(self._physical_root)
            current = self.run_root
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32LocalAnalysisLaneError(
                        "V32_LOCAL_ANALYSIS_SYMLINK_FORBIDDEN"
                    )
        except V32LocalAnalysisLaneError:
            raise
        except (OSError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PATH_INVALID"
            ) from exc
        return candidate

    @contextmanager
    def _lock(self):
        path = self._safe_path(f"{STORE_ROOT}/.locks/lane.lock")
        ensure_directory_tree(path.parent)
        key = str(path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(path):
                yield

    def _timestamp(self, boundary: str, permit: Mapping[str, Any]) -> str:
        try:
            value = self._clock.timestamp(boundary=boundary, permit=permit)
        except Exception as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_CLOCK_FAILED"
            ) from exc
        return _time(value, "V32_LOCAL_ANALYSIS_CLOCK_INVALID")

    @staticmethod
    def _permit_identity(permit: Mapping[str, Any]) -> tuple[str, str, int]:
        try:
            permit_digest = verify_self_digest(permit, PERMIT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PERMIT_INVALID"
            ) from exc
        run_id = _text(permit.get("run_id"), "V32_LOCAL_ANALYSIS_PERMIT_INVALID")
        cycle = permit.get("analysis_cycle_index")
        if (
            permit.get("permit_kind") != "ANALYSIS_TICK"
            or permit.get("opened_lane") != "ANALYSIS_LANE"
            or isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or not 1 <= cycle <= 16
            or permit.get("source_collection_transactions_allowed") != 1
            or permit.get("agent_stage_attempt_limits")
            != {"PROPOSAL": 1, "SELECTION": 1}
            or permit.get("future_outcomes_readable") is not False
            or permit.get("source_scope") != SOURCE_SCOPE
            or permit.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or permit.get("executable") is not False
            or permit.get("account_access") is not False
            or permit.get("order_submission") is not False
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PERMIT_BOUNDARY_INVALID"
            )
        return run_id, permit_digest, cycle

    def _validate_supervisor_chain(
        self,
        *,
        permit: Mapping[str, Any],
        before: Mapping[str, Any],
        opened: Mapping[str, Any],
    ) -> None:
        run_id, permit_digest, cycle = self._permit_identity(permit)
        try:
            before_digest = verify_v32_tick_supervisor_checkpoint(before)
            verify_v32_tick_supervisor_checkpoint(opened)
            schedule_sets = self._outcome.load_schedule_sets(run_id=run_id)
            if len(schedule_sets) < cycle - 1:
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_SUPERVISOR_CHAIN_INVALID"
                )
            verify_v32_tick_supervisor_permit(
                permit,
                checkpoint=before,
                schedule_sets=schedule_sets[: cycle - 1],
            )
        except (TypeError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SUPERVISOR_CHAIN_INVALID"
            ) from exc
        if (
            before_digest
            != permit.get("supervisor_checkpoint_digest_before_permit")
            or opened.get("predecessor_checkpoint_digest") != before_digest
            or opened.get("active_permit_digest") != permit_digest
            or opened.get("active_permit_kind") != "ANALYSIS_TICK"
            or opened.get("status") != "ANALYSIS_TICK_OPEN"
            or opened.get("run_id") != permit.get("run_id")
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SUPERVISOR_CHAIN_INVALID"
            )
        authority_projection_digest = verify_v32_active_authority_projection(
            self._authority
        )
        if (
            self._authority.get("authorized_run_id") != permit.get("run_id")
            or authority_projection_digest
            != self._authority.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
            or self._authority.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
            != permit.get("active_authority_digest")
            or self._authority.get("experiment_contract_digest")
            != permit.get("experiment_contract_digest")
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_AUTHORITY_BINDING_INVALID"
            )

    @staticmethod
    def _binding_for(
        checkpoint: Mapping[str, Any], *, cycle: int, role: str
    ) -> Mapping[str, Any] | None:
        matches = [
            row
            for row in checkpoint.get("artifact_bindings", ())
            if row.get("cycle_index") == cycle and row.get("role") == role
        ]
        if len(matches) > 1:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DUPLICATE_ROLE_BINDING"
            )
        return matches[0] if matches else None

    def _document(
        self, checkpoint: Mapping[str, Any], *, cycle: int, role: str
    ) -> Mapping[str, Any] | None:
        binding = self._binding_for(checkpoint, cycle=cycle, role=role)
        return None if binding is None else self._dynamic.load_artifact(binding)

    def _role_ref(self, *, cycle: int, role: str) -> str:
        return (
            f"{RESEARCH_STORE_ROOT}/cycles/{cycle:04d}/analysis-lane/"
            f"{role}.json"
        )

    def _persist_role(
        self,
        *,
        run_id: str,
        cycle: int,
        role: str,
        document: Mapping[str, Any],
        recorded_at: str,
    ) -> Mapping[str, Any]:
        checkpoint = self._dynamic.load_checkpoint(run_id=run_id)
        existing = self._binding_for(checkpoint, cycle=cycle, role=role)
        if existing is not None:
            if self._dynamic.load_artifact(existing) != dict(document):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_ROLE_WRITE_ONCE_CONFLICT"
                )
            return checkpoint
        return self._artifact_writer.persist_verified_artifact(
            run_id=run_id,
            cycle_index=cycle,
            role=role,
            relative_ref=self._role_ref(cycle=cycle, role=role),
            document=document,
            expected_checkpoint_digest=checkpoint[RESEARCH_CHECKPOINT_DIGEST_FIELD],
            recorded_at=recorded_at,
        )

    @staticmethod
    def _advance(status: str, digest: str) -> Mapping[str, str]:
        return {
            "advance_status": status,
            "durable_transition_digest": _digest(
                digest, "V32_LOCAL_ANALYSIS_TRANSITION_DIGEST_INVALID"
            ),
        }

    def _qualification_id(self, *, run_id: str, cycle: int) -> str:
        try:
            value = self._qualification_id_factory(
                run_id=run_id, cycle_index=cycle
            )
        except TypeError:
            value = self._qualification_id_factory(run_id, cycle)
        return _text(value, "V32_LOCAL_ANALYSIS_QUALIFICATION_ID_INVALID")

    def _qualified_source(
        self, *, run_id: str, cycle: int
    ) -> Any | None:
        qualification_id = self._qualification_id(run_id=run_id, cycle=cycle)
        try:
            return verify_durable_v32_public_source_qualification(
                store=self._source,
                qualification_id=qualification_id,
                active_authority=self._authority,
            )
        except Exception:
            from ..domain.v32_cycle_source_admission import qualification_ref

            if self._source.artifact_exists(
                relative_ref=qualification_ref(qualification_id)
            ):
                raise
            return None

    def _admission(self, *, run_id: str, cycle: int) -> Mapping[str, Any] | None:
        try:
            return verify_durable_v32_cycle_source_admission(
                run_store=self._admitted_source,
                run_id=run_id,
                cycle_index=cycle,
                expected_authority_projection_digest=self._authority[
                    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
                ],
                expected_governing_authority_digest=self._authority[
                    GOVERNING_AUTHORITY_DIGEST_FIELD
                ],
                expected_experiment_contract_digest=self._authority[
                    "experiment_contract_digest"
                ],
            )
        except Exception:
            if self._admitted_source.artifact_exists(
                relative_ref=cycle_source_admission_ref(cycle)
            ):
                raise
            return None

    def _source_replay(
        self, *, run_id: str, cycle: int
    ) -> Mapping[str, Any] | None:
        qualification_id = self._qualification_id(run_id=run_id, cycle=cycle)
        try:
            return verify_durable_v32_source_replay_receipt(
                public_evidence_verifier=self._public,
                source_store=self._source,
                run_store=self._admitted_source,
                active_authority=self._authority,
                qualification_id=qualification_id,
                run_id=run_id,
                cycle_index=cycle,
            )
        except Exception:
            if self._admitted_source.artifact_exists(
                relative_ref=durable_source_replay_receipt_ref(cycle)
            ):
                raise
            return None

    def _validate_source_preparation_head(
        self,
        *,
        run_id: str,
        cycle: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> None:
        """Bind pre-permit source work to the exact READY run heads."""

        try:
            verify_v32_tick_supervisor_checkpoint(supervisor_checkpoint)
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            outcome = self._outcome.load_checkpoint(run_id=run_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_HEAD_INVALID"
            ) from exc
        if (
            supervisor_checkpoint.get("run_id") != run_id
            or supervisor_checkpoint.get("status") != "READY"
            or supervisor_checkpoint.get("active_permit_digest") is not None
            or supervisor_checkpoint.get("next_analysis_cycle_index") != cycle
            or dynamic.get("status") != "READY"
            or dynamic.get("next_analysis_cycle_index") != cycle
            or dynamic.get(RESEARCH_CHECKPOINT_DIGEST_FIELD)
            != supervisor_checkpoint.get("current_research_checkpoint_digest")
            or outcome.get("checkpoint_digest")
            != supervisor_checkpoint.get("current_outcome_checkpoint_digest")
            or self._authority.get("authorized_run_id") != run_id
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_HEAD_INVALID"
            )

    def _prior_source_context(
        self,
        *,
        run_id: str,
        cycle: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> dict[str, Any]:
        if cycle == 1:
            return {}
        previous = verify_durable_v32_cycle_source_admission(
            run_store=self._admitted_source,
            run_id=run_id,
            cycle_index=cycle - 1,
            expected_authority_projection_digest=self._authority[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            expected_governing_authority_digest=self._authority[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            expected_experiment_contract_digest=self._authority[
                "experiment_contract_digest"
            ],
        )
        previous_binding = previous["cycle_source_admission_binding"]
        if (
            previous_binding["semantic_digest"]
            != supervisor_checkpoint.get("last_source_admission_digest")
            or previous_binding["physical_sha256"]
            != supervisor_checkpoint.get(
                "last_source_admission_physical_sha256"
            )
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_PRIOR_BINDING_MISMATCH"
            )
        return {
            "previous_cycle_source_admission_binding": previous_binding,
            "prior_snapshot_binding": previous["current_snapshot_binding"],
            "prior_open_interest_datum_digest": previous[
                "current_open_interest_datum_digest"
            ],
            "prior_open_interest_status": previous[
                "current_open_interest_status"
            ],
            "prior_open_interest_zero_imputed": False,
        }

    def _load_prepared_source_unlocked(
        self, *, run_id: str, cycle: int
    ) -> Mapping[str, Any] | None:
        qualification = self._qualified_source(run_id=run_id, cycle=cycle)
        admission = self._admission(run_id=run_id, cycle=cycle)
        replay = self._source_replay(run_id=run_id, cycle=cycle)
        present = tuple(
            item is not None for item in (qualification, admission, replay)
        )
        if present != (True, True, True):
            if present in {
                (False, False, False),
                (True, False, False),
                (True, True, False),
            }:
                return None
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_PREFIX_INVALID"
            )
        assert qualification is not None and admission is not None and replay is not None
        admission_document = admission["cycle_source_admission"]
        replay_document = replay["durable_source_replay_receipt"]
        cutoff = qualification.formal_qualification["decision_time"]
        if (
            admission_document.get("decision_time") != cutoff
            or admission_document.get("source_cutoff_at", cutoff) != cutoff
            or replay_document.get("run_id") != run_id
            or replay_document.get("cycle_index") != cycle
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_BINDING_INVALID"
            )
        return {
            "run_id": run_id,
            "cycle_index": cycle,
            "source_cutoff_at": cutoff,
            "admitted_at": admission_document["admitted_at"],
            "replayed_at": replay_document["replayed_at"],
            "source_qualification_digest": qualification.formal_qualification[
                "formal_source_qualification_digest"
            ],
            "source_admission_digest": admission_document[
                SOURCE_ADMISSION_DIGEST_FIELD
            ],
            "durable_source_replay_receipt_digest": replay_document[
                SOURCE_REPLAY_DIGEST_FIELD
            ],
            "qualification": qualification,
            "admission": admission,
            "replay": replay,
        }

    def load_durable_prepared_source(
        self,
        *,
        run_id: str,
        cycle_index: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Read and fully replay a source prefix; never call a transport."""

        cycle = cycle_index
        if (
            isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or not 1 <= cycle <= 16
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_CYCLE_INVALID"
            )
        with self._lock():
            self._validate_source_preparation_head(
                run_id=run_id,
                cycle=cycle,
                supervisor_checkpoint=supervisor_checkpoint,
            )
            prepared = self._load_prepared_source_unlocked(
                run_id=run_id, cycle=cycle
            )
            if prepared is None:
                return None
            return deepcopy(
                {
                    key: value
                    for key, value in prepared.items()
                    if key not in {"qualification", "admission", "replay"}
                }
            )

    def prepare_cycle_source(
        self,
        *,
        run_id: str,
        cycle_index: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Seal one SOURCE_READY boundary from a bounded write-once prefix.

        Qualification, admission, and replay remain independently durable,
        but they are advanced under one lane owner instead of consuming three
        scheduler wakes.  A crash may leave only a legal prefix; the next call
        resumes that exact prefix without repeating the public collection.
        """

        cycle = cycle_index
        if (
            isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or not 1 <= cycle <= 16
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_SOURCE_PREPARATION_CYCLE_INVALID"
            )
        context = {
            "run_id": run_id,
            "analysis_cycle_index": cycle,
            "source_preparation": True,
        }
        with self._lock():
            self._validate_source_preparation_head(
                run_id=run_id,
                cycle=cycle,
                supervisor_checkpoint=supervisor_checkpoint,
            )
            prepared = self._load_prepared_source_unlocked(
                run_id=run_id, cycle=cycle
            )
            if prepared is not None:
                return {
                    "preparation_status": "SOURCE_READY",
                    "state_changed": False,
                    "internal_append_only_substage_count": 0,
                    "internal_append_only_substages": [],
                    **{
                        key: value
                        for key, value in prepared.items()
                        if key not in {"qualification", "admission", "replay"}
                    },
                }

            completed_substages: list[str] = []
            qualification = self._qualified_source(run_id=run_id, cycle=cycle)
            if qualification is None:
                qualification = self._collector.collect_and_qualify(
                    qualification_id=self._qualification_id(
                        run_id=run_id, cycle=cycle
                    ),
                    run_id=run_id,
                    cycle_index=cycle,
                    active_authority=self._authority,
                )
                completed_substages.append("SOURCE_QUALIFICATION_SEALED")

            admission = self._admission(run_id=run_id, cycle=cycle)
            if admission is None:
                cutoff = qualification.formal_qualification["decision_time"]
                admission = admit_fresh_v32_source_to_cycle(
                    source_store=self._source,
                    run_store=self._admitted_source,
                    active_authority=self._authority,
                    qualification_id=self._qualification_id(
                        run_id=run_id, cycle=cycle
                    ),
                    run_id=run_id,
                    cycle_index=cycle,
                    decision_time=cutoff,
                    admitted_at=self._timestamp("SOURCE_ADMITTED", context),
                    **self._prior_source_context(
                        run_id=run_id,
                        cycle=cycle,
                        supervisor_checkpoint=supervisor_checkpoint,
                    ),
                )
                completed_substages.append("SOURCE_ADMISSION_SEALED")

            replay = self._source_replay(run_id=run_id, cycle=cycle)
            if replay is None:
                replay = compose_and_persist_v32_durable_source_replay_receipt(
                    public_evidence_verifier=self._public,
                    source_store=self._source,
                    run_store=self._admitted_source,
                    active_authority=self._authority,
                    qualification_id=self._qualification_id(
                        run_id=run_id, cycle=cycle
                    ),
                    run_id=run_id,
                    cycle_index=cycle,
                    replayed_at=self._timestamp("SOURCE_REPLAYED", context),
                )
                completed_substages.append("SOURCE_REPLAY_SEALED")

            prepared = self._load_prepared_source_unlocked(
                run_id=run_id, cycle=cycle
            )
            if prepared is None or not completed_substages:
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_SOURCE_PREPARATION_STATE_INVALID"
                )
            projection = {
                key: value
                for key, value in prepared.items()
                if key not in {"qualification", "admission", "replay"}
            }
            return {
                "preparation_status": "SOURCE_READY",
                "state_changed": True,
                "internal_append_only_substage_count": len(
                    completed_substages
                ),
                "internal_append_only_substages": completed_substages,
                "durable_transition_digest": projection[
                    "durable_source_replay_receipt_digest"
                ],
                **projection,
            }

    def _previous(
        self, checkpoint: Mapping[str, Any], *, cycle: int
    ) -> tuple[dict[str, Mapping[str, Any] | None], dict[str, Mapping[str, Any] | None]]:
        roles = {
            "dynamic_state": "dynamic_state",
            "action_plan": "action_plan",
            "timeframe_context": "timeframe_context",
            "public_market_graph_projection": "public_market_graph_projection",
            "pit_evidence_availability_registry": (
                "verified_pit_evidence_availability_registry"
            ),
            "analysis_acceptance": "analysis_acceptance",
            "commit_envelope": "commit_envelope",
        }
        documents: dict[str, Mapping[str, Any] | None] = {}
        bindings: dict[str, Mapping[str, Any] | None] = {}
        for key, role in roles.items():
            binding = (
                None
                if cycle == 1
                else self._binding_for(checkpoint, cycle=cycle - 1, role=role)
            )
            bindings[key] = None if binding is None else _public_binding(binding)
            documents[key] = (
                None if binding is None else self._dynamic.load_artifact(binding)
            )
        if cycle > 1 and any(value is None for value in documents.values()):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PREVIOUS_ACCEPTED_PREFIX_INCOMPLETE"
            )
        return documents, bindings

    def _mailbox_documents(
        self,
        *,
        run_id: str,
        cycle: int,
        stage: str,
        allow_recovery_tail: bool = False,
    ) -> Mapping[str, Any]:
        loader = getattr(self._mailbox, "load_stage_chain", None)
        if callable(loader):
            try:
                return loader(run_id=run_id, cycle_index=cycle, stage=stage)
            except V32CurrentRootAgentMailboxStoreError as exc:
                if not allow_recovery_tail or str(exc) not in {
                    "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE",
                    "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE",
                }:
                    raise
                recovery_loader = getattr(
                    self._mailbox,
                    "load_verified_recovery_stage_view",
                    None,
                )
                if callable(recovery_loader):
                    return recovery_loader(
                        run_id=run_id,
                        cycle_index=cycle,
                        stage=stage,
                    )
                raise
        # Compatibility bridge for the pre-read-port mailbox.  This calls its
        # owning full-chain replay routine; it does not parse mailbox files or
        # weaken any verifier.  Remove when all supported stores expose the
        # public read-only method.
        return self._mailbox._stage_documents(cycle_index=cycle, stage=stage)

    def _context_package(
        self,
        *,
        stage: str,
        packet: Mapping[str, Any],
        packet_binding: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        package = self._material.lossless_context_package(
            stage=stage,
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
        )
        if package is not None and not isinstance(package, Mapping):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_CONTEXT_PACKAGE_INVALID"
            )
        return package

    @staticmethod
    def _context_builder_kwargs(package: Mapping[str, Any] | None) -> dict[str, Any]:
        return {"lossless_context_package": package} if package is not None else {}

    @staticmethod
    def _compiler_package_kwargs(
        *,
        stage: str,
        package: Mapping[str, Any] | None,
        proposal_package: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if stage == "PROPOSAL":
            return (
                {"proposal_lossless_context_package": package}
                if package is not None
                else {}
            )
        result: dict[str, Any] = {}
        if package is not None:
            result["selection_lossless_context_package"] = package
        if proposal_package is not None:
            result["proposal_lossless_context_package"] = proposal_package
        return result

    def _current_material(
        self, checkpoint: Mapping[str, Any], *, cycle: int
    ) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
        roles = {
            "active_authority_projection": "active_authority_projection",
            "cycle_source_admission": "cycle_source_admission",
            "public_market_analysis_bundle": "public_market_analysis_bundle",
            "public_market_graph_projection": "public_market_graph_projection",
            "pit_evidence_registry": "support_pit_registry",
            "graph_dependency_registry": "support_graph_registry",
            "durable_source_replay_receipt": "durable_source_replay",
            "pit_evidence_availability_registry": (
                "verified_pit_evidence_availability_registry"
            ),
            "agent_market_graph_view": "agent_market_graph_view",
            "timeframe_context_state": "timeframe_context",
        }
        documents: dict[str, Mapping[str, Any]] = {}
        bindings: dict[str, Mapping[str, Any]] = {}
        for key, role in roles.items():
            binding = self._binding_for(checkpoint, cycle=cycle, role=role)
            if binding is None:
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_CURRENT_MATERIAL_INCOMPLETE"
                )
            documents[key] = self._dynamic.load_artifact(binding)
            bindings[key] = _public_binding(binding)
        return documents, bindings

    def _persist_and_return(
        self,
        *,
        run_id: str,
        cycle: int,
        role: str,
        document: Mapping[str, Any],
        permit: Mapping[str, Any],
    ) -> Mapping[str, str]:
        checkpoint = self._persist_role(
            run_id=run_id,
            cycle=cycle,
            role=role,
            document=document,
            recorded_at=self._timestamp("RESEARCH_ARTIFACT_RECORDED", permit),
        )
        return self._advance(
            "PENDING", checkpoint[RESEARCH_CHECKPOINT_DIGEST_FIELD]
        )

    def _advance_once(
        self,
        *,
        permit: Mapping[str, Any],
        before: Mapping[str, Any],
        opened: Mapping[str, Any],
    ) -> Mapping[str, str]:
        run_id, permit_digest, cycle = self._permit_identity(permit)
        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        outcome = self._outcome.load_checkpoint(run_id=run_id)

        if dynamic.get("status") == "FAILED" or outcome.get("status") == "FAILED_CLOSED":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_LOWER_STORE_ALREADY_FAILED"
            )
        if dynamic.get("accepted_analysis_cycles", 0) < cycle:
            if dynamic.get("status") == "READY":
                if (
                    dynamic[RESEARCH_CHECKPOINT_DIGEST_FIELD]
                    != permit.get("research_checkpoint_digest")
                    or dynamic.get("next_analysis_cycle_index") != cycle
                    or outcome.get("checkpoint_digest")
                    != permit.get("outcome_checkpoint_digest")
                ):
                    raise V32LocalAnalysisLaneError(
                        "V32_LOCAL_ANALYSIS_PREOPEN_HEAD_MISMATCH"
                    )
                advanced = self._dynamic.open_cycle(
                    run_id=run_id,
                    cycle_index=cycle,
                    expected_checkpoint_digest=dynamic[
                        RESEARCH_CHECKPOINT_DIGEST_FIELD
                    ],
                    opened_at=permit["issued_at"],
                )
                return self._advance(
                    "PENDING", advanced[RESEARCH_CHECKPOINT_DIGEST_FIELD]
                )
            if dynamic.get("status") != "OPEN" or dynamic.get("open_cycle_index") != cycle:
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_RESEARCH_SEQUENCE_INVALID"
                )

            # A process can stop after an immutable role file is fsynced but
            # before its checkpoint binding is replaced.  Recover that exact
            # one-file tail before source, clock, mailbox, or Agent work.  The
            # store verifies role order and cross-document contracts and uses
            # the predecessor checkpoint time, so this wake performs only the
            # missing CAS and cannot invent a replacement artifact.
            recovered_orphan = (
                self._artifact_writer.recover_next_verified_orphan_artifact(
                    run_id=run_id,
                    cycle_index=cycle,
                    expected_checkpoint_digest=dynamic[
                        RESEARCH_CHECKPOINT_DIGEST_FIELD
                    ],
                )
            )
            if recovered_orphan is not None:
                return self._advance(
                    "PENDING",
                    recovered_orphan["checkpoint"][
                        RESEARCH_CHECKPOINT_DIGEST_FIELD
                    ],
                )

            # If the acceptance file was attached on the preceding wake, its
            # own accepted_at is the sealed transition time.  Finish the
            # deterministic commit tail immediately, before replay code asks
            # clocks to rebuild already-bound compiler artifacts.
            acceptance_binding = self._binding_for(
                dynamic, cycle=cycle, role="analysis_acceptance"
            )
            if acceptance_binding is not None:
                acceptance = self._dynamic.load_artifact(acceptance_binding)
                accepted = self._dynamic.recover_persisted_commit_tail(
                    run_id=run_id,
                    cycle_index=cycle,
                    expected_checkpoint_digest=dynamic[
                        RESEARCH_CHECKPOINT_DIGEST_FIELD
                    ],
                    recovered_at=acceptance["accepted_at"],
                )
                return self._advance(
                    "PENDING", accepted[RESEARCH_CHECKPOINT_DIGEST_FIELD]
                )

        # Source qualification/admission/replay is sealed before the permit.
        # The lane only attaches that verified prefix to the open research cycle.
        for role, document in (
            ("supervisor_checkpoint", before),
            ("supervisor_permit", permit),
            ("active_authority_projection", self._authority),
        ):
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=document,
                    permit=permit,
                )

        prepared = self._load_prepared_source_unlocked(
            run_id=run_id, cycle=cycle
        )
        if prepared is None:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PREPERMIT_SOURCE_REQUIRED"
            )
        qualification = prepared["qualification"]
        admission = prepared["admission"]
        replay = prepared["replay"]
        if (
            prepared["source_cutoff_at"] != permit.get("analysis_decision_at")
            or _moment(
                prepared["admitted_at"],
                "V32_LOCAL_ANALYSIS_SOURCE_TIME_INVALID",
            )
            > _moment(
                prepared["replayed_at"],
                "V32_LOCAL_ANALYSIS_SOURCE_TIME_INVALID",
            )
            or _moment(
                prepared["replayed_at"],
                "V32_LOCAL_ANALYSIS_SOURCE_TIME_INVALID",
            )
            > _moment(
                permit["issued_at"],
                "V32_LOCAL_ANALYSIS_SOURCE_TIME_INVALID",
            )
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PREPERMIT_SOURCE_BINDING_INVALID"
            )

        source_roles = (
            ("source_capture", qualification.source_capture),
            ("source_snapshot", qualification.market_snapshot),
            ("source_qualification", qualification.formal_qualification),
            ("source_full_loader", admission["full_loader_receipt"]),
            ("cycle_source_admission", admission["cycle_source_admission"]),
            ("public_market_analysis_bundle", qualification.public_market_analysis_bundle),
            ("support_pit_registry", qualification.pit_registry),
            ("durable_source_replay", replay["durable_source_replay_receipt"]),
        )
        for role, document in source_roles:
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=document,
                    permit=permit,
                )

        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        previous_documents, previous_bindings = self._previous(dynamic, cycle=cycle)
        bundle = self._document(
            dynamic, cycle=cycle, role="public_market_analysis_bundle"
        )
        pit = self._document(dynamic, cycle=cycle, role="support_pit_registry")
        assert bundle is not None and pit is not None
        # A persisted bundle is untrusted input on every resumed invocation.
        # Re-run its owning verifier before any timeframe projection or replay.
        self._public.verify_public_market_analysis_bundle(bundle)
        projection = self._document(
            dynamic, cycle=cycle, role="public_market_graph_projection"
        )
        if projection is None:
            projection = build_v32_public_market_graph_projection_v1(
                bundle,
                previous_projection=previous_documents[
                    "public_market_graph_projection"
                ],
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="public_market_graph_projection",
                document=projection,
                permit=permit,
            )
        graph_registry = self._document(
            dynamic, cycle=cycle, role="support_graph_registry"
        )
        if graph_registry is None:
            graph_registry = build_v32_verified_graph_dependency_registry_v1(
                graph_projection=projection,
                analysis_bundle=bundle,
                decision_time=permit["analysis_decision_at"],
                previous_projection=previous_documents[
                    "public_market_graph_projection"
                ],
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="support_graph_registry",
                document=graph_registry,
                permit=permit,
            )
        availability = self._document(
            dynamic,
            cycle=cycle,
            role="verified_pit_evidence_availability_registry",
        )
        if availability is None:
            availability = build_v32_verified_pit_evidence_availability_registry_v1(
                public_evidence_verifier=self._public,
                public_market_analysis_bundle=bundle,
                pit_evidence_registry=pit,
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="verified_pit_evidence_availability_registry",
                document=availability,
                permit=permit,
            )
        market_view = self._document(
            dynamic, cycle=cycle, role="agent_market_graph_view"
        )
        if market_view is None:
            market_view = build_v32_agent_market_graph_view_v1(
                public_evidence_verifier=self._public,
                public_market_analysis_bundle=bundle,
                public_market_graph_projection=projection,
                pit_evidence_registry=pit,
                graph_dependency_registry=graph_registry,
                pit_evidence_availability_registry=availability,
                previous_public_market_graph_projection=previous_documents[
                    "public_market_graph_projection"
                ],
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="agent_market_graph_view",
                document=market_view,
                permit=permit,
            )
        timeframe = self._document(dynamic, cycle=cycle, role="timeframe_context")
        timeframe_is_new = timeframe is None
        if timeframe_is_new:
            timeframe = self._material.build_timeframe_context(
                permit=permit,
                public_market_analysis_bundle=bundle,
                previous_timeframe_context=previous_documents["timeframe_context"],
            )
        assert timeframe is not None
        if previous_documents["timeframe_context"] is None:
            verify_v32_timeframe_context_state_v1(timeframe)
        else:
            verify_v32_timeframe_context_transition_v1(
                previous_state=previous_documents["timeframe_context"],
                current_state=timeframe,
            )
        verify_v32_timeframe_payload_bindings_v1(
            timeframe_context_state=timeframe,
            public_market_analysis_bundle=bundle,
        )
        verify_v32_timeframe_production_policy_v1(
            timeframe_context_state=timeframe,
            public_market_analysis_bundle=bundle,
        )
        verify_v32_timeframe_invalidation_bindings_v1(
            timeframe_context_state=timeframe,
            public_market_analysis_bundle=bundle,
            previous_state=previous_documents["timeframe_context"],
        )
        if timeframe_is_new:
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="timeframe_context",
                document=timeframe,
                permit=permit,
            )

        current_documents, current_bindings = self._current_material(
            dynamic, cycle=cycle
        )
        proposal_packet = self._document(dynamic, cycle=cycle, role="proposal_packet")
        if proposal_packet is None:
            mature_ids = set(permit.get("mature_terminal_schedule_ids", ()))
            matured_materials = [
                row
                for row in self._outcome.load_terminal_receipt_materials(
                    run_id=run_id
                )
                if row["receipt"].get("schedule_id") in mature_ids
            ]
            if sorted(
                row["receipt"]["schedule_id"] for row in matured_materials
            ) != sorted(mature_ids):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_MATURED_OUTCOME_PREFIX_INVALID"
                )
            matured = [row["receipt"] for row in matured_materials]
            matured_bindings = [
                row["receipt_binding"] for row in matured_materials
            ]
            proposal_packet = self._material.build_proposal_packet(
                permit=permit,
                active_authority_projection=self._authority,
                current_artifacts=current_documents,
                current_bindings=current_bindings,
                previous_artifacts=previous_documents,
                previous_bindings=previous_bindings,
                matured_outcome_receipts=matured,
                matured_outcome_receipt_bindings=matured_bindings,
            )
            verify_v32_proposal_canonical_packet_v1(proposal_packet)
            supports = proposal_packet.get("support_documents", {})
            if (
                proposal_packet.get("run_id") != run_id
                or proposal_packet.get("cycle_index") != cycle
                or proposal_packet.get("decision_time")
                != permit.get("analysis_decision_at")
                or supports.get("active_authority_projection") != self._authority
                or supports.get("cycle_source_admission")
                != current_documents["cycle_source_admission"]
                or supports.get("timeframe_context_state") != timeframe
                or supports.get("agent_market_graph_view") != market_view
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_PROPOSAL_CURRENT_MATERIAL_MISMATCH"
                )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="proposal_packet",
                document=proposal_packet,
                permit=permit,
            )

        proposal_packet_binding = _public_binding(
            self._binding_for(dynamic, cycle=cycle, role="proposal_packet") or {}
        )
        proposal_package = self._context_package(
            stage="PROPOSAL",
            packet=proposal_packet,
            packet_binding=proposal_packet_binding,
        )
        proposal_context = self._document(dynamic, cycle=cycle, role="proposal_input")
        if proposal_context is None:
            proposal_context = build_v32_agent_input_context_v1(
                agent_stage="PROPOSAL",
                canonical_packet=proposal_packet,
                canonical_packet_binding=proposal_packet_binding,
                created_at=self._timestamp("PROPOSAL_CONTEXT_CREATED", permit),
                **self._context_builder_kwargs(proposal_package),
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="proposal_input",
                document=proposal_context,
                permit=permit,
            )

        try:
            mailbox_checkpoint = self._mailbox.load_checkpoint(
                run_id=run_id, cycle_index=cycle
            )
        except Exception:
            mailbox_checkpoint = self._mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{run_id}::{cycle:04d}",
                run_id=run_id,
                cycle_index=cycle,
                created_at=proposal_context["created_at"],
            )
            return self._advance(
                "PENDING", mailbox_checkpoint["current_root_agent_mailbox_checkpoint_digest"]
            )

        if mailbox_checkpoint["stage_states"]["PROPOSAL"]["status"] == "READY":
            context_binding = _public_binding(
                self._binding_for(dynamic, cycle=cycle, role="proposal_input") or {}
            )
            kwargs = {
                "run_id": run_id,
                "cycle_index": cycle,
                "expected_checkpoint_digest": mailbox_checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                "agent_input_context": proposal_context,
                "agent_input_context_binding": context_binding,
                "reserved_at": proposal_context["created_at"],
            }
            if proposal_package is not None:
                kwargs["lossless_context_package"] = proposal_package
            result = self._mailbox.enqueue_request(**kwargs)
            return self._advance(
                "PENDING",
                result["checkpoint"]["current_root_agent_mailbox_checkpoint_digest"],
            )

        proposal_status = mailbox_checkpoint["stage_states"]["PROPOSAL"]["status"]
        if proposal_status in {"REQUESTED", "CLAIMED"}:
            return self._advance(
                "PENDING",
                mailbox_checkpoint["current_root_agent_mailbox_checkpoint_digest"],
            )
        if proposal_status == "DELIVERED":
            documents = self._mailbox_documents(
                run_id=run_id,
                cycle=cycle,
                stage="PROPOSAL",
                allow_recovery_tail=True,
            )
            result = self._mailbox.consume_delivery(
                run_id=run_id,
                cycle_index=cycle,
                stage="PROPOSAL",
                expected_checkpoint_digest=mailbox_checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                consumed_at=documents["agent_delivery"]["delivered_at"],
            )
            return self._advance(
                "PENDING",
                result["checkpoint"]["current_root_agent_mailbox_checkpoint_digest"],
            )
        if proposal_status != "CONSUMED":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_PROPOSAL_MAILBOX_STATE_INVALID"
            )

        proposal_chain = self._mailbox_documents(
            run_id=run_id, cycle=cycle, stage="PROPOSAL"
        )
        # From this boundary onward the mailbox copy is authoritative.  It was
        # write-once persisted with the request and fully replayed by the
        # public read port; a caller cannot swap in a look-alike package.
        proposal_package = proposal_chain["lossless_context_package"]
        for role, key in (
            ("proposal_delivery", "agent_delivery"),
            ("proposal_consumption", "agent_consumption"),
        ):
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=proposal_chain[key],
                    permit=permit,
                )

        proposal_output = loads_json_strict(
            proposal_chain["agent_delivery"]["payload_utf8"]
        )
        verify_v32_proposal_semantic_output_v1(
            proposal_output,
            proposal_input_context=proposal_context,
            **self._compiler_package_kwargs(
                stage="PROPOSAL", package=proposal_package
            ),
        )
        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        if self._binding_for(dynamic, cycle=cycle, role="proposal_semantic_output") is None:
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="proposal_semantic_output",
                document=proposal_output,
                permit=permit,
            )
        proposal_receipt = compile_v32_proposal_delivery_v1(
            proposal_input_context=proposal_context,
            proposal_delivery=proposal_chain["agent_delivery"],
            proposal_consumption=proposal_chain["agent_consumption"],
            compiled_at=self._timestamp("PROPOSAL_COMPILED", permit),
            **self._compiler_package_kwargs(
                stage="PROPOSAL", package=proposal_package
            ),
        )
        for role, document in (
            ("proposal_compile_receipt", proposal_receipt),
            ("dynamic_state", proposal_receipt["compiled_dynamic_research_state"]),
            ("action_evaluation", proposal_receipt["sealed_action_evaluation"]),
        ):
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=document,
                    permit=permit,
                )

        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        state = self._document(dynamic, cycle=cycle, role="dynamic_state")
        evaluation = self._document(dynamic, cycle=cycle, role="action_evaluation")
        assert state is not None and evaluation is not None
        continuity = self._document(
            dynamic, cycle=cycle, role="dynamic_state_continuity"
        )
        if continuity is None:
            continuity = compose_v32_dynamic_state_continuity_v1(
                public_evidence_verifier=self._public,
                current_state=state,
                durable_previous_state=previous_documents["dynamic_state"],
                durable_previous_state_digest=(
                    None
                    if previous_bindings["dynamic_state"] is None
                    else previous_bindings["dynamic_state"]["semantic_digest"]
                ),
                verified_pit_evidence_registry=pit,
                verified_pit_evidence_registry_digest=pit[PIT_REGISTRY_DIGEST_FIELD],
                verified_public_market_analysis_bundle=bundle,
                verified_pit_evidence_availability_registry=availability,
                verified_pit_evidence_availability_registry_digest=availability[
                    "pit_evidence_availability_registry_digest"
                ],
                durable_previous_pit_evidence_availability_registry=(
                    previous_documents["pit_evidence_availability_registry"]
                ),
                durable_previous_pit_evidence_availability_registry_digest=(
                    None
                    if previous_bindings["pit_evidence_availability_registry"]
                    is None
                    else previous_bindings[
                        "pit_evidence_availability_registry"
                    ]["semantic_digest"]
                ),
                verified_graph_dependency_registry=graph_registry,
                verified_graph_dependency_registry_digest=graph_registry[
                    GRAPH_REGISTRY_DIGEST_FIELD
                ],
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="dynamic_state_continuity",
                document=continuity,
                permit=permit,
            )

        selection_packet = self._document(dynamic, cycle=cycle, role="selection_packet")
        if selection_packet is None:
            proposal_binding = lambda role: _public_binding(
                self._binding_for(dynamic, cycle=cycle, role=role) or {}
            )
            selection_packet = build_v32_selection_canonical_packet_v1(
                proposal_input_context=proposal_context,
                proposal_input_context_binding=proposal_binding("proposal_input"),
                proposal_delivery=proposal_chain["agent_delivery"],
                proposal_delivery_binding=proposal_chain["delivery_receipt"]
                ["agent_delivery_binding"],
                proposal_consumption=proposal_chain["agent_consumption"],
                proposal_consumption_binding=proposal_chain[
                    "consumption_receipt"
                ]["agent_consumption_binding"],
                compiled_dynamic_research_state=state,
                compiled_dynamic_research_state_binding=proposal_binding("dynamic_state"),
                sealed_action_evaluation=evaluation,
                sealed_action_evaluation_binding=proposal_binding("action_evaluation"),
                prepared_at=self._timestamp("SELECTION_PACKET_PREPARED", permit),
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="selection_packet",
                document=selection_packet,
                permit=permit,
            )

        selection_packet_binding = _public_binding(
            self._binding_for(dynamic, cycle=cycle, role="selection_packet") or {}
        )
        selection_package = self._context_package(
            stage="SELECTION",
            packet=selection_packet,
            packet_binding=selection_packet_binding,
        )
        selection_context = self._document(dynamic, cycle=cycle, role="selection_input")
        if selection_context is None:
            selection_context = build_v32_agent_input_context_v1(
                agent_stage="SELECTION",
                canonical_packet=selection_packet,
                canonical_packet_binding=selection_packet_binding,
                created_at=self._timestamp("SELECTION_CONTEXT_CREATED", permit),
                **self._context_builder_kwargs(selection_package),
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="selection_input",
                document=selection_context,
                permit=permit,
            )

        mailbox_checkpoint = self._mailbox.load_checkpoint(
            run_id=run_id, cycle_index=cycle
        )
        if mailbox_checkpoint["stage_states"]["SELECTION"]["status"] == "READY":
            kwargs = {
                "run_id": run_id,
                "cycle_index": cycle,
                "expected_checkpoint_digest": mailbox_checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                "agent_input_context": selection_context,
                "agent_input_context_binding": _public_binding(
                    self._binding_for(dynamic, cycle=cycle, role="selection_input")
                    or {}
                ),
                "reserved_at": selection_context["created_at"],
            }
            if selection_package is not None:
                kwargs["lossless_context_package"] = selection_package
            result = self._mailbox.enqueue_request(**kwargs)
            return self._advance(
                "PENDING",
                result["checkpoint"]["current_root_agent_mailbox_checkpoint_digest"],
            )
        selection_status = mailbox_checkpoint["stage_states"]["SELECTION"]["status"]
        if selection_status in {"REQUESTED", "CLAIMED"}:
            return self._advance(
                "PENDING",
                mailbox_checkpoint["current_root_agent_mailbox_checkpoint_digest"],
            )
        if selection_status == "DELIVERED":
            documents = self._mailbox_documents(
                run_id=run_id,
                cycle=cycle,
                stage="SELECTION",
                allow_recovery_tail=True,
            )
            result = self._mailbox.consume_delivery(
                run_id=run_id,
                cycle_index=cycle,
                stage="SELECTION",
                expected_checkpoint_digest=mailbox_checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                consumed_at=documents["agent_delivery"]["delivered_at"],
            )
            return self._advance(
                "PENDING",
                result["checkpoint"]["current_root_agent_mailbox_checkpoint_digest"],
            )
        if selection_status != "CONSUMED":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SELECTION_MAILBOX_STATE_INVALID"
            )

        selection_chain = self._mailbox_documents(
            run_id=run_id, cycle=cycle, stage="SELECTION"
        )
        selection_package = selection_chain["lossless_context_package"]
        for role, key in (
            ("selection_delivery", "agent_delivery"),
            ("selection_consumption", "agent_consumption"),
        ):
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=selection_chain[key],
                    permit=permit,
                )
        selection_output = loads_json_strict(
            selection_chain["agent_delivery"]["payload_utf8"]
        )
        verify_v32_selection_semantic_output_v1(
            selection_output,
            selection_input_context=selection_context,
            **self._compiler_package_kwargs(
                stage="SELECTION",
                package=selection_package,
                proposal_package=proposal_package,
            ),
        )
        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        if self._binding_for(dynamic, cycle=cycle, role="selection_semantic_output") is None:
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="selection_semantic_output",
                document=selection_output,
                permit=permit,
            )
        selection_receipt = compile_v32_selection_delivery_v1(
            proposal_compile_receipt=proposal_receipt,
            selection_input_context=selection_context,
            selection_delivery=selection_chain["agent_delivery"],
            selection_consumption=selection_chain["agent_consumption"],
            compiled_at=self._timestamp("SELECTION_COMPILED", permit),
            **self._compiler_package_kwargs(
                stage="SELECTION",
                package=selection_package,
                proposal_package=proposal_package,
            ),
        )
        for role, document in (
            ("selection_compile_receipt", selection_receipt),
            ("action_plan", selection_receipt["final_dynamic_action_plan"]),
        ):
            dynamic = self._dynamic.load_checkpoint(run_id=run_id)
            if self._binding_for(dynamic, cycle=cycle, role=role) is None:
                return self._persist_and_return(
                    run_id=run_id,
                    cycle=cycle,
                    role=role,
                    document=document,
                    permit=permit,
                )
        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        plan = self._document(dynamic, cycle=cycle, role="action_plan")
        assert plan is not None
        action_continuity = self._document(
            dynamic, cycle=cycle, role="action_plan_continuity"
        )
        if action_continuity is None:
            action_continuity = compose_v32_action_plan_continuity_v1(
                current_dynamic_state=state,
                current_action_plan=plan,
                durable_previous_dynamic_state=previous_documents["dynamic_state"],
                durable_previous_dynamic_state_digest=(
                    None
                    if previous_bindings["dynamic_state"] is None
                    else previous_bindings["dynamic_state"]["semantic_digest"]
                ),
                durable_previous_action_plan=previous_documents["action_plan"],
                durable_previous_action_plan_digest=(
                    None
                    if previous_bindings["action_plan"] is None
                    else previous_bindings["action_plan"]["semantic_digest"]
                ),
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="action_plan_continuity",
                document=action_continuity,
                permit=permit,
            )
        revision = self._document(
            dynamic, cycle=cycle, role="authorized_revision_cycle_registry"
        )
        if revision is None:
            required_gaps = build_v32_required_data_gap_escalations_v1(
                public_market_analysis_bundle=bundle
            )
            revision_material = (
                self._material.build_authorized_revision_cycle_registry(
                permit=permit,
                proposal_packet=proposal_packet,
                proposal_context_package=proposal_package,
                selection_packet=selection_packet,
                selection_context_package=selection_package,
                required_data_gap_escalations=required_gaps,
            )
            )
            if (
                not isinstance(revision_material, Mapping)
                or set(revision_material) != _REVISION_MATERIAL_FIELDS
                or not isinstance(revision_material["cycle_registry"], Mapping)
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_REVISION_MATERIAL_INVALID"
                )
            revision = revision_material["cycle_registry"]
            supplied_gaps = revision_material["data_gap_entries"]
            if (
                isinstance(supplied_gaps, (str, bytes))
                or not isinstance(supplied_gaps, Sequence)
                or sorted(
                    (
                        dict(row["escalation"])
                        for row in supplied_gaps
                        if isinstance(row, Mapping)
                        and isinstance(row.get("escalation"), Mapping)
                    ),
                    key=lambda row: row["gap_id"],
                )
                != required_gaps
                or len(supplied_gaps) != len(required_gaps)
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_DATA_GAP_COVERAGE_INCOMPLETE"
                )
            verify_v32_authorized_revision_cycle_registry_v1(
                revision,
                proposal_context=revision_material["proposal_context"],
                selection_context=revision_material["selection_context"],
                unknown_tracks=revision_material["unknown_tracks"],
                data_gap_entries=revision_material["data_gap_entries"],
                manual_evidence_entries=revision_material[
                    "manual_evidence_entries"
                ],
                environment_conformance=revision_material[
                    "environment_conformance"
                ],
                recovery_traces=revision_material["recovery_traces"],
                revision_input_state=revision_material[
                    "revision_input_state"
                ],
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="authorized_revision_cycle_registry",
                document=revision,
                permit=permit,
            )
        schedule = self._document(dynamic, cycle=cycle, role="outcome_schedule")
        if schedule is None:
            sealed_selection_receipt = self._document(
                dynamic, cycle=cycle, role="selection_compile_receipt"
            )
            if sealed_selection_receipt is None:
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_SELECTION_RECEIPT_REQUIRED"
                )
            decision_sealed_at = sealed_selection_receipt["compiled_at"]
            if (
                _moment(
                    decision_sealed_at,
                    "V32_LOCAL_ANALYSIS_DECISION_SEALED_TIME_INVALID",
                )
                - _moment(
                    prepared["source_cutoff_at"],
                    "V32_LOCAL_ANALYSIS_DECISION_SEALED_TIME_INVALID",
                )
                > timedelta(seconds=MAX_SOURCE_AGE_SECONDS)
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_SOURCE_STALE_AFTER_AGENT"
                )
            schedule = self._material.build_outcome_schedule_set(
                permit=permit,
                final_dynamic_action_plan=plan,
                proposal_packet=proposal_packet,
                decision_sealed_at=decision_sealed_at,
            )
            verify_v32_outcome_schedule_set(schedule)
            if (
                schedule.get("run_id") != run_id
                or schedule.get("cycle_index") != cycle
                or schedule.get("decision_time")
                != decision_sealed_at
                or schedule.get("sealed_decision_digest")
                != plan[ACTION_PLAN_DIGEST_FIELD]
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_SCHEDULE_BINDING_INVALID"
                )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="outcome_schedule",
                document=schedule,
                permit=permit,
            )
        shadow = self._document(dynamic, cycle=cycle, role="shadow_decision_bundle")
        if shadow is None:
            binding = lambda role: _public_binding(
                self._binding_for(dynamic, cycle=cycle, role=role) or {}
            )
            shadow = build_v32_replayable_shadow_decision_bundle_v1(
                bundle_id=f"shadow-bundle:{run_id}:{cycle:04d}",
                decision_id=schedule["decision_id"],
                created_at=self._timestamp("SHADOW_BUNDLE_CREATED", permit),
                public_market_analysis_bundle=bundle,
                public_market_analysis_bundle_binding=binding(
                    "public_market_analysis_bundle"
                ),
                pit_evidence_registry=pit,
                pit_evidence_registry_binding=binding("support_pit_registry"),
                sealed_action_evaluation=evaluation,
                sealed_action_evaluation_binding=binding("action_evaluation"),
                dynamic_research_state=state,
                selected_plan=plan,
                selected_plan_binding=binding("action_plan"),
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="shadow_decision_bundle",
                document=shadow,
                permit=permit,
            )
        commit = self._document(dynamic, cycle=cycle, role="commit_envelope")
        if commit is None:
            binding = lambda role: _public_binding(
                self._binding_for(dynamic, cycle=cycle, role=role) or {}
            )
            commit = build_v32_two_stage_commit_envelope_v1(
                proposal_input_context=proposal_context,
                proposal_delivery=proposal_chain["agent_delivery"],
                proposal_consumption=proposal_chain["agent_consumption"],
                selection_input_context=selection_context,
                selection_delivery=selection_chain["agent_delivery"],
                selection_consumption=selection_chain["agent_consumption"],
                final_dynamic_action_plan=plan,
                final_dynamic_action_plan_binding=binding("action_plan"),
                outcome_schedule_set=schedule,
                outcome_schedule_set_binding=binding("outcome_schedule"),
                sealed_at=self._timestamp("COMMIT_SEALED", permit),
                previous_commit_envelope_digest=(
                    None
                    if previous_bindings["commit_envelope"] is None
                        else previous_bindings["commit_envelope"]["semantic_digest"]
                ),
                proposal_lossless_context_package=proposal_package,
                selection_lossless_context_package=selection_package,
            )
            return self._persist_and_return(
                run_id=run_id,
                cycle=cycle,
                role="commit_envelope",
                document=commit,
                permit=permit,
            )

        dynamic = self._dynamic.load_checkpoint(run_id=run_id)
        if dynamic.get("accepted_analysis_cycles", 0) < cycle:
            acceptance_binding = self._binding_for(
                dynamic, cycle=cycle, role="analysis_acceptance"
            )
            recovered_at = (
                self._dynamic.load_artifact(acceptance_binding)["accepted_at"]
                if acceptance_binding is not None
                else self._timestamp("RESEARCH_CYCLE_ACCEPTED", permit)
            )
            accepted = self._dynamic.recover_persisted_commit_tail(
                run_id=run_id,
                cycle_index=cycle,
                expected_checkpoint_digest=dynamic[
                    RESEARCH_CHECKPOINT_DIGEST_FIELD
                ],
                recovered_at=recovered_at,
            )
            return self._advance(
                "PENDING", accepted[RESEARCH_CHECKPOINT_DIGEST_FIELD]
            )

        outcome = self._outcome.load_checkpoint(run_id=run_id)
        schedule_sets = self._outcome.load_schedule_sets(run_id=run_id)
        if len(schedule_sets) < cycle:
            if [row[SCHEDULE_SET_DIGEST_FIELD] for row in schedule_sets] != list(
                permit.get("outcome_schedule_set_digests", ())
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_PRIOR_SCHEDULE_PREFIX_MISMATCH"
                )
            outcome = self._outcome.register_schedule_set(
                schedule_set=schedule,
                registered_at=self._timestamp("OUTCOME_SCHEDULE_REGISTERED", permit),
            )
            return self._advance("PENDING", outcome["checkpoint_digest"])
        if len(schedule_sets) != cycle or schedule_sets[-1] != dict(schedule):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_OUTCOME_SCHEDULE_SEQUENCE_INVALID"
            )
        return self._seal_completion(permit=permit)

    def _failure_path(self, permit_digest: str) -> Path:
        return self._safe_path(
            f"{STORE_ROOT}/permits/{permit_digest}/failure-evidence.json"
        )

    def _terminal_path(self, permit_digest: str, kind: str) -> Path:
        name = "completion-envelope.json" if kind == "COMPLETION" else "failure-envelope.json"
        return self._safe_path(f"{STORE_ROOT}/permits/{permit_digest}/{name}")

    @staticmethod
    def _canonical_file(path: Path) -> Mapping[str, Any]:
        if not path.is_file() or path.is_symlink():
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DURABLE_FILE_INVALID"
            )
        document = load_json_strict(path)
        if path.read_bytes() != canonical_bytes(document) + b"\n":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DURABLE_FILE_NONCANONICAL"
            )
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DURABLE_FILE_INVALID"
            ) from exc
        return document

    def _load_terminal(
        self, *, permit_digest: str, kind: str
    ) -> Mapping[str, Any] | None:
        own = self._terminal_path(permit_digest, kind)
        other = self._terminal_path(
            permit_digest, "FAILURE" if kind == "COMPLETION" else "COMPLETION"
        )
        if own.exists() and other.exists():
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DUAL_TERMINAL_STATE"
            )
        if not own.exists():
            return None
        document = self._canonical_file(own)
        expected = _COMPLETION_FIELDS if kind == "COMPLETION" else _FAILURE_FIELDS
        if set(document) != expected:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_TERMINAL_ENVELOPE_INVALID"
            )
        return document

    def _write_terminal(
        self, *, permit_digest: str, kind: str, envelope: Mapping[str, Any]
    ) -> str:
        own = self._terminal_path(permit_digest, kind)
        other = self._terminal_path(
            permit_digest, "FAILURE" if kind == "COMPLETION" else "COMPLETION"
        )
        if other.exists():
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_DUAL_TERMINAL_STATE"
            )
        write_once_json(own, envelope)
        return canonical_digest(dict(envelope))

    def _build_completion_envelope(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        run_id, permit_digest, cycle = self._permit_identity(permit)
        checkpoint = self._dynamic.load_checkpoint(run_id=run_id)
        if checkpoint.get("accepted_analysis_cycles", 0) < cycle:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_COMPLETION_NOT_ACCEPTED"
            )
        acceptance_replay = self._dynamic.replay_cycle_acceptance(
            run_id=run_id, cycle_index=cycle
        )
        acceptance = acceptance_replay["acceptance"]
        acceptance_binding = acceptance_replay["binding"]
        replayed_required = acceptance_replay["required_bindings"]
        required_roles = (
            "cycle_source_admission",
            "public_market_analysis_bundle",
            "public_market_graph_projection",
            "support_graph_registry",
            "durable_source_replay",
            "shadow_decision_bundle",
            "outcome_schedule",
            "proposal_compile_receipt",
            "selection_compile_receipt",
            "action_plan",
            "commit_envelope",
            "timeframe_context",
            "dynamic_state",
        )
        required: dict[str, Mapping[str, Any]] = {}
        for role in required_roles:
            binding = replayed_required.get(role)
            if not isinstance(binding, Mapping):
                raise V32LocalAnalysisLaneError(
                    f"V32_LOCAL_ANALYSIS_COMPLETION_ROLE_MISSING:{role}"
                )
            required[role] = dict(binding)
        if (
            acceptance_binding.get("semantic_digest")
            != acceptance.get(ANALYSIS_ACCEPTANCE_DIGEST_FIELD)
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_ACCEPTANCE_BINDING_INVALID"
            )
        documents = {
            role: self._dynamic.load_artifact(binding)
            for role, binding in required.items()
        }
        bundle = documents["public_market_analysis_bundle"]
        projection = documents["public_market_graph_projection"]
        registry = documents["support_graph_registry"]
        source_replay = documents["durable_source_replay"]
        shadow = documents["shadow_decision_bundle"]
        previous_projection = None
        if cycle > 1:
            previous_acceptance_replay = self._dynamic.replay_cycle_acceptance(
                run_id=run_id, cycle_index=cycle - 1
            )
            previous_binding = previous_acceptance_replay[
                "required_bindings"
            ].get("public_market_graph_projection")
            if not isinstance(previous_binding, Mapping):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_PREVIOUS_GRAPH_MISSING"
                )
            previous_projection = self._dynamic.load_artifact(previous_binding)
        bundle_digest = self._public.verify_public_market_analysis_bundle(bundle)
        projection_digest = self._public.verify_public_market_graph_projection(
            projection,
            analysis_bundle=bundle,
            previous_projection=previous_projection,
        )
        registry_digest = self._public.verify_graph_dependency_registry(
            registry,
            graph_projection=projection,
            analysis_bundle=bundle,
            previous_projection=previous_projection,
        )
        replay = verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=self._public,
            source_store=self._source,
            run_store=self._admitted_source,
            active_authority=self._authority,
            qualification_id=self._qualification_id(run_id=run_id, cycle=cycle),
            run_id=run_id,
            cycle_index=cycle,
        )["durable_source_replay_receipt"]
        if replay != source_replay:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SOURCE_REPLAY_MISMATCH"
            )
        outcome_checkpoint = self._outcome.load_checkpoint(run_id=run_id)
        schedule_sets = self._outcome.load_schedule_sets(run_id=run_id)
        if len(schedule_sets) != cycle:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_COMPLETION_SCHEDULE_PREFIX_INVALID"
            )
        schedule = documents["outcome_schedule"]
        if schedule_sets[-1] != schedule:
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_COMPLETION_SCHEDULE_MISMATCH"
            )
        proposal_receipt = documents["proposal_compile_receipt"]
        selection_receipt = documents["selection_compile_receipt"]
        completion = {
            "schedule_sets_before": schedule_sets[:-1],
            "new_schedule_set": schedule,
            "accepted_state_digest": acceptance[
                ANALYSIS_ACCEPTANCE_DIGEST_FIELD
            ],
            "shadow_decision_bundle_digest": shadow[
                "shadow_decision_bundle_digest"
            ],
            "source_admission_digest": documents["cycle_source_admission"][
                SOURCE_ADMISSION_DIGEST_FIELD
            ],
            "source_admission_physical_sha256": required[
                "cycle_source_admission"
            ]["physical_sha256"],
            "proposal_lifecycle_digest": proposal_receipt[
                "proposal_semantic_compile_receipt_digest"
            ],
            "selection_lifecycle_digest": selection_receipt[
                "selection_semantic_compile_receipt_digest"
            ],
            "final_action_plan_digest": documents["action_plan"][
                ACTION_PLAN_DIGEST_FIELD
            ],
            "commit_envelope_digest": documents["commit_envelope"][
                COMMIT_ENVELOPE_DIGEST_FIELD
            ],
            "new_research_checkpoint_digest": checkpoint[
                RESEARCH_CHECKPOINT_DIGEST_FIELD
            ],
            "new_outcome_checkpoint_digest": outcome_checkpoint[
                "checkpoint_digest"
            ],
            "new_timeframe_cache_digest": documents["timeframe_context"][
                TIMEFRAME_DIGEST_FIELD
            ],
            "new_dynamic_state_digest": documents["dynamic_state"][
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            "completed_at": self._timestamp("ANALYSIS_COMPLETION_SEALED", permit),
        }
        source_schema_version = documents["cycle_source_admission"].get(
            "schema_version"
        )
        if source_schema_version == "2.0.0":
            completion.update(
                {
                    "source_admission_schema_version": source_schema_version,
                    "decision_sealed_at": selection_receipt["compiled_at"],
                }
            )
        elif source_schema_version != "1.0.0":
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_SOURCE_ADMISSION_SCHEMA_INVALID"
            )
        return {
            "permit_digest": permit_digest,
            "analysis_acceptance_digest": completion["accepted_state_digest"],
            "shadow_decision_bundle_digest": completion[
                "shadow_decision_bundle_digest"
            ],
            "durable_source_replay_receipt_digest": source_replay[
                SOURCE_REPLAY_DIGEST_FIELD
            ],
            "public_market_analysis_bundle_digest": bundle_digest,
            "public_market_graph_projection_digest": projection_digest,
            "graph_delta_digest": projection["graph_delta_digest"],
            "graph_dependency_registry_digest": registry_digest,
            "public_market_analysis_bundle": bundle,
            "public_market_graph_projection": projection,
            "previous_public_market_graph_projection": previous_projection,
            "graph_dependency_registry": registry,
            "durable_source_replay_receipt": source_replay,
            "analysis_acceptance": acceptance,
            "shadow_decision_bundle": shadow,
            "completion": completion,
        }

    def _seal_completion(self, *, permit: Mapping[str, Any]) -> Mapping[str, str]:
        _, permit_digest, _ = self._permit_identity(permit)
        envelope = self._build_completion_envelope(permit=permit)
        transition = self._write_terminal(
            permit_digest=permit_digest, kind="COMPLETION", envelope=envelope
        )
        return self._advance("COMPLETION_SEALED", transition)

    def _seal_failure(
        self, *, permit: Mapping[str, Any], error: Exception
    ) -> Mapping[str, str]:
        run_id, permit_digest, cycle = self._permit_identity(permit)
        existing_terminal = self._load_terminal(
            permit_digest=permit_digest, kind="FAILURE"
        )
        if existing_terminal is not None:
            return self._advance(
                "FAILURE_SEALED", canonical_digest(existing_terminal)
            )
        failure_path = self._failure_path(permit_digest)
        if failure_path.exists():
            evidence = self._canonical_file(failure_path)
        else:
            occurred_at = self._timestamp("ANALYSIS_FAILURE_SEALED", permit)
            try:
                research = self._dynamic.load_checkpoint(run_id=run_id)
                research_digest = research[RESEARCH_CHECKPOINT_DIGEST_FIELD]
            except Exception:
                research = None
                research_digest = permit["research_checkpoint_digest"]
            try:
                outcome_digest = self._outcome.load_checkpoint(run_id=run_id)[
                    "checkpoint_digest"
                ]
            except Exception:
                outcome_digest = permit["outcome_checkpoint_digest"]
            try:
                mailbox_digest = self._mailbox.load_checkpoint(
                    run_id=run_id, cycle_index=cycle
                )["current_root_agent_mailbox_checkpoint_digest"]
            except Exception:
                mailbox_digest = None
            message = (str(error).strip() or type(error).__name__)[:512]
            evidence = self_digest(
                {
                    "schema_id": FAILURE_EVIDENCE_SCHEMA_ID,
                    "schema_version": SCHEMA_VERSION,
                    "run_id": run_id,
                    "cycle_index": cycle,
                    "permit_digest": permit_digest,
                    "failure_class": type(error).__name__,
                    "failure_message": message,
                    "research_checkpoint_digest": research_digest,
                    "outcome_checkpoint_digest": outcome_digest,
                    "mailbox_checkpoint_digest": mailbox_digest,
                    "occurred_at": occurred_at,
                    "retry_allowed": False,
                    "resume_allowed": False,
                    "source_scope": SOURCE_SCOPE,
                    "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                    "executable": False,
                },
                FAILURE_EVIDENCE_DIGEST_FIELD,
            )
            write_once_json(failure_path, evidence)
            if isinstance(research, Mapping) and research.get("status") not in {
                "FAILED",
                "TERMINAL",
            }:
                try:
                    self._dynamic.fail_closed(
                        run_id=run_id,
                        expected_checkpoint_digest=research_digest,
                        failure_code="V32_LOCAL_ANALYSIS_LANE_FAILURE",
                        failure_summary=(
                            "local analysis lane sealed one non-retryable failure"
                        ),
                        failure_evidence_digest=evidence[
                            FAILURE_EVIDENCE_DIGEST_FIELD
                        ],
                        failed_at=occurred_at,
                    )
                except Exception:
                    # The independent lane evidence remains terminal even when
                    # the lower store cannot advance its own failure head.
                    pass
        if (
            not isinstance(evidence, Mapping)
            or set(evidence) != _FAILURE_EVIDENCE_FIELDS
            or verify_self_digest(evidence, FAILURE_EVIDENCE_DIGEST_FIELD)
            != evidence[FAILURE_EVIDENCE_DIGEST_FIELD]
        ):
            raise V32LocalAnalysisLaneError(
                "V32_LOCAL_ANALYSIS_FAILURE_EVIDENCE_INVALID"
            )
        envelope = {
            "permit_digest": permit_digest,
            "failure_code": (
                "SOURCE_STALE_AFTER_AGENT"
                if evidence["failure_message"]
                == "V32_LOCAL_ANALYSIS_SOURCE_STALE_AFTER_AGENT"
                else "COMMIT_STATE_CONFLICT"
            ),
            "failure_summary": (
                "SOURCE_STALE_AFTER_AGENT"
                if evidence["failure_message"]
                == "V32_LOCAL_ANALYSIS_SOURCE_STALE_AFTER_AGENT"
                else "V3.2 local analysis lane permanently failed closed"
            ),
            "failure_evidence_digest": evidence[FAILURE_EVIDENCE_DIGEST_FIELD],
            "occurred_at": evidence["occurred_at"],
        }
        transition = self._write_terminal(
            permit_digest=permit_digest, kind="FAILURE", envelope=envelope
        )
        return self._advance("FAILURE_SEALED", transition)

    def advance_analysis(
        self,
        *,
        permit: Mapping[str, Any],
        supervisor_checkpoint_before_permit: Mapping[str, Any],
        supervisor_open_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Advance one durable substage; ordinary Agent waiting is PENDING."""

        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            completion = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            if completion is not None:
                return self._advance(
                    "COMPLETION_SEALED", canonical_digest(completion)
                )
            failure = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            if failure is not None:
                return self._advance("FAILURE_SEALED", canonical_digest(failure))
            try:
                # Share exact, owner-bound lifecycle and public-graph
                # validations within this one wake.  Both scopes clear on
                # return/failure and never cross an execution owner.
                with (
                    self._public.verification_scope(),
                    v32_lifecycle_verification_scope_v1(),
                ):
                    self._validate_supervisor_chain(
                        permit=permit,
                        before=supervisor_checkpoint_before_permit,
                        opened=supervisor_open_checkpoint,
                    )
                    return self._advance_once(
                        permit=permit,
                        before=supervisor_checkpoint_before_permit,
                        opened=supervisor_open_checkpoint,
                    )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if not isinstance(exc, Exception):
                    raise
                return self._seal_failure(permit=permit, error=exc)

    def load_durable_analysis_completion(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            document = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            return deepcopy(document) if document is not None else None

    def verify_durable_analysis_completion(
        self,
        *,
        permit: Mapping[str, Any],
        completion_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            durable = self._load_terminal(
                permit_digest=permit_digest, kind="COMPLETION"
            )
            if durable is None or dict(durable) != dict(completion_envelope):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_COMPLETION_DURABILITY_MISMATCH"
                )
            # Completion replay is another single-call verification boundary.
            # Deduplicate exact successful lifecycle and public-graph checks;
            # both scopes are cleared before returning to the caller.
            with (
                self._public.verification_scope(),
                v32_lifecycle_verification_scope_v1(),
            ):
                expected = self._build_completion_envelope(permit=permit)
            # completed_at is a sealed lane time.  Replay every semantic field
            # while retaining that original time rather than asking the clock
            # for a second value.
            expected = deepcopy(dict(expected))
            expected["completion"]["completed_at"] = durable["completion"][
                "completed_at"
            ]
            if expected != dict(durable):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_COMPLETION_REPLAY_MISMATCH"
                )
            return deepcopy(durable)

    def load_durable_analysis_failure(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            document = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            return deepcopy(document) if document is not None else None

    def verify_durable_analysis_failure(
        self,
        *,
        permit: Mapping[str, Any],
        failure_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        _, permit_digest, _ = self._permit_identity(permit)
        with self._lock():
            durable = self._load_terminal(
                permit_digest=permit_digest, kind="FAILURE"
            )
            if durable is None or dict(durable) != dict(failure_envelope):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_FAILURE_DURABILITY_MISMATCH"
                )
            evidence = self._canonical_file(self._failure_path(permit_digest))
            if (
                set(evidence) != _FAILURE_EVIDENCE_FIELDS
                or verify_self_digest(evidence, FAILURE_EVIDENCE_DIGEST_FIELD)
                != durable["failure_evidence_digest"]
                or durable["permit_digest"] != permit_digest
                or durable["occurred_at"] != evidence["occurred_at"]
                or durable.get("failure_code")
                != (
                    "SOURCE_STALE_AFTER_AGENT"
                    if evidence["failure_message"]
                    == "V32_LOCAL_ANALYSIS_SOURCE_STALE_AFTER_AGENT"
                    else "COMMIT_STATE_CONFLICT"
                )
                or evidence["retry_allowed"] is not False
                or evidence["resume_allowed"] is not False
            ):
                raise V32LocalAnalysisLaneError(
                    "V32_LOCAL_ANALYSIS_FAILURE_REPLAY_MISMATCH"
                )
            return deepcopy(durable)


__all__ = [
    "FAILURE_EVIDENCE_DIGEST_FIELD",
    "FAILURE_EVIDENCE_SCHEMA_ID",
    "LocalV32AnalysisLane",
    "STORE_ROOT",
    "V32AnalysisClockPort",
    "V32AnalysisMaterialPort",
    "V32LocalAnalysisLaneError",
    "build_v32_required_data_gap_escalations_v1",
]
