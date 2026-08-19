"""Local one-boundary V3.2 audit lane with deterministic crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any, Callable, Mapping, Sequence

from ..application.v32_cycle_audit_completion import (
    build_v32_cycle_audit_completion_receipt_v1,
    verify_v32_cycle_audit_completion_receipt_v1,
)
from ..application.v32_deterministic_audit import (
    compose_v32_deterministic_boundary_audit_v1,
)
from ..domain.contracts.canonical import canonical_bytes
from ..domain.v32_cycle_audit_narrative import (
    BOUNDARY_TYPES,
    verify_v32_cycle_audit_policy_v1,
)
from .v32_authorized_revision_store import LocalV32AuthorizedRevisionStore
from .v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)


class V32LocalAuditLaneError(ValueError):
    """A boundary audit was missing, conflicting, or non-deterministic."""


Clock = Callable[[], str]


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32LocalAuditLaneError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32LocalAuditLaneError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32LocalAuditLaneError(code)
    return parsed.astimezone(UTC)


class LocalV32BoundaryAuditLane:
    """Persist exactly one deterministic post-boundary audit per call."""

    def __init__(
        self,
        *,
        revision_store: LocalV32AuthorizedRevisionStore,
        acceptance_completion_store: LocalV32CycleAuditCompletionStore,
        clock: Clock,
    ) -> None:
        if not isinstance(revision_store, LocalV32AuthorizedRevisionStore) or not isinstance(
            acceptance_completion_store, LocalV32CycleAuditCompletionStore
        ) or not callable(clock):
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_DEPENDENCY_INVALID")
        self._revision_store = revision_store
        self._completion_store = acceptance_completion_store
        self._clock = clock

    def _clock_time(self) -> str:
        try:
            value = self._clock()
        except Exception as exc:
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_CLOCK_FAILED") from exc
        _time(value, "V32_LOCAL_AUDIT_CLOCK_INVALID")
        return value

    @staticmethod
    def _acceptance_source(
        sealed_sources: Sequence[Mapping[str, Any]],
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        matches = [
            row
            for row in sealed_sources
            if isinstance(row, Mapping) and row.get("role") == "analysis_acceptance"
        ]
        if len(matches) != 1:
            raise V32LocalAuditLaneError(
                "V32_LOCAL_AUDIT_ACCEPTANCE_SOURCE_INVALID"
            )
        return matches[0]["document"], matches[0]["binding"]

    def advance_once(
        self,
        *,
        narrative_id: str,
        completion_id: str | None,
        run_id: str,
        cycle_index: int,
        boundary_type: str,
        boundary_sealed_at: str,
        sealed_sources: Sequence[Mapping[str, Any]],
        cycle_audit_policy: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create or replay one audit; never invoke market, Agent, or execution."""

        try:
            verify_v32_cycle_audit_policy_v1(cycle_audit_policy)
        except (TypeError, ValueError) as exc:
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_POLICY_INVALID") from exc
        if (
            boundary_type not in BOUNDARY_TYPES
            or cycle_audit_policy.get("run_scope_id") != run_id
        ):
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_SCOPE_INVALID")
        if boundary_type == "ACCEPTANCE":
            if not isinstance(completion_id, str) or not completion_id:
                raise V32LocalAuditLaneError(
                    "V32_LOCAL_AUDIT_COMPLETION_ID_REQUIRED"
                )
        elif completion_id is not None:
            raise V32LocalAuditLaneError(
                "V32_LOCAL_AUDIT_COMPLETION_ID_FORBIDDEN"
            )

        existing = self._revision_store.load_audit_bundle(
            run_id=run_id,
            cycle_index=cycle_index,
            boundary_type=boundary_type,
        )
        created = existing is None
        generated_at = (
            self._clock_time()
            if existing is None
            else str(existing["directory"]["generated_at"])
        )
        if _time(generated_at, "V32_LOCAL_AUDIT_TIME_INVALID") < _time(
            boundary_sealed_at, "V32_LOCAL_AUDIT_TIME_INVALID"
        ):
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_TIME_INVALID")
        try:
            rebuilt = compose_v32_deterministic_boundary_audit_v1(
                narrative_id=narrative_id,
                run_id=run_id,
                cycle_index=cycle_index,
                boundary_type=boundary_type,
                boundary_sealed_at=boundary_sealed_at,
                generated_at=generated_at,
                sealed_sources=sealed_sources,
                max_text_part_utf8_bytes=cycle_audit_policy[
                    "max_text_part_utf8_bytes"
                ],
                max_shard_canonical_bytes=cycle_audit_policy[
                    "max_shard_canonical_bytes"
                ],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_BUILD_INVALID") from exc
        if existing is not None and (
            existing["directory"] != rebuilt["directory"]
            or existing["shards"] != rebuilt["shards"]
        ):
            raise V32LocalAuditLaneError(
                "V32_LOCAL_AUDIT_EXISTING_REPLAY_MISMATCH"
            )
        persisted = self._revision_store.persist_audit_bundle(
            directory=rebuilt["directory"], shards=rebuilt["shards"]
        )

        completion = None
        completion_binding = None
        if boundary_type == "ACCEPTANCE":
            acceptance, acceptance_binding = self._acceptance_source(
                sealed_sources
            )
            existing_completion = self._completion_store.load_completion(
                run_id=run_id, cycle_index=cycle_index
            )
            completed_at = (
                self._clock_time()
                if existing_completion is None
                else str(existing_completion["completed_at"])
            )
            if _time(completed_at, "V32_LOCAL_AUDIT_TIME_INVALID") < _time(
                generated_at, "V32_LOCAL_AUDIT_TIME_INVALID"
            ):
                raise V32LocalAuditLaneError("V32_LOCAL_AUDIT_TIME_INVALID")
            try:
                completion = build_v32_cycle_audit_completion_receipt_v1(
                    completion_id=completion_id,
                    cycle_audit_policy=cycle_audit_policy,
                    analysis_acceptance=acceptance,
                    analysis_acceptance_binding=acceptance_binding,
                    narrative_directory=rebuilt["directory"],
                    narrative_directory_binding=persisted["directory_binding"],
                    narrative_shards=rebuilt["shards"],
                    narrative_shard_bindings=persisted["shard_bindings"],
                    completed_at=completed_at,
                )
                verify_v32_cycle_audit_completion_receipt_v1(
                    completion,
                    cycle_audit_policy=cycle_audit_policy,
                    analysis_acceptance=acceptance,
                    narrative_directory=rebuilt["directory"],
                    narrative_shards=rebuilt["shards"],
                )
            except (TypeError, ValueError) as exc:
                raise V32LocalAuditLaneError(
                    "V32_LOCAL_AUDIT_COMPLETION_INVALID"
                ) from exc
            if existing_completion is not None and existing_completion != completion:
                raise V32LocalAuditLaneError(
                    "V32_LOCAL_AUDIT_COMPLETION_REPLAY_MISMATCH"
                )
            completion_binding = self._completion_store.persist_completion(
                completion=completion,
                cycle_audit_policy=cycle_audit_policy,
                analysis_acceptance=acceptance,
                narrative_directory=rebuilt["directory"],
                narrative_shards=rebuilt["shards"],
            )
        return {
            "audit_status": "CREATED" if created else "EXISTING_VERIFIED",
            "boundary_type": boundary_type,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "directory": rebuilt["directory"],
            "directory_binding": persisted["directory_binding"],
            "shard_bindings": persisted["shard_bindings"],
            "acceptance_audit_completion": completion,
            "acceptance_audit_completion_binding": completion_binding,
            "network_request_count": 0,
            "agent_invocation_count": 0,
            "account_access": False,
            "order_submission": False,
            "executable": False,
            "result_digest": hashlib.sha256(
                canonical_bytes(
                    {
                        "directory_binding": persisted["directory_binding"],
                        "completion_binding": completion_binding,
                    }
                )
            ).hexdigest(),
        }


__all__ = ["LocalV32BoundaryAuditLane", "V32LocalAuditLaneError"]
