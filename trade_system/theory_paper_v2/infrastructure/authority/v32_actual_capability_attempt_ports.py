"""Minimal durable attempt adapters for the isolated V3.2 qualification.

The adapters own no authority creation and have no default transport or model.
Every public network boundary is injected.  Repeated controller wakes inspect
or advance the same durable attempt and return ``PENDING``; they never create a
second attempt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
import re
from typing import Any, Callable, Mapping

from ...application.v32_cycle_composition import run_v32_single_boundary_wake
from ...application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
)
from ...application.v32_durable_source_replay import (
    durable_source_replay_receipt_ref,
    compose_and_persist_v32_durable_source_replay_receipt,
    verify_durable_v32_source_replay_receipt,
)
from ...domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    QUALIFICATION_PROFILE,
    verify_v32_authority_v1,
)
from ...domain.v32_actual_capability_attempt_progress import (
    V32ActualCapabilityAttemptProgressError,
    verify_v32_actual_capability_attempt_progress_v1,
)
from ...domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
)
from ...domain.v32_runtime_support_contracts import (
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
)
from ...domain.v32_cycle_source_admission import (
    QUALIFICATION_DIGEST_FIELD,
    cycle_source_admission_ref,
    qualification_ref,
    verify_v32_active_authority_projection,
    verify_v32_formal_source_qualification,
)
from ...domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
)
from ..v32_current_root_agent_mailbox import LocalV32CurrentRootAgentMailbox
from ...v32_durable_json import ensure_directory_tree
from ..v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from ..v32_local_outcome_lane import LocalV32OutcomeLane
from ..v32_outcome_tick_store import LocalV32OutcomeTickStore
from ..v32_public_evidence_verifier import V32InfrastructurePublicEvidenceVerifier
from ..v32_public_source_collector import (
    V32PublicMarketBundleTransport,
    V32PublicSourceCollectorError,
    V32RawFirstOkxPublicBundleCollector,
    recover_durable_v32_public_source_failure_v1,
)
from ..v32_tick_supervisor_store import LocalV32TickSupervisorStore
from .v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from .v32_actual_capability_replay import (
    LocalV32ActualCapabilityEvidenceStore,
    compose_v32_current_codex_actual_evidence_root,
    compose_v32_outcome_monitor_actual_evidence_root,
    compose_v32_public_source_actual_evidence_root,
    verify_v32_actual_capability_evidence_root_v1,
)


class V32ActualCapabilityAttemptAdapterError(ValueError):
    """One durable adapter could not safely advance the current attempt."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32ActualCapabilityAttemptAdapterError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ActualCapabilityAttemptAdapterError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32ActualCapabilityAttemptAdapterError(code)
    return parsed.astimezone(UTC)


def verify_v32_current_codex_attempt_time_v1(
    *,
    qualification_authority: Mapping[str, Any],
    reservation: Mapping[str, Any],
    observed_at: str,
) -> str:
    """Bind every external Agent boundary to the sole hard phase-B window."""

    _authority(qualification_authority, "CURRENT_CODEX", reservation)
    observed = _time(observed_at, "V32_ACTUAL_CODEX_PORT_TIME_INVALID")
    reserved = _time(
        reservation.get("reserved_at"), "V32_ACTUAL_CODEX_PORT_TIME_INVALID"
    )
    if not (
        reserved
        <= observed
        <= reserved + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS)
    ):
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_CODEX_PORT_ATTEMPT_EXPIRED"
        )
    return observed_at


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ActualCapabilityAttemptAdapterError(code)
    return value


def _relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise V32ActualCapabilityAttemptAdapterError(code)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32ActualCapabilityAttemptAdapterError(code)
    return value


def _project_directory(project_root: Path, relative_ref: str) -> Path:
    root = Path(project_root).resolve(strict=True)
    target = root
    for part in PurePosixPath(
        _relative(relative_ref, "V32_ACTUAL_ATTEMPT_PATH_INVALID")
    ).parts:
        target = target / part
        if target.exists() and target.is_symlink():
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_ATTEMPT_PATH_INVALID"
            )
    ensure_directory_tree(target)
    try:
        target.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_PATH_INVALID"
        ) from exc
    return target


def _existing_project_directory(project_root: Path, relative_ref: str) -> Path:
    """Resolve a pre-existing evidence root without creating replay state."""

    root = Path(project_root).resolve(strict=True)
    target = root
    for part in PurePosixPath(
        _relative(relative_ref, "V32_ACTUAL_ATTEMPT_PATH_INVALID")
    ).parts:
        target = target / part
        if target.is_symlink():
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_ATTEMPT_PATH_INVALID"
            )
    if not target.is_dir():
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_EVIDENCE_ROOT_MISSING"
        )
    try:
        target.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_PATH_INVALID"
        ) from exc
    return target


def _authority(
    authority: Mapping[str, Any], capability: str, reservation: Mapping[str, Any]
) -> str:
    try:
        digest = verify_v32_authority_v1(authority)
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_AUTHORITY_INVALID"
        ) from exc
    if (
        authority.get("profile") != QUALIFICATION_PROFILE
        or authority.get("status") != "ACTIVE"
        or authority.get("authorized_operation") != "V32_ISOLATED_QUALIFICATION"
        or reservation.get("capability") != capability
        or reservation.get("qualification_run_id") != authority.get("run_id")
        or reservation.get("target_run_id") != authority.get("target_run_id")
        or reservation.get("qualification_authority_digest") != digest
        or reservation.get("attempt_number") != 1
        or reservation.get("retry_allowed") is not False
    ):
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_AUTHORITY_INVALID"
        )
    return digest


def _result(
    *,
    capability: str,
    status: str,
    state_changed: bool,
    pending_reason: str | None,
    resume_token: str | None,
    resume_requested_at: str | None,
    observed_state_digest: str,
    evidence_root: Mapping[str, Any] | None,
    evidence_root_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = {
        "capability": capability,
        "status": status,
        "state_changed": state_changed,
        "pending_reason": pending_reason,
        "resume_token": resume_token,
        "resume_requested_at": resume_requested_at,
        "observed_state_digest": _digest(
            observed_state_digest, "V32_ACTUAL_ATTEMPT_RESULT_INVALID"
        ),
        "evidence_root": None if evidence_root is None else dict(evidence_root),
        "evidence_root_binding": (
            None if evidence_root_binding is None else dict(evidence_root_binding)
        ),
        "attempt_count": 1,
        "retry_performed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    verify_v32_actual_capability_attempt_progress(result)
    return result


def verify_v32_actual_capability_attempt_progress(
    result: Mapping[str, Any],
) -> None:
    try:
        verify_v32_actual_capability_attempt_progress_v1(
            result,
            evidence_root_verifier=verify_v32_actual_capability_evidence_root_v1,
        )
    except V32ActualCapabilityAttemptProgressError as exc:
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_ATTEMPT_RESULT_INVALID"
        ) from exc


class V32PublicSourceQualificationAttemptPort:
    """One raw-first public bundle attempt plus local admission and replay."""

    capability = "PUBLIC_SOURCE"

    def __init__(
        self,
        *,
        project_root: Path,
        evidence_store: LocalV32ActualCapabilityEvidenceStore,
        source_store_root: str,
        run_store_root: str,
        source_qualification_id: str,
        active_authority_projection: Mapping[str, Any],
        transport: V32PublicMarketBundleTransport,
        clock: Callable[[], str],
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.evidence_store = evidence_store
        self.source_store_root = _relative(
            source_store_root, "V32_ACTUAL_PUBLIC_PORT_ROOT_INVALID"
        )
        self.run_store_root = _relative(
            run_store_root, "V32_ACTUAL_PUBLIC_PORT_ROOT_INVALID"
        )
        self.source_qualification_id = source_qualification_id
        verify_v32_active_authority_projection(active_authority_projection)
        self.active_authority_projection = dict(active_authority_projection)
        self.transport = transport
        self.clock = clock

    def _now(self) -> str:
        value = self.clock()
        _time(value, "V32_ACTUAL_PUBLIC_PORT_CLOCK_INVALID")
        return value

    def _project_failure_binding(
        self, binding: Mapping[str, Any]
    ) -> dict[str, str]:
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            }
        ):
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_PUBLIC_PORT_FAILURE_BINDING_INVALID"
            )
        return {
            "path": f"{self.source_store_root}/{_relative(binding['relative_ref'], 'V32_ACTUAL_PUBLIC_PORT_FAILURE_BINDING_INVALID')}",
            "schema_id": str(binding["schema_id"]),
            "digest_field": str(binding["digest_field"]),
            "semantic_digest": _digest(
                binding["semantic_digest"],
                "V32_ACTUAL_PUBLIC_PORT_FAILURE_BINDING_INVALID",
            ),
            "physical_sha256": _digest(
                binding["physical_sha256"],
                "V32_ACTUAL_PUBLIC_PORT_FAILURE_BINDING_INVALID",
            ),
        }

    def _recover_failure(self) -> dict[str, Any]:
        source_store = LocalV32CycleSourceAdmissionStore(
            _existing_project_directory(
                self.project_root, self.source_store_root
            )
        )
        return recover_durable_v32_public_source_failure_v1(
            store=source_store,
            qualification_id=self.source_qualification_id,
            active_authority=self.active_authority_projection,
            expected_run_id=str(
                self.active_authority_projection["authorized_run_id"]
            ),
            expected_cycle_index=1,
        )

    def verify_failure_evidence_binding(
        self, binding_value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        recovered = self._recover_failure()
        expected = self._project_failure_binding(
            recovered["failure_evidence_binding"]
        )
        if dict(binding_value) != expected:
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_PUBLIC_PORT_FAILURE_BINDING_MISMATCH"
            )
        return expected

    def advance_once(
        self,
        *,
        qualification_authority: Mapping[str, Any],
        reservation: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        resume_token: str | None,
        resume_requested_at: str | None,
    ) -> Mapping[str, Any]:
        del resume_token, resume_requested_at
        authority_digest = _authority(
            qualification_authority, self.capability, reservation
        )
        if (
            self.active_authority_projection.get("authorized_run_id")
            != qualification_authority.get("run_id")
            or self.active_authority_projection.get(
                "governing_authority_digest"
            )
            != authority_digest
        ):
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_PUBLIC_PORT_AUTHORITY_INVALID"
            )
        recovered = self.evidence_store.load_evidence_root(self.capability)
        if recovered is not None:
            if recovered["evidence_root"].get("attempt_reservation_binding") != dict(
                reservation_binding
            ):
                raise V32ActualCapabilityAttemptAdapterError(
                    "V32_ACTUAL_PUBLIC_PORT_RESERVATION_INVALID"
                )
            return _result(
                capability=self.capability,
                status="COMPLETE",
                state_changed=False,
                pending_reason=None,
                resume_token=None,
                resume_requested_at=None,
                observed_state_digest=recovered["evidence_root_binding"][
                    "semantic_digest"
                ],
                evidence_root=recovered["evidence_root"],
                evidence_root_binding=recovered["evidence_root_binding"],
            )

        source_store = LocalV32CycleSourceAdmissionStore(
            _project_directory(self.project_root, self.source_store_root)
        )
        run_store = LocalV32CycleSourceAdmissionStore(
            _project_directory(self.project_root, self.run_store_root)
        )
        qualification_relative_ref = qualification_ref(
            self.source_qualification_id
        )
        attempt_relative_ref = (
            qualification_relative_ref.rsplit("/", 1)[0]
            + "/attempt-reservation.json"
        )
        collector = V32RawFirstOkxPublicBundleCollector(
            transport=self.transport,
            clock=self.clock,
            store=source_store,
        )
        if not source_store.artifact_exists(relative_ref=attempt_relative_ref):
            try:
                collector.collect_and_qualify(
                    qualification_id=self.source_qualification_id,
                    run_id=str(qualification_authority["run_id"]),
                    cycle_index=1,
                    active_authority=self.active_authority_projection,
                )
            except V32PublicSourceCollectorError as exc:
                binding = exc.failure_evidence_binding
                if binding is not None:
                    project_binding = self._project_failure_binding(binding)
                    exc.failure_evidence_binding = (
                        self.verify_failure_evidence_binding(project_binding)
                    )
                raise exc from None
        if not source_store.artifact_exists(
            relative_ref=qualification_relative_ref
        ):
            try:
                collector.seal_interrupted_attempt_failure(
                    qualification_id=self.source_qualification_id,
                    run_id=str(qualification_authority["run_id"]),
                    cycle_index=1,
                    active_authority=self.active_authority_projection,
                )
            except V32PublicSourceCollectorError as exc:
                binding = exc.failure_evidence_binding
                if binding is not None:
                    project_binding = self._project_failure_binding(binding)
                    exc.failure_evidence_binding = (
                        self.verify_failure_evidence_binding(project_binding)
                    )
                raise exc from None
            try:
                recovered_failure = self._recover_failure()
                project_binding = self._project_failure_binding(
                    recovered_failure["failure_evidence_binding"]
                )
                project_binding = dict(
                    self.verify_failure_evidence_binding(project_binding)
                )
            except (OSError, TypeError, ValueError):
                raise V32ActualCapabilityAttemptAdapterError(
                    "V32_ACTUAL_PUBLIC_PORT_PARTIAL_ATTEMPT_FAILED_CLOSED"
                ) from None
            failure_document = recovered_failure["failure"]
            if isinstance(failure_document.get("failure_code"), str):
                recovered_failure_code = failure_document["failure_code"]
            else:
                failure_codes = failure_document.get("failure_codes")
                if (
                    not isinstance(failure_codes, list)
                    or not failure_codes
                    or not isinstance(failure_codes[-1], str)
                ):
                    raise V32ActualCapabilityAttemptAdapterError(
                        "V32_ACTUAL_PUBLIC_PORT_RECOVERED_FAILURE_CODE_INVALID"
                    )
                recovered_failure_code = failure_codes[-1]
            recovered_error = V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_PUBLIC_PORT_RECOVERED_FAILED_CLOSED:"
                f"{recovered_failure_code}"
            )
            recovered_error.failure_evidence_binding = project_binding
            raise recovered_error
        qualification = source_store.read_document(
            relative_ref=qualification_relative_ref,
            digest_field=QUALIFICATION_DIGEST_FIELD,
        )
        verify_v32_formal_source_qualification(qualification)
        admission_ref = cycle_source_admission_ref(1)
        if not run_store.artifact_exists(relative_ref=admission_ref):
            admit_fresh_v32_source_to_cycle(
                source_store=source_store,
                run_store=run_store,
                active_authority=self.active_authority_projection,
                qualification_id=self.source_qualification_id,
                run_id=str(qualification_authority["run_id"]),
                cycle_index=1,
                decision_time=qualification["decision_time"],
                # Qualification and admission are one local atomic boundary.
                # The admission contract requires this timestamp not to be
                # later than the already sealed decision boundary.
                admitted_at=qualification["decision_time"],
            )
        replay_ref = durable_source_replay_receipt_ref(1)
        if run_store.artifact_exists(relative_ref=replay_ref):
            replay = verify_durable_v32_source_replay_receipt(
                public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
                source_store=source_store,
                run_store=run_store,
                active_authority=self.active_authority_projection,
                qualification_id=self.source_qualification_id,
                run_id=str(qualification_authority["run_id"]),
                cycle_index=1,
            )
        else:
            replay = compose_and_persist_v32_durable_source_replay_receipt(
                public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
                source_store=source_store,
                run_store=run_store,
                active_authority=self.active_authority_projection,
                qualification_id=self.source_qualification_id,
                run_id=str(qualification_authority["run_id"]),
                cycle_index=1,
                replayed_at=self._now(),
            )
        replay_receipt = replay["durable_source_replay_receipt"]
        root = compose_v32_public_source_actual_evidence_root(
            project_root=self.project_root,
            qualification_authority=qualification_authority,
            attempt_reservation_binding=reservation_binding,
            active_authority_projection=self.active_authority_projection,
            source_store_root=self.source_store_root,
            run_store_root=self.run_store_root,
            qualification_id=self.source_qualification_id,
            started_at=replay_receipt["raw_before_derived_proof"][
                "attempt_started_at"
            ],
            completed_at=replay_receipt["replayed_at"],
        )
        binding = self.evidence_store.persist_evidence_root(root)
        return _result(
            capability=self.capability,
            status="COMPLETE",
            state_changed=True,
            pending_reason=None,
            resume_token=None,
            resume_requested_at=None,
            observed_state_digest=binding["semantic_digest"],
            evidence_root=root,
            evidence_root_binding=binding,
        )


class V32CurrentCodexQualificationAttemptPort:
    """Initialize or inspect the durable mailbox; Codex acts outside this port."""

    capability = "CURRENT_CODEX"

    def __init__(
        self,
        *,
        project_root: Path,
        evidence_store: LocalV32ActualCapabilityEvidenceStore,
        mailbox_store_root: str,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.evidence_store = evidence_store
        self.mailbox_store_root = _relative(
            mailbox_store_root, "V32_ACTUAL_CODEX_PORT_ROOT_INVALID"
        )
        self.clock = clock

    def verify_failure_evidence_binding(
        self, binding_value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        del binding_value
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_CODEX_FAILURE_EVIDENCE_UNSUPPORTED"
        )

    def advance_once(
        self,
        *,
        qualification_authority: Mapping[str, Any],
        reservation: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        resume_token: str | None,
        resume_requested_at: str | None,
    ) -> Mapping[str, Any]:
        del resume_token, resume_requested_at
        _authority(qualification_authority, self.capability, reservation)
        recovered = self.evidence_store.load_evidence_root(self.capability)
        if recovered is not None:
            return _result(
                capability=self.capability,
                status="COMPLETE",
                state_changed=False,
                pending_reason=None,
                resume_token=None,
                resume_requested_at=None,
                observed_state_digest=recovered["evidence_root_binding"][
                    "semantic_digest"
                ],
                evidence_root=recovered["evidence_root"],
                evidence_root_binding=recovered["evidence_root_binding"],
            )
        if self.clock is not None:
            verify_v32_current_codex_attempt_time_v1(
                qualification_authority=qualification_authority,
                reservation=reservation,
                observed_at=self.clock(),
            )
        mailbox = LocalV32CurrentRootAgentMailbox(
            _project_directory(self.project_root, self.mailbox_store_root)
        )
        if mailbox.checkpoint_exists(cycle_index=1):
            checkpoint = mailbox.load_checkpoint(
                run_id=str(qualification_authority["run_id"]), cycle_index=1
            )
        else:
            checkpoint = mailbox.initialize_checkpoint(
                mailbox_id=f"qualification::{qualification_authority['run_id']}",
                run_id=str(qualification_authority["run_id"]),
                cycle_index=1,
                created_at=str(reservation["reserved_at"]),
            )
        if checkpoint.get("status") != "COMPLETE":
            pending = mailbox.next_pending_request(
                run_id=str(qualification_authority["run_id"]), cycle_index=1
            )
            reason = (
                f"MAILBOX_{checkpoint['status']}"
                if pending is None
                else f"MAILBOX_{pending['next_action']}"
            )
            return _result(
                capability=self.capability,
                status="PENDING",
                state_changed=False,
                pending_reason=reason,
                resume_token=None,
                resume_requested_at=None,
                observed_state_digest=checkpoint[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                evidence_root=None,
                evidence_root_binding=None,
            )
        proposal = mailbox.load_stage_chain(
            run_id=str(qualification_authority["run_id"]),
            cycle_index=1,
            stage="PROPOSAL",
        )
        selection = mailbox.load_stage_chain(
            run_id=str(qualification_authority["run_id"]),
            cycle_index=1,
            stage="SELECTION",
        )
        root = compose_v32_current_codex_actual_evidence_root(
            project_root=self.project_root,
            qualification_authority=qualification_authority,
            attempt_reservation_binding=reservation_binding,
            mailbox_store_root=self.mailbox_store_root,
            started_at=proposal["request"]["reserved_at"],
            completed_at=selection["consumption_receipt"]["consumed_at"],
        )
        binding = self.evidence_store.persist_evidence_root(root)
        return _result(
            capability=self.capability,
            status="COMPLETE",
            state_changed=True,
            pending_reason=None,
            resume_token=None,
            resume_requested_at=None,
            observed_state_digest=binding["semantic_digest"],
            evidence_root=root,
            evidence_root_binding=binding,
        )


class V32OutcomeMonitorQualificationAttemptPort:
    """Advance only the dedicated one-shot qualification monitor probe."""

    capability = "OUTCOME_MONITOR"

    def __init__(
        self,
        *,
        project_root: Path,
        evidence_store: LocalV32ActualCapabilityEvidenceStore,
        probe_store_root: str,
        capture_port: Any,
        clock: Callable[[], str],
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.evidence_store = evidence_store
        self.probe_store_root = _relative(
            probe_store_root, "V32_ACTUAL_OUTCOME_PORT_ROOT_INVALID"
        )
        self.probe_store = LocalV32QualificationMonitorProbeStore(
            _project_directory(self.project_root, self.probe_store_root),
            capture_port=capture_port,
            clock=clock,
        )

    def _now(self) -> str:
        raise AssertionError("qualification probe clock is owned by its store")

    def verify_failure_evidence_binding(
        self, binding_value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        del binding_value
        raise V32ActualCapabilityAttemptAdapterError(
            "V32_ACTUAL_OUTCOME_FAILURE_EVIDENCE_UNSUPPORTED"
        )

    def advance_once(
        self,
        *,
        qualification_authority: Mapping[str, Any],
        reservation: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        resume_token: str | None,
        resume_requested_at: str | None,
    ) -> Mapping[str, Any]:
        _authority(qualification_authority, self.capability, reservation)
        recovered = self.evidence_store.load_evidence_root(self.capability)
        if recovered is not None:
            return _result(
                capability=self.capability,
                status="COMPLETE",
                state_changed=False,
                pending_reason=None,
                resume_token=resume_token,
                resume_requested_at=resume_requested_at,
                observed_state_digest=recovered["evidence_root_binding"][
                    "semantic_digest"
                ],
                evidence_root=recovered["evidence_root"],
                evidence_root_binding=recovered["evidence_root_binding"],
            )
        del resume_token, resume_requested_at
        prefix = self.probe_store.load_prefix()
        if prefix["failure"] is not None:
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_OUTCOME_PORT_FAILED_CLOSED"
            )
        if prefix["completion"] is not None:
            root = compose_v32_outcome_monitor_actual_evidence_root(
                project_root=self.project_root,
                qualification_authority=qualification_authority,
                attempt_reservation_binding=reservation_binding,
                probe_store_root=self.probe_store_root,
                probe_id=str(prefix["schedule"]["probe_id"]),
                started_at=prefix["completion"]["started_at"],
                completed_at=prefix["completion"]["completed_at"],
            )
            binding = self.evidence_store.persist_evidence_root(root)
            return _result(
                capability=self.capability,
                status="COMPLETE",
                state_changed=True,
                pending_reason=None,
                resume_token=None,
                resume_requested_at=None,
                observed_state_digest=binding["semantic_digest"],
                evidence_root=root,
                evidence_root_binding=binding,
            )

        wake = self.probe_store.advance_once()
        if wake["status"] == "FAILED_CLOSED":
            raise V32ActualCapabilityAttemptAdapterError(
                "V32_ACTUAL_OUTCOME_PORT_FAILED_CLOSED"
            )
        return _result(
            capability=self.capability,
            status="PENDING",
            state_changed=bool(wake["state_changed"]),
            pending_reason=str(wake["boundary_kind"]),
            resume_token=None,
            resume_requested_at=None,
            observed_state_digest=str(wake["observed_state_digest"]),
            evidence_root=None,
            evidence_root_binding=None,
        )


__all__ = [
    "V32ActualCapabilityAttemptAdapterError",
    "V32CurrentCodexQualificationAttemptPort",
    "V32OutcomeMonitorQualificationAttemptPort",
    "V32PublicSourceQualificationAttemptPort",
    "verify_v32_current_codex_attempt_time_v1",
    "verify_v32_actual_capability_attempt_progress",
]
