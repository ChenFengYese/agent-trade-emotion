"""Production composition for the sole local, non-executable V3.2 target run.

The caller supplies only the project root and expected target run identity.
This composition first invokes the complete
V3.2 current-authority loader, reads the exact verified source bytes itself,
constructs the operating-system UTC clock internally, initializes the three
existing revision-zero stores, and delegates final write-once publication to
the run-control store.  Authority documents, authority digests, timestamps,
clocks, account data, and execution adapters are deliberately not injectable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..application.v32_authorized_revision_orchestration import (
    SUPPORT_BUNDLE_DIGEST_FIELD,
    SUPPORT_BUNDLE_SCHEMA_ID,
)
from ..application.v32_prospective_runtime import (
    initialize_v32_prospective_runtime_v1,
)
from ..domain.contracts.canonical import load_json_strict, verify_self_digest
from ..domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_SCHEMA_ID,
    verify_v32_authority_v1,
    verify_v32_qualification_retirement_receipt_v1,
)
from ..domain.governance.v32_qualification_identity import (
    TOMBSTONED_V32_RUN_IDS,
    V32QualificationIdentityError,
    validate_v32_run_id_syntax_v1,
)
from ..domain.v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as CYCLE_AUDIT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CYCLE_AUDIT_POLICY_SCHEMA_ID,
    verify_v32_cycle_audit_policy_v1,
)
from ..domain.v32_run_genesis import (
    GENESIS_SOURCE_SPECS,
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_SCHEMA_ID,
    SOURCE_ROLES,
    build_v32_initial_timeframe_genesis_entity_v1,
    validate_v32_target_projection_v1,
    verify_v32_revision_zero_checkpoints_v1,
)
from ..infrastructure.authority.v32_current_research import (
    V32_APPLICATION_PROJECTION_KEYS,
    V32_CURRENT_RESEARCH_AUTHORITY_PATH,
    load_v32_current_research_authority,
)
from ..infrastructure.authority.v32_actual_capability_replay import (
    build_v32_actual_capability_full_replay_registry,
)
from ..infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
)
from ..infrastructure.v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)
from ..infrastructure.v32_dynamic_store import LocalV32DynamicStore
from ..infrastructure.v32_local_audit_lane import LocalV32BoundaryAuditLane
from ..infrastructure.v32_outcome_tick_store import LocalV32OutcomeTickStore
from ..infrastructure.v32_run_control_store import (
    CONTROL_ROOT_RELATIVE,
    CURRENT_RUN_POINTER_REF,
    LocalV32RunControlStore,
)
from ..infrastructure.v32_runtime_clock import build_v32_system_clock_v1
from ..infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)


class V32TargetRunCompositionError(ValueError):
    """Production target-run genesis could not be proven and published."""


def _active_target_run_id(value: Any) -> str:
    try:
        run_id = validate_v32_run_id_syntax_v1(value)
    except V32QualificationIdentityError as exc:
        raise V32TargetRunCompositionError(str(exc)) from exc
    if run_id in TOMBSTONED_V32_RUN_IDS:
        raise V32TargetRunCompositionError(
            "V32_QUALIFICATION_RUN_ID_TOMBSTONED"
        )
    return run_id


_GLOBAL_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_REVISION_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)


def _contained_file(project_root: Path, relative_ref: Any, code: str) -> Path:
    if not isinstance(relative_ref, str) or not relative_ref:
        raise V32TargetRunCompositionError(code)
    lexical = PurePosixPath(relative_ref)
    if (
        "\\" in relative_ref
        or lexical.as_posix() != relative_ref
        or lexical.is_absolute()
        or any(part in {"", ".", ".."} for part in lexical.parts)
    ):
        raise V32TargetRunCompositionError(code)
    current = project_root
    try:
        for part in lexical.parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise V32TargetRunCompositionError(code)
        resolved = current.resolve(strict=True)
        resolved.relative_to(project_root.resolve(strict=True))
    except V32TargetRunCompositionError:
        raise
    except (OSError, ValueError) as exc:
        raise V32TargetRunCompositionError(code) from exc
    if current.is_symlink() or not current.is_file():
        raise V32TargetRunCompositionError(code)
    return current


def _read_exact_projection_sources(
    *, project_root: Path, projection: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, dict[str, str]], dict[str, bytes]]:
    if tuple(projection) != V32_APPLICATION_PROJECTION_KEYS:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_PROJECTION_SET_INVALID"
        )
    authority = projection["authority"]
    supplied_bindings: dict[str, Mapping[str, Any]] = {
        "theory_approval": authority["theory_approval_binding"],
        "experiment_contract": authority["experiment_contract_binding"],
        "manifest": authority["runtime_manifest_binding"],
        "authorization_receipt": authority["authorization_receipt_binding"],
    }
    raw_bytes: dict[str, bytes] = {}
    bindings: dict[str, dict[str, str]] = {}
    by_role = {spec.role: spec for spec in GENESIS_SOURCE_SPECS}
    for role in SOURCE_ROLES[:-1]:
        spec = by_role[role]
        binding = supplied_bindings[role]
        if (
            not isinstance(binding, Mapping)
            or set(binding) != _GLOBAL_BINDING_FIELDS
            or binding.get("schema_id") != spec.schema_id
            or binding.get("digest_field") != spec.digest_field
            or binding.get("semantic_digest")
            != projection[role].get(spec.digest_field)
        ):
            raise V32TargetRunCompositionError(
                f"V32_TARGET_COMPOSITION_GLOBAL_BINDING_INVALID:{role}"
            )
        path = _contained_file(
            project_root,
            binding["path"],
            f"V32_TARGET_COMPOSITION_GLOBAL_FILE_INVALID:{role}",
        )
        payload = path.read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != binding.get("physical_sha256")
            or load_json_strict(path) != dict(projection[role])
        ):
            raise V32TargetRunCompositionError(
                f"V32_TARGET_COMPOSITION_GLOBAL_FILE_DRIFT:{role}"
            )
        raw_bytes[role] = payload
        bindings[role] = dict(binding)

    authority_spec = by_role["authority"]
    authority_ref = V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    authority_path = _contained_file(
        project_root,
        authority_ref,
        "V32_TARGET_COMPOSITION_AUTHORITY_FILE_INVALID",
    )
    authority_payload = authority_path.read_bytes()
    if load_json_strict(authority_path) != dict(authority):
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUTHORITY_FILE_DRIFT"
        )
    try:
        authority_digest = verify_self_digest(authority, AUTHORITY_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUTHORITY_DIGEST_INVALID"
        ) from exc
    bindings["authority"] = {
        "path": authority_ref,
        "schema_id": AUTHORITY_SCHEMA_ID,
        "digest_field": AUTHORITY_DIGEST_FIELD,
        "semantic_digest": authority_digest,
        "physical_sha256": hashlib.sha256(authority_payload).hexdigest(),
    }
    if (
        authority_spec.schema_id != AUTHORITY_SCHEMA_ID
        or authority_spec.digest_field != AUTHORITY_DIGEST_FIELD
    ):
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUTHORITY_SPEC_INVALID"
        )
    raw_bytes["authority"] = authority_payload
    return bindings, raw_bytes


def _load_bound_json(
    project_root: Path,
    binding: Mapping[str, Any],
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> Mapping[str, Any]:
    if not isinstance(binding, Mapping):
        raise V32TargetRunCompositionError(code)
    if set(binding) == _GLOBAL_BINDING_FIELDS:
        ref = binding.get("path")
    elif set(binding) == _REVISION_BINDING_FIELDS:
        ref = binding.get("relative_ref")
    else:
        raise V32TargetRunCompositionError(code)
    if (
        binding.get("schema_id") != schema_id
        or binding.get("digest_field") != digest_field
    ):
        raise V32TargetRunCompositionError(code)
    path = _contained_file(project_root, ref, code)
    payload = path.read_bytes()
    document = load_json_strict(path)
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(code) from exc
    if (
        document.get("schema_id") != schema_id
        or semantic != binding.get("semantic_digest")
        or hashlib.sha256(payload).hexdigest() != binding.get("physical_sha256")
    ):
        raise V32TargetRunCompositionError(code)
    return document


def _load_cycle_audit_policy(
    *, project_root: Path, manifest: Mapping[str, Any], expected_run_id: str
) -> Mapping[str, Any]:
    try:
        support_binding = manifest["support_document_bindings"][
            "authorized_revision_support_bundle_digest"
        ]
    except (KeyError, TypeError) as exc:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUDIT_SUPPORT_MISSING"
        ) from exc
    support_bundle = _load_bound_json(
        project_root,
        support_binding,
        schema_id=SUPPORT_BUNDLE_SCHEMA_ID,
        digest_field=SUPPORT_BUNDLE_DIGEST_FIELD,
        code="V32_TARGET_COMPOSITION_AUDIT_SUPPORT_INVALID",
    )
    rows = support_bundle.get("components")
    if not isinstance(rows, list):
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUDIT_SUPPORT_INVALID"
        )
    matches = [
        row.get("binding")
        for row in rows
        if isinstance(row, Mapping) and row.get("role") == "cycle_audit_policy"
    ]
    if len(matches) != 1:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUDIT_POLICY_BINDING_INVALID"
        )
    policy = _load_bound_json(
        project_root,
        matches[0],
        schema_id=CYCLE_AUDIT_POLICY_SCHEMA_ID,
        digest_field=CYCLE_AUDIT_POLICY_DIGEST_FIELD,
        code="V32_TARGET_COMPOSITION_AUDIT_POLICY_INVALID",
    )
    try:
        verify_v32_cycle_audit_policy_v1(policy)
    except (TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUDIT_POLICY_INVALID"
        ) from exc
    if policy.get("run_scope_id") != expected_run_id:
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_AUDIT_POLICY_SCOPE_INVALID"
        )
    return policy


def _audit_source_binding(binding: Mapping[str, Any], *, code: str) -> dict[str, str]:
    """Translate an exact durable binding into the audit Domain vocabulary."""

    if not isinstance(binding, Mapping):
        raise V32TargetRunCompositionError(code)
    if set(binding) == _GLOBAL_BINDING_FIELDS:
        relative_ref = binding.get("path")
    elif set(binding) == _REVISION_BINDING_FIELDS:
        relative_ref = binding.get("relative_ref")
    else:
        raise V32TargetRunCompositionError(code)
    if not isinstance(relative_ref, str) or not relative_ref:
        raise V32TargetRunCompositionError(code)
    return {
        "relative_ref": relative_ref,
        "schema_id": str(binding["schema_id"]),
        "digest_field": str(binding["digest_field"]),
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def replay_v32_target_run_from_current_authority_v1(
    *,
    project_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Read-only full-authority replay of the sole already published genesis."""

    expected_run_id = _active_target_run_id(expected_run_id)
    project = Path(project_root).absolute()
    if project.is_symlink() or not project.is_dir():
        raise V32TargetRunCompositionError(
            "V32_TARGET_REPLAY_PROJECT_ROOT_INVALID"
        )
    try:
        # The full loader remains first even when local run state is absent.
        projection = load_v32_current_research_authority(
            project,
            expected_run_id=expected_run_id,
            capability_verifiers=(
                build_v32_actual_capability_full_replay_registry()
            ),
        )
        global_bindings, global_raw_bytes = _read_exact_projection_sources(
            project_root=project, projection=projection
        )
        projection_state = validate_v32_target_projection_v1(
            projection=projection, global_bindings=global_bindings
        )
        if projection_state["run_id"] != expected_run_id:
            raise V32TargetRunCompositionError(
                "V32_TARGET_REPLAY_RUN_SCOPE_INVALID"
            )
        cycle_audit_policy = _load_cycle_audit_policy(
            project_root=project,
            manifest=projection["manifest"],
            expected_run_id=expected_run_id,
        )
        # LocalV32RunControlStore creates its control directory on
        # construction.  Refuse an absent root first so this public replay API
        # stays non-creating even when no genesis has ever been published.
        control_root = project / CONTROL_ROOT_RELATIVE
        if control_root.is_symlink() or not control_root.is_dir():
            raise V32TargetRunCompositionError(
                "V32_TARGET_REPLAY_PUBLISHED_GENESIS_REQUIRED"
            )
        control_store = LocalV32RunControlStore(project)
        if (
            control_store.assert_pointer_available(
                expected_run_id=expected_run_id
            )
            is None
        ):
            raise V32TargetRunCompositionError(
                "V32_TARGET_REPLAY_PUBLISHED_GENESIS_REQUIRED"
            )
        replayed = control_store.replay_published_genesis(
            expected_run_id=expected_run_id,
            projection=projection,
            global_bindings=global_bindings,
            global_raw_bytes=global_raw_bytes,
        )
        return {
            **dict(replayed),
            "composition_status": "GENESIS_REPLAYED_READ_ONLY",
            "full_loader_verified": True,
            "authority_projection": {
                role: dict(projection[role])
                for role in V32_APPLICATION_PROJECTION_KEYS
            },
            "global_source_bindings": {
                role: dict(global_bindings[role]) for role in SOURCE_ROLES
            },
            "cycle_audit_policy": dict(cycle_audit_policy),
            "replay_only": True,
            "state_mutation_count": 0,
            "network_request_count": 0,
            "account_access": False,
            "order_submission": False,
            "executable": False,
        }
    except V32TargetRunCompositionError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(
            f"V32_TARGET_REPLAY_FAILED:{exc}"
        ) from exc


def seal_v32_cycle_zero_qualification_audit_v1(
    *,
    project_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Create or replay the qualification audit without opening cycle 1.

    This is intentionally a separate owner from genesis publication.  The
    caller cannot supply documents, bindings, a timestamp, a clock, stores, or
    an analysis permit.  All three narrative sources are reopened from the
    bindings already sealed into the published run genesis.
    """

    expected_run_id = _active_target_run_id(expected_run_id)
    project = Path(project_root).absolute()
    if project.is_symlink() or not project.is_dir():
        raise V32TargetRunCompositionError(
            "V32_QUALIFICATION_AUDIT_PROJECT_ROOT_INVALID"
        )
    try:
        # Ordering is an authority invariant.  No pointer/genesis replay or
        # audit-store write is attempted before the complete loader succeeds.
        projection = load_v32_current_research_authority(
            project,
            expected_run_id=expected_run_id,
            capability_verifiers=(
                build_v32_actual_capability_full_replay_registry()
            ),
        )
        global_bindings, global_raw_bytes = _read_exact_projection_sources(
            project_root=project, projection=projection
        )
        projection_state = validate_v32_target_projection_v1(
            projection=projection, global_bindings=global_bindings
        )
        if projection_state["run_id"] != expected_run_id:
            raise V32TargetRunCompositionError(
                "V32_QUALIFICATION_AUDIT_RUN_SCOPE_INVALID"
            )
        cycle_audit_policy = _load_cycle_audit_policy(
            project_root=project,
            manifest=projection["manifest"],
            expected_run_id=expected_run_id,
        )

        clock = build_v32_system_clock_v1()
        control_store = LocalV32RunControlStore(project)
        with control_store.genesis_guard():
            if (
                control_store.assert_pointer_available(
                    expected_run_id=expected_run_id
                )
                is None
            ):
                raise V32TargetRunCompositionError(
                    "V32_QUALIFICATION_AUDIT_PUBLISHED_GENESIS_REQUIRED"
                )
            replayed = control_store.replay_published_genesis(
                expected_run_id=expected_run_id,
                projection=projection,
                global_bindings=global_bindings,
                global_raw_bytes=global_raw_bytes,
            )
            bindings = replayed.get("qualification_audit_source_bindings")
            if not isinstance(bindings, Mapping) or set(bindings) != {
                "qualification_retirement",
                "target_authority",
                "run_genesis",
            }:
                raise V32TargetRunCompositionError(
                    "V32_QUALIFICATION_AUDIT_SOURCE_BINDINGS_MISSING"
                )

            run_root = Path(str(replayed["run_root"]))
            retirement = _load_bound_json(
                project,
                bindings["qualification_retirement"],
                schema_id=QUALIFICATION_RETIREMENT_SCHEMA_ID,
                digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
                code="V32_QUALIFICATION_AUDIT_RETIREMENT_INVALID",
            )
            target_authority = _load_bound_json(
                run_root,
                bindings["target_authority"],
                schema_id=AUTHORITY_SCHEMA_ID,
                digest_field=AUTHORITY_DIGEST_FIELD,
                code="V32_QUALIFICATION_AUDIT_TARGET_AUTHORITY_INVALID",
            )
            run_genesis = _load_bound_json(
                control_store.control_root,
                bindings["run_genesis"],
                schema_id=RUN_GENESIS_SCHEMA_ID,
                digest_field=RUN_GENESIS_DIGEST_FIELD,
                code="V32_QUALIFICATION_AUDIT_RUN_GENESIS_INVALID",
            )
            try:
                verify_v32_qualification_retirement_receipt_v1(retirement)
                verify_v32_authority_v1(target_authority)
            except (TypeError, ValueError) as exc:
                raise V32TargetRunCompositionError(
                    "V32_QUALIFICATION_AUDIT_TYPED_SOURCE_INVALID"
                ) from exc
            if (
                retirement.get("target_run_id") != expected_run_id
                or target_authority.get("run_id") != expected_run_id
                or target_authority != projection["authority"]
                or run_genesis != replayed["run_genesis"]
            ):
                raise V32TargetRunCompositionError(
                    "V32_QUALIFICATION_AUDIT_SOURCE_SCOPE_INVALID"
                )

            pointer_path = _contained_file(
                control_store.control_root,
                CURRENT_RUN_POINTER_REF,
                "V32_QUALIFICATION_AUDIT_POINTER_INVALID",
            )
            genesis_path = _contained_file(
                control_store.control_root,
                bindings["run_genesis"]["relative_ref"],
                "V32_QUALIFICATION_AUDIT_RUN_GENESIS_INVALID",
            )
            pointer_before = pointer_path.read_bytes()
            genesis_before = genesis_path.read_bytes()
            sealed_sources = [
                {
                    "role": "qualification_retirement",
                    "document": dict(retirement),
                    "binding": _audit_source_binding(
                        bindings["qualification_retirement"],
                        code="V32_QUALIFICATION_AUDIT_RETIREMENT_BINDING_INVALID",
                    ),
                },
                {
                    "role": "target_authority",
                    "document": dict(target_authority),
                    "binding": _audit_source_binding(
                        bindings["target_authority"],
                        code="V32_QUALIFICATION_AUDIT_AUTHORITY_BINDING_INVALID",
                    ),
                },
                {
                    "role": "run_genesis",
                    "document": dict(run_genesis),
                    "binding": _audit_source_binding(
                        bindings["run_genesis"],
                        code="V32_QUALIFICATION_AUDIT_GENESIS_BINDING_INVALID",
                    ),
                },
            ]
            revision_store = LocalV32AuthorizedRevisionStore(run_root)
            audit_lane = LocalV32BoundaryAuditLane(
                revision_store=revision_store,
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(
                    run_root
                ),
                clock=clock,
            )
            audit = audit_lane.advance_once(
                narrative_id=f"v32-qualification::{expected_run_id}::0000",
                completion_id=None,
                run_id=expected_run_id,
                cycle_index=0,
                boundary_type="QUALIFICATION",
                boundary_sealed_at=str(run_genesis["created_at"]),
                sealed_sources=sealed_sources,
                cycle_audit_policy=cycle_audit_policy,
            )

            # The independent owner may append only the qualification audit.
            # Replaying the exact published state after that append proves the
            # genesis receipt and sole pointer were not used as mutable gates.
            replayed_after = control_store.replay_published_genesis(
                expected_run_id=expected_run_id,
                projection=projection,
                global_bindings=global_bindings,
                global_raw_bytes=global_raw_bytes,
            )
            if (
                pointer_path.read_bytes() != pointer_before
                or genesis_path.read_bytes() != genesis_before
                or replayed_after["pointer"] != replayed["pointer"]
                or replayed_after["run_genesis"] != replayed["run_genesis"]
            ):
                raise V32TargetRunCompositionError(
                    "V32_QUALIFICATION_AUDIT_GENESIS_MUTATION_FORBIDDEN"
                )
            return {
                **dict(audit),
                "composition_status": (
                    "QUALIFICATION_AUDIT_CREATED"
                    if audit["audit_status"] == "CREATED"
                    else "QUALIFICATION_AUDIT_REPLAYED"
                ),
                "full_loader_verified": True,
                "production_clock_adapter": clock.adapter_id,
                "source_bindings": {
                    row["role"]: dict(row["binding"])
                    for row in sealed_sources
                },
                "genesis_and_pointer_unchanged": True,
                "first_analysis_permit_gate_status": (
                    "QUALIFICATION_AUDIT_PRESENT_NECESSARY_CONDITION_ONLY"
                ),
                "first_analysis_permit_opened": False,
                "cycle_one_started": False,
            }
    except V32TargetRunCompositionError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(
            f"V32_QUALIFICATION_AUDIT_FAILED:{exc}"
        ) from exc


def initialize_v32_target_run_from_current_authority_v1(
    *,
    project_root: Path,
    expected_run_id: str,
) -> Mapping[str, Any]:
    """Create or replay the sole target genesis without starting cycle 1.

    There is intentionally no parameter for authority documents, authority
    digest, source bytes, created_at, clock, stores, or a bare timeframe
    digest.  The returned pointer records that the first analysis permit is
    still blocked pending the independent cycle-0 qualification audit.
    """

    expected_run_id = _active_target_run_id(expected_run_id)
    project = Path(project_root).absolute()
    if project.is_symlink() or not project.is_dir():
        raise V32TargetRunCompositionError(
            "V32_TARGET_COMPOSITION_PROJECT_ROOT_INVALID"
        )
    try:
        # Ordering is a P0 invariant: no runtime directory exists before the
        # complete historical + target authority loader succeeds.
        projection = load_v32_current_research_authority(
            project,
            expected_run_id=expected_run_id,
            capability_verifiers=(
                build_v32_actual_capability_full_replay_registry()
            ),
        )
        global_bindings, global_raw_bytes = _read_exact_projection_sources(
            project_root=project, projection=projection
        )
        projection_state = validate_v32_target_projection_v1(
            projection=projection, global_bindings=global_bindings
        )
        if projection_state["run_id"] != expected_run_id:
            raise V32TargetRunCompositionError(
                "V32_TARGET_COMPOSITION_RUN_SCOPE_INVALID"
            )
        cycle_audit_policy = _load_cycle_audit_policy(
            project_root=project,
            manifest=projection["manifest"],
            expected_run_id=expected_run_id,
        )

        # The production clock factory is constructed internally even on an
        # idempotent replay; an existing genesis keeps its original timestamp.
        clock = build_v32_system_clock_v1()
        control_store = LocalV32RunControlStore(project)
        with control_store.genesis_guard():
            pointer = control_store.assert_pointer_available(
                expected_run_id=expected_run_id
            )
            if pointer is not None:
                replayed = control_store.replay_published_genesis(
                    expected_run_id=expected_run_id,
                    projection=projection,
                    global_bindings=global_bindings,
                    global_raw_bytes=global_raw_bytes,
                )
                return {
                    **dict(replayed),
                    "composition_status": "GENESIS_REPLAYED",
                    "full_loader_verified": True,
                    "production_clock_adapter": clock.adapter_id,
                    "system_clock_timestamp_reused": True,
                    "runtime_status": (
                        "GENESIS_SEALED_AWAITING_QUALIFICATION_AUDIT"
                    ),
                }

            run_root = control_store.run_root(expected_run_id)
            dynamic_store = LocalV32DynamicStore(run_root)
            outcome_store = LocalV32OutcomeTickStore(run_root)
            supervisor_store = LocalV32TickSupervisorStore(run_root)
            recovered_created_at = control_store.existing_revision_zero_created_at(
                run_id=expected_run_id
            )
            created_at = recovered_created_at or clock()
            initial_timeframe_entity = build_v32_initial_timeframe_genesis_entity_v1(
                run_id=expected_run_id, created_at=created_at
            )
            timeframe_digest = initial_timeframe_entity[
                "initial_timeframe_genesis_digest"
            ]
            runtime = initialize_v32_prospective_runtime_v1(
                dynamic_store=dynamic_store,
                outcome_store=outcome_store,
                supervisor_store=supervisor_store,
                run_id=expected_run_id,
                experiment_contract_digest=projection_state[
                    "experiment_contract_digest"
                ],
                active_authority_digest=projection_state["authority_digest"],
                initial_timeframe_cache_digest=timeframe_digest,
                cycle_audit_policy=cycle_audit_policy,
                created_at=created_at,
            )
            checkpoints = {
                "dynamic": dynamic_store.load_checkpoint(
                    run_id=expected_run_id
                ),
                "outcome": outcome_store.load_checkpoint(
                    run_id=expected_run_id
                ),
                "supervisor": supervisor_store.load_checkpoint(
                    run_id=expected_run_id
                ),
            }
            verify_v32_revision_zero_checkpoints_v1(
                checkpoints=checkpoints,
                run_id=expected_run_id,
                experiment_contract_digest=projection_state[
                    "experiment_contract_digest"
                ],
                active_authority_digest=projection_state["authority_digest"],
                initial_timeframe_digest=timeframe_digest,
                created_at=created_at,
            )
            published = control_store.seal_and_publish(
                created_at=created_at,
                projection=projection,
                global_bindings=global_bindings,
                global_raw_bytes=global_raw_bytes,
                initial_timeframe_entity=initial_timeframe_entity,
                revision_zero_checkpoints=checkpoints,
                _already_guarded=True,
            )
            return {
                **dict(published),
                "composition_status": "GENESIS_CREATED",
                "full_loader_verified": True,
                "production_clock_adapter": clock.adapter_id,
                "system_clock_timestamp_reused": recovered_created_at is not None,
                "checkpoint_initialization": dict(runtime),
                "runtime_status": "GENESIS_SEALED_AWAITING_QUALIFICATION_AUDIT",
            }
    except V32TargetRunCompositionError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32TargetRunCompositionError(
            f"V32_TARGET_COMPOSITION_FAILED:{exc}"
        ) from exc


__all__ = [
    "V32TargetRunCompositionError",
    "initialize_v32_target_run_from_current_authority_v1",
    "replay_v32_target_run_from_current_authority_v1",
    "seal_v32_cycle_zero_qualification_audit_v1",
]
