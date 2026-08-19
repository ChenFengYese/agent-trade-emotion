"""One-shot local composition for the V3.2 actual capability qualification.

The runner owns sequencing and receipt creation.  Capability attempts are
injected ports: this module has no transport, model, account, credential, or
order interface.  A durable reservation is written before each port is called,
so a partial failure cannot be retried under the same qualification root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from ..domain.governance.v32_authorization import (
    ACTUAL_CAPABILITY_RECEIPT_SPECS,
    AUTHORITY_SCHEMA_ID,
    CAPABILITY_KEYS,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_DIGEST_FIELD,
    QUALIFICATION_RECEIPT_SCHEMA_ID,
    build_v32_actual_capability_receipt_v1,
    build_v32_fresh_capability_qualification_receipt_v1,
    verify_v32_actual_capability_receipt_v1,
    verify_v32_authority_v1,
    verify_v32_fresh_capability_qualification_receipt_v1,
)
from ..domain.v32_runtime_support_contracts import (
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
)
from .v32_actual_capability_ports import (
    V32ActualCapabilityAttemptPort,
    V32ActualCapabilityEvidenceStorePort,
)


class V32ActualCapabilityQualificationError(ValueError):
    """The one-shot qualification composition failed closed."""


ATTEMPT_ORDER = ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
_ATTEMPT_RESULT_FIELDS = frozenset(
    {"evidence_root", "evidence_root_binding"}
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32ActualCapabilityQualificationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ActualCapabilityQualificationError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32ActualCapabilityQualificationError(code)
    return parsed.astimezone(UTC)


def _clock_time(clock: Callable[[], str]) -> str:
    try:
        value = clock()
    except Exception as exc:
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_CLOCK_FAILED"
        ) from exc
    _time(value, "V32_ACTUAL_QUALIFICATION_CLOCK_INVALID")
    return value


def _enforce_current_codex_duration(
    *, capability: str, started: datetime, completed: datetime
) -> None:
    """Reject a Codex qualification that cannot fit the runtime safety window.

    The 120-second target remains an observed service objective.  The 660-second
    boundary is the hard safety gate because a slower analysis cannot finish
    before the runtime's reserved outcome-monitor margin.
    """

    if (
        capability == "CURRENT_CODEX"
        and (completed - started).total_seconds()
        > TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_CURRENT_CODEX_DURATION_EXCEEDED"
        )


def _attempt_ports(
    value: Any,
) -> dict[str, V32ActualCapabilityAttemptPort]:
    if not isinstance(value, Mapping) or set(value) != set(CAPABILITY_KEYS):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_ATTEMPT_PORTS_INVALID"
        )
    result: dict[str, V32ActualCapabilityAttemptPort] = {}
    for capability in CAPABILITY_KEYS:
        port = value.get(capability)
        if not callable(getattr(port, "execute_once", None)):
            raise V32ActualCapabilityQualificationError(
                "V32_ACTUAL_QUALIFICATION_ATTEMPT_PORTS_INVALID"
            )
        result[capability] = port
    return result


def seal_v32_actual_capability_qualification_from_completed_attempts(
    *,
    project_root: Path,
    evidence_store: V32ActualCapabilityEvidenceStorePort,
    qualification_id: str,
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, str],
    completed_attempts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal receipts from three already durable attempts without retrying them."""

    if (
        evidence_store.project_root != Path(project_root).resolve(strict=True)
        or not isinstance(completed_attempts, Mapping)
        or set(completed_attempts) != set(CAPABILITY_KEYS)
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_COMPLETED_SET_INVALID"
        )
    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
        durable_authority = evidence_store.load_binding(
            qualification_authority_binding,
            verifier=verify_v32_authority_v1,
        )
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_AUTHORITY_INVALID"
        ) from exc
    if (
        durable_authority != dict(qualification_authority)
        or qualification_authority.get("schema_id") != AUTHORITY_SCHEMA_ID
        or qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or qualification_authority.get("status") != "ACTIVE"
        or qualification_authority.get("authorized_operation")
        != "V32_ISOLATED_QUALIFICATION"
        or qualification_authority.get("run_id")
        == qualification_authority.get("target_run_id")
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_AUTHORITY_INVALID"
        )
    authority_recorded = _time(
        qualification_authority["recorded_at"],
        "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID",
    )
    replay_registry = evidence_store.full_replay_registry()
    if (
        not isinstance(replay_registry, Mapping)
        or set(replay_registry) != set(CAPABILITY_KEYS)
        or any(
            not callable(replay_registry.get(capability))
            for capability in CAPABILITY_KEYS
        )
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_FULL_REPLAY_REGISTRY_INVALID"
        )

    actual_receipts: dict[str, dict[str, Any]] = {}
    actual_receipt_bindings: dict[str, dict[str, str]] = {}
    evidence_roots: dict[str, dict[str, Any]] = {}
    evidence_root_bindings: dict[str, dict[str, str]] = {}
    previous_completed: datetime | None = None
    for capability in ATTEMPT_ORDER:
        result = completed_attempts[capability]
        if not isinstance(result, Mapping) or set(result) != _ATTEMPT_RESULT_FIELDS:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ATTEMPT_RESULT_INVALID:{capability}"
            )
        try:
            root = evidence_store.load_binding(
                result["evidence_root_binding"],
                verifier=evidence_store.verify_evidence_root,
            )
            reservation = evidence_store.load_attempt_reservation(capability)
        except (KeyError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            ) from exc
        if reservation is None or dict(result["evidence_root"]) != root:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            )
        started = _time(
            root["started_at"], "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
        )
        completed = _time(
            root["completed_at"], "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
        )
        _enforce_current_codex_duration(
            capability=capability, started=started, completed=completed
        )
        if (
            root.get("capability") != capability
            or root.get("qualification_run_id")
            != qualification_authority["run_id"]
            or root.get("target_run_id")
            != qualification_authority["target_run_id"]
            or root.get("qualification_authority_digest") != authority_digest
            or root.get("attempt_reservation_binding")
            != reservation["reservation_binding"]
            or result["evidence_root_binding"].get("path")
            != evidence_store.root_ref(capability)
            or root.get("attempt_count") != 1
            or root.get("retry_allowed") is not False
            or root.get("replay_network_calls") != 0
            or not authority_recorded < started <= completed
            or (previous_completed is not None and started < previous_completed)
        ):
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            )
        receipt = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id=f"actual-capability:{capability.lower()}:{qualification_id}",
            qualification_run_id=str(qualification_authority["run_id"]),
            target_run_id=str(qualification_authority["target_run_id"]),
            started_at=root["started_at"],
            completed_at=root["completed_at"],
            qualification_authority_binding=qualification_authority_binding,
            evidence_root_binding=result["evidence_root_binding"],
        )
        try:
            replay = replay_registry[capability](
                project_root=project_root,
                capability_receipt=receipt,
                evidence_root_binding=result["evidence_root_binding"],
                qualification_authority=qualification_authority,
            )
        except (TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_FULL_REPLAY_FAILED:{capability}"
            ) from exc
        root_digest = evidence_store.verify_evidence_root(root)
        if replay != {
            "capability": capability,
            "evidence_root_semantic_digest": root_digest,
            "full_replay_verified": True,
            "replay_network_calls": 0,
        }:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_FULL_REPLAY_FAILED:{capability}"
            )
        verify_v32_actual_capability_receipt_v1(receipt)
        schema_id, digest_field = ACTUAL_CAPABILITY_RECEIPT_SPECS[capability]
        receipt_binding = evidence_store.preview_typed_document_binding(
            relative_ref=evidence_store.receipt_ref(capability),
            document=receipt,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        evidence_roots[capability] = root
        evidence_root_bindings[capability] = dict(
            result["evidence_root_binding"]
        )
        actual_receipts[capability] = receipt
        actual_receipt_bindings[capability] = receipt_binding
        previous_completed = completed

    ordered_receipt_bindings = {
        capability: actual_receipt_bindings[capability]
        for capability in CAPABILITY_KEYS
    }
    qualification_receipt = build_v32_fresh_capability_qualification_receipt_v1(
        qualification_id=qualification_id,
        qualification_run_id=str(qualification_authority["run_id"]),
        target_run_id=str(qualification_authority["target_run_id"]),
        started_at=min(root["started_at"] for root in evidence_roots.values()),
        completed_at=max(
            root["completed_at"] for root in evidence_roots.values()
        ),
        qualification_authority_binding=qualification_authority_binding,
        capability_evidence_bindings=ordered_receipt_bindings,
    )
    verify_v32_fresh_capability_qualification_receipt_v1(qualification_receipt)
    qualification_receipt_binding = evidence_store.preview_typed_document_binding(
        relative_ref=evidence_store.qualification_receipt_ref,
        document=qualification_receipt,
        schema_id=QUALIFICATION_RECEIPT_SCHEMA_ID,
        digest_field=QUALIFICATION_RECEIPT_DIGEST_FIELD,
    )
    batch = [
        {
            "relative_ref": evidence_store.receipt_ref(capability),
            "document": actual_receipts[capability],
            "schema_id": ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][0],
            "digest_field": ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][1],
        }
        for capability in ATTEMPT_ORDER
    ]
    batch.append(
        {
            "relative_ref": evidence_store.qualification_receipt_ref,
            "document": qualification_receipt,
            "schema_id": QUALIFICATION_RECEIPT_SCHEMA_ID,
            "digest_field": QUALIFICATION_RECEIPT_DIGEST_FIELD,
        }
    )
    persisted_bindings = evidence_store.persist_typed_documents_atomically(batch)
    if (
        any(
            persisted_bindings.get(evidence_store.receipt_ref(capability))
            != ordered_receipt_bindings[capability]
            for capability in CAPABILITY_KEYS
        )
        or persisted_bindings.get(evidence_store.qualification_receipt_ref)
        != qualification_receipt_binding
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_BATCH_BINDING_INVALID"
        )
    return {
        "qualification_id": qualification_id,
        "qualification_run_id": qualification_authority["run_id"],
        "target_run_id": qualification_authority["target_run_id"],
        "attempt_order": list(ATTEMPT_ORDER),
        "evidence_roots": evidence_roots,
        "evidence_root_bindings": evidence_root_bindings,
        "actual_capability_receipts": actual_receipts,
        "actual_capability_receipt_bindings": ordered_receipt_bindings,
        "qualification_receipt": qualification_receipt,
        "qualification_receipt_binding": qualification_receipt_binding,
        "network_replay_calls": 0,
        "retry_allowed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def run_v32_actual_capability_qualification(
    *,
    project_root: Path,
    evidence_store: V32ActualCapabilityEvidenceStorePort,
    qualification_id: str,
    qualification_authority: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, str],
    attempt_ports: Mapping[str, V32ActualCapabilityAttemptPort],
    clock: Callable[[], str],
) -> dict[str, Any]:
    """Run exactly one attempt per capability and seal four final receipts."""

    if evidence_store.project_root != Path(project_root).resolve(strict=True):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_STORE_ROOT_INVALID"
        )
    ports = _attempt_ports(attempt_ports)
    try:
        authority_digest = verify_v32_authority_v1(qualification_authority)
        durable_authority = evidence_store.load_binding(
            qualification_authority_binding,
            verifier=verify_v32_authority_v1,
        )
    except (TypeError, ValueError) as exc:
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_AUTHORITY_INVALID"
        ) from exc
    if (
        durable_authority != dict(qualification_authority)
        or qualification_authority.get("schema_id") != AUTHORITY_SCHEMA_ID
        or qualification_authority.get("profile") != QUALIFICATION_PROFILE
        or qualification_authority.get("status") != "ACTIVE"
        or qualification_authority.get("authorized_operation")
        != "V32_ISOLATED_QUALIFICATION"
        or qualification_authority.get("run_id")
        == qualification_authority.get("target_run_id")
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_AUTHORITY_INVALID"
        )

    authority_recorded = _time(
        qualification_authority["recorded_at"],
        "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID",
    )
    replay_registry = evidence_store.full_replay_registry()
    if (
        not isinstance(replay_registry, Mapping)
        or set(replay_registry) != set(CAPABILITY_KEYS)
        or any(
            not callable(replay_registry.get(capability))
            for capability in CAPABILITY_KEYS
        )
    ):
        raise V32ActualCapabilityQualificationError(
            "V32_ACTUAL_QUALIFICATION_FULL_REPLAY_REGISTRY_INVALID"
        )
    actual_receipts: dict[str, dict[str, Any]] = {}
    actual_receipt_bindings: dict[str, dict[str, str]] = {}
    evidence_roots: dict[str, dict[str, Any]] = {}
    evidence_root_bindings: dict[str, dict[str, str]] = {}
    previous_completed: datetime | None = None

    for capability in ATTEMPT_ORDER:
        reserved_at = _clock_time(clock)
        reservation_time = _time(
            reserved_at, "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
        )
        if reservation_time <= authority_recorded or (
            previous_completed is not None and reservation_time < previous_completed
        ):
            raise V32ActualCapabilityQualificationError(
                "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
            )
        try:
            reserved = evidence_store.reserve_attempt(
                capability=capability,
                qualification_run_id=str(qualification_authority["run_id"]),
                target_run_id=str(qualification_authority["target_run_id"]),
                qualification_authority_digest=authority_digest,
                reserved_at=reserved_at,
            )
            result = ports[capability].execute_once(
                capability=capability,
                qualification_authority=qualification_authority,
                qualification_authority_binding=qualification_authority_binding,
                reservation=reserved["reservation"],
                reservation_binding=reserved["reservation_binding"],
            )
        except Exception as exc:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ATTEMPT_FAILED:{capability}"
            ) from exc
        if not isinstance(result, Mapping) or set(result) != _ATTEMPT_RESULT_FIELDS:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ATTEMPT_RESULT_INVALID:{capability}"
            )
        try:
            root = evidence_store.load_binding(
                result["evidence_root_binding"],
                verifier=evidence_store.verify_evidence_root,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            ) from exc
        if dict(result["evidence_root"]) != root:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            )
        started = _time(
            root["started_at"], "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
        )
        completed = _time(
            root["completed_at"], "V32_ACTUAL_QUALIFICATION_CHRONOLOGY_INVALID"
        )
        _enforce_current_codex_duration(
            capability=capability, started=started, completed=completed
        )
        if (
            root.get("capability") != capability
            or root.get("qualification_run_id") != qualification_authority["run_id"]
            or root.get("target_run_id") != qualification_authority["target_run_id"]
            or root.get("qualification_authority_digest") != authority_digest
            or root.get("attempt_reservation_binding")
            != reserved["reservation_binding"]
            or result["evidence_root_binding"].get("path")
            != evidence_store.root_ref(capability)
            or root.get("attempt_count") != 1
            or root.get("retry_allowed") is not False
            or root.get("replay_network_calls") != 0
            or not authority_recorded < reservation_time <= started <= completed
            or (previous_completed is not None and started < previous_completed)
        ):
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_ROOT_INVALID:{capability}"
            )
        receipt = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id=f"actual-capability:{capability.lower()}:{qualification_id}",
            qualification_run_id=str(qualification_authority["run_id"]),
            target_run_id=str(qualification_authority["target_run_id"]),
            started_at=root["started_at"],
            completed_at=root["completed_at"],
            qualification_authority_binding=qualification_authority_binding,
            evidence_root_binding=result["evidence_root_binding"],
        )
        try:
            replay = replay_registry[capability](
                project_root=project_root,
                capability_receipt=receipt,
                evidence_root_binding=result["evidence_root_binding"],
                qualification_authority=qualification_authority,
            )
        except (TypeError, ValueError) as exc:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_FULL_REPLAY_FAILED:{capability}"
            ) from exc
        root_digest = evidence_store.verify_evidence_root(root)
        if replay != {
            "capability": capability,
            "evidence_root_semantic_digest": root_digest,
            "full_replay_verified": True,
            "replay_network_calls": 0,
        }:
            raise V32ActualCapabilityQualificationError(
                f"V32_ACTUAL_QUALIFICATION_FULL_REPLAY_FAILED:{capability}"
            )
        verify_v32_actual_capability_receipt_v1(receipt)
        schema_id, digest_field = ACTUAL_CAPABILITY_RECEIPT_SPECS[capability]
        receipt_binding = evidence_store.preview_typed_document_binding(
            relative_ref=evidence_store.receipt_ref(capability),
            document=receipt,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        evidence_roots[capability] = root
        evidence_root_bindings[capability] = dict(
            result["evidence_root_binding"]
        )
        actual_receipts[capability] = receipt
        actual_receipt_bindings[capability] = receipt_binding
        previous_completed = completed

    # The early replay above stops a bad one-shot path as soon as possible, but
    # no receipt is durable yet.  The final sealer reopens and replays all three
    # roots as one set, validates all four prospective receipts, preflights all
    # final paths, and then performs the only receipt persistence boundary.
    return seal_v32_actual_capability_qualification_from_completed_attempts(
        project_root=project_root,
        evidence_store=evidence_store,
        qualification_id=qualification_id,
        qualification_authority=qualification_authority,
        qualification_authority_binding=qualification_authority_binding,
        completed_attempts={
            capability: {
                "evidence_root": evidence_roots[capability],
                "evidence_root_binding": evidence_root_bindings[capability],
            }
            for capability in CAPABILITY_KEYS
        },
    )


__all__ = [
    "ATTEMPT_ORDER",
    "V32ActualCapabilityAttemptPort",
    "V32ActualCapabilityQualificationError",
    "run_v32_actual_capability_qualification",
    "seal_v32_actual_capability_qualification_from_completed_attempts",
]
