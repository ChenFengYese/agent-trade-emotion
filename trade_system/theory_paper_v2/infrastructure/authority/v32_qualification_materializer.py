"""One-boundary materializer for the isolated V3.2 qualification Agent chain."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Callable, ContextManager, Mapping

from ...application.v32_agent_market_graph_view import build_v32_agent_market_graph_view_v1
from ...application.v32_agent_semantic_compiler import (
    compile_v32_proposal_delivery_v1,
    compile_v32_selection_delivery_v1,
)
from ...application.v32_cycle_source_admission import verify_durable_v32_cycle_source_admission
from ...application.v32_durable_source_replay import verify_durable_v32_source_replay_receipt
from ...application.v32_dynamic_state_continuity import (
    build_v32_verified_pit_evidence_availability_registry_v1,
)
from ...domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    loads_json_strict,
    verify_self_digest,
)
from ...v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    write_once_json,
)
from ...domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    THEORY_APPROVAL_DIGEST_FIELD,
)
from ...domain.governance.v32_experiment_contract import DIGEST_FIELD as CONTRACT_DIGEST_FIELD
from ...domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    PROPOSAL_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_DIGEST_FIELD,
    build_v32_agent_input_context_v1,
    build_v32_selection_canonical_packet_v1,
)
from ...domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_DIGEST_FIELD,
)
from ...domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    SOURCE_ADMISSION_DIGEST_FIELD,
)
from ...domain.v32_dynamic_action_plan import DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD
from ...domain.v32_dynamic_research import DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD
from ...domain.v32_qualification_monitor_probe import build_v32_qualification_monitor_probe_v1
from ...infrastructure.v32_analysis_material_adapter import LocalV32AnalysisMaterialAdapter
from ...infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from ...infrastructure.v32_cycle_source_admission_store import LocalV32CycleSourceAdmissionStore
from ...infrastructure.v32_public_evidence_verifier import V32InfrastructurePublicEvidenceVerifier
from ...infrastructure.v32_public_market_graph_projection import (
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
)
from ...infrastructure.v32_public_source_collector import verify_durable_v32_public_source_qualification
from .v32_qualification_monitor_probe_store import LocalV32QualificationMonitorProbeStore
from .v32_actual_capability_attempt_ports import (
    verify_v32_current_codex_attempt_time_v1,
)


class V32QualificationMaterializerError(ValueError):
    """The isolated qualification material chain failed closed."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


STORE_ROOT = "v32-qualification-material-v1"
_HEX = set("0123456789abcdef")
_AUTHORITY_FILES = {
    "theory_approval": ("theory-approval.json", THEORY_APPROVAL_DIGEST_FIELD),
    "experiment_contract": ("experiment-contract.json", CONTRACT_DIGEST_FIELD),
    "manifest": ("runtime-manifest.json", RUNTIME_MANIFEST_DIGEST_FIELD),
    "authorization_receipt": (
        "qualification/authorization.json",
        AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    ),
    "authority": ("qualification/authority.json", AUTHORITY_DIGEST_FIELD),
}
_SUPPORT_FILES = {
    "association_preregistration": "support/association.json",
    "authorized_revision_support_bundle": "support/revision-bundle.json",
    "clock_and_tick_policy": "support/clock.json",
    "evaluation_contract": "support/evaluation.json",
    "outcome_adapter_contract": "support/outcome-adapter.json",
    "recovery_supervision_policy": "support/recovery.json",
    "twelve_axis_source_registry": "support/twelve-axis.json",
    "context_compaction_policy": "support/revision/context.json",
    "unknown_subjective_policy": "support/revision/unknown.json",
    "data_gap_manual_policy": "support/revision/data-gap.json",
    "cycle_audit_policy": "support/revision/audit.json",
    "environment_capability_profile": "support/revision/environment.json",
}


def _digest_field(document: Mapping[str, Any]) -> str:
    matches: list[str] = []
    for key, value in document.items():
        if (
            isinstance(value, str)
            and len(value) == 64
            and set(value) <= _HEX
            and key.endswith("_digest")
        ):
            try:
                verify_self_digest(document, key)
            except (TypeError, ValueError):
                continue
            matches.append(key)
    if len(matches) != 1:
        raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_DIGEST_INVALID")
    return matches[0]


def _time(clock: Callable[[], str]) -> str:
    value = clock()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_CLOCK_INVALID") from exc
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_CLOCK_INVALID")
    return value


class LocalV32QualificationMaterialStore:
    def __init__(self, project_root: Path, root_relative_ref: str) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        relative = PurePosixPath(root_relative_ref)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_ROOT_INVALID")
        self.root_relative_ref = relative.as_posix()
        self.root = self.project_root.joinpath(*relative.parts)
        ensure_directory_tree(self.root)
        if self.root.is_symlink():
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_ROOT_INVALID")
        self.roles = self.root / STORE_ROOT / "roles"
        ensure_directory_tree(self.roles)

    def _path(self, role: str) -> Path:
        if not isinstance(role, str) or not role or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in role):
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_ROLE_INVALID")
        path = self.roles / f"{role}.json"
        if path.exists() and path.is_symlink():
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_PATH_INVALID")
        return path

    def load(self, role: str) -> Mapping[str, Any] | None:
        path = self._path(role)
        if not path.exists():
            return None
        document = load_json_strict(path)
        field = _digest_field(document)
        if path.read_bytes() != canonical_bytes(document) + b"\n":
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_BYTES_INVALID")
        verify_self_digest(document, field)
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32QualificationMaterializerError(
                "V32_QUALIFICATION_MATERIAL_BYTES_INVALID"
            ) from exc
        return document

    def binding(self, role: str) -> Mapping[str, str]:
        document = self.load(role)
        if document is None:
            raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_MISSING")
        path = self._path(role)
        field = _digest_field(document)
        return {
            "relative_ref": path.relative_to(self.project_root).as_posix(),
            "schema_id": str(document["schema_id"]),
            "digest_field": field,
            "semantic_digest": str(document[field]),
            "physical_sha256": hashlib.sha256(
                canonical_bytes(dict(document)) + b"\n"
            ).hexdigest(),
        }

    def persist(self, role: str, document: Mapping[str, Any]) -> Mapping[str, Any]:
        _digest_field(document)
        path = self._path(role)
        if path.exists():
            existing = self.load(role)
            if existing != dict(document):
                raise V32QualificationMaterializerError("V32_QUALIFICATION_MATERIAL_CONFLICT")
            confirm_existing_json(path, document)
            return {"state_changed": False, "role": role, "binding": self.binding(role)}
        write_once_json(path, document)
        return {"state_changed": True, "role": role, "binding": self.binding(role)}

    def predecessor_bindings(self) -> dict[str, dict[str, str]]:
        """Replay and bind the exact material set present at call time."""

        result: dict[str, dict[str, str]] = {}
        for path in sorted(self.roles.glob("*.json")):
            if path.is_symlink():
                raise V32QualificationMaterializerError(
                    "V32_QUALIFICATION_MATERIAL_PATH_INVALID"
                )
            role = path.stem
            binding = self.binding(role)
            result[role] = {
                "path": binding["relative_ref"],
                "schema_id": binding["schema_id"],
                "digest_field": binding["digest_field"],
                "semantic_digest": binding["semantic_digest"],
                "physical_sha256": binding["physical_sha256"],
            }
        return result


class LocalV32QualificationMaterializer:
    """Advance one real qualification material or mailbox boundary per call."""

    def __init__(
        self,
        *,
        project_root: Path,
        authority_root_relative_ref: str,
        material_store: LocalV32QualificationMaterialStore,
        source_store: LocalV32CycleSourceAdmissionStore,
        admitted_source_store: LocalV32CycleSourceAdmissionStore,
        mailbox: LocalV32CurrentRootAgentMailbox,
        probe_store: LocalV32QualificationMonitorProbeStore,
        qualification_authority: Mapping[str, Any],
        qualification_authority_binding: Mapping[str, Any],
        current_codex_attempt_reservation: Mapping[str, Any],
        active_authority_projection: Mapping[str, Any],
        source_qualification_id: str,
        clock: Callable[[], str],
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.authority_root = PurePosixPath(authority_root_relative_ref).as_posix()
        self.store = material_store
        self.source = source_store
        self.admitted = admitted_source_store
        self.mailbox = mailbox
        self.probe = probe_store
        self.authority = dict(qualification_authority)
        self.authority_binding = dict(qualification_authority_binding)
        self.current_codex_attempt_reservation = dict(
            current_codex_attempt_reservation
        )
        self.projection = dict(active_authority_projection)
        self.qualification_id = source_qualification_id
        self.clock = clock
        self.public = V32InfrastructurePublicEvidenceVerifier()

    def _load_fixed(self, suffix: str) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        path = self.project_root / self.authority_root / suffix
        document = load_json_strict(path)
        field = _digest_field(document)
        payload = path.read_bytes()
        if payload != canonical_bytes(document) + b"\n":
            raise V32QualificationMaterializerError("V32_QUALIFICATION_FIXED_BYTES_INVALID")
        return document, {
            "relative_ref": path.relative_to(self.project_root).as_posix(),
            "schema_id": str(document["schema_id"]),
            "digest_field": field,
            "semantic_digest": str(document[field]),
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _adapter(self) -> LocalV32AnalysisMaterialAdapter:
        authority_documents = {}
        for role, (suffix, _) in _AUTHORITY_FILES.items():
            authority_documents[role] = self._load_fixed(suffix)[0]
        supports: dict[str, Mapping[str, Any]] = {}
        support_bindings: dict[str, Mapping[str, str]] = {}
        for role, suffix in _SUPPORT_FILES.items():
            supports[role], support_bindings[role] = self._load_fixed(suffix)
        theory, theory_binding = self._load_fixed("theory-semantic-document.json")
        return LocalV32AnalysisMaterialAdapter(
            verified_target_authority_bundle=authority_documents,
            active_authority_projection=self.projection,
            theory_semantic_document=theory,
            theory_semantic_document_binding=theory_binding,
            frozen_support_documents=supports,
            frozen_support_bindings=support_bindings,
        )

    def _persist(self, role: str, document: Mapping[str, Any]) -> Mapping[str, Any]:
        self._phase(f"MATERIAL_PERSIST:{role.upper()}")
        result = self.store.persist(role, document)
        return {
            "status": "PENDING",
            "boundary_kind": f"QUALIFICATION_MATERIAL_PERSISTED:{role}",
            "state_changed": bool(result["state_changed"]),
            "observed_state_digest": result["binding"]["semantic_digest"],
        }

    def _current_codex_time(self) -> str:
        observed_at = _time(self.clock)
        return verify_v32_current_codex_attempt_time_v1(
            qualification_authority=self.authority,
            reservation=self.current_codex_attempt_reservation,
            observed_at=observed_at,
        )

    def _phase(self, value: str) -> None:
        self._active_materialization_phase = value

    def verification_scope(self) -> ContextManager[None]:
        """Own graph verification for one caller-defined material burst."""

        return self.public.verification_scope()

    def advance_once(self) -> Mapping[str, Any]:
        """Advance one boundary and attach its actual entered phase on failure."""

        self._phase("MATERIALIZATION:ENTRY")
        try:
            # One materialization boundary is the owning verification request.
            # Projection, registry, and Agent-view verification may all need the
            # same strict current graph snapshot during this call; keep their
            # successful reconstruction local to this owner only.  During a
            # bounded qualification wake this inner scope nests inside the
            # outer burst scope.  Any append changes the strict snapshot key,
            # so the prior reconstruction cannot be reused for changed bytes.
            with self.public.verification_scope():
                return self._advance_once_impl()
        except Exception as exc:
            failure = V32QualificationMaterializerError(
                "V32_QUALIFICATION_MATERIALIZATION_PHASE_FAILED"
            )
            failure.materialization_phase = self._active_materialization_phase
            raise failure from exc

    def _advance_once_impl(self) -> Mapping[str, Any]:
        self._phase("TIME:CURRENT_CODEX_WINDOW")
        self._current_codex_time()
        run_id = str(self.authority["run_id"])
        self._phase("SOURCE_REPLAY:QUALIFICATION")
        qualification = verify_durable_v32_public_source_qualification(
            store=self.source,
            qualification_id=self.qualification_id,
            active_authority=self.projection,
        )
        self._phase("SOURCE_REPLAY:ADMISSION")
        admission = verify_durable_v32_cycle_source_admission(
            run_store=self.admitted,
            run_id=run_id,
            cycle_index=1,
            expected_authority_projection_digest=self.projection[ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD],
            expected_governing_authority_digest=self.projection[GOVERNING_AUTHORITY_DIGEST_FIELD],
            expected_experiment_contract_digest=self.projection["experiment_contract_digest"],
        )
        self._phase("SOURCE_REPLAY:DURABLE_RECEIPT")
        replay = verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=self.public,
            source_store=self.source,
            run_store=self.admitted,
            active_authority=self.projection,
            qualification_id=self.qualification_id,
            run_id=run_id,
            cycle_index=1,
        )
        source_roles = (
            ("active_authority_projection", self.projection),
            ("source_capture", qualification.source_capture),
            ("source_snapshot", qualification.market_snapshot),
            ("source_qualification", qualification.formal_qualification),
            ("cycle_source_admission", admission["cycle_source_admission"]),
            ("public_market_analysis_bundle", qualification.public_market_analysis_bundle),
            ("support_pit_registry", qualification.pit_registry),
            ("durable_source_replay", replay["durable_source_replay_receipt"]),
        )
        for role, document in source_roles:
            self._phase(f"MATERIAL_REPLAY:{role.upper()}")
            if self.store.load(role) is None:
                return self._persist(role, document)

        self._phase("MATERIAL_REPLAY:PUBLIC_MARKET_ANALYSIS_BUNDLE")
        bundle = self.store.load("public_market_analysis_bundle")
        pit = self.store.load("support_pit_registry")
        admission_document = self.store.load("cycle_source_admission")
        assert bundle is not None and pit is not None and admission_document is not None
        decision_time = str(qualification.formal_qualification["decision_time"])
        permit = {
            "permit_kind": "ANALYSIS_TICK",
            "run_id": run_id,
            "analysis_cycle_index": 1,
            "analysis_decision_at": decision_time,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_access": False,
            "order_submission": False,
        }
        self._phase("MATERIAL_REPLAY:PUBLIC_MARKET_GRAPH_PROJECTION")
        projection = self.store.load("public_market_graph_projection")
        if projection is None:
            self._phase("MATERIAL_BUILD:PUBLIC_MARKET_GRAPH_PROJECTION")
            return self._persist(
                "public_market_graph_projection",
                build_v32_public_market_graph_projection_v1(bundle, previous_projection=None),
            )
        graph_registry = self.store.load("support_graph_registry")
        if graph_registry is None:
            self._phase("MATERIAL_BUILD:SUPPORT_GRAPH_REGISTRY")
            return self._persist(
                "support_graph_registry",
                build_v32_verified_graph_dependency_registry_v1(
                    graph_projection=projection,
                    analysis_bundle=bundle,
                    decision_time=decision_time,
                    previous_projection=None,
                ),
            )
        availability = self.store.load("verified_pit_evidence_availability_registry")
        if availability is None:
            self._phase(
                "MATERIAL_BUILD:VERIFIED_PIT_EVIDENCE_AVAILABILITY_REGISTRY"
            )
            return self._persist(
                "verified_pit_evidence_availability_registry",
                build_v32_verified_pit_evidence_availability_registry_v1(
                    public_evidence_verifier=self.public,
                    public_market_analysis_bundle=bundle,
                    pit_evidence_registry=pit,
                ),
            )
        market_view = self.store.load("agent_market_graph_view")
        if market_view is None:
            self._phase("MATERIAL_BUILD:AGENT_MARKET_GRAPH_VIEW")
            return self._persist(
                "agent_market_graph_view",
                build_v32_agent_market_graph_view_v1(
                    public_evidence_verifier=self.public,
                    public_market_analysis_bundle=bundle,
                    public_market_graph_projection=projection,
                    pit_evidence_registry=pit,
                    graph_dependency_registry=graph_registry,
                    pit_evidence_availability_registry=availability,
                    previous_public_market_graph_projection=None,
                ),
            )
        self._phase("FIXED_SUPPORT_REPLAY:ANALYSIS_ADAPTER")
        adapter = self._adapter()
        timeframe = self.store.load("timeframe_context")
        if timeframe is None:
            self._phase("MATERIAL_BUILD:TIMEFRAME_CONTEXT")
            return self._persist(
                "timeframe_context",
                adapter.build_timeframe_context(
                    permit=permit,
                    public_market_analysis_bundle=bundle,
                    previous_timeframe_context=None,
                ),
            )
        proposal_packet = self.store.load("proposal_packet")
        if proposal_packet is None:
            self._phase("MATERIAL_BUILD:PROPOSAL_PACKET")
            current = {
                "active_authority_projection": self.projection,
                "cycle_source_admission": admission_document,
                "public_market_analysis_bundle": bundle,
                "public_market_graph_projection": projection,
                "pit_evidence_registry": pit,
                "graph_dependency_registry": graph_registry,
                "durable_source_replay_receipt": self.store.load("durable_source_replay"),
                "pit_evidence_availability_registry": availability,
                "agent_market_graph_view": market_view,
                "timeframe_context_state": timeframe,
            }
            bindings = {
                key: self.store.binding(
                    {
                        "pit_evidence_registry": "support_pit_registry",
                        "graph_dependency_registry": "support_graph_registry",
                        "durable_source_replay_receipt": "durable_source_replay",
                        "pit_evidence_availability_registry": "verified_pit_evidence_availability_registry",
                        "timeframe_context_state": "timeframe_context",
                    }.get(key, key)
                )
                for key in current
            }
            proposal_packet = adapter.build_proposal_packet(
                permit=permit,
                active_authority_projection=self.projection,
                current_artifacts=current,
                current_bindings=bindings,
                previous_artifacts={
                    "dynamic_state": None, "action_plan": None, "timeframe_context": None
                },
                previous_bindings={
                    "dynamic_state": None, "action_plan": None, "timeframe_context": None
                },
                matured_outcome_receipts=[],
                matured_outcome_receipt_bindings=[],
            )
            return self._persist("proposal_packet", proposal_packet)
        self._phase("CONTEXT_PACKAGE:PROPOSAL")
        proposal_package = adapter.lossless_context_package(
            stage="PROPOSAL",
            canonical_packet=proposal_packet,
            canonical_packet_binding=self.store.binding("proposal_packet"),
        )
        proposal_input = self.store.load("proposal_input")
        if proposal_input is None:
            self._phase("MATERIAL_BUILD:PROPOSAL_INPUT")
            return self._persist(
                "proposal_input",
                build_v32_agent_input_context_v1(
                    agent_stage="PROPOSAL",
                    canonical_packet=proposal_packet,
                    canonical_packet_binding=self.store.binding("proposal_packet"),
                    created_at=self._current_codex_time(),
                    **({"lossless_context_package": proposal_package} if proposal_package else {}),
                ),
            )
        self._phase("MAILBOX_REPLAY:CHECKPOINT")
        if not self.mailbox.checkpoint_exists(cycle_index=1):
            self._phase("MAILBOX_WRITE:INITIALIZE")
            checkpoint = self.mailbox.initialize_checkpoint(
                mailbox_id=f"qualification::{run_id}",
                run_id=run_id,
                cycle_index=1,
                created_at=str(self.current_codex_attempt_reservation["reserved_at"]),
            )
            return {
                "status": "PENDING", "boundary_kind": "QUALIFICATION_MAILBOX_INITIALIZED",
                "state_changed": True, "observed_state_digest": checkpoint[MAILBOX_DIGEST_FIELD],
            }
        mailbox_checkpoint = self.mailbox.load_checkpoint(run_id=run_id, cycle_index=1)
        proposal_status = mailbox_checkpoint["stage_states"]["PROPOSAL"]["status"]
        if proposal_status == "READY":
            self._phase("MAILBOX_WRITE:PROPOSAL_ENQUEUE")
            result = self.mailbox.enqueue_request(
                run_id=run_id, cycle_index=1,
                expected_checkpoint_digest=mailbox_checkpoint[MAILBOX_DIGEST_FIELD],
                agent_input_context=proposal_input,
                agent_input_context_binding=self.store.binding("proposal_input"),
                reserved_at=proposal_input["created_at"],
                **({"lossless_context_package": proposal_package} if proposal_package else {}),
            )
            return {"status": "PENDING", "boundary_kind": "QUALIFICATION_PROPOSAL_ENQUEUED", "state_changed": True, "observed_state_digest": result["checkpoint"][MAILBOX_DIGEST_FIELD]}
        if proposal_status in {"REQUESTED", "CLAIMED"}:
            return {"status": "AWAITING_AGENT", "boundary_kind": "NO_ADVANCE_AWAITING_PROPOSAL", "state_changed": False, "observed_state_digest": mailbox_checkpoint[MAILBOX_DIGEST_FIELD]}
        try:
            proposal_chain = self.mailbox.load_stage_chain(
                run_id=run_id, cycle_index=1, stage="PROPOSAL"
            )
        except V32CurrentRootAgentMailboxStoreError as exc:
            if proposal_status != "DELIVERED" or str(exc) not in {
                "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE",
                "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE",
            }:
                raise
            proposal_chain = self.mailbox.load_verified_recovery_stage_view(
                run_id=run_id, cycle_index=1, stage="PROPOSAL"
            )
        if proposal_status == "DELIVERED":
            self._phase("MAILBOX_WRITE:PROPOSAL_CONSUME")
            result = self.mailbox.consume_delivery(
                run_id=run_id, cycle_index=1, stage="PROPOSAL",
                expected_checkpoint_digest=mailbox_checkpoint[MAILBOX_DIGEST_FIELD],
                consumed_at=proposal_chain["agent_delivery"]["delivered_at"],
            )
            return {"status": "PENDING", "boundary_kind": "QUALIFICATION_PROPOSAL_CONSUMED", "state_changed": True, "observed_state_digest": result["checkpoint"][MAILBOX_DIGEST_FIELD]}
        if proposal_status != "CONSUMED":
            raise V32QualificationMaterializerError("V32_QUALIFICATION_PROPOSAL_STATE_INVALID")
        proposal_receipt = self.store.load("proposal_compile_receipt")
        if proposal_receipt is None:
            self._phase("MATERIAL_BUILD:PROPOSAL_COMPILE_RECEIPT")
            proposal_receipt = compile_v32_proposal_delivery_v1(
                proposal_input_context=proposal_input,
                proposal_delivery=proposal_chain["agent_delivery"],
                proposal_consumption=proposal_chain["agent_consumption"],
                compiled_at=self._current_codex_time(),
                **({"proposal_lossless_context_package": proposal_package} if proposal_package else {}),
            )
            return self._persist("proposal_compile_receipt", proposal_receipt)
        for role, document in (
            ("dynamic_state", proposal_receipt["compiled_dynamic_research_state"]),
            ("action_evaluation", proposal_receipt["sealed_action_evaluation"]),
        ):
            self._phase(f"MATERIAL_REPLAY:{role.upper()}")
            if self.store.load(role) is None:
                return self._persist(role, document)
        state = self.store.load("dynamic_state")
        evaluation = self.store.load("action_evaluation")
        assert state is not None and evaluation is not None
        selection_packet = self.store.load("selection_packet")
        if selection_packet is None:
            self._phase("MATERIAL_BUILD:SELECTION_PACKET")
            selection_packet = build_v32_selection_canonical_packet_v1(
                proposal_input_context=proposal_input,
                proposal_input_context_binding=self.store.binding("proposal_input"),
                proposal_delivery=proposal_chain["agent_delivery"],
                proposal_delivery_binding=proposal_chain["delivery_receipt"]["agent_delivery_binding"],
                proposal_consumption=proposal_chain["agent_consumption"],
                proposal_consumption_binding=proposal_chain["consumption_receipt"]["agent_consumption_binding"],
                compiled_dynamic_research_state=state,
                compiled_dynamic_research_state_binding=self.store.binding("dynamic_state"),
                sealed_action_evaluation=evaluation,
                sealed_action_evaluation_binding=self.store.binding("action_evaluation"),
                prepared_at=self._current_codex_time(),
            )
            return self._persist("selection_packet", selection_packet)
        self._phase("CONTEXT_PACKAGE:SELECTION")
        selection_package = adapter.lossless_context_package(
            stage="SELECTION", canonical_packet=selection_packet,
            canonical_packet_binding=self.store.binding("selection_packet"),
        )
        selection_input = self.store.load("selection_input")
        if selection_input is None:
            self._phase("MATERIAL_BUILD:SELECTION_INPUT")
            return self._persist(
                "selection_input",
                build_v32_agent_input_context_v1(
                    agent_stage="SELECTION", canonical_packet=selection_packet,
                    canonical_packet_binding=self.store.binding("selection_packet"),
                    created_at=self._current_codex_time(),
                    **({"lossless_context_package": selection_package} if selection_package else {}),
                ),
            )
        mailbox_checkpoint = self.mailbox.load_checkpoint(run_id=run_id, cycle_index=1)
        selection_status = mailbox_checkpoint["stage_states"]["SELECTION"]["status"]
        if selection_status == "READY":
            self._phase("MAILBOX_WRITE:SELECTION_ENQUEUE")
            result = self.mailbox.enqueue_request(
                run_id=run_id, cycle_index=1,
                expected_checkpoint_digest=mailbox_checkpoint[MAILBOX_DIGEST_FIELD],
                agent_input_context=selection_input,
                agent_input_context_binding=self.store.binding("selection_input"),
                reserved_at=selection_input["created_at"],
                **({"lossless_context_package": selection_package} if selection_package else {}),
            )
            return {"status": "PENDING", "boundary_kind": "QUALIFICATION_SELECTION_ENQUEUED", "state_changed": True, "observed_state_digest": result["checkpoint"][MAILBOX_DIGEST_FIELD]}
        if selection_status in {"REQUESTED", "CLAIMED"}:
            return {"status": "AWAITING_AGENT", "boundary_kind": "NO_ADVANCE_AWAITING_SELECTION", "state_changed": False, "observed_state_digest": mailbox_checkpoint[MAILBOX_DIGEST_FIELD]}
        try:
            selection_chain = self.mailbox.load_stage_chain(
                run_id=run_id, cycle_index=1, stage="SELECTION"
            )
        except V32CurrentRootAgentMailboxStoreError as exc:
            if selection_status != "DELIVERED" or str(exc) not in {
                "V32_MAILBOX_STORE_DELIVERY_CHAIN_INCOMPLETE",
                "V32_MAILBOX_STORE_CONSUMPTION_CHAIN_INCOMPLETE",
            }:
                raise
            selection_chain = self.mailbox.load_verified_recovery_stage_view(
                run_id=run_id, cycle_index=1, stage="SELECTION"
            )
        if selection_status == "DELIVERED":
            self._phase("MAILBOX_WRITE:SELECTION_CONSUME")
            result = self.mailbox.consume_delivery(
                run_id=run_id, cycle_index=1, stage="SELECTION",
                expected_checkpoint_digest=mailbox_checkpoint[MAILBOX_DIGEST_FIELD],
                consumed_at=selection_chain["agent_delivery"]["delivered_at"],
            )
            return {"status": "PENDING", "boundary_kind": "QUALIFICATION_SELECTION_CONSUMED", "state_changed": True, "observed_state_digest": result["checkpoint"][MAILBOX_DIGEST_FIELD]}
        if selection_status != "CONSUMED":
            raise V32QualificationMaterializerError("V32_QUALIFICATION_SELECTION_STATE_INVALID")
        selection_receipt = self.store.load("selection_compile_receipt")
        if selection_receipt is None:
            self._phase("MATERIAL_BUILD:SELECTION_COMPILE_RECEIPT")
            selection_receipt = compile_v32_selection_delivery_v1(
                proposal_compile_receipt=proposal_receipt,
                selection_input_context=selection_input,
                selection_delivery=selection_chain["agent_delivery"],
                selection_consumption=selection_chain["agent_consumption"],
                compiled_at=self._current_codex_time(),
                **({"selection_lossless_context_package": selection_package} if selection_package else {}),
                **({"proposal_lossless_context_package": proposal_package} if proposal_package else {}),
            )
            return self._persist("selection_compile_receipt", selection_receipt)
        plan = self.store.load("action_plan")
        if plan is None:
            return self._persist("action_plan", selection_receipt["final_dynamic_action_plan"])
        self._phase("PROBE_REPLAY:SCHEDULE")
        prefix = self.probe.load_prefix() if (self.probe.store / "schedule.json").exists() else None
        if prefix is None:
            self._phase("PROBE_WRITE:SCHEDULE")
            self._current_codex_time()
            result = self.probe.initialize(
                build_v32_qualification_monitor_probe_v1(
                    probe_id=f"qualification-monitor-probe::{run_id}",
                    qualification_authority=self.authority,
                    final_action_plan_digest=plan[ACTION_PLAN_DIGEST_FIELD],
                    selection_consumption_digest=selection_chain["agent_consumption"][AGENT_CONSUMPTION_DIGEST_FIELD],
                    decision_time=selection_receipt["compiled_at"],
                )
            )
            return {**result, "status": "PENDING"}
        return {"status": "READY", "boundary_kind": "NO_ADVANCE_MATERIAL_COMPLETE", "state_changed": False, "observed_state_digest": plan[ACTION_PLAN_DIGEST_FIELD]}


__all__ = [
    "LocalV32QualificationMaterialStore",
    "LocalV32QualificationMaterializer",
    "STORE_ROOT",
    "V32QualificationMaterializerError",
]
