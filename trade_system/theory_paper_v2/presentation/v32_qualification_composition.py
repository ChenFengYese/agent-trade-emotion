"""Legacy V3.2 qualification replay and post-Phase-A operations.

Creation of new legacy qualification namespaces is retired.  Existing
namespaces may still be replayed and completed through the narrow identity-only
surface while their exact frozen checkout remains available.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from ..application.v32_actual_capability_qualification_controller import (
    LocalV32ActualCapabilityQualificationControllerStore,
    advance_v32_actual_capability_qualification_controller_once,
    replay_v32_actual_capability_qualification_controller_v1,
    stable_v32_materialization_failure_codes_v1,
)
from ..domain.governance.v32_experiment_contract import DIGEST_FIELD as CONTRACT_DIGEST_FIELD
from ..domain.governance.v32_qualification_identity import (
    V32QualificationIdentityError,
    validate_v32_active_qualification_identity_v1,
)
from ..domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    REQUEST_DIGEST_FIELD,
    build_v32_current_codex_presentation_envelope_v1,
    build_v32_current_root_agent_mailbox_claim_v1,
    claim_v32_current_root_agent_mailbox_request_v1,
)
from ..domain.v32_cycle_source_admission import build_v32_active_authority_projection
from ..domain.v32_runtime_support_contracts import (
    MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
)
from ..infrastructure.authority.v32_actual_capability_attempt_ports import (
    V32CurrentCodexQualificationAttemptPort,
    V32OutcomeMonitorQualificationAttemptPort,
    V32PublicSourceQualificationAttemptPort,
    verify_v32_current_codex_attempt_time_v1,
)
from ..infrastructure.authority.v32_actual_capability_replay import (
    LocalV32ActualCapabilityEvidenceStore,
)
from ..infrastructure.authority.v32_current_research import (
    V32CurrentResearchAuthorityError,
    load_v32_qualification_phase_a_authority,
)
from ..infrastructure.authority.v32_authority_lifecycle import (
    finalize_v32_target_authority,
    load_v32_target_finalization_phase_times_if_started,
)
from ..infrastructure.authority.v32_qualification_runtime_namespace import (
    RUNTIME_BASE,
    V32QualificationRuntimeNamespaceError,
    assert_v32_qualification_runtime_namespace_v1,
    assert_v32_qualification_runtime_root_components_v1,
    build_v32_qualification_runtime_paths_v1,
)
from ..infrastructure.authority.v32_qualification_materializer import (
    LocalV32QualificationMaterialStore,
    LocalV32QualificationMaterializer,
)
from ..infrastructure.authority.v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from ..infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from ..infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from ..infrastructure.v32_okx_public_bundle_transport import V32OkxPublicBundleTransport
from ..infrastructure.v32_okx_public_outcome_adapter import V32OkxPublicMarkCaptureAdapter
from ..infrastructure.v32_runtime_clock import build_v32_system_clock_v1
from ..v32_durable_json import ensure_directory_tree, exclusive_lock_file


class V32QualificationCompositionError(ValueError):
    """The fixed production qualification composition failed closed."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_QUALIFICATION_COMPOSITION_LOCK_BASE = f"{RUNTIME_BASE}/.composition-locks"
_PHASE_B_TIME_KEYS = (
    "retired_at",
    "target_gate_evaluated_at",
    "target_phase_evaluated_at",
    "target_authorization_issued_at",
    "target_authority_recorded_at",
)
_PHASE_TIME_MAX_READS_PER_KEY = 4096


def _phase_clock_moment_v1(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_PHASE_CLOCK_INVALID"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_PHASE_CLOCK_INVALID"
        ) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_PHASE_CLOCK_INVALID"
        )
    return parsed.astimezone(UTC)


def _acquire_lifecycle_phase_times_v1(
    clock: Callable[[], str],
    *,
    keys: Sequence[str],
    strict_successors: frozenset[str],
    not_before: str,
) -> dict[str, str]:
    """Read a real UTC plan satisfying the lifecycle's existing order.

    The system wall clock is allowed to return the same microsecond twice or
    to move backwards.  Neither condition may be normalized into a synthetic
    future timestamp.  Instead, this pre-persistence helper performs bounded
    fresh reads and fails closed if the real clock cannot satisfy the exact
    weak/strict chronology.
    """

    previous = _phase_clock_moment_v1(not_before)
    acquired: dict[str, str] = {}
    for key in keys:
        strict = key in strict_successors
        for _ in range(_PHASE_TIME_MAX_READS_PER_KEY):
            value = clock()
            moment = _phase_clock_moment_v1(value)
            if moment > previous or (not strict and moment == previous):
                acquired[key] = value
                previous = moment
                break
        else:
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_PHASE_CLOCK_DID_NOT_ADVANCE"
            )
    return acquired


def _ids(target_run_id: str, qualification_run_id: str) -> tuple[str, str]:
    try:
        return validate_v32_active_qualification_identity_v1(
            target_run_id=target_run_id,
            qualification_run_id=qualification_run_id,
        )
    except V32QualificationIdentityError as exc:
        raise V32QualificationCompositionError(str(exc)) from exc


def _runtime_paths(qualification_run_id: str) -> dict[str, str]:
    try:
        return build_v32_qualification_runtime_paths_v1(qualification_run_id)
    except V32QualificationRuntimeNamespaceError as exc:
        raise V32QualificationCompositionError(str(exc)) from exc


def _assert_namespace(qualification_run_id: str) -> dict[str, str]:
    try:
        return dict(
            assert_v32_qualification_runtime_namespace_v1(
                project_root=PROJECT_ROOT,
                qualification_run_id=qualification_run_id,
                require_root=True,
            )
        )
    except V32QualificationRuntimeNamespaceError as exc:
        raise V32QualificationCompositionError(str(exc)) from exc


@contextmanager
def _qualification_composition_guard_v1(
    qualification_run_id: str,
) -> Iterator[None]:
    """Serialize every post-Phase-A live mutation across processes.

    Material, mailbox and controller stores have deliberately separate local
    CAS locks.  Without one outer owner, two long-running composition calls
    can each pass their own replay and then interleave those otherwise valid
    store mutations.  The guard lives outside every scanned evidence prefix
    so it cannot be mistaken for material, mailbox or failure evidence.
    """

    try:
        assert_v32_qualification_runtime_root_components_v1(
            project_root=PROJECT_ROOT,
            qualification_run_id=qualification_run_id,
        )
    except V32QualificationRuntimeNamespaceError as exc:
        raise V32QualificationCompositionError(str(exc)) from exc
    lock_path = PROJECT_ROOT.joinpath(
        *_QUALIFICATION_COMPOSITION_LOCK_BASE.split("/")
    ).joinpath(f"{qualification_run_id}.lock")
    try:
        ensure_directory_tree(lock_path.parent)
        lock_manager = exclusive_lock_file(lock_path)
        lock_manager.__enter__()
    except (OSError, TypeError, ValueError) as exc:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_COMPOSITION_GUARD_FAILED"
        ) from exc
    try:
        # Recheck after waiting: a caller that blocked behind another process
        # must begin from the complete successor it published.
        _assert_namespace(qualification_run_id)
        yield
    except BaseException as primary:
        try:
            lock_manager.__exit__(
                type(primary), primary, primary.__traceback__
            )
        except BaseException as cleanup_error:
            try:
                primary.add_note(
                    "V32_QUALIFICATION_COMPOSITION_GUARD_RELEASE_FAILED:"
                    f"{type(cleanup_error).__name__}"
                )
            except (AttributeError, TypeError):
                pass
        raise
    else:
        try:
            lock_manager.__exit__(None, None, None)
        except (OSError, TypeError, ValueError) as exc:
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_COMPOSITION_GUARD_FAILED"
            ) from exc


_V32_QUALIFICATION_APPEND_ONLY_MATERIAL_BOUNDARIES = frozenset(
    {
        "QUALIFICATION_MAILBOX_INITIALIZED",
        "QUALIFICATION_PROPOSAL_ENQUEUED",
        "QUALIFICATION_PROPOSAL_CONSUMED",
        "QUALIFICATION_SELECTION_ENQUEUED",
        "QUALIFICATION_SELECTION_CONSUMED",
    }
)
_V32_QUALIFICATION_READ_ONLY_MATERIAL_BOUNDARIES = frozenset(
    {
        "NO_ADVANCE_AWAITING_PROPOSAL",
        "NO_ADVANCE_AWAITING_SELECTION",
        "NO_ADVANCE_MATERIAL_COMPLETE",
        "NO_ADVANCE_NO_PROGRESS",
    }
)


def _is_v32_qualification_append_only_material_boundary_v1(
    boundary: str,
) -> bool:
    return bool(
        boundary.startswith("QUALIFICATION_MATERIAL_PERSISTED:")
        or boundary in _V32_QUALIFICATION_APPEND_ONLY_MATERIAL_BOUNDARIES
    )


def _advance_v32_qualification_material_burst_v1(
    materializer: LocalV32QualificationMaterializer,
) -> Mapping[str, Any]:
    """Own one exact graph-verification scope for the bounded wake."""

    with materializer.verification_scope():
        return _advance_v32_qualification_material_burst_within_scope_v1(
            materializer
        )


def _advance_v32_qualification_material_burst_within_scope_v1(
    materializer: LocalV32QualificationMaterializer,
) -> Mapping[str, Any]:
    """Run only append-only material substages until an external boundary."""

    burst_boundaries: list[str] = []
    append_only_boundaries: list[str] = []
    material: Mapping[str, Any] | None = None
    for _ in range(MAX_ANALYSIS_SUBSTAGES_PER_WAKE):
        material = materializer.advance_once()
        boundary = material.get("boundary_kind")
        status = material.get("status")
        state_changed = material.get("state_changed")
        if (
            not isinstance(boundary, str)
            or not boundary
            or status not in {"PENDING", "AWAITING_AGENT", "READY"}
            or not isinstance(state_changed, bool)
        ):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_MATERIAL_BURST_RESULT_INVALID"
            )
        probe_boundary = boundary.startswith(
            "QUALIFICATION_MONITOR_PROBE_"
        )
        append_only_boundary = (
            _is_v32_qualification_append_only_material_boundary_v1(boundary)
        )
        read_only_boundary = (
            boundary in _V32_QUALIFICATION_READ_ONLY_MATERIAL_BOUNDARIES
        )
        if state_changed is True and not (
            append_only_boundary or probe_boundary
        ):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID"
            )
        if state_changed is False and not (
            read_only_boundary or probe_boundary
        ):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID"
            )
        if (
            status == "AWAITING_AGENT"
            and boundary
            not in {
                "NO_ADVANCE_AWAITING_PROPOSAL",
                "NO_ADVANCE_AWAITING_SELECTION",
            }
        ) or (
            status == "READY"
            and boundary != "NO_ADVANCE_MATERIAL_COMPLETE"
        ) or (
            status == "PENDING"
            and boundary
            in {
                "NO_ADVANCE_AWAITING_PROPOSAL",
                "NO_ADVANCE_AWAITING_SELECTION",
                "NO_ADVANCE_MATERIAL_COMPLETE",
            }
        ):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID"
            )
        burst_boundaries.append(boundary)
        if state_changed is True and append_only_boundary:
            append_only_boundaries.append(boundary)
        if (
            status in {"AWAITING_AGENT", "READY"}
            or probe_boundary
        ):
            break
        if state_changed is not True:
            break
    if material is None:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_MATERIAL_BURST_EMPTY"
        )
    return {
        **dict(material),
        "burst_step_count": len(burst_boundaries),
        "burst_step_limit": MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
        "burst_step_boundaries": burst_boundaries,
        "internal_append_only_substage_count": len(append_only_boundaries),
        "internal_append_only_substage_boundaries": append_only_boundaries,
        "qualification_probe_boundary_completed": str(
            material["boundary_kind"]
        ).startswith("QUALIFICATION_MONITOR_PROBE_")
        and material["state_changed"] is True,
        "burst_stop_reason": (
            "AGENT_REQUIRED"
            if material["status"] == "AWAITING_AGENT"
            else "PROBE_BOUNDARY_COMPLETED"
            if str(material["boundary_kind"]).startswith(
                "QUALIFICATION_MONITOR_PROBE_"
            )
            else "MATERIAL_READY"
            if material["status"] == "READY"
            else "NO_PROGRESS"
            if material["state_changed"] is False
            else "SUBSTAGE_LIMIT_REACHED"
        ),
    }


def _v32_qualification_material_burst_stops_before_controller_v1(
    material: Mapping[str, Any],
) -> bool:
    """Keep one wake from crossing a committed material/probe boundary."""

    return bool(
        material.get("state_changed") is True
        or material.get("status") == "AWAITING_AGENT"
        or material.get("burst_stop_reason")
        in {"SUBSTAGE_LIMIT_REACHED", "NO_PROGRESS"}
    )


def _project_store_binding(
    *, store_root: str, binding: Mapping[str, Any] | None
) -> dict[str, str] | None:
    if binding is None:
        return None
    return {
        "path": f"{store_root}/{binding['relative_ref']}",
        "schema_id": str(binding["schema_id"]),
        "digest_field": str(binding["digest_field"]),
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def _project_store_inventory(
    *, store_root: str, bindings: list[Mapping[str, Any]]
) -> list[dict[str, str]]:
    return [
        dict(_project_store_binding(store_root=store_root, binding=binding))
        for binding in bindings
    ]


def _prefix_scan_failure_codes(
    prefix: str, exc: BaseException
) -> tuple[str, ...]:
    # The scan exception is raised while handling the original materializer
    # exception, so Python links the latter as ``__context__``.  Persist only
    # the owning scan marker here; the original typed chain is already bound in
    # ``failure_codes`` and must not masquerade as the scan's own cause.
    del exc
    return (f"{prefix}_PREFIX_REPLAY_FAILED",)


def _load_authority(
    *, target_run_id: str, qualification_run_id: str
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], dict[str, str]]:
    target, qualification = _ids(target_run_id, qualification_run_id)
    try:
        replay = load_v32_qualification_phase_a_authority(
            PROJECT_ROOT,
            expected_target_run_id=target,
            expected_qualification_run_id=qualification,
        )
    except V32CurrentResearchAuthorityError as exc:
        reason = str(exc)
        if "POSTCOMMIT" in reason or "workspace_freeze" in reason:
            reason = f"V32_QUALIFICATION_POSTCOMMIT_REPLAY_FAILED:{reason}"
        raise V32QualificationCompositionError(
            f"V32_QUALIFICATION_PHASE_A_FULL_REPLAY_FAILED:{reason}"
        ) from exc
    return (
        dict(replay["qualification_authority"]),
        dict(replay["qualification_authority_binding"]),
        dict(replay["experiment_contract"]),
        dict(replay["runtime_paths"]),
    )


def _replay_controller_before_agent_v1(
    *,
    authority: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    contract: Mapping[str, Any],
    paths: Mapping[str, str],
) -> tuple[Mapping[str, Any], LocalV32ActualCapabilityEvidenceStore]:
    clock = build_v32_system_clock_v1()
    evidence = LocalV32ActualCapabilityEvidenceStore(
        PROJECT_ROOT, paths["evidence"]
    )
    projection = build_v32_active_authority_projection(
        run_id=str(authority["run_id"]),
        recorded_at=str(authority["recorded_at"]),
        experiment_contract_digest=str(contract[CONTRACT_DIGEST_FIELD]),
        governing_authority_binding={
            "relative_ref": authority_binding["path"],
            **{
                key: authority_binding[key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        },
    )
    capture = V32OkxPublicMarkCaptureAdapter()
    probe_store = LocalV32QualificationMonitorProbeStore(
        PROJECT_ROOT / paths["probe"], capture_port=capture, clock=clock
    )
    ports = {
        "PUBLIC_SOURCE": V32PublicSourceQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            source_store_root=paths["source"],
            run_store_root=paths["run_source"],
            source_qualification_id=f"{authority['run_id']}:public-source",
            active_authority_projection=projection,
            transport=V32OkxPublicBundleTransport(),
            clock=clock,
        ),
        "CURRENT_CODEX": V32CurrentCodexQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            mailbox_store_root=paths["mailbox"],
            clock=clock,
        ),
        "OUTCOME_MONITOR": V32OutcomeMonitorQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            probe_store_root=paths["probe"],
            capture_port=capture,
            clock=clock,
        ),
    }
    checkpoint = replay_v32_actual_capability_qualification_controller_v1(
        controller_store=LocalV32ActualCapabilityQualificationControllerStore(
            PROJECT_ROOT, paths["controller"]
        ),
        evidence_store=evidence,
        controller_id=f"qualification-controller::{authority['run_id']}",
        qualification_id=f"qualification::{authority['run_id']}",
        qualification_authority=authority,
        qualification_authority_binding=authority_binding,
        attempt_ports=ports,
    )
    if checkpoint is None:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_CONTROLLER_MISSING"
        )
    if checkpoint.get("status") == "FAILED_CLOSED":
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_CONTROLLER_FAILED_CLOSED"
        )
    states = checkpoint.get("capability_states")
    if (
        checkpoint.get("status") != "RUNNING"
        or not isinstance(states, Mapping)
        or states.get("PUBLIC_SOURCE", {}).get("status") != "COMPLETE"
        or states.get("CURRENT_CODEX", {}).get("status") != "PENDING"
        or states.get("OUTCOME_MONITOR", {}).get("status") != "READY"
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_CONTROLLER_STATE_INVALID"
        )
    reservation = evidence.load_attempt_reservation("CURRENT_CODEX")
    if (
        reservation is None
        or reservation.get("reservation_binding")
        != states["CURRENT_CODEX"].get("reservation_binding")
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_CURRENT_CODEX_RESERVATION_DRIFT"
        )
    return checkpoint, evidence


def _replayed_phase_a_result(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    try:
        replay = load_v32_qualification_phase_a_authority(
            PROJECT_ROOT,
            expected_target_run_id=target_run_id,
            expected_qualification_run_id=qualification_run_id,
        )
    except V32CurrentResearchAuthorityError as exc:
        raise V32QualificationCompositionError(
            f"V32_QUALIFICATION_PHASE_A_FULL_REPLAY_FAILED:{exc}"
        ) from exc
    return {
        **replay,
        "status": "QUALIFICATION_AUTHORITY_READY",
        "support_document_bindings": replay["runtime_manifest"][
            "support_document_bindings"
        ],
        "current_pointer_written": False,
        "network_calls": 0,
        "authority_boundary": "PUBLIC_LOCAL_NON_EXECUTABLE",
        "phase_a_recovery_status": "EXISTING_FULL_REPLAY",
    }


def prepare_v32_qualification_from_committed_workspace_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Replay an existing legacy qualification; never create a new one."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    paths = _runtime_paths(qualification)
    runtime_path = PROJECT_ROOT.joinpath(*Path(paths["root"]).parts)
    if runtime_path.exists() or runtime_path.is_symlink():
        return _replayed_phase_a_result(
            target_run_id=target,
            qualification_run_id=qualification,
        )
    raise V32QualificationCompositionError(
        "V32_LEGACY_NEW_QUALIFICATION_ROUTE_RETIRED"
    )


def run_v32_postcommit_regressions_for_qualification_once_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Reject creation of new run-scoped legacy double-suite receipts.

    Historical receipt formats remain verifiable through their dedicated readers.
    Current code testing is deliberately independent of run identity and uses
    ``tools/run_theory_tests.py``.
    """

    _ids(target_run_id, qualification_run_id)
    raise V32QualificationCompositionError(
        "V32_POSTCOMMIT_LEGACY_WRITER_RETIRED_USE_UNIQUE_LOCAL_TEST_RUNNER"
    )


def _advance_v32_qualification_once_unguarded_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Advance one controller/probe boundary and a bounded material substage burst."""

    authority, authority_binding, contract, paths = _load_authority(
        target_run_id=target_run_id, qualification_run_id=qualification_run_id
    )
    clock = build_v32_system_clock_v1()
    evidence = LocalV32ActualCapabilityEvidenceStore(
        PROJECT_ROOT, paths["evidence"]
    )
    projection = build_v32_active_authority_projection(
        run_id=qualification_run_id,
        recorded_at=str(authority["recorded_at"]),
        experiment_contract_digest=str(contract[CONTRACT_DIGEST_FIELD]),
        governing_authority_binding={
            "relative_ref": authority_binding["path"],
            **{key: authority_binding[key] for key in (
                "schema_id", "digest_field", "semantic_digest", "physical_sha256"
            )},
        },
    )
    controller_store = LocalV32ActualCapabilityQualificationControllerStore(
        PROJECT_ROOT, paths["controller"]
    )
    checkpoint = controller_store.load()
    recovered_material_failure = controller_store.load_materialization_failure()
    if recovered_material_failure is not None:
        receipt, _ = recovered_material_failure
        result = controller_store.seal_materialization_failure(
            materialization_stage=str(receipt["materialization_stage"]),
            failure_codes=tuple(receipt["failure_codes"]),
            failure_time_status=str(receipt["failure_time_status"]),
            failed_at=receipt["failed_at"],
            last_known_at=str(receipt["last_known_at"]),
            qualification_authority_binding=authority_binding,
            attempt_reservation_binding=receipt["attempt_reservation_binding"],
            material_store_root=str(receipt["material_store_root"]),
            material_prefix_status=str(receipt["material_prefix_status"]),
            material_scan_failure_codes=tuple(
                receipt["material_scan_failure_codes"]
            ),
            material_predecessor_bindings=receipt[
                "material_predecessor_bindings"
            ],
            mailbox_store_root=str(receipt["mailbox_store_root"]),
            mailbox_prefix_status=str(receipt["mailbox_prefix_status"]),
            mailbox_scan_failure_codes=tuple(
                receipt["mailbox_scan_failure_codes"]
            ),
            mailbox_prefix_bindings=receipt["mailbox_prefix_bindings"],
            probe_store_root=str(receipt["probe_store_root"]),
            probe_prefix_status=str(receipt["probe_prefix_status"]),
            probe_scan_failure_codes=tuple(
                receipt["probe_scan_failure_codes"]
            ),
            probe_schedule_binding=receipt["probe_schedule_binding"],
        )
        _assert_namespace(qualification_run_id)
        return result
    capture = V32OkxPublicMarkCaptureAdapter()
    probe_store = LocalV32QualificationMonitorProbeStore(
        PROJECT_ROOT / paths["probe"], capture_port=capture, clock=clock
    )
    ports = {
        "PUBLIC_SOURCE": V32PublicSourceQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            source_store_root=paths["source"],
            run_store_root=paths["run_source"],
            source_qualification_id=f"{qualification_run_id}:public-source",
            active_authority_projection=projection,
            transport=V32OkxPublicBundleTransport(),
            clock=clock,
        ),
        "CURRENT_CODEX": V32CurrentCodexQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            mailbox_store_root=paths["mailbox"],
            clock=clock,
        ),
        "OUTCOME_MONITOR": V32OutcomeMonitorQualificationAttemptPort(
            project_root=PROJECT_ROOT,
            evidence_store=evidence,
            probe_store_root=paths["probe"],
            capture_port=capture,
            clock=clock,
        ),
    }
    if (
        checkpoint is not None
        and checkpoint["capability_states"]["PUBLIC_SOURCE"]["status"] == "COMPLETE"
        and checkpoint["capability_states"]["CURRENT_CODEX"]["status"] == "PENDING"
        and checkpoint["capability_states"]["OUTCOME_MONITOR"]["status"] == "READY"
    ):
        current_attempt = evidence.load_attempt_reservation("CURRENT_CODEX")
        if current_attempt is None:
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_CURRENT_CODEX_RESERVATION_MISSING"
            )
        material_stage = "MATERIAL_STORE:OPEN"
        material_predecessors: dict[str, dict[str, str]] = {}
        try:
            material_store = LocalV32QualificationMaterialStore(
                PROJECT_ROOT, paths["material"]
            )
            material_stage = "MATERIAL_PREFIX:REPLAY"
            material_predecessors = material_store.predecessor_bindings()
            material_stage = "MATERIALIZER:CONSTRUCT"
            mailbox = LocalV32CurrentRootAgentMailbox(
                PROJECT_ROOT / paths["mailbox"]
            )
            materializer = LocalV32QualificationMaterializer(
                project_root=PROJECT_ROOT,
                authority_root_relative_ref=paths["root"],
                material_store=material_store,
                source_store=LocalV32CycleSourceAdmissionStore(
                    PROJECT_ROOT / paths["source"]
                ),
                admitted_source_store=LocalV32CycleSourceAdmissionStore(
                    PROJECT_ROOT / paths["run_source"]
                ),
                mailbox=mailbox,
                probe_store=probe_store,
                qualification_authority=authority,
                qualification_authority_binding=authority_binding,
                current_codex_attempt_reservation=current_attempt["reservation"],
                active_authority_projection=projection,
                source_qualification_id=f"{qualification_run_id}:public-source",
                clock=clock,
            )
            material_stage = "MATERIALIZER:ADVANCE"
            material = _advance_v32_qualification_material_burst_v1(
                materializer
            )
        except Exception as exc:
            material_stage = str(
                getattr(
                    exc,
                    "materialization_phase",
                    material_stage,
                )
            )
            # The failed operation may have published a write-once child before
            # raising.  Each recovery scan is isolated: a broken scan is itself
            # durable failure evidence and cannot reopen the same attempt.
            material_predecessors = {}
            material_prefix_status = "UNKNOWN_REPLAY_FAILED"
            material_scan_failure_codes = (
                "MATERIAL_PREFIX_REPLAY_UNAVAILABLE",
            )
            if "material_store" in locals():
                try:
                    material_predecessors = (
                        material_store.predecessor_bindings()
                    )
                    material_prefix_status = "VERIFIED_EXACT"
                    material_scan_failure_codes = ()
                except Exception as scan_exc:
                    material_scan_failure_codes = _prefix_scan_failure_codes(
                        "MATERIAL", scan_exc
                    )

            mailbox_prefix_bindings = []
            mailbox_prefix_status = "UNKNOWN_REPLAY_FAILED"
            mailbox_scan_failure_codes = (
                "MAILBOX_PREFIX_REPLAY_UNAVAILABLE",
            )
            if "mailbox" in locals():
                try:
                    mailbox_prefix_bindings = _project_store_inventory(
                        store_root=paths["mailbox"],
                        bindings=mailbox.json_prefix_inventory_v1(
                            run_id=qualification_run_id, cycle_index=1
                        ),
                    )
                    mailbox_prefix_status = "VERIFIED_EXACT"
                    mailbox_scan_failure_codes = ()
                except Exception as scan_exc:
                    mailbox_scan_failure_codes = _prefix_scan_failure_codes(
                        "MAILBOX", scan_exc
                    )

            probe_schedule_binding = None
            probe_prefix_status = "UNKNOWN_REPLAY_FAILED"
            probe_scan_failure_codes = (
                "PROBE_PREFIX_REPLAY_UNAVAILABLE",
            )
            if "probe_store" in locals():
                try:
                    probe_schedule_binding = _project_store_binding(
                        store_root=paths["probe"],
                        binding=probe_store.schedule_binding_v1(),
                    )
                    probe_prefix_status = "VERIFIED_EXACT"
                    probe_scan_failure_codes = ()
                except Exception as scan_exc:
                    probe_scan_failure_codes = _prefix_scan_failure_codes(
                        "PROBE", scan_exc
                    )
            try:
                failed_at = clock()
                failure_time_status = "OBSERVED"
                last_known_at = failed_at
            except Exception:
                failure_time_status = "UNKNOWN_CLOCK_UNAVAILABLE"
                failed_at = None
                last_known_at = str(checkpoint["updated_at"])
            result = controller_store.seal_materialization_failure(
                materialization_stage=material_stage,
                failure_codes=stable_v32_materialization_failure_codes_v1(exc),
                failure_time_status=failure_time_status,
                failed_at=failed_at,
                last_known_at=last_known_at,
                qualification_authority_binding=authority_binding,
                attempt_reservation_binding=current_attempt[
                    "reservation_binding"
                ],
                material_store_root=paths["material"],
                material_prefix_status=material_prefix_status,
                material_scan_failure_codes=material_scan_failure_codes,
                material_predecessor_bindings=material_predecessors,
                mailbox_store_root=paths["mailbox"],
                mailbox_prefix_status=mailbox_prefix_status,
                mailbox_scan_failure_codes=mailbox_scan_failure_codes,
                mailbox_prefix_bindings=mailbox_prefix_bindings,
                probe_store_root=paths["probe"],
                probe_prefix_status=probe_prefix_status,
                probe_scan_failure_codes=probe_scan_failure_codes,
                probe_schedule_binding=probe_schedule_binding,
            )
            _assert_namespace(qualification_run_id)
            return result
        if _v32_qualification_material_burst_stops_before_controller_v1(
            material
        ):
            result = {
                "runtime_status": "PENDING",
                "boundary_kind": material["boundary_kind"],
                "material": material,
                "checkpoint": checkpoint,
            }
            _assert_namespace(qualification_run_id)
            return result
    result = advance_v32_actual_capability_qualification_controller_once(
        controller_store=controller_store,
        evidence_store=evidence,
        controller_id=f"qualification-controller::{qualification_run_id}",
        qualification_id=f"qualification::{qualification_run_id}",
        qualification_authority=authority,
        qualification_authority_binding=authority_binding,
        attempt_ports=ports,
        clock=clock,
    )
    _assert_namespace(qualification_run_id)
    return result


def _read_and_claim_v32_qualification_agent_request_unguarded_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Claim the sole currently queued canonical packet for current Codex."""

    authority, authority_binding, contract, paths = _load_authority(
        target_run_id=target_run_id, qualification_run_id=qualification_run_id
    )
    controller_checkpoint, evidence = _replay_controller_before_agent_v1(
        authority=authority,
        authority_binding=authority_binding,
        contract=contract,
        paths=paths,
    )
    current_attempt = evidence.load_attempt_reservation("CURRENT_CODEX")
    if (
        current_attempt is None
        or current_attempt.get("reservation_binding")
        != controller_checkpoint["capability_states"]["CURRENT_CODEX"][
            "reservation_binding"
        ]
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_CURRENT_CODEX_RESERVATION_DRIFT"
        )
    mailbox = LocalV32CurrentRootAgentMailbox(
        PROJECT_ROOT / paths["mailbox"]
    )
    checkpoint = mailbox.load_checkpoint(run_id=qualification_run_id, cycle_index=1)
    pending = mailbox.next_pending_request(run_id=qualification_run_id, cycle_index=1)
    if pending is None:
        raise V32QualificationCompositionError("V32_QUALIFICATION_AGENT_REQUEST_NOT_READY")
    valid_pending = (
        pending.get("stage_status") == "REQUESTED"
        and pending.get("next_action") == "CURRENT_ROOT_CODEX_CLAIM"
    ) or (
        pending.get("stage_status") == "CLAIMED"
        and pending.get("next_action")
        == "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
    )
    if not valid_pending:
        raise V32QualificationCompositionError("V32_QUALIFICATION_AGENT_REQUEST_NOT_READY")
    chain_before = mailbox.load_stage_chain(
        run_id=qualification_run_id, cycle_index=1, stage=str(pending["stage"])
    )
    if (
        chain_before.get("stage_status") != pending.get("stage_status")
        or chain_before.get("checkpoint_digest")
        != checkpoint.get(MAILBOX_CHECKPOINT_DIGEST_FIELD)
        or chain_before.get("request") != pending.get("request")
        or chain_before.get("claim") != pending.get("claim")
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_REQUEST_CHAIN_INVALID"
        )
    authority_packet = (
        chain_before["canonical_packet_original"]
        if pending["stage"] == "PROPOSAL"
        else mailbox.load_stage_chain(
            run_id=qualification_run_id, cycle_index=1, stage="PROPOSAL"
        )["canonical_packet_original"]
    )
    if authority_packet.get("authority_document") != authority:
        raise V32QualificationCompositionError("V32_QUALIFICATION_AGENT_AUTHORITY_DRIFT")
    request = pending["request"]
    orphan_claim = chain_before.get("claim")
    if pending["stage_status"] == "CLAIMED":
        if not isinstance(orphan_claim, Mapping):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_AGENT_CLAIMED_REPLAY_INVALID"
            )
        claim_at = str(orphan_claim["claimed_at"])
        verify_v32_current_codex_attempt_time_v1(
            qualification_authority=authority,
            reservation=current_attempt["reservation"],
            observed_at=claim_at,
        )
        result = build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=checkpoint,
            request=request,
            claim=orphan_claim,
            lossless_context_package=chain_before[
                "lossless_context_package"
            ],
            control_context={
                "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                "stage": pending["stage"],
                "stage_status": "CLAIMED",
                "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
            },
        )
        _assert_namespace(qualification_run_id)
        return result
    if orphan_claim is None:
        claim_at = str(build_v32_system_clock_v1()())
        preview_claim = build_v32_current_root_agent_mailbox_claim_v1(
            request=request, claimed_at=claim_at
        )
    elif isinstance(orphan_claim, Mapping):
        # The immutable claim may have reached disk before the checkpoint CAS.
        # Recovery must use those first bytes and their original boundary time;
        # a new wall-clock value would create a conflicting second claim.
        preview_claim = dict(orphan_claim)
        claim_at = str(preview_claim["claimed_at"])
    else:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_ORPHAN_CLAIM_INVALID"
        )
    verify_v32_current_codex_attempt_time_v1(
        qualification_authority=authority,
        reservation=current_attempt["reservation"],
        observed_at=claim_at,
    )
    preview_checkpoint = claim_v32_current_root_agent_mailbox_request_v1(
        checkpoint=checkpoint,
        request=request,
        claim=preview_claim,
    )
    result = build_v32_current_codex_presentation_envelope_v1(
        mailbox_checkpoint=preview_checkpoint,
        request=request,
        claim=preview_claim,
        lossless_context_package=chain_before["lossless_context_package"],
        control_context={
            "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
            "stage": pending["stage"],
            "stage_status": "CLAIMED",
            "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
        },
    )
    # Namespace replay and every authority/presentation check are complete
    # before the sole durable CAS.  After this call returns, the mailbox store
    # owns verification and exact-tail recovery; this composition performs no
    # fallible reread that could report failure after a successful mutation.
    _assert_namespace(qualification_run_id)
    mailbox.claim_request(
        run_id=qualification_run_id,
        cycle_index=1,
        stage=str(pending["stage"]),
        expected_checkpoint_digest=checkpoint[MAILBOX_CHECKPOINT_DIGEST_FIELD],
        claimed_at=claim_at,
    )
    return result


def _submit_v32_qualification_agent_delivery_unguarded_v1(
    *,
    target_run_id: str,
    qualification_run_id: str,
    stage: str,
    expected_request_digest: str,
    expected_current_codex_presentation_digest: str,
    payload_utf8: str,
) -> Mapping[str, Any]:
    """Submit one current-Codex UTF-8 delivery to the already claimed request."""

    authority, authority_binding, contract, paths = _load_authority(
        target_run_id=target_run_id, qualification_run_id=qualification_run_id
    )
    controller_checkpoint, evidence = _replay_controller_before_agent_v1(
        authority=authority,
        authority_binding=authority_binding,
        contract=contract,
        paths=paths,
    )
    if stage not in {"PROPOSAL", "SELECTION"}:
        raise V32QualificationCompositionError("V32_QUALIFICATION_AGENT_STAGE_INVALID")
    current_attempt = evidence.load_attempt_reservation("CURRENT_CODEX")
    if (
        current_attempt is None
        or current_attempt.get("reservation_binding")
        != controller_checkpoint["capability_states"]["CURRENT_CODEX"][
            "reservation_binding"
        ]
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_CURRENT_CODEX_RESERVATION_DRIFT"
        )
    mailbox = LocalV32CurrentRootAgentMailbox(
        PROJECT_ROOT / paths["mailbox"]
    )
    checkpoint = mailbox.load_checkpoint(run_id=qualification_run_id, cycle_index=1)
    try:
        chain = mailbox.load_stage_chain(
            run_id=qualification_run_id, cycle_index=1, stage=stage
        )
    except V32CurrentRootAgentMailboxStoreError as exc:
        if str(exc) not in {
            "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE",
            "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE",
        }:
            raise
        chain = mailbox.load_verified_recovery_stage_view(
            run_id=qualification_run_id,
            cycle_index=1,
            stage=stage,
        )
    if (
        chain.get("stage_status") == "CLAIMED"
        and isinstance(chain.get("agent_delivery"), Mapping)
        and chain.get("recovery_tail_kind") is None
    ):
        chain = mailbox.load_verified_recovery_stage_view(
            run_id=qualification_run_id,
            cycle_index=1,
            stage=stage,
        )
    if chain["request"].get(REQUEST_DIGEST_FIELD) != expected_request_digest:
        raise V32QualificationCompositionError("V32_QUALIFICATION_REQUEST_DIGEST_DRIFT")
    status = chain.get("stage_status")
    if status not in {"CLAIMED", "DELIVERED"} or (
        chain.get("checkpoint_digest")
        != checkpoint.get(MAILBOX_CHECKPOINT_DIGEST_FIELD)
        or not isinstance(chain.get("claim"), Mapping)
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_PRESENTATION_STATE_INVALID"
        )
    orphan_delivery_recovery = chain.get("recovery_tail_kind") in {
        "DELIVERY_ONLY",
        "DELIVERY_RECEIPT_PRE_CAS",
    }
    if status == "DELIVERED":
        try:
            snapshot = mailbox.load_claimed_stage_snapshot(
                run_id=qualification_run_id,
                cycle_index=1,
                stage=stage,
            )
        except Exception as exc:
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_AGENT_DELIVERY_REPLAY_INVALID"
            ) from exc
        if (
            snapshot.get("request") != chain.get("request")
            or snapshot.get("claim") != chain.get("claim")
            or snapshot.get("lossless_context_package")
            != chain.get("lossless_context_package")
            or not isinstance(chain.get("agent_delivery"), Mapping)
            or not isinstance(chain.get("delivery_receipt"), Mapping)
        ):
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_AGENT_DELIVERY_REPLAY_INVALID"
            )
        presentation_checkpoint = snapshot["mailbox_checkpoint"]
        boundary_at = str(chain["agent_delivery"]["delivered_at"])
    elif orphan_delivery_recovery:
        try:
            snapshot = {
                "mailbox_checkpoint": chain["mailbox_checkpoint"],
                "request": chain["request"],
                "claim": chain["claim"],
                "lossless_context_package": chain[
                    "lossless_context_package"
                ],
            }
            presentation_checkpoint = snapshot["mailbox_checkpoint"]
            boundary_at = str(chain["agent_delivery"]["delivered_at"])
        except Exception as exc:
            raise V32QualificationCompositionError(
                "V32_QUALIFICATION_AGENT_DELIVERY_RECOVERY_VIEW_INVALID"
            ) from exc
    else:
        snapshot = None
        presentation_checkpoint = checkpoint
        boundary_at = build_v32_system_clock_v1()()
    verify_v32_current_codex_attempt_time_v1(
        qualification_authority=authority,
        reservation=current_attempt["reservation"],
        observed_at=boundary_at,
    )
    presentation = build_v32_current_codex_presentation_envelope_v1(
        mailbox_checkpoint=presentation_checkpoint,
        request=(snapshot or chain)["request"],
        claim=(snapshot or chain)["claim"],
        lossless_context_package=(snapshot or chain)[
            "lossless_context_package"
        ],
        control_context={
            "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
            "stage": stage,
            "stage_status": "CLAIMED",
            "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
        },
    )
    if presentation.get(
        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
    ) != expected_current_codex_presentation_digest:
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_PRESENTATION_DIGEST_DRIFT"
        )
    if (
        chain.get("delivery_receipt") is not None
        and chain["delivery_receipt"].get(
            "current_codex_presentation_digest"
        )
        != expected_current_codex_presentation_digest
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_AGENT_PRESENTATION_DIGEST_DRIFT"
        )
    _assert_namespace(qualification_run_id)
    result = mailbox.submit_delivery(
        run_id=qualification_run_id,
        cycle_index=1,
        stage=stage,
        expected_checkpoint_digest=presentation_checkpoint[
            MAILBOX_CHECKPOINT_DIGEST_FIELD
        ],
        current_codex_presentation_envelope=presentation,
        expected_current_codex_presentation_digest=(
            expected_current_codex_presentation_digest
        ),
        delivered_at=boundary_at,
        payload_utf8=payload_utf8,
    )
    return result


def _finalize_v32_target_authority_from_completed_qualification_unguarded_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Retire one COMPLETE qualification through the fixed per-ID namespace."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    _, authority_binding, _, paths = _load_authority(
        target_run_id=target,
        qualification_run_id=qualification,
    )
    controller = LocalV32ActualCapabilityQualificationControllerStore(
        PROJECT_ROOT, paths["controller"]
    ).load()
    if (
        controller is None
        or controller.get("status") != "COMPLETE"
        or controller.get("qualification_run_id") != qualification
        or controller.get("target_run_id") != target
        or controller.get("qualification_authority_binding") != authority_binding
        or not isinstance(controller.get("qualification_receipt_binding"), Mapping)
    ):
        raise V32QualificationCompositionError(
            "V32_QUALIFICATION_COMPLETE_CONTROLLER_REQUIRED"
        )
    times = load_v32_target_finalization_phase_times_if_started(
        project_root=PROJECT_ROOT,
        runtime_root_relative_ref=paths["root"],
        expected_target_run_id=target,
        expected_qualification_run_id=qualification,
        qualification_authority_binding=authority_binding,
        qualification_receipt_binding=controller[
            "qualification_receipt_binding"
        ],
    )
    if times is None:
        clock = build_v32_system_clock_v1()
        times = _acquire_lifecycle_phase_times_v1(
            clock,
            keys=_PHASE_B_TIME_KEYS,
            strict_successors=frozenset({"target_gate_evaluated_at"}),
            not_before=str(controller["updated_at"]),
        )
    result = finalize_v32_target_authority(
        project_root=PROJECT_ROOT,
        runtime_root_relative_ref=paths["root"],
        expected_target_run_id=target,
        expected_qualification_run_id=qualification,
        qualification_authority_binding=authority_binding,
        qualification_receipt_binding=controller[
            "qualification_receipt_binding"
        ],
        phase_times=times,
    )
    _assert_namespace(qualification)
    return result


def advance_v32_qualification_once_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Advance one qualification wake under its sole composition owner."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    with _qualification_composition_guard_v1(qualification):
        return _advance_v32_qualification_once_unguarded_v1(
            target_run_id=target,
            qualification_run_id=qualification,
        )


def read_and_claim_v32_qualification_agent_request_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Claim the sole Agent request under the same composition owner."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    with _qualification_composition_guard_v1(qualification):
        return _read_and_claim_v32_qualification_agent_request_unguarded_v1(
            target_run_id=target,
            qualification_run_id=qualification,
        )


def submit_v32_qualification_agent_delivery_v1(
    *,
    target_run_id: str,
    qualification_run_id: str,
    stage: str,
    expected_request_digest: str,
    expected_current_codex_presentation_digest: str,
    payload_utf8: str,
) -> Mapping[str, Any]:
    """Submit one Agent delivery under the same composition owner."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    with _qualification_composition_guard_v1(qualification):
        return _submit_v32_qualification_agent_delivery_unguarded_v1(
            target_run_id=target,
            qualification_run_id=qualification,
            stage=stage,
            expected_request_digest=expected_request_digest,
            expected_current_codex_presentation_digest=(
                expected_current_codex_presentation_digest
            ),
            payload_utf8=payload_utf8,
        )


def finalize_v32_target_authority_from_completed_qualification_v1(
    *, target_run_id: str, qualification_run_id: str
) -> Mapping[str, Any]:
    """Finalize one COMPLETE qualification under its composition owner."""

    target, qualification = _ids(target_run_id, qualification_run_id)
    with _qualification_composition_guard_v1(qualification):
        return (
            _finalize_v32_target_authority_from_completed_qualification_unguarded_v1(
                target_run_id=target,
                qualification_run_id=qualification,
            )
        )


__all__ = [
    "V32QualificationCompositionError",
    "advance_v32_qualification_once_v1",
    "finalize_v32_target_authority_from_completed_qualification_v1",
    "prepare_v32_qualification_from_committed_workspace_v1",
    "read_and_claim_v32_qualification_agent_request_v1",
    "run_v32_postcommit_regressions_for_qualification_once_v1",
    "submit_v32_qualification_agent_delivery_v1",
]
