from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v332_hype_data import _json, _seal_core
from tests.test_theory_paper_v2_v332_experiment_runtime import (
    _V332_PACKAGE,
    _policy as _experiment_policy,
)
from tests.test_theory_paper_v2_v332_offline_e2e import (
    _GOAL_PHYSICAL_ID,
    _TypedMissingOutcome,
    _FixedRuntimeClock,
    _deliver_and_complete_decision,
    _deliver_and_complete_review,
    _v332_request,
)
from trade_system.theory_paper_v2.application.market_cycle.ports import (
    OutcomeObservation,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    BehaviorPlan,
    InputSnapshot,
)
from trade_system.theory_paper_v2.domain.market_cycle.evaluation import (
    OperationalEvaluationContractError,
)
from trade_system.theory_paper_v2.domain.market_cycle.evidence import (
    EvidencePolicy,
    V332_EVIDENCE_POLICY_ID,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
    V332_THEORY_REVISION,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.operational_evaluation import (
    evaluate_completed_cycle_operationally,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.codex_mailbox import (
    MarketCycleAgentMailboxError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.okx_outcome import (
    OkxMarkOutcome,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.operational_evaluation_store import (
    FileOperationalEvaluationStore,
    OperationalEvaluationStoreError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    build_market_cycle_runtime,
    initialize_v332_run,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    MARK_PRICE_PATH,
    MAX_PUBLIC_RESPONSE_BYTES,
    PUBLIC_ROUTE_POLICY_ID,
    build_public_get_request,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli


def _time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _policy() -> EvidencePolicy:
    return EvidencePolicy(
        policy_id=V332_EVIDENCE_POLICY_ID,
        theory_revision=V332_THEORY_REVISION,
    )


def _build_operational_runtime(root: Path):  # noqa: ANN202
    policy = replace(
        _experiment_policy(root.name),
        capability_ids=("OPERATIONAL_EVALUATION",),
        local_paper_authorized=False,
        paper_account=None,
    )
    initialize_v332_run(
        root,
        theory_package=_V332_PACKAGE,
        experiment_policy=policy,
    )
    clock = _FixedRuntimeClock()
    runtime = build_market_cycle_runtime(
        runtime_root=root,
        theory_package=_V332_PACKAGE,
        expected_theory_identity=V332_THEORY_IDENTITY,
        clock=clock,
    )
    return runtime, FileRawCaptureStore(root), clock


def _seal_observed_outcome(
    raw_store: object, *, cycle_id: str, plan: BehaviorPlan, value: str = "44"
) -> None:
    due = datetime.fromisoformat(plan.outcome_due_at)
    capture_id = f"outcome-mark-{hashlib.sha256(plan.outcome_due_at.encode()).hexdigest()[:16]}"
    query = {"instId": "HYPE-USDT-SWAP", "instType": "SWAP"}
    _, final_url, ordered_query = build_public_get_request(
        path=MARK_PRICE_PATH, query=query
    )
    body = _json(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": "HYPE-USDT-SWAP",
                    "markPx": value,
                    "ts": str(int(due.timestamp() * 1000)),
                }
            ],
        }
    )
    raw_store.seal_response(
        cycle_id=cycle_id,
        capture_id=capture_id,
        payload=body,
        summary={
            "component_id": "OUTCOME_MARK_PRICE",
            "method": "GET",
            "path": MARK_PRICE_PATH,
            "query": ordered_query,
            "request_started_at": _time(due),
            "response_received_at": _time(due + timedelta(seconds=1)),
            "capture_completed_at": _time(due + timedelta(seconds=2)),
            "http_status": 200,
            "final_url": final_url,
            "route_policy_id": PUBLIC_ROUTE_POLICY_ID,
            "attempt_number": 1,
            "retry_allowed": False,
            "response_limit_bytes": MAX_PUBLIC_RESPONSE_BYTES,
            "body_truncated": False,
        },
    )


class _ForgedObservedOutcome:
    def __init__(self, raw_ref: object) -> None:
        self._raw_ref = raw_ref

    def observe(self, request: object) -> OutcomeObservation:
        due_at = getattr(request, "due_at")
        return OutcomeObservation(
            observed_at=due_at,
            effective_at=due_at,
            available_at=due_at,
            terminal_status="OBSERVED",
            value="44",
            unit="USDT_PER_HYPE",
            missing_reason=None,
            raw_ref=self._raw_ref,
            source_health=(),
        )


class V332OperationalEvaluationTests(unittest.TestCase):
    def _completed_fixture(
        self, root: Path, *, outcome_mode: str
    ) -> tuple[object, str]:
        runtime, raw_store, clock = _build_operational_runtime(root)
        cycle_id = f"v332-operational-{outcome_mode.lower()}"
        runtime.service.create(_v332_request(cycle_id))
        _seal_core(raw_store, cycle_id=cycle_id)
        runtime.service.run_next(cycle_id)
        runtime.service.run_next(cycle_id)
        _deliver_and_complete_decision(runtime, cycle_id)
        decision_delivery = loads_json_strict(
            (
                root
                / "cycles"
                / cycle_id
                / "transport"
                / "agent-delivery.json"
            ).read_bytes()
        )
        self.assertEqual(
            decision_delivery["physical_goal_id"], _GOAL_PHYSICAL_ID
        )
        self.assertEqual(decision_delivery["schema_version"], "1.1.0")
        with mock.patch.dict(
            "os.environ",
            {"CODEX_THREAD_ID": _GOAL_PHYSICAL_ID.removeprefix("codex-thread:")},
            clear=False,
        ):
            self.assertEqual(
                runtime.service.deliver_agent_decision(
                    cycle_id,
                    decision_delivery["decision_text"].encode("utf-8"),
                ),
                "EXISTING_IDENTICAL",
            )
        with mock.patch.dict(
            "os.environ",
            {
                "CODEX_THREAD_ID": (
                    "119ff5a3-529a-77d2-a3e4-595710406637"
                )
            },
            clear=False,
        ), self.assertRaisesRegex(
            MarketCycleAgentMailboxError,
            "MARKET_CYCLE_AGENT_DELIVERY_GOAL_CONFLICT",
        ):
            runtime.service.deliver_agent_decision(
                cycle_id,
                decision_delivery["decision_text"].encode("utf-8"),
            )
        runtime.service.run_next(cycle_id)
        runtime.service.run_next(cycle_id)
        plan = BehaviorPlan.from_dict(
            runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
        )
        if outcome_mode == "TYPED_MISSING":
            runtime.service._service._outcome = _TypedMissingOutcome()
            clock.current = plan.outcome_due_at
        elif outcome_mode == "OBSERVED":
            _seal_observed_outcome(
                raw_store, cycle_id=cycle_id, plan=plan
            )
            clock.current = _time(
                datetime.fromisoformat(plan.outcome_due_at)
                + timedelta(seconds=2)
            )
        elif outcome_mode == "FORGED_DECISION_RAW":
            snapshot = InputSnapshot.from_dict(
                runtime.repository.load_artifact(cycle_id, "InputSnapshot")
            )
            runtime.service._service._outcome = _ForgedObservedOutcome(
                snapshot.raw_refs[0].to_dict()
            )
            clock.current = plan.outcome_due_at
        else:
            raise AssertionError(outcome_mode)
        runtime.service.run_next(cycle_id)
        runtime.service.run_next(cycle_id)
        runtime.service.run_next(cycle_id)
        _deliver_and_complete_review(runtime, cycle_id)
        review_delivery = loads_json_strict(
            (
                root
                / "cycles"
                / cycle_id
                / "transport"
                / "agent-review-delivery.json"
            ).read_bytes()
        )
        self.assertEqual(
            review_delivery["physical_goal_id"], _GOAL_PHYSICAL_ID
        )
        self.assertEqual(review_delivery["schema_version"], "1.1.0")
        runtime.service.run_next(cycle_id)
        runtime.service.run_next(cycle_id)
        self.assertEqual(runtime.service.status(cycle_id).stage, "COMPLETE")
        return runtime, cycle_id

    @staticmethod
    def _evaluate(runtime: object, cycle_id: str):  # noqa: ANN205
        return evaluate_completed_cycle_operationally(
            runtime=runtime,
            cycle_id=cycle_id,
            evaluation_id=f"{cycle_id}.evaluation",
            evaluated_at="2026-08-13T12:16:00+00:00",
            evidence_policy=_policy(),
        )

    def test_typed_missing_rebuild_is_byte_identical_and_never_invents_direction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="TYPED_MISSING"
            )
            first = self._evaluate(runtime, cycle_id)
            second = self._evaluate(runtime, cycle_id)

        self.assertEqual(canonical_bytes(first.to_dict()), canonical_bytes(second.to_dict()))
        self.assertEqual(first.payload_sha256, second.payload_sha256)
        self.assertEqual(first.endpoint_measure["status"], "TYPED_MISSING")
        self.assertIsNone(first.endpoint_measure["endpoint_mark"])
        self.assertIsNone(first.endpoint_measure["change_sign"])
        self.assertEqual(
            first.paper_facts["status"],
            "NOT_INCLUDED_IN_E0_OPERATIONAL_EVALUATION",
        )
        self.assertTrue(first.dimension_statuses["path"].startswith("CENSORED"))

    def test_observed_endpoint_is_replayed_from_exact_raw_before_reporting_displacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="OBSERVED"
            )
            evaluated = self._evaluate(runtime, cycle_id)

        self.assertEqual(evaluated.endpoint_measure["decision_mark"], "43.125")
        self.assertEqual(evaluated.endpoint_measure["endpoint_mark"], "44")
        self.assertEqual(evaluated.endpoint_measure["absolute_change"], "0.875")
        self.assertEqual(evaluated.endpoint_measure["change_sign"], "UP")
        self.assertIn(
            "PREDICTION_NOT_SCORED", evaluated.dimension_statuses["direction"]
        )

    def test_operational_replay_always_binds_agent_delivery_as_path_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="OBSERVED"
            )
            plan = BehaviorPlan.from_dict(
                runtime.repository.load_artifact(cycle_id, "BehaviorPlan")
            )
            requests: list[object] = []
            original_observe = OkxMarkOutcome.observe

            def recording_observe(adapter: object, request: object):  # noqa: ANN202
                requests.append(request)
                return original_observe(adapter, request)  # type: ignore[arg-type]

            with mock.patch.object(
                OkxMarkOutcome, "observe", new=recording_observe
            ):
                self._evaluate(runtime, cycle_id)

        self.assertEqual(1, len(requests))
        self.assertEqual(plan.agent_delivered_at, requests[0].path_start_at)

    def test_decision_time_raw_cannot_support_a_forged_observed_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="FORGED_DECISION_RAW"
            )
            with self.assertRaisesRegex(
                OperationalEvaluationContractError,
                "cannot be replayed from exact sealed raw",
            ):
                self._evaluate(runtime, cycle_id)

    def test_runtime_run_binding_drift_fails_before_facts_are_built(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="TYPED_MISSING"
            )
            binding_path = (
                runtime.runtime_root
                / "cycles"
                / cycle_id
                / "transport"
                / "run-binding.json"
            )
            document = loads_json_strict(binding_path.read_bytes())
            document["experiment_identity"] = "self-consistent-but-foreign"
            binding_path.write_bytes(canonical_bytes(document) + b"\n")
            with self.assertRaisesRegex(
                OperationalEvaluationContractError,
                "runtime cycle provenance verification failed",
            ):
                self._evaluate(runtime, cycle_id)

    def test_create_once_package_is_idempotent_and_rejects_different_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="TYPED_MISSING"
            )
            store = FileOperationalEvaluationStore(runtime)
            with mock.patch.object(
                type(runtime.controller_state),
                "trusted_now",
                return_value="2026-08-13T12:16:00+00:00",
            ) as trusted_now:
                first = store.evaluate_and_seal(
                    cycle_id=cycle_id,
                    evaluation_id=f"{cycle_id}.evaluation",
                    evidence_policy=_policy(),
                )
                second = store.evaluate_and_seal(
                    cycle_id=cycle_id,
                    evaluation_id=f"{cycle_id}.evaluation",
                    evidence_policy=_policy(),
                )
            trusted_now.assert_called_once_with()
            self.assertEqual(canonical_bytes(first), canonical_bytes(second))
            self.assertEqual(
                first["evaluation_document"]["payload"]["evaluated_at"],
                "2026-08-13T12:16:00+00:00",
            )
            self.assertEqual(store.load(cycle_id), first)
            self.assertEqual(
                first["evaluation_document_sha256"],
                hashlib.sha256(
                    canonical_bytes(first["evaluation_document"])
                ).hexdigest(),
            )
            self.assertEqual(first["binding"]["cycle_id"], cycle_id)
            self.assertEqual(
                first["binding"]["implementation_sha256"],
                runtime.run_manifest.implementation_sha256,
            )
            self.assertTrue(store.package_path(cycle_id).is_file())
            with self.assertRaisesRegex(
                OperationalEvaluationStoreError, "ID_WRITE_ONCE_CONFLICT"
            ):
                store.evaluate_and_seal(
                    cycle_id=cycle_id,
                    evaluation_id=f"{cycle_id}.different-evaluation",
                    evidence_policy=_policy(),
                )

    def test_cli_evaluate_writes_and_returns_the_saved_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime, cycle_id = self._completed_fixture(
                Path(temporary) / "run", outcome_mode="TYPED_MISSING"
            )
            with mock.patch.object(
                type(runtime.controller_state),
                "trusted_now",
                return_value="2026-08-13T12:16:00+00:00",
            ), mock.patch.object(market_cycle_cli, "_write") as write:
                self.assertEqual(
                    market_cycle_cli.main(
                        [
                            "--runtime-root",
                            str(runtime.runtime_root),
                            "--theory-version",
                            "3.3.2",
                            "evaluate-operational",
                            cycle_id,
                        ]
                    ),
                    0,
                )
            emitted = write.call_args.args[0]
            saved = FileOperationalEvaluationStore(runtime).load(cycle_id)
            self.assertEqual(emitted, saved)
            self.assertEqual(
                emitted["evaluation_document"]["payload"]["evaluation_id"],
                f"{cycle_id}.e0-operational-evaluation",
            )
            with mock.patch.object(market_cycle_cli, "_write") as explicit_write:
                self.assertEqual(
                    market_cycle_cli.main(
                        [
                            "--runtime-root",
                            str(runtime.runtime_root),
                            "--theory-version",
                            "3.3.2",
                            "evaluate-operational",
                            cycle_id,
                            "--evaluation-id",
                            f"{cycle_id}.e0-operational-evaluation",
                        ]
                    ),
                    0,
                )
            self.assertEqual(explicit_write.call_args.args[0], saved)
            parsed = market_cycle_cli._parser().parse_args(
                [
                    "--theory-version",
                    "3.3.2",
                    "evaluate-operational",
                    cycle_id,
                ]
            )
            self.assertFalse(hasattr(parsed, "evaluated_at"))


if __name__ == "__main__":
    unittest.main()
