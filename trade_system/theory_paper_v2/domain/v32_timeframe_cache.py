"""Pure V3.2 multi-timeframe context and cache-transition contracts.

The contract makes the first cycle a complete context build and later cycles
bounded delta updates.  A slow strategic frame may be carried forward only
while it is point-in-time valid, unexpired, and untouched by a newly available
invalidation event.  The module owns no files, clocks, sources, Agent calls,
portfolio state, or execution.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest


class V32TimeframeCacheError(ValueError):
    """A V3.2 timeframe or cache-continuity invariant failed closed."""


SCHEMA_ID = "theory_paper_v32_timeframe_context_state_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "timeframe_context_state_digest"

FRAME_ROLES = ("STRATEGIC_CONTEXT", "TACTICAL_DELTA", "TRIGGER")
FRAME_UPDATE_MODES = ("REFRESHED", "CARRIED_FORWARD")
STATE_MODES = ("FULL_CONTEXT", "DELTA_UPDATE")
INVALIDATION_EVENT_TYPES = (
    "MACRO_POLICY_RELEASE",
    "REGULATORY_CHANGE",
    "SOURCE_SCHEMA_DRIFT",
    "SOURCE_REVISION",
    "EXTREME_VOLATILITY",
    "CROSS_ASSET_REGIME_BREAK",
    "STRATEGIC_TTL_EXPIRED",
    "AUTHORIZED_FORCED_REBUILD",
)

# This is the single owner of the production REFRESHED-frame policy.  Adapters
# may project it, but must not redefine TTLs, dependency groups, or invalidators.
_PRODUCTION_FRAME_SPECS = {
    "STRATEGIC_CONTEXT": {
        "ttl_seconds": 86_400,
        "dependency_groups": (
            "MULTI_TIMEFRAME_PRICE",
            "PUBLIC_EVENT_AND_REGIME",
        ),
        "invalidation_event_types": (
            "AUTHORIZED_FORCED_REBUILD",
            "CROSS_ASSET_REGIME_BREAK",
            "EXTREME_VOLATILITY",
            "MACRO_POLICY_RELEASE",
            "REGULATORY_CHANGE",
            "SOURCE_REVISION",
            "SOURCE_SCHEMA_DRIFT",
            "STRATEGIC_TTL_EXPIRED",
        ),
    },
    "TACTICAL_DELTA": {
        "ttl_seconds": 3_600,
        "dependency_groups": (
            "DERIVATIVES_AND_LIQUIDITY",
            "TACTICAL_PRICE",
        ),
        "invalidation_event_types": (
            "EXTREME_VOLATILITY",
            "SOURCE_REVISION",
        ),
    },
    "TRIGGER": {
        "ttl_seconds": 900,
        "dependency_groups": ("PUBLIC_TRIGGER_AND_MARKET_MICROSTRUCTURE",),
        "invalidation_event_types": (
            "EXTREME_VOLATILITY",
            "SOURCE_SCHEMA_DRIFT",
        ),
    },
}

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_FRAME_FIELDS = frozenset(
    {
        "frame_id",
        "role",
        "update_mode",
        "created_at",
        "as_of",
        "available_at",
        "expires_at",
        "payload_digest",
        "source_refs",
        "dependency_groups",
        "invalidation_event_types",
        "previous_frame_digest",
        "frame_digest",
    }
)
_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "occurred_at",
        "available_at",
        "evidence_refs",
    }
)
_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_time",
        "state_mode",
        "previous_state_digest",
        "frames",
        "observed_invalidation_events",
        "strategic_rebuild_required",
        "analysis_clock_interval_seconds",
        "target_delta_processing_seconds",
        "point_in_time_policy",
        "cache_policy",
        "source_scope",
        "external_execution_authority",
        "executable",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32TimeframeCacheError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32TimeframeCacheError(code) from exc
    if parsed.tzinfo is None:
        raise V32TimeframeCacheError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32TimeframeCacheError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32TimeframeCacheError(code)
    return value


def _strings(value: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32TimeframeCacheError(code)
    rows = [_text(row, code) for row in value]
    if (not allow_empty and not rows) or len(rows) != len(set(rows)):
        raise V32TimeframeCacheError(code)
    return sorted(rows)


def _positive_int(value: Any, code: str, *, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        raise V32TimeframeCacheError(code)
    return value


def _series_subset(
    series: Mapping[str, Any], *tokens: str
) -> dict[str, Any]:
    return {
        str(key): deepcopy(value)
        for key, value in sorted(series.items())
        if any(token in str(key).upper() for token in tokens)
    }


def project_v32_timeframe_source_refs_v1(
    public_market_analysis_bundle: Mapping[str, Any],
) -> list[str]:
    """Project the exact production raw-source references from a verified bundle.

    The public-market bundle remains owned by its public-evidence module.  The
    caller must run that owning verifier first; this pure function only performs
    the deterministic cross-module projection used by timeframe construction
    and replay.
    """

    code = "V32_CACHE_PUBLIC_BUNDLE_SOURCE_REFS_INVALID"
    if not isinstance(public_market_analysis_bundle, Mapping):
        raise V32TimeframeCacheError(code)
    try:
        aggregate = public_market_analysis_bundle["aggregate_raw_binding"]
        request_bindings = public_market_analysis_bundle["request_raw_bindings"]
        if (
            not isinstance(aggregate, Mapping)
            or isinstance(request_bindings, (str, bytes))
            or not isinstance(request_bindings, Sequence)
        ):
            raise V32TimeframeCacheError(code)
        refs = {_text(aggregate.get("relative_ref"), code)}
        for row in request_bindings:
            if not isinstance(row, Mapping):
                raise V32TimeframeCacheError(code)
            raw_binding = row.get("raw_binding")
            if raw_binding is None:
                continue
            if not isinstance(raw_binding, Mapping):
                raise V32TimeframeCacheError(code)
            refs.add(_text(raw_binding.get("relative_ref"), code))
        return sorted(refs)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TimeframeCacheError):
            raise
        raise V32TimeframeCacheError(code) from exc


def project_v32_refreshed_frame_policy_v1(
    *,
    role: str,
    run_id: str,
    decision_time: str,
    public_market_analysis_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Project all non-payload fields fixed for one production REFRESHED frame."""

    code = "V32_CACHE_PRODUCTION_FRAME_POLICY_INVALID"
    normalized_role = _text(role, code)
    if normalized_role not in FRAME_ROLES:
        raise V32TimeframeCacheError(code)
    run = _text(run_id, code)
    decision = _moment(decision_time, code)
    if not isinstance(public_market_analysis_bundle, Mapping):
        raise V32TimeframeCacheError(code)
    try:
        spec = _PRODUCTION_FRAME_SPECS[normalized_role]
        as_of = _time(public_market_analysis_bundle["as_of"], code)
        available_at = _time(public_market_analysis_bundle["available_at"], code)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TimeframeCacheError):
            raise
        raise V32TimeframeCacheError(code) from exc
    expires_at = (
        decision + timedelta(seconds=int(spec["ttl_seconds"]))
    ).isoformat().replace("+00:00", "Z")
    return {
        "frame_id": f"v32:{run}:{normalized_role.lower()}",
        "created_at": _time(decision_time, code),
        "as_of": as_of,
        "available_at": available_at,
        "expires_at": expires_at,
        "source_refs": project_v32_timeframe_source_refs_v1(
            public_market_analysis_bundle
        ),
        "dependency_groups": sorted(spec["dependency_groups"]),
        "invalidation_event_types": sorted(spec["invalidation_event_types"]),
    }


def verify_v32_timeframe_production_policy_v1(
    *,
    timeframe_context_state: Mapping[str, Any],
    public_market_analysis_bundle: Mapping[str, Any],
) -> str:
    """Bind every REFRESHED frame to the one frozen production policy.

    A CARRIED_FORWARD frame is accepted here only for STRATEGIC_CONTEXT.  Its
    immutable fields intentionally remain bound to the exact predecessor by the
    transition verifier, rather than being rewritten to the current bundle.
    Callers replaying a delta must therefore verify that transition first.
    """

    supplied = _verify_state_shape_and_digest(timeframe_context_state)
    if not isinstance(public_market_analysis_bundle, Mapping):
        raise V32TimeframeCacheError(
            "V32_CACHE_PRODUCTION_POLICY_PUBLIC_BUNDLE_INVALID"
        )
    if (
        public_market_analysis_bundle.get("run_id")
        != timeframe_context_state.get("run_id")
        or public_market_analysis_bundle.get("cycle_index")
        != timeframe_context_state.get("cycle_index")
    ):
        raise V32TimeframeCacheError(
            "V32_CACHE_PRODUCTION_POLICY_PUBLIC_BUNDLE_SCOPE_INVALID"
        )
    frames = {row["role"]: row for row in timeframe_context_state["frames"]}
    for role in FRAME_ROLES:
        frame = frames[role]
        if frame["update_mode"] == "CARRIED_FORWARD":
            if role != "STRATEGIC_CONTEXT":
                raise V32TimeframeCacheError(
                    f"V32_CACHE_PRODUCTION_POLICY_CARRY_INVALID:{role}"
                )
            continue
        expected = project_v32_refreshed_frame_policy_v1(
            role=role,
            run_id=timeframe_context_state["run_id"],
            decision_time=timeframe_context_state["decision_time"],
            public_market_analysis_bundle=public_market_analysis_bundle,
        )
        if any(frame.get(field) != value for field, value in expected.items()):
            raise V32TimeframeCacheError(
                f"V32_CACHE_PRODUCTION_FRAME_POLICY_MISMATCH:{role}"
            )
    return supplied


def project_v32_timeframe_payloads_v1(
    public_market_analysis_bundle: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Project the exact three frame payloads from one verified public bundle.

    The caller must first run the owning public-bundle verifier.  Keeping this
    pure projection in Domain lets both the producer and final acceptance
    independently bind every frame to the same current market material.
    """

    code = "V32_CACHE_PUBLIC_BUNDLE_PROJECTION_INVALID"
    if not isinstance(public_market_analysis_bundle, Mapping):
        raise V32TimeframeCacheError(code)
    try:
        bundle_digest = _digest(
            public_market_analysis_bundle["public_market_analysis_bundle_digest"],
            code,
        )
        series = public_market_analysis_bundle["closed_bar_series"]
        axis_evidence = public_market_analysis_bundle["axis_source_evidence"]
        request_bindings = public_market_analysis_bundle["request_raw_bindings"]
        if (
            not isinstance(series, Mapping)
            or isinstance(axis_evidence, (str, bytes))
            or not isinstance(axis_evidence, Sequence)
            or isinstance(request_bindings, (str, bytes))
            or not isinstance(request_bindings, Sequence)
        ):
            raise V32TimeframeCacheError(code)
        axis_rows: list[dict[str, Any]] = []
        for row in axis_evidence:
            if not isinstance(row, Mapping):
                raise V32TimeframeCacheError(code)
            axis_rows.append(
                {
                    key: deepcopy(value)
                    for key, value in sorted(row.items())
                    if key
                    not in {
                        "observed_at",
                        "available_at",
                        "raw_bundle_sha256",
                        "axis_source_evidence_digest",
                    }
                }
            )
        coverage: list[dict[str, Any]] = []
        for row in request_bindings:
            if not isinstance(row, Mapping):
                raise V32TimeframeCacheError(code)
            coverage.append(
                {
                    "component_id": row["component_id"],
                    "status": row["status"],
                    "error_code": row["error_code"],
                }
            )
        return {
            "STRATEGIC_CONTEXT": {
                "axis_source_registry_digest": public_market_analysis_bundle[
                    "axis_source_registry_digest"
                ],
                "axis_semantics": axis_rows,
                "source_coverage": coverage,
                "slow_series": _series_subset(series, "4H", "1D", "24H"),
            },
            "TACTICAL_DELTA": {
                "bundle_digest": bundle_digest,
                "datums": deepcopy(public_market_analysis_bundle["datums"]),
                "tactical_series": _series_subset(series, "15M", "1H", "60M"),
            },
            "TRIGGER": {
                "bundle_digest": bundle_digest,
                "request_raw_bindings": deepcopy(request_bindings),
                "fast_series": _series_subset(series, "1M", "5M", "15M"),
                "as_of": public_market_analysis_bundle["as_of"],
            },
        }
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32TimeframeCacheError):
            raise
        raise V32TimeframeCacheError(code) from exc


def verify_v32_timeframe_payload_bindings_v1(
    *,
    timeframe_context_state: Mapping[str, Any],
    public_market_analysis_bundle: Mapping[str, Any],
) -> dict[str, str]:
    """Verify that every accepted frame is derived from the current bundle."""

    _verify_state_shape_and_digest(timeframe_context_state)
    payloads = project_v32_timeframe_payloads_v1(public_market_analysis_bundle)
    frames = {
        row["role"]: row
        for row in timeframe_context_state["frames"]
        if isinstance(row, Mapping) and row.get("role") in FRAME_ROLES
    }
    if set(frames) != set(FRAME_ROLES):
        raise V32TimeframeCacheError("V32_CACHE_FRAME_ROLE_SET_INVALID")
    expected = {role: canonical_digest(payloads[role]) for role in FRAME_ROLES}
    for role in FRAME_ROLES:
        if frames[role].get("payload_digest") != expected[role]:
            raise V32TimeframeCacheError(
                f"V32_CACHE_FRAME_PAYLOAD_BINDING_MISMATCH:{role}"
            )
    return expected


def verify_v32_timeframe_invalidation_bindings_v1(
    *,
    timeframe_context_state: Mapping[str, Any],
    public_market_analysis_bundle: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None,
) -> None:
    """Bind typed invalidations to current PIT evidence or the prior TTL."""

    _verify_state_shape_and_digest(timeframe_context_state)
    run_id = timeframe_context_state["run_id"]
    cycle = timeframe_context_state["cycle_index"]
    events = timeframe_context_state["observed_invalidation_events"]
    try:
        pit_members = set(public_market_analysis_bundle["pit_member_digests"])
    except (KeyError, TypeError) as exc:
        raise V32TimeframeCacheError(
            "V32_CACHE_INVALIDATION_SOURCE_BUNDLE_INVALID"
        ) from exc
    if any(_HEX_64.fullmatch(str(value)) is None for value in pit_members):
        raise V32TimeframeCacheError(
            "V32_CACHE_INVALIDATION_SOURCE_BUNDLE_INVALID"
        )
    prior_strategic: Mapping[str, Any] | None = None
    if previous_state is not None:
        _verify_state_shape_and_digest(previous_state)
        if (
            previous_state.get("run_id") != run_id
            or previous_state.get("cycle_index") != cycle - 1
        ):
            raise V32TimeframeCacheError(
                "V32_CACHE_INVALIDATION_PREVIOUS_STATE_INVALID"
            )
        prior_strategic = next(
            row
            for row in previous_state["frames"]
            if row["role"] == "STRATEGIC_CONTEXT"
        )
    for event in events:
        if event["event_type"] == "STRATEGIC_TTL_EXPIRED":
            expected_id = f"v32:{run_id}:strategic-ttl-expired:{cycle:04d}"
            if (
                prior_strategic is None
                or event["event_id"] != expected_id
                or event["occurred_at"] != prior_strategic["expires_at"]
                or event["available_at"] != prior_strategic["expires_at"]
                or event["evidence_refs"] != [prior_strategic["frame_digest"]]
            ):
                raise V32TimeframeCacheError(
                    "V32_CACHE_TTL_INVALIDATION_BINDING_INVALID"
                )
            continue
        # Current production has no owning source schema that can prove that a
        # PIT member semantically represents the claimed macro/regulatory/etc.
        # Reject such injection instead of accepting a digest-only label.
        raise V32TimeframeCacheError(
            "V32_CACHE_EXTERNAL_INVALIDATION_SOURCE_UNQUALIFIED"
        )


def _event(row: Any, *, decision_time: datetime) -> dict[str, Any]:
    code = "V32_CACHE_INVALIDATION_EVENT_INVALID"
    if not isinstance(row, Mapping) or set(row) != _EVENT_FIELDS:
        raise V32TimeframeCacheError(code)
    event_type = _text(row["event_type"], code)
    if event_type not in INVALIDATION_EVENT_TYPES:
        raise V32TimeframeCacheError(code)
    occurred = _moment(row["occurred_at"], code)
    available = _moment(row["available_at"], code)
    if occurred > available or available > decision_time:
        raise V32TimeframeCacheError("V32_CACHE_INVALIDATION_EVENT_TIME_INVALID")
    return {
        "event_id": _text(row["event_id"], code),
        "event_type": event_type,
        "occurred_at": _time(row["occurred_at"], code),
        "available_at": _time(row["available_at"], code),
        "evidence_refs": _strings(row["evidence_refs"], code),
    }


def _frame(
    row: Any,
    *,
    decision_time: datetime,
    previous_frame: Mapping[str, Any] | None,
    allow_unresolved_predecessor: bool = False,
) -> dict[str, Any]:
    code = "V32_CACHE_FRAME_INVALID"
    if not isinstance(row, Mapping) or set(row) != _FRAME_FIELDS:
        raise V32TimeframeCacheError(code)
    role = _text(row["role"], code)
    update_mode = _text(row["update_mode"], code)
    if role not in FRAME_ROLES or update_mode not in FRAME_UPDATE_MODES:
        raise V32TimeframeCacheError(code)
    created = _moment(row["created_at"], code)
    as_of = _moment(row["as_of"], code)
    available = _moment(row["available_at"], code)
    expires = _moment(row["expires_at"], code)
    if not (as_of <= available <= created <= decision_time < expires):
        raise V32TimeframeCacheError("V32_CACHE_FRAME_TIME_INVALID")
    invalidation_types = _strings(
        row["invalidation_event_types"], code, allow_empty=role != "STRATEGIC_CONTEXT"
    )
    if any(item not in INVALIDATION_EVENT_TYPES for item in invalidation_types):
        raise V32TimeframeCacheError(code)
    if role == "STRATEGIC_CONTEXT" and not invalidation_types:
        raise V32TimeframeCacheError("V32_CACHE_STRATEGIC_INVALIDATORS_REQUIRED")

    normalized = {
        "frame_id": _text(row["frame_id"], code),
        "role": role,
        "update_mode": update_mode,
        "created_at": _time(row["created_at"], code),
        "as_of": _time(row["as_of"], code),
        "available_at": _time(row["available_at"], code),
        "expires_at": _time(row["expires_at"], code),
        "payload_digest": _digest(row["payload_digest"], code),
        "source_refs": _strings(row["source_refs"], code),
        "dependency_groups": _strings(row["dependency_groups"], code),
        "invalidation_event_types": invalidation_types,
        "previous_frame_digest": _digest(
            row["previous_frame_digest"], code, nullable=True
        ),
    }

    if update_mode == "CARRIED_FORWARD":
        if role != "STRATEGIC_CONTEXT":
            raise V32TimeframeCacheError("V32_CACHE_CARRY_FORWARD_INVALID")
        if previous_frame is None and not allow_unresolved_predecessor:
            raise V32TimeframeCacheError("V32_CACHE_CARRY_FORWARD_INVALID")
        if previous_frame is None:
            if normalized["previous_frame_digest"] is None:
                raise V32TimeframeCacheError(
                    "V32_CACHE_CARRY_FORWARD_BINDING_INVALID"
                )
        else:
            previous_digest = _digest(
                previous_frame.get("frame_digest"), "V32_CACHE_CARRY_FORWARD_INVALID"
            )
            if normalized["previous_frame_digest"] != previous_digest:
                raise V32TimeframeCacheError("V32_CACHE_CARRY_FORWARD_BINDING_INVALID")
            immutable_fields = (
                "frame_id",
                "role",
                "created_at",
                "as_of",
                "available_at",
                "expires_at",
                "payload_digest",
                "source_refs",
                "dependency_groups",
                "invalidation_event_types",
            )
            if any(
                normalized[name] != previous_frame.get(name) for name in immutable_fields
            ):
                raise V32TimeframeCacheError("V32_CACHE_CARRY_FORWARD_MUTATION")
    else:
        if previous_frame is None:
            if (
                normalized["previous_frame_digest"] is not None
                and not allow_unresolved_predecessor
            ):
                raise V32TimeframeCacheError("V32_CACHE_REFRESH_BINDING_INVALID")
        else:
            if normalized["previous_frame_digest"] != previous_frame.get("frame_digest"):
                raise V32TimeframeCacheError("V32_CACHE_REFRESH_BINDING_INVALID")
            if created < _moment(previous_frame["created_at"], code):
                raise V32TimeframeCacheError("V32_CACHE_REFRESH_TIME_REGRESSION")

    expected_frame_digest = canonical_digest(normalized)
    if row["frame_digest"] != expected_frame_digest:
        raise V32TimeframeCacheError("V32_CACHE_FRAME_DIGEST_INVALID")
    normalized["frame_digest"] = expected_frame_digest
    return normalized


def _verify_state_shape_and_digest(document: Mapping[str, Any]) -> str:
    """Validate one state's intrinsic bytes without claiming chain continuity."""

    if not isinstance(document, Mapping) or set(document) != _STATE_FIELDS:
        raise V32TimeframeCacheError("V32_CACHE_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32TimeframeCacheError("V32_CACHE_DOCUMENT_DIGEST_INVALID") from exc
    if (
        document.get("schema_id") != SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("state_mode") not in STATE_MODES
        or document.get("point_in_time_policy")
        != "FRAME_AS_OF_LE_AVAILABLE_LE_CREATED_LE_DECISION_LT_EXPIRES"
        or document.get("cache_policy")
        != "FULL_GENESIS_FAST_FRAMES_REFRESH_EACH_DELTA_STRATEGIC_CARRY_UNTIL_TTL_OR_EVENT"
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V32TimeframeCacheError("V32_CACHE_DOCUMENT_INVALID")
    _text(document.get("run_id"), "V32_CACHE_RUN_ID_INVALID")
    cycle = _positive_int(
        document.get("cycle_index"), "V32_CACHE_CYCLE_INVALID", upper=1_000_000
    )
    decision = _moment(document.get("decision_time"), "V32_CACHE_DECISION_TIME_INVALID")
    interval = _positive_int(
        document.get("analysis_clock_interval_seconds"),
        "V32_CACHE_ANALYSIS_INTERVAL_INVALID",
        upper=86_400,
    )
    processing = _positive_int(
        document.get("target_delta_processing_seconds"),
        "V32_CACHE_PROCESSING_TARGET_INVALID",
        upper=interval,
    )
    if interval != 900 or processing > 120:
        raise V32TimeframeCacheError("V32_CACHE_FROZEN_SPEED_POLICY_INVALID")
    previous_digest = _digest(
        document.get("previous_state_digest"),
        "V32_CACHE_PREVIOUS_DIGEST_INVALID",
        nullable=True,
    )
    if (cycle == 1) != (previous_digest is None):
        raise V32TimeframeCacheError("V32_CACHE_PREVIOUS_DIGEST_INVALID")
    if (cycle == 1 and document.get("state_mode") != "FULL_CONTEXT") or (
        cycle > 1 and document.get("state_mode") != "DELTA_UPDATE"
    ):
        raise V32TimeframeCacheError("V32_CACHE_STATE_MODE_INVALID")
    frames = [
        _frame(
            row,
            decision_time=decision,
            previous_frame=None,
            allow_unresolved_predecessor=cycle > 1,
        )
        for row in document.get("frames", ())
    ]
    roles = [row["role"] for row in frames]
    if set(roles) != set(FRAME_ROLES) or len(roles) != len(set(roles)):
        raise V32TimeframeCacheError("V32_CACHE_FRAME_ROLE_SET_INVALID")
    frame_by_role = {row["role"]: row for row in frames}
    if cycle == 1 and any(row["update_mode"] != "REFRESHED" for row in frames):
        raise V32TimeframeCacheError("V32_CACHE_GENESIS_REFRESH_REQUIRED")
    if cycle > 1 and any(
        frame_by_role[role]["update_mode"] != "REFRESHED"
        for role in ("TACTICAL_DELTA", "TRIGGER")
    ):
        raise V32TimeframeCacheError("V32_CACHE_FAST_FRAME_REFRESH_REQUIRED")
    events = [
        _event(row, decision_time=decision)
        for row in document.get("observed_invalidation_events", ())
    ]
    event_ids = [row["event_id"] for row in events]
    if len(event_ids) != len(set(event_ids)):
        raise V32TimeframeCacheError("V32_CACHE_INVALIDATION_EVENT_DUPLICATE")
    if not isinstance(document.get("strategic_rebuild_required"), bool):
        raise V32TimeframeCacheError("V32_CACHE_REBUILD_FLAG_INVALID")
    return supplied


def build_v32_context_frame_v1(
    *,
    frame_id: str,
    role: str,
    update_mode: str,
    created_at: str,
    as_of: str,
    available_at: str,
    expires_at: str,
    payload_digest: str,
    source_refs: Sequence[str],
    dependency_groups: Sequence[str],
    invalidation_event_types: Sequence[str],
    previous_frame: Mapping[str, Any] | None,
    decision_time: str,
) -> dict[str, Any]:
    """Build one exact frame with its own semantic digest."""

    code = "V32_CACHE_FRAME_INVALID"
    candidate = {
        "frame_id": _text(frame_id, code),
        "role": _text(role, code),
        "update_mode": _text(update_mode, code),
        "created_at": _time(created_at, code),
        "as_of": _time(as_of, code),
        "available_at": _time(available_at, code),
        "expires_at": _time(expires_at, code),
        "payload_digest": _digest(payload_digest, code),
        "source_refs": _strings(source_refs, code),
        "dependency_groups": _strings(dependency_groups, code),
        "invalidation_event_types": _strings(
            invalidation_event_types,
            code,
            allow_empty=role != "STRATEGIC_CONTEXT",
        ),
        "previous_frame_digest": (
            None if previous_frame is None else previous_frame.get("frame_digest")
        ),
    }
    candidate["frame_digest"] = canonical_digest(candidate)
    return _frame(
        candidate,
        decision_time=_moment(decision_time, "V32_CACHE_DECISION_TIME_INVALID"),
        previous_frame=previous_frame,
    )


def build_v32_timeframe_context_state_v1(
    *,
    run_id: str,
    cycle_index: int,
    decision_time: str,
    state_mode: str,
    previous_state: Mapping[str, Any] | None,
    frames: Sequence[Mapping[str, Any]],
    observed_invalidation_events: Sequence[Mapping[str, Any]],
    analysis_clock_interval_seconds: int = 900,
    target_delta_processing_seconds: int = 120,
) -> dict[str, Any]:
    """Build one full-context or delta-context cache state."""

    run = _text(run_id, "V32_CACHE_RUN_ID_INVALID")
    cycle = _positive_int(cycle_index, "V32_CACHE_CYCLE_INVALID", upper=1_000_000)
    if state_mode not in STATE_MODES:
        raise V32TimeframeCacheError("V32_CACHE_STATE_MODE_INVALID")
    decision_text = _time(decision_time, "V32_CACHE_DECISION_TIME_INVALID")
    decision = _moment(decision_text, "V32_CACHE_DECISION_TIME_INVALID")
    interval = _positive_int(
        analysis_clock_interval_seconds,
        "V32_CACHE_ANALYSIS_INTERVAL_INVALID",
        upper=86_400,
    )
    processing = _positive_int(
        target_delta_processing_seconds,
        "V32_CACHE_PROCESSING_TARGET_INVALID",
        upper=interval,
    )
    if interval != 900 or processing > 120:
        raise V32TimeframeCacheError("V32_CACHE_FROZEN_SPEED_POLICY_INVALID")

    previous_digest: str | None = None
    previous_frames: dict[str, Mapping[str, Any]] = {}
    if cycle == 1:
        if state_mode != "FULL_CONTEXT" or previous_state is not None:
            raise V32TimeframeCacheError("V32_CACHE_GENESIS_INVALID")
    else:
        if state_mode != "DELTA_UPDATE" or previous_state is None:
            raise V32TimeframeCacheError("V32_CACHE_DELTA_PREVIOUS_REQUIRED")
        try:
            previous_digest = _verify_state_shape_and_digest(previous_state)
        except (TypeError, ValueError) as exc:
            raise V32TimeframeCacheError("V32_CACHE_PREVIOUS_STATE_INVALID") from exc
        if (
            previous_state.get("run_id") != run
            or previous_state.get("cycle_index") != cycle - 1
            or _moment(previous_state.get("decision_time"), "V32_CACHE_PREVIOUS_TIME_INVALID")
            >= decision
        ):
            raise V32TimeframeCacheError("V32_CACHE_PREVIOUS_CONTINUITY_INVALID")
        previous_frames = {row["role"]: row for row in previous_state["frames"]}

    normalized_events = [_event(row, decision_time=decision) for row in observed_invalidation_events]
    event_ids = [row["event_id"] for row in normalized_events]
    if len(event_ids) != len(set(event_ids)):
        raise V32TimeframeCacheError("V32_CACHE_INVALIDATION_EVENT_DUPLICATE")

    normalized_frames = [
        _frame(
            row,
            decision_time=decision,
            previous_frame=previous_frames.get(row.get("role")) if previous_frames else None,
        )
        for row in frames
    ]
    roles = [row["role"] for row in normalized_frames]
    if set(roles) != set(FRAME_ROLES) or len(roles) != len(set(roles)):
        raise V32TimeframeCacheError("V32_CACHE_FRAME_ROLE_SET_INVALID")
    frame_by_role = {row["role"]: row for row in normalized_frames}

    if cycle == 1 and any(row["update_mode"] != "REFRESHED" for row in normalized_frames):
        raise V32TimeframeCacheError("V32_CACHE_GENESIS_REFRESH_REQUIRED")
    if cycle > 1 and any(
        frame_by_role[role]["update_mode"] != "REFRESHED"
        for role in ("TACTICAL_DELTA", "TRIGGER")
    ):
        raise V32TimeframeCacheError("V32_CACHE_FAST_FRAME_REFRESH_REQUIRED")

    strategic = frame_by_role["STRATEGIC_CONTEXT"]
    triggering_events = [
        row
        for row in normalized_events
        if row["event_type"] in strategic["invalidation_event_types"]
        and (
            cycle == 1
            or _moment(row["available_at"], "V32_CACHE_INVALIDATION_EVENT_TIME_INVALID")
            > _moment(previous_state["decision_time"], "V32_CACHE_PREVIOUS_TIME_INVALID")
        )
    ]
    rebuild_required = bool(triggering_events)
    if strategic["update_mode"] == "CARRIED_FORWARD" and rebuild_required:
        raise V32TimeframeCacheError("V32_CACHE_STALE_STRATEGIC_CARRY_FORBIDDEN")
    if strategic["update_mode"] == "REFRESHED" and triggering_events:
        latest_available = max(
            _moment(row["available_at"], "V32_CACHE_INVALIDATION_EVENT_TIME_INVALID")
            for row in triggering_events
        )
        if _moment(strategic["created_at"], "V32_CACHE_FRAME_TIME_INVALID") < latest_available:
            raise V32TimeframeCacheError("V32_CACHE_STRATEGIC_REFRESH_PRECEDES_INVALIDATION")

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle,
        "decision_time": decision_text,
        "state_mode": state_mode,
        "previous_state_digest": previous_digest,
        "frames": sorted(normalized_frames, key=lambda row: FRAME_ROLES.index(row["role"])),
        "observed_invalidation_events": sorted(
            normalized_events, key=lambda row: (row["available_at"], row["event_id"])
        ),
        "strategic_rebuild_required": rebuild_required,
        "analysis_clock_interval_seconds": interval,
        "target_delta_processing_seconds": processing,
        "point_in_time_policy": "FRAME_AS_OF_LE_AVAILABLE_LE_CREATED_LE_DECISION_LT_EXPIRES",
        "cache_policy": "FULL_GENESIS_FAST_FRAMES_REFRESH_EACH_DELTA_STRATEGIC_CARRY_UNTIL_TTL_OR_EVENT",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_timeframe_context_state_v1(
    document: Mapping[str, Any], *, previous_state: Mapping[str, Any] | None = None
) -> str:
    supplied = _verify_state_shape_and_digest(document)
    cycle = document.get("cycle_index")
    if cycle == 1:
        if previous_state is not None:
            raise V32TimeframeCacheError("V32_CACHE_GENESIS_INVALID")
        rebuilt = build_v32_timeframe_context_state_v1(
            run_id=document["run_id"],
            cycle_index=cycle,
            decision_time=document["decision_time"],
            state_mode=document["state_mode"],
            previous_state=None,
            frames=document["frames"],
            observed_invalidation_events=document["observed_invalidation_events"],
            analysis_clock_interval_seconds=document["analysis_clock_interval_seconds"],
            target_delta_processing_seconds=document["target_delta_processing_seconds"],
        )
    else:
        if previous_state is None:
            raise V32TimeframeCacheError("V32_CACHE_DELTA_PREVIOUS_REQUIRED")
        rebuilt = build_v32_timeframe_context_state_v1(
            run_id=document["run_id"],
            cycle_index=cycle,
            decision_time=document["decision_time"],
            state_mode=document["state_mode"],
            previous_state=previous_state,
            frames=document["frames"],
            observed_invalidation_events=document["observed_invalidation_events"],
            analysis_clock_interval_seconds=document["analysis_clock_interval_seconds"],
            target_delta_processing_seconds=document["target_delta_processing_seconds"],
        )
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32TimeframeCacheError("V32_CACHE_RECONSTRUCTION_MISMATCH")
    return supplied


def verify_v32_timeframe_context_state_intrinsic_v1(
    document: Mapping[str, Any],
) -> str:
    """Verify one stored state's exact shape/digest without replaying its parent.

    This verifier is only for a predecessor that has already been loaded through
    its owning accepted-state store.  A new delta must still pass
    ``verify_v32_timeframe_context_transition_v1`` against that predecessor.
    """

    return _verify_state_shape_and_digest(document)


def verify_v32_timeframe_context_transition_v1(
    *, previous_state: Mapping[str, Any], current_state: Mapping[str, Any]
) -> str:
    """Replay and verify one exact predecessor-to-delta transition."""

    previous_digest = _verify_state_shape_and_digest(previous_state)
    if current_state.get("previous_state_digest") != previous_digest:
        raise V32TimeframeCacheError("V32_CACHE_PREVIOUS_BINDING_MISMATCH")
    return verify_v32_timeframe_context_state_v1(
        current_state, previous_state=previous_state
    )


__all__ = [
    "DIGEST_FIELD",
    "FRAME_ROLES",
    "FRAME_UPDATE_MODES",
    "INVALIDATION_EVENT_TYPES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "STATE_MODES",
    "V32TimeframeCacheError",
    "build_v32_context_frame_v1",
    "build_v32_timeframe_context_state_v1",
    "project_v32_refreshed_frame_policy_v1",
    "project_v32_timeframe_payloads_v1",
    "project_v32_timeframe_source_refs_v1",
    "verify_v32_timeframe_invalidation_bindings_v1",
    "verify_v32_timeframe_payload_bindings_v1",
    "verify_v32_timeframe_production_policy_v1",
    "verify_v32_timeframe_context_state_v1",
    "verify_v32_timeframe_context_state_intrinsic_v1",
    "verify_v32_timeframe_context_transition_v1",
]
