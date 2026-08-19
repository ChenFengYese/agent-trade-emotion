"""Minimal immutable contracts for V3.3.2 continuity checkpoints.

The contracts record controller and fact-owner heads.  They do not schedule a
cycle, choose an Agent action, or claim that a run was closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_digest


CONTINUITY_SCHEMA_ID = "agent-trade-emotion.v332-continuity-checkpoint"
CONTINUITY_SCHEMA_VERSION = "1.0.0"
CONTINUITY_RECOVERY_SCHEMA_ID = "agent-trade-emotion.v332-continuity-recovery"
CONTINUITY_RECOVERY_SCHEMA_VERSION = "1.0.0"
RECOVERY_PROBE_SCHEMA_ID = "agent-trade-emotion.v332-recovery-probe"
RECOVERY_PROBE_SCHEMA_VERSION = "1.0.0"
RECOVERY_OBSERVATION_SCHEMA_ID = "agent-trade-emotion.v332-recovery-observation"
RECOVERY_OBSERVATION_SCHEMA_VERSION = "1.0.0"
ABSOLUTE_SLOT_GAP = "ABSOLUTE_SLOT_GAP"
FINALIZATION_AWAITING_RUN_CLOSE = "CONTINUITY_FINALIZED_AWAITING_RUN_CLOSE"
RECOVERY_INJECTION_POINTS = frozenset(
    {
        "INPUT_SEALED_RESTART",
        "WORKER_PREPARED_RESTART",
        "PAPER_INTENT_RECORDED_RESTART",
        "ATTENTION_REQUEST_DURABLE_RESTART",
        "WORKER_SPAWN_REQUESTED_BEFORE_ACK_RESTART",
    }
)
RECOVERY_FORBIDDEN_DUPLICATES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "INPUT_SEALED_RESTART": ("INPUT_SNAPSHOT_ARTIFACT",),
        "WORKER_PREPARED_RESTART": ("WORKER_DISPATCH",),
        "PAPER_INTENT_RECORDED_RESTART": (
            "PAPER_INTENT_EVENT",
            "PAPER_COMMAND_EVENT",
        ),
        "ATTENTION_REQUEST_DURABLE_RESTART": (
            "ATTENTION_REQUEST_EVENT",
            "ATTENTION_DISPATCH",
        ),
        "WORKER_SPAWN_REQUESTED_BEFORE_ACK_RESTART": (
            "WORKER_SPAWN_REQUEST",
            "WORKER_EXECUTION",
        ),
    }
)
_KINDS = frozenset({"OPEN", "CHECKPOINT", "FINAL"})
_SLOT_KINDS = frozenset({"BASE", "AGENT_ATTENTION", "FINAL"})
_ATTEMPT_STATUSES = frozenset(
    {"ATTEMPTED_TERMINAL", "CAPACITY_SKIPPED", "NOT_ATTEMPTED"}
)
_DISPOSITIONS = frozenset(
    {"OPENED", "CONTINUE", "RESTART_REQUIRED", "FINALIZED"}
)
_RECOVERY_ACTIONS = frozenset(
    {"CONTINUE", "RESTART_REQUIRED", "FINALIZED"}
)
_HEAD_STATUSES = frozenset({"UNCHANGED", "MONOTONIC_PROGRESS"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}\Z")


class ContinuityContractError(ValueError):
    """One checkpoint or recovery view is malformed or self-contradictory."""


def _identifier(value: object, *, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ContinuityContractError(f"CONTINUITY_{field.upper()}_INVALID")
    return value


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ContinuityContractError(f"CONTINUITY_{field.upper()}_INVALID")
    return value


def _moment(value: object, *, field: str) -> datetime:
    if type(value) is not str or not value or len(value) > 64:
        raise ContinuityContractError(f"CONTINUITY_{field.upper()}_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuityContractError(
            f"CONTINUITY_{field.upper()}_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuityContractError(f"CONTINUITY_{field.upper()}_INVALID")
    return parsed


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def absolute_slot(starts_at: str, sampling_seconds: int, observed_at: str) -> int:
    """Return the stable epoch-relative sampling slot for one observation."""

    start = _moment(starts_at, field="starts_at")
    observed = _moment(observed_at, field="observed_at")
    if type(sampling_seconds) is not int or sampling_seconds <= 0:
        raise ContinuityContractError("CONTINUITY_SAMPLING_SECONDS_INVALID")
    delta = observed - start
    microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    if microseconds < 0:
        raise ContinuityContractError("CONTINUITY_OBSERVED_BEFORE_START")
    return microseconds // (sampling_seconds * 1_000_000)


def scheduled_at(starts_at: str, sampling_seconds: int, slot: int) -> str:
    """Return the exact scheduled instant for an absolute slot."""

    start = _moment(starts_at, field="starts_at")
    if (
        type(sampling_seconds) is not int
        or sampling_seconds <= 0
        or type(slot) is not int
        or slot < 0
    ):
        raise ContinuityContractError("CONTINUITY_ABSOLUTE_SLOT_INVALID")
    return (start + timedelta(seconds=sampling_seconds * slot)).isoformat()


@dataclass(frozen=True, slots=True)
class ContinuityCheckpointV1:
    run_id: str
    policy_sha256: str
    sequence: int
    record_kind: str
    previous_record_sha256: str | None
    absolute_slot: int
    slot_kind: str
    source_event_id: str | None
    slot_scheduled_at: str
    latest_useful_at: str | None
    attempt_status: str
    observed_at: str
    issue_code: str | None
    disposition: str
    owner_heads: Mapping[str, Any]
    finalization_status: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _identifier(self.run_id, field="run_id"))
        object.__setattr__(
            self, "policy_sha256", _sha256(self.policy_sha256, field="policy_sha256")
        )
        if type(self.sequence) is not int or self.sequence < 1:
            raise ContinuityContractError("CONTINUITY_SEQUENCE_INVALID")
        if self.record_kind not in _KINDS:
            raise ContinuityContractError("CONTINUITY_RECORD_KIND_INVALID")
        if self.sequence == 1:
            if self.previous_record_sha256 is not None:
                raise ContinuityContractError("CONTINUITY_PREVIOUS_SHA_INVALID")
        else:
            _sha256(self.previous_record_sha256, field="previous_record_sha256")
        if type(self.absolute_slot) is not int or self.absolute_slot < 0:
            raise ContinuityContractError("CONTINUITY_ABSOLUTE_SLOT_INVALID")
        if self.slot_kind not in _SLOT_KINDS:
            raise ContinuityContractError("CONTINUITY_SLOT_KIND_INVALID")
        if self.source_event_id is not None:
            _identifier(self.source_event_id, field="source_event_id")
        scheduled = _moment(self.slot_scheduled_at, field="slot_scheduled_at")
        observed = _moment(self.observed_at, field="observed_at")
        if observed < scheduled:
            raise ContinuityContractError("CONTINUITY_OBSERVED_BEFORE_SLOT")
        latest = (
            None
            if self.latest_useful_at is None
            else _moment(self.latest_useful_at, field="latest_useful_at")
        )
        if self.attempt_status not in _ATTEMPT_STATUSES:
            raise ContinuityContractError("CONTINUITY_ATTEMPT_STATUS_INVALID")
        if self.issue_code is not None:
            _identifier(self.issue_code, field="issue_code")
        if self.disposition not in _DISPOSITIONS:
            raise ContinuityContractError("CONTINUITY_DISPOSITION_INVALID")
        if not isinstance(self.owner_heads, Mapping) or not self.owner_heads:
            raise ContinuityContractError("CONTINUITY_OWNER_HEADS_INVALID")
        plain_heads = _plain(self.owner_heads)
        try:
            canonical_digest(plain_heads)
        except (TypeError, ValueError) as exc:
            raise ContinuityContractError("CONTINUITY_OWNER_HEADS_INVALID") from exc
        object.__setattr__(self, "owner_heads", _freeze(plain_heads))
        if self.record_kind == "OPEN":
            if (
                self.sequence != 1
                or self.disposition != "OPENED"
                or self.slot_kind != "BASE"
            ):
                raise ContinuityContractError("CONTINUITY_OPEN_RECORD_INVALID")
        elif self.record_kind == "FINAL":
            if (
                self.disposition != "FINALIZED"
                or self.issue_code is not None
                or self.slot_kind != "FINAL"
                or self.finalization_status != FINALIZATION_AWAITING_RUN_CLOSE
            ):
                raise ContinuityContractError("CONTINUITY_FINAL_RECORD_INVALID")
        elif self.disposition not in {"CONTINUE", "RESTART_REQUIRED"}:
            raise ContinuityContractError("CONTINUITY_CHECKPOINT_DISPOSITION_INVALID")
        if self.record_kind != "FINAL" and self.finalization_status is not None:
            raise ContinuityContractError("CONTINUITY_FINALIZATION_STATUS_INVALID")
        if self.slot_kind == "AGENT_ATTENTION":
            if (
                self.record_kind != "CHECKPOINT"
                or self.source_event_id is None
                or latest is None
                or latest < scheduled
            ):
                raise ContinuityContractError("CONTINUITY_ATTENTION_SLOT_INVALID")
        elif (
            self.source_event_id is not None
            or latest is not None
            or self.attempt_status != "NOT_ATTEMPTED"
        ):
            raise ContinuityContractError("CONTINUITY_NON_ATTENTION_SLOT_INVALID")
        if (self.disposition == "RESTART_REQUIRED") != (self.issue_code is not None):
            # Continuable issues remain visible but have CONTINUE disposition.
            if self.disposition == "RESTART_REQUIRED" or self.issue_code is None:
                raise ContinuityContractError("CONTINUITY_ISSUE_DISPOSITION_INVALID")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_id": CONTINUITY_SCHEMA_ID,
            "schema_version": CONTINUITY_SCHEMA_VERSION,
            "run_id": self.run_id,
            "policy_sha256": self.policy_sha256,
            "sequence": self.sequence,
            "record_kind": self.record_kind,
            "previous_record_sha256": self.previous_record_sha256,
            "absolute_slot": self.absolute_slot,
            "slot_kind": self.slot_kind,
            "source_event_id": self.source_event_id,
            "slot_scheduled_at": self.slot_scheduled_at,
            "latest_useful_at": self.latest_useful_at,
            "attempt_status": self.attempt_status,
            "observed_at": self.observed_at,
            "issue_code": self.issue_code,
            "disposition": self.disposition,
            "owner_heads": _plain(self.owner_heads),
            "finalization_status": self.finalization_status,
        }

    @property
    def record_sha256(self) -> str:
        return canonical_digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "record_sha256": self.record_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContinuityCheckpointV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "run_id",
                "policy_sha256",
                "sequence",
                "record_kind",
                "previous_record_sha256",
                "absolute_slot",
                "slot_kind",
                "source_event_id",
                "slot_scheduled_at",
                "latest_useful_at",
                "attempt_status",
                "observed_at",
                "issue_code",
                "disposition",
                "owner_heads",
                "finalization_status",
                "record_sha256",
            }
        )
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != fields
            or value.get("schema_id") != CONTINUITY_SCHEMA_ID
            or value.get("schema_version") != CONTINUITY_SCHEMA_VERSION
        ):
            raise ContinuityContractError("CONTINUITY_RECORD_FIELDS_INVALID")
        record = cls(
            **{
                key: value[key]
                for key in fields
                - {"schema_id", "schema_version", "record_sha256"}
            }
        )
        if value["record_sha256"] != record.record_sha256:
            raise ContinuityContractError("CONTINUITY_RECORD_SHA256_INVALID")
        return record


@dataclass(frozen=True, slots=True)
class ContinuityRecoveryV1:
    run_id: str
    policy_sha256: str
    recovered_at: str
    last_sequence: int
    last_record_sha256: str
    current_absolute_slot: int
    action: str
    owner_head_status: str
    issue_code: str | None

    def __post_init__(self) -> None:
        _identifier(self.run_id, field="run_id")
        _sha256(self.policy_sha256, field="policy_sha256")
        _moment(self.recovered_at, field="recovered_at")
        if type(self.last_sequence) is not int or self.last_sequence < 1:
            raise ContinuityContractError("CONTINUITY_RECOVERY_SEQUENCE_INVALID")
        _sha256(self.last_record_sha256, field="last_record_sha256")
        if type(self.current_absolute_slot) is not int or self.current_absolute_slot < 0:
            raise ContinuityContractError("CONTINUITY_RECOVERY_SLOT_INVALID")
        if self.action not in _RECOVERY_ACTIONS:
            raise ContinuityContractError("CONTINUITY_RECOVERY_ACTION_INVALID")
        if self.owner_head_status not in _HEAD_STATUSES:
            raise ContinuityContractError("CONTINUITY_RECOVERY_HEAD_STATUS_INVALID")
        if self.issue_code is not None:
            _identifier(self.issue_code, field="issue_code")
        if (self.action == "RESTART_REQUIRED") != (self.issue_code is not None):
            raise ContinuityContractError("CONTINUITY_RECOVERY_ISSUE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": CONTINUITY_RECOVERY_SCHEMA_ID,
            "schema_version": CONTINUITY_RECOVERY_SCHEMA_VERSION,
            "run_id": self.run_id,
            "policy_sha256": self.policy_sha256,
            "recovered_at": self.recovered_at,
            "last_sequence": self.last_sequence,
            "last_record_sha256": self.last_record_sha256,
            "current_absolute_slot": self.current_absolute_slot,
            "action": self.action,
            "owner_head_status": self.owner_head_status,
            "issue_code": self.issue_code,
        }


@dataclass(frozen=True, slots=True)
class RecoveryProbeV1:
    """Create-once, pre-restart declaration of one safe local fault probe."""

    probe_id: str
    run_id: str
    policy_sha256: str
    run_identity_sha256: str
    injection_point: str
    expected_owner_heads: Mapping[str, Any]
    forbidden_duplicates: tuple[str, ...]
    created_at: str
    created_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", _identifier(self.probe_id, field="probe_id"))
        object.__setattr__(self, "run_id", _identifier(self.run_id, field="run_id"))
        _sha256(self.policy_sha256, field="policy_sha256")
        _sha256(self.run_identity_sha256, field="run_identity_sha256")
        if self.injection_point not in RECOVERY_INJECTION_POINTS:
            raise ContinuityContractError("CONTINUITY_RECOVERY_INJECTION_POINT_INVALID")
        if (
            not isinstance(self.expected_owner_heads, Mapping)
            or not self.expected_owner_heads
        ):
            raise ContinuityContractError("CONTINUITY_RECOVERY_OWNER_HEADS_INVALID")
        plain_heads = _plain(self.expected_owner_heads)
        try:
            canonical_digest(plain_heads)
        except (TypeError, ValueError) as exc:
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_OWNER_HEADS_INVALID"
            ) from exc
        object.__setattr__(self, "expected_owner_heads", _freeze(plain_heads))
        forbidden = tuple(self.forbidden_duplicates)
        if forbidden != RECOVERY_FORBIDDEN_DUPLICATES[self.injection_point]:
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_FORBIDDEN_DUPLICATES_INVALID"
            )
        object.__setattr__(self, "forbidden_duplicates", forbidden)
        _moment(self.created_at, field="created_at")
        if self.created_by != "TRUSTED_CONTINUITY_CLOCK":
            raise ContinuityContractError("CONTINUITY_RECOVERY_CREATED_BY_INVALID")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_id": RECOVERY_PROBE_SCHEMA_ID,
            "schema_version": RECOVERY_PROBE_SCHEMA_VERSION,
            "probe_id": self.probe_id,
            "run_id": self.run_id,
            "policy_sha256": self.policy_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "injection_point": self.injection_point,
            "expected_owner_heads": _plain(self.expected_owner_heads),
            "forbidden_duplicates": list(self.forbidden_duplicates),
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @property
    def probe_sha256(self) -> str:
        return canonical_digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "probe_sha256": self.probe_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RecoveryProbeV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "probe_id",
                "run_id",
                "policy_sha256",
                "run_identity_sha256",
                "injection_point",
                "expected_owner_heads",
                "forbidden_duplicates",
                "created_at",
                "created_by",
                "probe_sha256",
            }
        )
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != fields
            or value.get("schema_id") != RECOVERY_PROBE_SCHEMA_ID
            or value.get("schema_version") != RECOVERY_PROBE_SCHEMA_VERSION
        ):
            raise ContinuityContractError("CONTINUITY_RECOVERY_PROBE_FIELDS_INVALID")
        probe = cls(
            probe_id=value["probe_id"],
            run_id=value["run_id"],
            policy_sha256=value["policy_sha256"],
            run_identity_sha256=value["run_identity_sha256"],
            injection_point=value["injection_point"],
            expected_owner_heads=value["expected_owner_heads"],
            forbidden_duplicates=tuple(value["forbidden_duplicates"]),
            created_at=value["created_at"],
            created_by=value["created_by"],
        )
        if value["probe_sha256"] != probe.probe_sha256:
            raise ContinuityContractError("CONTINUITY_RECOVERY_PROBE_SHA256_INVALID")
        return probe


@dataclass(frozen=True, slots=True)
class RecoveryObservationV1:
    """Create-once result derived from a probe and freshly replayed owners."""

    probe_id: str
    probe_sha256: str
    run_id: str
    policy_sha256: str
    observed_at: str
    observed_owner_heads: Mapping[str, Any]
    replay_status: str
    duplicate_status: str
    action: str
    reason_code: str

    def __post_init__(self) -> None:
        _identifier(self.probe_id, field="probe_id")
        _sha256(self.probe_sha256, field="probe_sha256")
        _identifier(self.run_id, field="run_id")
        _sha256(self.policy_sha256, field="policy_sha256")
        _moment(self.observed_at, field="observed_at")
        if not isinstance(self.observed_owner_heads, Mapping):
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_OBSERVED_HEADS_INVALID"
            )
        plain_heads = _plain(self.observed_owner_heads)
        try:
            canonical_digest(plain_heads)
        except (TypeError, ValueError) as exc:
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_OBSERVED_HEADS_INVALID"
            ) from exc
        object.__setattr__(self, "observed_owner_heads", _freeze(plain_heads))
        if self.replay_status not in {"IDENTICAL", "OWNER_HEAD_DRIFT", "UNRESOLVED"}:
            raise ContinuityContractError("CONTINUITY_RECOVERY_REPLAY_STATUS_INVALID")
        if self.duplicate_status not in {
            "NONE_OBSERVED",
            "DUPLICATE_OR_DRIFT",
            "UNRESOLVED",
        }:
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_DUPLICATE_STATUS_INVALID"
            )
        if self.action not in {"CONTINUE", "RESTART_REQUIRED"}:
            raise ContinuityContractError("CONTINUITY_RECOVERY_PROBE_ACTION_INVALID")
        _identifier(self.reason_code, field="reason_code")
        if self.action == "CONTINUE":
            if (
                self.replay_status != "IDENTICAL"
                or self.duplicate_status != "NONE_OBSERVED"
                or self.reason_code != "SAFE_LOCAL_REPLAY_IDENTICAL"
            ):
                raise ContinuityContractError(
                    "CONTINUITY_RECOVERY_CONTINUE_EVIDENCE_INVALID"
                )
        elif self.reason_code == "SAFE_LOCAL_REPLAY_IDENTICAL":
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_RESTART_REASON_INVALID"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_id": RECOVERY_OBSERVATION_SCHEMA_ID,
            "schema_version": RECOVERY_OBSERVATION_SCHEMA_VERSION,
            "probe_id": self.probe_id,
            "probe_sha256": self.probe_sha256,
            "run_id": self.run_id,
            "policy_sha256": self.policy_sha256,
            "observed_at": self.observed_at,
            "observed_owner_heads": _plain(self.observed_owner_heads),
            "replay_status": self.replay_status,
            "duplicate_status": self.duplicate_status,
            "action": self.action,
            "reason_code": self.reason_code,
        }

    @property
    def observation_sha256(self) -> str:
        return canonical_digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.body_dict(),
            "observation_sha256": self.observation_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RecoveryObservationV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "probe_id",
                "probe_sha256",
                "run_id",
                "policy_sha256",
                "observed_at",
                "observed_owner_heads",
                "replay_status",
                "duplicate_status",
                "action",
                "reason_code",
                "observation_sha256",
            }
        )
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != fields
            or value.get("schema_id") != RECOVERY_OBSERVATION_SCHEMA_ID
            or value.get("schema_version") != RECOVERY_OBSERVATION_SCHEMA_VERSION
        ):
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_OBSERVATION_FIELDS_INVALID"
            )
        observation = cls(
            **{
                key: value[key]
                for key in fields
                - {"schema_id", "schema_version", "observation_sha256"}
            }
        )
        if value["observation_sha256"] != observation.observation_sha256:
            raise ContinuityContractError(
                "CONTINUITY_RECOVERY_OBSERVATION_SHA256_INVALID"
            )
        return observation


__all__ = [
    "ABSOLUTE_SLOT_GAP",
    "CONTINUITY_RECOVERY_SCHEMA_ID",
    "CONTINUITY_RECOVERY_SCHEMA_VERSION",
    "CONTINUITY_SCHEMA_ID",
    "CONTINUITY_SCHEMA_VERSION",
    "ContinuityCheckpointV1",
    "ContinuityContractError",
    "ContinuityRecoveryV1",
    "FINALIZATION_AWAITING_RUN_CLOSE",
    "RECOVERY_FORBIDDEN_DUPLICATES",
    "RECOVERY_INJECTION_POINTS",
    "RECOVERY_OBSERVATION_SCHEMA_ID",
    "RECOVERY_OBSERVATION_SCHEMA_VERSION",
    "RECOVERY_PROBE_SCHEMA_ID",
    "RECOVERY_PROBE_SCHEMA_VERSION",
    "RecoveryObservationV1",
    "RecoveryProbeV1",
    "absolute_slot",
    "scheduled_at",
]
