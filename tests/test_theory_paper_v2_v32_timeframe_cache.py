from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import re
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_timeframe_cache import (
    DIGEST_FIELD,
    FRAME_ROLES,
    V32TimeframeCacheError,
    build_v32_context_frame_v1,
    build_v32_timeframe_context_state_v1,
    project_v32_refreshed_frame_policy_v1,
    project_v32_timeframe_payloads_v1,
    verify_v32_timeframe_invalidation_bindings_v1,
    verify_v32_timeframe_payload_bindings_v1,
    verify_v32_timeframe_production_policy_v1,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_transition_v1,
)


RUN_ID = "v32-timeframe-test"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


@contextmanager
def _raises(error_type: type[Exception], pattern: str | None = None):
    try:
        yield
    except error_type as exc:
        if pattern is not None and re.search(pattern, str(exc)) is None:
            raise AssertionError(f"{exc!s} does not match {pattern!r}") from exc
    else:
        raise AssertionError(f"{error_type.__name__} was not raised")


def _frame(
    *,
    role: str,
    decision_time: str,
    previous: dict | None = None,
    update_mode: str = "REFRESHED",
    as_of: str,
    available_at: str,
    created_at: str,
    expires_at: str,
    payload_digest: str,
) -> dict:
    return build_v32_context_frame_v1(
        frame_id=f"frame-{role.lower()}",
        role=role,
        update_mode=update_mode,
        created_at=created_at,
        as_of=as_of,
        available_at=available_at,
        expires_at=expires_at,
        payload_digest=payload_digest,
        source_refs=[f"source:{role.lower()}"],
        dependency_groups=[f"dep:{role.lower()}"],
        invalidation_event_types=(
            [
                "MACRO_POLICY_RELEASE",
                "REGULATORY_CHANGE",
                "SOURCE_SCHEMA_DRIFT",
                "EXTREME_VOLATILITY",
            ]
            if role == "STRATEGIC_CONTEXT"
            else []
        ),
        previous_frame=previous,
        decision_time=decision_time,
    )


def _genesis() -> dict:
    decision = "2026-08-07T00:15:00Z"
    return build_v32_timeframe_context_state_v1(
        run_id=RUN_ID,
        cycle_index=1,
        decision_time=decision,
        state_mode="FULL_CONTEXT",
        previous_state=None,
        frames=[
            _frame(
                role="STRATEGIC_CONTEXT",
                decision_time=decision,
                as_of="2026-08-07T00:00:00Z",
                available_at="2026-08-07T00:02:00Z",
                created_at="2026-08-07T00:05:00Z",
                expires_at="2026-08-08T00:05:00Z",
                payload_digest=DIGEST_A,
            ),
            _frame(
                role="TACTICAL_DELTA",
                decision_time=decision,
                as_of="2026-08-07T00:00:00Z",
                available_at="2026-08-07T00:01:00Z",
                created_at="2026-08-07T00:04:00Z",
                expires_at="2026-08-07T01:04:00Z",
                payload_digest=DIGEST_B,
            ),
            _frame(
                role="TRIGGER",
                decision_time=decision,
                as_of="2026-08-07T00:00:00Z",
                available_at="2026-08-07T00:01:00Z",
                created_at="2026-08-07T00:04:00Z",
                expires_at="2026-08-07T00:34:00Z",
                payload_digest=DIGEST_C,
            ),
        ],
        observed_invalidation_events=[],
    )


def _delta(
    previous: dict, *, strategic_refresh: bool = False, events: list[dict] | None = None
) -> dict:
    decision = "2026-08-07T00:30:00Z"
    old = {row["role"]: row for row in previous["frames"]}
    if strategic_refresh:
        strategic = _frame(
            role="STRATEGIC_CONTEXT",
            decision_time=decision,
            previous=old["STRATEGIC_CONTEXT"],
            as_of="2026-08-07T00:20:00Z",
            available_at="2026-08-07T00:22:00Z",
            created_at="2026-08-07T00:24:00Z",
            expires_at="2026-08-08T00:24:00Z",
            payload_digest="d" * 64,
        )
    else:
        prior = old["STRATEGIC_CONTEXT"]
        strategic = build_v32_context_frame_v1(
            frame_id=prior["frame_id"],
            role=prior["role"],
            update_mode="CARRIED_FORWARD",
            created_at=prior["created_at"],
            as_of=prior["as_of"],
            available_at=prior["available_at"],
            expires_at=prior["expires_at"],
            payload_digest=prior["payload_digest"],
            source_refs=prior["source_refs"],
            dependency_groups=prior["dependency_groups"],
            invalidation_event_types=prior["invalidation_event_types"],
            previous_frame=prior,
            decision_time=decision,
        )
    return build_v32_timeframe_context_state_v1(
        run_id=RUN_ID,
        cycle_index=2,
        decision_time=decision,
        state_mode="DELTA_UPDATE",
        previous_state=previous,
        frames=[
            strategic,
            _frame(
                role="TACTICAL_DELTA",
                decision_time=decision,
                previous=old["TACTICAL_DELTA"],
                as_of="2026-08-07T00:15:00Z",
                available_at="2026-08-07T00:16:00Z",
                created_at="2026-08-07T00:20:00Z",
                expires_at="2026-08-07T01:20:00Z",
                payload_digest="e" * 64,
            ),
            _frame(
                role="TRIGGER",
                decision_time=decision,
                previous=old["TRIGGER"],
                as_of="2026-08-07T00:15:00Z",
                available_at="2026-08-07T00:16:00Z",
                created_at="2026-08-07T00:20:00Z",
                expires_at="2026-08-07T00:50:00Z",
                payload_digest="f" * 64,
            ),
        ],
        observed_invalidation_events=events or [],
    )


def _macro_event() -> dict:
    return {
        "event_id": "event-fed-release",
        "event_type": "MACRO_POLICY_RELEASE",
        "occurred_at": "2026-08-07T00:20:00Z",
        "available_at": "2026-08-07T00:22:00Z",
        "evidence_refs": ["public:official-release"],
    }


def _case_full_then_delta_carries_only_strategic_frame() -> None:
    genesis = _genesis()
    assert verify_v32_timeframe_context_state_v1(genesis) == genesis[DIGEST_FIELD]

    delta = _delta(genesis)
    assert (
        verify_v32_timeframe_context_transition_v1(
            previous_state=genesis, current_state=delta
        )
        == delta[DIGEST_FIELD]
    )
    modes = {row["role"]: row["update_mode"] for row in delta["frames"]}
    assert modes == {
        "STRATEGIC_CONTEXT": "CARRIED_FORWARD",
        "TACTICAL_DELTA": "REFRESHED",
        "TRIGGER": "REFRESHED",
    }
    assert delta["strategic_rebuild_required"] is False


def _case_delta_full_verification_requires_exact_predecessor() -> None:
    genesis = _genesis()
    delta = _delta(genesis)
    with _raises(V32TimeframeCacheError, "DELTA_PREVIOUS_REQUIRED"):
        verify_v32_timeframe_context_state_v1(delta)

    wrong = deepcopy(genesis)
    wrong["run_id"] = "other-run"
    wrong = self_digest(wrong, DIGEST_FIELD)
    with _raises(V32TimeframeCacheError):
        verify_v32_timeframe_context_state_v1(delta, previous_state=wrong)


def _case_new_invalidation_event_forces_strategic_refresh() -> None:
    genesis = _genesis()
    with _raises(V32TimeframeCacheError, "STALE_STRATEGIC_CARRY"):
        _delta(genesis, events=[_macro_event()])

    refreshed = _delta(genesis, strategic_refresh=True, events=[_macro_event()])
    assert refreshed["strategic_rebuild_required"] is True
    verify_v32_timeframe_context_transition_v1(
        previous_state=genesis, current_state=refreshed
    )


def _case_fast_frame_carry_forward_is_forbidden() -> None:
    genesis = _genesis()
    old = {row["role"]: row for row in genesis["frames"]}
    decision = "2026-08-07T00:30:00Z"
    prior = old["TRIGGER"]
    with _raises(V32TimeframeCacheError, "CARRY_FORWARD_INVALID"):
        build_v32_context_frame_v1(
            frame_id=prior["frame_id"],
            role="TRIGGER",
            update_mode="CARRIED_FORWARD",
            created_at=prior["created_at"],
            as_of=prior["as_of"],
            available_at=prior["available_at"],
            expires_at=prior["expires_at"],
            payload_digest=prior["payload_digest"],
            source_refs=prior["source_refs"],
            dependency_groups=prior["dependency_groups"],
            invalidation_event_types=[],
            previous_frame=prior,
            decision_time=decision,
        )


def _case_expired_strategic_frame_cannot_be_carried() -> None:
    genesis = _genesis()
    prior = next(
        row for row in genesis["frames"] if row["role"] == "STRATEGIC_CONTEXT"
    )
    with _raises(V32TimeframeCacheError, "FRAME_TIME_INVALID"):
        build_v32_context_frame_v1(
            frame_id=prior["frame_id"],
            role=prior["role"],
            update_mode="CARRIED_FORWARD",
            created_at=prior["created_at"],
            as_of=prior["as_of"],
            available_at=prior["available_at"],
            expires_at=prior["expires_at"],
            payload_digest=prior["payload_digest"],
            source_refs=prior["source_refs"],
            dependency_groups=prior["dependency_groups"],
            invalidation_event_types=prior["invalidation_event_types"],
            previous_frame=prior,
            decision_time="2026-08-08T00:05:00Z",
        )


def _case_point_in_time_and_frozen_speed_policy_fail_closed() -> None:
    with _raises(V32TimeframeCacheError, "FRAME_TIME_INVALID"):
        _frame(
            role="TRIGGER",
            decision_time="2026-08-07T00:15:00Z",
            as_of="2026-08-07T00:10:00Z",
            available_at="2026-08-07T00:16:00Z",
            created_at="2026-08-07T00:16:00Z",
            expires_at="2026-08-07T00:30:00Z",
            payload_digest=DIGEST_A,
        )
    with _raises(V32TimeframeCacheError, "FROZEN_SPEED_POLICY"):
        build_v32_timeframe_context_state_v1(
            run_id=RUN_ID,
            cycle_index=1,
            decision_time="2026-08-07T00:15:00Z",
            state_mode="FULL_CONTEXT",
            previous_state=None,
            frames=_genesis()["frames"],
            observed_invalidation_events=[],
            analysis_clock_interval_seconds=3600,
        )


def _case_frame_and_state_tampering_are_detected() -> None:
    genesis = _genesis()
    tampered = deepcopy(genesis)
    tampered["frames"][0]["payload_digest"] = "9" * 64
    tampered = self_digest(tampered, DIGEST_FIELD)
    with _raises(V32TimeframeCacheError, "FRAME_DIGEST_INVALID"):
        verify_v32_timeframe_context_state_v1(tampered)


def _production_bundle_and_state() -> tuple[dict, dict]:
    bundle = {
        "run_id": RUN_ID,
        "cycle_index": 1,
        "public_market_analysis_bundle_digest": "9" * 64,
        "closed_bar_series": {
            "15M": [{"close": "1", "volume": "2"}],
            "1H": [{"close": "3", "volume": "4"}],
            "4H": [{"close": "5", "volume": "6"}],
        },
        "axis_source_evidence": [
            {
                "axis_id": "AXIS_01",
                "status": "ADMITTED",
                "observed_at": "2026-08-07T00:00:00Z",
                "available_at": "2026-08-07T00:01:00Z",
                "raw_bundle_sha256": "8" * 64,
                "axis_source_evidence_digest": "7" * 64,
            }
        ],
        "request_raw_bindings": [
            {
                "component_id": "SERVER_TIME",
                "status": "OBSERVED",
                "error_code": None,
                "raw_binding": {"relative_ref": "raw/server-time.body"},
            }
        ],
        "axis_source_registry_digest": "6" * 64,
        "datums": [{"datum_id": "ticker-last", "value": "1"}],
        "as_of": "2026-08-07T00:00:00Z",
        "available_at": "2026-08-07T00:01:00Z",
        "aggregate_raw_binding": {"relative_ref": "raw/aggregate.body"},
    }
    payloads = project_v32_timeframe_payloads_v1(bundle)
    decision = "2026-08-07T00:15:00Z"
    frames = []
    for role in FRAME_ROLES:
        policy = project_v32_refreshed_frame_policy_v1(
            role=role,
            run_id=RUN_ID,
            decision_time=decision,
            public_market_analysis_bundle=bundle,
        )
        frames.append(
            build_v32_context_frame_v1(
                frame_id=policy["frame_id"],
                role=role,
                update_mode="REFRESHED",
                created_at=policy["created_at"],
                as_of=policy["as_of"],
                available_at=policy["available_at"],
                expires_at=policy["expires_at"],
                payload_digest=canonical_digest(payloads[role]),
                source_refs=policy["source_refs"],
                dependency_groups=policy["dependency_groups"],
                invalidation_event_types=policy["invalidation_event_types"],
                previous_frame=None,
                decision_time=decision,
            )
        )
    state = build_v32_timeframe_context_state_v1(
        run_id=RUN_ID,
        cycle_index=1,
        decision_time=decision,
        state_mode="FULL_CONTEXT",
        previous_state=None,
        frames=frames,
        observed_invalidation_events=[],
    )
    return bundle, state


def _case_all_frame_payloads_bind_to_current_bundle() -> None:
    bundle, state = _production_bundle_and_state()
    expected = verify_v32_timeframe_payload_bindings_v1(
        timeframe_context_state=state,
        public_market_analysis_bundle=bundle,
    )
    assert set(expected) == set(FRAME_ROLES)
    for role in FRAME_ROLES:
        forged = deepcopy(state)
        row = next(frame for frame in forged["frames"] if frame["role"] == role)
        row["payload_digest"] = "f" * 64
        row_without_digest = {key: value for key, value in row.items() if key != "frame_digest"}
        row["frame_digest"] = canonical_digest(row_without_digest)
        forged = self_digest(forged, DIGEST_FIELD)
        with _raises(V32TimeframeCacheError, "FRAME_PAYLOAD_BINDING_MISMATCH"):
            verify_v32_timeframe_payload_bindings_v1(
                timeframe_context_state=forged,
                public_market_analysis_bundle=bundle,
            )


def _resign_frame_mutation(
    state: dict, *, role: str, changes: dict[str, object]
) -> dict:
    original = next(row for row in state["frames"] if row["role"] == role)
    values = {
        key: deepcopy(original[key])
        for key in (
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
        )
    }
    values.update(changes)
    rebuilt = build_v32_context_frame_v1(
        **values,
        previous_frame=None,
        decision_time=state["decision_time"],
    )
    frames = [
        rebuilt if row["role"] == role else deepcopy(row)
        for row in state["frames"]
    ]
    return build_v32_timeframe_context_state_v1(
        run_id=state["run_id"],
        cycle_index=state["cycle_index"],
        decision_time=state["decision_time"],
        state_mode=state["state_mode"],
        previous_state=None,
        frames=frames,
        observed_invalidation_events=state["observed_invalidation_events"],
    )


def _case_production_policy_rejects_resigned_drift_for_every_role() -> None:
    bundle, state = _production_bundle_and_state()
    assert (
        verify_v32_timeframe_production_policy_v1(
            timeframe_context_state=state,
            public_market_analysis_bundle=bundle,
        )
        == state[DIGEST_FIELD]
    )
    mutations = {
        "long_ttl": {"expires_at": "2026-09-07T00:15:00Z"},
        "source_refs": {"source_refs": ["raw/forged.body"]},
        "dependencies_and_invalidators": {
            "dependency_groups": ["FORGED_DEPENDENCY"],
            "invalidation_event_types": ["REGULATORY_CHANGE"],
        },
        "frame_id": {"frame_id": "v32:forged:frame"},
        "time": {"created_at": "2026-08-07T00:14:59Z"},
    }
    for role in FRAME_ROLES:
        for mutation_name, changes in mutations.items():
            forged = _resign_frame_mutation(
                state, role=role, changes=deepcopy(changes)
            )
            # The attacker has recalculated both the frame and state digests;
            # structural verification alone therefore still succeeds.
            verify_v32_timeframe_context_state_v1(forged)
            with _raises(
                V32TimeframeCacheError,
                f"PRODUCTION_FRAME_POLICY_MISMATCH:{role}",
            ):
                verify_v32_timeframe_production_policy_v1(
                    timeframe_context_state=forged,
                    public_market_analysis_bundle=bundle,
                )


def _case_production_policy_accepts_normal_strategic_carry() -> None:
    bundle, previous = _production_bundle_and_state()
    current_bundle = deepcopy(bundle)
    current_bundle["cycle_index"] = 2
    current_bundle["public_market_analysis_bundle_digest"] = "a" * 64
    decision = "2026-08-07T00:30:00Z"
    previous_frames = {row["role"]: row for row in previous["frames"]}
    current_payloads = project_v32_timeframe_payloads_v1(current_bundle)
    strategic_previous = previous_frames["STRATEGIC_CONTEXT"]
    frames = [
        build_v32_context_frame_v1(
            frame_id=strategic_previous["frame_id"],
            role="STRATEGIC_CONTEXT",
            update_mode="CARRIED_FORWARD",
            created_at=strategic_previous["created_at"],
            as_of=strategic_previous["as_of"],
            available_at=strategic_previous["available_at"],
            expires_at=strategic_previous["expires_at"],
            payload_digest=strategic_previous["payload_digest"],
            source_refs=strategic_previous["source_refs"],
            dependency_groups=strategic_previous["dependency_groups"],
            invalidation_event_types=strategic_previous[
                "invalidation_event_types"
            ],
            previous_frame=strategic_previous,
            decision_time=decision,
        )
    ]
    for role in ("TACTICAL_DELTA", "TRIGGER"):
        policy = project_v32_refreshed_frame_policy_v1(
            role=role,
            run_id=RUN_ID,
            decision_time=decision,
            public_market_analysis_bundle=current_bundle,
        )
        frames.append(
            build_v32_context_frame_v1(
                frame_id=policy["frame_id"],
                role=role,
                update_mode="REFRESHED",
                created_at=policy["created_at"],
                as_of=policy["as_of"],
                available_at=policy["available_at"],
                expires_at=policy["expires_at"],
                payload_digest=canonical_digest(current_payloads[role]),
                source_refs=policy["source_refs"],
                dependency_groups=policy["dependency_groups"],
                invalidation_event_types=policy["invalidation_event_types"],
                previous_frame=previous_frames[role],
                decision_time=decision,
            )
        )
    current = build_v32_timeframe_context_state_v1(
        run_id=RUN_ID,
        cycle_index=2,
        decision_time=decision,
        state_mode="DELTA_UPDATE",
        previous_state=previous,
        frames=frames,
        observed_invalidation_events=[],
    )
    verify_v32_timeframe_context_transition_v1(
        previous_state=previous, current_state=current
    )
    assert (
        verify_v32_timeframe_production_policy_v1(
            timeframe_context_state=current,
            public_market_analysis_bundle=current_bundle,
        )
        == current[DIGEST_FIELD]
    )
    verify_v32_timeframe_payload_bindings_v1(
        timeframe_context_state=current,
        public_market_analysis_bundle=current_bundle,
    )


def _case_unqualified_external_invalidation_is_rejected_formally() -> None:
    genesis = _genesis()
    refreshed = _delta(
        genesis,
        strategic_refresh=True,
        events=[_macro_event()],
    )
    with _raises(V32TimeframeCacheError, "EXTERNAL_INVALIDATION_SOURCE_UNQUALIFIED"):
        verify_v32_timeframe_invalidation_bindings_v1(
            timeframe_context_state=refreshed,
            public_market_analysis_bundle={"pit_member_digests": ["1" * 64]},
            previous_state=genesis,
        )


def _case_strategic_projection_ignores_physical_noise_not_semantic_change() -> None:
    bundle = {
        "public_market_analysis_bundle_digest": "9" * 64,
        "closed_bar_series": {"4H": [{"close": "5"}]},
        "axis_source_evidence": [
            {
                "axis_id": "AXIS_01",
                "status": "ADMITTED",
                "observed_at": "2026-08-07T00:00:00Z",
                "available_at": "2026-08-07T00:01:00Z",
                "raw_bundle_sha256": "8" * 64,
                "axis_source_evidence_digest": "7" * 64,
            }
        ],
        "request_raw_bindings": [
            {
                "component_id": "OPEN_INTEREST",
                "status": "OBSERVED",
                "error_code": None,
            }
        ],
        "axis_source_registry_digest": "6" * 64,
        "datums": [],
        "as_of": "2026-08-07T00:00:00Z",
    }
    baseline = canonical_digest(
        project_v32_timeframe_payloads_v1(bundle)["STRATEGIC_CONTEXT"]
    )
    noise = deepcopy(bundle)
    noise["axis_source_evidence"][0]["observed_at"] = "2026-08-07T00:02:00Z"
    noise["axis_source_evidence"][0]["raw_bundle_sha256"] = "5" * 64
    assert canonical_digest(
        project_v32_timeframe_payloads_v1(noise)["STRATEGIC_CONTEXT"]
    ) == baseline

    axis_change = deepcopy(bundle)
    axis_change["axis_source_evidence"][0]["status"] = "UNKNOWN"
    assert canonical_digest(
        project_v32_timeframe_payloads_v1(axis_change)["STRATEGIC_CONTEXT"]
    ) != baseline

    coverage_change = deepcopy(bundle)
    coverage_change["request_raw_bindings"][0].update(
        {"status": "UNKNOWN", "error_code": "PUBLIC_SOURCE_UNAVAILABLE"}
    )
    assert canonical_digest(
        project_v32_timeframe_payloads_v1(coverage_change)["STRATEGIC_CONTEXT"]
    ) != baseline


class V32TimeframeCacheTests(unittest.TestCase):
    def test_full_then_delta_carries_only_strategic_frame(self) -> None:
        _case_full_then_delta_carries_only_strategic_frame()

    def test_delta_full_verification_requires_exact_predecessor(self) -> None:
        _case_delta_full_verification_requires_exact_predecessor()

    def test_new_invalidation_event_forces_strategic_refresh(self) -> None:
        _case_new_invalidation_event_forces_strategic_refresh()

    def test_fast_frame_carry_forward_is_forbidden(self) -> None:
        _case_fast_frame_carry_forward_is_forbidden()

    def test_expired_strategic_frame_cannot_be_carried(self) -> None:
        _case_expired_strategic_frame_cannot_be_carried()

    def test_point_in_time_and_frozen_speed_policy_fail_closed(self) -> None:
        _case_point_in_time_and_frozen_speed_policy_fail_closed()

    def test_frame_and_state_tampering_are_detected(self) -> None:
        _case_frame_and_state_tampering_are_detected()

    def test_all_frame_payloads_bind_to_current_bundle(self) -> None:
        _case_all_frame_payloads_bind_to_current_bundle()

    def test_production_policy_rejects_resigned_drift_for_every_role(self) -> None:
        _case_production_policy_rejects_resigned_drift_for_every_role()

    def test_production_policy_accepts_normal_strategic_carry(self) -> None:
        _case_production_policy_accepts_normal_strategic_carry()

    def test_unqualified_external_invalidation_is_rejected_formally(self) -> None:
        _case_unqualified_external_invalidation_is_rejected_formally()

    def test_strategic_projection_ignores_physical_noise_not_semantic_change(self) -> None:
        _case_strategic_projection_ignores_physical_noise_not_semantic_change()


if __name__ == "__main__":
    unittest.main()
