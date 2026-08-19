"""Authoritative, offline-only V3.3.2 operational evaluation composition."""

from __future__ import annotations

from typing import Any, Mapping

from ...application.market_cycle.data_profiles import (
    AssetDataProfileMarketDataAdapter,
)
from ...application.market_cycle.evaluation import (
    _build_operational_evaluation_facts_from_verified_cycle,
)
from ...application.market_cycle.ports import OutcomeRequest
from ...application.market_cycle.source import capture_input_snapshot
from ...domain.contracts.canonical import canonical_bytes
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
)
from ...domain.market_cycle.evaluation import (
    OperationalEvaluationContractError,
    OperationalEvaluationFactsV1,
)
from ...domain.market_cycle.evidence import (
    EvidencePolicy,
    V332_EVIDENCE_POLICY_ID,
)
from ...domain.market_cycle.theory import V332_THEORY_IDENTITY
from ..market_data.okx_profiles import (
    HYPE_OKX_PROFILE_ID,
    build_hype_data_profile_service,
)
from ..market_data.okx_transport import (
    PUBLIC_ROUTE_POLICY_ID,
    OkxPublicTransport,
)
from ..market_data.raw_capture import FileRawCaptureStore
from .okx_outcome import OkxMarkOutcome
from .runtime import MarketCycleRuntime


_ARTIFACT_MODELS = (
    ("InputSnapshot", InputSnapshot),
    ("HypothesisRecord", HypothesisRecord),
    ("BehaviorPlan", BehaviorPlan),
    ("Outcome", Outcome),
    ("Review", Review),
)


class _ReplaySideEffectForbidden(RuntimeError):
    pass


class _ReplayOnlyOpener:
    """Match the production route identity while making network use impossible."""

    route_policy_id = PUBLIC_ROUTE_POLICY_ID

    def open(self, request: object, timeout: float) -> object:
        del request, timeout
        raise _ReplaySideEffectForbidden("EVALUATION_NETWORK_FORBIDDEN")


def _forbidden_clock() -> str:
    raise _ReplaySideEffectForbidden("EVALUATION_CLOCK_FALLBACK_FORBIDDEN")


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise OperationalEvaluationContractError(reason)


def _runtime_identity(manifest: object) -> dict[str, Any]:
    identity_dict = getattr(manifest, "identity_dict", None)
    identity_sha256 = getattr(manifest, "identity_sha256", None)
    if not callable(identity_dict) or not isinstance(identity_sha256, str):
        raise OperationalEvaluationContractError("runtime manifest identity is invalid")
    value = dict(identity_dict())
    value["run_manifest_identity_sha256"] = identity_sha256
    return value


def _load_completed_artifacts(
    runtime: MarketCycleRuntime, cycle_id: str
) -> tuple[
    tuple[ArtifactRef, ...],
    InputSnapshot,
    HypothesisRecord,
    BehaviorPlan,
    Outcome,
    Review,
]:
    state = runtime.repository.load_state(cycle_id)
    _require(
        state.stage == "COMPLETE" and state.terminal and state.next_action is None,
        "operational evaluation requires one completed cycle",
    )
    references = tuple(state.artifact_refs)
    _require(
        tuple(item.artifact_type for item in references)
        == tuple(item[0] for item in _ARTIFACT_MODELS),
        "completed cycle artifact chain is incomplete or unordered",
    )
    artifacts: list[object] = []
    for artifact_type, model in _ARTIFACT_MODELS:
        value = runtime.repository.load_artifact(cycle_id, artifact_type)
        artifacts.append(model.from_dict(value))
    return (references, *artifacts)  # type: ignore[return-value]


def _verify_request_snapshot_binding(
    *, manifest: object, request: object, snapshot: InputSnapshot
) -> None:
    fields = (
        ("request_id", "request_id"),
        ("cycle_id", "cycle_id"),
        ("venue_id", "venue_id"),
        ("instrument_id", "instrument_id"),
        ("contract_identity", "contract_identity"),
        ("analysis_profile", "analysis_profile"),
        ("data_profile", "data_profile"),
        ("outcome_horizon_seconds", "outcome_horizon_seconds"),
        ("outcome_tolerance_seconds", "outcome_tolerance_seconds"),
        ("lawful_actions", "lawful_actions"),
        ("theory_identity", "theory_identity"),
    )
    for request_field, snapshot_field in fields:
        _require(
            getattr(request, request_field) == getattr(snapshot, snapshot_field),
            f"request and snapshot {request_field} mismatch",
        )
    _require(
        snapshot.contract_identity
        == getattr(manifest, "market_contract_identity", None),
        "runtime and snapshot market contract mismatch",
    )
    _require(
        snapshot.theory_identity.manifest_digest
        == getattr(manifest, "theory_manifest_sha256", None),
        "runtime and snapshot theory manifest mismatch",
    )


def _verify_input_snapshot_semantics(
    runtime: MarketCycleRuntime, request: object, snapshot: InputSnapshot
) -> None:
    raw_store = FileRawCaptureStore(runtime.runtime_root)
    adapter = AssetDataProfileMarketDataAdapter(
        service=build_hype_data_profile_service(raw_store=raw_store),
        profile_id=HYPE_OKX_PROFILE_ID,
    )
    try:
        replayed = capture_input_snapshot(
            request,  # type: ignore[arg-type]
            market_data=adapter,
            clock=lambda: snapshot.sealed_at,
        )
    except OperationalEvaluationContractError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise OperationalEvaluationContractError(
            "input snapshot cannot be replayed from admitted sealed raw"
        ) from exc
    _require(
        canonical_bytes(replayed.to_dict()) == canonical_bytes(snapshot.to_dict()),
        "sealed InputSnapshot does not match admitted raw replay",
    )


def _replay_outcome(
    runtime: MarketCycleRuntime,
    *,
    request: object,
    plan: BehaviorPlan,
    outcome: Outcome,
) -> object:
    _require(
        outcome.due_at == plan.outcome_due_at
        and outcome.tolerance_seconds == plan.outcome_tolerance_seconds,
        "Outcome window does not match BehaviorPlan",
    )
    raw_store = FileRawCaptureStore(runtime.runtime_root)
    transport = OkxPublicTransport(
        raw_sink=raw_store,
        clock=_forbidden_clock,
        opener=_ReplayOnlyOpener(),
    )
    outcome_port = OkxMarkOutcome(
        transport=transport,
        clock=_forbidden_clock,
        allow_public_collection=False,
    )
    try:
        return outcome_port.observe(
            OutcomeRequest(
                cycle_id=outcome.cycle_id,
                venue_id=getattr(request, "venue_id"),
                instrument_id=getattr(request, "instrument_id"),
                price_field="MARK_PRICE",
                due_at=plan.outcome_due_at,
                tolerance_seconds=plan.outcome_tolerance_seconds,
                # V3.3.2 always preregisters the forward path at the sealed
                # Agent decision time.  The stored Outcome cannot opt out of
                # replay merely by deleting or downgrading its path schema.
                path_start_at=plan.agent_delivered_at,
            )
        )
    except (OSError, TypeError, ValueError, _ReplaySideEffectForbidden) as exc:
        raise OperationalEvaluationContractError(
            "Outcome cannot be replayed from exact sealed raw"
        ) from exc


def _verify_observed_outcome_semantics(
    runtime: MarketCycleRuntime,
    *,
    request: object,
    plan: BehaviorPlan,
    outcome: Outcome,
) -> None:
    _require(outcome.terminal_status == "OBSERVED", "observed Outcome required")
    replayed = _replay_outcome(
        runtime, request=request, plan=plan, outcome=outcome
    )

    endpoint = outcome.endpoint_observation
    _require(isinstance(endpoint, Mapping), "observed Outcome endpoint is unavailable")
    _require(outcome.raw_refs, "observed Outcome must bind raw capture evidence")
    expected = {
        "terminal_status": "OBSERVED",
        "value": endpoint.get("value"),
        "unit": endpoint.get("unit"),
        "effective_at": endpoint.get("effective_at"),
        "available_at": endpoint.get("available_at"),
        "observed_at": outcome.observed_at,
        "raw_ref": outcome.raw_refs[0].to_dict(),
        "source_health": outcome.path_observations.get("source_health"),
        "path_observations": {
            key: value
            for key, value in outcome.path_observations.items()
            if key != "source_health"
        },
        "additional_raw_refs": [
            reference.to_dict() for reference in outcome.raw_refs[1:]
        ],
    }
    actual = {
        "terminal_status": replayed.terminal_status,
        "value": replayed.value,
        "unit": replayed.unit,
        "effective_at": replayed.effective_at,
        "available_at": replayed.available_at,
        "observed_at": replayed.observed_at,
        "raw_ref": replayed.raw_ref,
        "source_health": list(replayed.source_health),
        "path_observations": (
            {}
            if replayed.path_observations is None
            else dict(replayed.path_observations)
        ),
        "additional_raw_refs": list(replayed.additional_raw_refs),
    }
    _require(
        canonical_bytes(actual) == canonical_bytes(expected),
        "sealed Outcome does not match exact raw semantic replay",
    )


def _verify_typed_missing_outcome_semantics(
    runtime: MarketCycleRuntime,
    *,
    request: object,
    plan: BehaviorPlan,
    outcome: Outcome,
) -> None:
    _require(
        outcome.terminal_status == "TYPED_MISSING"
        and outcome.endpoint_observation is None,
        "typed-missing Outcome cannot contain endpoint evidence",
    )
    if not outcome.raw_refs:
        return
    replayed = _replay_outcome(
        runtime, request=request, plan=plan, outcome=outcome
    )
    source_health = outcome.path_observations.get("source_health")
    _require(
        isinstance(source_health, (list, tuple)),
        "typed-missing Outcome source health is invalid",
    )
    mark_raw_ref: Mapping[str, Any] | None = None
    path_raw_refs: list[Mapping[str, Any]] = []
    for item in source_health:
        _require(
            isinstance(item, Mapping),
            "typed-missing Outcome source health is invalid",
        )
        raw_ref = item.get("raw_ref")
        if raw_ref is None:
            continue
        _require(
            isinstance(raw_ref, Mapping),
            "typed-missing Outcome source health raw ref is invalid",
        )
        if item.get("component_id") == "OUTCOME_MARK_PRICE":
            _require(
                mark_raw_ref is None,
                "typed-missing Outcome mark raw set is ambiguous",
            )
            mark_raw_ref = raw_ref
        elif item.get("component_id") == "OUTCOME_CLOSED_CANDLES_15M":
            path_raw_refs.append(raw_ref)
    expected_refs = ([] if mark_raw_ref is None else [mark_raw_ref]) + path_raw_refs
    deduplicated_refs: list[Mapping[str, Any]] = []
    digests: set[object] = set()
    for reference in expected_refs:
        if reference.get("sha256") not in digests:
            deduplicated_refs.append(reference)
            digests.add(reference.get("sha256"))
    _require(
        canonical_bytes([reference.to_dict() for reference in outcome.raw_refs])
        == canonical_bytes(deduplicated_refs),
        "typed-missing Outcome raw set is invalid",
    )
    expected = {
        "terminal_status": "MISSING",
        "value": None,
        "unit": None,
        "effective_at": None,
        "available_at": None,
        "observed_at": outcome.observed_at,
        "missing_reason": outcome.typed_missing,
        "raw_ref": None if mark_raw_ref is None else dict(mark_raw_ref),
        "source_health": source_health,
        "path_observations": {
            key: value
            for key, value in outcome.path_observations.items()
            if key != "source_health"
        },
        "additional_raw_refs": [dict(reference) for reference in path_raw_refs],
    }
    actual = {
        "terminal_status": getattr(replayed, "terminal_status", None),
        "value": getattr(replayed, "value", None),
        "unit": getattr(replayed, "unit", None),
        "effective_at": getattr(replayed, "effective_at", None),
        "available_at": getattr(replayed, "available_at", None),
        "observed_at": getattr(replayed, "observed_at", None),
        "missing_reason": getattr(replayed, "missing_reason", None),
        "raw_ref": getattr(replayed, "raw_ref", None),
        "source_health": list(getattr(replayed, "source_health", ())),
        "path_observations": (
            {}
            if getattr(replayed, "path_observations", None) is None
            else dict(replayed.path_observations)
        ),
        "additional_raw_refs": list(
            getattr(replayed, "additional_raw_refs", ())
        ),
    }
    _require(
        canonical_bytes(actual) == canonical_bytes(expected),
        "sealed typed-missing Outcome does not match exact raw semantic replay",
    )


def evaluate_completed_cycle_operationally(
    *,
    runtime: MarketCycleRuntime,
    cycle_id: str,
    evaluation_id: str,
    evaluated_at: str,
    evidence_policy: EvidencePolicy,
) -> OperationalEvaluationFactsV1:
    """Derive no-score E0 facts from one verified COMPLETE runtime cycle.

    No run identity, artifact, raw reference, paper projection, or attention
    event is accepted from the caller.  This keeps E0 focused on the market
    cycle itself; paper and attention effectiveness remain a separate E1 gate.
    """

    if not isinstance(runtime, MarketCycleRuntime):
        raise OperationalEvaluationContractError("MarketCycleRuntime is required")
    if (
        runtime.identity != V332_THEORY_IDENTITY
        or not isinstance(evidence_policy, EvidencePolicy)
        or evidence_policy.policy_id != V332_EVIDENCE_POLICY_ID
    ):
        raise OperationalEvaluationContractError(
            "V3.3.2 operational evaluation identity is required"
        )
    experiment_policy = runtime.experiment_policy
    if (
        experiment_policy is None
        or experiment_policy.phase != "CAPABILITY_PILOT"
        or experiment_policy.capability_ids != ("OPERATIONAL_EVALUATION",)
    ):
        raise OperationalEvaluationContractError(
            "operational evaluation requires a singleton capability pilot policy"
        )
    try:
        manifest = runtime.service.verify_cycle_read(cycle_id)
        request = runtime.repository.load_request(cycle_id)
        (
            references,
            snapshot,
            hypothesis,
            plan,
            outcome,
            review,
        ) = _load_completed_artifacts(runtime, cycle_id)
    except OperationalEvaluationContractError:
        raise
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        raise OperationalEvaluationContractError(
            "runtime cycle provenance verification failed"
        ) from exc

    _verify_request_snapshot_binding(
        manifest=manifest, request=request, snapshot=snapshot
    )
    _verify_input_snapshot_semantics(runtime, request, snapshot)
    _require(
        outcome.due_at == plan.outcome_due_at
        and outcome.tolerance_seconds == plan.outcome_tolerance_seconds,
        "Outcome window does not match BehaviorPlan",
    )
    if outcome.terminal_status == "OBSERVED":
        _verify_observed_outcome_semantics(
            runtime, request=request, plan=plan, outcome=outcome
        )
    else:
        _verify_typed_missing_outcome_semantics(
            runtime, request=request, plan=plan, outcome=outcome
        )

    return _build_operational_evaluation_facts_from_verified_cycle(
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
        run_identity=_runtime_identity(manifest),
        evidence_policy=evidence_policy,
        snapshot=snapshot,
        snapshot_ref=references[0],
        hypothesis=hypothesis,
        hypothesis_ref=references[1],
        plan=plan,
        plan_ref=references[2],
        outcome=outcome,
        outcome_ref=references[3],
        review=review,
        review_ref=references[4],
    )


__all__ = ["evaluate_completed_cycle_operationally"]
