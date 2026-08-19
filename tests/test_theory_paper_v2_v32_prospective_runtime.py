from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tests import test_theory_paper_v2_v32_tick_supervisor as supervisor_fixture
from tests.test_theory_paper_v2_v32_agent_semantic_compiler import _full_fixture
from trade_system.theory_paper_v2.application.v32_cycle_acceptance import (
    DIGEST_FIELD as ACCEPTANCE_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.application.v32_prospective_runtime import (
    _outcome_audit_or_next,
    initialize_v32_prospective_runtime_v1,
    resolve_v32_active_analysis_agent_window_v1,
    route_v32_prospective_wake_v1,
    verify_v32_active_analysis_agent_window_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
    verify_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
    build_v32_outcome_tick_attempt,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
    MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_outcome_tick_permit,
    build_v32_tick_supervisor_checkpoint,
    build_v32_tick_supervisor_failure,
    complete_v32_analysis_tick,
    fail_v32_tick_supervisor,
    open_v32_tick_supervisor_permit,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
)


RUN_ID = "v32-prospective-runtime-test"
BASE = datetime(2026, 8, 8, tzinfo=UTC)


def ts(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def digest(seed: str) -> str:
    return canonical_digest({"seed": seed})


def prepared_source(
    *,
    cutoff: str,
    admitted: str | None = None,
    replayed: str | None = None,
) -> dict:
    return {
        "run_id": RUN_ID,
        "cycle_index": 1,
        "source_cutoff_at": cutoff,
        "admitted_at": admitted or cutoff,
        "replayed_at": replayed or admitted or cutoff,
        "source_qualification_digest": digest("source-qualification"),
        "source_admission_digest": digest("source-admission"),
        "durable_source_replay_receipt_digest": digest("source-replay"),
    }


def policy(run_id: str = RUN_ID) -> dict:
    return build_v32_cycle_audit_policy_v1(
        policy_id="v32-prospective-audit",
        run_scope_id=run_id,
        frozen_at=ts(BASE),
    )


def genesis(run_id: str = RUN_ID) -> dict:
    return build_v32_tick_supervisor_checkpoint(
        run_id=run_id,
        experiment_contract_digest="a" * 64,
        active_authority_digest="b" * 64,
        research_checkpoint_digest="c" * 64,
        outcome_checkpoint_digest="d" * 64,
        timeframe_cache_digest="e" * 64,
        created_at=ts(BASE),
    )


def active_analysis(run_id: str = RUN_ID) -> tuple[dict, dict]:
    before = genesis(run_id)
    permit = build_v32_analysis_tick_permit(
        checkpoint=before,
        schedule_sets=[],
        analysis_decision_at=ts(BASE + timedelta(seconds=1)),
        issued_at=ts(BASE + timedelta(seconds=2)),
        research_checkpoint_digest=before["current_research_checkpoint_digest"],
        outcome_checkpoint_digest=before["current_outcome_checkpoint_digest"],
        timeframe_cache_digest=before["current_timeframe_cache_digest"],
        prior_dynamic_state_digest=None,
    )
    opened = open_v32_tick_supervisor_permit(
        checkpoint=before,
        permit=permit,
        schedule_sets=[],
        updated_at=permit["issued_at"],
    )
    return opened, permit


def accepted_cycle() -> tuple[dict, dict, dict]:
    before = genesis()
    decision = BASE + timedelta(seconds=1)
    permit = build_v32_analysis_tick_permit(
        checkpoint=before,
        schedule_sets=[],
        analysis_decision_at=ts(decision),
        issued_at=ts(decision + timedelta(seconds=1)),
        research_checkpoint_digest=before["current_research_checkpoint_digest"],
        outcome_checkpoint_digest=before["current_outcome_checkpoint_digest"],
        timeframe_cache_digest=before["current_timeframe_cache_digest"],
        prior_dynamic_state_digest=None,
    )
    opened = open_v32_tick_supervisor_permit(
        checkpoint=before,
        permit=permit,
        schedule_sets=[],
        updated_at=permit["issued_at"],
    )
    acceptance = self_digest(
        {
            "schema_id": "test_v32_analysis_acceptance_v1",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "accepted_at": ts(decision + timedelta(seconds=3)),
        },
        ACCEPTANCE_DIGEST_FIELD,
    )
    schedule = build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id="decision:0001",
        cycle_index=1,
        decision_time=permit["analysis_decision_at"],
        scheduled_at=ts(decision + timedelta(seconds=2)),
        sealed_decision_digest=digest("sealed"),
        evaluation_contract_digest=digest("evaluation"),
    )
    completed = complete_v32_analysis_tick(
        checkpoint=opened,
        permit=permit,
        schedule_sets_before=[],
        new_schedule_set=schedule,
        accepted_state_digest=acceptance[ACCEPTANCE_DIGEST_FIELD],
        source_admission_digest=digest("source"),
        source_admission_physical_sha256=digest("source-physical"),
        proposal_lifecycle_digest=digest("proposal"),
        selection_lifecycle_digest=digest("selection"),
        final_action_plan_digest=digest("plan"),
        commit_envelope_digest=digest("commit"),
        shadow_decision_bundle_digest=digest("shadow"),
        new_research_checkpoint_digest=digest("research"),
        new_outcome_checkpoint_digest=digest("outcome"),
        new_timeframe_cache_digest=digest("timeframe"),
        new_dynamic_state_digest=digest("state"),
        completed_at=acceptance["accepted_at"],
    )
    return completed, schedule, acceptance


class ConstantClock:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class HybridTestClock(ConstantClock):
    def __init__(self, value: str, monotonic_values: list[int]) -> None:
        super().__init__(value)
        self._monotonic_values = iter(monotonic_values)

    def monotonic_ns(self) -> int:
        return next(self._monotonic_values)


class FakeSupervisorStore:
    def __init__(self, checkpoint: dict, permit: dict | None = None) -> None:
        self.checkpoint = checkpoint
        self.permit = permit
        self.fail_calls = []

    def initialize_checkpoint(self, *, checkpoint):
        self.checkpoint = deepcopy(dict(checkpoint))
        return deepcopy(self.checkpoint)

    def load_checkpoint(self, *, run_id):
        return deepcopy(self.checkpoint)

    def load_checkpoint_by_digest(self, *, run_id, checkpoint_digest):
        return genesis(run_id)

    def load_permit(self, *, run_id, permit_digest):
        assert self.permit is not None
        assert self.permit[PERMIT_DIGEST_FIELD] == permit_digest
        return deepcopy(self.permit)

    def fail_closed(self, **kwargs):
        self.fail_calls.append(deepcopy(kwargs))
        failure = build_v32_tick_supervisor_failure(
            checkpoint=self.checkpoint,
            failure_lane=kwargs["failure_lane"],
            failure_code=kwargs["failure_code"],
            failure_summary=kwargs["failure_summary"],
            failure_evidence_digest=kwargs["failure_evidence_digest"],
            occurred_at=kwargs["occurred_at"],
        )
        self.checkpoint = fail_v32_tick_supervisor(
            checkpoint=self.checkpoint, failure=failure
        )
        return deepcopy(self.checkpoint)


class FakeOutcomeStore:
    def __init__(self, schedule_sets=None) -> None:
        self.schedule_sets = list(schedule_sets or [])
        self.terminal_receipt_materials = []
        self.checkpoint = self_digest(
            {"schema_id": "test_outcome_checkpoint_v1", "run_id": RUN_ID},
            "checkpoint_digest",
        )

    def initialize_checkpoint(self, **_kwargs):
        return deepcopy(self.checkpoint)

    def load_checkpoint(self, *, run_id):
        return deepcopy(self.checkpoint)

    def load_schedule_sets(self, *, run_id):
        return deepcopy(self.schedule_sets)

    def load_terminal_receipt_materials(self, *, run_id):
        return deepcopy(self.terminal_receipt_materials)


def artifact(role: str) -> tuple[dict, dict]:
    digest_field = f"{role}_digest"
    document = self_digest(
        {
            "schema_id": f"test_{role}_v1",
            "run_id": RUN_ID,
            "cycle_index": 1,
        },
        digest_field,
    )
    binding = {
        "role": role,
        "cycle_index": 1,
        "relative_ref": f"cycles/0001/{role}.json",
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }
    return document, binding


class FakeDynamicStore:
    def __init__(self, acceptance: dict | None = None) -> None:
        self.acceptance = acceptance
        self.document, self.binding = artifact("analysis_material")
        self.checkpoint = self_digest(
            {"schema_id": "test_dynamic_checkpoint_v1", "run_id": RUN_ID},
            "dynamic_research_checkpoint_digest",
        )

    def initialize_checkpoint(self, **_kwargs):
        return deepcopy(self.checkpoint)

    def load_checkpoint(self, *, run_id):
        return deepcopy(self.checkpoint)

    def replay_cycle_acceptance(self, *, run_id, cycle_index):
        assert self.acceptance is not None
        acceptance_binding = {
            "role": "analysis_acceptance",
            "cycle_index": 1,
            "relative_ref": "cycles/0001/acceptance.json",
            "schema_id": self.acceptance["schema_id"],
            "digest_field": ACCEPTANCE_DIGEST_FIELD,
            "semantic_digest": self.acceptance[ACCEPTANCE_DIGEST_FIELD],
            "physical_sha256": hashlib.sha256(
                canonical_bytes(self.acceptance) + b"\n"
            ).hexdigest(),
        }
        return {
            "acceptance": deepcopy(self.acceptance),
            "binding": acceptance_binding,
            "required_bindings": {"analysis_material": deepcopy(self.binding)},
        }

    def load_artifact(self, binding):
        assert binding == self.binding
        return deepcopy(self.document)


class FakeMailbox:
    def __init__(self) -> None:
        self.pending = None
        self.checkpoint = None
        self.chain = None
        self.reads = 0

    def next_pending_request(self, *, run_id, cycle_index):
        self.reads += 1
        return deepcopy(self.pending)

    def load_checkpoint(self, *, run_id, cycle_index):
        return deepcopy(self.checkpoint)

    def load_stage_chain(self, *, run_id, cycle_index, stage):
        return deepcopy(self.chain)

    def install_pending(self) -> None:
        self.pending = pending_request()
        self.checkpoint = {"checkpoint": "bound"}
        self.chain = {
            "request": deepcopy(self.pending["request"]),
            "claim": deepcopy(self.pending["claim"]),
            "stage_status": self.pending["stage_status"],
            "checkpoint_digest": self.pending["checkpoint_digest"],
            "lossless_context_package": None,
            "ordered_agent_input_delivery_units": deepcopy(
                self.pending["ordered_agent_input_delivery_units"]
            ),
        }


def pending_request() -> dict:
    return {
        "run_id": RUN_ID,
        "cycle_index": 1,
        "stage": "PROPOSAL",
        "stage_status": "REQUESTED",
        "next_action": "CURRENT_ROOT_CODEX_CLAIM",
        "checkpoint_digest": digest("mailbox"),
        "request": {
            "request_id": "proposal-request",
            "context_delivery_mode": "INLINE",
        },
        "claim": None,
        "ordered_agent_input_delivery_units": [
            {"sequence": 1, "document": {"packet": "complete"}}
        ],
        "canonical_packet_original_binding": {
            "semantic_digest": digest("packet")
        },
    }


def fake_presentation(**kwargs) -> dict:
    return {
        "request": deepcopy(kwargs["request"]),
        "control_context": deepcopy(kwargs["control_context"]),
        "current_root_codex_only": True,
        "complete_packet_exactly_once": True,
    }


class FakeRevisionStore:
    def __init__(self) -> None:
        self.bundles = {
            "QUALIFICATION": {
                "directory": {"boundary": "QUALIFICATION"},
                "shards": [{"boundary": "QUALIFICATION"}],
            }
        }

    def load_audit_bundle(self, *, run_id, cycle_index, boundary_type):
        return deepcopy(self.bundles.get(boundary_type))


class FakeCompletionStore:
    def __init__(self) -> None:
        self.completion = None

    def load_completion(self, *, run_id, cycle_index):
        return deepcopy(self.completion)


class FakeAuditLane:
    def __init__(self, revision: FakeRevisionStore) -> None:
        self.revision = revision
        self.calls = []

    def advance_once(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        boundary = kwargs["boundary_type"]
        self.revision.bundles[boundary] = {
            "directory": {"boundary": boundary},
            "shards": [{"boundary": boundary}],
        }
        return {
            "boundary_type": boundary,
            "audit_status": "CREATED",
            "result_digest": digest(f"audit-{boundary}"),
        }


_DEFAULT_PREPARED_SOURCE = object()


class FakeAnalysisPort:
    def __init__(
        self,
        *,
        completion=None,
        failure=None,
        prepared=_DEFAULT_PREPARED_SOURCE,
        preparation_result=None,
        preparation_error: Exception | None = None,
    ) -> None:
        self.completion = completion
        self.failure = failure
        self.prepared = (
            prepared_source(cutoff=ts(BASE))
            if prepared is _DEFAULT_PREPARED_SOURCE
            else prepared
        )
        self.preparation_result = preparation_result or {
            **prepared_source(cutoff=ts(BASE)),
            "preparation_status": "SOURCE_READY",
            "state_changed": True,
            "internal_append_only_substage_count": 3,
            "internal_append_only_substages": [
                "SOURCE_QUALIFICATION_SEALED",
                "SOURCE_ADMISSION_SEALED",
                "SOURCE_REPLAY_SEALED",
            ],
            "durable_transition_digest": digest("source-replay"),
        }
        self.preparation_error = preparation_error
        self.prepare_calls = []

    def load_durable_prepared_source(self, **_kwargs):
        return deepcopy(self.prepared)

    def prepare_cycle_source(self, **kwargs):
        self.prepare_calls.append(deepcopy(kwargs))
        if self.preparation_error is not None:
            raise self.preparation_error
        return deepcopy(self.preparation_result)

    def load_durable_analysis_completion(self, *, permit):
        return deepcopy(self.completion)

    def load_durable_analysis_failure(self, *, permit):
        return deepcopy(self.failure)


class RecordingWakeRunner:
    def __init__(
        self,
        *,
        mailbox: FakeMailbox | None = None,
        request_after_call: bool = False,
        advance_status: str = "PENDING",
        supervisor_close: bool = False,
    ) -> None:
        self.calls = []
        self.mailbox = mailbox
        self.request_after_call = request_after_call
        self.advance_status = advance_status
        self.supervisor_close = supervisor_close

    def __call__(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.request_after_call and self.mailbox is not None:
            self.mailbox.install_pending()
        lane = kwargs["lane_requests"][0]["lane"]
        if self.supervisor_close:
            return {
                "runtime_status": "COMPLETED",
                "boundary_kind": f"SUPERVISOR_{lane}_COMPLETED",
                "durable_state_boundaries_this_wake": 1,
            }
        return {
            "runtime_status": "PENDING",
            "boundary_kind": f"{lane}_SUBSTAGE_ADVANCED",
            "lane_advance_status": self.advance_status,
            "durable_transition_digest": digest(f"step-{len(self.calls)}"),
        }


def common_ports(
    *,
    checkpoint,
    permit=None,
    schedules=None,
    acceptance=None,
    run_id: str = RUN_ID,
):
    revision = FakeRevisionStore()
    completion = FakeCompletionStore()
    return {
        "supervisor_store": FakeSupervisorStore(checkpoint, permit),
        "dynamic_store": FakeDynamicStore(acceptance),
        "outcome_store": FakeOutcomeStore(schedules),
        "mailbox": FakeMailbox(),
        "revision_store": revision,
        "audit_completion_store": completion,
        "audit_lane": FakeAuditLane(revision),
        "analysis_port": FakeAnalysisPort(),
        "outcome_port": object(),
        "cycle_audit_policy": policy(run_id),
        "run_id": run_id,
    }


class V32ProspectiveRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mailbox_fixture = _full_fixture()

    def test_agent_window_accepts_one_microsecond_before_and_rejects_deadline(self) -> None:
        checkpoint, permit = active_analysis()
        deadline = datetime.fromisoformat(
            permit["issued_at"].replace("Z", "+00:00")
        ) + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS)
        before = ts(deadline - timedelta(microseconds=1))
        resolved = verify_v32_active_analysis_agent_window_v1(
            run_id=RUN_ID,
            supervisor_checkpoint=checkpoint,
            active_permit=permit,
            predecessor_checkpoint=genesis(),
            schedule_sets=[],
            observed_at=before,
        )
        self.assertTrue(resolved["strictly_before_deadline"])
        self.assertEqual(ts(deadline), resolved["permit_deadline_at"])
        with self.assertRaisesRegex(
            ValueError,
            "V32_RUNTIME_ACTIVE_ANALYSIS_AGENT_WINDOW_EXPIRED",
        ):
            verify_v32_active_analysis_agent_window_v1(
                run_id=RUN_ID,
                supervisor_checkpoint=checkpoint,
                active_permit=permit,
                predecessor_checkpoint=genesis(),
                schedule_sets=[],
                observed_at=ts(deadline),
            )

    def test_agent_window_uses_earliest_bound_due_schedule_minus_reserve(self) -> None:
        start = datetime(2026, 8, 7, tzinfo=UTC)
        checkpoint = supervisor_fixture.bootstrap()
        checkpoint, _, first = supervisor_fixture.analysis_cycle(
            checkpoint, [], decision_at=start
        )
        schedules = [first]
        checkpoint, _, _, _, _ = supervisor_fixture.outcome_tick(
            checkpoint,
            schedules,
            [],
            planned_at=start + timedelta(minutes=15),
        )
        predecessor = deepcopy(checkpoint)
        decision = start + timedelta(minutes=55)
        permit = build_v32_analysis_tick_permit(
            checkpoint=predecessor,
            schedule_sets=schedules,
            analysis_decision_at=ts(decision),
            issued_at=ts(decision + timedelta(seconds=1)),
            research_checkpoint_digest=predecessor[
                "current_research_checkpoint_digest"
            ],
            outcome_checkpoint_digest=predecessor[
                "current_outcome_checkpoint_digest"
            ],
            timeframe_cache_digest=predecessor[
                "current_timeframe_cache_digest"
            ],
            prior_dynamic_state_digest=predecessor[
                "current_dynamic_state_digest"
            ],
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=predecessor,
            permit=permit,
            schedule_sets=schedules,
            updated_at=permit["issued_at"],
        )
        result = resolve_v32_active_analysis_agent_window_v1(
            run_id=supervisor_fixture.RUN_ID,
            supervisor_checkpoint=opened,
            active_permit=permit,
            predecessor_checkpoint=predecessor,
            schedule_sets=schedules,
            observed_at=ts(decision + timedelta(seconds=30)),
        )
        self.assertEqual(ts(start + timedelta(hours=1)), result["next_due_at"])
        self.assertEqual(
            ts(
                start
                + timedelta(
                    hours=1,
                    seconds=-EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
                )
            ),
            result["permit_deadline_at"],
        )
        self.assertTrue(result["strictly_before_deadline"])

    def test_agent_window_fails_on_missing_schedule_or_predecessor(self) -> None:
        checkpoint, permit = active_analysis()
        observed_at = ts(BASE + timedelta(minutes=1))
        missing_schedule = deepcopy(permit)
        missing_schedule["outcome_schedule_set_digests"] = ["f" * 64]
        with self.assertRaisesRegex(
            ValueError, "V32_RUNTIME_BOUND_SCHEDULE_SET_MISSING"
        ):
            resolve_v32_active_analysis_agent_window_v1(
                run_id=RUN_ID,
                supervisor_checkpoint=checkpoint,
                active_permit=missing_schedule,
                predecessor_checkpoint=genesis(),
                schedule_sets=[],
                observed_at=observed_at,
            )
        with self.assertRaisesRegex(
            ValueError, "V32_RUNTIME_ACTIVE_ANALYSIS_WINDOW_INVALID"
        ):
            resolve_v32_active_analysis_agent_window_v1(
                run_id=RUN_ID,
                supervisor_checkpoint=checkpoint,
                active_permit=permit,
                predecessor_checkpoint={},
                schedule_sets=[],
                observed_at=observed_at,
            )

    def test_first_analysis_is_blocked_without_sealed_qualification_audit(self) -> None:
        ports = common_ports(checkpoint=genesis())
        ports["revision_store"].bundles.pop("QUALIFICATION")
        with self.assertRaisesRegex(
            ValueError,
            "V32_RUNTIME_QUALIFICATION_AUDIT_REQUIRED_BEFORE_ANALYSIS",
        ):
            route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=RecordingWakeRunner(),
            )

    def test_complete_three_horizon_outcome_gets_one_cycle_scoped_audit(self) -> None:
        checkpoint, schedule_set, _acceptance = accepted_cycle()
        schedule_by_id = {
            row["schedule_id"]: row for row in schedule_set["schedules"]
        }
        terminal_ids = sorted(schedule_by_id)
        checkpoint = {
            **checkpoint,
            "terminal_schedule_ids": terminal_ids,
        }
        outcome_store = FakeOutcomeStore([schedule_set])
        materials = []
        for index, horizon in enumerate(("15M", "1H", "4H"), start=1):
            schedule = next(
                row for row in schedule_set["schedules"] if row["horizon"] == horizon
            )
            receipt = {
                "schema_id": f"test_outcome_{horizon}_v1",
                "run_id": RUN_ID,
                "cycle_index": 1,
                "schedule_id": schedule["schedule_id"],
                "horizon": horizon,
                "resolved_at": ts(BASE + timedelta(minutes=15 * index)),
                "terminal": True,
            }
            materials.append(
                {
                    "receipt": receipt,
                    "receipt_binding": {
                        "relative_ref": f"outcomes/{horizon}.json",
                        "schema_id": receipt["schema_id"],
                        "digest_field": "outcome_receipt_digest",
                        "semantic_digest": digest(f"outcome-{horizon}"),
                        "physical_sha256": digest(f"outcome-{horizon}-physical"),
                    },
                }
            )
        outcome_store.terminal_receipt_materials = materials
        revision = FakeRevisionStore()
        audit_lane = FakeAuditLane(revision)

        result = _outcome_audit_or_next(
            supervisor=checkpoint,
            outcome_store=outcome_store,
            revision_store=revision,
            audit_lane=audit_lane,
            cycle_audit_policy=policy(),
            schedule_by_id=schedule_by_id,
        )

        self.assertEqual("OUTCOME", result["boundary_type"])
        self.assertEqual(1, len(audit_lane.calls))
        self.assertEqual(
            ["outcome_15m", "outcome_1h", "outcome_4h"],
            [row["role"] for row in audit_lane.calls[0]["sealed_sources"]],
        )
        self.assertEqual(
            ts(BASE + timedelta(minutes=45)),
            audit_lane.calls[0]["boundary_sealed_at"],
        )
        self.assertIsNone(
            _outcome_audit_or_next(
                supervisor=checkpoint,
                outcome_store=outcome_store,
                revision_store=revision,
                audit_lane=audit_lane,
                cycle_audit_policy=policy(),
                schedule_by_id=schedule_by_id,
            )
        )

    def test_expiry_outcome_audit_seals_shared_aggregate_once(self) -> None:
        checkpoint, schedule_set, _acceptance = accepted_cycle()
        schedule_by_id = {
            row["schedule_id"]: row for row in schedule_set["schedules"]
        }
        checkpoint = {
            **checkpoint,
            "terminal_schedule_ids": sorted(schedule_by_id),
        }
        aggregate = self_digest(
            {
                "schema_id": "theory_paper_v32_outcome_window_expiry_terminal_v1",
                "run_id": RUN_ID,
                "rows": sorted(schedule_by_id),
            },
            "outcome_window_expiry_terminal_digest",
        )
        aggregate_binding = {
            "relative_ref": "outcome-v32/expiry/shared.json",
            "schema_id": aggregate["schema_id"],
            "digest_field": "outcome_window_expiry_terminal_digest",
            "semantic_digest": aggregate[
                "outcome_window_expiry_terminal_digest"
            ],
            "physical_sha256": hashlib.sha256(
                canonical_bytes(aggregate) + b"\n"
            ).hexdigest(),
        }
        materials = []
        for index, horizon in enumerate(("15M", "1H", "4H")):
            schedule = next(
                row for row in schedule_set["schedules"] if row["horizon"] == horizon
            )
            receipt = {
                "schema_id": "theory_paper_v32_outcome_window_expiry_row_v1",
                "run_id": RUN_ID,
                "cycle_index": 1,
                "schedule_id": schedule["schedule_id"],
                "horizon": horizon,
                "resolved_at": ts(BASE + timedelta(hours=5)),
                "terminal": True,
            }
            binding = (
                {
                    "binding_kind": "EXPIRY_AGGREGATE_MEMBER",
                    "aggregate_document": aggregate,
                    "aggregate_binding": aggregate_binding,
                    "member_semantic_digest": digest("member-15m"),
                }
                if index == 0
                else {
                    "binding_kind": "EXPIRY_AGGREGATE_MEMBER_REF",
                    "aggregate_semantic_digest": aggregate_binding[
                        "semantic_digest"
                    ],
                    "member_semantic_digest": digest(f"member-{horizon}"),
                }
            )
            materials.append({"receipt": receipt, "receipt_binding": binding})
        outcome_store = FakeOutcomeStore([schedule_set])
        outcome_store.terminal_receipt_materials = materials
        revision = FakeRevisionStore()
        audit_lane = FakeAuditLane(revision)
        _outcome_audit_or_next(
            supervisor=checkpoint,
            outcome_store=outcome_store,
            revision_store=revision,
            audit_lane=audit_lane,
            cycle_audit_policy=policy(),
            schedule_by_id=schedule_by_id,
        )
        self.assertEqual(1, len(audit_lane.calls[0]["sealed_sources"]))
        self.assertEqual(
            aggregate,
            audit_lane.calls[0]["sealed_sources"][0]["document"],
        )

    def test_genesis_binds_dynamic_outcome_timeframe_and_supervisor(self) -> None:
        dynamic = FakeDynamicStore()
        outcome = FakeOutcomeStore()
        supervisor = FakeSupervisorStore(genesis())
        result = initialize_v32_prospective_runtime_v1(
            dynamic_store=dynamic,
            outcome_store=outcome,
            supervisor_store=supervisor,
            run_id=RUN_ID,
            experiment_contract_digest="a" * 64,
            active_authority_digest="b" * 64,
            initial_timeframe_cache_digest="e" * 64,
            cycle_audit_policy=policy(),
            created_at=ts(BASE),
        )
        self.assertEqual("READY", result["runtime_status"])
        self.assertEqual(
            dynamic.checkpoint["dynamic_research_checkpoint_digest"],
            supervisor.checkpoint["current_research_checkpoint_digest"],
        )
        self.assertEqual(
            outcome.checkpoint["checkpoint_digest"],
            supervisor.checkpoint["current_outcome_checkpoint_digest"],
        )
        self.assertEqual("e" * 64, result["timeframe_cache_digest"])

    def test_ready_cycle_seals_source_before_opening_analysis_permit(self) -> None:
        ports = common_ports(checkpoint=genesis())
        analysis = FakeAnalysisPort(prepared=None)
        ports["analysis_port"] = analysis
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(seconds=1))),
            wake_runner=runner,
        )
        self.assertEqual("SOURCE_READY", result["runtime_status"])
        self.assertEqual("SOURCE_PREPARATION_COMPLETED", result["boundary_kind"])
        self.assertEqual("SOURCE_READY", result["source_preparation_status"])
        self.assertEqual(3, result["internal_append_only_substage_count"])
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(analysis.prepare_calls))
        self.assertFalse(result["outcome_values_read"])

    def test_analysis_permit_uses_durable_source_cutoff_not_wake_clock(self) -> None:
        cutoff = ts(BASE + timedelta(microseconds=100_000))
        admitted = ts(BASE + timedelta(microseconds=200_000))
        replayed = ts(BASE + timedelta(microseconds=300_000))
        now = ts(BASE + timedelta(seconds=1, microseconds=123_456))
        ports = common_ports(checkpoint=genesis())
        ports["analysis_port"] = FakeAnalysisPort(
            prepared=prepared_source(
                cutoff=cutoff, admitted=admitted, replayed=replayed
            )
        )
        runner = RecordingWakeRunner()
        route_v32_prospective_wake_v1(
            **ports, clock=ConstantClock(now), wake_runner=runner
        )
        request = runner.calls[0]["lane_requests"][0]
        self.assertEqual("ANALYSIS", request["lane"])
        self.assertEqual(cutoff, request["analysis_decision_at"])
        self.assertEqual(now, request["issued_at"])

    def test_stale_prepared_source_fails_closed_without_opening_permit(self) -> None:
        ports = common_ports(checkpoint=genesis())
        ports["analysis_port"] = FakeAnalysisPort(
            prepared=prepared_source(cutoff=ts(BASE))
        )
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(seconds=901))),
            wake_runner=runner,
        )
        self.assertEqual("FAILED_CLOSED", result["runtime_status"])
        self.assertEqual(
            "SOURCE_CLOCK_OR_PIT_INVALID", result["failure_code"]
        )
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))

    def test_due_outcome_has_priority_over_missing_analysis_audit(self) -> None:
        checkpoint, schedule, acceptance = accepted_cycle()
        ports = common_ports(
            checkpoint=checkpoint,
            schedules=[schedule],
            acceptance=acceptance,
        )
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(schedule["schedules"][0]["outcome_not_before"]),
            wake_runner=runner,
        )
        self.assertEqual("OUTCOME", runner.calls[0]["lane_requests"][0]["lane"])
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", result["boundary_kind"])
        self.assertEqual([], ports["audit_lane"].calls)

    def test_active_expiry_permit_reloads_without_legacy_attempt(self) -> None:
        before, schedule, acceptance = accepted_cycle()
        expires_at = datetime.fromisoformat(
            schedule["schedules"][0]["expires_at"].replace("Z", "+00:00")
        )
        issued_at = ts(expires_at + timedelta(microseconds=1))
        permit = build_v32_outcome_tick_permit(
            checkpoint=before,
            schedule_sets=[schedule],
            tick_attempt=None,
            issued_at=issued_at,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=before,
            permit=permit,
            schedule_sets=[schedule],
            updated_at=issued_at,
        )
        ports = common_ports(
            checkpoint=opened,
            permit=permit,
            schedules=[schedule],
            acceptance=acceptance,
        )
        ports["supervisor_store"].load_checkpoint_by_digest = (
            lambda **_kwargs: deepcopy(before)
        )
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(issued_at),
            wake_runner=runner,
        )
        self.assertEqual("OUTCOME_SUBSTAGE_ADVANCED", result["boundary_kind"])
        self.assertEqual("OUTCOME", runner.calls[0]["lane_requests"][0]["lane"])

    def test_active_public_tick_crossing_grace_fails_before_network(self) -> None:
        before, schedule, acceptance = accepted_cycle()
        due_at = schedule["schedules"][0]["outcome_not_before"]
        attempt = build_v32_outcome_tick_attempt(
            run_id=RUN_ID,
            tick_index=before["next_outcome_tick_index"],
            planned_tick_at=due_at,
            reserved_at=due_at,
        )
        permit = build_v32_outcome_tick_permit(
            checkpoint=before,
            schedule_sets=[schedule],
            tick_attempt=attempt,
            issued_at=due_at,
        )
        opened = open_v32_tick_supervisor_permit(
            checkpoint=before,
            permit=permit,
            schedule_sets=[schedule],
            updated_at=due_at,
            tick_attempt=attempt,
        )
        ports = common_ports(
            checkpoint=opened,
            permit=permit,
            schedules=[schedule],
            acceptance=acceptance,
        )
        ports["supervisor_store"].load_checkpoint_by_digest = (
            lambda **_kwargs: deepcopy(before)
        )
        runner = RecordingWakeRunner()
        expired_at = ts(
            datetime.fromisoformat(
                schedule["schedules"][0]["expires_at"].replace("Z", "+00:00")
            )
            + timedelta(microseconds=1)
        )
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(expired_at),
            wake_runner=runner,
        )
        self.assertEqual("FAILED_CLOSED", result["runtime_status"])
        self.assertEqual(0, result["network_requests"])
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))

    def test_missing_active_permit_is_durably_failed_closed(self) -> None:
        checkpoint, _permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=None)
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
            wake_runner=runner,
        )
        self.assertEqual("FAILED_CLOSED", result["runtime_status"])
        self.assertEqual("SUPERVISOR_ACTIVE_PERMIT_FAILED_CLOSED", result["boundary_kind"])
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))

    def test_active_permit_schedule_registry_corruption_fails_closed(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)

        def corrupt_registry(*, run_id):
            raise ValueError("injected schedule registry corruption")

        ports["outcome_store"].load_schedule_sets = corrupt_registry
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
            wake_runner=runner,
        )
        self.assertEqual("FAILED_CLOSED", result["runtime_status"])
        self.assertEqual(
            "SUPERVISOR_ACTIVE_PERMIT_FAILED_CLOSED",
            result["boundary_kind"],
        )
        self.assertEqual(0, result["network_requests"])
        self.assertEqual([], runner.calls)
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))
        again = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(minutes=2))),
            wake_runner=runner,
        )
        self.assertEqual("FAILED_CLOSED", again["runtime_status"])
        self.assertEqual("NO_MUTATION_TERMINAL_STATE", again["boundary_kind"])
        self.assertEqual(0, again["durable_state_boundaries_this_wake"])
        self.assertEqual(0, again["network_requests"])
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))

    def test_burst_stops_at_mailbox_and_returns_complete_external_request(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        mailbox = ports["mailbox"]
        runner = RecordingWakeRunner(
            mailbox=mailbox, request_after_call=True
        )
        with mock.patch(
            "trade_system.theory_paper_v2.application.v32_prospective_runtime."
            "build_v32_current_codex_presentation_envelope_v1",
            side_effect=fake_presentation,
        ):
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=runner,
            )
        self.assertEqual(1, len(runner.calls))
        request = result
        self.assertEqual("PROPOSAL", request["control_context"]["stage"])
        self.assertTrue(request["current_root_codex_only"])
        self.assertTrue(request["complete_packet_exactly_once"])
        self.assertEqual(
            request["request"]["request_id"], "proposal-request"
        )

    def test_analysis_burst_has_a_hard_sixty_four_step_reentry_bound(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        runner = RecordingWakeRunner()
        with mock.patch(
            "trade_system.theory_paper_v2.application.v32_prospective_runtime."
            "build_v32_current_codex_presentation_envelope_v1",
            side_effect=fake_presentation,
        ):
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=runner,
            )
        self.assertEqual(MAX_ANALYSIS_SUBSTAGES_PER_WAKE, len(runner.calls))
        self.assertEqual(
            MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
            result["internal_append_only_substages"],
        )
        self.assertEqual(1, result["high_level_boundaries_completed_this_wake"])
        self.assertEqual(
            MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
            result["durable_state_boundaries_this_wake"],
        )
        self.assertEqual(
            "BURST_STEP_BOUND_REACHED", result["analysis_burst_stop_reason"]
        )

    def test_already_requested_mailbox_is_zero_write_wait(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        ports["mailbox"].install_pending()
        runner = RecordingWakeRunner()
        with mock.patch(
            "trade_system.theory_paper_v2.application.v32_prospective_runtime."
            "build_v32_current_codex_presentation_envelope_v1",
            side_effect=fake_presentation,
        ):
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=runner,
            )
        self.assertEqual([], runner.calls)
        self.assertEqual(
            "PROSPECTIVE_PENDING_AGENT_ACTION",
            result["control_context"]["presentation_kind"],
        )
        self.assertNotIn("runtime_status", result)
        self.assertNotIn("external_action_request", result)
        self.assertNotIn("supervisor_alert_status", result)

    def test_real_local_mailbox_requested_and_claimed_are_exact_bounded_outputs(
        self,
    ) -> None:
        fixture = self.mailbox_fixture
        run_id = fixture["proposal_context"]["run_id"]
        packet = fixture["proposal_context"]["canonical_packet"]
        for stage_status in ("REQUESTED", "CLAIMED"):
            with self.subTest(stage_status=stage_status), TemporaryDirectory() as root:
                mailbox = LocalV32CurrentRootAgentMailbox(Path(root))
                initial = mailbox.initialize_checkpoint(
                    mailbox_id=f"mailbox::{run_id}::1",
                    run_id=run_id,
                    cycle_index=1,
                    created_at="2026-08-07T00:16:00Z",
                )
                opened = mailbox.enqueue_request(
                    run_id=run_id,
                    cycle_index=1,
                    expected_checkpoint_digest=initial[
                        MAILBOX_CHECKPOINT_DIGEST_FIELD
                    ],
                    agent_input_context=fixture["proposal_context"],
                    agent_input_context_binding=fixture[
                        "proposal_context_binding"
                    ],
                    reserved_at="2026-08-07T00:16:05Z",
                )
                current = opened["checkpoint"]
                if stage_status == "CLAIMED":
                    claimed = mailbox.claim_request(
                        run_id=run_id,
                        cycle_index=1,
                        stage="PROPOSAL",
                        expected_checkpoint_digest=current[
                            MAILBOX_CHECKPOINT_DIGEST_FIELD
                        ],
                        claimed_at="2026-08-07T00:16:10Z",
                    )
                    current = claimed["checkpoint"]
                checkpoint, permit = active_analysis(run_id)
                ports = common_ports(
                    checkpoint=checkpoint,
                    permit=permit,
                    run_id=run_id,
                )
                ports["mailbox"] = mailbox
                alert = mock.Mock()

                result = route_v32_prospective_wake_v1(
                    **ports,
                    clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                    supervisor_alert_port=alert,
                    wake_runner=RecordingWakeRunner(),
                )

                verify_v32_current_codex_presentation_envelope_v1(result)
                self.assertLessEqual(
                    len(canonical_bytes(result)),
                    MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
                )
                self.assertEqual(
                    canonical_bytes(result).count(canonical_bytes(packet)), 1
                )
                self.assertEqual(
                    stage_status, result["control_context"]["stage_status"]
                )
                self.assertNotIn("external_action_request", result)
                self.assertNotIn("supervisor_alert_status", result)
                alert.load_alert_status.assert_not_called()
                after = mailbox.load_checkpoint(run_id=run_id, cycle_index=1)
                self.assertEqual(
                    current[MAILBOX_CHECKPOINT_DIGEST_FIELD],
                    after[MAILBOX_CHECKPOINT_DIGEST_FIELD],
                )

    def test_orphan_claim_tail_remains_requested_and_wake_is_zero_write(
        self,
    ) -> None:
        fixture = self.mailbox_fixture
        run_id = fixture["proposal_context"]["run_id"]
        with TemporaryDirectory() as root:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(root))
            initial = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{run_id}::1",
                run_id=run_id,
                cycle_index=1,
                created_at="2026-08-07T00:16:00Z",
            )
            opened = mailbox.enqueue_request(
                run_id=run_id,
                cycle_index=1,
                expected_checkpoint_digest=initial[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=fixture["proposal_context"],
                agent_input_context_binding=fixture[
                    "proposal_context_binding"
                ],
                reserved_at="2026-08-07T00:16:05Z",
            )
            with mock.patch.object(
                mailbox,
                "_commit",
                side_effect=RuntimeError("simulated crash before checkpoint CAS"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    mailbox.claim_request(
                        run_id=run_id,
                        cycle_index=1,
                        stage="PROPOSAL",
                        expected_checkpoint_digest=opened["checkpoint"][
                            MAILBOX_CHECKPOINT_DIGEST_FIELD
                        ],
                        claimed_at="2026-08-07T00:16:10Z",
                    )
            chain = mailbox.load_stage_chain(
                run_id=run_id, cycle_index=1, stage="PROPOSAL"
            )
            self.assertEqual(chain["stage_status"], "REQUESTED")
            self.assertIsNotNone(chain["claim"])
            before = tuple(
                (path.relative_to(root).as_posix(), path.read_bytes())
                for path in sorted(Path(root).rglob("*.json"))
            )
            checkpoint, permit = active_analysis(run_id)
            ports = common_ports(
                checkpoint=checkpoint,
                permit=permit,
                run_id=run_id,
            )
            ports["mailbox"] = mailbox
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=RecordingWakeRunner(),
            )
            after = tuple(
                (path.relative_to(root).as_posix(), path.read_bytes())
                for path in sorted(Path(root).rglob("*.json"))
            )
            verify_v32_current_codex_presentation_envelope_v1(result)
            self.assertEqual(result["control_context"]["stage_status"], "REQUESTED")
            self.assertEqual(
                result["control_context"]["next_action"],
                "CURRENT_ROOT_CODEX_CLAIM",
            )
            self.assertIsNone(result["claim"])
            self.assertEqual(before, after)

    def test_durable_delivery_after_response_loss_is_consumed_by_analysis_lane(
        self,
    ) -> None:
        fixture = self.mailbox_fixture
        run_id = fixture["proposal_context"]["run_id"]
        with TemporaryDirectory() as root:
            mailbox = LocalV32CurrentRootAgentMailbox(Path(root))
            initial = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{run_id}::1",
                run_id=run_id,
                cycle_index=1,
                created_at="2026-08-07T00:16:00Z",
            )
            opened = mailbox.enqueue_request(
                run_id=run_id,
                cycle_index=1,
                expected_checkpoint_digest=initial[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=fixture["proposal_context"],
                agent_input_context_binding=fixture[
                    "proposal_context_binding"
                ],
                reserved_at="2026-08-07T00:16:05Z",
            )
            claimed = mailbox.claim_request(
                run_id=run_id,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=opened["checkpoint"][
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                claimed_at="2026-08-07T00:16:10Z",
            )
            supervisor, permit = active_analysis(run_id)
            ports = common_ports(
                checkpoint=supervisor,
                permit=permit,
                run_id=run_id,
            )
            ports["mailbox"] = mailbox
            presentation = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=RecordingWakeRunner(),
            )
            verify_v32_current_codex_presentation_envelope_v1(presentation)
            mailbox.submit_delivery(
                run_id=run_id,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=claimed["checkpoint"][
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                current_codex_presentation_envelope=presentation,
                expected_current_codex_presentation_digest=presentation[
                    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                ],
                delivered_at="2026-08-07T00:16:20Z",
                payload_utf8=fixture["proposal_payload"],
            )
            self.assertEqual(
                "DELIVERED",
                mailbox.next_pending_request(
                    run_id=run_id, cycle_index=1
                )["stage_status"],
            )

            consume_calls: list[dict] = []

            def consume_runner(**kwargs):
                consume_calls.append(deepcopy(kwargs))
                checkpoint = mailbox.load_checkpoint(
                    run_id=run_id, cycle_index=1
                )
                mailbox.consume_delivery(
                    run_id=run_id,
                    cycle_index=1,
                    stage="PROPOSAL",
                    expected_checkpoint_digest=checkpoint[
                        MAILBOX_CHECKPOINT_DIGEST_FIELD
                    ],
                    consumed_at="2026-08-07T00:16:30Z",
                )
                return {
                    "runtime_status": "PENDING",
                    "boundary_kind": "ANALYSIS_SUBSTAGE_ADVANCED",
                    "lane_advance_status": "COMPLETION_SEALED",
                    "durable_transition_digest": digest("consumed-delivery"),
                }

            # The delivery response is deliberately ignored above.  A fresh
            # wake must treat DELIVERED as controller work, not ask Codex to
            # submit the same payload again.
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=consume_runner,
            )
            self.assertEqual(1, len(consume_calls))
            self.assertEqual(
                "COMPLETION_SEALED", result["analysis_burst_stop_reason"]
            )
            self.assertEqual(
                "CONSUMED",
                mailbox.load_stage_chain(
                    run_id=run_id,
                    cycle_index=1,
                    stage="PROPOSAL",
                )["stage_status"],
            )

    def test_pending_mailbox_read_failure_is_one_stable_runtime_error(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        mailbox = mock.Mock()
        mailbox.next_pending_request.return_value = pending_request()
        mailbox.load_checkpoint.side_effect = RuntimeError("host-specific")
        ports["mailbox"] = mailbox
        with self.assertRaisesRegex(
            ValueError, "V32_RUNTIME_MAILBOX_PRESENTATION_READ_FAILED"
        ):
            route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=RecordingWakeRunner(),
            )

    def test_malformed_pending_mailbox_state_fails_before_lane_advance(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        malformed = pending_request()
        malformed["run_id"] = "wrong-run"
        ports["mailbox"].pending = malformed
        runner = RecordingWakeRunner()
        with self.assertRaisesRegex(
            ValueError, "V32_RUNTIME_MAILBOX_PENDING_STATE_INVALID"
        ):
            route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=runner,
            )
        self.assertEqual([], runner.calls)

    def test_post_substage_presentation_failure_returns_boundary_report(
        self,
    ) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        mailbox = ports["mailbox"]
        runner = RecordingWakeRunner(mailbox=mailbox, request_after_call=True)
        with mock.patch(
            "trade_system.theory_paper_v2.application.v32_prospective_runtime."
            "build_v32_current_codex_presentation_envelope_v1",
            side_effect=ValueError("host-specific"),
        ):
            result = route_v32_prospective_wake_v1(
                **ports,
                clock=ConstantClock(ts(BASE + timedelta(minutes=1))),
                wake_runner=runner,
            )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(
            "ANALYSIS_SUBSTAGE_COMMITTED_AGENT_PRESENTATION_FAILED",
            result["boundary_kind"],
        )
        self.assertEqual(
            "V32_RUNTIME_AGENT_PRESENTATION_BUILD_FAILED",
            result["agent_presentation_error_code"],
        )
        self.assertEqual(1, result["durable_state_boundaries_this_wake"])
        self.assertFalse(result["outcome_values_read"])

    def test_active_analysis_runs_inside_budget_and_reserves_outcome_window(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        runner = RecordingWakeRunner(advance_status="COMPLETION_SEALED")
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=HybridTestClock(
                ts(BASE + timedelta(minutes=10)),
                [1_000_000_000, 1_007_000_000],
            ),
            wake_runner=runner,
        )
        self.assertEqual("ANALYSIS", runner.calls[0]["lane_requests"][0]["lane"])
        self.assertEqual("COMPLETION_SEALED", result["analysis_burst_stop_reason"])
        self.assertEqual(ts(BASE + timedelta(minutes=15, seconds=2)), result["next_due_at"])
        self.assertEqual(
            ts(
                BASE
                + timedelta(
                    seconds=2 + TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS
                )
            ),
            result["permit_deadline_at"],
        )
        self.assertEqual(
            EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
            int(
                (
                    datetime.fromisoformat(
                        result["next_due_at"].replace("Z", "+00:00")
                    )
                    - datetime.fromisoformat(
                        result["permit_deadline_at"].replace("Z", "+00:00")
                    )
                ).total_seconds()
            ),
        )
        self.assertEqual(7, result["analysis_burst_monotonic_elapsed_ms"])

    def test_deadline_without_sealed_terminal_fails_closed_without_outcome_read(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(minutes=12))),
            wake_runner=runner,
        )
        self.assertEqual([], runner.calls)
        self.assertEqual("FAILED_CLOSED", result["runtime_status"])
        self.assertFalse(result["outcome_values_read"])
        self.assertEqual(1, len(ports["supervisor_store"].fail_calls))

    def test_sealed_analysis_tail_closes_supervisor_as_separate_boundary(self) -> None:
        checkpoint, permit = active_analysis()
        ports = common_ports(checkpoint=checkpoint, permit=permit)
        ports["analysis_port"] = FakeAnalysisPort(completion={"sealed": True})
        runner = RecordingWakeRunner(supervisor_close=True)
        result = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(ts(BASE + timedelta(minutes=31))),
            wake_runner=runner,
        )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual("SUPERVISOR_ANALYSIS_COMPLETED", result["boundary_kind"])
        self.assertEqual([], ports["supervisor_store"].fail_calls)

    def test_analysis_and_acceptance_audits_are_two_wakes(self) -> None:
        checkpoint, schedule, acceptance = accepted_cycle()
        ports = common_ports(
            checkpoint=checkpoint,
            schedules=[schedule],
            acceptance=acceptance,
        )
        before_due = ts(BASE + timedelta(minutes=5))
        first = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(before_due),
            wake_runner=RecordingWakeRunner(),
        )
        second = route_v32_prospective_wake_v1(
            **ports,
            clock=ConstantClock(before_due),
            wake_runner=RecordingWakeRunner(),
        )
        self.assertEqual("ANALYSIS_AUDIT_ADVANCED", first["boundary_kind"])
        self.assertEqual("ACCEPTANCE_AUDIT_ADVANCED", second["boundary_kind"])
        self.assertEqual(
            ["ANALYSIS", "ACCEPTANCE"],
            [call["boundary_type"] for call in ports["audit_lane"].calls],
        )
        self.assertIsNone(ports["audit_lane"].calls[0]["completion_id"])
        self.assertIsNotNone(ports["audit_lane"].calls[1]["completion_id"])


if __name__ == "__main__":
    unittest.main()
