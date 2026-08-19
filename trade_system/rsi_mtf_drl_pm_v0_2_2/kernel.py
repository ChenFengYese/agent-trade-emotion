"""Pure deterministic reference kernel for RSI-MTF-DRL-PM v0.2.2.

The kernel consumes only explicit immutable arguments.  It intentionally has
no source adapter, I/O, clock, environment, randomness, backtest, OMS or live
trading capability.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from typing import Any

from .contract import ContractValidationError, serialize_contract
from .model import (
    DECIMAL_CONTEXT,
    ArtifactTuple,
    BundleValidationFailure,
    FrozenMapping,
    KernelValidationError,
    OIEndpointSelection,
    ValidatedBundle,
    canonical_json,
    decimal_sum,
    decimal_value,
    exact_keys,
    freeze,
    is_safe_integer,
    is_sha256,
    materialize,
    parse_decimal,
    sha256_json,
    stable_id,
    validate_decimal,
)


_SYNTHETIC_LANE = "E0_SYNTHETIC_CANONICAL_V0_2_2"
_SCOPE_KEYS = ("venue_id", "instrument_id", "lane_id", "availability_kind")
_SOURCE_QUERY_KEYS = _SCOPE_KEYS + ("source_id", "source_schema_version")
_SOURCE_KINDS = (
    "CLOSED_MARK_BAR",
    "BOOK_SNAPSHOT",
    "AGG_TRADE",
    "OPEN_INTEREST",
)
_SOURCE_SCHEMA = {
    "CLOSED_MARK_BAR": "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
    "BOOK_SNAPSHOT": "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
    "AGG_TRADE": "rsi-mtf-drl-pm.agg-trade.v0.2.2",
    "OPEN_INTEREST": "rsi-mtf-drl-pm.open-interest.v0.2.2",
}
_SOURCE_ID_FIELD = {
    "CLOSED_MARK_BAR": "stable_bar_id",
    "BOOK_SNAPSHOT": "event_id",
    "AGG_TRADE": "event_id",
    "OPEN_INTEREST": "event_id",
}
_SOURCE_TIME_FIELD = {
    "CLOSED_MARK_BAR": "bar_close_at_us",
    "BOOK_SNAPSHOT": "event_time_us",
    "AGG_TRADE": "event_time_us",
    "OPEN_INTEREST": "event_time_us",
}
_GENERATION_FIELD = {
    "CLOSED_MARK_BAR": "stream_generation_id",
    "BOOK_SNAPSHOT": "book_generation_id",
    "AGG_TRADE": "stream_generation_id",
    "OPEN_INTEREST": "stream_generation_id",
}
_SOURCE_DOMAIN = {
    "CLOSED_MARK_BAR": "closed-mark-bar/v0.2.2",
    "BOOK_SNAPSHOT": "book-snapshot/v0.2.2",
    "AGG_TRADE": "agg-trade/v0.2.2",
    "OPEN_INTEREST": "open-interest/v0.2.2",
}
_SOURCE_EXACT_KEYS = {
    "CLOSED_MARK_BAR": (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "stream_generation_id",
        "period_seconds",
        "bar_open_at_us",
        "bar_close_at_us",
        "closed_at_us",
        "lane_available_at_us",
        "close_price",
        "source_sequence",
        "quality",
        "payload_sha256",
        "stable_bar_id",
    ),
    "BOOK_SNAPSHOT": (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "book_generation_id",
        "event_time_us",
        "lane_available_at_us",
        "source_sequence",
        "best_bid",
        "best_ask",
        "bids",
        "asks",
        "sequence_contiguous",
        "quality",
        "payload_sha256",
        "event_id",
    ),
    "AGG_TRADE": (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "stream_generation_id",
        "event_time_us",
        "lane_available_at_us",
        "source_sequence",
        "price",
        "qty_base",
        "buyer_is_taker",
        "quality",
        "payload_sha256",
        "event_id",
    ),
    "OPEN_INTEREST": (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "stream_generation_id",
        "event_time_us",
        "lane_available_at_us",
        "source_sequence",
        "oi_base",
        "quality",
        "payload_sha256",
        "event_id",
    ),
}
_ARTIFACT_SCHEMA_IDS = (
    "CLOSED_MARK_BAR",
    "BOOK_SNAPSHOT",
    "AGG_TRADE",
    "OPEN_INTEREST",
    "SOURCE_COVERAGE_SEAL",
    "VENUE_INSTRUMENT_SNAPSHOT",
    "ACCOUNT_RISK_SNAPSHOT",
    "FROZEN_EV_EVIDENCE",
    "U_OBSERVATION_RECEIPT",
    "SYNTHETIC_FIXTURE_MANIFEST",
    "POLICY_REGISTRY",
    "REDUCER_PRIORITY_POLICY",
    "PI_EXIT_POLICY",
    "FIRST_HIT_LABEL_POLICY",
    "DECISION_INPUT_BINDING",
    "SHARED_ENTRY_ACTION",
    "EXIT_POLICY_INSTANCE",
    "C4_C5_EXOGENOUS_PATH_MANIFEST",
    "SYNTHETIC_FUNDING_OBSERVATION",
    "SYNTHETIC_CONFLICT_PROOF",
)
_STATIC_POLICY_SCHEMAS = frozenset(
    {
        "POLICY_REGISTRY",
        "REDUCER_PRIORITY_POLICY",
        "PI_EXIT_POLICY",
        "FIRST_HIT_LABEL_POLICY",
    }
)
_BUNDLE_KEYS = (
    "schema_version",
    "bundle_scope_id",
    "ledger_bindings",
    "ledger_identity",
    "ledger_seed",
    "action_context",
    "entry_execution_binding",
    "artifacts",
    "coverage",
    "event_array",
    "finalized_at_us",
    "event_set_sha256",
    "bundle_sha256",
)
_LEDGER_BINDING_KEYS = (
    "core_raw_sha256",
    "v0_2_contract_canonical_sha256",
    "v0_2_1_addendum_raw_sha256",
    "v0_2_2_delta_raw_sha256",
    "v0_2_2_contract_sha256",
    "composite_theory_id",
    "policy_bundle_sha256",
    "code_sha256",
    "data_or_fixture_sha256",
    "ledger_seed_sha256",
)
_IDENTITY_KEYS = (
    "venue_id",
    "instrument_id",
    "lane_id",
    "account_scope_id",
    "role",
    "episode_id",
    "opportunity_id",
    "control_id",
    "candidate_id",
)
_COVERAGE_KEYS = (
    "status",
    "window_start_exclusive_us",
    "window_end_inclusive_us",
    "expected_grid_times_us",
    "observed_grid_times_us",
    "missing_grid_times_us",
    "event_count",
    "artifact_count",
    "event_set_sha256",
    "artifact_set_sha256",
    "coverage_sha256",
)
_GAP_KEYS = ("start_exclusive_us", "end_inclusive_us", "reason")
_GAP_REASONS = (
    "SEQUENCE_GAP",
    "CONNECTION_GAP",
    "IMPORT_GAP",
    "CONFLICT",
)
_WRAPPER_KEYS = (
    "artifact_id",
    "artifact_scope_id",
    "schema_id",
    "available_at_us",
    "payload_sha256",
    "payload",
)
_EVENT_KEYS = (
    "event_kind",
    "venue_id",
    "instrument_id",
    "episode_id",
    "opportunity_id",
    "control_id",
    "candidate_id",
    "event_time_us",
    "lane_available_at_us",
    "economic_event_time_us",
    "priority_rank",
    "source_sequence",
    "source_event_id",
    "predecessor_event_ids",
    "input_artifact_ids",
    "shared_entry_event_id",
    "request_id",
    "order_id",
    "payload_sha256",
    "payload",
)
_REDUCER_KINDS = (
    "CONTROL_ABSTAIN",
    "ENTRY_SUBMIT",
    "ENTRY_ACK",
    "ENTRY_REJECT",
    "ENTRY_EXPIRE",
    "FILL_CUMULATIVE",
    "CANCEL_REQUEST",
    "CANCEL_ACK",
    "CANCEL_REJECT_OR_UNKNOWN",
    "STOP_REQUEST",
    "STOP_ACK",
    "STOP_REJECT_OR_UNKNOWN",
    "TARGET_REQUEST",
    "TARGET_ACK",
    "TARGET_REJECT_OR_UNKNOWN",
    "POSITION_SNAPSHOT",
    "FUNDING_DEBIT",
    "PENDING_DEADLINE",
    "PROTECTION_REPAIR",
    "ACCOUNT_MISMATCH",
    "KILL",
    "STOP_HIT",
    "STRUCTURE_EXIT",
    "TARGET_HIT",
    "HORIZON",
    "BARRIER_EVALUATION",
    "REDUCE_ONLY_EXIT_REQUEST",
    "EXIT_FILL_CUMULATIVE",
    "EXIT_ACK",
    "EXIT_REJECT_OR_UNKNOWN",
    "RECONCILE_OK",
    "DATA_HEALTH_INVALID",
    "EVENT_CONFLICT",
    "NO_CHANGE",
)
_FIXED_EVENT_RANK = {
    "ACCOUNT_MISMATCH": 1,
    "KILL": 1,
    "DATA_HEALTH_INVALID": 1,
    "EVENT_CONFLICT": 1,
    "FILL_CUMULATIVE": 2,
    "EXIT_FILL_CUMULATIVE": 2,
    "POSITION_SNAPSHOT": 2,
    "FUNDING_DEBIT": 3,
    "STOP_HIT": 4,
    "PENDING_DEADLINE": 6,
    "STOP_REJECT_OR_UNKNOWN": 6,
    "PROTECTION_REPAIR": 6,
    "STRUCTURE_EXIT": 7,
    "TARGET_HIT": 8,
    "HORIZON": 9,
    "STOP_REQUEST": 10,
    "TARGET_REQUEST": 10,
    "TARGET_ACK": 10,
    "TARGET_REJECT_OR_UNKNOWN": 10,
    "REDUCE_ONLY_EXIT_REQUEST": 10,
    "EXIT_ACK": 10,
    "EXIT_REJECT_OR_UNKNOWN": 10,
    "RECONCILE_OK": 10,
    "CONTROL_ABSTAIN": 11,
    "ENTRY_SUBMIT": 11,
    "ENTRY_ACK": 11,
    "ENTRY_REJECT": 11,
    "ENTRY_EXPIRE": 11,
    "CANCEL_REQUEST": 11,
    "CANCEL_ACK": 11,
    "CANCEL_REJECT_OR_UNKNOWN": 11,
    "BARRIER_EVALUATION": 12,
    "NO_CHANGE": 12,
}
_STOP_ACK_RANK_PREDICATE = (
    "PREFIX_CURRENT_PROTECTION_REQUEST_EXACT_ID_PRICE_QTY_SIDE_"
    "REDUCE_ONLY_ROLE_AND_COVERAGE_SUFFICIENT"
)
_STATES = (
    "FLAT",
    "ENTRY_PENDING",
    "PROTECTION_PENDING",
    "OPEN_PROTECTED_PRE_LOCK",
    "PROFIT_LOCKED",
    "EXIT_PENDING",
    "CLOSED",
    "HALTED_RECONCILE",
)
_CLASS_COUNTS = (
    "NO_FILL",
    "TP",
    "SL",
    "STRUCTURE_EXIT",
    "TIMEOUT",
    "OPERATIONAL_OVERRIDE",
)
_ZERO_SHA = "0" * 64


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _array(value: Any) -> tuple[Any, ...] | None:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return None


def _without(value: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: child for key, child in value.items() if key not in keys}


def _frozen_mapping(value: Mapping[str, Any]) -> FrozenMapping:
    result = freeze(value)
    if not isinstance(result, FrozenMapping):
        raise TypeError("expected immutable mapping")
    return result


def _artifact_sequence(artifacts: Any) -> tuple[Mapping[str, Any], ...] | None:
    if isinstance(artifacts, ArtifactTuple):
        return tuple(artifacts.artifacts)
    if isinstance(artifacts, Mapping):
        values = _array(artifacts.get("artifacts"))
    else:
        values = _array(artifacts)
    if values is None or not all(isinstance(item, Mapping) for item in values):
        return None
    return tuple(values)


def _payload(wrapper_or_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    candidate = wrapper_or_payload.get("payload")
    if isinstance(candidate, Mapping) and "schema_id" in wrapper_or_payload:
        return candidate
    return wrapper_or_payload


def _scope(value: Mapping[str, Any]) -> tuple[Any, Any, Any, Any]:
    return tuple(value.get(key) for key in _SCOPE_KEYS)  # type: ignore[return-value]


def _scope_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in _SCOPE_KEYS}


def _query_matches(payload: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    return (
        exact_keys(query, _SOURCE_QUERY_KEYS)
        and all(payload.get(key) == query.get(key) for key in _SCOPE_KEYS + ("source_id",))
        and payload.get("schema_version") == query.get("source_schema_version")
    )


def _find_artifact(
    artifacts: Sequence[Mapping[str, Any]], artifact_id: Any
) -> Mapping[str, Any] | None:
    matches = [item for item in artifacts if item.get("artifact_id") == artifact_id]
    if len(matches) != 1:
        return None
    return matches[0]


def _ordered_source_projection(source_object: Mapping[str, Any]) -> FrozenMapping:
    payload = _payload(source_object)
    if payload is None:
        raise ValueError("malformed source object")
    kind = source_object.get("schema_id")
    if kind not in _SOURCE_KINDS:
        schema = payload.get("schema_version")
        matches = [candidate for candidate, literal in _SOURCE_SCHEMA.items() if schema == literal]
        if len(matches) != 1:
            raise ValueError("unknown source kind")
        kind = matches[0]
    object_id = payload.get(_SOURCE_ID_FIELD[kind])
    generation_id = payload.get(_GENERATION_FIELD[kind])
    projection = {
        "object_kind": kind,
        "venue_id": payload.get("venue_id"),
        "instrument_id": payload.get("instrument_id"),
        "lane_id": payload.get("lane_id"),
        "availability_kind": payload.get("availability_kind"),
        "economic_time_us": payload.get(_SOURCE_TIME_FIELD[kind]),
        "lane_available_at_us": payload.get("lane_available_at_us"),
        "source_sequence": payload.get("source_sequence"),
        "source_object_id": object_id,
        "payload_sha256": payload.get("payload_sha256"),
        "generation_id": generation_id,
    }
    if (
        not all(isinstance(projection[key], str) and projection[key] for key in ("venue_id", "instrument_id", "lane_id", "availability_kind"))
        or not is_safe_integer(projection["economic_time_us"], nonnegative=True)
        or not is_safe_integer(projection["lane_available_at_us"], nonnegative=True)
        or not is_safe_integer(projection["source_sequence"], nonnegative=True)
        or not is_sha256(object_id)
        or not is_sha256(generation_id)
        or not is_sha256(projection["payload_sha256"])
    ):
        raise ValueError("malformed ordered source projection")
    return _frozen_mapping(projection)


def _source_collision(source_artifacts: Any) -> bool:
    artifacts = _artifact_sequence(source_artifacts)
    if artifacts is None:
        raise ValueError("malformed source artifact tuple")
    seen: dict[tuple[Any, ...], tuple[str, bytes]] = {}
    for wrapper in artifacts:
        projection = _ordered_source_projection(wrapper)
        payload = _payload(wrapper)
        if payload is None:
            raise ValueError("malformed source payload")
        key = (
            payload.get("schema_version"),
            *(_scope(payload)),
            payload.get("source_id"),
            projection["generation_id"],
            projection["source_sequence"],
        )
        current = (projection["source_object_id"], canonical_json(payload))
        previous = seen.get(key)
        if previous is not None and previous != current:
            return True
        seen[key] = current
    return False


def _select_coverage_seal(artifacts: Any, binding: Mapping[str, Any]) -> Any:
    values = _artifact_sequence(artifacts)
    if values is None or not exact_keys(
        binding,
        (
            "coverage_seal_artifact_id",
            "coverage_seal_sha256",
            "venue_id",
            "instrument_id",
            "lane_id",
            "availability_kind",
            "source_id",
            "source_schema_version",
            "covered_object_kind",
            "window_start_exclusive_us",
            "window_end_inclusive_us",
            "lane_available_at_us",
        ),
    ):
        raise ValueError("malformed coverage selector input")
    candidates: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != "SOURCE_COVERAGE_SEAL":
            continue
        payload = _payload(wrapper)
        if payload is None:
            raise ValueError("malformed coverage payload")
        fields = (
            "venue_id",
            "instrument_id",
            "lane_id",
            "availability_kind",
            "source_id",
            "source_schema_version",
            "covered_object_kind",
            "window_start_exclusive_us",
            "window_end_inclusive_us",
            "lane_available_at_us",
        )
        if all(payload.get(key) == binding.get(key) for key in fields):
            candidates.append(wrapper)
    unique = {item.get("artifact_id"): item for item in candidates}
    if not unique:
        return "UNKNOWN"
    if len(unique) > 1:
        return "COVERAGE_CONFLICT"
    winner = next(iter(unique.values()))
    payload = _payload(winner)
    if (
        winner.get("artifact_id") != binding.get("coverage_seal_artifact_id")
        or payload is None
        or payload.get("seal_sha256") != binding.get("coverage_seal_sha256")
    ):
        return "UNKNOWN"
    return _frozen_mapping(winner)


def _validate_coverage_seal(
    source_artifacts: Any,
    seal_artifact: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> bool:
    values = _artifact_sequence(source_artifacts)
    seal = _payload(seal_artifact)
    if values is None or seal is None:
        return False
    if _select_coverage_seal((seal_artifact,), binding) in ("UNKNOWN", "COVERAGE_CONFLICT"):
        return False
    if seal.get("schema_version") != "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2":
        return False
    kind = seal.get("covered_object_kind")
    if kind not in _SOURCE_KINDS:
        return False
    expected: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != kind:
            continue
        payload = _payload(wrapper)
        if payload is None:
            return False
        economic = payload.get(_SOURCE_TIME_FIELD[kind])
        if (
            _scope(payload) == _scope(seal)
            and payload.get("source_id") == seal.get("source_id")
            and payload.get("schema_version") == seal.get("source_schema_version")
            and is_safe_integer(economic, nonnegative=True)
            and seal.get("window_start_exclusive_us") < economic <= seal.get("window_end_inclusive_us")
        ):
            if payload.get("lane_available_at_us") > seal.get("lane_available_at_us"):
                return False
            expected.append(wrapper)
    if _source_collision(expected):
        return False
    expected.sort(
        key=lambda item: (
            _ordered_source_projection(item)["economic_time_us"],
            _ordered_source_projection(item)["source_sequence"],
            _ordered_source_projection(item)["source_object_id"],
        )
    )
    expected_ids = [
        _ordered_source_projection(item)["source_object_id"] for item in expected
    ]
    sealed_event_ids = _array(seal.get("covered_event_ids"))
    if sealed_event_ids is None or list(sealed_event_ids) != expected_ids:
        return False
    if seal.get("event_count") != len(expected_ids):
        return False
    expected_set_sha = stable_id(
        "coverage-covered-event-set/v0.2.2",
        {
            "venue_id": seal.get("venue_id"),
            "instrument_id": seal.get("instrument_id"),
            "lane_id": seal.get("lane_id"),
            "availability_kind": seal.get("availability_kind"),
            "source_id": seal.get("source_id"),
            "source_schema_version": seal.get("source_schema_version"),
            "covered_object_kind": kind,
            "window_start_exclusive_us": seal.get("window_start_exclusive_us"),
            "window_end_inclusive_us": seal.get("window_end_inclusive_us"),
            "covered_event_ids": expected_ids,
        },
    )
    if seal.get("covered_event_set_sha256") != expected_set_sha:
        return False
    ranges = _array(seal.get("generation_ranges"))
    gaps = _array(seal.get("observed_gap_intervals"))
    if ranges is None or gaps is None:
        return False
    if list(ranges) != sorted(ranges, key=lambda item: item.get("generation_id") if isinstance(item, Mapping) else ""):
        return False
    expected_by_generation: dict[str, list[int]] = {}
    for wrapper in expected:
        projection = _ordered_source_projection(wrapper)
        expected_by_generation.setdefault(
            projection["generation_id"], []
        ).append(projection["source_sequence"])
    if len(ranges) != len(expected_by_generation):
        return False
    for item in ranges:
        if not exact_keys(
            item,
            (
                "generation_id",
                "first_source_sequence",
                "last_source_sequence",
                "event_count",
            ),
        ):
            return False
        generation_id = item.get("generation_id")
        sequences = expected_by_generation.get(generation_id)
        if sequences is None or len(sequences) != len(set(sequences)):
            return False
        first, last = item.get("first_source_sequence"), item.get("last_source_sequence")
        if (
            not is_safe_integer(first, nonnegative=True)
            or not is_safe_integer(last, nonnegative=True)
            or last < first
            or item.get("event_count") != last - first + 1
            or sorted(sequences) != list(range(first, last + 1))
        ):
            return False
    all_valid = all(
        _payload(item).get("quality") == "VALID"
        and (
            item.get("schema_id") != "BOOK_SNAPSHOT"
            or _payload(item).get("sequence_contiguous") is True
        )
        for item in expected
        if _payload(item) is not None
    )
    should_complete = not gaps and all_valid
    if seal.get("complete") is not should_complete:
        return False
    return seal.get("seal_sha256") == stable_id(
        "source-coverage-seal/v0.2.2", _without(seal, "seal_sha256")
    )


def _select_latest_source(
    artifacts: Any,
    query: Mapping[str, Any],
    tau_us: int,
    max_age_us: int,
    kind: str,
    *,
    require_contiguous: bool,
) -> Any:
    values = _artifact_sequence(artifacts)
    if (
        values is None
        or kind not in ("BOOK_SNAPSHOT", "OPEN_INTEREST")
        or not is_safe_integer(tau_us, nonnegative=True)
        or not is_safe_integer(max_age_us, nonnegative=True)
        or not exact_keys(query, _SOURCE_QUERY_KEYS)
    ):
        raise ValueError("malformed source selector input")
    candidates: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != kind:
            continue
        payload = _payload(wrapper)
        if payload is None or not _query_matches(payload, query):
            continue
        event_time = payload.get("event_time_us")
        eligible = (
            payload.get("quality") == "VALID"
            and (not require_contiguous or payload.get("sequence_contiguous") is True)
            and is_safe_integer(event_time, nonnegative=True)
            and event_time <= tau_us
            and payload.get("lane_available_at_us") <= tau_us
            and 0 <= tau_us - event_time <= max_age_us
        )
        if eligible:
            candidates.append(wrapper)
    if not candidates:
        return "UNKNOWN"
    if _source_collision(candidates):
        return "CONFLICT"
    latest = max(_payload(item).get("event_time_us") for item in candidates)
    winners = [item for item in candidates if _payload(item).get("event_time_us") == latest]
    winners.sort(
        key=lambda item: (
            _payload(item).get("lane_available_at_us"),
            _payload(item).get("source_sequence"),
            _payload(item).get("event_id"),
        )
    )
    return _frozen_mapping(winners[0])


def _select_book(
    artifacts: Any,
    query: Mapping[str, Any],
    tau_us: int,
    max_age_us: int,
) -> Any:
    return _select_latest_source(
        artifacts, query, tau_us, max_age_us, "BOOK_SNAPSHOT", require_contiguous=True
    )


def _select_book_grid(
    artifacts: Any, query: Mapping[str, Any], grid_time_us: int
) -> Any:
    return _select_book(artifacts, query, grid_time_us, 1_000_000)


def _select_open_interest(
    artifacts: Any,
    query: Mapping[str, Any],
    tau_us: int,
    max_age_us: int,
) -> Any:
    return _select_latest_source(
        artifacts, query, tau_us, max_age_us, "OPEN_INTEREST", require_contiguous=False
    )


def _venue_structurally_valid(payload: Mapping[str, Any]) -> bool:
    if payload.get("quality") != "VALID":
        return False
    decimal_kinds = {
        "tick_size": "Price",
        "lot_step": "Price",
        "min_qty": "Price",
        "max_qty": "Price",
        "min_notional_usdt": "Price",
        "max_notional_usdt": "Price",
        "max_leverage": "Price",
        "initial_margin_rate": "Price",
        "fee_bps_per_side": "Bps",
    }
    if not all(validate_decimal(kind, payload.get(key)) for key, kind in decimal_kinds.items()):
        return False
    try:
        tick = parse_decimal(payload["tick_size"], "Price")
        lot = parse_decimal(payload["lot_step"], "Price")
        minimum = parse_decimal(payload["min_qty"], "Price")
        maximum = parse_decimal(payload["max_qty"], "Price")
        min_notional = parse_decimal(payload["min_notional_usdt"], "Price")
        max_notional = parse_decimal(payload["max_notional_usdt"], "Price")
        leverage = parse_decimal(payload["max_leverage"], "Price")
        margin = parse_decimal(payload["initial_margin_rate"], "Price")
        fee = parse_decimal(payload["fee_bps_per_side"], "Bps")
    except (KeyError, ValueError):
        return False
    return (
        tick > 0
        and lot > 0
        and minimum > 0
        and maximum >= minimum
        and min_notional > 0
        and max_notional >= min_notional
        and leverage > 0
        and Decimal(0) < margin <= Decimal(1)
        and fee >= 0
    )


def _select_venue_snapshot(
    artifacts: Any, scope: Mapping[str, Any], tau_us: int
) -> Any:
    values = _artifact_sequence(artifacts)
    if (
        values is None
        or not exact_keys(scope, _SCOPE_KEYS)
        or not is_safe_integer(tau_us, nonnegative=True)
    ):
        raise ValueError("malformed venue selector input")
    candidates: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != "VENUE_INSTRUMENT_SNAPSHOT":
            continue
        payload = _payload(wrapper)
        if payload is None:
            raise ValueError("malformed venue payload")
        if (
            _scope(payload) == _scope(scope)
            and _venue_structurally_valid(payload)
            and payload.get("effective_at_us") <= tau_us
            and payload.get("lane_available_at_us") <= tau_us
        ):
            candidates.append(wrapper)
    if not candidates:
        return "UNKNOWN"
    latest = max(_payload(item).get("effective_at_us") for item in candidates)
    winners = [item for item in candidates if _payload(item).get("effective_at_us") == latest]
    fingerprints = {_payload(item).get("rule_fingerprint_sha256") for item in winners}
    if len(fingerprints) != 1:
        return "RULE_SNAPSHOT_CONFLICT"
    winners.sort(key=lambda item: _payload(item).get("snapshot_id"))
    return _frozen_mapping(winners[0])


def _select_account_snapshot(
    artifacts: Any,
    account_query: Mapping[str, Any],
    tau_us: int,
    max_age_us: int,
) -> Any:
    values = _artifact_sequence(artifacts)
    account_keys = ("account_scope_id",) + _SOURCE_QUERY_KEYS
    if (
        values is None
        or not exact_keys(account_query, account_keys)
        or account_query.get("source_schema_version")
        != "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2"
        or not is_safe_integer(tau_us, nonnegative=True)
        or not is_safe_integer(max_age_us, nonnegative=True)
    ):
        raise ValueError("malformed account selector input")
    candidates: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != "ACCOUNT_RISK_SNAPSHOT":
            continue
        payload = _payload(wrapper)
        if payload is None:
            raise ValueError("malformed account payload")
        effective = payload.get("effective_at_us")
        if (
            payload.get("account_scope_id") == account_query.get("account_scope_id")
            and _query_matches(payload, account_query)
            and payload.get("quality") == "VALID"
            and is_safe_integer(effective, nonnegative=True)
            and effective <= tau_us
            and payload.get("lane_available_at_us") <= tau_us
            and 0 <= tau_us - effective <= max_age_us
        ):
            candidates.append(wrapper)
    if not candidates:
        return "UNKNOWN"
    latest = max(_payload(item).get("effective_at_us") for item in candidates)
    winners = [item for item in candidates if _payload(item).get("effective_at_us") == latest]
    payload_hashes = {_payload(item).get("payload_sha256") for item in winners}
    if len(payload_hashes) != 1:
        return "ACCOUNT_SNAPSHOT_CONFLICT"
    winners.sort(key=lambda item: _payload(item).get("snapshot_id"))
    return _frozen_mapping(winners[0])


def _select_closed_mark_bar_slot(
    artifacts: Any,
    query: Mapping[str, Any],
    period_seconds: int,
    bar_open_at_us: int,
    tau_us: int,
) -> Any:
    values = _artifact_sequence(artifacts)
    if (
        values is None
        or not exact_keys(query, _SOURCE_QUERY_KEYS)
        or period_seconds not in (900, 14400)
        or not is_safe_integer(bar_open_at_us, nonnegative=True)
        or not is_safe_integer(tau_us, nonnegative=True)
    ):
        raise ValueError("malformed bar selector input")
    candidates: list[Mapping[str, Any]] = []
    for wrapper in values:
        if wrapper.get("schema_id") != "CLOSED_MARK_BAR":
            continue
        payload = _payload(wrapper)
        if payload is None:
            raise ValueError("malformed bar payload")
        if (
            _query_matches(payload, query)
            and payload.get("period_seconds") == period_seconds
            and payload.get("bar_open_at_us") == bar_open_at_us
            and payload.get("quality") == "VALID"
            and is_safe_integer(payload.get("bar_close_at_us"), nonnegative=True)
            and is_safe_integer(payload.get("closed_at_us"), nonnegative=True)
            and is_safe_integer(payload.get("lane_available_at_us"), nonnegative=True)
            and payload.get("bar_close_at_us")
            <= payload.get("closed_at_us")
            <= payload.get("lane_available_at_us")
            and payload.get("closed_at_us") <= tau_us
            and payload.get("lane_available_at_us") <= tau_us
        ):
            candidates.append(wrapper)
    if not candidates:
        return "UNKNOWN"
    payload_hashes = {_payload(item).get("payload_sha256") for item in candidates}
    if len(payload_hashes) != 1 or _source_collision(candidates):
        return "CONFLICT"
    candidates.sort(key=lambda item: _payload(item).get("stable_bar_id"))
    return _frozen_mapping(candidates[0])


def _select_agg_trade_window(
    artifacts: Any,
    query: Mapping[str, Any],
    start_exclusive_us: int,
    end_inclusive_us: int,
    decision_at_us: int,
    seal_binding: Mapping[str, Any],
) -> Any:
    values = _artifact_sequence(artifacts)
    if (
        values is None
        or not exact_keys(query, _SOURCE_QUERY_KEYS)
        or not all(
            is_safe_integer(value, nonnegative=True)
            for value in (start_exclusive_us, end_inclusive_us, decision_at_us)
        )
        or not start_exclusive_us < end_inclusive_us <= decision_at_us
    ):
        raise ValueError("malformed trade-window selector input")
    seal = _select_coverage_seal(values, seal_binding)
    if seal in ("UNKNOWN", "COVERAGE_CONFLICT"):
        return seal
    if not isinstance(seal, Mapping):
        raise ValueError("invalid seal selector carrier")
    source = [
        item
        for item in values
        if item.get("schema_id") == "AGG_TRADE"
        and (payload := _payload(item)) is not None
        and _query_matches(payload, query)
        and start_exclusive_us < payload.get("event_time_us") <= end_inclusive_us
    ]
    if not _validate_coverage_seal(source, seal, seal_binding):
        return "UNKNOWN"
    seal_payload = _payload(seal)
    if seal_payload is None or seal_payload.get("complete") is not True:
        return "UNKNOWN"
    by_id = {
        _payload(item).get("event_id"): item
        for item in source
        if _payload(item) is not None
    }
    ordered: list[FrozenMapping] = []
    for event_id in seal_payload.get("covered_event_ids", ()):
        wrapper = by_id.get(event_id)
        payload = _payload(wrapper) if wrapper is not None else None
        if (
            wrapper is None
            or payload is None
            or payload.get("quality") != "VALID"
            or payload.get("lane_available_at_us") > decision_at_us
        ):
            return "UNKNOWN"
        ordered.append(_frozen_mapping(wrapper))
    return ArtifactTuple(tuple(ordered))


def _validate_oi_completeness(
    artifacts: Any,
    query: Mapping[str, Any],
    t_us: int,
    seal_binding: Mapping[str, Any],
) -> Any:
    values = _artifact_sequence(artifacts)
    if (
        values is None
        or not is_safe_integer(t_us, nonnegative=True)
        or t_us < 960_000_000
        or not exact_keys(query, _SOURCE_QUERY_KEYS)
    ):
        raise ValueError("malformed OI completeness input")
    if (
        seal_binding.get("covered_object_kind") != "OPEN_INTEREST"
        or seal_binding.get("window_start_exclusive_us") != t_us - 960_000_000
        or seal_binding.get("window_end_inclusive_us") != t_us
    ):
        return "UNKNOWN"
    seal = _select_coverage_seal(values, seal_binding)
    if not isinstance(seal, Mapping):
        return "UNKNOWN"
    sources = [
        item
        for item in values
        if item.get("schema_id") == "OPEN_INTEREST"
        and (payload := _payload(item)) is not None
        and _query_matches(payload, query)
        and t_us - 960_000_000 < payload.get("event_time_us") <= t_us
    ]
    if not _validate_coverage_seal(sources, seal, seal_binding):
        return "UNKNOWN"
    seal_payload = _payload(seal)
    if seal_payload is None or seal_payload.get("complete") is not True:
        return "UNKNOWN"
    now = _select_open_interest(values, query, t_us, 60_000_000)
    previous = _select_open_interest(values, query, t_us - 900_000_000, 60_000_000)
    if not isinstance(now, Mapping) or not isinstance(previous, Mapping):
        return "UNKNOWN"
    covered_ids = set(seal_payload.get("covered_event_ids", ()))
    if (
        _payload(now).get("event_id") not in covered_ids
        or _payload(previous).get("event_id") not in covered_ids
    ):
        return "UNKNOWN"
    return OIEndpointSelection(
        _frozen_mapping(seal),
        _frozen_mapping(now),
        _frozen_mapping(previous),
    )


def _validate_decimal(kind: str, value: str) -> bool:
    return validate_decimal(kind, value)


_POLICY_DOMAIN_BY_SCHEMA = {
    "rsi-mtf-drl-pm.u-policy.v0.2.2": "u-policy/v0.2.2",
    "rsi-mtf-drl-pm.entry-policy.v0.2.2": "entry-policy/v0.2.2",
    "rsi-mtf-drl-pm.exit-policy-template.v0.2.2": "exit-policy-template/v0.2.2",
    "rsi-mtf-drl-pm.cost-policy.v0.2.2": "cost-policy/v0.2.2",
    "rsi-mtf-drl-pm.risk-policy.v0.2.2": "risk-policy/v0.2.2",
    "rsi-mtf-drl-pm.label-policy-binding.v0.2.2": "label-policy-binding/v0.2.2",
    "rsi-mtf-drl-pm.data-role-policy.v0.2.2": "data-role-policy/v0.2.2",
    "rsi-mtf-drl-pm.estimator-policy.v0.2.2": "estimator-policy/v0.2.2",
    "rsi-mtf-drl-pm.source-selector-policy.v0.2.2": "source-selector-policy/v0.2.2",
    "rsi-mtf-drl-pm.reducer-priority-policy.v0.2.2": "reducer-priority-policy/v0.2.2",
    "rsi-mtf-drl-pm.pi-exit.v0.2.2": "pi-exit-policy/v0.2.2",
    "rsi-mtf-drl-pm.first-hit-label-policy.v0.2.2": "first-hit-label-policy/v0.2.2",
}


def _source_payload_valid(kind: str, payload: Mapping[str, Any]) -> bool:
    if kind not in _SOURCE_KINDS or not exact_keys(payload, _SOURCE_EXACT_KEYS[kind]):
        return False
    if (
        payload.get("schema_version") != _SOURCE_SCHEMA[kind]
        or payload.get("availability_kind") != "SYNTHETIC"
        or payload.get("lane_id") != _SYNTHETIC_LANE
        or not all(
            isinstance(payload.get(key), str) and payload.get(key)
            for key in ("venue_id", "instrument_id", "lane_id", "source_id")
        )
        or not is_sha256(payload.get(_GENERATION_FIELD[kind]))
        or not is_safe_integer(payload.get("source_sequence"), nonnegative=True)
        or payload.get("quality") not in ("VALID", "INVALID", "GAP", "CONFLICT")
    ):
        return False
    economic = payload.get(_SOURCE_TIME_FIELD[kind])
    available = payload.get("lane_available_at_us")
    if (
        not is_safe_integer(economic, nonnegative=True)
        or not is_safe_integer(available, nonnegative=True)
        or economic > available
    ):
        return False
    if kind == "CLOSED_MARK_BAR":
        period = payload.get("period_seconds")
        opened = payload.get("bar_open_at_us")
        closed = payload.get("bar_close_at_us")
        if (
            period not in (900, 14400)
            or not is_safe_integer(opened, nonnegative=True)
            or not is_safe_integer(closed, nonnegative=True)
            or closed - opened != period * 1_000_000
            or opened % (period * 1_000_000) != 0
            or closed % (period * 1_000_000) != 0
            or not is_safe_integer(payload.get("closed_at_us"), nonnegative=True)
            or not closed
            <= payload.get("closed_at_us")
            <= payload.get("lane_available_at_us")
            or not validate_decimal("Price", payload.get("close_price"))
        ):
            return False
    elif kind == "BOOK_SNAPSHOT":
        if (
            not isinstance(payload.get("sequence_contiguous"), bool)
            or not validate_decimal("Price", payload.get("best_bid"))
            or not validate_decimal("Price", payload.get("best_ask"))
        ):
            return False
        try:
            bid = parse_decimal(payload["best_bid"], "Price")
            ask = parse_decimal(payload["best_ask"], "Price")
        except (KeyError, ValueError):
            return False
        bids, asks = _array(payload.get("bids")), _array(payload.get("asks"))
        if bid >= ask or not bids or not asks:
            return False
        previous: Decimal | None = None
        for index, level in enumerate(bids):
            if not exact_keys(level, ("price", "qty_base")):
                return False
            if not validate_decimal("Price", level.get("price")) or not validate_decimal(
                "Price", level.get("qty_base")
            ):
                return False
            price = parse_decimal(level["price"], "Price")
            if (index == 0 and price != bid) or (previous is not None and price >= previous):
                return False
            previous = price
        previous = None
        for index, level in enumerate(asks):
            if not exact_keys(level, ("price", "qty_base")):
                return False
            if not validate_decimal("Price", level.get("price")) or not validate_decimal(
                "Price", level.get("qty_base")
            ):
                return False
            price = parse_decimal(level["price"], "Price")
            if (index == 0 and price != ask) or (previous is not None and price <= previous):
                return False
            previous = price
    elif kind == "AGG_TRADE":
        if (
            not validate_decimal("Price", payload.get("price"))
            or not validate_decimal("Price", payload.get("qty_base"))
            or not isinstance(payload.get("buyer_is_taker"), bool)
        ):
            return False
    elif kind == "OPEN_INTEREST" and not validate_decimal("Price", payload.get("oi_base")):
        return False
    object_id_key = _SOURCE_ID_FIELD[kind]
    expected_payload = sha256_json(_without(payload, "payload_sha256", object_id_key))
    if payload.get("payload_sha256") != expected_payload:
        return False
    return payload.get(object_id_key) == stable_id(
        _SOURCE_DOMAIN[kind], _without(payload, object_id_key)
    )


def _coverage_shape_valid(payload: Mapping[str, Any]) -> bool:
    keys = (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "source_schema_version",
        "covered_object_kind",
        "window_start_exclusive_us",
        "window_end_inclusive_us",
        "lane_available_at_us",
        "generation_ranges",
        "covered_event_ids",
        "covered_event_set_sha256",
        "event_count",
        "observed_gap_intervals",
        "complete",
        "seal_sha256",
    )
    if not exact_keys(payload, keys):
        return False
    start, end, available = (
        payload.get("window_start_exclusive_us"),
        payload.get("window_end_inclusive_us"),
        payload.get("lane_available_at_us"),
    )
    ids = _array(payload.get("covered_event_ids"))
    ranges = _array(payload.get("generation_ranges"))
    gaps = _array(payload.get("observed_gap_intervals"))
    if not (
        payload.get("schema_version")
        == "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2"
        and payload.get("covered_object_kind") in _SOURCE_KINDS
        and payload.get("availability_kind") == "SYNTHETIC"
        and payload.get("lane_id") == _SYNTHETIC_LANE
        and all(is_safe_integer(value, nonnegative=True) for value in (start, end, available))
        and start < end <= available
        and ids is not None
        and ranges is not None
        and gaps is not None
        and all(is_sha256(item) for item in ids)
        and len(ids) == len(set(ids))
        and is_safe_integer(payload.get("event_count"), nonnegative=True)
        and isinstance(payload.get("complete"), bool)
        and is_sha256(payload.get("covered_event_set_sha256"))
        and is_sha256(payload.get("seal_sha256"))
    ):
        return False
    gap_values = list(gaps)
    previous_end: int | None = None
    previous_key: tuple[int, int, str] | None = None
    for gap in gap_values:
        if not exact_keys(gap, _GAP_KEYS):
            return False
        gap_start = gap.get("start_exclusive_us")
        gap_end = gap.get("end_inclusive_us")
        reason = gap.get("reason")
        if (
            not is_safe_integer(gap_start, nonnegative=True)
            or not is_safe_integer(gap_end, nonnegative=True)
            or reason not in _GAP_REASONS
            or not start <= gap_start < gap_end <= end
        ):
            return False
        key = (gap_start, gap_end, reason)
        if previous_key is not None and key <= previous_key:
            return False
        if previous_end is not None and gap_start < previous_end:
            return False
        previous_key = key
        previous_end = gap_end
    return True


def _venue_payload_valid(payload: Mapping[str, Any]) -> bool:
    keys = (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "contract_kind",
        "effective_at_us",
        "lane_available_at_us",
        "tick_size",
        "lot_step",
        "min_qty",
        "max_qty",
        "min_notional_usdt",
        "max_notional_usdt",
        "max_leverage",
        "initial_margin_rate",
        "fee_bps_per_side",
        "rule_fingerprint_sha256",
        "quality",
        "payload_sha256",
        "snapshot_id",
    )
    if not exact_keys(payload, keys):
        return False
    if (
        payload.get("schema_version")
        != "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2"
        or payload.get("contract_kind") != "LINEAR_USDT_PERPETUAL"
        or payload.get("availability_kind") != "SYNTHETIC"
        or payload.get("lane_id") != _SYNTHETIC_LANE
        or payload.get("quality") not in ("VALID", "INVALID", "CONFLICT")
        or not is_safe_integer(payload.get("effective_at_us"), nonnegative=True)
        or not is_safe_integer(payload.get("lane_available_at_us"), nonnegative=True)
        or payload.get("effective_at_us") > payload.get("lane_available_at_us")
    ):
        return False
    fingerprint = stable_id(
        "venue-rule-fingerprint/v0.2.2",
        {
            key: payload.get(key)
            for key in (
                "contract_kind",
                "tick_size",
                "lot_step",
                "min_qty",
                "max_qty",
                "min_notional_usdt",
                "max_notional_usdt",
                "max_leverage",
                "initial_margin_rate",
                "fee_bps_per_side",
            )
        },
    )
    if payload.get("rule_fingerprint_sha256") != fingerprint:
        return False
    if payload.get("quality") == "VALID" and not _venue_structurally_valid(payload):
        return False
    if payload.get("payload_sha256") != sha256_json(
        _without(payload, "payload_sha256", "snapshot_id")
    ):
        return False
    return payload.get("snapshot_id") == stable_id(
        "venue-instrument-snapshot/v0.2.2", _without(payload, "snapshot_id")
    )


def _account_payload_valid(payload: Mapping[str, Any]) -> bool:
    keys = (
        "schema_version",
        "account_scope_id",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "source_id",
        "effective_at_us",
        "lane_available_at_us",
        "equity_usdt",
        "available_balance_usdt",
        "existing_initial_margin_usdt",
        "open_order_reserve_usdt",
        "pending_fee_reserve_usdt",
        "position_qty_base",
        "position_vwap",
        "open_order_ids",
        "quality",
        "payload_sha256",
        "snapshot_id",
    )
    if not exact_keys(payload, keys):
        return False
    if (
        payload.get("schema_version")
        != "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2"
        or payload.get("availability_kind") != "SYNTHETIC"
        or payload.get("lane_id") != _SYNTHETIC_LANE
        or payload.get("quality") not in ("VALID", "INVALID", "CONFLICT")
        or not all(
            isinstance(payload.get(key), str) and payload.get(key)
            for key in ("account_scope_id", "source_id")
        )
        or not is_safe_integer(payload.get("effective_at_us"), nonnegative=True)
        or not is_safe_integer(payload.get("lane_available_at_us"), nonnegative=True)
        or payload.get("effective_at_us") > payload.get("lane_available_at_us")
    ):
        return False
    money_fields = (
        "equity_usdt",
        "available_balance_usdt",
        "existing_initial_margin_usdt",
        "open_order_reserve_usdt",
        "pending_fee_reserve_usdt",
    )
    if not all(validate_decimal("Money", payload.get(key)) for key in money_fields):
        return False
    if not validate_decimal("DecimalString", payload.get("position_qty_base")):
        return False
    position = parse_decimal(payload["position_qty_base"])
    vwap = payload.get("position_vwap")
    if (position == 0) != (vwap is None) or (vwap is not None and not validate_decimal("Price", vwap)):
        return False
    orders = _array(payload.get("open_order_ids"))
    if (
        orders is None
        or not all(isinstance(item, str) and item for item in orders)
        or list(orders) != sorted(set(orders), key=lambda item: item.encode("utf-8"))
    ):
        return False
    if parse_decimal(payload["available_balance_usdt"], "Money") > parse_decimal(
        payload["equity_usdt"], "Money"
    ):
        return False
    if payload.get("payload_sha256") != sha256_json(
        _without(payload, "payload_sha256", "snapshot_id")
    ):
        return False
    return payload.get("snapshot_id") == stable_id(
        "account-risk-snapshot/v0.2.2", _without(payload, "snapshot_id")
    )


def _ev_evidence_valid(payload: Mapping[str, Any], composite_theory_id: Any) -> bool:
    keys = (
        "schema_version",
        "venue_id",
        "instrument_id",
        "lane_id",
        "availability_kind",
        "evidence_kind",
        "candidate_id",
        "control_id",
        "side",
        "management_state",
        "relative_anchor_bp_bucket",
        "extension_bp_bucket",
        "role",
        "sample_start_exclusive_us",
        "sample_end_inclusive_us",
        "issued_at_us",
        "lane_available_at_us",
        "expires_at_us",
        "observations",
        "n",
        "sum_y_r",
        "min_y_r",
        "max_y_r",
        "class_counts",
        "observations_sha256",
        "estimator_policy_sha256",
        "cost_policy_sha256",
        "label_policy_sha256",
        "data_role_sha256",
        "evidence_sha256",
    )
    if not exact_keys(payload, keys):
        return False
    kind = payload.get("evidence_kind")
    extension = payload.get("extension_bp_bucket")
    if (
        payload.get("schema_version") != "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2"
        or payload.get("role") != "SYNTHETIC"
        or payload.get("availability_kind") != "SYNTHETIC"
        or payload.get("lane_id") != _SYNTHETIC_LANE
        or kind not in ("SUBMIT", "HOLD", "EXIT_NOW")
        or payload.get("control_id") not in ("C1", "C2", "C3", "C4", "Cmu", "C5")
        or payload.get("side") not in ("LONG", "SHORT")
        or (
            kind == "SUBMIT"
            and (payload.get("management_state") != "PRE_SUBMIT" or extension is not None)
        )
        or (
            kind in ("HOLD", "EXIT_NOW")
            and (
                payload.get("management_state") != "PROFIT_LOCKED"
                or not is_safe_integer(extension, nonnegative=True)
            )
        )
    ):
        return False
    start, end, issued, available, expires = (
        payload.get("sample_start_exclusive_us"),
        payload.get("sample_end_inclusive_us"),
        payload.get("issued_at_us"),
        payload.get("lane_available_at_us"),
        payload.get("expires_at_us"),
    )
    if (
        not all(is_safe_integer(value, nonnegative=True) for value in (start, end, issued, available, expires))
        or not start < end < issued <= available <= expires
        or expires - issued != 30_000_000
    ):
        return False
    observations = _array(payload.get("observations"))
    counts = _mapping(payload.get("class_counts"))
    if observations is None or not exact_keys(counts, _CLASS_COUNTS):
        return False
    sort_keys: list[tuple[Any, Any, Any]] = []
    values: list[str] = []
    calculated_counts = {name: 0 for name in _CLASS_COUNTS}
    for observation in observations:
        if not exact_keys(
            observation,
            (
                "observation_id",
                "opportunity_id",
                "terminal_at_us",
                "label_tail_us",
                "label_record_sha256",
                "y_r",
                "terminal_class",
                "bindings_sha256",
            ),
        ):
            return False
        terminal, tail = observation.get("terminal_at_us"), observation.get("label_tail_us")
        terminal_class = observation.get("terminal_class")
        if (
            not is_safe_integer(terminal, nonnegative=True)
            or not is_safe_integer(tail, nonnegative=True)
            or not start < terminal
            or terminal + tail > end
            or terminal_class not in _CLASS_COUNTS
            or not validate_decimal("DecimalString", observation.get("y_r"))
        ):
            return False
        y = parse_decimal(observation["y_r"])
        if y < -1 or y > 3:
            return False
        binding_preimage = {
            "composite_theory_id": composite_theory_id,
            "venue_id": payload.get("venue_id"),
            "instrument_id": payload.get("instrument_id"),
            "lane_id": payload.get("lane_id"),
            "availability_kind": payload.get("availability_kind"),
            "evidence_kind": kind,
            "candidate_id": payload.get("candidate_id"),
            "control_id": payload.get("control_id"),
            "side": payload.get("side"),
            "management_state": payload.get("management_state"),
            "relative_anchor_bp_bucket": payload.get("relative_anchor_bp_bucket"),
            "extension_bp_bucket": extension,
            "estimator_policy_sha256": payload.get("estimator_policy_sha256"),
            "cost_policy_sha256": payload.get("cost_policy_sha256"),
            "label_policy_sha256": payload.get("label_policy_sha256"),
            "data_role_sha256": payload.get("data_role_sha256"),
        }
        if observation.get("bindings_sha256") != stable_id(
            "ev-observation-bindings/v0.2.2", binding_preimage
        ):
            return False
        expected_observation_id = stable_id(
            "ev-observation/v0.2.2",
            {
                key: observation.get(key)
                for key in (
                    "opportunity_id",
                    "terminal_at_us",
                    "label_tail_us",
                    "label_record_sha256",
                    "y_r",
                    "terminal_class",
                    "bindings_sha256",
                )
            },
        )
        if observation.get("observation_id") != expected_observation_id:
            return False
        sort_keys.append(
            (
                terminal,
                observation.get("opportunity_id"),
                observation.get("label_record_sha256"),
            )
        )
        values.append(observation["y_r"])
        calculated_counts[terminal_class] += 1
    if sort_keys != sorted(sort_keys) or len(sort_keys) != len(set(sort_keys)):
        return False
    if payload.get("n") != len(observations) or dict(counts) != calculated_counts:
        return False
    calculated_sum = decimal_sum(values)
    if payload.get("sum_y_r") != calculated_sum:
        return False
    if not observations:
        if payload.get("min_y_r") is not None or payload.get("max_y_r") is not None:
            return False
    else:
        numeric = [parse_decimal(value) for value in values]
        if (
            payload.get("min_y_r") != decimal_value(min(numeric))
            or payload.get("max_y_r") != decimal_value(max(numeric))
        ):
            return False
    observation_set = {
        key: payload.get(key)
        for key in (
            "venue_id",
            "instrument_id",
            "lane_id",
            "availability_kind",
            "evidence_kind",
            "candidate_id",
            "control_id",
            "side",
            "management_state",
            "relative_anchor_bp_bucket",
            "extension_bp_bucket",
        )
    }
    observation_set["observations"] = observations
    if payload.get("observations_sha256") != stable_id(
        "ev-observation-set/v0.2.2", observation_set
    ):
        return False
    return payload.get("evidence_sha256") == stable_id(
        "frozen-ev-evidence/v0.2.2", _without(payload, "evidence_sha256")
    )


def _walk_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for child in value.values():
            found.extend(_walk_mappings(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_walk_mappings(child))
    return tuple(found)


def _policy_chain_valid(artifacts: Sequence[Mapping[str, Any]]) -> bool:
    for wrapper in artifacts:
        payload = _payload(wrapper)
        if payload is None:
            return False
        for item in _walk_mappings(payload):
            schema = item.get("schema_version")
            domain = _POLICY_DOMAIN_BY_SCHEMA.get(schema)
            if domain is not None and item.get("policy_sha256") != stable_id(
                domain, _without(item, "policy_sha256")
            ):
                return False
            if "parameter_set_sha256" in item and set(item) >= {
                "parameter_set_sha256",
                "candidate_kind",
            }:
                if item.get("parameter_set_sha256") != stable_id(
                    "candidate-parameter-set/v0.2.2",
                    _without(item, "parameter_set_sha256"),
                ):
                    return False
            if "policy_bundle_sha256" in item and set(item) >= {
                "u_policy_sha256",
                "entry_policy_sha256",
                "exit_policy_template_sha256",
                "cost_policy_sha256",
                "risk_policy_sha256",
                "label_policy_sha256",
                "data_role_sha256",
                "estimator_policy_sha256",
            }:
                expected = stable_id(
                    "candidate-policy-bundle/v0.2.2",
                    _without(item, "policy_bundle_sha256"),
                )
                if item.get("policy_bundle_sha256") != expected:
                    return False
            if schema == "rsi-mtf-drl-pm.policy-registry.v0.2.2":
                if item.get("registry_sha256") != stable_id(
                    "policy-registry/v0.2.2", _without(item, "registry_sha256")
                ):
                    return False
                parameter = _mapping(item.get("parameter_set"))
                policy_bundle = _mapping(item.get("policy_bundle"))
                if parameter is None or policy_bundle is None:
                    return False
                expected_candidate = stable_id(
                    "rsi-mtf-drl-pm-candidate/v0.2.2",
                    {
                        "composite_theory_id": item.get("composite_theory_id"),
                        "parameter_set_sha256": parameter.get("parameter_set_sha256"),
                        "policy_bundle_sha256": policy_bundle.get("policy_bundle_sha256"),
                    },
                )
                if item.get("candidate_id") != expected_candidate:
                    return False
    return True


def _wrapper_time(schema_id: str, payload: Mapping[str, Any]) -> Any:
    if schema_id in _STATIC_POLICY_SCHEMAS:
        return None
    if schema_id in ("SYNTHETIC_FIXTURE_MANIFEST", "C4_C5_EXOGENOUS_PATH_MANIFEST"):
        return None
    if schema_id in (
        "CLOSED_MARK_BAR",
        "BOOK_SNAPSHOT",
        "AGG_TRADE",
        "OPEN_INTEREST",
        "SOURCE_COVERAGE_SEAL",
        "VENUE_INSTRUMENT_SNAPSHOT",
        "ACCOUNT_RISK_SNAPSHOT",
        "FROZEN_EV_EVIDENCE",
    ):
        return payload.get("lane_available_at_us")
    if schema_id == "U_OBSERVATION_RECEIPT":
        return payload.get("evaluation_at_us")
    if schema_id == "DECISION_INPUT_BINDING":
        return payload.get("decision_at_us")
    if schema_id == "SHARED_ENTRY_ACTION":
        return payload.get("action_at_us")
    return payload.get("available_at_us")


def _artifact_wrapper_valid(wrapper: Mapping[str, Any]) -> bool:
    if not exact_keys(wrapper, _WRAPPER_KEYS):
        return False
    schema_id = wrapper.get("schema_id")
    payload = _payload(wrapper)
    if schema_id not in _ARTIFACT_SCHEMA_IDS or payload is None:
        return False
    if wrapper.get("payload_sha256") != sha256_json(payload):
        return False
    if schema_id in _STATIC_POLICY_SCHEMAS:
        if wrapper.get("artifact_scope_id") is not None or wrapper.get("available_at_us") is not None:
            return False
    else:
        if not is_sha256(wrapper.get("artifact_scope_id")):
            return False
        if all(key in payload for key in _SCOPE_KEYS):
            expected_scope = stable_id(
                "synthetic-artifact-scope/v0.2.2",
                _scope_preimage(payload),
            )
            if wrapper.get("artifact_scope_id") != expected_scope:
                return False
        if schema_id not in (
            "SYNTHETIC_FIXTURE_MANIFEST",
            "C4_C5_EXOGENOUS_PATH_MANIFEST",
            "EXIT_POLICY_INSTANCE",
            "SYNTHETIC_FUNDING_OBSERVATION",
            "SYNTHETIC_CONFLICT_PROOF",
        ) and wrapper.get("available_at_us") != _wrapper_time(schema_id, payload):
            return False
    return wrapper.get("artifact_id") == stable_id(
        "synthetic-artifact/v0.2.2",
        {
            "artifact_scope_id": wrapper.get("artifact_scope_id"),
            "schema_id": schema_id,
            "available_at_us": wrapper.get("available_at_us"),
            "payload_sha256": wrapper.get("payload_sha256"),
        },
    )


def _c01_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    by_id = {item.get("artifact_id"): item for item in artifacts}
    for wrapper in artifacts:
        if wrapper.get("schema_id") != "SOURCE_COVERAGE_SEAL":
            continue
        seal = _payload(wrapper)
        if seal is None:
            continue
        covered_kind = seal.get("covered_object_kind")
        for source_id in seal.get("covered_event_ids", ()):
            source = by_id.get(source_id)
            if source is not None and source.get("schema_id") != covered_kind:
                return True
    return False


def _c02_violation(bundle: Mapping[str, Any]) -> bool:
    identity = _mapping(bundle.get("ledger_identity"))
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if identity is None or artifacts is None:
        return False
    expected = (
        identity.get("venue_id"),
        identity.get("instrument_id"),
        identity.get("lane_id"),
        "SYNTHETIC",
    )
    manifest_wrappers = [
        wrapper
        for wrapper in artifacts
        if wrapper.get("schema_id") == "SYNTHETIC_FIXTURE_MANIFEST"
    ]
    diagnostic_ids: set[Any] = set()
    manifest_source_ids: set[Any] = set()
    for wrapper in manifest_wrappers:
        payload = _payload(wrapper)
        if payload is not None:
            values = _array(payload.get("diagnostic_artifact_ids"))
            if values is not None:
                diagnostic_ids.update(values)
            source_ids = _array(payload.get("source_artifact_ids"))
            if source_ids is not None:
                manifest_source_ids.update(source_ids)
    if diagnostic_ids.intersection(manifest_source_ids):
        return True
    events = _array(bundle.get("event_array")) or ()
    wrappers_by_id = {wrapper.get("artifact_id"): wrapper for wrapper in artifacts}
    for diagnostic_id in diagnostic_ids:
        diagnostic = wrappers_by_id.get(diagnostic_id)
        diagnostic_payload = (
            _payload(diagnostic) if diagnostic is not None else None
        )
        if (
            diagnostic is None
            or diagnostic.get("schema_id") != "ACCOUNT_RISK_SNAPSHOT"
            or diagnostic_payload is None
            or (
                _scope(diagnostic_payload) == expected
                and diagnostic_payload.get("account_scope_id")
                == identity.get("account_scope_id")
            )
        ):
            return True

    def contains_artifact_id(value: Any, artifact_id: Any) -> bool:
        if isinstance(value, Mapping):
            return any(
                contains_artifact_id(child, artifact_id)
                for child in value.values()
            )
        if isinstance(value, (list, tuple)):
            return any(contains_artifact_id(child, artifact_id) for child in value)
        return value == artifact_id

    for wrapper in artifacts:
        if wrapper.get("schema_id") in _STATIC_POLICY_SCHEMAS:
            continue
        payload = _payload(wrapper)
        if payload is None or not all(key in payload for key in _SCOPE_KEYS):
            continue
        account_scope_mismatch = (
            wrapper.get("schema_id") == "ACCOUNT_RISK_SNAPSHOT"
            and payload.get("account_scope_id") != identity.get("account_scope_id")
        )
        if _scope(payload) == expected and not account_scope_mismatch:
            continue
        artifact_id = wrapper.get("artifact_id")
        if (
            wrapper.get("schema_id") != "ACCOUNT_RISK_SNAPSHOT"
            or artifact_id not in diagnostic_ids
        ):
            return True
        consumers = [
            event
            for event in events
            if artifact_id in event.get("input_artifact_ids", ())
        ]
        if len(consumers) != 1:
            return True
        consumer = consumers[0]
        consumer_payload = _mapping(consumer.get("payload"))
        if (
            consumer.get("event_kind") != "ACCOUNT_MISMATCH"
            or consumer_payload is None
            or consumer_payload.get("reason_code") != "SNAPSHOT_SCOPE_MISMATCH"
            or any(
                consumer_payload.get(key) is not None
                for key in (
                    "snapshot_id",
                    "account_scope_id",
                    "observed_position_qty",
                    "observed_position_vwap",
                )
            )
        ):
            return True
        if any(
            contains_artifact_id(_payload(candidate), artifact_id)
            for candidate in artifacts
            if candidate is not wrapper
            and candidate.get("schema_id") != "SYNTHETIC_FIXTURE_MANIFEST"
            and _payload(candidate) is not None
        ):
            return True
        if contains_artifact_id(bundle.get("entry_execution_binding"), artifact_id):
            return True
    return False


def _c03_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    for seal_wrapper in artifacts:
        if seal_wrapper.get("schema_id") != "SOURCE_COVERAGE_SEAL":
            continue
        seal = _payload(seal_wrapper)
        if seal is None or not _coverage_shape_valid(seal):
            return True
        binding = {
            "coverage_seal_artifact_id": seal_wrapper.get("artifact_id"),
            "coverage_seal_sha256": seal.get("seal_sha256"),
            **{
                key: seal.get(key)
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                    "source_id",
                    "source_schema_version",
                    "covered_object_kind",
                    "window_start_exclusive_us",
                    "window_end_inclusive_us",
                    "lane_available_at_us",
                )
            },
        }
        sources = [
            item
            for item in artifacts
            if item.get("schema_id") == seal.get("covered_object_kind")
        ]
        if not _validate_coverage_seal(sources, seal_wrapper, binding):
            return True
    return False


def _c04_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    for wrapper in artifacts:
        if wrapper.get("schema_id") != "CLOSED_MARK_BAR":
            continue
        payload = _payload(wrapper)
        if payload is not None and all(
            is_safe_integer(payload.get(key), nonnegative=True)
            for key in ("bar_close_at_us", "closed_at_us", "lane_available_at_us")
        ):
            if not (
                payload.get("bar_close_at_us")
                <= payload.get("closed_at_us")
                <= payload.get("lane_available_at_us")
            ):
                return True
    return False


def _c08_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    composite = None
    identity = _mapping(bundle.get("ledger_bindings"))
    if identity is not None:
        composite = identity.get("composite_theory_id")
    for wrapper in artifacts:
        if wrapper.get("schema_id") == "FROZEN_EV_EVIDENCE":
            payload = _payload(wrapper)
            if payload is not None and not _ev_evidence_valid(payload, composite):
                return True
    return False


def _c10_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    ids = {item.get("artifact_id") for item in artifacts}
    for event in bundle.get("event_array", ()):
        if not isinstance(event, Mapping) or event.get("event_kind") != "BARRIER_EVALUATION":
            continue
        payload = _mapping(event.get("payload"))
        if payload is None:
            continue
        for binding in payload.get("candidate_evidence_bindings", ()):
            if not isinstance(binding, Mapping):
                continue
            for key in ("hold_evidence_artifact_id", "exit_now_evidence_artifact_id"):
                if not is_sha256(binding.get(key)) or binding.get(key) not in ids:
                    return True
    return False


def _c13_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    return artifacts is not None and not _policy_chain_valid(artifacts)


def _c14_violation(bundle: Mapping[str, Any]) -> bool:
    return any(
        isinstance(event, Mapping)
        and event.get("event_kind")
        in ("MASTER_CREATED", "DEDUP_ATTACHED", "COOLDOWN_SUPPRESSED")
        for event in bundle.get("event_array", ())
    )


def _c17_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    for wrapper in artifacts:
        schema_id = wrapper.get("schema_id")
        payload = _payload(wrapper)
        if payload is None or schema_id in _STATIC_POLICY_SCHEMAS:
            continue
        if all(key in payload for key in _SCOPE_KEYS):
            expected_scope = stable_id(
                "synthetic-artifact-scope/v0.2.2", _scope_preimage(payload)
            )
            if wrapper.get("artifact_scope_id") != expected_scope:
                return True
        if (
            is_sha256(wrapper.get("payload_sha256"))
            and wrapper.get("artifact_id")
            != stable_id(
                "synthetic-artifact/v0.2.2",
                {
                    "artifact_scope_id": wrapper.get("artifact_scope_id"),
                    "schema_id": schema_id,
                    "available_at_us": wrapper.get("available_at_us"),
                    "payload_sha256": wrapper.get("payload_sha256"),
                },
            )
        ):
            return True
    return False


def _c18_violation(
    bundle: Mapping[str, Any], role: Any
) -> bool:
    if role != "SYNTHETIC":
        return isinstance(role, str)
    identity = _mapping(bundle.get("ledger_identity"))
    if identity is not None and identity.get("role") != "SYNTHETIC":
        return True
    for item in _walk_mappings(bundle):
        if item.get("role") in ("DEVELOPMENT", "CALIBRATION", "HOLDOUT", "PAPER", "TRADING"):
            return True
        if item.get("availability_kind") in ("ACTUAL", "RECONSTRUCTED"):
            return True
    return False


def _c19_violation(bundle: Mapping[str, Any]) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    if artifacts is None:
        return False
    for wrapper in artifacts:
        kind = wrapper.get("schema_id")
        payload = _payload(wrapper)
        if kind in _SOURCE_KINDS and payload is not None:
            if not is_sha256(payload.get(_GENERATION_FIELD[kind])):
                return True
        if kind == "SOURCE_COVERAGE_SEAL" and payload is not None:
            ranges = _array(payload.get("generation_ranges"))
            if ranges is None:
                continue
            for item in ranges:
                if not isinstance(item, Mapping) or not is_sha256(item.get("generation_id")):
                    return True
                first, last, count = (
                    item.get("first_source_sequence"),
                    item.get("last_source_sequence"),
                    item.get("event_count"),
                )
                if (
                    not is_safe_integer(first, nonnegative=True)
                    or not is_safe_integer(last, nonnegative=True)
                    or not is_safe_integer(count, nonnegative=True)
                    or last < first
                    or count != last - first + 1
                ):
                    return True
    return False


_SEED_KEYS = (
    "schema_version",
    "opportunity_id",
    "control_id",
    "candidate_id",
    "side",
    "anchor_at_us",
    "anchor_status",
    "anchor_price",
    "cost_basis",
    "policy_bindings",
    "master_u_receipt_sha256",
    "seed_sha256",
)
_SEED_POLICY_KEYS = (
    "u_policy_sha256",
    "entry_policy_sha256",
    "exit_policy_template_sha256",
    "cost_policy_sha256",
    "risk_policy_sha256",
    "label_policy_sha256",
    "data_role_sha256",
    "estimator_policy_sha256",
    "source_selector_policy_sha256",
    "reducer_priority_policy_sha256",
    "policy_bundle_sha256",
)
_ACTION_CONTEXT_KEYS = (
    "schema_version",
    "ledger_seed_sha256",
    "decision_kind",
    "action_at_us",
    "entry_mode",
    "shared_entry_action_sha256",
    "initial_levels",
    "risk_basis",
    "decision_input_binding_artifact_id",
    "decision_input_binding_sha256",
    "decision_result_sha256",
    "action_context_sha256",
)
_DECISION_INPUT_BINDING_KEYS = (
    "schema_version",
    "venue_id",
    "instrument_id",
    "lane_id",
    "availability_kind",
    "opportunity_id",
    "control_id",
    "side",
    "candidate_id",
    "decision_kind",
    "decision_at_us",
    "named_artifact_bindings",
    "selector_bindings",
    "source_artifact_ids",
    "source_artifact_set_sha256",
    "calculator_policy_bundle_sha256",
    "decision_result_sha256",
    "proof_sha256",
)
_POLICY_REGISTRY_KEYS = (
    "schema_version",
    "composite_theory_id",
    "v0_2_controls_sha256",
    "v0_2_entry_contract_sha256",
    "v0_2_risk_execution_contract_sha256",
    "v0_2_label_contract_sha256",
    "parameter_set",
    "u_policy",
    "entry_policy",
    "exit_policy_template",
    "cost_policy",
    "risk_policy",
    "label_policy",
    "data_role_policy",
    "estimator_policy",
    "source_selector_policy",
    "policy_bundle",
    "candidate_id",
    "registry_sha256",
)
_FIXTURE_MANIFEST_KEYS = (
    "schema_version",
    "composite_theory_id",
    "role",
    "availability_kind",
    "venue_id",
    "instrument_id",
    "lane_id",
    "generator_policy",
    "generator_policy_sha256",
    "source_queries",
    "source_artifact_ids",
    "diagnostic_artifact_ids",
    "source_artifact_set_sha256",
    "manifest_sha256",
)
_FIXTURE_QUERY_KEYS = (
    "closed_mark_bar_15m",
    "closed_mark_bar_4h",
    "book",
    "agg_trade",
    "open_interest",
    "account",
)


def _artifact_payload_schema_shape(wrapper: Mapping[str, Any]) -> bool:
    schema_id = wrapper.get("schema_id")
    payload = _payload(wrapper)
    if payload is None:
        return False
    if schema_id in _SOURCE_KINDS:
        return exact_keys(payload, _SOURCE_EXACT_KEYS[schema_id])
    if schema_id == "SOURCE_COVERAGE_SEAL":
        return _coverage_shape_valid(payload)
    if schema_id == "VENUE_INSTRUMENT_SNAPSHOT":
        return exact_keys(
            payload,
            (
                "schema_version",
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
                "contract_kind",
                "effective_at_us",
                "lane_available_at_us",
                "tick_size",
                "lot_step",
                "min_qty",
                "max_qty",
                "min_notional_usdt",
                "max_notional_usdt",
                "max_leverage",
                "initial_margin_rate",
                "fee_bps_per_side",
                "rule_fingerprint_sha256",
                "quality",
                "payload_sha256",
                "snapshot_id",
            ),
        )
    if schema_id == "ACCOUNT_RISK_SNAPSHOT":
        return exact_keys(
            payload,
            (
                "schema_version",
                "account_scope_id",
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
                "source_id",
                "effective_at_us",
                "lane_available_at_us",
                "equity_usdt",
                "available_balance_usdt",
                "existing_initial_margin_usdt",
                "open_order_reserve_usdt",
                "pending_fee_reserve_usdt",
                "position_qty_base",
                "position_vwap",
                "open_order_ids",
                "quality",
                "payload_sha256",
                "snapshot_id",
            ),
        )
    if schema_id == "FROZEN_EV_EVIDENCE":
        return payload.get("schema_version") == "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2"
    if schema_id == "REDUCER_PRIORITY_POLICY":
        return exact_keys(
            payload,
            (
                "schema_version",
                "event_rank",
                "stop_ack_rank_predicate",
                "tie_break",
                "unknown_event_action",
                "policy_sha256",
            ),
        )
    if schema_id == "U_OBSERVATION_RECEIPT":
        return exact_keys(
            payload,
            (
                "schema_version",
                "event_kind",
                "venue_id",
                "instrument_id",
                "lane_id",
                "role",
                "cycle_start_us",
                "grid_close_us",
                "evaluation_at_us",
                "master_opportunity_id",
                "parent_master_receipt_id",
                "u_policy_sha256",
                "input_bar_id",
                "receipt_sha256",
            ),
        )
    if schema_id == "SYNTHETIC_FIXTURE_MANIFEST":
        return exact_keys(payload, _FIXTURE_MANIFEST_KEYS)
    if schema_id == "POLICY_REGISTRY":
        return exact_keys(payload, _POLICY_REGISTRY_KEYS)
    if schema_id == "DECISION_INPUT_BINDING":
        return exact_keys(payload, _DECISION_INPUT_BINDING_KEYS)
    if schema_id == "SHARED_ENTRY_ACTION":
        return exact_keys(
            payload,
            (
                "schema_version",
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
                "source_control_id",
                "opportunity_id",
                "candidate_id",
                "side",
                "anchor_at_us",
                "anchor_price",
                "action_at_us",
                "p_limit",
                "submitted_qty",
                "expires_at_us",
                "initial_levels",
                "risk_basis",
                "entry_policy_sha256",
                "decision_input_binding_artifact_id",
                "decision_input_binding_sha256",
                "decision_result_sha256",
                "entry_action_sha256",
            ),
        )
    return isinstance(payload, Mapping) and isinstance(payload.get("schema_version"), str)


def _bundle_schema_valid(bundle: Mapping[str, Any]) -> bool:
    if not exact_keys(bundle, _BUNDLE_KEYS):
        return False
    if bundle.get("schema_version") != "rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.2":
        return False
    identity = _mapping(bundle.get("ledger_identity"))
    bindings = _mapping(bundle.get("ledger_bindings"))
    seed = _mapping(bundle.get("ledger_seed"))
    coverage = _mapping(bundle.get("coverage"))
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    events = _array(bundle.get("event_array"))
    if (
        not exact_keys(identity, _IDENTITY_KEYS)
        or not exact_keys(bindings, _LEDGER_BINDING_KEYS)
        or not exact_keys(seed, _SEED_KEYS)
        or not exact_keys(coverage, _COVERAGE_KEYS)
        or artifacts is None
        or events is None
    ):
        return False
    if (
        identity.get("control_id") not in ("C0", "C1", "C2", "C3", "C4", "Cmu", "C5")
        or identity.get("role") != "SYNTHETIC"
        or identity.get("lane_id") != _SYNTHETIC_LANE
        or not all(is_sha256(bindings.get(key)) for key in _LEDGER_BINDING_KEYS)
        or not all(is_sha256(identity.get(key)) for key in ("episode_id", "opportunity_id", "candidate_id"))
        or not is_safe_integer(bundle.get("finalized_at_us"), nonnegative=True)
    ):
        return False
    if (
        seed.get("schema_version") != "rsi-mtf-drl-pm.frozen-ledger-seed.v0.2.2"
        or not exact_keys(seed.get("policy_bindings"), _SEED_POLICY_KEYS)
        or not all(is_sha256(seed["policy_bindings"].get(key)) for key in _SEED_POLICY_KEYS)
        or seed.get("anchor_status") not in ("VALID", "UNKNOWN")
        or seed.get("side") not in ("LONG", "SHORT", "NONE")
        or not is_safe_integer(seed.get("anchor_at_us"), nonnegative=True)
        or not is_sha256(seed.get("seed_sha256"))
        or not is_sha256(seed.get("master_u_receipt_sha256"))
    ):
        return False
    if (
        (seed.get("anchor_status") == "VALID")
        != validate_decimal("Price", seed.get("anchor_price"))
        or (seed.get("anchor_status") == "UNKNOWN")
        != (seed.get("anchor_price") is None)
    ):
        return False
    context = bundle.get("action_context")
    if context is not None:
        if not exact_keys(context, _ACTION_CONTEXT_KEYS):
            return False
        if (
            context.get("schema_version")
            != "rsi-mtf-drl-pm.frozen-action-context.v0.2.2"
            or context.get("decision_kind") not in ("ENTRY", "ABSTAIN")
            or not is_safe_integer(context.get("action_at_us"), nonnegative=True)
            or not is_sha256(context.get("action_context_sha256"))
        ):
            return False
    if identity.get("control_id") == "C0":
        if (
            context is not None
            or bundle.get("entry_execution_binding") is not None
            or seed.get("side") != "NONE"
            or coverage.get("status") != "COMPLETE"
        ):
            return False
    elif seed.get("side") not in ("LONG", "SHORT"):
        return False
    for wrapper in artifacts:
        if (
            not exact_keys(wrapper, _WRAPPER_KEYS)
            or wrapper.get("schema_id") not in _ARTIFACT_SCHEMA_IDS
            or not is_sha256(wrapper.get("artifact_id"))
            or not is_sha256(wrapper.get("payload_sha256"))
            or not _artifact_payload_schema_shape(wrapper)
        ):
            return False
    artifact_ids = [item.get("artifact_id") for item in artifacts]
    if artifact_ids != sorted(artifact_ids) or len(artifact_ids) != len(set(artifact_ids)):
        return False
    if coverage.get("status") not in ("COMPLETE", "CENSORED"):
        return False
    for key in ("expected_grid_times_us", "observed_grid_times_us", "missing_grid_times_us"):
        values = _array(coverage.get(key))
        if (
            values is None
            or not all(is_safe_integer(value, nonnegative=True) for value in values)
            or list(values) != sorted(set(values))
        ):
            return False
    if not all(is_safe_integer(coverage.get(key), nonnegative=True) for key in ("window_start_exclusive_us", "window_end_inclusive_us", "event_count", "artifact_count")):
        return False
    for event in events:
        if (
            not exact_keys(event, _EVENT_KEYS)
            or event.get("event_kind") not in _REDUCER_KINDS
            or not isinstance(event.get("payload"), Mapping)
            or not is_sha256(event.get("payload_sha256"))
            or not is_sha256(event.get("source_event_id"))
            or not is_safe_integer(event.get("event_time_us"), nonnegative=True)
            or not is_safe_integer(event.get("lane_available_at_us"), nonnegative=True)
            or not is_safe_integer(event.get("priority_rank"), nonnegative=True)
            or not is_safe_integer(event.get("source_sequence"), nonnegative=True)
        ):
            return False
        for key in ("predecessor_event_ids", "input_artifact_ids"):
            values = _array(event.get(key))
            if (
                values is None
                or not all(is_sha256(value) for value in values)
                or list(values) != sorted(set(values))
            ):
                return False
    return True


def _artifact_payload_digest_valid(
    wrapper: Mapping[str, Any], composite_theory_id: Any
) -> bool:
    schema_id = wrapper.get("schema_id")
    payload = _payload(wrapper)
    if payload is None:
        return False
    if wrapper.get("payload_sha256") != sha256_json(payload):
        return False
    if schema_id in _SOURCE_KINDS:
        return _source_payload_valid(schema_id, payload)
    if schema_id == "SOURCE_COVERAGE_SEAL":
        return payload.get("seal_sha256") == stable_id(
            "source-coverage-seal/v0.2.2", _without(payload, "seal_sha256")
        )
    if schema_id == "VENUE_INSTRUMENT_SNAPSHOT":
        return _venue_payload_valid(payload)
    if schema_id == "ACCOUNT_RISK_SNAPSHOT":
        return _account_payload_valid(payload)
    if schema_id == "FROZEN_EV_EVIDENCE":
        return _ev_evidence_valid(payload, composite_theory_id)
    digest_domains = {
        "U_OBSERVATION_RECEIPT": ("receipt_sha256", "u-observation-receipt/v0.2.2"),
        "SYNTHETIC_FIXTURE_MANIFEST": ("manifest_sha256", "synthetic-fixture-manifest/v0.2.2"),
        "POLICY_REGISTRY": ("registry_sha256", "policy-registry/v0.2.2"),
        "REDUCER_PRIORITY_POLICY": ("policy_sha256", "reducer-priority-policy/v0.2.2"),
        "PI_EXIT_POLICY": ("policy_sha256", "pi-exit-policy/v0.2.2"),
        "FIRST_HIT_LABEL_POLICY": ("policy_sha256", "first-hit-label-policy/v0.2.2"),
        "DECISION_INPUT_BINDING": ("proof_sha256", "decision-input-binding/v0.2.2"),
        "SHARED_ENTRY_ACTION": ("entry_action_sha256", "shared-entry-action/v0.2.2"),
        "EXIT_POLICY_INSTANCE": ("policy_instance_sha256", "exit-policy-instance/v0.2.2"),
        "C4_C5_EXOGENOUS_PATH_MANIFEST": (
            "manifest_sha256",
            "c4-c5-exogenous-path-manifest/v0.2.2",
        ),
        "SYNTHETIC_CONFLICT_PROOF": ("proof_sha256", "synthetic-conflict-proof/v0.2.2"),
    }
    if schema_id in digest_domains:
        key, domain = digest_domains[schema_id]
        return payload.get(key) == stable_id(domain, _without(payload, key))
    if schema_id == "SYNTHETIC_FUNDING_OBSERVATION":
        return payload.get("funding_event_id") == stable_id(
            "synthetic-funding/v0.2.2",
            {
                "venue_id": payload.get("venue_id"),
                "instrument_id": payload.get("instrument_id"),
                "lane_id": payload.get("lane_id"),
                "interval_start_us": payload.get("interval_start_us"),
                "interval_end_us": payload.get("interval_end_us"),
            },
        )
    return False


def _bundle_digest_valid(
    contract: Mapping[str, Any], bundle: Mapping[str, Any]
) -> bool:
    bindings = _mapping(bundle.get("ledger_bindings"))
    seed = _mapping(bundle.get("ledger_seed"))
    coverage = _mapping(bundle.get("coverage"))
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    events = _array(bundle.get("event_array"))
    if None in (bindings, seed, coverage, artifacts, events):
        return False
    contract_digest = sha256_json(contract)
    if bindings.get("v0_2_2_contract_sha256") != contract_digest:
        return False
    if bindings.get("composite_theory_id") != contract.get("composite_theory_id"):
        return False
    if seed.get("seed_sha256") != stable_id(
        "frozen-ledger-seed/v0.2.2", _without(seed, "seed_sha256")
    ):
        return False
    context = bundle.get("action_context")
    if context is not None and context.get("action_context_sha256") != stable_id(
        "frozen-action-context/v0.2.2", _without(context, "action_context_sha256")
    ):
        return False
    for wrapper in artifacts:
        if not _artifact_payload_digest_valid(
            wrapper, bindings.get("composite_theory_id")
        ) or not _artifact_wrapper_valid(wrapper):
            return False
    for event in events:
        if event.get("payload_sha256") != sha256_json(event.get("payload")):
            return False
        event_preimage = {
            "bundle_scope_id": bundle.get("bundle_scope_id"),
            **{
                key: event.get(key)
                for key in (
                    "event_kind",
                    "event_time_us",
                    "lane_available_at_us",
                    "economic_event_time_us",
                    "priority_rank",
                    "source_sequence",
                    "predecessor_event_ids",
                    "input_artifact_ids",
                    "shared_entry_event_id",
                    "request_id",
                    "order_id",
                    "payload_sha256",
                )
            },
        }
        if event.get("source_event_id") != stable_id(
            "canonical-synthetic-event/v0.2.2", event_preimage
        ):
            return False
    event_set = stable_id("canonical-synthetic-event-set/v0.2.2", events)
    artifact_set = stable_id("canonical-synthetic-artifact-set/v0.2.2", artifacts)
    if (
        bundle.get("event_set_sha256") != event_set
        or coverage.get("event_set_sha256") != event_set
        or coverage.get("artifact_set_sha256") != artifact_set
        or coverage.get("coverage_sha256")
        != stable_id(
            "canonical-synthetic-coverage/v0.2.2",
            _without(coverage, "coverage_sha256"),
        )
    ):
        return False
    return bundle.get("bundle_sha256") == stable_id(
        "canonical-synthetic-event-bundle/v0.2.2",
        _without(bundle, "bundle_sha256"),
    )


def _bundle_binding_valid(bundle: Mapping[str, Any], as_of_us: int) -> bool:
    identity = _mapping(bundle.get("ledger_identity"))
    bindings = _mapping(bundle.get("ledger_bindings"))
    seed = _mapping(bundle.get("ledger_seed"))
    coverage = _mapping(bundle.get("coverage"))
    artifacts = _artifact_sequence(bundle.get("artifacts"))
    events = _array(bundle.get("event_array"))
    if None in (identity, bindings, seed, coverage, artifacts, events):
        return False
    if (
        seed.get("opportunity_id") != identity.get("opportunity_id")
        or seed.get("control_id") != identity.get("control_id")
        or seed.get("candidate_id") != identity.get("candidate_id")
        or bindings.get("ledger_seed_sha256") != seed.get("seed_sha256")
        or bindings.get("policy_bundle_sha256")
        != seed.get("policy_bindings", {}).get("policy_bundle_sha256")
        or not is_sha256(bindings.get("code_sha256"))
    ):
        return False
    expected_scope = stable_id(
        "canonical-synthetic-bundle-scope/v0.2.2",
        {
            "ledger_identity": identity,
            "ledger_seed_sha256": seed.get("seed_sha256"),
            "policy_bundle_sha256": bindings.get("policy_bundle_sha256"),
        },
    )
    if bundle.get("bundle_scope_id") != expected_scope:
        return False
    artifact_ids = {item.get("artifact_id") for item in artifacts}
    event_ids = {item.get("source_event_id") for item in events}
    if len(event_ids) != len(events):
        return False
    for event in events:
        if (
            event.get("venue_id") != identity.get("venue_id")
            or event.get("instrument_id") != identity.get("instrument_id")
            or event.get("episode_id") != identity.get("episode_id")
            or event.get("opportunity_id") != identity.get("opportunity_id")
            or event.get("control_id") != identity.get("control_id")
            or event.get("candidate_id") != identity.get("candidate_id")
            or event.get("lane_available_at_us") != event.get("event_time_us")
            or any(item not in artifact_ids for item in event.get("input_artifact_ids", ()))
            or any(item not in event_ids for item in event.get("predecessor_event_ids", ()))
        ):
            return False
    expected = set(coverage.get("expected_grid_times_us", ()))
    observed = set(coverage.get("observed_grid_times_us", ()))
    missing = set(coverage.get("missing_grid_times_us", ()))
    if (
        observed & missing
        or observed | missing != expected
        or (coverage.get("status") == "COMPLETE") != (not missing)
        or coverage.get("event_count") != len(events)
        or coverage.get("artifact_count") != len(artifacts)
    ):
        return False
    control = identity.get("control_id")
    finalized = bundle.get("finalized_at_us")
    if control == "C0":
        if (
            events
            or artifacts
            or finalized != seed.get("anchor_at_us")
            or coverage.get("window_start_exclusive_us") != finalized
            or coverage.get("window_end_inclusive_us") != finalized
            or expected
            or observed
            or missing
        ):
            return False
    elif not events or finalized != events[-1].get("event_time_us"):
        return False
    if finalized > as_of_us:
        return False
    return True


def validate_bundle(
    contract: Mapping[str, Any],
    bundle: Mapping[str, Any],
    as_of_us: int,
    role: str,
) -> ValidatedBundle | BundleValidationFailure:
    """Validate a closed synthetic bundle, returning the exact closed union."""

    try:
        serialize_contract(contract)
    except Exception:
        return BundleValidationFailure("INVALID", "E_KERNEL_CONTRACT_INVALID")
    try:
        if not isinstance(bundle, Mapping):
            return BundleValidationFailure("INVALID", "E_KERNEL_ARGUMENT_INVALID")
        closure_checks = (
            ("E_C01_MIXED_SOURCE_KIND", lambda: _c01_violation(bundle)),
            ("E_C02_SCOPE_MISMATCH", lambda: _c02_violation(bundle)),
            ("E_C03_COVERAGE_SET_INVALID", lambda: _c03_violation(bundle)),
            ("E_C04_BAR_CAUSALITY_INVALID", lambda: _c04_violation(bundle)),
            ("E_C08_EV_STATS_INCONSISTENT", lambda: _c08_violation(bundle)),
            ("E_C10_TARGET_ARTIFACT_ID_INVALID", lambda: _c10_violation(bundle)),
            ("E_C13_POLICY_DIGEST_MISMATCH", lambda: _c13_violation(bundle)),
            ("E_C14_U_RECEIPT_EVENT_FORBIDDEN", lambda: _c14_violation(bundle)),
            ("E_C17_ARTIFACT_SCOPE_MISMATCH", lambda: _c17_violation(bundle)),
            ("E_C18_ROLE_NOT_SYNTHETIC", lambda: _c18_violation(bundle, role)),
            ("E_C19_GENERATION_CLOSURE_INVALID", lambda: _c19_violation(bundle)),
        )
        for code, predicate in closure_checks:
            if predicate():
                return BundleValidationFailure("INVALID", code)
        if (
            not is_safe_integer(as_of_us, nonnegative=True)
            or not isinstance(role, str)
        ):
            return BundleValidationFailure("INVALID", "E_KERNEL_ARGUMENT_INVALID")
        if not _bundle_schema_valid(bundle):
            return BundleValidationFailure("INVALID", "E_KERNEL_SCHEMA_INVALID")
        if not _bundle_digest_valid(contract, bundle):
            return BundleValidationFailure("INVALID", "E_KERNEL_DIGEST_INVALID")
        if not _bundle_binding_valid(bundle, as_of_us):
            return BundleValidationFailure("INVALID", "E_KERNEL_BINDING_INVALID")
        frozen = _frozen_mapping(bundle)
        return ValidatedBundle(
            "VALID",
            frozen,
            bundle["bundle_sha256"],
            as_of_us,
            role,
        )
    except Exception:
        return BundleValidationFailure("INVALID", "E_KERNEL_ARGUMENT_INVALID")


def _decision_artifacts(artifacts: Any) -> tuple[Mapping[str, Any], ...] | None:
    if isinstance(artifacts, Mapping) and not isinstance(artifacts, ArtifactTuple):
        if not exact_keys(artifacts, ("artifacts",)):
            return None
    elif not isinstance(artifacts, ArtifactTuple):
        return None
    values = _artifact_sequence(artifacts)
    if values is None:
        return None
    ids = [item.get("artifact_id") for item in values]
    if (
        any(not is_sha256(item) for item in ids)
        or len(ids) != len(set(ids))
        or ids != sorted(ids)
    ):
        return None
    return values


def _decision_named(
    binding: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    key: str,
) -> Mapping[str, Any] | None:
    named = _mapping(binding.get("named_artifact_bindings"))
    if named is None:
        return None
    artifact_id = named.get(key)
    if artifact_id is None:
        return None
    return _find_artifact(artifacts, artifact_id)


def _decision_c05_violation(
    binding: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> bool:
    if binding.get("decision_kind") != "ENTRY":
        return False
    actions = [
        _payload(item)
        for item in artifacts
        if item.get("schema_id") == "SHARED_ENTRY_ACTION"
        and (_payload(item) or {}).get("decision_input_binding_sha256")
        == binding.get("proof_sha256")
    ]
    if len(actions) != 1:
        return False
    action = actions[0]
    levels = _mapping(action.get("initial_levels"))
    if levels is None or not validate_decimal("Price", levels.get("g0")):
        return False
    side, p_limit = action.get("side"), action.get("p_limit")
    if side not in ("LONG", "SHORT") or not validate_decimal("Price", p_limit):
        return False
    books = [
        item
        for item in artifacts
        if item.get("schema_id") == "BOOK_SNAPSHOT"
        and item.get("artifact_id") in set(binding.get("source_artifact_ids", ()))
    ]
    if not books:
        return False
    # Every selected source book remains a distinct grid candidate.  Equal
    # prices at distinct source times are intentionally not collapsed here.
    candidates: list[tuple[Decimal, Any, Decimal]] = []
    with localcontext(DECIMAL_CONTEXT):
        p = parse_decimal(p_limit, "Price")
        sign = Decimal(1) if side == "LONG" else Decimal(-1)
        for wrapper in books:
            payload = _payload(wrapper)
            if payload is None:
                continue
            price_text = payload.get("best_bid" if side == "LONG" else "best_ask")
            if not validate_decimal("Price", price_text):
                continue
            price = parse_decimal(price_text, "Price")
            favorable = sign * (price - p)
            if favorable > 0 and favorable * Decimal(10_000) >= p * Decimal(4):
                candidates.append((favorable, payload.get("event_time_us"), price))
    if not candidates:
        return False
    candidates.sort(key=lambda item: (item[0], item[1]))
    return decimal_value(candidates[0][2]) != levels.get("g0")


def _decision_c06_violation(
    binding: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> bool:
    anchor = _decision_named(binding, artifacts, "anchor_venue_snapshot_artifact_id")
    action = _decision_named(binding, artifacts, "action_venue_snapshot_artifact_id")
    if anchor is None or action is None:
        return False
    anchor_payload, action_payload = _payload(anchor), _payload(action)
    if anchor_payload is None or action_payload is None:
        return False
    if not _venue_structurally_valid(action_payload):
        return binding.get("decision_kind") == "ENTRY"
    changed = (
        anchor_payload.get("rule_fingerprint_sha256")
        != action_payload.get("rule_fingerprint_sha256")
    )
    return changed and binding.get("decision_kind") != "ABSTAIN"


def _decision_c07_violation(
    binding: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> bool:
    action = _decision_named(binding, artifacts, "action_account_snapshot_artifact_id")
    if action is None:
        return False
    payload = _payload(action)
    if payload is None:
        return False
    same_scope = [
        item
        for item in artifacts
        if item.get("schema_id") == "ACCOUNT_RISK_SNAPSHOT"
        and (candidate := _payload(item)) is not None
        and candidate.get("account_scope_id") == payload.get("account_scope_id")
        and _scope(candidate) == _scope(payload)
        and candidate.get("source_id") == payload.get("source_id")
        and candidate.get("effective_at_us") == payload.get("effective_at_us")
        and candidate.get("quality") == "VALID"
    ]
    return len({_payload(item).get("payload_sha256") for item in same_scope}) > 1


def _decision_c09_violation(artifacts: Sequence[Mapping[str, Any]]) -> bool:
    for wrapper in artifacts:
        payload = _payload(wrapper)
        if payload is None:
            continue
        bindings = payload.get("candidate_evidence_bindings")
        if bindings is None:
            continue
        values = _array(bindings)
        if values is None:
            return True
        target_ids: list[Any] = []
        for item in values:
            if not exact_keys(
                item,
                (
                    "target_candidate_id",
                    "relative_anchor_bp_bucket",
                    "extension_bp_bucket",
                    "hold_evidence_artifact_id",
                    "hold_evidence_sha256",
                    "hold_selection_key_sha256",
                    "exit_now_evidence_artifact_id",
                    "exit_now_evidence_sha256",
                    "exit_now_selection_key_sha256",
                    "binding_sha256",
                ),
            ):
                return True
            if item.get("binding_sha256") != stable_id(
                "target-candidate-evidence-binding/v0.2.2",
                _without(item, "binding_sha256"),
            ):
                return True
            hold = _find_artifact(artifacts, item.get("hold_evidence_artifact_id"))
            exit_now = _find_artifact(
                artifacts, item.get("exit_now_evidence_artifact_id")
            )
            if (
                hold is None
                or exit_now is None
                or hold.get("schema_id") != "FROZEN_EV_EVIDENCE"
                or exit_now.get("schema_id") != "FROZEN_EV_EVIDENCE"
                or _payload(hold).get("evidence_kind") != "HOLD"
                or _payload(exit_now).get("evidence_kind") != "EXIT_NOW"
            ):
                return True
            pair_fields = (
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
                "candidate_id",
                "control_id",
                "side",
                "management_state",
                "relative_anchor_bp_bucket",
                "extension_bp_bucket",
                "sample_start_exclusive_us",
                "sample_end_inclusive_us",
                "n",
                "estimator_policy_sha256",
                "cost_policy_sha256",
                "label_policy_sha256",
                "data_role_sha256",
            )
            if any(_payload(hold).get(key) != _payload(exit_now).get(key) for key in pair_fields):
                return True
            target_ids.append(item.get("target_candidate_id"))
        ordered = [
            (item.get("target_candidate_id"), item.get("binding_sha256")) for item in values
        ]
        if (
            len(target_ids) != len(set(target_ids))
            or ordered != sorted(ordered)
            or (
                payload.get("target_winner_candidate_id") is not None
                and payload.get("target_winner_candidate_id") not in target_ids
            )
        ):
            return True
    return False


def _decision_c11_violation(
    binding: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> bool:
    selected_values = _array(binding.get("source_artifact_ids"))
    if selected_values is None:
        return False
    selected_ids = set(selected_values)
    oi = [
        item
        for item in artifacts
        if item.get("schema_id") == "OPEN_INTEREST"
        and item.get("artifact_id") in selected_ids
    ]
    if not oi:
        return False
    roots = _decision_root_authorities(binding, artifacts)
    if roots is None:
        # C12 owns a missing or malformed mandatory root authority.
        return False
    manifest = roots["manifest"]
    queries = _mapping(manifest.get("source_queries"))
    query = _mapping(queries.get("open_interest")) if queries is not None else None
    t_us = binding.get("decision_at_us")
    if (
        query is None
        or not exact_keys(query, _SOURCE_QUERY_KEYS)
        or not is_safe_integer(t_us, nonnegative=True)
        or t_us < 960_000_000
    ):
        return True
    manifest_ids = set(manifest.get("source_artifact_ids", ()))
    fixture_artifacts = tuple(
        item for item in artifacts if item.get("artifact_id") in manifest_ids
    )
    seals = [
        item
        for item in fixture_artifacts
        if item.get("schema_id") == "SOURCE_COVERAGE_SEAL"
        and item.get("artifact_id") in selected_ids
        and (payload := _payload(item)) is not None
        and payload.get("covered_object_kind") == "OPEN_INTEREST"
        and payload.get("window_start_exclusive_us") == t_us - 960_000_000
        and payload.get("window_end_inclusive_us") == t_us
        and all(payload.get(key) == query.get(key) for key in _SCOPE_KEYS)
        and payload.get("source_id") == query.get("source_id")
        and payload.get("source_schema_version")
        == query.get("source_schema_version")
    ]
    if len(seals) != 1:
        return True
    seal = seals[0]
    seal_payload = _payload(seal)
    if seal_payload is None:
        return True
    seal_binding = {
        "coverage_seal_artifact_id": seal.get("artifact_id"),
        "coverage_seal_sha256": seal_payload.get("seal_sha256"),
        **{
            key: seal_payload.get(key)
            for key in (
                "venue_id",
                "instrument_id",
                "lane_id",
                "availability_kind",
                "source_id",
                "source_schema_version",
                "covered_object_kind",
                "window_start_exclusive_us",
                "window_end_inclusive_us",
                "lane_available_at_us",
            )
        },
    }
    try:
        endpoints = _validate_oi_completeness(
            fixture_artifacts, query, t_us, seal_binding
        )
    except (TypeError, ValueError):
        return True
    if not isinstance(endpoints, OIEndpointSelection):
        return True
    required_wrapper_ids = {
        endpoints.coverage_seal_artifact.get("artifact_id"),
        endpoints.oi_now_artifact.get("artifact_id"),
        endpoints.oi_prev_artifact.get("artifact_id"),
    }
    if not required_wrapper_ids <= selected_ids:
        return True
    covered_event_ids = set(seal_payload.get("covered_event_ids", ()))
    covered_wrappers = [
        item
        for item in fixture_artifacts
        if item.get("schema_id") == "OPEN_INTEREST"
        and (payload := _payload(item)) is not None
        and payload.get("event_id") in covered_event_ids
    ]
    return (
        len(covered_wrappers) != len(covered_event_ids)
        or any(item.get("artifact_id") not in selected_ids for item in covered_wrappers)
    )


def _decision_binding_digest_valid(binding: Mapping[str, Any]) -> bool:
    named = _mapping(binding.get("named_artifact_bindings"))
    selectors = _mapping(binding.get("selector_bindings"))
    ids = _array(binding.get("source_artifact_ids"))
    if (
        not exact_keys(binding, _DECISION_INPUT_BINDING_KEYS)
        or
        binding.get("schema_version")
        != "rsi-mtf-drl-pm.decision-input-binding.v0.2.2"
        or not exact_keys(
            named,
            (
                "anchor_venue_snapshot_artifact_id",
                "action_venue_snapshot_artifact_id",
                "anchor_account_snapshot_artifact_id",
                "action_account_snapshot_artifact_id",
                "submit_ev_evidence_artifact_id",
                "master_u_receipt_artifact_id",
                "policy_registry_artifact_id",
                "fixture_manifest_artifact_id",
            ),
        )
        or not exact_keys(
            selectors,
            (
                "anchor_account_max_age_us",
                "action_account_max_age_us",
                "submit_ev_selection_key_sha256",
            ),
        )
        or ids is None
        or list(ids) != sorted(set(ids))
        or not all(is_sha256(item) for item in ids)
    ):
        return False
    expected_set = stable_id(
        "decision-source-artifact-set/v0.2.2",
        {
            **{
                key: binding.get(key)
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "availability_kind",
                    "opportunity_id",
                    "control_id",
                    "side",
                    "candidate_id",
                    "decision_at_us",
                )
            },
            "named_artifact_bindings": named,
            "selector_bindings": selectors,
            "source_artifact_ids": ids,
        },
    )
    return (
        binding.get("source_artifact_set_sha256") == expected_set
        and binding.get("proof_sha256")
        == stable_id(
            "decision-input-binding/v0.2.2",
            _without(binding, "proof_sha256"),
        )
    )


def _fixture_manifest_root_valid(payload: Mapping[str, Any]) -> bool:
    if (
        not exact_keys(payload, _FIXTURE_MANIFEST_KEYS)
        or payload.get("schema_version")
        != "rsi-mtf-drl-pm.synthetic-fixture-manifest.v0.2.2"
        or payload.get("role") != "SYNTHETIC"
        or payload.get("availability_kind") != "SYNTHETIC"
        or payload.get("lane_id") != _SYNTHETIC_LANE
    ):
        return False
    scope = _scope_preimage(payload)
    queries = _mapping(payload.get("source_queries"))
    if not exact_keys(queries, _FIXTURE_QUERY_KEYS):
        return False
    schemas = {
        "closed_mark_bar_15m": _SOURCE_SCHEMA["CLOSED_MARK_BAR"],
        "closed_mark_bar_4h": _SOURCE_SCHEMA["CLOSED_MARK_BAR"],
        "book": _SOURCE_SCHEMA["BOOK_SNAPSHOT"],
        "agg_trade": _SOURCE_SCHEMA["AGG_TRADE"],
        "open_interest": _SOURCE_SCHEMA["OPEN_INTEREST"],
        "account": "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
    }
    for key, schema in schemas.items():
        query = _mapping(queries.get(key))
        expected_keys = (
            ("account_scope_id",) + _SOURCE_QUERY_KEYS
            if key == "account"
            else _SOURCE_QUERY_KEYS
        )
        if (
            not exact_keys(query, expected_keys)
            or any(query.get(scope_key) != scope[scope_key] for scope_key in _SCOPE_KEYS)
            or not isinstance(query.get("source_id"), str)
            or not query.get("source_id")
            or query.get("source_schema_version") != schema
        ):
            return False
    generator = _mapping(payload.get("generator_policy"))
    generator_keys = (
        "schema_version",
        "composite_theory_id",
        "generator_kind",
        "randomness_rule",
        "wall_clock_rule",
        "outcome_access_rule",
        "source_schema_versions",
        "policy_sha256",
    )
    expected_source_schemas = [
        "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
        "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
        "rsi-mtf-drl-pm.agg-trade.v0.2.2",
        "rsi-mtf-drl-pm.open-interest.v0.2.2",
        "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2",
        "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2",
        "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
        "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2",
        "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2",
    ]
    if (
        not exact_keys(generator, generator_keys)
        or generator.get("schema_version")
        != "rsi-mtf-drl-pm.synthetic-fixture-generator-policy.v0.2.2"
        or generator.get("composite_theory_id")
        != payload.get("composite_theory_id")
        or generator.get("generator_kind")
        != "DETERMINISTIC_HAND_AUTHORED_E0_FIXTURE"
        or generator.get("randomness_rule") != "FORBIDDEN"
        or generator.get("wall_clock_rule") != "FORBIDDEN"
        or generator.get("outcome_access_rule")
        != "DECISION_INPUTS_CAUSAL_ONLY_FUTURE_EVENTS_PREDECLARED_NOT_READ"
        or materialize(generator.get("source_schema_versions"))
        != expected_source_schemas
        or generator.get("policy_sha256")
        != stable_id(
            "synthetic-fixture-generator-policy/v0.2.2",
            _without(generator, "policy_sha256"),
        )
        or payload.get("generator_policy_sha256")
        != generator.get("policy_sha256")
    ):
        return False
    source_ids = _array(payload.get("source_artifact_ids"))
    diagnostic_ids = _array(payload.get("diagnostic_artifact_ids"))
    if (
        source_ids is None
        or diagnostic_ids is None
        or not all(is_sha256(item) for item in source_ids + diagnostic_ids)
        or list(source_ids) != sorted(set(source_ids))
        or list(diagnostic_ids) != sorted(set(diagnostic_ids))
        or set(source_ids) & set(diagnostic_ids)
    ):
        return False
    expected_set = stable_id(
        "synthetic-fixture-artifact-set/v0.2.2",
        {
            **scope,
            "source_queries": queries,
            "source_artifact_ids": source_ids,
            "diagnostic_artifact_ids": diagnostic_ids,
        },
    )
    return (
        payload.get("source_artifact_set_sha256") == expected_set
        and payload.get("manifest_sha256")
        == stable_id(
            "synthetic-fixture-manifest/v0.2.2",
            _without(payload, "manifest_sha256"),
        )
    )


def _decision_root_authorities(
    binding: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
) -> Mapping[str, Mapping[str, Any]] | None:
    named = _mapping(binding.get("named_artifact_bindings"))
    source_ids = _array(binding.get("source_artifact_ids"))
    if named is None or source_ids is None:
        return None
    mandatory = {
        "master_u_receipt_artifact_id": "U_OBSERVATION_RECEIPT",
        "policy_registry_artifact_id": "POLICY_REGISTRY",
        "fixture_manifest_artifact_id": "SYNTHETIC_FIXTURE_MANIFEST",
    }
    resolved: dict[str, Mapping[str, Any]] = {}
    for key, schema_id in mandatory.items():
        artifact_id = named.get(key)
        wrapper = _find_artifact(artifacts, artifact_id)
        if (
            not is_sha256(artifact_id)
            or artifact_id not in source_ids
            or wrapper is None
            or wrapper.get("schema_id") != schema_id
        ):
            return None
        resolved[key] = wrapper
    if len({item.get("artifact_id") for item in resolved.values()}) != len(
        mandatory
    ):
        return None
    registry = _payload(resolved["policy_registry_artifact_id"])
    manifest = _payload(resolved["fixture_manifest_artifact_id"])
    master = _payload(resolved["master_u_receipt_artifact_id"])
    if (
        registry is None
        or manifest is None
        or master is None
        or not exact_keys(registry, _POLICY_REGISTRY_KEYS)
        or registry.get("schema_version")
        != "rsi-mtf-drl-pm.policy-registry.v0.2.2"
        or not _fixture_manifest_root_valid(manifest)
        or master.get("schema_version")
        != "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2"
        or master.get("event_kind") != "MASTER_CREATED"
        or master.get("role") != "SYNTHETIC"
    ):
        return None
    policy_bundle = _mapping(registry.get("policy_bundle"))
    u_policy = _mapping(registry.get("u_policy"))
    parameter_set = _mapping(registry.get("parameter_set"))
    scope_id = stable_id(
        "synthetic-artifact-scope/v0.2.2",
        {key: binding.get(key) for key in _SCOPE_KEYS},
    )
    if (
        policy_bundle is None
        or u_policy is None
        or parameter_set is None
        or not is_sha256(policy_bundle.get("policy_bundle_sha256"))
        or binding.get("calculator_policy_bundle_sha256")
        != policy_bundle.get("policy_bundle_sha256")
        or binding.get("candidate_id") != registry.get("candidate_id")
        or registry.get("candidate_id")
        != stable_id(
            "rsi-mtf-drl-pm-candidate/v0.2.2",
            {
                "composite_theory_id": registry.get("composite_theory_id"),
                "parameter_set_sha256": parameter_set.get(
                    "parameter_set_sha256"
                ),
                "policy_bundle_sha256": policy_bundle.get(
                    "policy_bundle_sha256"
                ),
            },
        )
        or manifest.get("composite_theory_id")
        != registry.get("composite_theory_id")
        or any(
            binding.get(key) != manifest.get(key)
            for key in ("venue_id", "instrument_id", "lane_id", "availability_kind")
        )
        or resolved["fixture_manifest_artifact_id"].get("artifact_scope_id")
        != scope_id
        or resolved["fixture_manifest_artifact_id"].get("available_at_us")
        is not None
        or resolved["master_u_receipt_artifact_id"].get("artifact_scope_id")
        != scope_id
        or any(
            master.get(key) != binding.get(key)
            for key in ("venue_id", "instrument_id", "lane_id")
        )
        or master.get("master_opportunity_id") != binding.get("opportunity_id")
        or master.get("u_policy_sha256") != u_policy.get("policy_sha256")
        or not is_safe_integer(master.get("evaluation_at_us"), nonnegative=True)
        or not is_safe_integer(binding.get("decision_at_us"), nonnegative=True)
        or master.get("evaluation_at_us") > binding.get("decision_at_us")
        or not all(
            is_safe_integer(master.get(key), nonnegative=True)
            for key in ("cycle_start_us", "grid_close_us")
        )
        or not master.get("cycle_start_us")
        <= master.get("grid_close_us")
        <= master.get("evaluation_at_us")
        or master.get("master_opportunity_id")
        != stable_id(
            "master-opportunity/v0.2.2",
            {
                "u_policy_sha256": master.get("u_policy_sha256"),
                "venue_id": master.get("venue_id"),
                "instrument_id": master.get("instrument_id"),
                "lane_id": master.get("lane_id"),
                "availability_kind": "SYNTHETIC",
                "role": master.get("role"),
                "cycle_start_us": master.get("cycle_start_us"),
            },
        )
        or not _policy_chain_valid(
            (resolved["policy_registry_artifact_id"],)
        )
    ):
        return None
    allowed_source_schemas = frozenset(
        _SOURCE_KINDS
        + (
            "SOURCE_COVERAGE_SEAL",
            "VENUE_INSTRUMENT_SNAPSHOT",
            "ACCOUNT_RISK_SNAPSHOT",
            "FROZEN_EV_EVIDENCE",
            "U_OBSERVATION_RECEIPT",
            "POLICY_REGISTRY",
            "SYNTHETIC_FIXTURE_MANIFEST",
        )
    )
    manifest_source_ids = set(manifest.get("source_artifact_ids", ()))
    mandatory_non_fixture_ids = {
        resolved["policy_registry_artifact_id"].get("artifact_id"),
        resolved["fixture_manifest_artifact_id"].get("artifact_id"),
    }
    if (
        resolved["master_u_receipt_artifact_id"].get("artifact_id")
        not in manifest_source_ids
        or set(source_ids) - mandatory_non_fixture_ids - manifest_source_ids
    ):
        return None
    composite = registry.get("composite_theory_id")
    for artifact_id in source_ids:
        wrapper = _find_artifact(artifacts, artifact_id)
        if (
            wrapper is None
            or wrapper.get("schema_id") not in allowed_source_schemas
            or not _artifact_payload_schema_shape(wrapper)
            or not _artifact_payload_digest_valid(wrapper, composite)
            or not _artifact_wrapper_valid(wrapper)
        ):
            return None
    return {
        "registry_wrapper": resolved["policy_registry_artifact_id"],
        "registry": registry,
        "manifest_wrapper": resolved["fixture_manifest_artifact_id"],
        "manifest": manifest,
        "master_wrapper": resolved["master_u_receipt_artifact_id"],
        "master": master,
    }


def _decision_c12_violation(
    binding: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    as_of_us: Any,
) -> bool:
    if not _decision_binding_digest_valid(binding):
        return True
    roots = _decision_root_authorities(binding, artifacts)
    if roots is None:
        return True
    if binding.get("decision_at_us") != as_of_us:
        return True
    ids = set(binding.get("source_artifact_ids", ()))
    by_id = {item.get("artifact_id"): item for item in artifacts}
    if ids - set(by_id):
        return True
    for artifact_id in ids:
        wrapper = by_id[artifact_id]
        available = wrapper.get("available_at_us")
        if available is not None and available > as_of_us:
            return True
        if wrapper.get("schema_id") in (
            "DECISION_INPUT_BINDING",
            "SHARED_ENTRY_ACTION",
            "EXIT_POLICY_INSTANCE",
            "C4_C5_EXOGENOUS_PATH_MANIFEST",
        ):
            return True
    named = binding.get("named_artifact_bindings", {})
    if any(
        artifact_id is not None and artifact_id not in ids
        for artifact_id in named.values()
    ):
        return True
    if binding.get("decision_kind") == "ENTRY":
        if any(value is None for value in named.values()):
            return True
        actions = [
            _payload(item)
            for item in artifacts
            if item.get("schema_id") == "SHARED_ENTRY_ACTION"
            and (_payload(item) or {}).get("decision_input_binding_sha256")
            == binding.get("proof_sha256")
        ]
        if len(actions) != 1 or actions[0].get("action_at_us") != as_of_us:
            return True
    return False


def _decision_c20_violation(
    binding: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> bool:
    selectors = _mapping(binding.get("selector_bindings"))
    named = _mapping(binding.get("named_artifact_bindings"))
    if selectors is None or named is None:
        return False
    if (
        selectors.get("anchor_account_max_age_us") != 1_000_000
        or selectors.get("action_account_max_age_us") != 1_000_000
    ):
        return True
    roots = _decision_root_authorities(binding, artifacts)
    if roots is None:
        return True
    manifest = roots["manifest"]
    master = roots["master"]
    seed_time = master.get("evaluation_at_us")
    action_time = binding.get("decision_at_us")
    manifest_source_ids = set(manifest.get("source_artifact_ids", ()))
    fixture_artifacts = tuple(
        item
        for item in artifacts
        if item.get("artifact_id") in manifest_source_ids
    )
    input_bar_id = master.get("input_bar_id")
    input_bar = _find_artifact(fixture_artifacts, input_bar_id)
    bar_query = _mapping(
        (_mapping(manifest.get("source_queries")) or {}).get(
            "closed_mark_bar_15m"
        )
    )
    grid_close = master.get("grid_close_us")
    if (
        input_bar is None
        or input_bar.get("schema_id") != "CLOSED_MARK_BAR"
        or bar_query is None
        or not is_safe_integer(grid_close, nonnegative=True)
        or grid_close < 900_000_000
    ):
        return True
    selected_bar = _select_closed_mark_bar_slot(
        fixture_artifacts,
        bar_query,
        900,
        grid_close - 900_000_000,
        seed_time,
    )
    if (
        not isinstance(selected_bar, Mapping)
        or selected_bar.get("artifact_id") != input_bar_id
    ):
        return True
    scope = {key: binding.get(key) for key in _SCOPE_KEYS}
    for phase, tau in (("anchor", seed_time), ("action", action_time)):
        expected_venue_id = named.get(
            f"{phase}_venue_snapshot_artifact_id"
        )
        selected_venue = _select_venue_snapshot(
            fixture_artifacts, scope, tau
        )
        if (
            isinstance(selected_venue, Mapping)
            and selected_venue.get("artifact_id") != expected_venue_id
        ) or (
            not isinstance(selected_venue, Mapping)
            and expected_venue_id is not None
        ):
            return True
    account_query = _mapping(
        (_mapping(manifest.get("source_queries")) or {}).get("account")
    )
    if account_query is None:
        return True
    for phase, tau in (("anchor", seed_time), ("action", action_time)):
        expected_account_id = named.get(
            f"{phase}_account_snapshot_artifact_id"
        )
        selected_account = _select_account_snapshot(
            fixture_artifacts, account_query, tau, 1_000_000
        )
        if (
            isinstance(selected_account, Mapping)
            and selected_account.get("artifact_id") != expected_account_id
        ) or (
            not isinstance(selected_account, Mapping)
            and expected_account_id is not None
        ):
            return True
    return False


def _abstain_result_from_digest(binding: Mapping[str, Any]) -> FrozenMapping | None:
    null_levels = {
        "anchor": None,
        "p_limit": None,
        "i0": None,
        "g0": None,
        "s0": None,
        "t0": None,
        "h0_us": None,
        "tcap": None,
    }
    zero_risk = {
        "submitted_qty": "0",
        "r_unit_usdt": "0",
        "r_episode_max_usdt": "0",
        "pending_existing_at_action_usdt": "0",
    }
    reasons = (
        "RULE_CHANGE",
        "ANCHOR_UNKNOWN",
        "NO_C1_EVENT",
        "GATE_FALSE",
        "GATE_UNKNOWN_AT_DEADLINE",
        "ENTRY_ZONE_EMPTY",
        "COMMON_CHECK_FAILED",
        "EV_UNKNOWN",
        "RISK_OR_MARGIN_FAIL",
        "TTL_EXPIRED",
    )
    matches: list[dict[str, Any]] = []
    for reason in reasons:
        result = {
            "decision_kind": "ABSTAIN",
            "action_at_us": binding.get("decision_at_us"),
            "reason_code": reason,
            "initial_levels": null_levels,
            "risk_basis": zero_risk,
        }
        if stable_id("decision-result/v0.2.2", result) == binding.get(
            "decision_result_sha256"
        ):
            matches.append(result)
    if len(matches) != 1:
        return None
    return _frozen_mapping(matches[0])


def calculate_decision(
    contract: Mapping[str, Any],
    binding: Mapping[str, Any],
    artifacts: Any,
    as_of_us: int,
    role: str,
) -> FrozenMapping:
    """Recompute the sealed ENTRY/ABSTAIN result from its explicit proof."""

    try:
        serialize_contract(contract)
    except Exception:
        raise KernelValidationError("E_KERNEL_CONTRACT_INVALID") from None
    try:
        if not isinstance(binding, Mapping):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        values = _decision_artifacts(artifacts)
        if values is None:
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        closure_checks = (
            ("E_C05_BOOK_GRID_DEDUP_INVALID", lambda: _decision_c05_violation(binding, values)),
            ("E_C06_VENUE_RULE_MAPPING_INVALID", lambda: _decision_c06_violation(binding, values)),
            ("E_C07_ACCOUNT_ASOF_CONFLICT", lambda: _decision_c07_violation(binding, values)),
            ("E_C09_TARGET_EVIDENCE_INCOMPLETE", lambda: _decision_c09_violation(values)),
            ("E_C11_OI_SEAL_INCOMPLETE", lambda: _decision_c11_violation(binding, values)),
            ("E_C12_DECISION_PROOF_INVALID", lambda: _decision_c12_violation(binding, values, as_of_us)),
            ("E_C20_SELECTOR_BINDING_MISMATCH", lambda: _decision_c20_violation(binding, values)),
        )
        for code, predicate in closure_checks:
            if predicate():
                raise KernelValidationError(code)
        if (
            not is_safe_integer(as_of_us, nonnegative=True)
            or not isinstance(role, str)
            or role != "SYNTHETIC"
        ):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        if (
            binding.get("decision_kind") not in ("ENTRY", "ABSTAIN")
            or binding.get("availability_kind") != "SYNTHETIC"
            or binding.get("lane_id") != _SYNTHETIC_LANE
        ):
            raise KernelValidationError("E_KERNEL_SCHEMA_INVALID")
        if not _decision_binding_digest_valid(binding):
            raise KernelValidationError("E_KERNEL_DIGEST_INVALID")
        if binding.get("decision_kind") == "ABSTAIN":
            result = _abstain_result_from_digest(binding)
            if result is None:
                raise KernelValidationError("E_KERNEL_BINDING_INVALID")
            return result
        actions = [
            _payload(item)
            for item in values
            if item.get("schema_id") == "SHARED_ENTRY_ACTION"
            and (_payload(item) or {}).get("decision_input_binding_sha256")
            == binding.get("proof_sha256")
        ]
        if len(actions) != 1:
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        action = actions[0]
        result = {
            "decision_kind": "ENTRY",
            "action_at_us": action.get("action_at_us"),
            "p_limit": action.get("p_limit"),
            "submitted_qty": action.get("submitted_qty"),
            "initial_levels": action.get("initial_levels"),
            "risk_basis": action.get("risk_basis"),
        }
        if stable_id("decision-result/v0.2.2", result) != binding.get(
            "decision_result_sha256"
        ):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        return _frozen_mapping(result)
    except KernelValidationError:
        raise
    except Exception:
        raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID") from None


def _matching_sufficient_stop_ack(
    event: Mapping[str, Any],
    processed: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
) -> bool:
    if event.get("event_kind") != "STOP_ACK":
        return False
    payload = _mapping(event.get("payload"))
    if payload is None or payload.get("status") != "ACKED" or payload.get("reduce_only") is not True:
        return False
    all_stop_requests = [
        candidate
        for candidate in processed
        if candidate.get("event_kind") == "STOP_REQUEST"
    ]
    requests = [
        candidate
        for candidate in all_stop_requests
        if candidate.get("request_id") == event.get("request_id")
        and candidate.get("order_id") == event.get("order_id")
    ]
    if len(requests) != 1:
        return False
    if not all_stop_requests or requests[0] is not all_stop_requests[-1]:
        return False
    request_payload = _mapping(requests[0].get("payload"))
    if request_payload is None:
        return False
    fields = (
        "price",
        "qty",
        "order_side",
        "reduce_only",
        "replaces_order_id",
        "stop_role",
    )
    if any(payload.get(key) != request_payload.get(key) for key in fields):
        return False
    if request_payload.get("stop_role") not in (
        "INITIAL_PROTECTION",
        "PROTECTION_REPAIR",
        "DYNAMIC_MANAGEMENT",
    ):
        return False
    try:
        with localcontext(DECIMAL_CONTEXT):
            requested_qty = parse_decimal(request_payload.get("qty"), "QtyBase")
            entry_cumulative = Decimal(0)
            exit_cumulative = Decimal(0)
            latest_by_order: dict[tuple[Any, Any, str], Decimal] = {}
            for candidate in processed:
                kind = candidate.get("event_kind")
                if kind not in ("FILL_CUMULATIVE", "EXIT_FILL_CUMULATIVE"):
                    continue
                candidate_payload = _mapping(candidate.get("payload"))
                if candidate_payload is None:
                    return False
                cumulative = parse_decimal(
                    candidate_payload.get("cum_qty"), "QtyBase"
                )
                key = (
                    candidate.get("request_id"),
                    candidate.get("order_id"),
                    kind,
                )
                prior = latest_by_order.get(key, Decimal(0))
                if cumulative < prior:
                    return False
                latest_by_order[key] = cumulative
            for (_, _, kind), cumulative in latest_by_order.items():
                if kind == "FILL_CUMULATIVE":
                    entry_cumulative += cumulative
                else:
                    exit_cumulative += cumulative
            required_qty = max(Decimal(0), entry_cumulative - exit_cumulative)
            if required_qty <= 0 or requested_qty < required_qty:
                return False
    except (TypeError, ValueError):
        return False
    referenced = [
        _find_artifact(artifacts, artifact_id)
        for artifact_id in event.get("input_artifact_ids", ())
    ]
    return all(item is not None for item in referenced)


def _event_priority(
    event: Mapping[str, Any],
    processed: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
) -> int:
    kind = event.get("event_kind")
    if kind == "STOP_ACK":
        return 5 if _matching_sufficient_stop_ack(event, processed, artifacts) else 10
    if kind not in _FIXED_EVENT_RANK:
        raise ValueError("unknown reducer event kind")
    return _FIXED_EVENT_RANK[kind]


def _priority_policy_violation(
    bundle: Mapping[str, Any],
) -> bool:
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    policy_artifacts = [
        item for item in artifacts if item.get("schema_id") == "REDUCER_PRIORITY_POLICY"
    ]
    identity = _mapping(bundle.get("ledger_identity"))
    control_id = None if identity is None else identity.get("control_id")
    if control_id == "C0":
        if policy_artifacts:
            return True
    elif len(policy_artifacts) != 1:
        return True
    if policy_artifacts:
        policy = _payload(policy_artifacts[0])
        event_rank = _mapping(policy.get("event_rank")) if policy is not None else None
        expected = dict(_FIXED_EVENT_RANK)
        expected["STOP_ACK"] = {"MATCHING_SUFFICIENT": 5, "OTHERWISE": 10}
        if (
            policy is None
            or not exact_keys(
                policy,
                (
                    "schema_version",
                    "event_rank",
                    "stop_ack_rank_predicate",
                    "tie_break",
                    "unknown_event_action",
                    "policy_sha256",
                ),
            )
            or policy.get("schema_version")
            != "rsi-mtf-drl-pm.reducer-priority-policy.v0.2.2"
            or set(event_rank or {}) != set(_REDUCER_KINDS)
            or materialize(event_rank) != expected
            or policy.get("stop_ack_rank_predicate")
            != _STOP_ACK_RANK_PREDICATE
            or tuple(policy.get("tie_break", ()))
            != (
                "event_time_us",
                "priority_rank",
                "source_sequence",
                "source_event_id",
            )
            or policy.get("unknown_event_action") != "REJECT_BUNDLE"
            or policy.get("policy_sha256")
            != stable_id(
                "reducer-priority-policy/v0.2.2",
                _without(policy, "policy_sha256"),
            )
            or policy.get("policy_sha256")
            != (
                bundle.get("ledger_seed", {})
                .get("policy_bindings", {})
                .get("reducer_priority_policy_sha256")
            )
        ):
            return True
    processed: list[Mapping[str, Any]] = []
    for event in bundle.get("event_array", ()):
        try:
            rank = _event_priority(event, processed, artifacts)
        except (TypeError, ValueError):
            return True
        if event.get("priority_rank") != rank:
            return True
        processed.append(event)
    return False


def _causality_violation(bundle: Mapping[str, Any]) -> bool:
    events = tuple(bundle.get("event_array", ()))
    by_id = {event.get("source_event_id"): event for event in events}
    submissions = [
        event for event in events if event.get("event_kind") == "ENTRY_SUBMIT"
    ]
    if len(submissions) > 1:
        return True
    submission = submissions[0] if submissions else None
    action_at = None if submission is None else submission.get("event_time_us")
    if submission is not None:
        if (
            submission.get("event_time_us") != submission.get("lane_available_at_us")
            or submission.get("economic_event_time_us") is not None
        ):
            return True
    descendants: set[Any] = set()
    if submission is not None:
        root = submission.get("source_event_id")
        changed = True
        while changed:
            changed = False
            for event in events:
                if event.get("source_event_id") in descendants or event is submission:
                    continue
                if root in event.get("predecessor_event_ids", ()) or any(
                    predecessor in descendants
                    for predecessor in event.get("predecessor_event_ids", ())
                ):
                    descendants.add(event.get("source_event_id"))
                    changed = True
        required_descendant_kinds = frozenset(_REDUCER_KINDS) - {
            "ENTRY_SUBMIT",
            "CONTROL_ABSTAIN",
        }
        if any(
            event.get("event_kind") in required_descendant_kinds
            and event.get("source_event_id") not in descendants
            for event in events
        ):
            return True
        for event_id in descendants:
            event = by_id[event_id]
            if event.get("event_time_us") <= action_at:
                return True
            economic = event.get("economic_event_time_us")
            if economic is not None and economic <= action_at:
                return True
    processed: set[Any] = set()
    remaining = list(events)
    reconstructed: list[Mapping[str, Any]] = []
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    while remaining:
        ready = [
            event
            for event in remaining
            if set(event.get("predecessor_event_ids", ())) <= processed
        ]
        if not ready:
            return True
        ready.sort(
            key=lambda event: (
                event.get("event_time_us"),
                _event_priority(event, reconstructed, artifacts),
                event.get("source_sequence"),
                event.get("source_event_id"),
            )
        )
        winner = ready[0]
        reconstructed.append(winner)
        processed.add(winner.get("source_event_id"))
        remaining.remove(winner)
    return canonical_json(reconstructed) != canonical_json(events)


def _revalidate_carrier(
    contract: Mapping[str, Any],
    carrier: Any,
    as_of_us: int,
    role: str,
) -> ValidatedBundle:
    if not isinstance(carrier, ValidatedBundle):
        raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
    if (
        carrier.status != "VALID"
        or carrier.validated_as_of_us != as_of_us
        or carrier.role != role
        or carrier.bundle.get("bundle_sha256") != carrier.bundle_sha256
    ):
        raise KernelValidationError("E_KERNEL_BINDING_INVALID")
    outcome = validate_bundle(contract, carrier.bundle, as_of_us, role)
    if not isinstance(outcome, ValidatedBundle):
        raise KernelValidationError("E_KERNEL_BINDING_INVALID")
    if (
        outcome.bundle_sha256 != carrier.bundle_sha256
        or outcome.validated_as_of_us != carrier.validated_as_of_us
        or outcome.role != carrier.role
        or canonical_json(outcome.bundle) != canonical_json(carrier.bundle)
    ):
        raise KernelValidationError("E_KERNEL_BINDING_INVALID")
    return outcome


_LEDGER_RECORD_KEYS = (
    "schema_version",
    "ledger_id",
    "sequence",
    "event_id",
    "source_event_id",
    "source_sequence",
    "parent_event_id",
    "previous_hash",
    "record_hash",
    "bindings",
    "identity",
    "side",
    "action_context_sha256",
    "event_kind",
    "state_before",
    "state_after",
    "times",
    "inputs",
    "levels",
    "quantities",
    "risk",
    "orders",
    "costs",
    "reconcile",
    "decision",
    "operator",
)
_LEVEL_KEYS = (
    "anchor",
    "p_limit",
    "pe",
    "i0",
    "g0",
    "s0",
    "stop_before",
    "stop_after",
    "t0",
    "target_before",
    "target_after",
    "h0_us",
    "tcap",
    "current_exit_price",
)
_QUANTITY_KEYS = (
    "submitted_qty",
    "q_auth",
    "open_qty",
    "reconciled_qty",
    "effective_protected_qty",
    "unprotected_qty",
    "excess_qty",
)
_RISK_KEYS = (
    "r_unit_usdt",
    "r_episode_max_usdt",
    "realized_loss_usdt",
    "pending_existing_usdt",
    "pending_unprotected_usdt",
    "locked_net_usdt",
    "protection_pending_kind",
    "protection_pending_started_at_us",
    "protection_pending_deadline_us",
    "exit_pending_started_at_us",
    "exit_pending_deadline_us",
)
_COST_KEYS = (
    "realized_gross_usdt",
    "fee_incurred_usdt",
    "funding_incurred_usdt",
    "entry_slippage_usdt",
    "exit_worst_usdt",
    "funding_buffer_usdt",
    "tail_usdt",
)


def _empty_levels() -> dict[str, Any]:
    return {key: None for key in _LEVEL_KEYS}


def _zero_quantities() -> dict[str, str]:
    return {key: "0" for key in _QUANTITY_KEYS}


def _zero_risk() -> dict[str, Any]:
    return {
        "r_unit_usdt": "0",
        "r_episode_max_usdt": "0",
        "realized_loss_usdt": "0",
        "pending_existing_usdt": "0",
        "pending_unprotected_usdt": "0",
        "locked_net_usdt": "0",
        "protection_pending_kind": None,
        "protection_pending_started_at_us": None,
        "protection_pending_deadline_us": None,
        "exit_pending_started_at_us": None,
        "exit_pending_deadline_us": None,
    }


def _zero_costs() -> dict[str, str]:
    return {key: "0" for key in _COST_KEYS}


def _record_hash(record: Mapping[str, Any]) -> str:
    return stable_id(
        "management-ledger-record/v0.2.2", _without(record, "record_hash")
    )


def _genesis_record(bundle: Mapping[str, Any]) -> FrozenMapping:
    bindings = materialize(bundle["ledger_bindings"])
    identity = materialize(bundle["ledger_identity"])
    seed = bundle["ledger_seed"]
    ledger_id = stable_id(
        "management-ledger/v0.2.2",
        {
            "bindings": bindings,
            **{
                key: identity[key]
                for key in (
                    "venue_id",
                    "instrument_id",
                    "lane_id",
                    "account_scope_id",
                    "role",
                    "episode_id",
                    "opportunity_id",
                    "control_id",
                    "candidate_id",
                )
            },
        },
    )
    event_id = stable_id(
        "management-genesis/v0.2.2",
        {"ledger_id": ledger_id, "bindings": bindings, "identity": identity},
    )
    anchor = seed["anchor_at_us"]
    side = "NONE" if identity["control_id"] == "C0" else seed["side"]
    record: dict[str, Any] = {
        "schema_version": "rsi-mtf-drl-pm.management-ledger.v0.2.2",
        "ledger_id": ledger_id,
        "sequence": 0,
        "event_id": event_id,
        "source_event_id": None,
        "source_sequence": None,
        "parent_event_id": None,
        "previous_hash": _ZERO_SHA,
        "record_hash": _ZERO_SHA,
        "bindings": bindings,
        "identity": identity,
        "side": side,
        "action_context_sha256": None,
        "event_kind": "GENESIS",
        "state_before": "FLAT",
        "state_after": "FLAT",
        "times": {
            "event_time_us": anchor,
            "lane_available_at_us": anchor,
            "decision_at_us": anchor,
            "evaluated_at_us": anchor,
            "written_at_us": anchor,
        },
        "inputs": {
            "input_ids": [],
            "input_bundle_sha256": stable_id(
                "management-genesis-inputs/v0.2.2",
                {
                    "ledger_id": ledger_id,
                    "opportunity_id": identity["opportunity_id"],
                    "control_id": identity["control_id"],
                    "side": side,
                    "genesis_at_us": anchor,
                },
            ),
            "quality": "VALID",
        },
        "levels": _empty_levels(),
        "quantities": _zero_quantities(),
        "risk": _zero_risk(),
        "orders": [],
        "costs": _zero_costs(),
        "reconcile": {
            "snapshot_id": None,
            "snapshot_sha256": None,
            "position_qty": "0",
            "position_vwap": None,
            "account_match": None,
            "all_orders_terminal": True,
        },
        "decision": {
            "reason": "GENESIS",
            "priority_rank": 12,
            "barrier_authority": {"stop": "NONE", "target": "NONE"},
            "resume_after_protection": None,
            "no_change": True,
            "duplicate_of_event_id": None,
            "conflict_with_event_id": None,
        },
        "operator": {
            "kind": "SYSTEM",
            "id": "rsi-mtf-drl-pm-reducer-v0.2.2",
        },
    }
    record["record_hash"] = _record_hash(record)
    return _frozen_mapping(record)


def _artifact_descriptor(
    wrapper: Mapping[str, Any], anchor_at_us: int
) -> dict[str, Any]:
    schema_id = wrapper.get("schema_id")
    payload = _payload(wrapper)
    if payload is None:
        raise ValueError("malformed descriptor artifact")
    if wrapper.get("available_at_us") is None:
        lane_time = anchor_at_us
    elif schema_id == "U_OBSERVATION_RECEIPT":
        lane_time = payload.get("evaluation_at_us")
    elif schema_id == "DECISION_INPUT_BINDING":
        lane_time = payload.get("decision_at_us")
    elif schema_id == "SHARED_ENTRY_ACTION":
        lane_time = payload.get("action_at_us")
    else:
        lane_time = wrapper.get("available_at_us")
    if schema_id in ("CLOSED_MARK_BAR", "AGG_TRADE", "OPEN_INTEREST"):
        quality = {
            "VALID": "VALID",
            "GAP": "UNKNOWN",
            "INVALID": "INVALID",
            "CONFLICT": "CONFLICT",
        }.get(payload.get("quality"))
    elif schema_id == "BOOK_SNAPSHOT":
        if payload.get("quality") == "VALID" and payload.get("sequence_contiguous") is True:
            quality = "VALID"
        elif payload.get("quality") == "GAP":
            quality = "UNKNOWN"
        elif payload.get("quality") == "CONFLICT" or (
            payload.get("quality") == "VALID"
            and payload.get("sequence_contiguous") is not True
        ):
            quality = "CONFLICT"
        else:
            quality = "INVALID"
    elif schema_id == "SOURCE_COVERAGE_SEAL":
        gaps = payload.get("observed_gap_intervals", ())
        if any(
            isinstance(gap, Mapping) and gap.get("reason") == "CONFLICT"
            for gap in gaps
        ):
            quality = "CONFLICT"
        elif payload.get("complete") is True and not gaps:
            quality = "VALID"
        else:
            quality = "UNKNOWN"
    elif schema_id in ("VENUE_INSTRUMENT_SNAPSHOT", "ACCOUNT_RISK_SNAPSHOT"):
        quality = payload.get("quality")
    elif schema_id == "SYNTHETIC_CONFLICT_PROOF":
        quality = "CONFLICT"
    else:
        quality = "VALID"
    if quality not in ("VALID", "UNKNOWN", "INVALID", "CONFLICT"):
        raise ValueError("invalid descriptor quality")
    return {
        "input_id": wrapper.get("artifact_id"),
        "payload_sha256": wrapper.get("payload_sha256"),
        "lane_available_at_us": lane_time,
        "quality": quality,
    }


def _source_quality(event: Mapping[str, Any]) -> str:
    if event.get("event_kind") == "EVENT_CONFLICT":
        return "CONFLICT"
    if event.get("event_kind") in ("DATA_HEALTH_INVALID", "ACCOUNT_MISMATCH"):
        return "INVALID"
    payload = _mapping(event.get("payload"))
    if payload is not None and payload.get("status") == "UNKNOWN":
        return "UNKNOWN"
    return "VALID"


def _event_inputs(
    bundle: Mapping[str, Any],
    event: Mapping[str, Any],
    previous_hash: str,
    action_context_sha256: Any,
) -> dict[str, Any]:
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    events = {item.get("source_event_id"): item for item in bundle.get("event_array", ())}
    descriptors: list[dict[str, Any]] = [
        {
            "input_id": event.get("source_event_id"),
            "payload_sha256": event.get("payload_sha256"),
            "lane_available_at_us": event.get("lane_available_at_us"),
            "quality": _source_quality(event),
        }
    ]
    for artifact_id in event.get("input_artifact_ids", ()):
        wrapper = _find_artifact(artifacts, artifact_id)
        if wrapper is None:
            raise ValueError("event references an unknown artifact")
        descriptor = _artifact_descriptor(
            wrapper, bundle["ledger_seed"]["anchor_at_us"]
        )
        if descriptor["lane_available_at_us"] > event.get("event_time_us"):
            raise ValueError("artifact descriptor is future available")
        descriptors.append(descriptor)
    for predecessor_id in event.get("predecessor_event_ids", ()):
        predecessor = events.get(predecessor_id)
        if predecessor is None:
            raise ValueError("event references an unknown predecessor")
        descriptors.append(
            {
                "input_id": predecessor_id,
                "payload_sha256": predecessor.get("payload_sha256"),
                "lane_available_at_us": predecessor.get("lane_available_at_us"),
                "quality": _source_quality(predecessor),
            }
        )
    descriptors.sort(key=lambda item: item["input_id"])
    if len({item["input_id"] for item in descriptors}) != len(descriptors):
        raise ValueError("descriptor identity collision")
    severity = {"VALID": 0, "UNKNOWN": 1, "INVALID": 2, "CONFLICT": 3}
    quality = max(descriptors, key=lambda item: severity[item["quality"]])["quality"]
    source_envelope = stable_id(
        "canonical-synthetic-event-envelope/v0.2.2", event
    )
    input_bundle = stable_id(
        "management-record-inputs/v0.2.2",
        {
            "bundle_scope_id": bundle.get("bundle_scope_id"),
            "ledger_seed_sha256": bundle["ledger_seed"]["seed_sha256"],
            "action_context_sha256": action_context_sha256,
            "previous_hash": previous_hash,
            "source_event_sha256": source_envelope,
            "descriptors": descriptors,
        },
    )
    return {
        "input_ids": [item["input_id"] for item in descriptors],
        "input_bundle_sha256": input_bundle,
        "quality": quality,
    }


def _order_row(event: Mapping[str, Any], role: str) -> dict[str, Any]:
    payload = event.get("payload", {})
    is_cancel = role == "CANCEL"
    return {
        "role": role,
        "stop_role": payload.get("stop_role") if role == "STOP" else None,
        "target_role": payload.get("target_role") if role == "TARGET" else None,
        "exit_projection_mode": payload.get("projection_mode") if role == "EXIT" else None,
        "order_id": event.get("order_id"),
        "request_id": event.get("request_id"),
        "order_side": None if is_cancel else payload.get("order_side"),
        "lifecycle_status": "REQUESTED",
        "fill_status": "NONE",
        "price": payload.get("price") if role in ("ENTRY", "STOP", "TARGET") else None,
        "qty": payload.get("qty", "0"),
        "reduce_only": payload.get("reduce_only", False),
        "cum_qty": "0",
        "cum_quote_notional": "0",
        "remainder_terminal": False,
        "terminal_confirmed_by_snapshot_id": None,
    }


def _order_sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        "" if row.get(key) is None else str(row.get(key))
        for key in (
            "role",
            "stop_role",
            "target_role",
            "exit_projection_mode",
            "order_id",
            "request_id",
        )
    )


def _latest_authority(
    orders: Sequence[Mapping[str, Any]], role: str, side: str
) -> Any:
    active = [
        row
        for row in orders
        if row.get("role") == role
        and row.get("lifecycle_status") == "ACKED"
        and row.get("fill_status") != "FILLED"
        and row.get("remainder_terminal") is not True
        and validate_decimal("Price", row.get("price"))
    ]
    if not active:
        return None
    sign = Decimal(1) if side == "LONG" else Decimal(-1)

    def authority_key(row: Mapping[str, Any]) -> Decimal:
        with localcontext(DECIMAL_CONTEXT):
            return sign * parse_decimal(row["price"], "Price")

    active.sort(key=authority_key)
    return active[-1].get("price")


def _apply_orders_and_fills(
    event: Mapping[str, Any],
    previous_orders: Sequence[Mapping[str, Any]],
    previous_quantities: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], Decimal, bool, bool]:
    orders = [dict(row) for row in previous_orders]
    quantities = {key: str(previous_quantities.get(key, "0")) for key in _QUANTITY_KEYS}
    kind = event.get("event_kind")
    payload = event.get("payload", {})
    role_by_request = {
        "ENTRY_SUBMIT": "ENTRY",
        "CANCEL_REQUEST": "CANCEL",
        "STOP_REQUEST": "STOP",
        "TARGET_REQUEST": "TARGET",
        "REDUCE_ONLY_EXIT_REQUEST": "EXIT",
    }
    changed = False
    positive_fill = False
    quote_delta = Decimal(0)
    if kind in role_by_request:
        if any(
            row.get("order_id") == event.get("order_id")
            and row.get("request_id") == event.get("request_id")
            for row in orders
        ):
            raise ValueError("duplicate order request identity")
        row = _order_row(event, role_by_request[kind])
        if not row["order_id"] or not row["request_id"]:
            raise ValueError("request identity is absent")
        orders.append(row)
        if kind == "ENTRY_SUBMIT":
            quantities["submitted_qty"] = payload.get("qty")
        changed = True
    lifecycle_map = {
        "ENTRY_ACK": ("ACKED", "ENTRY"),
        "ENTRY_REJECT": ("REJECTED", "ENTRY"),
        "ENTRY_EXPIRE": ("EXPIRED", "ENTRY"),
        "STOP_ACK": ("ACKED", "STOP"),
        "STOP_REJECT_OR_UNKNOWN": (payload.get("status", "UNKNOWN"), "STOP"),
        "TARGET_ACK": ("ACKED", "TARGET"),
        "TARGET_REJECT_OR_UNKNOWN": (payload.get("status", "UNKNOWN"), "TARGET"),
        "EXIT_ACK": ("ACKED", "EXIT"),
        "EXIT_REJECT_OR_UNKNOWN": (payload.get("status", "UNKNOWN"), "EXIT"),
    }
    if kind in lifecycle_map:
        status, role = lifecycle_map[kind]
        matches = [
            row
            for row in orders
            if row.get("order_id") == event.get("order_id")
            and row.get("request_id") == event.get("request_id")
            and row.get("role") == role
        ]
        if len(matches) != 1:
            raise ValueError("lifecycle identity does not resolve")
        matches[0]["lifecycle_status"] = status
        if status in ("REJECTED", "EXPIRED"):
            matches[0]["remainder_terminal"] = matches[0]["fill_status"] == "FILLED"
        changed = True
    if kind in ("CANCEL_ACK", "CANCEL_REJECT_OR_UNKNOWN"):
        targets = [
            row
            for row in orders
            if row.get("order_id") == payload.get("target_order_id")
            and row.get("role") != "CANCEL"
        ]
        if len(targets) != 1:
            raise ValueError("cancel target does not resolve")
        if kind == "CANCEL_ACK":
            targets[0]["lifecycle_status"] = "CANCELED"
        changed = True
    if kind in ("FILL_CUMULATIVE", "EXIT_FILL_CUMULATIVE"):
        matches = [row for row in orders if row.get("order_id") == event.get("order_id")]
        if len(matches) != 1:
            raise ValueError("fill order identity does not resolve")
        row = matches[0]
        with localcontext(DECIMAL_CONTEXT):
            new_qty = parse_decimal(payload.get("cum_qty"), "QtyBase")
            new_quote = parse_decimal(payload.get("cum_quote_notional"), "Money")
            old_qty = parse_decimal(row["cum_qty"], "QtyBase")
            old_quote = parse_decimal(row["cum_quote_notional"], "Money")
            if new_qty < old_qty or new_quote < old_quote or (
                new_qty == old_qty and new_quote != old_quote
            ):
                raise ValueError("cumulative fill is not monotone")
            delta = new_qty - old_qty
            quote_delta = new_quote - old_quote
            row["cum_qty"] = decimal_value(new_qty)
            row["cum_quote_notional"] = decimal_value(new_quote)
            if new_qty == parse_decimal(row["qty"], "QtyBase"):
                row["fill_status"] = "FILLED"
                row["remainder_terminal"] = True
            elif new_qty > 0:
                row["fill_status"] = "PARTIAL"
            positive_fill = delta > 0
            if positive_fill:
                open_qty = parse_decimal(quantities["open_qty"], "QtyBase")
                if kind == "FILL_CUMULATIVE":
                    open_qty += delta
                elif row.get("exit_projection_mode") == "INTENDED_FILL_PROJECTION":
                    open_qty -= delta
                    if open_qty < 0:
                        raise ValueError("intended exit overfills projection")
                quantities["open_qty"] = decimal_value(open_qty)
                quantities["reconciled_qty"] = decimal_value(open_qty)
        changed = changed or positive_fill
    orders.sort(key=_order_sort_key)
    return orders, quantities, quote_delta, positive_fill, changed


def _reduce_event_record(
    bundle: Mapping[str, Any],
    previous: Mapping[str, Any],
    event: Mapping[str, Any],
    processed_events: Sequence[Mapping[str, Any]],
) -> FrozenMapping:
    before_state = previous["state_after"]
    context = bundle.get("action_context")
    activates = (
        previous.get("action_context_sha256") is None
        and context is not None
        and event.get("event_kind")
        in (
            "CONTROL_ABSTAIN",
            "ENTRY_SUBMIT",
            "ACCOUNT_MISMATCH",
            "KILL",
            "DATA_HEALTH_INVALID",
            "EVENT_CONFLICT",
        )
    )
    action_context_sha = (
        context.get("action_context_sha256")
        if activates
        else previous.get("action_context_sha256")
    )
    levels = dict(materialize(previous["levels"]))
    quantities_before = materialize(previous["quantities"])
    risk = dict(materialize(previous["risk"]))
    costs = dict(materialize(previous["costs"]))
    reconcile = dict(materialize(previous["reconcile"]))
    orders, quantities, quote_delta, positive_fill, order_changed = _apply_orders_and_fills(
        event, previous["orders"], quantities_before
    )
    kind = event.get("event_kind")
    payload = event.get("payload", {})
    state = before_state
    reason = "NO_CHANGE"
    resume = previous["decision"].get("resume_after_protection")
    if kind == "CONTROL_ABSTAIN" and before_state == "FLAT":
        state, reason = "CLOSED", "ABSTAIN"
    elif kind == "ENTRY_SUBMIT" and before_state == "FLAT":
        state, reason = "ENTRY_PENDING", "ACTION"
        initial = context.get("initial_levels", {}) if context is not None else {}
        levels.update(
            {
                "anchor": initial.get("anchor"),
                "p_limit": initial.get("p_limit"),
                "i0": initial.get("i0"),
                "g0": initial.get("g0"),
                "s0": initial.get("s0"),
                "t0": initial.get("t0"),
                "h0_us": initial.get("h0_us"),
                "tcap": initial.get("tcap"),
            }
        )
        risk_basis = context.get("risk_basis", {}) if context is not None else {}
        risk["r_unit_usdt"] = risk_basis.get("r_unit_usdt", "0")
        risk["r_episode_max_usdt"] = risk_basis.get("r_episode_max_usdt", "0")
        risk["pending_existing_usdt"] = risk_basis.get(
            "pending_existing_at_action_usdt", "0"
        )
    elif kind == "FILL_CUMULATIVE" and positive_fill:
        if before_state in ("CLOSED", "EXIT_PENDING"):
            state, reason = "HALTED_RECONCILE", "HALT"
        else:
            first = quantities_before.get("q_auth") == "0"
            if first:
                with localcontext(DECIMAL_CONTEXT):
                    cum_qty = parse_decimal(payload.get("cum_qty"), "QtyBase")
                    cum_quote = parse_decimal(
                        payload.get("cum_quote_notional"), "Money"
                    )
                    quantities["q_auth"] = decimal_value(cum_qty)
                    levels["pe"] = decimal_value(cum_quote / cum_qty)
                risk["protection_pending_kind"] = "FIRST_FILL_PENDING"
                risk["protection_pending_started_at_us"] = event.get("event_time_us")
                risk["protection_pending_deadline_us"] = event.get("event_time_us") + 2_000_000
            elif parse_decimal(quantities["open_qty"], "QtyBase") > parse_decimal(
                quantities["q_auth"], "QtyBase"
            ):
                risk["protection_pending_kind"] = "EXCESS_FILL_PENDING"
            state, reason = "PROTECTION_PENDING", "FILL"
    elif kind == "STOP_ACK":
        sufficient = _matching_sufficient_stop_ack(
            event,
            processed_events,
            _artifact_sequence(bundle.get("artifacts")) or (),
        )
        if sufficient and before_state == "PROTECTION_PENDING":
            quantities["effective_protected_qty"] = payload.get("qty", "0")
            quantities["unprotected_qty"] = "0"
            risk["protection_pending_kind"] = None
            risk["protection_pending_started_at_us"] = None
            risk["protection_pending_deadline_us"] = None
            state = resume or "OPEN_PROTECTED_PRE_LOCK"
            resume = None
            reason = "PROTECT"
        else:
            reason = "ACTION"
    elif kind in ("STOP_HIT", "STRUCTURE_EXIT", "TARGET_HIT", "HORIZON"):
        if before_state in (
            "PROTECTION_PENDING",
            "OPEN_PROTECTED_PRE_LOCK",
            "PROFIT_LOCKED",
        ):
            state, reason = "EXIT_PENDING", "EXIT"
            risk["exit_pending_started_at_us"] = event.get("event_time_us")
            risk["exit_pending_deadline_us"] = event.get("event_time_us") + 2_000_000
            resume = None
    elif kind == "REDUCE_ONLY_EXIT_REQUEST" and before_state in (
        "PROTECTION_PENDING",
        "OPEN_PROTECTED_PRE_LOCK",
        "PROFIT_LOCKED",
    ):
        state, reason = "EXIT_PENDING", "EXIT"
        if risk.get("exit_pending_started_at_us") is None:
            risk["exit_pending_started_at_us"] = event.get("event_time_us")
            risk["exit_pending_deadline_us"] = event.get("event_time_us") + 2_000_000
    elif kind == "EXIT_FILL_CUMULATIVE" and positive_fill:
        reason = "FILL"
        if quantities["open_qty"] == "0":
            risk["exit_pending_started_at_us"] = None
            risk["exit_pending_deadline_us"] = None
            risk["protection_pending_kind"] = None
            risk["protection_pending_started_at_us"] = None
            risk["protection_pending_deadline_us"] = None
    elif kind == "PENDING_DEADLINE":
        deadline_kind = payload.get("deadline_kind")
        deadline = payload.get("deadline_at_us")
        if deadline_kind in ("FIRST_FILL_PENDING", "EXCESS_FILL_PENDING"):
            if (
                risk.get("protection_pending_kind") != deadline_kind
                or risk.get("protection_pending_deadline_us") != deadline
            ):
                reason = "NO_CHANGE"
            else:
                state, reason = "HALTED_RECONCILE", "HALT"
        elif deadline_kind == "EXIT_PENDING":
            if risk.get("exit_pending_deadline_us") != deadline or quantities["open_qty"] == "0":
                reason = "NO_CHANGE"
            else:
                state, reason = "HALTED_RECONCILE", "HALT"
    elif kind in (
        "STOP_REJECT_OR_UNKNOWN",
        "TARGET_REJECT_OR_UNKNOWN",
        "EXIT_REJECT_OR_UNKNOWN",
        "CANCEL_REJECT_OR_UNKNOWN",
    ) and before_state not in ("FLAT", "CLOSED"):
        state, reason = "HALTED_RECONCILE", "HALT"
    elif kind in ("ACCOUNT_MISMATCH", "KILL", "DATA_HEALTH_INVALID", "EVENT_CONFLICT"):
        if before_state == "FLAT" and not orders:
            state, reason = "CLOSED", "ABSTAIN"
        else:
            state, reason = "HALTED_RECONCILE", "HALT"
        if kind == "ACCOUNT_MISMATCH":
            observed = payload.get("observed_position_qty")
            if observed is not None:
                reconcile["position_qty"] = observed
                reconcile["position_vwap"] = payload.get("observed_position_vwap")
            reconcile["account_match"] = False
    elif kind in ("POSITION_SNAPSHOT", "RECONCILE_OK"):
        position = payload.get("position_qty", "0")
        reconcile.update(
            {
                "snapshot_id": payload.get("snapshot_id"),
                "snapshot_sha256": payload.get("snapshot_sha256"),
                "position_qty": position,
                "position_vwap": payload.get("position_vwap"),
                "account_match": payload.get("reconcile_mode")
                != "OPERATIONAL_FLAT_AFTER_MISMATCH",
                "all_orders_terminal": payload.get("all_orders_terminal", False),
            }
        )
        if (
            kind == "RECONCILE_OK"
            and position == "0"
            and payload.get("all_orders_terminal") is True
            and before_state in ("EXIT_PENDING", "HALTED_RECONCILE", "CLOSED")
        ):
            state, reason = "CLOSED", "RECONCILE"
        else:
            reason = "RECONCILE"
    elif kind == "FUNDING_DEBIT":
        with localcontext(DECIMAL_CONTEXT):
            costs["funding_incurred_usdt"] = decimal_value(
                parse_decimal(costs["funding_incurred_usdt"], "Money")
                + parse_decimal(payload.get("debit_usdt"), "Money")
            )
        reason = "ACTION"
    elif order_changed:
        reason = "ACTION"
    with localcontext(DECIMAL_CONTEXT):
        open_qty = parse_decimal(quantities["open_qty"], "QtyBase")
        protected = parse_decimal(
            quantities["effective_protected_qty"], "QtyBase"
        )
        q_auth = parse_decimal(quantities["q_auth"], "QtyBase")
        quantities["reconciled_qty"] = decimal_value(
            max(open_qty, abs(parse_decimal(reconcile.get("position_qty", "0"))))
            if reconcile.get("account_match") is False
            else open_qty
        )
        reconciled = parse_decimal(quantities["reconciled_qty"], "QtyBase")
        quantities["unprotected_qty"] = decimal_value(
            max(Decimal(0), reconciled - protected)
        )
        quantities["excess_qty"] = decimal_value(
            max(Decimal(0), reconciled - q_auth)
        )
    stop_before = previous["levels"].get("stop_after")
    target_before = previous["levels"].get("target_after")
    stop_after = _latest_authority(orders, "STOP", previous["side"])
    target_after = _latest_authority(orders, "TARGET", previous["side"])
    levels["stop_before"] = stop_before
    levels["target_before"] = target_before
    levels["stop_after"] = stop_after
    levels["target_after"] = target_after
    levels["current_exit_price"] = (
        payload.get("observed_exit_price")
        if kind in ("STOP_HIT", "STRUCTURE_EXIT", "TARGET_HIT")
        else None
    )
    fee_bps = bundle["ledger_seed"]["cost_basis"].get("fee_bps_per_side", "0")
    with localcontext(DECIMAL_CONTEXT):
        entry_quote = sum(
            (
                parse_decimal(row["cum_quote_notional"], "Money")
                for row in orders
                if row.get("role") == "ENTRY"
            ),
            Decimal(0),
        )
        exit_quote = sum(
            (
                parse_decimal(row["cum_quote_notional"], "Money")
                for row in orders
                if row.get("role") == "EXIT"
            ),
            Decimal(0),
        )
        costs["fee_incurred_usdt"] = decimal_value(
            (entry_quote + exit_quote) * parse_decimal(fee_bps, "Bps") / Decimal(10_000)
        )
    previous_projection = {
        "state": before_state,
        "levels": materialize(previous["levels"]),
        "quantities": materialize(previous["quantities"]),
        "risk": materialize(previous["risk"]),
        "orders": materialize(previous["orders"]),
        "costs": materialize(previous["costs"]),
        "reconcile": materialize(previous["reconcile"]),
    }
    current_projection = {
        "state": state,
        "levels": levels,
        "quantities": quantities,
        "risk": risk,
        "orders": orders,
        "costs": costs,
        "reconcile": reconcile,
    }
    no_change = canonical_json(previous_projection) == canonical_json(current_projection)
    if reason == "NO_CHANGE":
        no_change = True
    parent = (
        previous.get("parent_event_id")
        if previous["decision"].get("no_change") is True
        else previous.get("event_id")
    )
    record: dict[str, Any] = {
        "schema_version": "rsi-mtf-drl-pm.management-ledger.v0.2.2",
        "ledger_id": previous["ledger_id"],
        "sequence": previous["sequence"] + 1,
        "event_id": stable_id(
            "management-event/v0.2.2",
            {
                "ledger_id": previous["ledger_id"],
                "event_kind": kind,
                "source_event_id": event.get("source_event_id"),
            },
        ),
        "source_event_id": event.get("source_event_id"),
        "source_sequence": event.get("source_sequence"),
        "parent_event_id": parent,
        "previous_hash": previous["record_hash"],
        "record_hash": _ZERO_SHA,
        "bindings": materialize(previous["bindings"]),
        "identity": materialize(previous["identity"]),
        "side": previous["side"],
        "action_context_sha256": action_context_sha,
        "event_kind": kind,
        "state_before": before_state,
        "state_after": state,
        "times": {
            "event_time_us": event.get("event_time_us"),
            "lane_available_at_us": event.get("lane_available_at_us"),
            "decision_at_us": event.get("lane_available_at_us"),
            "evaluated_at_us": event.get("lane_available_at_us"),
            "written_at_us": event.get("lane_available_at_us"),
        },
        "inputs": _event_inputs(
            bundle, event, previous["record_hash"], action_context_sha
        ),
        "levels": levels,
        "quantities": quantities,
        "risk": risk,
        "orders": orders,
        "costs": costs,
        "reconcile": reconcile,
        "decision": {
            "reason": reason,
            "priority_rank": event.get("priority_rank"),
            "barrier_authority": {
                "stop": (
                    "NEW_ACKED"
                    if stop_after is not None and stop_after != stop_before
                    else "OLD_ACKED"
                    if stop_after is not None
                    else "NONE"
                ),
                "target": (
                    "NEW_ACKED"
                    if target_after is not None and target_after != target_before
                    else "OLD_ACKED"
                    if target_after is not None
                    else "NONE"
                ),
            },
            "resume_after_protection": resume,
            "no_change": no_change,
            "duplicate_of_event_id": None,
            "conflict_with_event_id": (
                payload.get("original_event_id")
                if kind == "EVENT_CONFLICT"
                else event.get("source_event_id")
                if reason == "HALT" and kind not in (
                    "ACCOUNT_MISMATCH",
                    "KILL",
                    "DATA_HEALTH_INVALID",
                )
                else None
            ),
        },
        "operator": {
            "kind": "SYSTEM",
            "id": "rsi-mtf-drl-pm-reducer-v0.2.2",
        },
    }
    record["record_hash"] = _record_hash(record)
    return _frozen_mapping(record)


def reduce_event_array(
    contract: Mapping[str, Any],
    validated_bundle: ValidatedBundle,
    as_of_us: int,
    role: str,
) -> tuple[FrozenMapping, ...]:
    """Replay the sealed ready-set without generating or reordering events."""

    try:
        serialize_contract(contract)
    except Exception:
        raise KernelValidationError("E_KERNEL_CONTRACT_INVALID") from None
    try:
        if not isinstance(validated_bundle, ValidatedBundle):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        if (
            not is_safe_integer(as_of_us, nonnegative=True)
            or not isinstance(role, str)
        ):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        embedded = validated_bundle.bundle
        if _priority_policy_violation(embedded):
            raise KernelValidationError("E_C15_PRIORITY_TABLE_INVALID")
        if _causality_violation(embedded):
            raise KernelValidationError("E_C16_DESCENDANT_CAUSALITY_INVALID")
        carrier = _revalidate_carrier(
            contract, validated_bundle, as_of_us, role
        )
        bundle = carrier.bundle
        records: list[FrozenMapping] = [_genesis_record(bundle)]
        processed: list[Mapping[str, Any]] = []
        for event in bundle.get("event_array", ()):
            record = _reduce_event_record(bundle, records[-1], event, processed)
            records.append(record)
            processed.append(event)
        if (
            bundle["ledger_identity"]["control_id"] != "C0"
            and records[-1]["state_after"] != "CLOSED"
        ):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        expected_code = bundle["ledger_bindings"]["code_sha256"]
        if any(record["bindings"]["code_sha256"] != expected_code for record in records):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        return tuple(records)
    except KernelValidationError:
        raise
    except Exception:
        raise KernelValidationError("E_KERNEL_BINDING_INVALID") from None


def _ledger_schema_valid(record: Mapping[str, Any]) -> bool:
    if not exact_keys(record, _LEDGER_RECORD_KEYS):
        return False
    if (
        record.get("schema_version") != "rsi-mtf-drl-pm.management-ledger.v0.2.2"
        or record.get("event_kind") not in ("GENESIS",) + _REDUCER_KINDS
        or record.get("state_before") not in _STATES
        or record.get("state_after") not in _STATES
        or not is_safe_integer(record.get("sequence"), nonnegative=True)
        or not is_sha256(record.get("ledger_id"))
        or not is_sha256(record.get("event_id"))
        or not is_sha256(record.get("previous_hash"))
        or not is_sha256(record.get("record_hash"))
        or not exact_keys(record.get("bindings"), _LEDGER_BINDING_KEYS)
        or not exact_keys(record.get("identity"), _IDENTITY_KEYS)
        or not exact_keys(record.get("levels"), _LEVEL_KEYS)
        or not exact_keys(record.get("quantities"), _QUANTITY_KEYS)
        or not exact_keys(record.get("risk"), _RISK_KEYS)
        or not exact_keys(record.get("costs"), _COST_KEYS)
    ):
        return False
    if not all(
        validate_decimal("QtyBase", record["quantities"].get(key))
        for key in _QUANTITY_KEYS
    ):
        return False
    if not all(
        validate_decimal("DecimalString", record["risk"].get(key))
        for key in (
            "r_unit_usdt",
            "r_episode_max_usdt",
            "realized_loss_usdt",
            "pending_existing_usdt",
            "pending_unprotected_usdt",
            "locked_net_usdt",
        )
    ):
        return False
    if not all(
        validate_decimal("DecimalString", record["costs"].get(key))
        for key in _COST_KEYS
    ):
        return False
    times = _mapping(record.get("times"))
    if not exact_keys(
        times,
        (
            "event_time_us",
            "lane_available_at_us",
            "decision_at_us",
            "evaluated_at_us",
            "written_at_us",
        ),
    ):
        return False
    ordered_times = [
        times.get(key)
        for key in (
            "event_time_us",
            "lane_available_at_us",
            "decision_at_us",
            "evaluated_at_us",
            "written_at_us",
        )
    ]
    if not all(is_safe_integer(value, nonnegative=True) for value in ordered_times):
        return False
    if ordered_times != sorted(ordered_times):
        return False
    return materialize(record.get("operator")) == {
        "kind": "SYSTEM",
        "id": "rsi-mtf-drl-pm-reducer-v0.2.2",
    }


def encode_ledger(
    contract: Mapping[str, Any],
    ledger_record: Mapping[str, Any],
    as_of_us: int,
    role: str,
) -> bytes:
    """Validate and encode one immutable ledger record without replacement."""

    try:
        serialize_contract(contract)
    except Exception:
        raise KernelValidationError("E_KERNEL_CONTRACT_INVALID") from None
    try:
        if (
            not isinstance(ledger_record, Mapping)
            or not is_safe_integer(as_of_us, nonnegative=True)
            or not isinstance(role, str)
        ):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        if not _ledger_schema_valid(ledger_record):
            raise KernelValidationError("E_KERNEL_SCHEMA_INVALID")
        if ledger_record.get("record_hash") != _record_hash(ledger_record):
            raise KernelValidationError("E_KERNEL_DIGEST_INVALID")
        if (
            role != "SYNTHETIC"
            or ledger_record["identity"].get("role") != role
            or ledger_record["times"].get("written_at_us") > as_of_us
            or not is_sha256(ledger_record["bindings"].get("code_sha256"))
        ):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        return canonical_json(ledger_record)
    except KernelValidationError:
        raise
    except Exception:
        raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID") from None


def _trace_digest_valid(trace: Sequence[Mapping[str, Any]]) -> bool:
    if not trace:
        return False
    for index, record in enumerate(trace):
        if record.get("sequence") != index or record.get("record_hash") != _record_hash(record):
            return False
        if index == 0:
            if (
                record.get("previous_hash") != _ZERO_SHA
                or record.get("event_kind") != "GENESIS"
            ):
                return False
        elif (
            record.get("previous_hash") != trace[index - 1].get("record_hash")
            or record.get("ledger_id") != trace[0].get("ledger_id")
        ):
            return False
    return True


def _management_event_id(
    trace: Sequence[Mapping[str, Any]], source_event_id: Any
) -> Any:
    matches = [
        record.get("event_id")
        for record in trace
        if record.get("source_event_id") == source_event_id
    ]
    return matches[0] if len(matches) == 1 else None


def _path_input_bundle(
    bundle: Mapping[str, Any],
    trace: Sequence[Mapping[str, Any]],
    first_fill: Mapping[str, Any],
    terminal: Mapping[str, Any],
    censored: bool,
    censor_reason: Any,
) -> FrozenMapping:
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    events = tuple(bundle.get("event_array", ()))
    start_index = events.index(first_fill)
    terminal_index = events.index(terminal)
    event_slice = events[start_index : terminal_index + 1]
    fill_economic = first_fill.get("economic_event_time_us")
    fill_causal = first_fill.get("event_time_us")
    path_start = (
        (max(fill_economic, fill_causal) + 999_999) // 1_000_000
    ) * 1_000_000
    h0 = trace[-1]["levels"].get("h0_us")
    book_points: dict[int, dict[str, Any]] = {}
    coverage_artifacts: list[Mapping[str, Any]] = []
    for event in event_slice:
        for artifact_id in event.get("input_artifact_ids", ()):
            wrapper = _find_artifact(artifacts, artifact_id)
            if wrapper is None:
                continue
            payload = _payload(wrapper)
            if payload is None:
                continue
            if wrapper.get("schema_id") == "BOOK_SNAPSHOT":
                grid = event.get("event_time_us")
                side = trace[-1].get("side")
                book_points.setdefault(
                    grid,
                    {
                        "grid_time_us": grid,
                        "book_artifact_id": wrapper.get("artifact_id"),
                        "book_event_id": payload.get("event_id"),
                        "book_event_time_us": payload.get("event_time_us"),
                        "lane_available_at_us": payload.get("lane_available_at_us"),
                        "source_sequence": payload.get("source_sequence"),
                        "exit_side_price": payload.get(
                            "best_bid" if side == "LONG" else "best_ask"
                        ),
                        "payload_sha256": payload.get("payload_sha256"),
                    },
                )
            elif wrapper.get("schema_id") == "SOURCE_COVERAGE_SEAL":
                coverage_artifacts.append(wrapper)
    reducer_events = [
        {
            "management_event_id": _management_event_id(
                trace, event.get("source_event_id")
            ),
            "source_event_id": event.get("source_event_id"),
            "event_kind": event.get("event_kind"),
            "event_time_us": event.get("event_time_us"),
            "economic_event_time_us": event.get("economic_event_time_us"),
            "priority_rank": event.get("priority_rank"),
            "source_sequence": event.get("source_sequence"),
            "predecessor_event_ids": event.get("predecessor_event_ids"),
            "input_artifact_ids": event.get("input_artifact_ids"),
            "payload_sha256": event.get("payload_sha256"),
        }
        for event in event_slice
    ]
    funding_events: list[dict[str, Any]] = []
    for event in event_slice:
        if event.get("event_kind") != "FUNDING_DEBIT":
            continue
        payload = event.get("payload", {})
        funding_ids = [
            artifact_id
            for artifact_id in event.get("input_artifact_ids", ())
            if (_find_artifact(artifacts, artifact_id) or {}).get("schema_id")
            == "SYNTHETIC_FUNDING_OBSERVATION"
        ]
        if len(funding_ids) != 1:
            raise ValueError("funding event does not have one observation")
        funding_events.append(
            {
                "funding_event_id": payload.get("funding_event_id"),
                "source_event_id": event.get("source_event_id"),
                "input_artifact_id": funding_ids[0],
                "economic_event_time_us": payload.get("economic_event_time_us"),
                "event_time_us": event.get("event_time_us"),
                "source_sequence": event.get("source_sequence"),
                "interval_start_us": payload.get("interval_start_us"),
                "interval_end_us": payload.get("interval_end_us"),
                "funding_rate": payload.get("funding_rate"),
                "payload_sha256": event.get("payload_sha256"),
            }
        )
    funding_events.sort(
        key=lambda item: (
            item["event_time_us"],
            item["source_sequence"],
            item["source_event_id"],
        )
    )
    exit_policies = [
        _payload(item)
        for item in artifacts
        if item.get("schema_id") == "EXIT_POLICY_INSTANCE"
    ]
    if len(exit_policies) != 1:
        raise ValueError("filled control lacks one exit policy instance")
    source_coverage = coverage_artifacts[0] if len(coverage_artifacts) == 1 else None
    missing = (
        [terminal.get("event_time_us")]
        if censored and censor_reason in (
            "DATA_GAP",
            "SEQUENCE_CONFLICT",
            "LANE_MIX",
            "ENDPOINT_MISSING",
        )
        else []
    )
    path: dict[str, Any] = {
        "schema_version": "rsi-mtf-drl-pm.path-input-bundle.v0.2.2",
        "opportunity_id": bundle["ledger_identity"]["opportunity_id"],
        "control_id": bundle["ledger_identity"]["control_id"],
        "side": trace[-1]["side"],
        "lane_id": bundle["ledger_identity"]["lane_id"],
        "availability_kind": "SYNTHETIC",
        "first_fill_shared_event_id": first_fill.get("shared_entry_event_id"),
        "first_fill_economic_time_us": fill_economic,
        "first_fill_causal_time_us": fill_causal,
        "path_start_us": path_start,
        "h0_us": h0,
        "evaluated_through_us": terminal.get("event_time_us"),
        "status": "CENSORED" if censored else "COMPLETE",
        "censor_reason": censor_reason if censored else None,
        "censor_cause_event_id": (
            _management_event_id(trace, terminal.get("source_event_id"))
            if censored
            else None
        ),
        "synthetic_coverage_sha256": bundle["coverage"]["coverage_sha256"],
        "source_coverage_artifact_id": (
            source_coverage.get("artifact_id") if source_coverage is not None else None
        ),
        "source_coverage_seal_sha256": (
            _payload(source_coverage).get("seal_sha256")
            if source_coverage is not None
            else None
        ),
        "book_points": [book_points[key] for key in sorted(book_points)],
        "missing_grid_times_us": missing,
        "reducer_events": reducer_events,
        "funding_events": funding_events,
        "funding_events_sha256": stable_id(
            "path-funding-events/v0.2.2", funding_events
        ),
        "exit_policy_sha256": exit_policies[0].get("policy_instance_sha256"),
        "path_input_sha256": _ZERO_SHA,
    }
    path["path_input_sha256"] = stable_id(
        "path-input-bundle/v0.2.2", _without(path, "path_input_sha256")
    )
    return _frozen_mapping(path)


def _label_bindings(
    bundle: Mapping[str, Any],
    trace: Sequence[Mapping[str, Any]],
    entry_binding_sha: str,
) -> dict[str, Any]:
    ledger = bundle["ledger_bindings"]
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    label_policy_artifacts = [
        _payload(item)
        for item in artifacts
        if item.get("schema_id") == "FIRST_HIT_LABEL_POLICY"
    ]
    label_policy_sha = (
        label_policy_artifacts[0].get("policy_sha256")
        if len(label_policy_artifacts) == 1
        else bundle["ledger_seed"]["policy_bindings"]["label_policy_sha256"]
    )
    return {
        "core_raw_sha256": ledger["core_raw_sha256"],
        "v0_2_contract_canonical_sha256": ledger[
            "v0_2_contract_canonical_sha256"
        ],
        "v0_2_1_addendum_raw_sha256": ledger["v0_2_1_addendum_raw_sha256"],
        "v0_2_2_delta_raw_sha256": ledger["v0_2_2_delta_raw_sha256"],
        "v0_2_2_contract_sha256": ledger["v0_2_2_contract_sha256"],
        "composite_theory_id": ledger["composite_theory_id"],
        "candidate_id": bundle["ledger_identity"]["candidate_id"],
        "policy_bundle_sha256": ledger["policy_bundle_sha256"],
        "code_sha256": ledger["code_sha256"],
        "data_or_fixture_sha256": ledger["data_or_fixture_sha256"],
        "synthetic_bundle_sha256": bundle["bundle_sha256"],
        "entry_execution_binding_sha256": entry_binding_sha,
        "management_ledger_head_sha256": trace[-1]["record_hash"],
        "label_policy_sha256": label_policy_sha,
    }


def _first_hit_label_value(
    bundle: Mapping[str, Any], trace: Sequence[Mapping[str, Any]]
) -> FrozenMapping:
    identity = bundle["ledger_identity"]
    control = identity["control_id"]
    side = trace[-1]["side"]
    events = tuple(bundle.get("event_array", ()))
    entry_events = [event for event in events if event.get("event_kind") == "ENTRY_SUBMIT"]
    fill_events = [
        event
        for event in events
        if event.get("event_kind") == "FILL_CUMULATIVE"
        and parse_decimal(event.get("payload", {}).get("cum_qty"), "QtyBase") > 0
    ]
    if control == "C0":
        action_at = bundle["ledger_seed"]["anchor_at_us"]
        envelope: dict[str, Any] = {
            "control_id": "C0",
            "side": "NONE",
            "action_at_us": action_at,
            "submission_label": "NO_ACTION",
            "execution_flags": [],
            "observation_status": "NOT_APPLICABLE",
            "censor_reason": None,
            "market_path_label": None,
            "terminal_event_id": None,
            "terminal_at_us": None,
            "fill_sequence_sha256": None,
            "path_input_sha256": None,
            "pi_exit_sha256": None,
            "label_record_sha256": _ZERO_SHA,
        }
        entry_sha = stable_id(
            "no-entry-execution/v0.2.2",
            {"opportunity_id": identity["opportunity_id"], "control_id": control},
        )
    elif not entry_events:
        terminal = next(
            (
                event
                for event in events
                if event.get("event_kind")
                in (
                    "CONTROL_ABSTAIN",
                    "ACCOUNT_MISMATCH",
                    "KILL",
                    "DATA_HEALTH_INVALID",
                    "EVENT_CONFLICT",
                )
            ),
            events[-1],
        )
        terminal_id = _management_event_id(trace, terminal.get("source_event_id"))
        if terminal.get("event_kind") == "CONTROL_ABSTAIN":
            terminal_id = stable_id(
                "control-abstain-terminal/v0.2.2",
                {
                    "opportunity_id": identity["opportunity_id"],
                    "control_id": control,
                    "terminal_at_us": terminal.get("event_time_us"),
                    "reason_code": terminal.get("payload", {}).get("reason_code"),
                },
            )
        envelope = {
            "control_id": control,
            "side": side,
            "action_at_us": bundle["action_context"]["action_at_us"],
            "submission_label": "NO_ACTION",
            "execution_flags": [],
            "observation_status": "NOT_APPLICABLE",
            "censor_reason": None,
            "market_path_label": None,
            "terminal_event_id": terminal_id,
            "terminal_at_us": terminal.get("event_time_us"),
            "fill_sequence_sha256": None,
            "path_input_sha256": None,
            "pi_exit_sha256": None,
            "label_record_sha256": _ZERO_SHA,
        }
        entry_sha = stable_id(
            "no-entry-execution/v0.2.2",
            {"opportunity_id": identity["opportunity_id"], "control_id": control},
        )
    elif not fill_events:
        binding = bundle.get("entry_execution_binding")
        entry_sha = binding.get("fill_sequence_sha256")
        terminal = next(
            (
                event
                for event in events
                if event.get("event_kind")
                in ("ENTRY_REJECT", "ENTRY_EXPIRE", "CANCEL_ACK")
            ),
            events[-1],
        )
        envelope = {
            "control_id": control,
            "side": side,
            "action_at_us": bundle["action_context"]["action_at_us"],
            "submission_label": "NO_FILL",
            "execution_flags": [],
            "observation_status": "NOT_APPLICABLE",
            "censor_reason": None,
            "market_path_label": None,
            "terminal_event_id": _management_event_id(
                trace, terminal.get("source_event_id")
            ),
            "terminal_at_us": terminal.get("event_time_us"),
            "fill_sequence_sha256": entry_sha,
            "path_input_sha256": None,
            "pi_exit_sha256": None,
            "label_record_sha256": _ZERO_SHA,
        }
    else:
        binding = bundle.get("entry_execution_binding")
        entry_sha = binding.get("fill_sequence_sha256")
        first_fill = fill_events[0]
        market_map = {
            "STOP_HIT": "SL",
            "STRUCTURE_EXIT": "STRUCTURE_EXIT",
            "TARGET_HIT": "TP",
            "HORIZON": "TIMEOUT",
        }
        market = next(
            (
                event
                for event in events[events.index(first_fill) :]
                if event.get("event_kind") in market_map
            ),
            None,
        )
        operational_kinds = {
            "ACCOUNT_MISMATCH",
            "KILL",
            "DATA_HEALTH_INVALID",
            "EVENT_CONFLICT",
            "STOP_REJECT_OR_UNKNOWN",
            "TARGET_REJECT_OR_UNKNOWN",
            "EXIT_REJECT_OR_UNKNOWN",
        }
        operational = next(
            (
                event
                for event in events[events.index(first_fill) :]
                if event.get("event_kind") in operational_kinds
            ),
            None,
        )
        operational_wins = (
            operational is not None
            and (market is None or events.index(operational) < events.index(market))
        )
        terminal = operational if operational_wins else market
        if terminal is None:
            terminal = events[-1]
        censor_reason = None
        if operational_wins:
            reason_code = operational.get("payload", {}).get("reason_code")
            censor_reason = {
                "DATA_GAP": "DATA_GAP",
                "SEQUENCE_CONFLICT": "SEQUENCE_CONFLICT",
                "LANE_MIX": "LANE_MIX",
                "ENDPOINT_MISSING": "ENDPOINT_MISSING",
            }.get(reason_code, "OPERATIONAL_OVERRIDE")
        path = _path_input_bundle(
            bundle,
            trace,
            first_fill,
            terminal,
            operational_wins,
            censor_reason,
        )
        flags: list[str] = []
        if any(
            event.get("payload", {}).get("fill_status") == "PARTIAL"
            for event in fill_events
        ) or trace[-1]["quantities"]["q_auth"] != trace[-1]["quantities"]["submitted_qty"]:
            flags.append("PARTIAL_FILL")
        if operational is not None:
            flags.append("OPERATIONAL_OVERRIDE")
        if any(
            record["state_before"] in ("CLOSED", "EXIT_PENDING")
            and record["event_kind"] == "FILL_CUMULATIVE"
            for record in trace
        ):
            flags.append("LATE_FILL")
        if any(
            record["event_kind"]
            in ("STOP_REJECT_OR_UNKNOWN", "PENDING_DEADLINE")
            and record["state_after"] == "HALTED_RECONCILE"
            for record in trace
        ):
            flags.append("PROTECTION_FAILURE")
        flag_order = (
            "PARTIAL_FILL",
            "OPERATIONAL_OVERRIDE",
            "LATE_FILL",
            "PROTECTION_FAILURE",
        )
        flags = [flag for flag in flag_order if flag in flags]
        envelope = {
            "control_id": control,
            "side": side,
            "action_at_us": bundle["action_context"]["action_at_us"],
            "submission_label": "FILLED",
            "execution_flags": flags,
            "observation_status": "CENSORED" if operational_wins else "COMPLETE",
            "censor_reason": censor_reason,
            "market_path_label": (
                None if operational_wins else market_map.get(terminal.get("event_kind"))
            ),
            "terminal_event_id": _management_event_id(
                trace, terminal.get("source_event_id")
            ),
            "terminal_at_us": terminal.get("event_time_us"),
            "fill_sequence_sha256": entry_sha,
            "path_input_sha256": path["path_input_sha256"],
            "pi_exit_sha256": None,
            "label_record_sha256": _ZERO_SHA,
        }
    artifacts = _artifact_sequence(bundle.get("artifacts")) or ()
    if control == "C5":
        pi = [
            _payload(item)
            for item in artifacts
            if item.get("schema_id") == "PI_EXIT_POLICY"
        ]
        if len(pi) != 1:
            raise ValueError("C5 lacks one PiExit policy")
        envelope["pi_exit_sha256"] = pi[0].get("policy_sha256")
        context = bundle.get("action_context")
        entry_binding = bundle.get("entry_execution_binding")
        if (
            context is not None
            and context.get("entry_mode") == "REPLAY_C4"
            and entry_binding is not None
            and entry_binding.get("source_control_id") != "C4"
        ):
            raise ValueError("C5 did not reuse the C4 entry binding")
    bindings = _label_bindings(bundle, trace, entry_sha)
    if any(record["bindings"]["code_sha256"] != bindings["code_sha256"] for record in trace):
        raise ValueError("label code binding differs from reducer trace")
    envelope["label_record_sha256"] = stable_id(
        "label-record/v0.2.2",
        {
            "bindings": bindings,
            "label": _without(envelope, "label_record_sha256"),
        },
    )
    return _frozen_mapping(envelope)


def first_hit_label(
    contract: Mapping[str, Any],
    validated_bundle: ValidatedBundle,
    reducer_trace: Sequence[Mapping[str, Any]],
    as_of_us: int,
    role: str,
) -> FrozenMapping:
    """Finalize the immutable first-hit label from a revalidated closed replay."""

    try:
        serialize_contract(contract)
    except Exception:
        raise KernelValidationError("E_KERNEL_CONTRACT_INVALID") from None
    try:
        if (
            not isinstance(validated_bundle, ValidatedBundle)
            or not isinstance(reducer_trace, (list, tuple))
            or not reducer_trace
            or not all(isinstance(record, Mapping) for record in reducer_trace)
            or not is_safe_integer(as_of_us, nonnegative=True)
            or not isinstance(role, str)
        ):
            raise KernelValidationError("E_KERNEL_ARGUMENT_INVALID")
        if not all(_ledger_schema_valid(record) for record in reducer_trace):
            raise KernelValidationError("E_KERNEL_SCHEMA_INVALID")
        if not _trace_digest_valid(reducer_trace):
            raise KernelValidationError("E_KERNEL_DIGEST_INVALID")
        carrier = _revalidate_carrier(
            contract, validated_bundle, as_of_us, role
        )
        try:
            expected_trace = reduce_event_array(contract, carrier, as_of_us, role)
        except KernelValidationError:
            raise KernelValidationError("E_KERNEL_BINDING_INVALID") from None
        if canonical_json(expected_trace) != canonical_json(reducer_trace):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        if (
            carrier.bundle["ledger_identity"]["control_id"] != "C0"
            and reducer_trace[-1]["state_after"] != "CLOSED"
        ):
            raise KernelValidationError("E_KERNEL_BINDING_INVALID")
        return _first_hit_label_value(carrier.bundle, reducer_trace)
    except KernelValidationError:
        raise
    except Exception:
        raise KernelValidationError("E_KERNEL_BINDING_INVALID") from None
