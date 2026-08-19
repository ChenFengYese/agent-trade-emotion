"""Sole production composition for one V3.2 prospective target run.

The wake entry deliberately accepts only the project root and expected target
identity.  Two narrower current-root Codex entries additionally claim the one
queued request or submit one explicit UTF-8 payload.  Every entry first replays
the complete current authority chain and already-published sole genesis.  The
Agent entries then bind their one mailbox mutation to an unchanged active
analysis permit; the wake entry constructs the fixed runtime ports.

Construction performs no network request.  The only objects with a public
network capability are the source collector and outcome capture adapter, and
the Application router can invoke only the lane selected by the durable
Supervisor checkpoint.  This module has no account, credential, order,
portfolio, paper-trading, live-trading, or execution adapter.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..application.v32_prospective_runtime import (
    V32ProspectiveRuntimeError,
    route_v32_prospective_wake_v1,
    verify_v32_active_analysis_agent_window_v1,
)
from ..domain.contracts.canonical import load_json_strict, verify_self_digest
from ..domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
)
from ..domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
)
from ..domain.v32_agent_lifecycle import PROPOSAL_SUPPORT_SPECS
from ..domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_SCHEMA_ID,
    REQUEST_DIGEST_FIELD,
    STAGES as AGENT_STAGES,
    build_v32_current_codex_presentation_envelope_v1,
    build_v32_current_root_agent_mailbox_claim_v1,
    claim_v32_current_root_agent_mailbox_request_v1,
    verify_v32_current_codex_presentation_envelope_v1,
)
from ..domain.v32_cycle_source_admission import (
    build_v32_active_authority_projection,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
)
from ..infrastructure.v32_analysis_material_adapter import (
    LocalV32AnalysisMaterialAdapter,
    LocalV32NoRevisionInputMaterialReader,
)
from ..infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
)
from ..infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from ..infrastructure.v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)
from ..infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from ..infrastructure.v32_dynamic_store import LocalV32DynamicStore
from ..infrastructure.v32_local_analysis_lane import LocalV32AnalysisLane
from ..infrastructure.v32_local_audit_lane import LocalV32BoundaryAuditLane
from ..infrastructure.v32_local_outcome_lane import LocalV32OutcomeLane
from ..infrastructure.v32_okx_public_bundle_transport import (
    V32OkxPublicBundleTransport,
)
from ..infrastructure.v32_okx_public_outcome_adapter import (
    V32OkxPublicMarkCaptureAdapter,
)
from ..infrastructure.v32_outcome_tick_store import LocalV32OutcomeTickStore
from ..infrastructure.v32_public_source_collector import (
    V32RawFirstOkxPublicBundleCollector,
)
from ..infrastructure.v32_recovery_supervision_store import (
    LocalV32RecoverySupervisionStore,
)
from ..infrastructure.v32_read_only_status import (
    read_v32_read_only_status_snapshot_v1,
)
from ..infrastructure.v32_run_control_store import LocalV32RunControlStore
from ..infrastructure.v32_runtime_clock import build_v32_system_clock_v1
from ..infrastructure.v32_terminal_seal_store import LocalV32TerminalSealStore
from ..infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from .v32_target_run_composition import (
    replay_v32_target_run_from_current_authority_v1,
)


class V32TargetWakeCompositionError(ValueError):
    """The sole target wake could not be composed from frozen local state."""


_GLOBAL_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_RELATIVE_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_DIRECT_SUPPORT_ROLES = {
    "association_preregistration_digest": "association_preregistration",
    "authorized_revision_support_bundle_digest": (
        "authorized_revision_support_bundle"
    ),
    "clock_policy_digest": "clock_and_tick_policy",
    "evaluation_contract_digest": "evaluation_contract",
    "outcome_adapter_contract_digest": "outcome_adapter_contract",
    "recovery_supervision_policy_digest": "recovery_supervision_policy",
    "twelve_axis_source_registry_digest": "twelve_axis_source_registry",
}
_REVISION_COMPONENT_ROLES = frozenset(
    {
        "context_compaction_policy",
        "unknown_subjective_policy",
        "data_gap_manual_policy",
        "cycle_audit_policy",
        "environment_capability_profile",
    }
)
_DYNAMIC_SUPPORT_ROLES = frozenset(
    {
        "active_authority_projection",
        "experiment_contract",
        "timeframe_context_state",
        "agent_market_graph_view",
        "cycle_source_admission",
    }
)
_STATIC_SUPPORT_ROLES = frozenset(PROPOSAL_SUPPORT_SPECS).difference(
    _DYNAMIC_SUPPORT_ROLES
)
_SOURCE_STORE_DIRECTORY = "v32-public-source-store-v1"


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_PROJECT_ROOT_SYMLINK_FORBIDDEN"
            )
        project = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_PROJECT_ROOT_INVALID"
        ) from exc
    if not project.is_dir():
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_PROJECT_ROOT_INVALID"
        )
    return project


def _contained_file(project: Path, relative_ref: Any, code: str) -> Path:
    if not isinstance(relative_ref, str) or not relative_ref:
        raise V32TargetWakeCompositionError(code)
    lexical = PurePosixPath(relative_ref)
    if (
        "\\" in relative_ref
        or lexical.is_absolute()
        or lexical.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V32TargetWakeCompositionError(code)
    current = project
    try:
        for part in lexical.parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise V32TargetWakeCompositionError(code)
        target = current.resolve(strict=True)
        target.relative_to(project)
    except V32TargetWakeCompositionError:
        raise
    except (OSError, ValueError) as exc:
        raise V32TargetWakeCompositionError(code) from exc
    if target.is_symlink() or not target.is_file():
        raise V32TargetWakeCompositionError(code)
    return target


def _read_exact_bound_document(
    *,
    project: Path,
    binding_value: Any,
    schema_id: str,
    digest_field: str,
    code: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(binding_value, Mapping):
        raise V32TargetWakeCompositionError(code)
    fields = set(binding_value)
    if fields == _GLOBAL_BINDING_FIELDS:
        relative_ref = binding_value.get("path")
        reference_field = "path"
    elif fields == _RELATIVE_BINDING_FIELDS:
        relative_ref = binding_value.get("relative_ref")
        reference_field = "relative_ref"
    else:
        raise V32TargetWakeCompositionError(code)
    if (
        binding_value.get("schema_id") != schema_id
        or binding_value.get("digest_field") != digest_field
    ):
        raise V32TargetWakeCompositionError(code)
    path = _contained_file(project, relative_ref, code)
    payload = path.read_bytes()
    try:
        document = load_json_strict(path)
        semantic_digest = verify_self_digest(document, digest_field)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise V32TargetWakeCompositionError(code) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_id") != schema_id
        or semantic_digest != binding_value.get("semantic_digest")
        or hashlib.sha256(payload).hexdigest()
        != binding_value.get("physical_sha256")
    ):
        raise V32TargetWakeCompositionError(code)
    binding = {
        reference_field: str(relative_ref),
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic_digest,
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }
    return document, binding


def _load_verified_analysis_materials(
    *, project: Path, replay: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Reopen exact bytes only after the complete authority loader succeeded."""

    projection = replay.get("authority_projection")
    if not isinstance(projection, Mapping):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_AUTHORITY_PROJECTION_MISSING"
        )
    manifest = projection.get("manifest")
    if not isinstance(manifest, Mapping):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_MANIFEST_MISSING"
        )
    theory, theory_binding = _read_exact_bound_document(
        project=project,
        binding_value=manifest.get("theory_semantic_document_binding"),
        schema_id=THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID,
        digest_field=THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD,
        code="V32_TARGET_WAKE_THEORY_MATERIAL_INVALID",
    )
    manifest_supports = manifest.get("support_document_bindings")
    if not isinstance(manifest_supports, Mapping):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_SUPPORT_BINDINGS_INVALID"
        )

    documents: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, str]] = {}
    for manifest_role, analysis_role in _DIRECT_SUPPORT_ROLES.items():
        try:
            schema_id, digest_field = PROPOSAL_SUPPORT_SPECS[analysis_role]
        except KeyError as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_SUPPORT_SPEC_INVALID"
            ) from exc
        document, binding = _read_exact_bound_document(
            project=project,
            binding_value=manifest_supports.get(manifest_role),
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"V32_TARGET_WAKE_SUPPORT_INVALID:{analysis_role}",
        )
        documents[analysis_role] = document
        bindings[analysis_role] = binding

    rows = documents["authorized_revision_support_bundle"].get("components")
    if not isinstance(rows, list):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_REVISION_SUPPORT_SET_INVALID"
        )
    component_bindings: dict[str, Any] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"role", "binding"}
            or row.get("role") in component_bindings
        ):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_REVISION_SUPPORT_SET_INVALID"
            )
        component_bindings[str(row["role"])] = row["binding"]
    if set(component_bindings) != _REVISION_COMPONENT_ROLES:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_REVISION_SUPPORT_SET_INVALID"
        )
    for role in sorted(_REVISION_COMPONENT_ROLES):
        schema_id, digest_field = PROPOSAL_SUPPORT_SPECS[role]
        document, binding = _read_exact_bound_document(
            project=project,
            binding_value=component_bindings[role],
            schema_id=schema_id,
            digest_field=digest_field,
            code=f"V32_TARGET_WAKE_REVISION_SUPPORT_INVALID:{role}",
        )
        documents[role] = document
        bindings[role] = binding
    if set(documents) != _STATIC_SUPPORT_ROLES or set(bindings) != _STATIC_SUPPORT_ROLES:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_ANALYSIS_SUPPORT_SET_INVALID"
        )
    if replay.get("cycle_audit_policy") != documents["cycle_audit_policy"]:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_AUDIT_POLICY_REPLAY_MISMATCH"
        )
    return {
        "theory_semantic_document": theory,
        "theory_semantic_document_binding": theory_binding,
        "support_documents": documents,
        "support_bindings": bindings,
    }


def _active_authority_projection(replay: Mapping[str, Any]) -> Mapping[str, Any]:
    projection = replay["authority_projection"]
    authority = projection["authority"]
    contract = projection["experiment_contract"]
    global_binding = replay["global_source_bindings"]["authority"]
    if not isinstance(global_binding, Mapping) or set(global_binding) != _GLOBAL_BINDING_FIELDS:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_GOVERNING_AUTHORITY_BINDING_INVALID"
        )
    return build_v32_active_authority_projection(
        run_id=str(authority["run_id"]),
        recorded_at=str(authority["recorded_at"]),
        experiment_contract_digest=str(
            contract[EXPERIMENT_CONTRACT_DIGEST_FIELD]
        ),
        governing_authority_binding={
            "relative_ref": str(global_binding["path"]),
            "schema_id": str(global_binding["schema_id"]),
            "digest_field": str(global_binding["digest_field"]),
            "semantic_digest": str(global_binding["semantic_digest"]),
            "physical_sha256": str(global_binding["physical_sha256"]),
        },
    )


class _AnalysisSystemClock:
    """Translate the one internal SystemUTC clock to the analysis-lane port."""

    __slots__ = ("_clock",)

    def __init__(self, clock: Any) -> None:
        self._clock = clock

    def timestamp(self, *, boundary: str, permit: Mapping[str, Any]) -> str:
        if not isinstance(boundary, str) or not isinstance(permit, Mapping):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_ANALYSIS_CLOCK_REQUEST_INVALID"
            )
        return str(self._clock())


class _OutcomeDatetimeSystemClock:
    """Expose the internal SystemUTC clock in the outcome adapter's type."""

    __slots__ = ("_clock",)

    def __init__(self, clock: Any) -> None:
        self._clock = clock

    def __call__(self) -> datetime:
        value = str(self._clock())
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_OUTCOME_CLOCK_INVALID"
            ) from exc
        if parsed.tzinfo is None:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_OUTCOME_CLOCK_INVALID"
            )
        return parsed


def _qualification_id(*, run_id: str, cycle_index: int) -> str:
    identity = hashlib.sha256(run_id.encode("utf-8", errors="strict")).hexdigest()
    return f"v32-source-q-{identity}-{cycle_index:04d}"


def _current_codex_presentation_from_routed_wake(
    result: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the exact bounded Agent envelope without adding a wrapper."""

    candidate: Any = result
    if result.get("schema_id") != CURRENT_CODEX_PRESENTATION_SCHEMA_ID:
        candidate = result.get("external_action_request")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("schema_id")
        != CURRENT_CODEX_PRESENTATION_SCHEMA_ID
    ):
        return None
    verify_v32_current_codex_presentation_envelope_v1(candidate)
    return candidate


def _load_verified_target_context(
    *,
    project_root: Path,
    expected_run_id: str,
) -> tuple[Path, Mapping[str, Any], Path]:
    """Replay the complete target authority/genesis before exposing a run root."""

    project = _project_root(project_root)

    # The owning replay runs the complete old+current authority loader, exact
    # five-source byte replay, sole pointer replay, and genesis replay.  It is
    # deliberately the first stateful dependency touched by every public entry.
    replay = replay_v32_target_run_from_current_authority_v1(
        project_root=project,
        expected_run_id=expected_run_id,
    )
    if (
        replay.get("full_loader_verified") is not True
        or replay.get("replay_only") is not True
        or replay.get("state_mutation_count") != 0
        or replay.get("network_request_count") != 0
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_GENESIS_PREFLIGHT_INVALID"
        )
    projection = replay.get("authority_projection")
    if (
        not isinstance(projection, Mapping)
        or projection.get("authority", {}).get("run_id") != expected_run_id
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_RUN_SCOPE_INVALID"
        )
    try:
        supplied_run_root = Path(str(replay["run_root"])).absolute()
        if supplied_run_root.is_symlink():
            raise V32TargetWakeCompositionError(
                "V32_TARGET_WAKE_RUN_ROOT_INVALID"
            )
        run_root = supplied_run_root.resolve(strict=True)
        run_root.relative_to(project)
        expected_root = (
            project
            / ".runtime"
            / "theory-paper-v32"
            / "runs"
            / expected_run_id
        ).resolve(strict=True)
    except (KeyError, OSError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_RUN_ROOT_INVALID"
        ) from exc
    if not run_root.is_dir() or run_root != expected_root:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_WAKE_RUN_ROOT_INVALID"
        )
    return project, replay, run_root


def _load_active_target_agent_boundary(
    *,
    supervisor_store: LocalV32TickSupervisorStore,
    outcome_store: LocalV32OutcomeTickStore,
    expected_run_id: str,
    observed_at: str,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    int,
    Mapping[str, Any],
]:
    """Load one stable ANALYSIS_TICK permit and bind it to its exact cycle."""

    try:
        checkpoint = supervisor_store.load_checkpoint(run_id=expected_run_id)
        permit_digest = checkpoint.get("active_permit_digest")
        if not isinstance(permit_digest, str):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_ANALYSIS_PERMIT_REQUIRED"
            )
        permit = supervisor_store.load_permit(
            run_id=expected_run_id, permit_digest=permit_digest
        )
        predecessor = supervisor_store.load_checkpoint_by_digest(
            run_id=expected_run_id,
            checkpoint_digest=str(
                permit["supervisor_checkpoint_digest_before_permit"]
            ),
        )
        schedule_sets = outcome_store.load_schedule_sets(
            run_id=expected_run_id
        )
        window = verify_v32_active_analysis_agent_window_v1(
            run_id=expected_run_id,
            supervisor_checkpoint=checkpoint,
            active_permit=permit,
            predecessor_checkpoint=predecessor,
            schedule_sets=schedule_sets,
            observed_at=observed_at,
        )
        cycle_index = int(window["analysis_cycle_index"])
        stable_checkpoint = supervisor_store.load_checkpoint(
            run_id=expected_run_id
        )
    except V32TargetWakeCompositionError:
        raise
    except V32ProspectiveRuntimeError as exc:
        raise V32TargetWakeCompositionError(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_REPLAY_INVALID"
        ) from exc
    if dict(stable_checkpoint) != dict(checkpoint):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_BOUNDARY_CHANGED"
        )
    return checkpoint, permit, predecessor, cycle_index, window


def _assert_target_agent_boundary_unchanged(
    *,
    supervisor_store: LocalV32TickSupervisorStore,
    outcome_store: LocalV32OutcomeTickStore,
    expected_run_id: str,
    observed_at: str,
    checkpoint_before: Mapping[str, Any],
    permit_before: Mapping[str, Any],
    predecessor_before: Mapping[str, Any],
    cycle_index_before: int,
    window_before: Mapping[str, Any],
) -> Mapping[str, Any]:
    (
        checkpoint_after,
        permit_after,
        predecessor_after,
        cycle_index_after,
        window_after,
    ) = (
        _load_active_target_agent_boundary(
            supervisor_store=supervisor_store,
            outcome_store=outcome_store,
            expected_run_id=expected_run_id,
            observed_at=observed_at,
        )
    )
    if (
        dict(checkpoint_after) != dict(checkpoint_before)
        or dict(permit_after) != dict(permit_before)
        or dict(predecessor_after) != dict(predecessor_before)
        or cycle_index_after != cycle_index_before
        or any(
            window_after.get(field) != window_before.get(field)
            for field in (
                "run_id",
                "analysis_cycle_index",
                "supervisor_checkpoint_digest",
                "predecessor_checkpoint_digest",
                "active_permit_digest",
                "bound_schedule_set_digests",
                "bound_schedule_sets",
                "next_due_at",
                "permit_deadline_at",
            )
        )
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_BOUNDARY_CHANGED"
        )
    return window_after


_PUBLIC_ARTIFACT_BINDING_FIELDS = (
    "relative_ref",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
)


def _agent_boundary_moment(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_TIME_INVALID"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_TIME_INVALID"
        ) from exc
    if parsed.tzinfo is None:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_TIME_INVALID"
        )
    return parsed


def _assert_target_agent_clock_not_regressed(
    *, earlier_at: str, later_at: str
) -> None:
    """Reject a wall-clock rollback across one Agent mutation boundary."""

    if _agent_boundary_moment(later_at) < _agent_boundary_moment(earlier_at):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_CLOCK_REGRESSION"
        )


def _verify_target_agent_request_anchor(
    *,
    dynamic_store: LocalV32DynamicStore,
    expected_run_id: str,
    cycle_index: int,
    stage: str,
    request: Mapping[str, Any],
    mailbox_chain: Mapping[str, Any],
    predecessor_checkpoint: Mapping[str, Any],
    active_permit: Mapping[str, Any],
    window: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Bind one mailbox request to the owning dynamic-cycle artifacts."""

    input_role = "proposal_input" if stage == "PROPOSAL" else "selection_input"
    packet_role = "proposal_packet" if stage == "PROPOSAL" else "selection_packet"
    try:
        dynamic_checkpoint = dynamic_store.load_checkpoint(
            run_id=expected_run_id
        )
        bindings: dict[str, Mapping[str, Any]] = {}
        for role in (
            "supervisor_checkpoint",
            "supervisor_permit",
            input_role,
            packet_role,
        ):
            matches = [
                binding
                for binding in dynamic_checkpoint["artifact_bindings"]
                if binding.get("cycle_index") == cycle_index
                and binding.get("role") == role
            ]
            if len(matches) != 1:
                raise V32TargetWakeCompositionError(
                    f"V32_TARGET_AGENT_DYNAMIC_ANCHOR_MISSING:{role}"
                )
            bindings[role] = matches[0]
        documents = {
            role: dynamic_store.load_artifact(binding)
            for role, binding in bindings.items()
        }
        owning_input_binding = {
            field: bindings[input_role][field]
            for field in _PUBLIC_ARTIFACT_BINDING_FIELDS
        }
        owning_packet_binding = {
            field: bindings[packet_role][field]
            for field in _PUBLIC_ARTIFACT_BINDING_FIELDS
        }
    except V32TargetWakeCompositionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_DYNAMIC_ANCHOR_INVALID"
        ) from exc

    context = request.get("agent_input_context")
    packet = mailbox_chain.get("canonical_packet_original")
    if (
        dynamic_checkpoint.get("status") != "OPEN"
        or dynamic_checkpoint.get("open_cycle_index") != cycle_index
        or dynamic_checkpoint.get("run_id") != expected_run_id
        or documents["supervisor_checkpoint"] != dict(predecessor_checkpoint)
        or documents["supervisor_permit"] != dict(active_permit)
        or not isinstance(context, Mapping)
        or documents[input_role] != dict(context)
        or request.get("agent_input_context_binding") != owning_input_binding
        or context.get("canonical_packet_binding") != owning_packet_binding
        or mailbox_chain.get("request") != request
        or not isinstance(packet, Mapping)
        or documents[packet_role] != dict(packet)
        or request.get("run_id") != expected_run_id
        or request.get("cycle_index") != cycle_index
        or request.get("stage") != stage
        or context.get("run_id") != expected_run_id
        or context.get("cycle_index") != cycle_index
        or context.get("agent_stage") != stage
        or context.get("decision_time")
        != active_permit.get("analysis_decision_at")
        or packet.get("run_id") != expected_run_id
        or packet.get("cycle_index") != cycle_index
        or packet.get("decision_time")
        != active_permit.get("analysis_decision_at")
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_NOT_BOUND_TO_ACTIVE_PERMIT"
        )
    issued = _agent_boundary_moment(active_permit.get("issued_at"))
    created = _agent_boundary_moment(context.get("created_at"))
    reserved = _agent_boundary_moment(request.get("reserved_at"))
    deadline = _agent_boundary_moment(window.get("permit_deadline_at"))
    if not issued <= created <= reserved < deadline or created >= deadline:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_TIME_NOT_BOUND_TO_ACTIVE_PERMIT"
        )
    return {
        "dynamic_checkpoint": dict(dynamic_checkpoint),
        "supervisor_checkpoint_binding": dict(
            bindings["supervisor_checkpoint"]
        ),
        "supervisor_permit_binding": dict(bindings["supervisor_permit"]),
        "input_binding": dict(bindings[input_role]),
        "packet_binding": dict(bindings[packet_role]),
        "request_digest": request.get(REQUEST_DIGEST_FIELD),
        "stage": stage,
    }


def _assert_target_agent_anchor_unchanged(
    *,
    anchor_before: Mapping[str, Any],
    **kwargs: Any,
) -> Mapping[str, Any]:
    anchor_after = _verify_target_agent_request_anchor(**kwargs)
    if dict(anchor_after) != dict(anchor_before):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_DYNAMIC_ANCHOR_CHANGED"
        )
    return anchor_after


def read_and_claim_v32_target_agent_request_v1(
    *,
    project_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Claim one queued target-run Agent request under its active permit."""

    project, _, run_root = _load_verified_target_context(
        project_root=project_root,
        expected_run_id=expected_run_id,
    )
    control_store = LocalV32RunControlStore(project)
    with control_store.run_composition_guard(run_id=expected_run_id):
        return _read_and_claim_v32_target_agent_request_under_guard(
            run_root=run_root,
            expected_run_id=expected_run_id,
        )


def _read_and_claim_v32_target_agent_request_under_guard(
    *,
    run_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    supervisor_store = LocalV32TickSupervisorStore(run_root)
    outcome_store = LocalV32OutcomeTickStore(run_root)
    dynamic_store = LocalV32DynamicStore(run_root)
    # Read only enough verified Supervisor state to locate the mailbox cycle.
    # The complete active-window replay happens below at the exact claim time.
    # This ordering is what makes an immutable claim written before a crashed
    # checkpoint CAS recoverable without inventing a newer claimed_at value.
    try:
        bootstrap_supervisor = supervisor_store.load_checkpoint(
            run_id=expected_run_id
        )
        bootstrap_permit_digest = bootstrap_supervisor.get(
            "active_permit_digest"
        )
        if not isinstance(bootstrap_permit_digest, str):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_ANALYSIS_PERMIT_REQUIRED"
            )
        bootstrap_permit = supervisor_store.load_permit(
            run_id=expected_run_id,
            permit_digest=bootstrap_permit_digest,
        )
        cycle_index = int(bootstrap_permit["analysis_cycle_index"])
    except V32TargetWakeCompositionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_REPLAY_INVALID"
        ) from exc
    mailbox = LocalV32CurrentRootAgentMailbox(run_root)
    pending = mailbox.next_pending_request(
        run_id=expected_run_id, cycle_index=cycle_index
    )
    valid_pending = pending is not None and (
        (
            pending.get("stage_status") == "REQUESTED"
            and pending.get("next_action") == "CURRENT_ROOT_CODEX_CLAIM"
        )
        or (
            pending.get("stage_status") == "CLAIMED"
            and pending.get("next_action")
            == "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
        )
    )
    if not valid_pending or (
        pending.get("stage") not in AGENT_STAGES
        or pending.get("run_id") != expected_run_id
        or pending.get("cycle_index") != cycle_index
        or not isinstance(pending.get("request"), Mapping)
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_NOT_READY"
        )
    stage = str(pending["stage"])
    request = pending["request"]
    chain_before = mailbox.load_stage_chain(
        run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
    )
    if (
        chain_before.get("stage_status") != pending.get("stage_status")
        or chain_before.get("request") != request
        or chain_before.get("checkpoint_digest")
        != pending.get("checkpoint_digest")
        or chain_before.get("claim") != pending.get("claim")
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_CHAIN_INVALID"
        )
    orphan_claim = chain_before.get("claim")
    committed_claim_replay = pending["stage_status"] == "CLAIMED"
    clock: Any | None = None
    if committed_claim_replay:
        if not isinstance(orphan_claim, Mapping):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLAIMED_REPLAY_INVALID"
            )
        preview_claim = dict(orphan_claim)
        try:
            initial_observed_at = str(preview_claim["claimed_at"])
        except KeyError as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLAIMED_REPLAY_INVALID"
            ) from exc
    elif orphan_claim is None:
        clock = build_v32_system_clock_v1()
        initial_observed_at = str(clock())
        preview_claim: Mapping[str, Any] | None = None
    elif isinstance(orphan_claim, Mapping):
        preview_claim = dict(orphan_claim)
        try:
            initial_observed_at = str(preview_claim["claimed_at"])
        except KeyError as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_ORPHAN_CLAIM_INVALID"
            ) from exc
    else:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_ORPHAN_CLAIM_INVALID"
        )
    (
        supervisor_before,
        permit_before,
        predecessor_before,
        active_cycle_index,
        window_before,
    ) = _load_active_target_agent_boundary(
        supervisor_store=supervisor_store,
        outcome_store=outcome_store,
        expected_run_id=expected_run_id,
        observed_at=initial_observed_at,
    )
    if active_cycle_index != cycle_index:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_BOUNDARY_CHANGED"
        )
    anchor_before = _verify_target_agent_request_anchor(
        dynamic_store=dynamic_store,
        expected_run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
        request=request,
        mailbox_chain=chain_before,
        predecessor_checkpoint=predecessor_before,
        active_permit=permit_before,
        window=window_before,
    )
    checkpoint_digest = pending.get("checkpoint_digest")
    if not isinstance(checkpoint_digest, str):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_MAILBOX_CHECKPOINT_INVALID"
        )
    mailbox_checkpoint = mailbox.load_checkpoint(
        run_id=expected_run_id, cycle_index=cycle_index
    )
    if (
        mailbox_checkpoint.get(MAILBOX_CHECKPOINT_DIGEST_FIELD)
        != checkpoint_digest
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_MAILBOX_CHECKPOINT_INVALID"
        )
    claimed_snapshot: Mapping[str, Any] | None = None
    if committed_claim_replay:
        try:
            claimed_snapshot = mailbox.load_claimed_stage_snapshot(
                run_id=expected_run_id,
                cycle_index=cycle_index,
                stage=stage,
            )
        except Exception as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLAIMED_REPLAY_INVALID"
            ) from exc
        if (
            claimed_snapshot.get("mailbox_checkpoint")
            != mailbox_checkpoint
            or claimed_snapshot.get("request") != request
            or claimed_snapshot.get("claim") != preview_claim
            or claimed_snapshot.get("lossless_context_package")
            != chain_before.get("lossless_context_package")
        ):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLAIMED_REPLAY_INVALID"
            )
    if preview_claim is None:
        if clock is None:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLOCK_REQUIRED"
            )
        mutation_at = str(clock())
        _assert_target_agent_clock_not_regressed(
            earlier_at=initial_observed_at, later_at=mutation_at
        )
    else:
        # This is exact-tail completion of the already-published immutable
        # claim, not a new logical boundary.  Reuse its original timestamp.
        mutation_at = initial_observed_at
    mutation_window = _assert_target_agent_boundary_unchanged(
        supervisor_store=supervisor_store,
        outcome_store=outcome_store,
        expected_run_id=expected_run_id,
        observed_at=mutation_at,
        checkpoint_before=supervisor_before,
        permit_before=permit_before,
        predecessor_before=predecessor_before,
        cycle_index_before=cycle_index,
        window_before=window_before,
    )
    _assert_target_agent_anchor_unchanged(
        anchor_before=anchor_before,
        dynamic_store=dynamic_store,
        expected_run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
        request=request,
        mailbox_chain=chain_before,
        predecessor_checkpoint=predecessor_before,
        active_permit=permit_before,
        window=mutation_window,
    )
    try:
        if preview_claim is None:
            preview_claim = build_v32_current_root_agent_mailbox_claim_v1(
                request=request, claimed_at=mutation_at
            )
        preview_checkpoint = (
            claimed_snapshot["mailbox_checkpoint"]
            if committed_claim_replay and claimed_snapshot is not None
            else claim_v32_current_root_agent_mailbox_request_v1(
                checkpoint=mailbox_checkpoint,
                request=request,
                claim=preview_claim,
            )
        )
        presentation = build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=preview_checkpoint,
            request=request,
            claim=preview_claim,
            lossless_context_package=chain_before[
                "lossless_context_package"
            ],
            control_context={
                "presentation_kind": "TARGET_AGENT_CLAIM",
                "stage": stage,
                "stage_status": "CLAIMED",
                "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                "active_analysis_permit_digest": permit_before[
                    PERMIT_DIGEST_FIELD
                ],
                "supervisor_checkpoint_digest": supervisor_before[
                    SUPERVISOR_CHECKPOINT_DIGEST_FIELD
                ],
                "permit_deadline_at": mutation_window["permit_deadline_at"],
                "agent_boundary_at": mutation_at,
            },
        )
    except Exception as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_PRESENTATION_PRECHECK_FAILED"
        ) from exc
    # Every authority, permit, anchor, chronology and presentation check has
    # completed before this sole CAS.  The concrete mailbox store owns the
    # exact transition and orphan-tail recovery.  No fallible external reread
    # or third clock occurs after a successful mutation.
    if not committed_claim_replay:
        mailbox.claim_request(
            run_id=expected_run_id,
            cycle_index=cycle_index,
            stage=stage,
            expected_checkpoint_digest=checkpoint_digest,
            claimed_at=mutation_at,
        )
    return presentation


def submit_v32_target_agent_delivery_v1(
    *,
    project_root: Path,
    expected_run_id: str,
    stage: str,
    expected_request_digest: str,
    expected_current_codex_presentation_digest: str,
    payload_utf8: str,
) -> Mapping[str, Any]:
    """Submit one explicit UTF-8 delivery under the unchanged active permit."""

    project, _, run_root = _load_verified_target_context(
        project_root=project_root,
        expected_run_id=expected_run_id,
    )
    control_store = LocalV32RunControlStore(project)
    with control_store.run_composition_guard(run_id=expected_run_id):
        return _submit_v32_target_agent_delivery_under_guard(
            run_root=run_root,
            expected_run_id=expected_run_id,
            stage=stage,
            expected_request_digest=expected_request_digest,
            expected_current_codex_presentation_digest=(
                expected_current_codex_presentation_digest
            ),
            payload_utf8=payload_utf8,
        )


def _submit_v32_target_agent_delivery_under_guard(
    *,
    run_root: Path,
    expected_run_id: str,
    stage: str,
    expected_request_digest: str,
    expected_current_codex_presentation_digest: str,
    payload_utf8: str,
) -> Mapping[str, Any]:
    supervisor_store = LocalV32TickSupervisorStore(run_root)
    outcome_store = LocalV32OutcomeTickStore(run_root)
    dynamic_store = LocalV32DynamicStore(run_root)
    try:
        bootstrap_supervisor = supervisor_store.load_checkpoint(
            run_id=expected_run_id
        )
        bootstrap_permit_digest = bootstrap_supervisor.get(
            "active_permit_digest"
        )
        if not isinstance(bootstrap_permit_digest, str):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_ANALYSIS_PERMIT_REQUIRED"
            )
        bootstrap_permit = supervisor_store.load_permit(
            run_id=expected_run_id,
            permit_digest=bootstrap_permit_digest,
        )
        cycle_index = int(bootstrap_permit["analysis_cycle_index"])
    except V32TargetWakeCompositionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_REPLAY_INVALID"
        ) from exc
    if stage not in AGENT_STAGES:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_STAGE_INVALID"
        )
    mailbox = LocalV32CurrentRootAgentMailbox(run_root)
    recovery_chain: Mapping[str, Any] | None = None
    try:
        pending = mailbox.next_pending_request(
            run_id=expected_run_id, cycle_index=cycle_index
        )
    except V32CurrentRootAgentMailboxStoreError as exc:
        if str(exc) not in {
            "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE",
            "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE",
        }:
            raise
        recovery_chain = mailbox.load_verified_recovery_stage_view(
            run_id=expected_run_id,
            cycle_index=cycle_index,
            stage=stage,
        )
        if recovery_chain.get("recovery_tail_kind") not in {
            "DELIVERY_ONLY",
            "DELIVERY_RECEIPT_PRE_CAS",
        }:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_DELIVERY_RECOVERY_VIEW_INVALID"
            )
        pending = {
            "run_id": expected_run_id,
            "cycle_index": cycle_index,
            "stage": stage,
            "stage_status": recovery_chain["stage_status"],
            "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
            "checkpoint_digest": recovery_chain["checkpoint_digest"],
            "request": recovery_chain["request"],
            "claim": recovery_chain["claim"],
        }
    if (
        pending is None
        or pending.get("run_id") != expected_run_id
        or pending.get("cycle_index") != cycle_index
        or pending.get("stage") != stage
        or (
            pending.get("stage_status"), pending.get("next_action")
        )
        not in {
            ("CLAIMED", "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"),
            ("DELIVERED", "CONTROLLER_CONSUME_DELIVERY"),
        }
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_DELIVERY_NOT_READY"
        )
    chain = recovery_chain or mailbox.load_stage_chain(
        run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
    )
    if (
        chain.get("stage_status") == "CLAIMED"
        and isinstance(chain.get("agent_delivery"), Mapping)
        and recovery_chain is None
    ):
        chain = mailbox.load_verified_recovery_stage_view(
            run_id=expected_run_id,
            cycle_index=cycle_index,
            stage=stage,
        )
        if chain.get("recovery_tail_kind") not in {
            "DELIVERY_ONLY",
            "DELIVERY_RECEIPT_PRE_CAS",
        }:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_DELIVERY_RECOVERY_VIEW_INVALID"
            )
    request = chain.get("request")
    if (
        chain.get("stage_status") != pending.get("stage_status")
        or not isinstance(request, Mapping)
        or request.get(REQUEST_DIGEST_FIELD) != expected_request_digest
        or request != pending.get("request")
        or chain.get("claim") != pending.get("claim")
        or chain.get("checkpoint_digest") != pending.get("checkpoint_digest")
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_REQUEST_DIGEST_OR_CHAIN_DRIFT"
        )
    committed_delivery_replay = chain["stage_status"] == "DELIVERED"
    orphan_delivery_recovery = chain.get("recovery_tail_kind") in {
        "DELIVERY_ONLY",
        "DELIVERY_RECEIPT_PRE_CAS",
    }
    claimed_snapshot: Mapping[str, Any] | None = None
    clock: Any | None = None
    if committed_delivery_replay:
        try:
            claimed_snapshot = mailbox.load_claimed_stage_snapshot(
                run_id=expected_run_id,
                cycle_index=cycle_index,
                stage=stage,
            )
            initial_observed_at = str(
                chain["agent_delivery"]["delivered_at"]
            )
        except Exception as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_DELIVERY_REPLAY_INVALID"
            ) from exc
        if (
            claimed_snapshot.get("request") != request
            or claimed_snapshot.get("claim") != chain.get("claim")
            or claimed_snapshot.get("lossless_context_package")
            != chain.get("lossless_context_package")
            or not isinstance(chain.get("agent_delivery"), Mapping)
            or not isinstance(chain.get("delivery_receipt"), Mapping)
        ):
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_DELIVERY_REPLAY_INVALID"
            )
    elif orphan_delivery_recovery:
        try:
            initial_observed_at = str(
                chain["agent_delivery"]["delivered_at"]
            )
            claimed_snapshot = {
                "mailbox_checkpoint": chain["mailbox_checkpoint"],
                "request": chain["request"],
                "claim": chain["claim"],
                "lossless_context_package": chain[
                    "lossless_context_package"
                ],
            }
        except Exception as exc:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_DELIVERY_RECOVERY_VIEW_INVALID"
            ) from exc
    else:
        clock = build_v32_system_clock_v1()
        initial_observed_at = str(clock())
    (
        supervisor_before,
        permit_before,
        predecessor_before,
        active_cycle_index,
        window_before,
    ) = _load_active_target_agent_boundary(
        supervisor_store=supervisor_store,
        outcome_store=outcome_store,
        expected_run_id=expected_run_id,
        observed_at=initial_observed_at,
    )
    if active_cycle_index != cycle_index:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_SUPERVISOR_BOUNDARY_CHANGED"
        )
    anchor_before = _verify_target_agent_request_anchor(
        dynamic_store=dynamic_store,
        expected_run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
        request=request,
        mailbox_chain=chain,
        predecessor_checkpoint=predecessor_before,
        active_permit=permit_before,
        window=window_before,
    )
    if committed_delivery_replay or orphan_delivery_recovery:
        mutation_at = initial_observed_at
    else:
        if clock is None:
            raise V32TargetWakeCompositionError(
                "V32_TARGET_AGENT_CLOCK_REQUIRED"
            )
        mutation_at = str(clock())
    # The fresh pre-CAS time is the linearization point: chronology, the
    # Supervisor window, its schedules, and the Dynamic owning anchor must all
    # still verify before the immutable mailbox mutation is allowed.
    _assert_target_agent_clock_not_regressed(
        earlier_at=initial_observed_at, later_at=mutation_at
    )
    mutation_window = _assert_target_agent_boundary_unchanged(
        supervisor_store=supervisor_store,
        outcome_store=outcome_store,
        expected_run_id=expected_run_id,
        observed_at=mutation_at,
        checkpoint_before=supervisor_before,
        permit_before=permit_before,
        predecessor_before=predecessor_before,
        cycle_index_before=cycle_index,
        window_before=window_before,
    )
    _assert_target_agent_anchor_unchanged(
        anchor_before=anchor_before,
        dynamic_store=dynamic_store,
        expected_run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
        request=request,
        mailbox_chain=chain,
        predecessor_checkpoint=predecessor_before,
        active_permit=permit_before,
        window=mutation_window,
    )
    current_mailbox_checkpoint = mailbox.load_checkpoint(
        run_id=expected_run_id, cycle_index=cycle_index
    )
    if current_mailbox_checkpoint.get(
        MAILBOX_CHECKPOINT_DIGEST_FIELD
    ) != pending.get("checkpoint_digest"):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_MAILBOX_CHECKPOINT_INVALID"
        )
    mailbox_checkpoint = (
        claimed_snapshot["mailbox_checkpoint"]
        if committed_delivery_replay and claimed_snapshot is not None
        else current_mailbox_checkpoint
    )
    presentation_chain = claimed_snapshot or chain
    presentation = build_v32_current_codex_presentation_envelope_v1(
        mailbox_checkpoint=mailbox_checkpoint,
        request=presentation_chain["request"],
        claim=presentation_chain["claim"],
        lossless_context_package=presentation_chain[
            "lossless_context_package"
        ],
        control_context={
            "presentation_kind": "TARGET_AGENT_CLAIM",
            "stage": stage,
            "stage_status": "CLAIMED",
            "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
            "active_analysis_permit_digest": permit_before[
                PERMIT_DIGEST_FIELD
            ],
            "supervisor_checkpoint_digest": supervisor_before[
                SUPERVISOR_CHECKPOINT_DIGEST_FIELD
            ],
            "permit_deadline_at": mutation_window["permit_deadline_at"],
            "agent_boundary_at": presentation_chain["claim"]["claimed_at"],
        },
    )
    if presentation.get(
        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
    ) != expected_current_codex_presentation_digest:
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_PRESENTATION_DIGEST_DRIFT"
        )
    if (
        chain.get("delivery_receipt") is not None
        and chain["delivery_receipt"].get(
            "current_codex_presentation_digest"
        )
        != expected_current_codex_presentation_digest
    ):
        raise V32TargetWakeCompositionError(
            "V32_TARGET_AGENT_PRESENTATION_DIGEST_DRIFT"
        )
    # The Supervisor/permit/window/anchor replay above is the complete
    # pre-CAS decision boundary.  Return the concrete store result directly so
    # no post-CAS reread, third clock, or non-durable "quarantine" claim can
    # turn a successful immutable delivery into an API-level failure.
    return mailbox.submit_delivery(
        run_id=expected_run_id,
        cycle_index=cycle_index,
        stage=stage,
        expected_checkpoint_digest=str(
            mailbox_checkpoint[MAILBOX_CHECKPOINT_DIGEST_FIELD]
        ),
        current_codex_presentation_envelope=presentation,
        expected_current_codex_presentation_digest=(
            expected_current_codex_presentation_digest
        ),
        delivered_at=mutation_at,
        payload_utf8=payload_utf8,
    )


def run_v32_target_wake_v1(
    *,
    project_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Route at most one V3.2 wake from the sole frozen target run.

    No authority document, clock, store, model/Agent adapter, transport,
    outcome adapter, wake runner, or execution capability is caller-injectable.
    A missing cycle-zero qualification audit therefore fails inside the
    Application router before either public network lane can be invoked.
    """

    project, replay, run_root = _load_verified_target_context(
        project_root=project_root,
        expected_run_id=expected_run_id,
    )
    control_store = LocalV32RunControlStore(project)
    with control_store.run_composition_guard(run_id=expected_run_id):
        return _run_v32_target_wake_under_guard(
            project=project,
            replay=replay,
            run_root=run_root,
            expected_run_id=expected_run_id,
        )


def read_v32_target_status_v1(
    *, project_root: Path, expected_run_id: str
) -> Mapping[str, Any]:
    """Read the sole target status with full authority replay and zero writes."""

    _, replay, run_root = _load_verified_target_context(
        project_root=project_root,
        expected_run_id=expected_run_id,
    )
    manifest = replay["authority_projection"]["manifest"]
    clock = build_v32_system_clock_v1()
    result = read_v32_read_only_status_snapshot_v1(
        run_root=run_root,
        run_id=expected_run_id,
        observed_at=str(clock()),
    )
    return {
        **dict(result),
        "qualification_run_id": manifest["qualification_run_id"],
        "engine_version": {
            "theory": "V3.2",
            "runtime_manifest_id": manifest["manifest_id"],
            "runtime_manifest_schema_version": manifest["schema_version"],
            "runtime_manifest_digest": manifest[
                RUNTIME_MANIFEST_DIGEST_FIELD
            ],
        },
        "full_authority_and_genesis_replayed": True,
        "production_clock_adapter": clock.adapter_id,
    }


def _run_v32_target_wake_under_guard(
    *,
    project: Path,
    replay: Mapping[str, Any],
    run_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Construct and route one wake while the per-run guard is held."""

    projection = replay["authority_projection"]
    materials = _load_verified_analysis_materials(project=project, replay=replay)
    active_authority = _active_authority_projection(replay)
    clock = build_v32_system_clock_v1()

    dynamic_store = LocalV32DynamicStore(run_root)
    outcome_store = LocalV32OutcomeTickStore(run_root)
    supervisor_store = LocalV32TickSupervisorStore(run_root)
    mailbox = LocalV32CurrentRootAgentMailbox(run_root)
    source_store = LocalV32CycleSourceAdmissionStore(
        run_root / _SOURCE_STORE_DIRECTORY
    )
    admitted_source_store = LocalV32CycleSourceAdmissionStore(run_root)
    revision_store = LocalV32AuthorizedRevisionStore(run_root)
    audit_completion_store = LocalV32CycleAuditCompletionStore(run_root)
    audit_lane = LocalV32BoundaryAuditLane(
        revision_store=revision_store,
        acceptance_completion_store=audit_completion_store,
        clock=clock,
    )
    supervision_store = LocalV32RecoverySupervisionStore(run_root)
    terminal_store = LocalV32TerminalSealStore(run_root)

    source_collector = V32RawFirstOkxPublicBundleCollector(
        transport=V32OkxPublicBundleTransport(clock=clock),
        clock=clock,
        store=source_store,
    )
    material_port = LocalV32AnalysisMaterialAdapter(
        verified_target_authority_bundle=projection,
        active_authority_projection=active_authority,
        theory_semantic_document=materials["theory_semantic_document"],
        theory_semantic_document_binding=materials[
            "theory_semantic_document_binding"
        ],
        frozen_support_documents=materials["support_documents"],
        frozen_support_bindings=materials["support_bindings"],
        strategy_revision_material_reader=(
            LocalV32NoRevisionInputMaterialReader()
        ),
        strategy_revision_observation_clock=clock,
    )
    analysis_lane = LocalV32AnalysisLane(
        dynamic_store=dynamic_store,
        outcome_store=outcome_store,
        source_store=source_store,
        admitted_source_store=admitted_source_store,
        source_collector=source_collector,
        mailbox=mailbox,
        active_authority_projection=active_authority,
        qualification_id_factory=_qualification_id,
        clock=_AnalysisSystemClock(clock),
        material_port=material_port,
    )
    outcome_lane = LocalV32OutcomeLane(
        store=outcome_store,
        capture_port=V32OkxPublicMarkCaptureAdapter(
            clock=_OutcomeDatetimeSystemClock(clock)
        ),
    )

    result = route_v32_prospective_wake_v1(
        supervisor_store=supervisor_store,
        dynamic_store=dynamic_store,
        outcome_store=outcome_store,
        mailbox=mailbox,
        revision_store=revision_store,
        audit_completion_store=audit_completion_store,
        audit_lane=audit_lane,
        analysis_port=analysis_lane,
        outcome_port=outcome_lane,
        cycle_audit_policy=replay["cycle_audit_policy"],
        run_id=expected_run_id,
        clock=clock,
        supervisor_alert_port=supervision_store,
        supervision_evidence_port=supervision_store,
        terminal_seal_port=terminal_store,
    )
    agent_presentation = _current_codex_presentation_from_routed_wake(result)
    if agent_presentation is not None:
        control_context = agent_presentation["control_context"]
        if (
            control_context["presentation_kind"]
            == "PROSPECTIVE_PENDING_AGENT_ACTION"
            and control_context["stage_status"] == "CLAIMED"
        ):
            # The generic Application router can only prove that the mailbox
            # claim exists; it cannot bind the target permit/window fields that
            # the public target submit entry verifies.  A lost response after
            # the claim CAS must therefore replay the target-specific envelope
            # from the sealed claimed snapshot.  This path is read-only: the
            # internal claim composition detects CLAIMED and performs no
            # second Agent attempt, write, or clock allocation.
            target_presentation = (
                _read_and_claim_v32_target_agent_request_under_guard(
                    run_root=run_root,
                    expected_run_id=expected_run_id,
                )
            )
            if (
                target_presentation.get("request")
                != agent_presentation.get("request")
                or target_presentation.get("claim")
                != agent_presentation.get("claim")
                or target_presentation.get("control_context", {}).get("stage")
                != control_context["stage"]
            ):
                raise V32TargetWakeCompositionError(
                    "V32_TARGET_AGENT_CLAIMED_PRESENTATION_REPLAY_DRIFT"
                )
            return target_presentation
        # The Agent-facing object has already been capacity checked and
        # self-digested.  Any composition metadata wrapper would invalidate the
        # final 1 MiB delivery boundary, so transmit these exact bytes only.
        return agent_presentation
    return {
        **dict(result),
        "target_wake_composition": "V32_SOLE_PRODUCTION_WAKE_V1",
        "full_authority_and_genesis_replayed": True,
        "production_clock_adapter": clock.adapter_id,
        "public_network_scope": "ROUTED_SOURCE_OR_OUTCOME_LANE_ONLY",
        "account_access": False,
        "order_submission": False,
        "executable": False,
    }


__all__ = [
    "V32TargetWakeCompositionError",
    "read_and_claim_v32_target_agent_request_v1",
    "read_v32_target_status_v1",
    "run_v32_target_wake_v1",
    "submit_v32_target_agent_delivery_v1",
]
