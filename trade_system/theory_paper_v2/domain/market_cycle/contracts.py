"""Immutable contracts for the minimal Agent-first market cycle.

The five business artifact types are deliberately small and content-addressed
by the infrastructure repository.  ``RunState`` is only an Application-owned
projection over their references; it is not a sixth business artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from ..contracts.canonical import canonical_decimal
from .theory import (
    CURRENT_THEORY_IDENTITY,
    TheoryIdentity,
    V332_THEORY_IDENTITY,
    require_supported_theory_identity,
)


class MarketCycleContractError(ValueError):
    """A value violates a frozen market-cycle contract."""


BUSINESS_ARTIFACT_TYPES = (
    "InputSnapshot",
    "HypothesisRecord",
    "BehaviorPlan",
    "Outcome",
    "Review",
)

LAWFUL_REFERENCE_ACTIONS = (
    "LONG_REFERENCE",
    "SHORT_REFERENCE",
    "WATCH_REFERENCE",
    "WAIT",
    "CONDITIONAL_TRIGGER",
    "PROBE_REFERENCE",
    "OPEN_REFERENCE",
    "HOLD_REFERENCE",
    "ADD_REFERENCE",
    "REDUCE_REFERENCE",
    "HARVEST_REFERENCE",
    "CLOSE_REFERENCE",
    "HEDGE_REFERENCE",
    "REVERSE_AS_TWO_EPISODES",
    "REENTER_AS_NEW_EPISODE",
    "OTHER_INFORMATION_ACTION",
)
MARKET_DATA_PROFILES = frozenset(
    {
        "BASELINE_PRICE",
        "BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
    }
)
RUN_STATE_LOGICAL_OWNER = "Application.CycleService"
RUN_STATE_PHYSICAL_WRITER = "Infrastructure.CycleRepository"

RUN_STAGES = (
    "REQUESTED",
    "INPUT_SEALED",
    "ANALYZED",
    "PLAN_SEALED",
    "OUTCOME_DUE",
    "OUTCOME_SEALED",
    "REVIEWED",
    "COMPLETE",
)
RUN_FAILURE_STAGES = frozenset(
    {
        "REJECTED_SCOPE",
        "INPUT_UNAVAILABLE",
        "INPUT_INVALID",
        "ANALYSIS_FAILED",
        "PLAN_INVALID",
        "OUTCOME_INVALID",
        "REVIEW_FAILED",
    }
)
RUN_TERMINAL_STAGES = RUN_FAILURE_STAGES | {"COMPLETE"}
RUN_NEXT_ACTION = {
    "REQUESTED": "CAPTURE_INPUT",
    "INPUT_SEALED": "ANALYZE",
    "ANALYZED": "COPY_AGENT_DECISION_TO_PLAN",
    "PLAN_SEALED": "WAIT_FOR_OUTCOME",
    "OUTCOME_DUE": "CAPTURE_OUTCOME",
    "OUTCOME_SEALED": "REVIEW",
    "REVIEWED": "COMPLETE",
    "COMPLETE": None,
}
ALLOWED_RUN_STATE_TRANSITIONS = {
    "REQUESTED": frozenset({"INPUT_SEALED"}) | RUN_FAILURE_STAGES,
    "INPUT_SEALED": frozenset({"ANALYZED"}) | RUN_FAILURE_STAGES,
    "ANALYZED": frozenset({"PLAN_SEALED"}) | RUN_FAILURE_STAGES,
    "PLAN_SEALED": frozenset({"OUTCOME_DUE"}) | RUN_FAILURE_STAGES,
    "OUTCOME_DUE": frozenset({"OUTCOME_SEALED"}) | RUN_FAILURE_STAGES,
    "OUTCOME_SEALED": frozenset({"REVIEWED"}) | RUN_FAILURE_STAGES,
    "REVIEWED": frozenset({"COMPLETE"}) | RUN_FAILURE_STAGES,
    "COMPLETE": frozenset(),
}

_EXPECTED_ARTIFACTS_BY_STAGE = {
    "REQUESTED": (),
    "INPUT_SEALED": ("InputSnapshot",),
    "ANALYZED": ("InputSnapshot", "HypothesisRecord"),
    "PLAN_SEALED": ("InputSnapshot", "HypothesisRecord", "BehaviorPlan"),
    "OUTCOME_DUE": ("InputSnapshot", "HypothesisRecord", "BehaviorPlan"),
    "OUTCOME_SEALED": (
        "InputSnapshot",
        "HypothesisRecord",
        "BehaviorPlan",
        "Outcome",
    ),
    "REVIEWED": BUSINESS_ARTIFACT_TYPES,
    "COMPLETE": BUSINESS_ARTIFACT_TYPES,
}

_PROHIBITED_ANALYTIC_FIELDS = frozenset(
    {
        "probability",
        "probabilities",
        "probability_pct",
        "expected_value",
        "ev",
        "win_probability",
        "win_rate",
        "entropy",
        "margin",
        "sum_to_100",
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
AGENT_DECISION_MAX_UTF8_BYTES = 256 * 1024
AGENT_OUTPUT_INCOMPLETE = "AGENT_OUTPUT_INCOMPLETE"
AGENT_PROJECTION_STATUSES = frozenset({"AVAILABLE", "UNKNOWN"})
MEMORY_ITEM_MAX_UTF8_BYTES = 512 * 1024
MEMORY_CONTEXT_MAX_UTF8_BYTES = 2 * 1024 * 1024
MEMORY_ITEM_KINDS = (
    "RECENT_FULL_DAILY",
    "RELATED_DECISION_REVIEW",
    "DERIVED_OLDER_SUMMARY",
)
MEMORY_ITEM_STATUSES = frozenset({"AVAILABLE", "UNKNOWN"})
MEMORY_AVAILABILITY_BASES = frozenset({"SEALED_AT", "REVIEWED_AT"})
MEMORY_ITEM_LIMITS = MappingProxyType(
    {
        "RECENT_FULL_DAILY": 2,
        "RELATED_DECISION_REVIEW": 8,
        "DERIVED_OLDER_SUMMARY": 1,
    }
)
_REVIEW_SYSTEM_FACT_FIELDS = frozenset(
    {
        "outcome_status",
        "typed_missing",
        "endpoint_observation",
        "path_observations",
        "outcome_raw_refs",
    }
)
_V332_ORDERED_PATH_SCHEMA_ID = (
    "agent_trade_emotion_v332_ordered_outcome_path"
)


def _ordered_path_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MarketCycleContractError(f"{field_name} must be a canonical decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise MarketCycleContractError(
            f"{field_name} must be a canonical decimal"
        ) from exc
    if (
        not parsed.is_finite()
        or parsed <= 0
        or canonical_decimal(parsed) != value
    ):
        raise MarketCycleContractError(f"{field_name} must be a canonical decimal")
    return parsed


def _validate_v332_ordered_path(
    value: Mapping[str, Any],
    *,
    due_at: datetime,
    observed_at: datetime,
    raw_hashes: frozenset[str],
    required: bool,
) -> None:
    if value.get("schema_id") != _V332_ORDERED_PATH_SCHEMA_ID:
        if required:
            raise MarketCycleContractError(
                "V3.3.2 Outcome requires the ordered path contract"
            )
        return
    expected_fields = frozenset(
        {
            "schema_id",
            "schema_version",
            "status",
            "path_start_at",
            "path_end_at",
            "interval",
            "intrabar_order",
            "points",
            "coverage",
            "missing_reason",
            "source_health",
        }
    )
    if frozenset(value) != expected_fields:
        raise MarketCycleContractError("ordered Outcome path fields mismatch")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("status") not in {"ORDERED", "PARTIAL", "CENSORED"}
        or value.get("interval") != "15m"
        or value.get("intrabar_order") != "UNRESOLVED_WITHIN_BAR"
    ):
        raise MarketCycleContractError("ordered Outcome path contract is invalid")
    start = _parse_timestamp(
        value.get("path_start_at"), field_name="path_observations.path_start_at"
    )
    end = _parse_timestamp(
        value.get("path_end_at"), field_name="path_observations.path_end_at"
    )
    if start >= end or end != due_at:
        raise MarketCycleContractError("ordered Outcome path window is invalid")
    points = value.get("points")
    coverage = value.get("coverage")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
        raise MarketCycleContractError("ordered Outcome path points are invalid")
    if not isinstance(coverage, Mapping) or frozenset(coverage) != frozenset(
        {
            "expected_point_count",
            "observed_point_count",
            "gap_count",
            "covers_all_closed_intervals",
        }
    ):
        raise MarketCycleContractError("ordered Outcome path coverage is invalid")
    interval = timedelta(minutes=15)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    start_since_epoch = start_utc - epoch
    first_open = epoch + (
        (start_since_epoch + interval - timedelta(microseconds=1)) // interval
    ) * interval
    expected_opened: tuple[datetime, ...] = tuple(
        first_open + index * interval
        for index in range(max(0, (end_utc - first_open) // interval))
    )
    expected_opened_set = frozenset(expected_opened)
    observed_opened: list[datetime] = []
    previous: datetime | None = None
    for index, point in enumerate(points):
        if not isinstance(point, Mapping) or frozenset(point) != frozenset(
            {
                "sequence_index",
                "opened_at",
                "closed_at",
                "open",
                "high",
                "low",
                "close",
                "confirmed_closed",
                "available_at",
                "raw_sha256",
            }
        ):
            raise MarketCycleContractError("ordered Outcome path point is invalid")
        opened = _parse_timestamp(
            point.get("opened_at"), field_name="path_observations.points.opened_at"
        )
        closed = _parse_timestamp(
            point.get("closed_at"), field_name="path_observations.points.closed_at"
        )
        available = _parse_timestamp(
            point.get("available_at"),
            field_name="path_observations.points.available_at",
        )
        if (
            point.get("sequence_index") != index
            or point.get("confirmed_closed") is not True
            or opened.utcoffset() != timedelta(0)
            or closed.utcoffset() != timedelta(0)
            or (opened - epoch) % interval != timedelta(0)
            or closed - opened != interval
            or opened not in expected_opened_set
            or not start <= opened < closed <= end
            or available < closed
            or available > observed_at
            or (previous is not None and opened <= previous)
        ):
            raise MarketCycleContractError("ordered Outcome path chronology is invalid")
        open_price = _ordered_path_decimal(
            point.get("open"), field_name="path_observations.points.open"
        )
        high = _ordered_path_decimal(
            point.get("high"), field_name="path_observations.points.high"
        )
        low = _ordered_path_decimal(
            point.get("low"), field_name="path_observations.points.low"
        )
        close_price = _ordered_path_decimal(
            point.get("close"), field_name="path_observations.points.close"
        )
        if high < max(open_price, close_price) or low > min(open_price, close_price):
            raise MarketCycleContractError("ordered Outcome path geometry is invalid")
        raw_sha = _require_sha256(
            point.get("raw_sha256"),
            field_name="path_observations.points.raw_sha256",
        )
        if raw_sha not in raw_hashes:
            raise MarketCycleContractError("ordered Outcome path raw digest is not sealed")
        observed_opened.append(opened)
        previous = opened
    expected_count = len(expected_opened)
    observed_count = len(points)
    gap_count = expected_count - observed_count
    covers = (
        expected_count > 0
        and tuple(observed_opened) == expected_opened
    )
    if (
        coverage.get("expected_point_count") != expected_count
        or coverage.get("observed_point_count") != observed_count
        or coverage.get("gap_count") != gap_count
        or coverage.get("covers_all_closed_intervals") is not covers
    ):
        raise MarketCycleContractError("ordered Outcome path coverage does not match points")
    missing_reason = value.get("missing_reason")
    if value.get("status") == "ORDERED":
        if not covers or missing_reason is not None:
            raise MarketCycleContractError("ORDERED Outcome path is incomplete")
    else:
        if not isinstance(missing_reason, str) or not missing_reason:
            raise MarketCycleContractError("incomplete Outcome path requires a reason")
        if value.get("status") == "CENSORED" and observed_count != 0:
            raise MarketCycleContractError("CENSORED Outcome path cannot contain points")
        if value.get("status") == "PARTIAL" and (
            observed_count == 0 or covers
        ):
            raise MarketCycleContractError("PARTIAL Outcome path must be incomplete")


def _parse_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise MarketCycleContractError(f"{field_name} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketCycleContractError(f"{field_name} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketCycleContractError(f"{field_name} must include an explicit UTC offset")
    return parsed


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketCycleContractError(f"{field_name} must be a non-empty string")
    return value


def _require_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise MarketCycleContractError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _require_cycle_relative_path(value: object, *, field_name: str) -> str:
    path = _require_nonempty_string(value, field_name=field_name)
    path_parts = path.split("/")
    if (
        path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path_parts)
    ):
        raise MarketCycleContractError(
            f"{field_name} must be a canonical cycle-relative path"
        )
    return path


def _require_provenance_path(value: object, *, field_name: str) -> str:
    """Validate a stable source path without requiring cycle relativity."""

    path = _require_nonempty_string(value, field_name=field_name)
    if path != path.strip() or "\x00" in path or "\\" in path:
        raise MarketCycleContractError(
            f"{field_name} must be a canonical POSIX source path"
        )
    candidate = path[1:] if path.startswith("/") else path
    parts = candidate.split("/")
    if not candidate or any(part in {"", ".", ".."} for part in parts):
        raise MarketCycleContractError(
            f"{field_name} must be a canonical POSIX source path"
        )
    return path


def _memory_text_bytes(value: object, *, field_name: str) -> bytes:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise MarketCycleContractError(
            f"{field_name} must be readable non-empty UTF-8 text"
        )
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise MarketCycleContractError(
            f"{field_name} must be strict UTF-8 text"
        ) from exc
    if len(raw) > MEMORY_ITEM_MAX_UTF8_BYTES:
        raise MarketCycleContractError(
            f"{field_name} exceeds {MEMORY_ITEM_MAX_UTF8_BYTES} UTF-8 bytes"
        )
    return raw


def _agent_text_bytes(
    value: object,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> bytes:
    if not isinstance(value, str):
        raise MarketCycleContractError(f"{field_name} must be UTF-8 text")
    if not allow_empty and not value.strip():
        raise MarketCycleContractError(f"{field_name} must be readable non-empty text")
    if "\x00" in value:
        raise MarketCycleContractError(f"{field_name} must not contain NUL")
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise MarketCycleContractError(f"{field_name} must be strict UTF-8 text") from exc
    if len(raw) > AGENT_DECISION_MAX_UTF8_BYTES:
        raise MarketCycleContractError(
            f"{field_name} exceeds {AGENT_DECISION_MAX_UTF8_BYTES} UTF-8 bytes"
        )
    return raw


def _optional_agent_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    _agent_text_bytes(value, field_name=field_name)
    return value


def _validate_agent_projection(
    *,
    decision_text: str,
    projection_status: object,
    projection_reason: object,
    hypothesis_index: Iterable[object],
    agent_action_text: object,
    agent_position_text: object,
) -> tuple[str, str | None, tuple[str, ...], str | None, str | None]:
    if (
        type(projection_status) is not str
        or projection_status not in AGENT_PROJECTION_STATUSES
    ):
        raise MarketCycleContractError("projection_status must be AVAILABLE or UNKNOWN")
    if not isinstance(hypothesis_index, (list, tuple)):
        raise MarketCycleContractError("hypothesis_index must be an array of text spans")
    index = _freeze_strings(
        hypothesis_index,
        field_name="hypothesis_index",
        unique=False,
    )
    action_text = _optional_agent_text(
        agent_action_text, field_name="agent_action_text"
    )
    position_text = _optional_agent_text(
        agent_position_text, field_name="agent_position_text"
    )
    for field_name, value in (
        ("agent_action_text", action_text),
        ("agent_position_text", position_text),
    ):
        if value is not None and value not in decision_text:
            raise MarketCycleContractError(
                f"{field_name} must be an exact span of agent_decision_text"
            )
    if projection_status == "AVAILABLE":
        if projection_reason is not None:
            raise MarketCycleContractError(
                "AVAILABLE projection must not contain projection_reason"
            )
        if not index or action_text is None or position_text is None:
            raise MarketCycleContractError(
                "AVAILABLE projection requires hypothesis, action and position hints"
            )
        reason = None
    else:
        if projection_reason != AGENT_OUTPUT_INCOMPLETE:
            raise MarketCycleContractError(
                "UNKNOWN projection requires AGENT_OUTPUT_INCOMPLETE"
            )
        reason = AGENT_OUTPUT_INCOMPLETE
    return projection_status, reason, index, action_text, position_text


def _require_int(value: object, *, field_name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise MarketCycleContractError(f"{field_name} must be an integer >= {minimum}")
    return value


def _field_name_is_prohibited(field_name: str) -> bool:
    normalized = field_name.strip().lower().replace("-", "_")
    return (
        normalized in _PROHIBITED_ANALYTIC_FIELDS
        or normalized.endswith("_probability")
        or normalized.endswith("_probability_pct")
        or normalized.endswith("_expected_value")
    )


def _freeze_json(value: Any, *, path: str) -> Any:
    """Deep-freeze a JSON-like value while rejecting floats and pseudo-precision."""

    if isinstance(value, float):
        raise MarketCycleContractError(
            f"{path} contains float; use an exact integer or decimal string"
        )
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return value
    if isinstance(value, Mapping):
        keys = tuple(value)
        if any(not isinstance(key, str) or not key for key in keys):
            raise MarketCycleContractError(f"{path} object keys must be non-empty strings")
        frozen: dict[str, Any] = {}
        for key in sorted(keys):
            if _field_name_is_prohibited(key):
                raise MarketCycleContractError(f"{path}.{key} is a prohibited probability/EV field")
            frozen[key] = _freeze_json(value[key], path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise MarketCycleContractError(
        f"{path} contains unsupported type {type(value).__name__}; use JSON primitives"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _freeze_strings(
    values: Iterable[object],
    *,
    field_name: str,
    allow_empty: bool = True,
    unique: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MarketCycleContractError(f"{field_name} must be a sequence, not a string")
    result = tuple(
        _require_nonempty_string(value, field_name=f"{field_name}[{index}]")
        for index, value in enumerate(values)
    )
    if not allow_empty and not result:
        raise MarketCycleContractError(f"{field_name} must not be empty")
    if unique and len(result) != len(set(result)):
        raise MarketCycleContractError(f"{field_name} must not contain duplicates")
    return result


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    context: str,
) -> None:
    if not isinstance(value, Mapping):
        raise MarketCycleContractError(f"{context} must be an object")
    actual = frozenset(value)
    missing = required - actual
    extra = actual - required - optional
    if missing or extra:
        raise MarketCycleContractError(
            f"{context} fields mismatch: missing={sorted(missing)!r}, extra={sorted(extra)!r}"
        )


def _theory_to_dict(identity: TheoryIdentity) -> dict[str, object]:
    return identity.to_dict()


def _theory_from_dict(value: object) -> TheoryIdentity:
    if not isinstance(value, Mapping):
        raise MarketCycleContractError("theory_identity must be an object")
    try:
        identity = TheoryIdentity.from_dict(value)
        return require_supported_theory_identity(identity)
    except ValueError as exc:
        raise MarketCycleContractError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_type: str
    artifact_id: str
    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.artifact_type, field_name="artifact_type")
        _require_nonempty_string(self.artifact_id, field_name="artifact_id")
        path = _require_nonempty_string(self.path, field_name="path")
        path_parts = path.split("/")
        if (
            path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path_parts)
        ):
            raise MarketCycleContractError(
                "ArtifactRef.path must be a canonical cycle-relative path"
            )
        _require_int(self.size_bytes, field_name="size_bytes", minimum=1)
        _require_sha256(self.sha256, field_name="sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactRef":
        _require_exact_keys(
            value,
            required=frozenset(
                {"artifact_type", "artifact_id", "path", "size_bytes", "sha256"}
            ),
            context="ArtifactRef",
        )
        return cls(
            artifact_type=value["artifact_type"],
            artifact_id=value["artifact_id"],
            path=value["path"],
            size_bytes=value["size_bytes"],
            sha256=value["sha256"],
        )


@dataclass(frozen=True, slots=True)
class VerifiedMemoryItem:
    """One runtime-verified, non-authoritative memory source.

    ``source_sha256`` binds the exact UTF-8 bytes forwarded to the Agent.  A
    controller may provide an explicit ``UNKNOWN`` source record, but absence
    of every item is represented by the packet memory-context status instead
    of manufacturing a source.
    """

    kind: str
    status: str
    source_path: str
    source_sha256: str
    source_cycle_id: str
    venue_id: str
    instrument_id: str
    contract_identity: str
    availability_basis: str
    source_available_at: str
    verbatim_text: str

    def __post_init__(self) -> None:
        if self.kind not in MEMORY_ITEM_KINDS:
            raise MarketCycleContractError("unsupported memory item kind")
        if self.status not in MEMORY_ITEM_STATUSES:
            raise MarketCycleContractError(
                "memory item status must be AVAILABLE or UNKNOWN"
            )
        path = _require_provenance_path(
            self.source_path, field_name="memory.source_path"
        )
        digest = _require_sha256(
            self.source_sha256, field_name="memory.source_sha256"
        )
        for field_name in (
            "source_cycle_id",
            "venue_id",
            "instrument_id",
            "contract_identity",
        ):
            _require_nonempty_string(
                getattr(self, field_name), field_name=f"memory.{field_name}"
            )
        if self.availability_basis not in MEMORY_AVAILABILITY_BASES:
            raise MarketCycleContractError(
                "memory.availability_basis must be SEALED_AT or REVIEWED_AT"
            )
        _parse_timestamp(
            self.source_available_at, field_name="memory.source_available_at"
        )
        raw = _memory_text_bytes(
            self.verbatim_text, field_name="memory.verbatim_text"
        )
        if hashlib.sha256(raw).hexdigest() != digest:
            raise MarketCycleContractError(
                "memory.source_sha256 does not match verbatim UTF-8 bytes"
            )
        object.__setattr__(self, "source_path", path)

    @property
    def size_bytes(self) -> int:
        return len(self.verbatim_text.encode("utf-8", errors="strict"))

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "status": self.status,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "size_bytes": self.size_bytes,
            "source_cycle_id": self.source_cycle_id,
            "venue_id": self.venue_id,
            "instrument_id": self.instrument_id,
            "contract_identity": self.contract_identity,
            "availability_basis": self.availability_basis,
            "source_available_at": self.source_available_at,
            "verbatim_text": self.verbatim_text,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VerifiedMemoryItem":
        _require_exact_keys(
            value,
            required=frozenset(
                {
                    "kind",
                    "status",
                    "source_path",
                    "source_sha256",
                    "source_cycle_id",
                    "venue_id",
                    "instrument_id",
                    "contract_identity",
                    "availability_basis",
                    "source_available_at",
                    "verbatim_text",
                }
            ),
            optional=frozenset({"size_bytes"}),
            context="VerifiedMemoryItem",
        )
        item = cls(
            kind=value["kind"],
            status=value["status"],
            source_path=value["source_path"],
            source_sha256=value["source_sha256"],
            source_cycle_id=value["source_cycle_id"],
            venue_id=value["venue_id"],
            instrument_id=value["instrument_id"],
            contract_identity=value["contract_identity"],
            availability_basis=value["availability_basis"],
            source_available_at=value["source_available_at"],
            verbatim_text=value["verbatim_text"],
        )
        if "size_bytes" in value and value["size_bytes"] != item.size_bytes:
            raise MarketCycleContractError(
                "memory.size_bytes does not match verbatim UTF-8 bytes"
            )
        return item


def normalize_verified_memory_items(
    values: Iterable[VerifiedMemoryItem | Mapping[str, Any]],
) -> tuple[VerifiedMemoryItem, ...]:
    """Freeze the runtime-provided bounded memory context in caller order."""

    if isinstance(values, (str, bytes, Mapping)):
        raise MarketCycleContractError("verified_memory must be a sequence")
    normalized: list[VerifiedMemoryItem] = []
    counts = {kind: 0 for kind in MEMORY_ITEM_KINDS}
    identities: set[tuple[str, str]] = set()
    total_size = 0
    for index, supplied in enumerate(values):
        if isinstance(supplied, VerifiedMemoryItem):
            item = supplied
        elif isinstance(supplied, Mapping):
            item = VerifiedMemoryItem.from_dict(supplied)
        else:
            raise MarketCycleContractError(
                f"verified_memory[{index}] must be VerifiedMemoryItem"
            )
        counts[item.kind] += 1
        if counts[item.kind] > MEMORY_ITEM_LIMITS[item.kind]:
            raise MarketCycleContractError(
                f"verified_memory exceeds {item.kind} bound"
            )
        identity = (item.source_path, item.source_sha256)
        if identity in identities:
            raise MarketCycleContractError(
                "verified_memory must not repeat a source path/digest"
            )
        identities.add(identity)
        total_size += item.size_bytes
        if total_size > MEMORY_CONTEXT_MAX_UTF8_BYTES:
            raise MarketCycleContractError(
                f"verified_memory exceeds {MEMORY_CONTEXT_MAX_UTF8_BYTES} UTF-8 bytes"
            )
        normalized.append(item)
    return tuple(normalized)


def verified_memory_context(
    values: Iterable[VerifiedMemoryItem | Mapping[str, Any]],
) -> dict[str, object]:
    """Return the transparent non-authoritative packet envelope."""

    items = normalize_verified_memory_items(values)
    unknown_count = sum(item.status == "UNKNOWN" for item in items)
    if not items:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_NOT_PROVIDED"
    elif unknown_count:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_PARTIAL"
    else:
        status = "AVAILABLE"
        typed_unknown = None
    return {
        "authority": "NON_AUTHORITATIVE_CONTEXT_ONLY",
        "status": status,
        "typed_unknown": typed_unknown,
        "bounds": {
            "item_limits": dict(MEMORY_ITEM_LIMITS),
            "max_item_utf8_bytes": MEMORY_ITEM_MAX_UTF8_BYTES,
            "max_context_utf8_bytes": MEMORY_CONTEXT_MAX_UTF8_BYTES,
        },
        "items": [item.to_dict() for item in items],
    }


@dataclass(frozen=True, slots=True)
class CycleRequest:
    request_id: str
    cycle_id: str
    requested_at: str
    venue_id: str
    instrument_id: str
    contract_identity: str
    analysis_profile: str
    data_profile: str
    outcome_horizon_seconds: int
    outcome_tolerance_seconds: int
    lawful_actions: tuple[str, ...]
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "cycle_id",
            "venue_id",
            "instrument_id",
            "contract_identity",
            "analysis_profile",
            "data_profile",
        ):
            _require_nonempty_string(getattr(self, field_name), field_name=field_name)
        _parse_timestamp(self.requested_at, field_name="requested_at")
        if self.analysis_profile not in {"COLD", "DELTA", "EVENT_FAST"}:
            raise MarketCycleContractError("unsupported analysis_profile")
        if self.data_profile not in MARKET_DATA_PROFILES:
            raise MarketCycleContractError("unsupported data_profile")
        _require_int(
            self.outcome_horizon_seconds,
            field_name="outcome_horizon_seconds",
            minimum=1,
        )
        _require_int(
            self.outcome_tolerance_seconds,
            field_name="outcome_tolerance_seconds",
            minimum=0,
        )
        lawful_actions = _freeze_strings(
            self.lawful_actions, field_name="lawful_actions", allow_empty=False
        )
        if not set(lawful_actions).issubset(LAWFUL_REFERENCE_ACTIONS):
            invalid = sorted(set(lawful_actions) - set(LAWFUL_REFERENCE_ACTIONS))
            raise MarketCycleContractError(f"unsupported lawful actions: {invalid!r}")
        object.__setattr__(self, "lawful_actions", lawful_actions)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "cycle_id": self.cycle_id,
            "requested_at": self.requested_at,
            "venue_id": self.venue_id,
            "instrument_id": self.instrument_id,
            "contract_identity": self.contract_identity,
            "analysis_profile": self.analysis_profile,
            "data_profile": self.data_profile,
            "outcome_horizon_seconds": self.outcome_horizon_seconds,
            "outcome_tolerance_seconds": self.outcome_tolerance_seconds,
            "lawful_actions": list(self.lawful_actions),
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CycleRequest":
        fields = frozenset(
            {
                "request_id",
                "cycle_id",
                "requested_at",
                "venue_id",
                "instrument_id",
                "contract_identity",
                "analysis_profile",
                "data_profile",
                "outcome_horizon_seconds",
                "outcome_tolerance_seconds",
                "lawful_actions",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="CycleRequest")
        return cls(
            request_id=value["request_id"],
            cycle_id=value["cycle_id"],
            requested_at=value["requested_at"],
            venue_id=value["venue_id"],
            instrument_id=value["instrument_id"],
            contract_identity=value["contract_identity"],
            analysis_profile=value["analysis_profile"],
            data_profile=value["data_profile"],
            outcome_horizon_seconds=value["outcome_horizon_seconds"],
            outcome_tolerance_seconds=value["outcome_tolerance_seconds"],
            lawful_actions=tuple(value["lawful_actions"]),
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


def _validate_observation(
    name: str, observation: object, *, decision_at: datetime, raw_hashes: frozenset[str]
) -> None:
    if not isinstance(observation, Mapping):
        raise MarketCycleContractError(f"observation {name!r} must be an object")
    for field_name in ("value", "available_at", "raw_sha256"):
        if field_name not in observation:
            raise MarketCycleContractError(f"observation {name!r} lacks {field_name}")
    available_at = _parse_timestamp(
        observation["available_at"], field_name=f"observations.{name}.available_at"
    )
    if available_at > decision_at:
        raise MarketCycleContractError(f"observation {name!r} violates point-in-time isolation")
    raw_sha256 = _require_sha256(
        observation["raw_sha256"], field_name=f"observations.{name}.raw_sha256"
    )
    if raw_sha256 not in raw_hashes:
        raise MarketCycleContractError(f"observation {name!r} raw digest is not sealed")


@dataclass(frozen=True, slots=True)
class InputSnapshot:
    snapshot_id: str
    cycle_id: str
    request_id: str
    source_cutoff_at: str
    decision_at: str
    sealed_at: str
    venue_id: str
    instrument_id: str
    contract_identity: str
    analysis_profile: str
    data_profile: str
    outcome_horizon_seconds: int
    outcome_tolerance_seconds: int
    lawful_actions: tuple[str, ...]
    core_observations: Mapping[str, Any]
    optional_observations: Mapping[str, Any]
    unknowns: tuple[str, ...]
    raw_refs: tuple[ArtifactRef, ...]
    source_health: tuple[Mapping[str, Any], ...]
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        for field_name in (
            "snapshot_id",
            "cycle_id",
            "request_id",
            "venue_id",
            "instrument_id",
            "contract_identity",
            "analysis_profile",
            "data_profile",
        ):
            _require_nonempty_string(getattr(self, field_name), field_name=field_name)
        source_cutoff_at = _parse_timestamp(
            self.source_cutoff_at, field_name="source_cutoff_at"
        )
        decision_at = _parse_timestamp(self.decision_at, field_name="decision_at")
        sealed_at = _parse_timestamp(self.sealed_at, field_name="sealed_at")
        if source_cutoff_at > decision_at:
            raise MarketCycleContractError("source_cutoff_at cannot follow decision_at")
        if sealed_at < decision_at:
            raise MarketCycleContractError("InputSnapshot must be sealed at or after decision_at")
        if self.analysis_profile not in {"COLD", "DELTA", "EVENT_FAST"}:
            raise MarketCycleContractError("unsupported analysis_profile")
        if self.data_profile not in MARKET_DATA_PROFILES:
            raise MarketCycleContractError("unsupported data_profile")
        _require_int(
            self.outcome_horizon_seconds,
            field_name="outcome_horizon_seconds",
            minimum=1,
        )
        _require_int(
            self.outcome_tolerance_seconds,
            field_name="outcome_tolerance_seconds",
            minimum=0,
        )
        outcome_due_at = decision_at + timedelta(
            seconds=self.outcome_horizon_seconds
        )
        if sealed_at >= outcome_due_at:
            raise MarketCycleContractError(
                "InputSnapshot must be sealed before outcome_due_at"
            )
        lawful_actions = _freeze_strings(
            self.lawful_actions, field_name="lawful_actions", allow_empty=False
        )
        if not set(lawful_actions).issubset(LAWFUL_REFERENCE_ACTIONS):
            raise MarketCycleContractError("InputSnapshot contains an unsupported lawful action")
        raw_refs = tuple(self.raw_refs)
        if not all(isinstance(reference, ArtifactRef) for reference in raw_refs):
            raise MarketCycleContractError("raw_refs must contain ArtifactRef values")
        if not raw_refs:
            raise MarketCycleContractError("InputSnapshot must bind at least one raw capture")
        raw_hashes = frozenset(reference.sha256 for reference in raw_refs)
        core = _freeze_json(self.core_observations, path="core_observations")
        optional = _freeze_json(self.optional_observations, path="optional_observations")
        if not isinstance(core, Mapping) or not isinstance(optional, Mapping):
            raise MarketCycleContractError("observations must be objects")
        required_core = frozenset(
            {"server_time", "instrument", "mark_price", "closed_15m_bars"}
        )
        if frozenset(core) != required_core:
            raise MarketCycleContractError(
                "core_observations must contain exactly server_time, instrument, "
                "mark_price and closed_15m_bars"
            )
        for name, observation in core.items():
            _validate_observation(
                name,
                observation,
                decision_at=source_cutoff_at,
                raw_hashes=raw_hashes,
            )
        for name, observation in optional.items():
            _validate_observation(
                name,
                observation,
                decision_at=source_cutoff_at,
                raw_hashes=raw_hashes,
            )
        candles = core["closed_15m_bars"]
        if not isinstance(candles, Mapping) or "last_closed_at" not in candles:
            raise MarketCycleContractError("closed_15m_bars must declare last_closed_at")
        if _parse_timestamp(
            candles["last_closed_at"],
            field_name="core_observations.closed_15m_bars.last_closed_at",
        ) > source_cutoff_at:
            raise MarketCycleContractError("a bar after source cutoff cannot enter a snapshot")
        unknowns = _freeze_strings(self.unknowns, field_name="unknowns")
        source_health = tuple(
            _freeze_json(item, path=f"source_health[{index}]")
            for index, item in enumerate(self.source_health)
        )
        for index, item in enumerate(source_health):
            if (
                not isinstance(item, Mapping)
                or not isinstance(item.get("component_id"), str)
                or not item.get("component_id")
                or item.get("status") not in {"OBSERVED", "MISSING", "UNKNOWN"}
            ):
                raise MarketCycleContractError(
                    f"source_health[{index}] lacks a typed component status"
                )
            if "available_at" in item and _parse_timestamp(
                item["available_at"],
                field_name=f"source_health[{index}].available_at",
            ) > source_cutoff_at:
                raise MarketCycleContractError(
                    f"source_health[{index}] violates source cutoff"
                )
        object.__setattr__(self, "lawful_actions", lawful_actions)
        object.__setattr__(self, "core_observations", core)
        object.__setattr__(self, "optional_observations", optional)
        object.__setattr__(self, "unknowns", unknowns)
        object.__setattr__(self, "raw_refs", raw_refs)
        object.__setattr__(self, "source_health", source_health)
        require_supported_theory_identity(self.theory_identity)

    @property
    def outcome_due_at(self) -> str:
        due = _parse_timestamp(self.decision_at, field_name="decision_at") + timedelta(
            seconds=self.outcome_horizon_seconds
        )
        return due.isoformat()

    @classmethod
    def seal(
        cls,
        request: CycleRequest,
        *,
        snapshot_id: str,
        source_cutoff_at: str,
        decision_at: str,
        sealed_at: str,
        core_observations: Mapping[str, Any],
        optional_observations: Mapping[str, Any],
        unknowns: Sequence[str],
        raw_refs: Sequence[ArtifactRef],
        source_health: Sequence[Mapping[str, Any]],
    ) -> "InputSnapshot":
        requested_at = _parse_timestamp(request.requested_at, field_name="requested_at")
        cutoff_at = _parse_timestamp(source_cutoff_at, field_name="source_cutoff_at")
        decision = _parse_timestamp(decision_at, field_name="decision_at")
        if not requested_at <= cutoff_at <= decision:
            raise MarketCycleContractError(
                "snapshot chronology must be requested_at <= source_cutoff_at <= decision_at"
            )
        return cls(
            snapshot_id=snapshot_id,
            cycle_id=request.cycle_id,
            request_id=request.request_id,
            source_cutoff_at=source_cutoff_at,
            decision_at=decision_at,
            sealed_at=sealed_at,
            venue_id=request.venue_id,
            instrument_id=request.instrument_id,
            contract_identity=request.contract_identity,
            analysis_profile=request.analysis_profile,
            data_profile=request.data_profile,
            outcome_horizon_seconds=request.outcome_horizon_seconds,
            outcome_tolerance_seconds=request.outcome_tolerance_seconds,
            lawful_actions=request.lawful_actions,
            core_observations=core_observations,
            optional_observations=optional_observations,
            unknowns=tuple(unknowns),
            raw_refs=tuple(raw_refs),
            source_health=tuple(source_health),
            theory_identity=request.theory_identity,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "cycle_id": self.cycle_id,
            "request_id": self.request_id,
            "source_cutoff_at": self.source_cutoff_at,
            "decision_at": self.decision_at,
            "sealed_at": self.sealed_at,
            "venue_id": self.venue_id,
            "instrument_id": self.instrument_id,
            "contract_identity": self.contract_identity,
            "analysis_profile": self.analysis_profile,
            "data_profile": self.data_profile,
            "outcome_horizon_seconds": self.outcome_horizon_seconds,
            "outcome_tolerance_seconds": self.outcome_tolerance_seconds,
            "lawful_actions": list(self.lawful_actions),
            "core_observations": _thaw_json(self.core_observations),
            "optional_observations": _thaw_json(self.optional_observations),
            "unknowns": list(self.unknowns),
            "raw_refs": [reference.to_dict() for reference in self.raw_refs],
            "source_health": [_thaw_json(item) for item in self.source_health],
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InputSnapshot":
        fields = frozenset(
            {
                "snapshot_id",
                "cycle_id",
                "request_id",
                "source_cutoff_at",
                "decision_at",
                "sealed_at",
                "venue_id",
                "instrument_id",
                "contract_identity",
                "analysis_profile",
                "data_profile",
                "outcome_horizon_seconds",
                "outcome_tolerance_seconds",
                "lawful_actions",
                "core_observations",
                "optional_observations",
                "unknowns",
                "raw_refs",
                "source_health",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="InputSnapshot")
        return cls(
            snapshot_id=value["snapshot_id"],
            cycle_id=value["cycle_id"],
            request_id=value["request_id"],
            source_cutoff_at=value["source_cutoff_at"],
            decision_at=value["decision_at"],
            sealed_at=value["sealed_at"],
            venue_id=value["venue_id"],
            instrument_id=value["instrument_id"],
            contract_identity=value["contract_identity"],
            analysis_profile=value["analysis_profile"],
            data_profile=value["data_profile"],
            outcome_horizon_seconds=value["outcome_horizon_seconds"],
            outcome_tolerance_seconds=value["outcome_tolerance_seconds"],
            lawful_actions=tuple(value["lawful_actions"]),
            core_observations=value["core_observations"],
            optional_observations=value["optional_observations"],
            unknowns=tuple(value["unknowns"]),
            raw_refs=tuple(ArtifactRef.from_dict(item) for item in value["raw_refs"]),
            source_health=tuple(value["source_health"]),
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


def snapshot_bound_memory_context(
    snapshot: InputSnapshot,
    values: Iterable[VerifiedMemoryItem | Mapping[str, Any]],
) -> dict[str, object]:
    """Project verified memory through the current snapshot's PIT boundary.

    Provenance that is current-cycle, future-available, or identity-mismatched
    remains visible as a typed UNKNOWN entry, but its source text is never
    forwarded to the Agent.  Contextual rejection is an optional-data
    degradation and therefore never raises or terminates the current cycle.
    Structural corruption continues to be rejected by normalization.
    """

    if not isinstance(snapshot, InputSnapshot):
        raise MarketCycleContractError(
            "snapshot_bound_memory_context requires an InputSnapshot"
        )
    items = normalize_verified_memory_items(values)
    cutoff_at = _parse_timestamp(
        snapshot.source_cutoff_at, field_name="source_cutoff_at"
    )
    projected: list[dict[str, object]] = []
    eligible_count = 0
    contains_declared_unknown = False
    for item in items:
        typed_unknown: str | None = None
        if item.source_cycle_id == snapshot.cycle_id:
            typed_unknown = "MEMORY_SOURCE_CURRENT_CYCLE_EXCLUDED"
        elif item.venue_id != snapshot.venue_id:
            typed_unknown = "MEMORY_SOURCE_VENUE_MISMATCH"
        elif item.instrument_id != snapshot.instrument_id:
            typed_unknown = "MEMORY_SOURCE_INSTRUMENT_MISMATCH"
        elif item.contract_identity != snapshot.contract_identity:
            typed_unknown = "MEMORY_SOURCE_CONTRACT_MISMATCH"
        elif _parse_timestamp(
            item.source_available_at, field_name="memory.source_available_at"
        ) > cutoff_at:
            typed_unknown = "MEMORY_SOURCE_AFTER_SNAPSHOT_CUTOFF"

        if typed_unknown is None:
            projected.append(item.to_dict())
            eligible_count += 1
            contains_declared_unknown = (
                contains_declared_unknown or item.status == "UNKNOWN"
            )
            continue

        withheld = item.to_dict()
        withheld.pop("verbatim_text")
        withheld["status"] = "UNKNOWN"
        withheld["typed_unknown"] = typed_unknown
        projected.append(withheld)

    if not items:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_NOT_PROVIDED"
    elif eligible_count == len(items) and not contains_declared_unknown:
        status = "AVAILABLE"
        typed_unknown = None
    elif eligible_count == 0:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_NO_ELIGIBLE_ITEMS"
    else:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_PARTIAL"
    return {
        "authority": "NON_AUTHORITATIVE_CONTEXT_ONLY",
        "status": status,
        "typed_unknown": typed_unknown,
        "bounds": {
            "item_limits": dict(MEMORY_ITEM_LIMITS),
            "max_item_utf8_bytes": MEMORY_ITEM_MAX_UTF8_BYTES,
            "max_context_utf8_bytes": MEMORY_CONTEXT_MAX_UTF8_BYTES,
        },
        "items": projected,
    }


def validate_snapshot_bound_memory_context(
    snapshot: InputSnapshot, value: Mapping[str, Any]
) -> dict[str, object]:
    """Validate one persisted PIT-filtered memory envelope without restoring text.

    Redacted entries intentionally have no ``verbatim_text``.  This validator
    therefore checks their complete provenance and recomputes the exclusion
    reason from the sealed snapshot, while eligible entries are rebuilt from
    ``VerifiedMemoryItem``.  It is the persisted-sidecar counterpart of
    ``snapshot_bound_memory_context`` and shares the same Domain-owned rules.
    """

    if not isinstance(snapshot, InputSnapshot):
        raise MarketCycleContractError(
            "validate_snapshot_bound_memory_context requires an InputSnapshot"
        )
    _require_exact_keys(
        value,
        required=frozenset(
            {"authority", "status", "typed_unknown", "bounds", "items"}
        ),
        context="snapshot-bound memory context",
    )
    expected_bounds = {
        "item_limits": dict(MEMORY_ITEM_LIMITS),
        "max_item_utf8_bytes": MEMORY_ITEM_MAX_UTF8_BYTES,
        "max_context_utf8_bytes": MEMORY_CONTEXT_MAX_UTF8_BYTES,
    }
    supplied_items = value["items"]
    if not isinstance(supplied_items, list):
        raise MarketCycleContractError("memory context items must be a list")

    item_fields = frozenset(
        {
            "kind",
            "status",
            "source_path",
            "source_sha256",
            "size_bytes",
            "source_cycle_id",
            "venue_id",
            "instrument_id",
            "contract_identity",
            "availability_basis",
            "source_available_at",
        }
    )
    counts = {kind: 0 for kind in MEMORY_ITEM_KINDS}
    identities: set[tuple[str, str]] = set()
    total_size = 0
    projected: list[dict[str, object]] = []
    eligible_count = 0
    contains_declared_unknown = False
    cutoff_at = _parse_timestamp(
        snapshot.source_cutoff_at, field_name="source_cutoff_at"
    )

    for index, supplied in enumerate(supplied_items):
        if not isinstance(supplied, Mapping):
            raise MarketCycleContractError(
                f"memory context items[{index}] must be an object"
            )
        if "verbatim_text" in supplied:
            item = VerifiedMemoryItem.from_dict(supplied)
            expected_item = item.to_dict()
        else:
            _require_exact_keys(
                supplied,
                required=item_fields | {"typed_unknown"},
                context=f"redacted memory item[{index}]",
            )
            kind = supplied["kind"]
            if kind not in MEMORY_ITEM_KINDS:
                raise MarketCycleContractError("unsupported memory item kind")
            if supplied["status"] != "UNKNOWN":
                raise MarketCycleContractError(
                    "redacted memory item status must be UNKNOWN"
                )
            _require_provenance_path(
                supplied["source_path"], field_name="memory.source_path"
            )
            _require_sha256(
                supplied["source_sha256"], field_name="memory.source_sha256"
            )
            _require_int(
                supplied["size_bytes"],
                field_name="memory.size_bytes",
                minimum=1,
            )
            if supplied["size_bytes"] > MEMORY_ITEM_MAX_UTF8_BYTES:
                raise MarketCycleContractError(
                    "memory.size_bytes exceeds the per-item bound"
                )
            for field_name in (
                "source_cycle_id",
                "venue_id",
                "instrument_id",
                "contract_identity",
            ):
                _require_nonempty_string(
                    supplied[field_name], field_name=f"memory.{field_name}"
                )
            if supplied["availability_basis"] not in MEMORY_AVAILABILITY_BASES:
                raise MarketCycleContractError(
                    "memory.availability_basis must be SEALED_AT or REVIEWED_AT"
                )
            _parse_timestamp(
                supplied["source_available_at"],
                field_name="memory.source_available_at",
            )
            expected_item = dict(supplied)

        counts[expected_item["kind"]] += 1
        if counts[expected_item["kind"]] > MEMORY_ITEM_LIMITS[expected_item["kind"]]:
            raise MarketCycleContractError(
                f"verified_memory exceeds {expected_item['kind']} bound"
            )
        identity = (
            str(expected_item["source_path"]),
            str(expected_item["source_sha256"]),
        )
        if identity in identities:
            raise MarketCycleContractError(
                "verified_memory must not repeat a source path/digest"
            )
        identities.add(identity)
        total_size += int(expected_item["size_bytes"])
        if total_size > MEMORY_CONTEXT_MAX_UTF8_BYTES:
            raise MarketCycleContractError(
                f"verified_memory exceeds {MEMORY_CONTEXT_MAX_UTF8_BYTES} UTF-8 bytes"
            )

        reason: str | None = None
        if expected_item["source_cycle_id"] == snapshot.cycle_id:
            reason = "MEMORY_SOURCE_CURRENT_CYCLE_EXCLUDED"
        elif expected_item["venue_id"] != snapshot.venue_id:
            reason = "MEMORY_SOURCE_VENUE_MISMATCH"
        elif expected_item["instrument_id"] != snapshot.instrument_id:
            reason = "MEMORY_SOURCE_INSTRUMENT_MISMATCH"
        elif expected_item["contract_identity"] != snapshot.contract_identity:
            reason = "MEMORY_SOURCE_CONTRACT_MISMATCH"
        elif _parse_timestamp(
            expected_item["source_available_at"],
            field_name="memory.source_available_at",
        ) > cutoff_at:
            reason = "MEMORY_SOURCE_AFTER_SNAPSHOT_CUTOFF"

        if "verbatim_text" in expected_item:
            if reason is not None:
                raise MarketCycleContractError(
                    "ineligible memory item must not expose verbatim_text"
                )
            projected.append(expected_item)
            eligible_count += 1
            contains_declared_unknown = (
                contains_declared_unknown
                or expected_item["status"] == "UNKNOWN"
            )
        else:
            if reason is None or expected_item["typed_unknown"] != reason:
                raise MarketCycleContractError(
                    "redacted memory item exclusion reason is invalid"
                )
            projected.append(expected_item)

    if not projected:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_NOT_PROVIDED"
    elif eligible_count == len(projected) and not contains_declared_unknown:
        status = "AVAILABLE"
        typed_unknown = None
    elif eligible_count == 0:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_NO_ELIGIBLE_ITEMS"
    else:
        status = "UNKNOWN"
        typed_unknown = "MEMORY_CONTEXT_PARTIAL"
    expected = {
        "authority": "NON_AUTHORITATIVE_CONTEXT_ONLY",
        "status": status,
        "typed_unknown": typed_unknown,
        "bounds": expected_bounds,
        "items": projected,
    }
    if dict(value) != expected:
        raise MarketCycleContractError("snapshot-bound memory context is invalid")
    return expected


@dataclass(frozen=True, slots=True)
class HypothesisRecord:
    record_id: str
    cycle_id: str
    input_snapshot_ref: ArtifactRef
    decision_at: str
    agent_delivered_at: str
    sealed_at: str
    outcome_horizon_seconds: int
    outcome_tolerance_seconds: int
    agent_request_sha256: str
    agent_delivery_path: str
    agent_delivery_sha256: str
    agent_decision_text: str
    agent_decision_size_bytes: int
    agent_decision_sha256: str
    projection_status: str
    projection_reason: str | None
    hypothesis_index: tuple[str, ...]
    agent_action_text: str | None
    agent_position_text: str | None
    lawful_actions: tuple[str, ...]
    unresolved_unknowns: tuple[str, ...]
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.record_id, field_name="record_id")
        _require_nonempty_string(self.cycle_id, field_name="cycle_id")
        if not isinstance(self.input_snapshot_ref, ArtifactRef):
            raise MarketCycleContractError("input_snapshot_ref must be ArtifactRef")
        if self.input_snapshot_ref.artifact_type != "InputSnapshot":
            raise MarketCycleContractError("HypothesisRecord must reference InputSnapshot")
        decision_at = _parse_timestamp(self.decision_at, field_name="decision_at")
        delivered_at = _parse_timestamp(
            self.agent_delivered_at, field_name="agent_delivered_at"
        )
        sealed_at = _parse_timestamp(self.sealed_at, field_name="sealed_at")
        if not decision_at <= delivered_at <= sealed_at:
            raise MarketCycleContractError(
                "HypothesisRecord chronology must be decision_at <= "
                "agent_delivered_at <= sealed_at"
            )
        _require_int(
            self.outcome_horizon_seconds,
            field_name="outcome_horizon_seconds",
            minimum=1,
        )
        _require_int(
            self.outcome_tolerance_seconds,
            field_name="outcome_tolerance_seconds",
            minimum=0,
        )
        outcome_due_at = decision_at + timedelta(
            seconds=self.outcome_horizon_seconds
        )
        if sealed_at >= outcome_due_at:
            raise MarketCycleContractError(
                "HypothesisRecord must be sealed before outcome_due_at"
            )
        _require_sha256(
            self.agent_request_sha256, field_name="agent_request_sha256"
        )
        delivery_path = _require_cycle_relative_path(
            self.agent_delivery_path, field_name="agent_delivery_path"
        )
        _require_sha256(
            self.agent_delivery_sha256, field_name="agent_delivery_sha256"
        )
        decision_raw = _agent_text_bytes(
            self.agent_decision_text, field_name="agent_decision_text"
        )
        _require_int(
            self.agent_decision_size_bytes,
            field_name="agent_decision_size_bytes",
            minimum=1,
        )
        if self.agent_decision_size_bytes != len(decision_raw):
            raise MarketCycleContractError(
                "agent_decision_size_bytes does not match verbatim UTF-8 bytes"
            )
        decision_sha256 = _require_sha256(
            self.agent_decision_sha256, field_name="agent_decision_sha256"
        )
        if hashlib.sha256(decision_raw).hexdigest() != decision_sha256:
            raise MarketCycleContractError(
                "agent_decision_sha256 does not match verbatim UTF-8 bytes"
            )
        (
            projection_status,
            projection_reason,
            hypothesis_index,
            action_text,
            position_text,
        ) = _validate_agent_projection(
            decision_text=self.agent_decision_text,
            projection_status=self.projection_status,
            projection_reason=self.projection_reason,
            hypothesis_index=self.hypothesis_index,
            agent_action_text=self.agent_action_text,
            agent_position_text=self.agent_position_text,
        )
        lawful_actions = _freeze_strings(
            self.lawful_actions, field_name="lawful_actions", allow_empty=False
        )
        if not set(lawful_actions).issubset(LAWFUL_REFERENCE_ACTIONS):
            raise MarketCycleContractError("HypothesisRecord contains unsupported action")
        unknowns = _freeze_strings(
            self.unresolved_unknowns, field_name="unresolved_unknowns"
        )
        if (
            projection_status == "UNKNOWN"
            and AGENT_OUTPUT_INCOMPLETE not in unknowns
        ):
            raise MarketCycleContractError(
                "UNKNOWN projection must retain AGENT_OUTPUT_INCOMPLETE"
            )
        object.__setattr__(self, "agent_delivery_path", delivery_path)
        object.__setattr__(self, "projection_status", projection_status)
        object.__setattr__(self, "projection_reason", projection_reason)
        object.__setattr__(self, "hypothesis_index", hypothesis_index)
        object.__setattr__(self, "agent_action_text", action_text)
        object.__setattr__(self, "agent_position_text", position_text)
        object.__setattr__(self, "lawful_actions", lawful_actions)
        object.__setattr__(self, "unresolved_unknowns", unknowns)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "cycle_id": self.cycle_id,
            "input_snapshot_ref": self.input_snapshot_ref.to_dict(),
            "decision_at": self.decision_at,
            "agent_delivered_at": self.agent_delivered_at,
            "sealed_at": self.sealed_at,
            "outcome_horizon_seconds": self.outcome_horizon_seconds,
            "outcome_tolerance_seconds": self.outcome_tolerance_seconds,
            "agent_request_sha256": self.agent_request_sha256,
            "agent_delivery_path": self.agent_delivery_path,
            "agent_delivery_sha256": self.agent_delivery_sha256,
            "agent_decision_text": self.agent_decision_text,
            "agent_decision_size_bytes": self.agent_decision_size_bytes,
            "agent_decision_sha256": self.agent_decision_sha256,
            "projection_status": self.projection_status,
            "projection_reason": self.projection_reason,
            "hypothesis_index": list(self.hypothesis_index),
            "agent_action_text": self.agent_action_text,
            "agent_position_text": self.agent_position_text,
            "lawful_actions": list(self.lawful_actions),
            "unresolved_unknowns": list(self.unresolved_unknowns),
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HypothesisRecord":
        fields = frozenset(
            {
                "record_id",
                "cycle_id",
                "input_snapshot_ref",
                "decision_at",
                "agent_delivered_at",
                "sealed_at",
                "outcome_horizon_seconds",
                "outcome_tolerance_seconds",
                "agent_request_sha256",
                "agent_delivery_path",
                "agent_delivery_sha256",
                "agent_decision_text",
                "agent_decision_size_bytes",
                "agent_decision_sha256",
                "projection_status",
                "projection_reason",
                "hypothesis_index",
                "agent_action_text",
                "agent_position_text",
                "lawful_actions",
                "unresolved_unknowns",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="HypothesisRecord")
        return cls(
            record_id=value["record_id"],
            cycle_id=value["cycle_id"],
            input_snapshot_ref=ArtifactRef.from_dict(value["input_snapshot_ref"]),
            decision_at=value["decision_at"],
            agent_delivered_at=value["agent_delivered_at"],
            sealed_at=value["sealed_at"],
            outcome_horizon_seconds=value["outcome_horizon_seconds"],
            outcome_tolerance_seconds=value["outcome_tolerance_seconds"],
            agent_request_sha256=value["agent_request_sha256"],
            agent_delivery_path=value["agent_delivery_path"],
            agent_delivery_sha256=value["agent_delivery_sha256"],
            agent_decision_text=value["agent_decision_text"],
            agent_decision_size_bytes=value["agent_decision_size_bytes"],
            agent_decision_sha256=value["agent_decision_sha256"],
            projection_status=value["projection_status"],
            projection_reason=value["projection_reason"],
            hypothesis_index=tuple(value["hypothesis_index"]),
            agent_action_text=value["agent_action_text"],
            agent_position_text=value["agent_position_text"],
            lawful_actions=tuple(value["lawful_actions"]),
            unresolved_unknowns=tuple(value["unresolved_unknowns"]),
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


@dataclass(frozen=True, slots=True)
class BehaviorPlan:
    plan_id: str
    cycle_id: str
    hypothesis_record_ref: ArtifactRef
    decision_at: str
    agent_delivered_at: str
    sealed_at: str
    risk_mode: str
    execution_mapping: str
    executable_quantity: None
    agent_request_sha256: str
    agent_delivery_path: str
    agent_delivery_sha256: str
    agent_decision_text: str
    agent_decision_size_bytes: int
    agent_decision_sha256: str
    projection_status: str
    projection_reason: str | None
    hypothesis_index: tuple[str, ...]
    agent_action_text: str | None
    agent_position_text: str | None
    outcome_due_at: str
    outcome_tolerance_seconds: int
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.plan_id, field_name="plan_id")
        _require_nonempty_string(self.cycle_id, field_name="cycle_id")
        if not isinstance(self.hypothesis_record_ref, ArtifactRef):
            raise MarketCycleContractError("hypothesis_record_ref must be ArtifactRef")
        if self.hypothesis_record_ref.artifact_type != "HypothesisRecord":
            raise MarketCycleContractError("BehaviorPlan must reference HypothesisRecord")
        decision_at = _parse_timestamp(self.decision_at, field_name="decision_at")
        delivered_at = _parse_timestamp(
            self.agent_delivered_at, field_name="agent_delivered_at"
        )
        sealed_at = _parse_timestamp(self.sealed_at, field_name="sealed_at")
        if not decision_at <= delivered_at <= sealed_at:
            raise MarketCycleContractError(
                "BehaviorPlan chronology must be decision_at <= agent_delivered_at "
                "<= sealed_at"
            )
        outcome_due = _parse_timestamp(self.outcome_due_at, field_name="outcome_due_at")
        if outcome_due <= decision_at:
            raise MarketCycleContractError("outcome_due_at must be after decision_at")
        if sealed_at >= outcome_due:
            raise MarketCycleContractError(
                "BehaviorPlan must be sealed before outcome_due_at"
            )
        _require_int(
            self.outcome_tolerance_seconds,
            field_name="outcome_tolerance_seconds",
            minimum=0,
        )
        if self.risk_mode != "REFERENCE":
            raise MarketCycleContractError("new market cycles are REFERENCE-only")
        if self.execution_mapping != "NOT_READY" or self.executable_quantity is not None:
            raise MarketCycleContractError(
                "execution must remain NOT_READY with executable_quantity=null"
            )
        _require_sha256(
            self.agent_request_sha256, field_name="agent_request_sha256"
        )
        delivery_path = _require_cycle_relative_path(
            self.agent_delivery_path, field_name="agent_delivery_path"
        )
        _require_sha256(
            self.agent_delivery_sha256, field_name="agent_delivery_sha256"
        )
        decision_raw = _agent_text_bytes(
            self.agent_decision_text, field_name="agent_decision_text"
        )
        _require_int(
            self.agent_decision_size_bytes,
            field_name="agent_decision_size_bytes",
            minimum=1,
        )
        if self.agent_decision_size_bytes != len(decision_raw):
            raise MarketCycleContractError(
                "agent_decision_size_bytes does not match verbatim UTF-8 bytes"
            )
        decision_sha256 = _require_sha256(
            self.agent_decision_sha256, field_name="agent_decision_sha256"
        )
        if hashlib.sha256(decision_raw).hexdigest() != decision_sha256:
            raise MarketCycleContractError(
                "agent_decision_sha256 does not match verbatim UTF-8 bytes"
            )
        (
            projection_status,
            projection_reason,
            hypothesis_index,
            action_text,
            position_text,
        ) = _validate_agent_projection(
            decision_text=self.agent_decision_text,
            projection_status=self.projection_status,
            projection_reason=self.projection_reason,
            hypothesis_index=self.hypothesis_index,
            agent_action_text=self.agent_action_text,
            agent_position_text=self.agent_position_text,
        )
        object.__setattr__(self, "agent_delivery_path", delivery_path)
        object.__setattr__(self, "projection_status", projection_status)
        object.__setattr__(self, "projection_reason", projection_reason)
        object.__setattr__(self, "hypothesis_index", hypothesis_index)
        object.__setattr__(self, "agent_action_text", action_text)
        object.__setattr__(self, "agent_position_text", position_text)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "cycle_id": self.cycle_id,
            "hypothesis_record_ref": self.hypothesis_record_ref.to_dict(),
            "decision_at": self.decision_at,
            "agent_delivered_at": self.agent_delivered_at,
            "sealed_at": self.sealed_at,
            "risk_mode": self.risk_mode,
            "execution_mapping": self.execution_mapping,
            "executable_quantity": None,
            "agent_request_sha256": self.agent_request_sha256,
            "agent_delivery_path": self.agent_delivery_path,
            "agent_delivery_sha256": self.agent_delivery_sha256,
            "agent_decision_text": self.agent_decision_text,
            "agent_decision_size_bytes": self.agent_decision_size_bytes,
            "agent_decision_sha256": self.agent_decision_sha256,
            "projection_status": self.projection_status,
            "projection_reason": self.projection_reason,
            "hypothesis_index": list(self.hypothesis_index),
            "agent_action_text": self.agent_action_text,
            "agent_position_text": self.agent_position_text,
            "outcome_due_at": self.outcome_due_at,
            "outcome_tolerance_seconds": self.outcome_tolerance_seconds,
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BehaviorPlan":
        fields = frozenset(
            {
                "plan_id",
                "cycle_id",
                "hypothesis_record_ref",
                "decision_at",
                "agent_delivered_at",
                "sealed_at",
                "risk_mode",
                "execution_mapping",
                "executable_quantity",
                "agent_request_sha256",
                "agent_delivery_path",
                "agent_delivery_sha256",
                "agent_decision_text",
                "agent_decision_size_bytes",
                "agent_decision_sha256",
                "projection_status",
                "projection_reason",
                "hypothesis_index",
                "agent_action_text",
                "agent_position_text",
                "outcome_due_at",
                "outcome_tolerance_seconds",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="BehaviorPlan")
        return cls(
            plan_id=value["plan_id"],
            cycle_id=value["cycle_id"],
            hypothesis_record_ref=ArtifactRef.from_dict(value["hypothesis_record_ref"]),
            decision_at=value["decision_at"],
            agent_delivered_at=value["agent_delivered_at"],
            sealed_at=value["sealed_at"],
            risk_mode=value["risk_mode"],
            execution_mapping=value["execution_mapping"],
            executable_quantity=value["executable_quantity"],
            agent_request_sha256=value["agent_request_sha256"],
            agent_delivery_path=value["agent_delivery_path"],
            agent_delivery_sha256=value["agent_delivery_sha256"],
            agent_decision_text=value["agent_decision_text"],
            agent_decision_size_bytes=value["agent_decision_size_bytes"],
            agent_decision_sha256=value["agent_decision_sha256"],
            projection_status=value["projection_status"],
            projection_reason=value["projection_reason"],
            hypothesis_index=tuple(value["hypothesis_index"]),
            agent_action_text=value["agent_action_text"],
            agent_position_text=value["agent_position_text"],
            outcome_due_at=value["outcome_due_at"],
            outcome_tolerance_seconds=value["outcome_tolerance_seconds"],
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


@dataclass(frozen=True, slots=True)
class Outcome:
    outcome_id: str
    cycle_id: str
    behavior_plan_ref: ArtifactRef
    due_at: str
    tolerance_seconds: int
    observed_at: str
    sealed_at: str
    terminal_status: str
    endpoint_observation: Mapping[str, Any] | None
    typed_missing: str | None
    path_observations: Mapping[str, Any]
    raw_refs: tuple[ArtifactRef, ...]
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.outcome_id, field_name="outcome_id")
        _require_nonempty_string(self.cycle_id, field_name="cycle_id")
        if not isinstance(self.behavior_plan_ref, ArtifactRef):
            raise MarketCycleContractError("behavior_plan_ref must be ArtifactRef")
        if self.behavior_plan_ref.artifact_type != "BehaviorPlan":
            raise MarketCycleContractError("Outcome must reference BehaviorPlan")
        due_at = _parse_timestamp(self.due_at, field_name="due_at")
        observed_at = _parse_timestamp(self.observed_at, field_name="observed_at")
        sealed_at = _parse_timestamp(self.sealed_at, field_name="sealed_at")
        if observed_at < due_at:
            raise MarketCycleContractError("Outcome cannot be observed before it is due")
        if sealed_at < observed_at:
            raise MarketCycleContractError("Outcome cannot be sealed before observed_at")
        _require_int(self.tolerance_seconds, field_name="tolerance_seconds", minimum=0)
        if self.terminal_status not in {"OBSERVED", "TYPED_MISSING"}:
            raise MarketCycleContractError("Outcome must end OBSERVED or TYPED_MISSING")
        raw_refs = tuple(self.raw_refs)
        if not all(isinstance(reference, ArtifactRef) for reference in raw_refs):
            raise MarketCycleContractError("Outcome.raw_refs must contain ArtifactRef values")
        raw_hashes = frozenset(reference.sha256 for reference in raw_refs)
        endpoint = (
            None
            if self.endpoint_observation is None
            else _freeze_json(self.endpoint_observation, path="endpoint_observation")
        )
        path_observations = _freeze_json(
            self.path_observations, path="path_observations"
        )
        if not isinstance(path_observations, Mapping):
            raise MarketCycleContractError("path_observations must be an object")
        if self.terminal_status == "OBSERVED":
            if not isinstance(endpoint, Mapping) or self.typed_missing is not None:
                raise MarketCycleContractError(
                    "OBSERVED outcome requires endpoint and no typed_missing"
                )
            for required in (
                "value",
                "unit",
                "price_field",
                "effective_at",
                "available_at",
                "raw_sha256",
            ):
                if required not in endpoint:
                    raise MarketCycleContractError(f"endpoint_observation lacks {required}")
            effective_at = _parse_timestamp(
                endpoint["effective_at"], field_name="endpoint_observation.effective_at"
            )
            if abs((effective_at - due_at).total_seconds()) > self.tolerance_seconds:
                raise MarketCycleContractError("endpoint is outside the preregistered tolerance")
            available_at = _parse_timestamp(
                endpoint["available_at"], field_name="endpoint_observation.available_at"
            )
            if available_at > observed_at:
                raise MarketCycleContractError("endpoint was not available when outcome was observed")
            raw_sha = _require_sha256(
                endpoint["raw_sha256"], field_name="endpoint_observation.raw_sha256"
            )
            if raw_sha not in raw_hashes:
                raise MarketCycleContractError("endpoint raw digest is not sealed")
        else:
            if endpoint is not None:
                raise MarketCycleContractError("TYPED_MISSING outcome cannot contain endpoint")
            _require_nonempty_string(self.typed_missing, field_name="typed_missing")
        _validate_v332_ordered_path(
            path_observations,
            due_at=due_at,
            observed_at=observed_at,
            raw_hashes=raw_hashes,
            required=self.theory_identity == V332_THEORY_IDENTITY,
        )
        object.__setattr__(self, "endpoint_observation", endpoint)
        object.__setattr__(self, "path_observations", path_observations)
        object.__setattr__(self, "raw_refs", raw_refs)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome_id": self.outcome_id,
            "cycle_id": self.cycle_id,
            "behavior_plan_ref": self.behavior_plan_ref.to_dict(),
            "due_at": self.due_at,
            "tolerance_seconds": self.tolerance_seconds,
            "observed_at": self.observed_at,
            "sealed_at": self.sealed_at,
            "terminal_status": self.terminal_status,
            "endpoint_observation": (
                None
                if self.endpoint_observation is None
                else _thaw_json(self.endpoint_observation)
            ),
            "typed_missing": self.typed_missing,
            "path_observations": _thaw_json(self.path_observations),
            "raw_refs": [reference.to_dict() for reference in self.raw_refs],
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Outcome":
        fields = frozenset(
            {
                "outcome_id",
                "cycle_id",
                "behavior_plan_ref",
                "due_at",
                "tolerance_seconds",
                "observed_at",
                "sealed_at",
                "terminal_status",
                "endpoint_observation",
                "typed_missing",
                "path_observations",
                "raw_refs",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="Outcome")
        return cls(
            outcome_id=value["outcome_id"],
            cycle_id=value["cycle_id"],
            behavior_plan_ref=ArtifactRef.from_dict(value["behavior_plan_ref"]),
            due_at=value["due_at"],
            tolerance_seconds=value["tolerance_seconds"],
            observed_at=value["observed_at"],
            sealed_at=value["sealed_at"],
            terminal_status=value["terminal_status"],
            endpoint_observation=value["endpoint_observation"],
            typed_missing=value["typed_missing"],
            path_observations=value["path_observations"],
            raw_refs=tuple(ArtifactRef.from_dict(item) for item in value["raw_refs"]),
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


@dataclass(frozen=True, slots=True)
class Review:
    review_id: str
    cycle_id: str
    behavior_plan_ref: ArtifactRef
    outcome_ref: ArtifactRef
    reviewed_at: str
    outcome_status: str
    agent_decision_sha256: str
    projection_status: str
    projection_reason: str | None
    system_facts: Mapping[str, Any]
    agent_review_delivered_at: str
    agent_review_request_sha256: str
    agent_review_delivery_path: str
    agent_review_delivery_sha256: str
    agent_review_text: str
    agent_review_size_bytes: int
    agent_review_sha256: str
    theory_writeback: bool
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.review_id, field_name="review_id")
        _require_nonempty_string(self.cycle_id, field_name="cycle_id")
        reviewed_at = _parse_timestamp(self.reviewed_at, field_name="reviewed_at")
        delivered_at = _parse_timestamp(
            self.agent_review_delivered_at,
            field_name="agent_review_delivered_at",
        )
        if delivered_at != reviewed_at:
            raise MarketCycleContractError(
                "reviewed_at must equal agent_review_delivered_at"
            )
        if not isinstance(self.behavior_plan_ref, ArtifactRef):
            raise MarketCycleContractError("behavior_plan_ref must be ArtifactRef")
        if not isinstance(self.outcome_ref, ArtifactRef):
            raise MarketCycleContractError("outcome_ref must be ArtifactRef")
        if self.behavior_plan_ref.artifact_type != "BehaviorPlan":
            raise MarketCycleContractError("Review must reference BehaviorPlan")
        if self.outcome_ref.artifact_type != "Outcome":
            raise MarketCycleContractError("Review must reference Outcome")
        if self.outcome_status not in {"OBSERVED", "TYPED_MISSING"}:
            raise MarketCycleContractError("Review outcome_status is invalid")
        _require_sha256(
            self.agent_decision_sha256, field_name="agent_decision_sha256"
        )
        if (
            type(self.projection_status) is not str
            or self.projection_status not in AGENT_PROJECTION_STATUSES
        ):
            raise MarketCycleContractError(
                "Review projection_status must be AVAILABLE or UNKNOWN"
            )
        if self.projection_status == "AVAILABLE":
            if self.projection_reason is not None:
                raise MarketCycleContractError(
                    "AVAILABLE Review projection must not contain projection_reason"
                )
        elif self.projection_reason != AGENT_OUTPUT_INCOMPLETE:
            raise MarketCycleContractError(
                "UNKNOWN Review projection requires AGENT_OUTPUT_INCOMPLETE"
            )
        _require_exact_keys(
            self.system_facts,
            required=_REVIEW_SYSTEM_FACT_FIELDS,
            context="Review.system_facts",
        )
        facts = _freeze_json(self.system_facts, path="system_facts")
        if not isinstance(facts, Mapping):
            raise MarketCycleContractError("system_facts must be an object")
        if facts.get("outcome_status") != self.outcome_status:
            raise MarketCycleContractError(
                "system_facts.outcome_status must match Review outcome_status"
            )
        if not isinstance(facts.get("path_observations"), Mapping):
            raise MarketCycleContractError(
                "system_facts.path_observations must be an object"
            )
        raw_fact_refs = facts.get("outcome_raw_refs")
        if not isinstance(raw_fact_refs, tuple) or not all(
            isinstance(item, Mapping) for item in raw_fact_refs
        ):
            raise MarketCycleContractError(
                "system_facts.outcome_raw_refs must be an array of references"
            )
        if self.outcome_status == "OBSERVED":
            if facts.get("typed_missing") is not None or not isinstance(
                facts.get("endpoint_observation"), Mapping
            ):
                raise MarketCycleContractError(
                    "OBSERVED Review facts require endpoint and no typed_missing"
                )
        else:
            if facts.get("endpoint_observation") is not None:
                raise MarketCycleContractError(
                    "TYPED_MISSING Review facts cannot contain endpoint"
                )
            _require_nonempty_string(
                facts.get("typed_missing"),
                field_name="system_facts.typed_missing",
            )
        _require_sha256(
            self.agent_review_request_sha256,
            field_name="agent_review_request_sha256",
        )
        review_delivery_path = _require_cycle_relative_path(
            self.agent_review_delivery_path,
            field_name="agent_review_delivery_path",
        )
        _require_sha256(
            self.agent_review_delivery_sha256,
            field_name="agent_review_delivery_sha256",
        )
        review_raw = _agent_text_bytes(
            self.agent_review_text, field_name="agent_review_text"
        )
        _require_int(
            self.agent_review_size_bytes,
            field_name="agent_review_size_bytes",
            minimum=1,
        )
        if self.agent_review_size_bytes != len(review_raw):
            raise MarketCycleContractError(
                "agent_review_size_bytes does not match verbatim UTF-8 bytes"
            )
        review_sha256 = _require_sha256(
            self.agent_review_sha256, field_name="agent_review_sha256"
        )
        if hashlib.sha256(review_raw).hexdigest() != review_sha256:
            raise MarketCycleContractError(
                "agent_review_sha256 does not match verbatim UTF-8 bytes"
            )
        if self.theory_writeback is not False:
            raise MarketCycleContractError("Review cannot write back into frozen theory")
        object.__setattr__(self, "system_facts", facts)
        object.__setattr__(self, "agent_review_delivery_path", review_delivery_path)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "cycle_id": self.cycle_id,
            "behavior_plan_ref": self.behavior_plan_ref.to_dict(),
            "outcome_ref": self.outcome_ref.to_dict(),
            "reviewed_at": self.reviewed_at,
            "outcome_status": self.outcome_status,
            "agent_decision_sha256": self.agent_decision_sha256,
            "projection_status": self.projection_status,
            "projection_reason": self.projection_reason,
            "system_facts": _thaw_json(self.system_facts),
            "agent_review_delivered_at": self.agent_review_delivered_at,
            "agent_review_request_sha256": self.agent_review_request_sha256,
            "agent_review_delivery_path": self.agent_review_delivery_path,
            "agent_review_delivery_sha256": self.agent_review_delivery_sha256,
            "agent_review_text": self.agent_review_text,
            "agent_review_size_bytes": self.agent_review_size_bytes,
            "agent_review_sha256": self.agent_review_sha256,
            "theory_writeback": False,
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Review":
        fields = frozenset(
            {
                "review_id",
                "cycle_id",
                "behavior_plan_ref",
                "outcome_ref",
                "reviewed_at",
                "outcome_status",
                "agent_decision_sha256",
                "projection_status",
                "projection_reason",
                "system_facts",
                "agent_review_delivered_at",
                "agent_review_request_sha256",
                "agent_review_delivery_path",
                "agent_review_delivery_sha256",
                "agent_review_text",
                "agent_review_size_bytes",
                "agent_review_sha256",
                "theory_writeback",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="Review")
        return cls(
            review_id=value["review_id"],
            cycle_id=value["cycle_id"],
            behavior_plan_ref=ArtifactRef.from_dict(value["behavior_plan_ref"]),
            outcome_ref=ArtifactRef.from_dict(value["outcome_ref"]),
            reviewed_at=value["reviewed_at"],
            outcome_status=value["outcome_status"],
            agent_decision_sha256=value["agent_decision_sha256"],
            projection_status=value["projection_status"],
            projection_reason=value["projection_reason"],
            system_facts=value["system_facts"],
            agent_review_delivered_at=value["agent_review_delivered_at"],
            agent_review_request_sha256=value["agent_review_request_sha256"],
            agent_review_delivery_path=value["agent_review_delivery_path"],
            agent_review_delivery_sha256=value["agent_review_delivery_sha256"],
            agent_review_text=value["agent_review_text"],
            agent_review_size_bytes=value["agent_review_size_bytes"],
            agent_review_sha256=value["agent_review_sha256"],
            theory_writeback=value["theory_writeback"],
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


@dataclass(frozen=True, slots=True)
class RunState:
    cycle_id: str
    stage: str
    revision: int
    artifact_refs: tuple[ArtifactRef, ...]
    next_action: str | None
    terminal: bool
    failure_reason: str | None
    theory_identity: TheoryIdentity = field(default=CURRENT_THEORY_IDENTITY)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.cycle_id, field_name="cycle_id")
        if self.stage not in set(RUN_STAGES) | RUN_FAILURE_STAGES:
            raise MarketCycleContractError("unsupported RunState stage")
        _require_int(self.revision, field_name="revision", minimum=0)
        references = tuple(self.artifact_refs)
        if not all(isinstance(reference, ArtifactRef) for reference in references):
            raise MarketCycleContractError("RunState.artifact_refs must contain ArtifactRef values")
        reference_types = tuple(reference.artifact_type for reference in references)
        if len(reference_types) != len(set(reference_types)):
            raise MarketCycleContractError("RunState may reference each artifact type once")
        if self.stage in _EXPECTED_ARTIFACTS_BY_STAGE:
            expected = _EXPECTED_ARTIFACTS_BY_STAGE[self.stage]
            if reference_types != expected:
                raise MarketCycleContractError(
                    f"RunState {self.stage} expects artifact refs {expected!r}"
                )
            expected_next = RUN_NEXT_ACTION[self.stage]
            expected_terminal = self.stage == "COMPLETE"
            if self.next_action != expected_next or self.terminal is not expected_terminal:
                raise MarketCycleContractError("RunState next_action/terminal projection mismatch")
            if self.failure_reason is not None:
                raise MarketCycleContractError("non-failure RunState cannot have failure_reason")
        else:
            valid_prefixes = tuple(
                _EXPECTED_ARTIFACTS_BY_STAGE[stage]
                for stage in RUN_STAGES
                if len(_EXPECTED_ARTIFACTS_BY_STAGE[stage]) == len(reference_types)
            )
            if reference_types not in valid_prefixes:
                raise MarketCycleContractError("failure RunState contains an invalid artifact prefix")
            if self.next_action is not None or self.terminal is not True:
                raise MarketCycleContractError("failure RunState must be terminal with no next action")
            _require_nonempty_string(self.failure_reason, field_name="failure_reason")
        object.__setattr__(self, "artifact_refs", references)
        require_supported_theory_identity(self.theory_identity)

    def to_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "stage": self.stage,
            "revision": self.revision,
            "artifact_refs": [reference.to_dict() for reference in self.artifact_refs],
            "next_action": self.next_action,
            "terminal": self.terminal,
            "failure_reason": self.failure_reason,
            "theory_identity": _theory_to_dict(self.theory_identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunState":
        fields = frozenset(
            {
                "cycle_id",
                "stage",
                "revision",
                "artifact_refs",
                "next_action",
                "terminal",
                "failure_reason",
                "theory_identity",
            }
        )
        _require_exact_keys(value, required=fields, context="RunState")
        return cls(
            cycle_id=value["cycle_id"],
            stage=value["stage"],
            revision=value["revision"],
            artifact_refs=tuple(
                ArtifactRef.from_dict(item) for item in value["artifact_refs"]
            ),
            next_action=value["next_action"],
            terminal=value["terminal"],
            failure_reason=value["failure_reason"],
            theory_identity=_theory_from_dict(value["theory_identity"]),
        )


def validate_run_state_transition(previous: RunState, current: RunState) -> None:
    """Validate a transition proposed by the Application-owned CycleService.

    This pure guard deliberately does not create or persist a new state.  The
    Application layer is the logical state owner; the repository only performs
    exclusive compare-and-store of a transition that has passed this guard.
    """

    if previous.terminal:
        raise MarketCycleContractError("terminal RunState cannot advance")
    if previous.cycle_id != current.cycle_id:
        raise MarketCycleContractError("RunState transition cannot change cycle_id")
    if previous.theory_identity != current.theory_identity:
        raise MarketCycleContractError("RunState transition cannot change theory identity")
    if current.revision != previous.revision + 1:
        raise MarketCycleContractError("RunState revision must advance exactly once")
    if current.stage not in ALLOWED_RUN_STATE_TRANSITIONS[previous.stage]:
        raise MarketCycleContractError(
            f"illegal RunState transition {previous.stage} -> {current.stage}"
        )
    previous_refs = previous.artifact_refs
    if current.artifact_refs[: len(previous_refs)] != previous_refs:
        raise MarketCycleContractError("RunState transition cannot replace prior artifact refs")
    if len(current.artifact_refs) - len(previous_refs) not in {0, 1}:
        raise MarketCycleContractError("one transition may add at most one business artifact")
    if current.stage in RUN_FAILURE_STAGES and current.artifact_refs != previous_refs:
        raise MarketCycleContractError(
            "failure transition cannot smuggle in an unsealed business artifact"
        )
