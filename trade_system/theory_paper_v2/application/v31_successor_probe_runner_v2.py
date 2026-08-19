"""Execute the successor V3.1 qualification probes without a real run.

The public entry point accepts bindings and a timestamp, never PASS values.
Every aggregate PASS is derived from focused failure injections against the
raw-first outcome state machine, its capture-only adapter/evidence store, and
the versioned experiment supervisor.  All HTTP behavior is injected locally;
this module cannot create an automation, account connection, order, or run.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import tempfile
import threading
from typing import Any, Mapping, Sequence
from unittest.mock import patch

from .v31_experiment_supervisor_v2 import (
    V31ExperimentSupervisorV2WorkflowError,
    initialize_v31_experiment_supervisor_v2,
    open_v31_cycle_permit_v2,
    record_v31_cycle_commit_v2,
    reserve_v31_cycle_commit_v2,
    verify_v31_cycle_permit_live_v2,
)
from .v31_monitor_runtime import initialize_v31_monitor_runtime
from .v31_outcome_resolution_v2 import (
    V31OutcomeResolutionV2Error,
    initialize_v31_outcome_evidence_runtime_v2,
    resolve_due_v31_monitor_v2,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.governance.v31_successor_probe_evidence_v2 import (
    RAW_FIRST_FAMILY,
    RAW_NETWORK_BOUNDARY,
    SUPERVISOR_FAMILY,
    SUPERVISOR_NETWORK_BOUNDARY,
    build_executed_probe_case_receipt_v2,
    build_executed_probe_family_evidence_v2,
    build_probe_runtime_closure_evidence_v2,
)
from ..domain.governance.v31_successor_qualification_v2 import (
    RAW_FIRST_FAILURE_CASES,
    SUPERVISOR_GATE_CASES,
    build_raw_first_failure_probe_v2,
    build_supervisor_gate_probe_v2,
)
from ..domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    build_minimal_experiment_contract,
    build_typed_path_monitor_plan,
)
from ..domain.v31_monitor_runtime import monitor_cycle_root
from ..domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    build_outcome_clock_policy,
    build_public_outcome_capture,
    parse_public_outcome_capture,
    verify_outcome_clock_policy,
)
from ..infrastructure.authority.v31_runtime_closure_v2 import (
    verify_v31_runtime_closure_bindings_v2,
)
from ..infrastructure.fresh_market.binance_usdm import HttpCapture
from ..infrastructure.v31_monitor_store import LocalV31MonitorStore
from ..infrastructure.v31_outcome_evidence_store_v2 import (
    LocalV31OutcomeEvidenceStoreV2,
    V31OutcomeEvidenceStoreV2Error,
)
from ..infrastructure.v31_public_outcome_capture_v2 import (
    OkxPublicOutcomeCaptureAdapterV2,
)
from ..infrastructure.v31_supervisor_store_v2 import LocalV31SupervisorStoreV2


class V31SuccessorProbeRunnerV2Error(ValueError):
    """A focused injection did not produce its preregistered observation."""


RUNNER_MODULE_PATH = (
    "trade_system/theory_paper_v2/application/v31_successor_probe_runner_v2.py"
)
RAW_TESTED_MODULE_PATHS = (
    RUNNER_MODULE_PATH,
    "trade_system/theory_paper_v2/application/v31_outcome_resolution_v2.py",
    "trade_system/theory_paper_v2/domain/v31_outcome_capture_v2.py",
    "trade_system/theory_paper_v2/infrastructure/v31_monitor_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_outcome_evidence_store_v2.py",
    "trade_system/theory_paper_v2/infrastructure/v31_public_outcome_capture_v2.py",
)
SUPERVISOR_TESTED_MODULE_PATHS = (
    RUNNER_MODULE_PATH,
    "trade_system/theory_paper_v2/application/v31_experiment_supervisor_v2.py",
    "trade_system/theory_paper_v2/domain/v31_experiment_supervisor_v2.py",
    "trade_system/theory_paper_v2/infrastructure/v31_supervisor_store_v2.py",
)

_PROBE_DECISION_AT = "2026-08-07T01:00:00Z"
_PROBE_CREATED_AT = "2026-08-07T01:00:01Z"
_PROBE_PLAN_WRITTEN_AT = "2026-08-07T01:00:02Z"
_PROBE_REQUESTED_AT = "2026-08-07T02:00:08Z"
_PROBE_RECOVERY_AT = "2026-08-07T02:00:09Z"
_PROBE_RECEIVED_AT = "2026-08-07T02:00:08.200000Z"
_OBSERVABLE_REF = "metric:mark-price-change-at-1h-horizon"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise V31SuccessorProbeRunnerV2Error(code)


def _exception_text(exc: BaseException) -> str:
    value = str(exc)
    return value if value else type(exc).__name__


def _timestamp_ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


def _valid_raw(*, received_at: str = _PROBE_RECEIVED_AT, offset_ms: int = -500) -> bytes:
    received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    provider = received + timedelta(milliseconds=offset_ms)
    return (
        '{"code":"0","data":[{"instId":"BTC-USDT-SWAP",'
        '"instType":"SWAP","markPx":"65000.1","ts":"'
        + _timestamp_ms(provider)
        + '"}]}'
    ).encode("utf-8")


class _StepClock:
    def __init__(self, values: Sequence[datetime]) -> None:
        self._values = tuple(values)
        self._position = 0
        self._lock = threading.Lock()
        if not self._values:
            raise V31SuccessorProbeRunnerV2Error("V31_PROBE_CLOCK_EMPTY")

    def __call__(self) -> datetime:
        with self._lock:
            position = min(self._position, len(self._values) - 1)
            self._position += 1
            return self._values[position]


class _StepMonotonic:
    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def __call__(self) -> int:
        with self._lock:
            value = self._value
            self._value += 2_000_000
            return value


class _InjectedTransport:
    """Controlled local response/error; never opens a network connection."""

    def __init__(
        self,
        *,
        body: bytes | None = None,
        error: BaseException | None = None,
        received_at: str = _PROBE_RECEIVED_AT,
    ) -> None:
        self.body = body
        self.error = error
        self.received_at = datetime.fromisoformat(
            received_at.replace("Z", "+00:00")
        )
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpCapture:
        _require(url == OKX_MARK_PRICE_URL, "V31_PROBE_TRANSPORT_URL_DRIFT")
        _require(timeout == 15.0, "V31_PROBE_TRANSPORT_TIMEOUT_DRIFT")
        self.calls += 1
        if self.error is not None:
            raise self.error
        _require(isinstance(self.body, bytes), "V31_PROBE_TRANSPORT_BODY_MISSING")
        return HttpCapture(
            status=200,
            headers={"Content-Type": "application/json"},
            body=self.body,
            received_at=self.received_at,
            final_url=OKX_MARK_PRICE_URL,
        )


class _BlockingInjectedTransport(_InjectedTransport):
    def __init__(self, *, body: bytes) -> None:
        super().__init__(body=body)
        self.started = threading.Event()
        self.release = threading.Event()

    def get(self, url: str, timeout: float) -> HttpCapture:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise V31SuccessorProbeRunnerV2Error(
                "V31_PROBE_BLOCKING_TRANSPORT_NOT_RELEASED"
            )
        return super().get(url, timeout)


def _adapter(transport: _InjectedTransport) -> OkxPublicOutcomeCaptureAdapterV2:
    start = datetime.fromisoformat(_PROBE_REQUESTED_AT.replace("Z", "+00:00"))
    return OkxPublicOutcomeCaptureAdapterV2(
        transport=transport,
        clock=_StepClock((start, start + timedelta(milliseconds=10))),
        monotonic_ns=_StepMonotonic(),
        timeout=15.0,
    )


def _monitor_rules() -> tuple[FrozenMonitorRule, ...]:
    return (
        FrozenMonitorRule(
            rule_id="confirm-positive",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=_OBSERVABLE_REF,
            operator=MonitorOperator.GT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="contradict-negative",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=_OBSERVABLE_REF,
            operator=MonitorOperator.LT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="falsify-large-loss",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=_OBSERVABLE_REF,
            operator=MonitorOperator.LTE,
            expected="-5",
            unit="PERCENT",
        ),
    )


def _raw_context(
    root: Path,
    *,
    case_tag: str,
    clock_policy: Mapping[str, Any],
) -> tuple[
    str,
    Mapping[str, Any],
    LocalV31MonitorStore,
    LocalV31OutcomeEvidenceStoreV2,
    Mapping[str, Any],
]:
    run_id = f"v31-local-successor-probe-{case_tag}"
    contract = build_minimal_experiment_contract(
        contract_id=f"v31-successor-probe-contract-{case_tag}",
        run_id=run_id,
        frozen_at="2026-08-07T00:00:00Z",
    )
    origin_bindings = {
        "accepted_state": {
            "ref": "cycles/0001/accepted-research-state.json",
            "digest": "a" * 64,
        },
        "path_set": {"ref": "path-set:probe", "digest": "b" * 64},
        "path": {"ref": "path:probe", "digest": "c" * 64},
        "hypothesis_revision": {
            "ref": "hypothesis:probe",
            "digest": "d" * 64,
        },
        "expectation_revision": {
            "ref": "expectation:probe",
            "digest": "e" * 64,
        },
    }
    plan = build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id="monitor:probe:1",
        cycle_id="cycle:probe:1",
        cycle_index=1,
        origin_bindings=origin_bindings,
        decision_at=_PROBE_DECISION_AT,
        observable_ref=_OBSERVABLE_REF,
        source_request_id="okx-public-mark-price:probe:1",
        rules=_monitor_rules(),
    )
    monitor_store = LocalV31MonitorStore(root)
    initialize_v31_monitor_runtime(
        store=monitor_store,
        experiment_contract=contract,
        created_at=_PROBE_CREATED_AT,
    )
    plan_ref = f"{monitor_cycle_root(1)}/monitor-plan.json"
    binding = monitor_store.write_document(
        relative_ref=plan_ref,
        document=plan,
        digest_field="monitor_plan_digest",
    )
    checkpoint = monitor_store.load_checkpoint(run_id=run_id)
    monitor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        checkpoint={
            **checkpoint,
            "revision": int(checkpoint["revision"]) + 1,
            "plan_bindings": [
                {
                    "cycle_index": 1,
                    "relative_ref": binding["relative_ref"],
                    "semantic_digest": binding["semantic_digest"],
                    "physical_sha256": binding["physical_sha256"],
                    "accepted_state_digest": origin_bindings["accepted_state"][
                        "digest"
                    ],
                }
            ],
            "updated_at": _PROBE_PLAN_WRITTEN_AT,
        },
    )
    evidence_store = LocalV31OutcomeEvidenceStoreV2(root)
    initialize_v31_outcome_evidence_runtime_v2(
        evidence_store=evidence_store,
        experiment_contract=contract,
        created_at=_PROBE_CREATED_AT,
        clock_policy=clock_policy,
    )
    return run_id, contract, monitor_store, evidence_store, plan


def _resolve(
    *,
    monitor_store: LocalV31MonitorStore,
    evidence_store: LocalV31OutcomeEvidenceStoreV2,
    contract: Mapping[str, Any],
    adapter: OkxPublicOutcomeCaptureAdapterV2,
    requested_at: str = _PROBE_REQUESTED_AT,
    clock_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    return resolve_due_v31_monitor_v2(
        monitor_store=monitor_store,
        evidence_store=evidence_store,
        experiment_contract=contract,
        capture_port=adapter,
        requested_at=requested_at,
        clock_policy=clock_policy,
    )


def _case_attempt_only_crash(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    run_id, contract, monitor, evidence, _plan = _raw_context(
        root, case_tag="attempt-only", clock_policy=clock_policy
    )
    transport = _InjectedTransport(error=SystemExit("injected-before-response"))
    adapter = _adapter(transport)
    first_code = None
    try:
        _resolve(
            monitor_store=monitor,
            evidence_store=evidence,
            contract=contract,
            adapter=adapter,
            clock_policy=clock_policy,
        )
    except SystemExit as exc:
        first_code = _exception_text(exc)
    _require(first_code == "injected-before-response", "V31_PROBE_ATTEMPT_CRASH_MISSING")
    second_code = None
    try:
        _resolve(
            monitor_store=monitor,
            evidence_store=evidence,
            contract=contract,
            adapter=adapter,
            requested_at=_PROBE_RECOVERY_AT,
            clock_policy=clock_policy,
        )
    except V31OutcomeResolutionV2Error as exc:
        second_code = _exception_text(exc)
    evidence_checkpoint = evidence.load_checkpoint(run_id=run_id)
    monitor_checkpoint = monitor.load_checkpoint(run_id=run_id)
    _require(
        second_code == "V31_OUTCOME_V2_LOCAL_RECOVERY_FAILED",
        "V31_PROBE_ATTEMPT_ONLY_RECOVERY_NOT_CLOSED",
    )
    _require(transport.calls == 1, "V31_PROBE_ATTEMPT_ONLY_REFETCHED")
    _require(
        evidence_checkpoint["status"] == "FAILED_CLOSED"
        and monitor_checkpoint["status"] == "FAILED_CLOSED",
        "V31_PROBE_ATTEMPT_ONLY_NOT_FAILED_CLOSED",
    )
    return (
        {
            "first_process_boundary": "SYSTEM_EXIT_BEFORE_RESPONSE",
            "first_exception": first_code,
            "recovery_exception": second_code,
            "transport_get_count": transport.calls,
            "second_get_count": 0,
            "evidence_status": evidence_checkpoint["status"],
            "monitor_status": monitor_checkpoint["status"],
            "retry_allowed": False,
        },
        "V31_OUTCOME_V2_LOCAL_RECOVERY_FAILED",
    )


def _boundary_parse_observation(
    *, clock_policy: Mapping[str, Any], offset_ms: int
) -> Mapping[str, Any]:
    raw = _valid_raw(offset_ms=offset_ms)
    capture = build_public_outcome_capture(
        run_id="v31-local-successor-probe-clock-vector",
        cycle_index=1,
        monitor_plan_digest="1" * 64,
        monitor_attempt_digest="2" * 64,
        source_request_id="okx-public-mark-price:probe:clock",
        requested_at=_PROBE_REQUESTED_AT,
        request_started_at=_PROBE_REQUESTED_AT,
        response_received_at=_PROBE_RECEIVED_AT,
        monotonic_elapsed_ms=2,
        status_code=200,
        content_type="application/json",
        final_url=OKX_MARK_PRICE_URL,
        raw_payload=raw,
    )
    return parse_public_outcome_capture(
        capture=capture,
        raw_payload=raw,
        clock_policy=clock_policy,
        observable_ref=_OBSERVABLE_REF,
    )


def _case_clock_policy(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    run_id, contract, monitor, evidence, _plan = _raw_context(
        root, case_tag="clock-drift", clock_policy=clock_policy
    )
    transport = _InjectedTransport(error=SystemExit("must-not-be-called"))
    adapter = _adapter(transport)
    changed = build_outcome_clock_policy(
        max_provider_clock_lead_ms=1_999,
        max_provider_age_ms=5_000,
    )
    drift_code = None
    try:
        _resolve(
            monitor_store=monitor,
            evidence_store=evidence,
            contract=contract,
            adapter=adapter,
            clock_policy=changed,
        )
    except V31OutcomeResolutionV2Error as exc:
        drift_code = _exception_text(exc)
    attempt_count = len(
        monitor.load_checkpoint(run_id=run_id)["resolution_attempt_bindings"]
    )
    vectors = {
        "provider_lead_plus_2000_ms": _boundary_parse_observation(
            clock_policy=clock_policy, offset_ms=2_000
        ),
        "provider_lead_plus_2001_ms": _boundary_parse_observation(
            clock_policy=clock_policy, offset_ms=2_001
        ),
        "provider_lag_minus_5000_ms": _boundary_parse_observation(
            clock_policy=clock_policy, offset_ms=-5_000
        ),
        "provider_lag_minus_5001_ms": _boundary_parse_observation(
            clock_policy=clock_policy, offset_ms=-5_001
        ),
    }
    statuses = {name: row["parse_status"] for name, row in vectors.items()}
    errors = {name: row["error_code"] for name, row in vectors.items()}
    _require(
        drift_code == "V31_OUTCOME_V2_CLOCK_POLICY_BINDING_MISMATCH",
        "V31_PROBE_CLOCK_DRIFT_NOT_REJECTED",
    )
    _require(
        transport.calls == 0 and attempt_count == 0,
        "V31_PROBE_CLOCK_DRIFT_REACHED_CAPTURE",
    )
    _require(
        statuses
        == {
            "provider_lead_plus_2000_ms": "ADMITTED_OBSERVED",
            "provider_lead_plus_2001_ms": "ADMITTED_UNKNOWN",
            "provider_lag_minus_5000_ms": "ADMITTED_OBSERVED",
            "provider_lag_minus_5001_ms": "ADMITTED_UNKNOWN",
        },
        "V31_PROBE_CLOCK_BOUNDARY_STATUS_INVALID",
    )
    _require(
        errors["provider_lead_plus_2001_ms"] == "CLOCK_BOUND_EXCEEDED"
        and errors["provider_lag_minus_5001_ms"] == "CLOCK_BOUND_EXCEEDED",
        "V31_PROBE_CLOCK_BOUNDARY_ERROR_INVALID",
    )
    return (
        {
            "policy_drift_exception": drift_code,
            "transport_get_count_before_rejection": transport.calls,
            "attempt_count_before_rejection": attempt_count,
            "boundary_parse_statuses": statuses,
            "boundary_error_codes": errors,
            "exact_inclusive_bounds": True,
        },
        "V31_OUTCOME_V2_CLOCK_POLICY_BINDING_MISMATCH",
    )


def _case_capture_crash_local_recovery(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    run_id, contract, monitor, evidence, _plan = _raw_context(
        root, case_tag="capture-crash", clock_policy=clock_policy
    )
    raw = _valid_raw()
    transport = _InjectedTransport(body=raw)
    adapter = _adapter(transport)
    from . import v31_outcome_resolution_v2 as workflow

    parse_boundary: dict[str, Any] = {}

    def crash_after_readback(**kwargs: Any) -> Mapping[str, Any]:
        raw_path = root / "monitor-v2/cycles/0001/capture/raw.bin"
        record_path = root / "monitor-v2/cycles/0001/capture/capture-record.json"
        parse_boundary.update(
            {
                "raw_exists_before_parse": raw_path.is_file(),
                "record_exists_before_parse": record_path.is_file(),
                "raw_matches_before_parse": raw_path.read_bytes() == raw,
                "parser_received_durable_raw": kwargs.get("raw_payload") == raw,
            }
        )
        raise SystemExit("injected-after-capture-before-parse")

    first_code = None
    with patch.object(workflow, "parse_public_outcome_capture", crash_after_readback):
        try:
            _resolve(
                monitor_store=monitor,
                evidence_store=evidence,
                contract=contract,
                adapter=adapter,
                clock_policy=clock_policy,
            )
        except SystemExit as exc:
            first_code = _exception_text(exc)
    result = _resolve(
        monitor_store=monitor,
        evidence_store=evidence,
        contract=contract,
        adapter=adapter,
        requested_at=_PROBE_RECOVERY_AT,
        clock_policy=clock_policy,
    )
    checkpoint = evidence.load_checkpoint(run_id=run_id)
    _require(
        first_code == "injected-after-capture-before-parse",
        "V31_PROBE_CAPTURE_CRASH_MISSING",
    )
    _require(all(parse_boundary.values()), "V31_PROBE_RAW_NOT_DURABLE_BEFORE_PARSE")
    _require(transport.calls == 1, "V31_PROBE_CAPTURE_RECOVERY_REFETCHED")
    _require(
        result["runtime_status"] == "RESOLVED_FROM_COMMITTED_CAPTURE",
        "V31_PROBE_CAPTURE_LOCAL_RECOVERY_FAILED",
    )
    _require(
        len(checkpoint["capture_bindings"]) == 1
        and len(checkpoint["parse_bindings"]) == 1
        and len(checkpoint["resolution_bindings"]) == 1,
        "V31_PROBE_CAPTURE_RECOVERY_EVIDENCE_INCOMPLETE",
    )
    return (
        {
            **parse_boundary,
            "first_exception": first_code,
            "recovery_runtime_status": result["runtime_status"],
            "transport_get_count": transport.calls,
            "recovery_get_count": 0,
            "capture_binding_count": len(checkpoint["capture_bindings"]),
            "parse_binding_count": len(checkpoint["parse_bindings"]),
            "resolution_binding_count": len(checkpoint["resolution_bindings"]),
        },
        "INJECTED_PROCESS_DEATH_AFTER_DURABLE_CAPTURE",
    )


def _case_invalid_json_and_failed_parse_immutable(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    invalid_root = root / "invalid-json"
    run_id, contract, monitor, evidence, _plan = _raw_context(
        invalid_root, case_tag="invalid-json", clock_policy=clock_policy
    )
    transport = _InjectedTransport(body=b"{")
    invalid_code = None
    try:
        _resolve(
            monitor_store=monitor,
            evidence_store=evidence,
            contract=contract,
            adapter=_adapter(transport),
            clock_policy=clock_policy,
        )
    except V31OutcomeResolutionV2Error as exc:
        invalid_code = _exception_text(exc)
    raw_path = invalid_root / "monitor-v2/cycles/0001/capture/raw.bin"
    parse_receipt = evidence.read_parse_receipt(run_id=run_id, cycle_index=1)
    invalid_checkpoint = evidence.load_checkpoint(run_id=run_id)
    _require(raw_path.read_bytes() == b"{", "V31_PROBE_INVALID_JSON_RAW_MISSING")
    _require(
        parse_receipt["parse_status"] == "REJECTED"
        and parse_receipt["error_code"] == "PUBLIC_JSON_INVALID",
        "V31_PROBE_INVALID_JSON_PARSE_STATUS_INVALID",
    )
    _require(
        invalid_checkpoint["status"] == "FAILED_CLOSED",
        "V31_PROBE_INVALID_JSON_NOT_FAILED_CLOSED",
    )

    immutable_root = root / "failed-parse-immutable"
    immutable_run, immutable_contract, immutable_monitor, immutable_evidence, plan = (
        _raw_context(
            immutable_root,
            case_tag="failed-parse-immutable",
            clock_policy=clock_policy,
        )
    )
    from . import v31_outcome_resolution_v2 as workflow

    with patch.object(
        workflow,
        "parse_public_outcome_capture",
        side_effect=SystemExit("injected-before-parse-commit"),
    ):
        try:
            _resolve(
                monitor_store=immutable_monitor,
                evidence_store=immutable_evidence,
                contract=immutable_contract,
                adapter=_adapter(_InjectedTransport(body=_valid_raw())),
                clock_policy=clock_policy,
            )
        except SystemExit:
            pass
    immutable_evidence.fail_checkpoint(
        run_id=immutable_run,
        cycle_index=1,
        failure_code="PROBE_PERMANENT_FAILURE",
        failed_at=_PROBE_RECOVERY_AT,
    )
    capture, raw, _binding = immutable_evidence.load_committed_capture(
        run_id=immutable_run, cycle_index=1
    )
    candidate = parse_public_outcome_capture(
        capture=capture,
        raw_payload=raw,
        clock_policy=clock_policy,
        observable_ref=str(plan["observable"]["observable_ref"]),
    )
    immutable_code = None
    try:
        immutable_evidence.commit_parse_receipt(
            run_id=immutable_run,
            cycle_index=1,
            receipt=candidate,
            clock_policy=clock_policy,
            observable_ref=str(plan["observable"]["observable_ref"]),
            committed_at=_PROBE_RECOVERY_AT,
        )
    except V31OutcomeEvidenceStoreV2Error as exc:
        immutable_code = _exception_text(exc)
    immutable_parse_path = (
        immutable_root / "monitor-v2/cycles/0001/parse-receipt.json"
    )
    _require(
        immutable_code == "V31_EVIDENCE_PARSE_SEQUENCE_INVALID",
        "V31_PROBE_FAILED_PARSE_APPEND_NOT_REJECTED",
    )
    _require(
        not immutable_parse_path.exists(),
        "V31_PROBE_FAILED_PARSE_MUTATED_DURABLE_STATE",
    )
    return (
        {
            "invalid_json_exception": invalid_code,
            "raw_persisted_before_rejection": raw_path.read_bytes() == b"{",
            "parse_status": parse_receipt["parse_status"],
            "parse_error_code": parse_receipt["error_code"],
            "evidence_status": invalid_checkpoint["status"],
            "failed_checkpoint_parse_append_exception": immutable_code,
            "parse_receipt_absent_after_failed_append": not immutable_parse_path.exists(),
            "transport_get_count": transport.calls,
        },
        "PUBLIC_JSON_INVALID_AND_V31_EVIDENCE_PARSE_SEQUENCE_INVALID",
    )


def _case_raw_tamper(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    run_id, contract, monitor, evidence, _plan = _raw_context(
        root, case_tag="raw-tamper", clock_policy=clock_policy
    )
    transport = _InjectedTransport(body=_valid_raw())
    result = _resolve(
        monitor_store=monitor,
        evidence_store=evidence,
        contract=contract,
        adapter=_adapter(transport),
        clock_policy=clock_policy,
    )
    raw_path = root / "monitor-v2/cycles/0001/capture/raw.bin"
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    tamper_code = None
    try:
        LocalV31OutcomeEvidenceStoreV2(root).load_checkpoint(run_id=run_id)
    except V31OutcomeEvidenceStoreV2Error as exc:
        tamper_code = _exception_text(exc)
    _require(
        result["runtime_status"] == "RESOLVED",
        "V31_PROBE_RAW_TAMPER_PRECONDITION_FAILED",
    )
    _require(
        tamper_code == "V31_EVIDENCE_CAPTURE_BINDING_INVALID",
        "V31_PROBE_RAW_TAMPER_NOT_BLOCKED",
    )
    return (
        {
            "pre_tamper_runtime_status": result["runtime_status"],
            "tamper_operation": "APPEND_ONE_SPACE_TO_TEMP_RAW_CAPTURE",
            "replay_exception": tamper_code,
            "transport_get_count": transport.calls,
            "replay_admitted": False,
        },
        "V31_EVIDENCE_CAPTURE_BINDING_INVALID",
    )


def _case_transport_failure_and_concurrent_one_get(
    root: Path, clock_policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    failure_root = root / "transport-failure"
    run_id, contract, monitor, evidence, _plan = _raw_context(
        failure_root, case_tag="transport-failure", clock_policy=clock_policy
    )
    timeout_transport = _InjectedTransport(error=TimeoutError("injected-timeout"))
    adapter = _adapter(timeout_transport)
    real_replace = evidence._replace_checkpoint

    def crash_after_receipt(**kwargs: Any) -> Mapping[str, Any]:
        if kwargs["candidate"].get("transport_failure_binding") is not None:
            raise SystemExit("injected-after-transport-receipt")
        return real_replace(**kwargs)

    first_code = None
    with patch.object(evidence, "_replace_checkpoint", side_effect=crash_after_receipt):
        try:
            _resolve(
                monitor_store=monitor,
                evidence_store=evidence,
                contract=contract,
                adapter=adapter,
                clock_policy=clock_policy,
            )
        except SystemExit as exc:
            first_code = _exception_text(exc)
    transport_receipt_path = (
        failure_root / "monitor-v2/cycles/0001/transport-failure.json"
    )
    recovery_code = None
    try:
        _resolve(
            monitor_store=monitor,
            evidence_store=evidence,
            contract=contract,
            adapter=adapter,
            requested_at=_PROBE_RECOVERY_AT,
            clock_policy=clock_policy,
        )
    except V31OutcomeResolutionV2Error as exc:
        recovery_code = _exception_text(exc)
    failure_checkpoint = evidence.load_checkpoint(run_id=run_id)
    _require(
        first_code == "injected-after-transport-receipt"
        and transport_receipt_path.is_file(),
        "V31_PROBE_TRANSPORT_RECEIPT_NOT_DURABLE_BEFORE_CRASH",
    )
    _require(
        recovery_code == "V31_OUTCOME_V2_NO_RESPONSE_RECOVERED:PUBLIC_TIMEOUT",
        "V31_PROBE_TRANSPORT_LOCAL_RECOVERY_INVALID",
    )
    _require(timeout_transport.calls == 1, "V31_PROBE_TRANSPORT_FAILURE_REFETCHED")
    _require(
        failure_checkpoint["status"] == "FAILED_CLOSED"
        and failure_checkpoint["transport_failure_binding"]["failure_code"]
        == "PUBLIC_TIMEOUT",
        "V31_PROBE_TRANSPORT_FAILURE_NOT_BOUND",
    )

    concurrent_root = root / "concurrent-one-get"
    concurrent_run, concurrent_contract, concurrent_monitor, concurrent_evidence, _ = (
        _raw_context(
            concurrent_root,
            case_tag="concurrent-one-get",
            clock_policy=clock_policy,
        )
    )
    blocking = _BlockingInjectedTransport(body=_valid_raw())
    concurrent_adapter = _adapter(blocking)
    results: list[Mapping[str, Any]] = []
    errors: list[str] = []

    def run_once() -> None:
        try:
            results.append(
                _resolve(
                    monitor_store=concurrent_monitor,
                    evidence_store=concurrent_evidence,
                    contract=concurrent_contract,
                    adapter=concurrent_adapter,
                    clock_policy=clock_policy,
                )
            )
        except BaseException as exc:
            errors.append(f"{type(exc).__name__}:{_exception_text(exc)}")

    first = threading.Thread(target=run_once, name="v31-probe-first")
    second = threading.Thread(target=run_once, name="v31-probe-second")
    first.start()
    _require(blocking.started.wait(timeout=5), "V31_PROBE_CONCURRENT_GET_NOT_STARTED")
    second.start()
    blocking.release.set()
    first.join(timeout=10)
    second.join(timeout=10)
    _require(not first.is_alive() and not second.is_alive(), "V31_PROBE_THREAD_STUCK")
    statuses = sorted(str(row["runtime_status"]) for row in results)
    concurrent_checkpoint = concurrent_evidence.load_checkpoint(run_id=concurrent_run)
    _require(errors == [], "V31_PROBE_CONCURRENT_RESOLUTION_ERROR")
    _require(blocking.calls == 1, "V31_PROBE_CONCURRENT_MULTIPLE_GETS")
    _require(
        len(results) == 2
        and "RESOLVED" in statuses
        and concurrent_checkpoint["status"] == "ACTIVE",
        "V31_PROBE_CONCURRENT_RESULT_INVALID",
    )
    return (
        {
            "transport_receipt_durable_before_crash": transport_receipt_path.is_file(),
            "first_exception": first_code,
            "recovery_exception": recovery_code,
            "failure_transport_get_count": timeout_transport.calls,
            "failure_recovery_get_count": 0,
            "typed_failure_code": failure_checkpoint["transport_failure_binding"][
                "failure_code"
            ],
            "concurrent_worker_count": 2,
            "concurrent_transport_get_count": blocking.calls,
            "concurrent_runtime_statuses": statuses,
            "concurrent_errors": errors,
            "concurrent_evidence_status": concurrent_checkpoint["status"],
        },
        "V31_OUTCOME_V2_NO_RESPONSE_RECOVERED:PUBLIC_TIMEOUT",
    )


class _ProbeResearchOwner:
    def __init__(self, *, run_id: str, authority_digest: str) -> None:
        self.run_id = run_id
        self.authority_digest = authority_digest
        self.documents: dict[str, dict[str, Any]] = {}
        self.nonce = 0
        self.checkpoint = self_digest(
            {
                "schema_id": "v31_successor_probe_research_owner",
                "schema_version": "2.0.0",
                "run_id": run_id,
                "status": "READY_FOR_CYCLE",
                "total_cycles": 8,
                "completed_cycles": 0,
                "next_cycle_index": 1,
                "active_cycle_index": None,
                "accepted_state_ref": None,
                "accepted_state_digest": None,
                "current_authority_digest": authority_digest,
                "failure_digest": None,
                "resume_allowed": True,
                "nonce": self.nonce,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "checkpoint_digest",
        )

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        _require(run_id == self.run_id, "V31_PROBE_RESEARCH_RUN_MISMATCH")
        verify_self_digest(self.checkpoint, "checkpoint_digest")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        document = copy.deepcopy(self.documents[relative_ref])
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise V31SuccessorProbeRunnerV2Error(
                "V31_PROBE_RESEARCH_SEMANTIC_DRIFT"
            )
        return document

    def commit_cycle(self, cycle_index: int) -> str:
        accepted_ref = f"cycles/{cycle_index:04d}/accepted-research-state.json"
        accepted = self_digest(
            {
                "schema_id": "v31_successor_probe_accepted_state",
                "schema_version": "2.0.0",
                "run_id": self.run_id,
                "cycle_index": cycle_index,
            },
            "accepted_state_digest",
        )
        self.documents[accepted_ref] = accepted
        self.nonce += 1
        current = {
            key: value
            for key, value in self.checkpoint.items()
            if key != "checkpoint_digest"
        }
        current.update(
            {
                "status": "TERMINAL" if cycle_index == 8 else "READY_FOR_CYCLE",
                "completed_cycles": cycle_index,
                "next_cycle_index": cycle_index + 1,
                "active_cycle_index": None,
                "accepted_state_ref": accepted_ref,
                "accepted_state_digest": accepted["accepted_state_digest"],
                "nonce": self.nonce,
            }
        )
        self.checkpoint = self_digest(current, "checkpoint_digest")
        return str(accepted["accepted_state_digest"])


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


class _ProbeMonitorOwner:
    def __init__(self, *, run_id: str, contract_digest: str) -> None:
        self.run_id = run_id
        self.documents: dict[str, dict[str, Any]] = {}
        self.nonce = 0
        self.checkpoint = self_digest(
            {
                "schema_id": "v31_successor_probe_monitor_owner",
                "schema_version": "2.0.0",
                "run_id": run_id,
                "experiment_contract_digest": contract_digest,
                "status": "ACTIVE",
                "total_cycles": 8,
                "plan_bindings": [],
                "resolution_attempt_bindings": [],
                "outcome_bindings": [],
                "last_outcome_receipt_digest": None,
                "failure_digest": None,
                "resume_allowed": True,
                "nonce": self.nonce,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "checkpoint_digest",
        )

    def _replace(self, **updates: Any) -> None:
        self.nonce += 1
        current = {
            key: value
            for key, value in self.checkpoint.items()
            if key != "checkpoint_digest"
        }
        current.update(updates)
        current["nonce"] = self.nonce
        self.checkpoint = self_digest(current, "checkpoint_digest")

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        _require(run_id == self.run_id, "V31_PROBE_MONITOR_RUN_MISMATCH")
        verify_self_digest(self.checkpoint, "checkpoint_digest")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        document = copy.deepcopy(self.documents[relative_ref])
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise V31SuccessorProbeRunnerV2Error(
                "V31_PROBE_MONITOR_SEMANTIC_DRIFT"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": digest_field,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": _physical(document),
        }

    def schedule(self, cycle_index: int, accepted_state_digest: str) -> None:
        plans = copy.deepcopy(self.checkpoint["plan_bindings"])
        plans.append(
            {
                "cycle_index": cycle_index,
                "relative_ref": f"monitor/cycles/{cycle_index:04d}/monitor-plan.json",
                "semantic_digest": hashlib.sha256(
                    f"plan:{cycle_index}".encode("utf-8")
                ).hexdigest(),
                "physical_sha256": hashlib.sha256(
                    f"plan-bytes:{cycle_index}".encode("utf-8")
                ).hexdigest(),
                "accepted_state_digest": accepted_state_digest,
            }
        )
        self._replace(plan_bindings=plans)

    def reserve_attempt(self, cycle_index: int) -> None:
        attempts = copy.deepcopy(self.checkpoint["resolution_attempt_bindings"])
        if len(attempts) >= cycle_index:
            return
        attempts.append(
            {
                "cycle_index": cycle_index,
                "relative_ref": f"monitor/cycles/{cycle_index:04d}/attempt.json",
                "semantic_digest": hashlib.sha256(
                    f"attempt:{cycle_index}".encode("utf-8")
                ).hexdigest(),
                "physical_sha256": hashlib.sha256(
                    f"attempt-bytes:{cycle_index}".encode("utf-8")
                ).hexdigest(),
            }
        )
        self._replace(resolution_attempt_bindings=attempts)

    def resolve(self, cycle_index: int, *, unknown: bool = False) -> str:
        self.reserve_attempt(cycle_index)
        outcomes = copy.deepcopy(self.checkpoint["outcome_bindings"])
        previous = self.checkpoint["last_outcome_receipt_digest"]
        receipt = self_digest(
            {
                "schema_id": "v31_successor_probe_legal_outcome_receipt",
                "schema_version": "2.0.0",
                "run_id": self.run_id,
                "cycle_index": cycle_index,
                "previous_outcome_receipt_digest": previous,
                "expectation_outcome": "UNKNOWN" if unknown else "FULFILLED",
                "path_outcome": "UNRESOLVED" if unknown else "SUPPORTED",
                "coverage_loss": unknown,
                "unknown_counted_as_coverage_loss": unknown,
            },
            "outcome_receipt_digest",
        )
        ref = f"monitor/cycles/{cycle_index:04d}/outcome-receipt.json"
        self.documents[ref] = receipt
        outcomes.append(
            {
                "cycle_index": cycle_index,
                "outcome_receipt_ref": ref,
                "outcome_receipt_digest": receipt["outcome_receipt_digest"],
                "outcome_receipt_physical_sha256": _physical(receipt),
            }
        )
        self._replace(
            status="TERMINAL" if cycle_index == 8 else "ACTIVE",
            outcome_bindings=outcomes,
            last_outcome_receipt_digest=receipt["outcome_receipt_digest"],
        )
        return str(receipt["outcome_receipt_digest"])

    def fail_closed(self) -> None:
        self._replace(
            status="FAILED_CLOSED", failure_digest="f" * 64, resume_allowed=False
        )

    def touch(self) -> None:
        self._replace()


class _SupervisorScenario:
    def __init__(self, root: Path, *, tag: str) -> None:
        self.root = root
        self.run_id = f"v31-local-successor-supervisor-probe-{tag}"
        self.contract_digest = hashlib.sha256(
            f"contract:{tag}".encode("utf-8")
        ).hexdigest()
        self.authority_digest = hashlib.sha256(
            f"authority:{tag}".encode("utf-8")
        ).hexdigest()
        self.research = _ProbeResearchOwner(
            run_id=self.run_id, authority_digest=self.authority_digest
        )
        self.monitor = _ProbeMonitorOwner(
            run_id=self.run_id, contract_digest=self.contract_digest
        )
        self.supervisor = LocalV31SupervisorStoreV2(root)
        self.now = datetime(2026, 8, 7, 3, 0, tzinfo=UTC)

    def tick(self) -> str:
        self.now += timedelta(seconds=1)
        return self.now.isoformat().replace("+00:00", "Z")

    def bootstrap(self) -> Mapping[str, Any]:
        return initialize_v31_experiment_supervisor_v2(
            supervisor_store=self.supervisor,
            research_store=self.research,
            monitor_store=self.monitor,
            run_id=self.run_id,
            experiment_contract_digest=self.contract_digest,
            active_authority_digest=self.authority_digest,
            created_at=self.tick(),
        )

    def open(self) -> Mapping[str, Any]:
        return open_v31_cycle_permit_v2(
            supervisor_store=self.supervisor,
            research_store=self.research,
            monitor_store=self.monitor,
            run_id=self.run_id,
            issued_at=self.tick(),
        )

    def reserve(self, permit: Mapping[str, Any], cycle_index: int) -> Mapping[str, Any]:
        return reserve_v31_cycle_commit_v2(
            supervisor_store=self.supervisor,
            research_store=self.research,
            monitor_store=self.monitor,
            run_id=self.run_id,
            permit_binding=permit["cycle_permit_binding"],
            commit_material_digest=hashlib.sha256(
                f"commit:{cycle_index}".encode("utf-8")
            ).hexdigest(),
            reserved_at=self.tick(),
        )

    def commit_owners(self, cycle_index: int) -> str:
        accepted_digest = self.research.commit_cycle(cycle_index)
        self.monitor.schedule(cycle_index, accepted_digest)
        return accepted_digest

    def record(self) -> Mapping[str, Any]:
        return record_v31_cycle_commit_v2(
            supervisor_store=self.supervisor,
            research_store=self.research,
            monitor_store=self.monitor,
            run_id=self.run_id,
            committed_at=self.tick(),
        )

    def reserve_and_commit(
        self, permit: Mapping[str, Any], cycle_index: int
    ) -> Mapping[str, Any]:
        self.reserve(permit, cycle_index)
        self.commit_owners(cycle_index)
        return self.record()


def _case_commit_intent_recovery(
    root: Path,
) -> tuple[dict[str, Any], str]:
    scenario = _SupervisorScenario(root, tag="commit-intent")
    scenario.bootstrap()
    permit = scenario.open()
    reserved = scenario.reserve(permit, 1)
    before_owner_commit = scenario.supervisor.load_checkpoint(run_id=scenario.run_id)
    intent_binding = reserved["commit_intent_binding"]
    intent = scenario.supervisor.read_document(
        relative_ref=intent_binding["relative_ref"],
        digest_field="commit_intent_digest",
        expected_semantic_digest=intent_binding["semantic_digest"],
    )
    research_before = scenario.research.load_checkpoint(run_id=scenario.run_id)
    scenario.supervisor = LocalV31SupervisorStoreV2(root)
    scenario.commit_owners(1)
    committed = scenario.record()
    _require(
        before_owner_commit["status"] == "COMMIT_RESERVED"
        and research_before["completed_cycles"] == 0,
        "V31_PROBE_COMMIT_INTENT_NOT_FIRST",
    )
    _require(
        intent["agent_reinvocation_allowed"] is False
        and intent["recovery_policy"] == "LOCAL_IDEMPOTENT_WRITES_ONLY",
        "V31_PROBE_COMMIT_INTENT_RECOVERY_POLICY_INVALID",
    )
    _require(
        committed["status"] == "AWAITING_OUTCOME"
        and committed["supervisor_checkpoint"]["completed_research_cycles"] == 1,
        "V31_PROBE_COMMIT_RECOVERY_FAILED",
    )
    return (
        {
            "status_before_owner_commit": before_owner_commit["status"],
            "research_completed_before_intent": research_before["completed_cycles"],
            "commit_intent_digest": intent["commit_intent_digest"],
            "agent_reinvocation_allowed": intent["agent_reinvocation_allowed"],
            "recovery_policy": intent["recovery_policy"],
            "fresh_store_recovery_used": True,
            "status_after_recovery": committed["status"],
            "completed_research_cycles": committed["supervisor_checkpoint"][
                "completed_research_cycles"
            ],
        },
        "COMMIT_INTENT_DURABLE_BEFORE_ACCEPTED_STATE",
    )


def _case_failed_monitor_blocks(
    root: Path,
) -> tuple[dict[str, Any], str]:
    scenario = _SupervisorScenario(root, tag="failed-monitor")
    scenario.bootstrap()
    permit = scenario.open()
    scenario.reserve_and_commit(permit, 1)
    scenario.monitor.fail_closed()
    error_code = None
    try:
        scenario.open()
    except V31ExperimentSupervisorV2WorkflowError as exc:
        error_code = _exception_text(exc)
    checkpoint = scenario.supervisor.load_checkpoint(run_id=scenario.run_id)
    _require(
        error_code == "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED",
        "V31_PROBE_FAILED_MONITOR_NOT_BLOCKED",
    )
    _require(
        checkpoint["status"] == "FAILED_CLOSED"
        and checkpoint["resume_allowed"] is False,
        "V31_PROBE_FAILED_MONITOR_NOT_TERMINAL",
    )
    return (
        {
            "open_next_cycle_exception": error_code,
            "supervisor_status": checkpoint["status"],
            "resume_allowed": checkpoint["resume_allowed"],
            "completed_research_cycles": checkpoint["completed_research_cycles"],
            "resolved_outcome_cycles": checkpoint["resolved_outcome_cycles"],
        },
        "V31_SUPERVISOR_V2_MONITOR_FAILED_CLOSED",
    )


def _case_one_boundary_stale_permit(
    root: Path,
) -> tuple[dict[str, Any], str]:
    scenario = _SupervisorScenario(root, tag="stale-permit")
    boot = scenario.bootstrap()
    opened = scenario.open()
    verified = verify_v31_cycle_permit_live_v2(
        supervisor_store=scenario.supervisor,
        research_store=scenario.research,
        monitor_store=scenario.monitor,
        run_id=scenario.run_id,
        permit_binding=opened["cycle_permit_binding"],
        operation="SOURCE_QUALIFICATION",
    )
    before_stale = scenario.supervisor.load_checkpoint(run_id=scenario.run_id)
    scenario.monitor.touch()
    stale_code = None
    try:
        verify_v31_cycle_permit_live_v2(
            supervisor_store=scenario.supervisor,
            research_store=scenario.research,
            monitor_store=scenario.monitor,
            run_id=scenario.run_id,
            permit_binding=opened["cycle_permit_binding"],
            operation="AGENT_ATTEMPT_RESERVATION",
        )
    except V31ExperimentSupervisorV2WorkflowError as exc:
        stale_code = _exception_text(exc)
    after_stale = scenario.supervisor.load_checkpoint(run_id=scenario.run_id)
    _require(verified["status"] == "PERMIT_LIVE", "V31_PROBE_PERMIT_NOT_LIVE")
    _require(
        stale_code == "V31_SUPERVISOR_V2_PERMIT_STALE",
        "V31_PROBE_STALE_PERMIT_NOT_REJECTED",
    )
    _require(
        before_stale["supervisor_checkpoint_digest"]
        == after_stale["supervisor_checkpoint_digest"]
        and after_stale["status"] == "CYCLE_PERMIT_OPEN"
        and after_stale["revision"] == int(boot["revision"]) + 1,
        "V31_PROBE_STALE_PERMIT_CHANGED_SECOND_BOUNDARY",
    )
    return (
        {
            "initial_permit_status": verified["status"],
            "stale_permit_exception": stale_code,
            "supervisor_status_after_rejection": after_stale["status"],
            "supervisor_revision_after_rejection": after_stale["revision"],
            "supervisor_checkpoint_unchanged_by_stale_rejection": (
                before_stale["supervisor_checkpoint_digest"]
                == after_stale["supervisor_checkpoint_digest"]
            ),
            "commit_intent_created": after_stale["active_commit_intent_digest"]
            is not None,
        },
        "V31_SUPERVISOR_V2_PERMIT_STALE",
    )


def _case_previous_outcome_required(
    root: Path,
) -> tuple[dict[str, Any], str]:
    scenario = _SupervisorScenario(root, tag="previous-outcome")
    scenario.bootstrap()
    permit = scenario.open()
    scenario.reserve_and_commit(permit, 1)
    missing_code = None
    try:
        scenario.open()
    except V31ExperimentSupervisorV2WorkflowError as exc:
        missing_code = _exception_text(exc)
    scenario.monitor.reserve_attempt(1)
    reserved_code = None
    try:
        scenario.open()
    except V31ExperimentSupervisorV2WorkflowError as exc:
        reserved_code = _exception_text(exc)
    unknown_digest = scenario.monitor.resolve(1, unknown=True)
    permit_two = scenario.open()
    _require(
        missing_code == "V31_SUPERVISOR_V2_PRIOR_OUTCOME_MISSING",
        "V31_PROBE_MISSING_OUTCOME_NOT_BLOCKED",
    )
    _require(
        reserved_code == "V31_SUPERVISOR_V2_RESERVED_ATTEMPT_WITHOUT_OUTCOME",
        "V31_PROBE_RESERVED_ATTEMPT_NOT_BLOCKED",
    )
    _require(
        permit_two["cycle_index"] == 2
        and permit_two["cycle_permit"]["previous_outcome_receipt_digest"]
        == unknown_digest,
        "V31_PROBE_DURABLE_UNKNOWN_DID_NOT_OPEN_NEXT_CYCLE",
    )
    return (
        {
            "missing_outcome_exception": missing_code,
            "reserved_attempt_exception": reserved_code,
            "durable_unknown_outcome_digest": unknown_digest,
            "unknown_counted_as_coverage_loss": True,
            "next_cycle_index_after_durable_unknown": permit_two["cycle_index"],
            "next_permit_previous_outcome_digest": permit_two["cycle_permit"][
                "previous_outcome_receipt_digest"
            ],
        },
        "V31_SUPERVISOR_V2_PRIOR_OUTCOME_MISSING",
    )


def _tested_bindings(
    runtime_closure_bindings: Mapping[str, str], paths: Sequence[str]
) -> dict[str, str]:
    missing = [path for path in paths if path not in runtime_closure_bindings]
    if missing:
        raise V31SuccessorProbeRunnerV2Error(
            "V31_PROBE_TESTED_MODULE_UNBOUND:" + ",".join(missing)
        )
    return {path: str(runtime_closure_bindings[path]) for path in sorted(paths)}


def run_successor_qualification_probes_v2(
    *,
    project_root: Path,
    executed_at: str,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
    runtime_closure_bindings: Mapping[str, str],
    clock_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ten local probes and return receipt-ready, verified documents.

    No argument carries PASS, an observed result, a run id, a network choice,
    or an automation target.  A mismatch raises before aggregate evidence is
    produced.
    """

    policy = dict(clock_policy or build_outcome_clock_policy())
    clock_policy_digest = verify_outcome_clock_policy(policy)
    verified_closure = verify_v31_runtime_closure_bindings_v2(
        project_root=project_root,
        production_root_paths=production_root_paths,
        trace_paths=trace_paths,
        frozen_bindings=runtime_closure_bindings,
    )
    runtime_closure_digest = canonical_digest(verified_closure)
    raw_modules = _tested_bindings(verified_closure, RAW_TESTED_MODULE_PATHS)
    supervisor_modules = _tested_bindings(
        verified_closure, SUPERVISOR_TESTED_MODULE_PATHS
    )
    runtime_evidence = build_probe_runtime_closure_evidence_v2(
        executed_at=executed_at,
        production_root_paths=production_root_paths,
        trace_paths=trace_paths,
        runtime_closure_bindings=verified_closure,
    )

    raw_cases = {
        "ATTEMPT_ONLY_CRASH_FAILS_CLOSED_WITHOUT_REFETCH": (
            _case_attempt_only_crash,
            {"vector": "crash-before-response", "expected_get_count": 1},
        ),
        "CLOCK_POLICY_DRIFT_REJECTED_BEFORE_PARSE": (
            _case_clock_policy,
            {
                "vector": "clock-policy-drift-and-inclusive-boundaries",
                "lead_bound_ms": 2_000,
                "age_bound_ms": 5_000,
            },
        ),
        "CRASH_AFTER_CAPTURE_RECOVERS_LOCALLY_WITHOUT_REFETCH": (
            _case_capture_crash_local_recovery,
            {"vector": "crash-after-capture-before-parse", "expected_get_count": 1},
        ),
        "INVALID_JSON_RAW_PRESERVED_BEFORE_PARSE_FAILURE": (
            _case_invalid_json_and_failed_parse_immutable,
            {"vector": "invalid-json-plus-failed-parse-immutability"},
        ),
        "RAW_TAMPER_BLOCKS_REPLAY": (
            _case_raw_tamper,
            {"vector": "post-resolution-raw-byte-tamper"},
        ),
        "TRANSPORT_FAILURE_CRASH_BINDS_FAILURE_WITHOUT_REFETCH": (
            _case_transport_failure_and_concurrent_one_get,
            {
                "vector": "orphan-timeout-receipt-plus-two-concurrent-wakeups",
                "concurrent_workers": 2,
            },
        ),
    }
    _require(
        tuple(sorted(raw_cases)) == RAW_FIRST_FAILURE_CASES,
        "V31_PROBE_RAW_CASE_SET_DRIFT",
    )
    raw_receipts: list[dict[str, Any]] = []
    for case_id in RAW_FIRST_FAILURE_CASES:
        runner, input_vector = raw_cases[case_id]
        with tempfile.TemporaryDirectory(prefix="v31-successor-raw-probe-") as directory:
            observation, exception_code = runner(Path(directory), policy)
        raw_receipts.append(
            build_executed_probe_case_receipt_v2(
                probe_family=RAW_FIRST_FAMILY,
                case_id=case_id,
                executed_at=executed_at,
                runtime_closure_digest=runtime_closure_digest,
                tested_module_bindings=raw_modules,
                clock_policy_digest=clock_policy_digest,
                test_input_digest=canonical_digest(input_vector),
                observation=observation,
                exception_code=exception_code,
                network_boundary=RAW_NETWORK_BOUNDARY,
            )
        )

    supervisor_cases = {
        "COMMIT_INTENT_PRECEDES_ACCEPTED_STATE": (
            _case_commit_intent_recovery,
            {"vector": "commit-intent-crash-recovery-with-fresh-store"},
        ),
        "FAILED_MONITOR_BLOCKS_NEW_CYCLE": (
            _case_failed_monitor_blocks,
            {"vector": "failed-monitor-before-next-permit"},
        ),
        "ONE_STATE_CHANGE_BOUNDARY_PER_WAKE": (
            _case_one_boundary_stale_permit,
            {"vector": "owner-digest-drift-after-permit"},
        ),
        "PREVIOUS_DURABLE_OUTCOME_REQUIRED_FOR_NEXT_CYCLE": (
            _case_previous_outcome_required,
            {"vector": "missing-reserved-then-durable-unknown-outcome"},
        ),
    }
    _require(
        tuple(sorted(supervisor_cases)) == SUPERVISOR_GATE_CASES,
        "V31_PROBE_SUPERVISOR_CASE_SET_DRIFT",
    )
    supervisor_receipts: list[dict[str, Any]] = []
    for case_id in SUPERVISOR_GATE_CASES:
        runner, input_vector = supervisor_cases[case_id]
        with tempfile.TemporaryDirectory(
            prefix="v31-successor-supervisor-probe-"
        ) as directory:
            observation, exception_code = runner(Path(directory))
        supervisor_receipts.append(
            build_executed_probe_case_receipt_v2(
                probe_family=SUPERVISOR_FAMILY,
                case_id=case_id,
                executed_at=executed_at,
                runtime_closure_digest=runtime_closure_digest,
                tested_module_bindings=supervisor_modules,
                clock_policy_digest=clock_policy_digest,
                test_input_digest=canonical_digest(input_vector),
                observation=observation,
                exception_code=exception_code,
                network_boundary=SUPERVISOR_NETWORK_BOUNDARY,
            )
        )

    raw_probe = build_raw_first_failure_probe_v2(
        tested_at=executed_at,
        clock_policy_digest=clock_policy_digest,
        case_results={receipt["case_id"]: "PASS" for receipt in raw_receipts},
    )
    supervisor_probe = build_supervisor_gate_probe_v2(
        tested_at=executed_at,
        case_results={receipt["case_id"]: "PASS" for receipt in supervisor_receipts},
    )
    raw_family_evidence = build_executed_probe_family_evidence_v2(
        probe_family=RAW_FIRST_FAMILY,
        executed_at=executed_at,
        runtime_closure_digest=runtime_closure_digest,
        clock_policy_digest=clock_policy_digest,
        case_receipts=raw_receipts,
        aggregate_probe=raw_probe,
    )
    supervisor_family_evidence = build_executed_probe_family_evidence_v2(
        probe_family=SUPERVISOR_FAMILY,
        executed_at=executed_at,
        runtime_closure_digest=runtime_closure_digest,
        clock_policy_digest=clock_policy_digest,
        case_receipts=supervisor_receipts,
        aggregate_probe=supervisor_probe,
    )
    return {
        "executed_at": executed_at,
        "clock_policy": policy,
        "runtime_closure_evidence": runtime_evidence,
        "raw_first_case_receipts": raw_receipts,
        "supervisor_case_receipts": supervisor_receipts,
        "raw_first_probe": raw_probe,
        "supervisor_probe": supervisor_probe,
        "raw_first_family_evidence": raw_family_evidence,
        "supervisor_family_evidence": supervisor_family_evidence,
        "network_access_performed": False,
        "real_run_created": False,
        "automation_created": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


__all__ = [
    "RAW_TESTED_MODULE_PATHS",
    "RUNNER_MODULE_PATH",
    "SUPERVISOR_TESTED_MODULE_PATHS",
    "V31SuccessorProbeRunnerV2Error",
    "run_successor_qualification_probes_v2",
]
