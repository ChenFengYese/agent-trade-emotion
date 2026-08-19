from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
import inspect
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v32_agent_semantic_compiler import _full_fixture
from tests.test_theory_paper_v2_v32_dynamic_store import (
    _writer as _dynamic_writer,
)
from trade_system.theory_paper_v2.application.v32_prospective_runtime import (
    V32ProspectiveRuntimeError,
    initialize_v32_prospective_runtime_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
)
from trade_system.theory_paper_v2.domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    build_v32_agent_input_context_v1,
    build_v32_embedded_document_binding_v1,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
    verify_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
    open_v32_tick_supervisor_permit,
)
from trade_system.theory_paper_v2.infrastructure.v32_dynamic_store import (
    CHECKPOINT_DIGEST_FIELD as DYNAMIC_CHECKPOINT_DIGEST_FIELD,
    LocalV32DynamicStore,
    STORE_ROOT as DYNAMIC_STORE_ROOT,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from trade_system.theory_paper_v2.presentation import (
    v32_target_wake_composition as composition,
)


RUN_ID = "v32-target-wake-test"
CREATED_AT = "2026-08-08T00:00:00Z"
CONTRACT_DIGEST = "b" * 64
AUTHORITY_DIGEST = "a" * 64
TIMEFRAME_DIGEST = "c" * 64
RESEARCH_DIGEST = "4" * 64
OUTCOME_DIGEST = "5" * 64
MAILBOX_BEFORE_DIGEST = "6" * 64
MAILBOX_AFTER_DIGEST = "7" * 64
REQUEST_DIGEST = "8" * 64
PRESENTATION_DIGEST = "9" * 64


class _UnusedMaterial:
    @staticmethod
    def _unexpected(*args, **kwargs):
        del args, kwargs
        raise AssertionError("material port must remain unused before audit gate")

    build_timeframe_context = _unexpected
    build_proposal_packet = _unexpected
    lossless_context_package = _unexpected
    build_authorized_revision_cycle_registry = _unexpected
    build_outcome_schedule_set = _unexpected


class _Clock:
    adapter_id = "V32_TEST_INTERNAL_CLOCK"

    def __call__(self) -> str:
        return "2026-08-08T00:01:00Z"

    def monotonic_ns(self) -> int:
        return 1


class _FixedClock(_Clock):
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class _SequenceClock(_Clock):
    def __init__(self, values: list[str]) -> None:
        self._values = iter(values)

    def __call__(self) -> str:
        return next(self._values)


def _policy(run_id: str = RUN_ID) -> dict:
    return build_v32_cycle_audit_policy_v1(
        policy_id="v32-target-wake-test-policy",
        run_scope_id=run_id,
        frozen_at=CREATED_AT,
    )


def _fake_replay(run_root: Path, run_id: str = RUN_ID) -> dict:
    return {
        "full_loader_verified": True,
        "replay_only": True,
        "state_mutation_count": 0,
        "network_request_count": 0,
        "run_root": str(run_root),
        "authority_projection": {
            "authority": {
                "run_id": run_id,
                "recorded_at": CREATED_AT,
            },
            "experiment_contract": {
                EXPERIMENT_CONTRACT_DIGEST_FIELD: CONTRACT_DIGEST,
            },
            "manifest": {},
            "theory_approval": {},
            "authorization_receipt": {},
        },
        "global_source_bindings": {
            "authority": {
                "path": "config/test-authority.json",
                "schema_id": AUTHORITY_SCHEMA_ID,
                "digest_field": AUTHORITY_DIGEST_FIELD,
                "semantic_digest": AUTHORITY_DIGEST,
                "physical_sha256": "d" * 64,
            }
        },
        "cycle_audit_policy": _policy(run_id),
    }


def _active_analysis_boundary() -> tuple[dict, dict, dict]:
    predecessor = build_v32_tick_supervisor_checkpoint(
        run_id=RUN_ID,
        experiment_contract_digest=CONTRACT_DIGEST,
        active_authority_digest=AUTHORITY_DIGEST,
        research_checkpoint_digest=RESEARCH_DIGEST,
        outcome_checkpoint_digest=OUTCOME_DIGEST,
        timeframe_cache_digest=TIMEFRAME_DIGEST,
        created_at=CREATED_AT,
    )
    permit = build_v32_analysis_tick_permit(
        checkpoint=predecessor,
        schedule_sets=[],
        analysis_decision_at="2026-08-08T00:00:01Z",
        issued_at="2026-08-08T00:00:02Z",
        research_checkpoint_digest=RESEARCH_DIGEST,
        outcome_checkpoint_digest=OUTCOME_DIGEST,
        timeframe_cache_digest=TIMEFRAME_DIGEST,
        prior_dynamic_state_digest=None,
    )
    checkpoint = open_v32_tick_supervisor_permit(
        checkpoint=predecessor,
        permit=permit,
        schedule_sets=[],
        updated_at=permit["issued_at"],
    )
    return checkpoint, permit, predecessor


def _pending_request(*, stage: str, status: str) -> dict:
    return {
        "run_id": RUN_ID,
        "cycle_index": 1,
        "stage": stage,
        "stage_status": status,
        "next_action": (
            "CURRENT_ROOT_CODEX_CLAIM"
            if status == "REQUESTED"
            else "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
        ),
        "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
        "request": {
            "current_root_agent_mailbox_request_digest": REQUEST_DIGEST
        },
        "claim": (
            None
            if status == "REQUESTED"
            else {
                "claim": "bound",
                "claimed_at": "2026-08-08T00:00:59Z",
            }
        ),
    }


def _fake_presentation_preview(**kwargs) -> dict:
    return {
        "mailbox_checkpoint": kwargs["mailbox_checkpoint"],
        "request": kwargs["request"],
        "claim": kwargs["claim"],
        "lossless_context_package": kwargs["lossless_context_package"],
        "control_context": kwargs["control_context"],
        "current_root_codex_only": True,
        "complete_packet_exactly_once": True,
        "executable": False,
        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD: PRESENTATION_DIGEST,
    }


def _persist_dynamic_agent_anchor(
    *,
    store: LocalV32DynamicStore,
    checkpoint: dict,
    run_id: str,
    predecessor: dict,
    permit: dict,
    packet: dict,
) -> tuple[dict, dict, dict]:
    current = dict(checkpoint)
    documents = (
        ("supervisor_checkpoint", predecessor),
        ("supervisor_permit", permit),
        ("proposal_packet", packet),
    )
    for index, (role, document) in enumerate(documents, start=1):
        current = dict(
            _dynamic_writer(store).persist_verified_artifact(
                run_id=run_id,
                cycle_index=1,
                role=role,
                relative_ref=(
                    f"{DYNAMIC_STORE_ROOT}/cycles/0001/test/"
                    f"{index:02d}-{role}.json"
                ),
                document=document,
                expected_checkpoint_digest=current[
                    DYNAMIC_CHECKPOINT_DIGEST_FIELD
                ],
                recorded_at="2026-08-07T00:15:20Z",
            )
        )
    packet_binding = next(
        row
        for row in current["artifact_bindings"]
        if row["cycle_index"] == 1 and row["role"] == "proposal_packet"
    )
    public_packet_binding = {
        field: packet_binding[field]
        for field in (
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        )
    }
    context = build_v32_agent_input_context_v1(
        agent_stage="PROPOSAL",
        canonical_packet=packet,
        canonical_packet_binding=public_packet_binding,
        created_at="2026-08-07T00:15:30Z",
    )
    current = dict(
        _dynamic_writer(store).persist_verified_artifact(
            run_id=run_id,
            cycle_index=1,
            role="proposal_input",
            relative_ref=(
                f"{DYNAMIC_STORE_ROOT}/cycles/0001/test/"
                "04-proposal_input.json"
            ),
            document=context,
            expected_checkpoint_digest=current[
                DYNAMIC_CHECKPOINT_DIGEST_FIELD
            ],
            recorded_at=context["created_at"],
        )
    )
    input_binding = next(
        row
        for row in current["artifact_bindings"]
        if row["cycle_index"] == 1 and row["role"] == "proposal_input"
    )
    public_input_binding = {
        field: input_binding[field]
        for field in (
            "relative_ref",
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        )
    }
    return current, public_input_binding, context


def _prepare_real_proposal_request(
    *,
    project: Path,
    permit_decision_at: str = "2026-08-07T00:15:00Z",
    use_non_owning_request_binding: bool = False,
) -> dict:
    fixture = _full_fixture()
    packet = fixture["proposal_context"]["canonical_packet"]
    run_id = str(packet["run_id"])
    run_root = project / ".runtime" / "theory-paper-v32" / "runs" / run_id
    run_root.mkdir(parents=True)

    dynamic_store = LocalV32DynamicStore(run_root)
    dynamic_initial = dynamic_store.initialize_checkpoint(
        run_id=run_id,
        experiment_contract_digest=CONTRACT_DIGEST,
        active_authority_digest=AUTHORITY_DIGEST,
        created_at="2026-08-07T00:14:00Z",
    )
    outcome_store = LocalV32OutcomeTickStore(run_root)
    outcome_checkpoint = outcome_store.initialize_checkpoint(
        run_id=run_id, created_at="2026-08-07T00:14:00Z"
    )
    predecessor = build_v32_tick_supervisor_checkpoint(
        run_id=run_id,
        experiment_contract_digest=CONTRACT_DIGEST,
        active_authority_digest=AUTHORITY_DIGEST,
        research_checkpoint_digest=dynamic_initial[
            DYNAMIC_CHECKPOINT_DIGEST_FIELD
        ],
        outcome_checkpoint_digest=outcome_checkpoint["checkpoint_digest"],
        timeframe_cache_digest=TIMEFRAME_DIGEST,
        created_at="2026-08-07T00:14:00Z",
    )
    permit = build_v32_analysis_tick_permit(
        checkpoint=predecessor,
        schedule_sets=[],
        analysis_decision_at=permit_decision_at,
        issued_at="2026-08-07T00:15:01Z",
        research_checkpoint_digest=dynamic_initial[
            DYNAMIC_CHECKPOINT_DIGEST_FIELD
        ],
        outcome_checkpoint_digest=outcome_checkpoint["checkpoint_digest"],
        timeframe_cache_digest=TIMEFRAME_DIGEST,
        prior_dynamic_state_digest=None,
    )
    supervisor_store = LocalV32TickSupervisorStore(run_root)
    initialized = supervisor_store.initialize_checkpoint(checkpoint=predecessor)
    opened = supervisor_store.open_permit(
        permit=permit,
        schedule_sets=[],
        expected_checkpoint_digest=initialized[
            "tick_supervisor_checkpoint_digest"
        ],
        opened_at=permit["issued_at"],
    )
    dynamic_open = dynamic_store.open_cycle(
        run_id=run_id,
        cycle_index=1,
        expected_checkpoint_digest=dynamic_initial[
            DYNAMIC_CHECKPOINT_DIGEST_FIELD
        ],
        opened_at=permit["issued_at"],
    )
    dynamic_checkpoint, owning_binding, context = _persist_dynamic_agent_anchor(
        store=dynamic_store,
        checkpoint=dict(dynamic_open),
        run_id=run_id,
        predecessor=predecessor,
        permit=permit,
        packet=packet,
    )
    mailbox = LocalV32CurrentRootAgentMailbox(run_root)
    mailbox_checkpoint = mailbox.initialize_checkpoint(
        mailbox_id=f"mailbox::{run_id}::1",
        run_id=run_id,
        cycle_index=1,
        created_at=context["created_at"],
    )
    queued = mailbox.enqueue_request(
        run_id=run_id,
        cycle_index=1,
        expected_checkpoint_digest=mailbox_checkpoint[
            MAILBOX_CHECKPOINT_DIGEST_FIELD
        ],
        agent_input_context=context,
        agent_input_context_binding=(
            build_v32_embedded_document_binding_v1(
                relative_ref="artifacts/non-owning-proposal-input.json",
                document=context,
                schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
                digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
            )
            if use_non_owning_request_binding
            else owning_binding
        ),
        reserved_at="2026-08-07T00:15:40Z",
    )
    return {
        "fixture": fixture,
        "context": context,
        "run_id": run_id,
        "run_root": run_root,
        "dynamic_store": dynamic_store,
        "dynamic_checkpoint": dynamic_checkpoint,
        "outcome_store": outcome_store,
        "supervisor_store": supervisor_store,
        "opened": opened,
        "permit": permit,
        "mailbox": mailbox,
        "queued": queued,
        "owning_binding": owning_binding,
    }


def _temporal_agent_mocks(*, entry_kind: str) -> dict:
    checkpoint, permit, predecessor = _active_analysis_boundary()
    supervisor = mock.Mock()
    supervisor.load_checkpoint.return_value = checkpoint
    supervisor.load_permit.return_value = permit
    supervisor.load_checkpoint_by_digest.return_value = predecessor
    outcome = mock.Mock()
    outcome.load_schedule_sets.return_value = []
    mailbox = mock.Mock()
    if entry_kind == "CLAIM":
        pending = _pending_request(stage="PROPOSAL", status="REQUESTED")
        claim = {"claim": "bound"}
        before = {
            "stage_status": "REQUESTED",
            "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
            "request": pending["request"],
            "canonical_packet_original": {},
            "lossless_context_package": None,
        }
        after = {
            **before,
            "stage_status": "CLAIMED",
            "checkpoint_digest": MAILBOX_AFTER_DIGEST,
            "claim": claim,
            "lossless_context_package": {},
            "ordered_agent_input_delivery_units": [],
        }
        mailbox.claim_request.return_value = {
            "checkpoint": {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_AFTER_DIGEST
            },
            "request": pending["request"],
            "claim": claim,
        }
        write = mailbox.claim_request
        mailbox.load_checkpoint.return_value = {
            MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
        }
    else:
        pending = _pending_request(stage="SELECTION", status="CLAIMED")
        before = {
            "stage_status": "CLAIMED",
            "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
            "request": pending["request"],
            "claim": pending["claim"],
        }
        delivery = {"delivery": "bound"}
        receipt = {"receipt": "bound"}
        after = {
            **before,
            "stage_status": "DELIVERED",
            "checkpoint_digest": MAILBOX_AFTER_DIGEST,
            "agent_delivery": delivery,
            "delivery_receipt": receipt,
        }
        mailbox.submit_delivery.return_value = {
            "checkpoint": {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_AFTER_DIGEST
            },
            "request": pending["request"],
            "claim": pending["claim"],
            "agent_delivery": delivery,
            "delivery_receipt": receipt,
        }
        write = mailbox.submit_delivery
        mailbox.load_checkpoint.return_value = {
            MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
        }
        before["lossless_context_package"] = None
    mailbox.next_pending_request.return_value = pending
    mailbox.load_stage_chain.side_effect = [before, after]
    return {
        "supervisor": supervisor,
        "outcome": outcome,
        "mailbox": mailbox,
        "write": write,
        "preview_claim": claim if entry_kind == "CLAIM" else None,
        "preview_checkpoint": (
            {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_AFTER_DIGEST
            }
            if entry_kind == "CLAIM"
            else None
        ),
    }


class V32TargetWakeCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._real_template_temp: tempfile.TemporaryDirectory[str] | None = None
        cls._real_template: dict | None = None

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._real_template_temp is not None:
            cls._real_template_temp.cleanup()
        super().tearDownClass()

    @classmethod
    def _prepare_real_request(
        cls,
        *,
        project: Path,
        permit_decision_at: str = "2026-08-07T00:15:00Z",
        use_non_owning_request_binding: bool = False,
    ) -> dict:
        if (
            permit_decision_at != "2026-08-07T00:15:00Z"
            or use_non_owning_request_binding
        ):
            return _prepare_real_proposal_request(
                project=project,
                permit_decision_at=permit_decision_at,
                use_non_owning_request_binding=use_non_owning_request_binding,
            )

        if cls._real_template is None:
            cls._real_template_temp = tempfile.TemporaryDirectory()
            cls._real_template = _prepare_real_proposal_request(
                project=Path(cls._real_template_temp.name)
            )
        template = cls._real_template
        run_id = str(template["run_id"])
        run_root = (
            project / ".runtime" / "theory-paper-v32" / "runs" / run_id
        )
        run_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template["run_root"], run_root)
        prepared = {
            key: deepcopy(template[key])
            for key in (
                "fixture",
                "context",
                "run_id",
                "dynamic_checkpoint",
                "opened",
                "permit",
                "queued",
                "owning_binding",
            )
        }
        prepared.update(
            {
                "run_root": run_root,
                "dynamic_store": LocalV32DynamicStore(run_root),
                "outcome_store": LocalV32OutcomeTickStore(run_root),
                "supervisor_store": LocalV32TickSupervisorStore(run_root),
                "mailbox": LocalV32CurrentRootAgentMailbox(run_root),
            }
        )
        return prepared

    def _assert_temporal_agent_failure(
        self,
        *,
        entry_kind: str,
        clock_values: list[str],
        expected_code: str,
        expected_write_count: int,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            dependencies = _temporal_agent_mocks(entry_kind=entry_kind)
            anchor = {"anchor": "stable"}
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=dependencies["supervisor"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=dependencies["outcome"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=dependencies["mailbox"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(clock_values),
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_root_agent_mailbox_claim_v1",
                    return_value=dependencies["preview_claim"],
                ),
                mock.patch.object(
                    composition,
                    "claim_v32_current_root_agent_mailbox_request_v1",
                    return_value=dependencies["preview_checkpoint"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    expected_code,
                ):
                    if entry_kind == "CLAIM":
                        composition.read_and_claim_v32_target_agent_request_v1(
                            project_root=project,
                            expected_run_id=RUN_ID,
                        )
                    else:
                        composition.submit_v32_target_agent_delivery_v1(
                            project_root=project,
                            expected_run_id=RUN_ID,
                            stage="SELECTION",
                            expected_request_digest=REQUEST_DIGEST,
                            expected_current_codex_presentation_digest=(
                                PRESENTATION_DIGEST
                            ),
                            payload_utf8='{"selected":"WAIT"}',
                        )
            self.assertEqual(
                dependencies["write"].call_count, expected_write_count
            )

    def _assert_agent_cas_has_no_postcheck(self, *, entry_kind: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            dependencies = _temporal_agent_mocks(entry_kind=entry_kind)
            anchor = {"anchor": "stable"}
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=dependencies["supervisor"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=dependencies["outcome"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=dependencies["mailbox"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    # Exactly two pre-CAS observations.  A legacy third,
                    # post-CAS read would exhaust this clock and fail the test.
                    return_value=_SequenceClock(
                        [
                            "2026-08-08T00:01:00Z",
                            "2026-08-08T00:01:01Z",
                        ]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_root_agent_mailbox_claim_v1",
                    return_value=dependencies["preview_claim"],
                ),
                mock.patch.object(
                    composition,
                    "claim_v32_current_root_agent_mailbox_request_v1",
                    return_value=dependencies["preview_checkpoint"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                if entry_kind == "CLAIM":
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=RUN_ID,
                    )
                else:
                    composition.submit_v32_target_agent_delivery_v1(
                        project_root=project,
                        expected_run_id=RUN_ID,
                        stage="SELECTION",
                        expected_request_digest=REQUEST_DIGEST,
                        expected_current_codex_presentation_digest=(
                            PRESENTATION_DIGEST
                        ),
                        payload_utf8='{"selected":"WAIT"}',
                    )
            self.assertEqual(dependencies["write"].call_count, 1)
            self.assertEqual(
                dependencies["mailbox"].load_stage_chain.call_count, 1
            )

    def test_public_signature_exposes_no_clock_document_or_adapter_injection(self) -> None:
        signatures = {
            "wake": (
                inspect.signature(composition.run_v32_target_wake_v1),
                ("project_root", "expected_run_id"),
            ),
            "claim": (
                inspect.signature(
                    composition.read_and_claim_v32_target_agent_request_v1
                ),
                ("project_root", "expected_run_id"),
            ),
            "submit": (
                inspect.signature(composition.submit_v32_target_agent_delivery_v1),
                (
                    "project_root",
                    "expected_run_id",
                    "stage",
                    "expected_request_digest",
                    "expected_current_codex_presentation_digest",
                    "payload_utf8",
                ),
            ),
        }
        for signature, expected in signatures.values():
            self.assertEqual(tuple(signature.parameters), expected)
            self.assertTrue(
                all(
                    parameter.kind is inspect.Parameter.KEYWORD_ONLY
                    for parameter in signature.parameters.values()
                )
            )
        forbidden = {
            "clock",
            "documents",
            "authority",
            "adapter",
            "transport",
            "wake_runner",
            "analysis_port",
            "outcome_port",
        }
        for signature, _ in signatures.values():
            self.assertFalse(forbidden.intersection(signature.parameters))

    def test_target_wake_passes_agent_envelope_through_by_identity(self) -> None:
        envelope = {
            "schema_id": composition.CURRENT_CODEX_PRESENTATION_SCHEMA_ID,
            "sentinel": "exact-object",
        }
        with mock.patch.object(
            composition,
            "verify_v32_current_codex_presentation_envelope_v1",
        ) as verify:
            self.assertIs(
                composition._current_codex_presentation_from_routed_wake(
                    envelope
                ),
                envelope,
            )
            wrapper = {
                "runtime_status": "AWAITING_CURRENT_ROOT_CODEX",
                "external_action_request": envelope,
            }
            self.assertIs(
                composition._current_codex_presentation_from_routed_wake(
                    wrapper
                ),
                envelope,
            )
            self.assertIsNone(
                composition._current_codex_presentation_from_routed_wake(
                    {"runtime_status": "NOT_DUE"}
                )
            )
        self.assertEqual(verify.call_args_list, [mock.call(envelope)] * 2)

    def test_expired_agent_entry_rejects_without_mutating_mailbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            dependencies = _temporal_agent_mocks(entry_kind="CLAIM")
            deadline = "2026-08-08T00:11:02Z"
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=dependencies["supervisor"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=dependencies["outcome"],
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=dependencies["mailbox"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_FixedClock(deadline),
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_RUNTIME_ACTIVE_ANALYSIS_AGENT_WINDOW_EXPIRED",
                ):
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=RUN_ID,
                    )
            dependencies["mailbox"].claim_request.assert_not_called()
            dependencies["supervisor"].fail_closed.assert_not_called()

    def test_pre_cas_deadline_boundary_writes_nothing_for_claim_and_submit(
        self,
    ) -> None:
        deadline = "2026-08-08T00:11:02Z"
        before = "2026-08-08T00:11:01.999999Z"
        for entry_kind in ("CLAIM", "SUBMIT"):
            with self.subTest(entry_kind=entry_kind):
                self._assert_temporal_agent_failure(
                    entry_kind=entry_kind,
                    clock_values=[before, deadline],
                    expected_code=(
                        "V32_RUNTIME_ACTIVE_ANALYSIS_AGENT_WINDOW_EXPIRED"
                    ),
                    expected_write_count=0,
                )

    def test_successful_agent_cas_has_no_post_cas_clock_or_external_reread(
        self,
    ) -> None:
        for entry_kind in ("CLAIM", "SUBMIT"):
            with self.subTest(entry_kind=entry_kind):
                self._assert_agent_cas_has_no_postcheck(
                    entry_kind=entry_kind
                )

    def test_pre_cas_clock_regression_writes_nothing_for_claim_and_submit(
        self,
    ) -> None:
        for entry_kind in ("CLAIM", "SUBMIT"):
            with self.subTest(entry_kind=entry_kind):
                self._assert_temporal_agent_failure(
                    entry_kind=entry_kind,
                    clock_values=[
                        "2026-08-08T00:01:00Z",
                        "2026-08-08T00:00:59Z",
                    ],
                    expected_code="V32_TARGET_AGENT_CLOCK_REGRESSION",
                    expected_write_count=0,
                )

    def test_claim_and_wake_share_one_per_run_exclusion_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            claim_entered = threading.Event()
            release_claim = threading.Event()
            wake_entered = threading.Event()
            failures: list[BaseException] = []

            def claim_under_guard(**kwargs):
                del kwargs
                claim_entered.set()
                if not release_claim.wait(timeout=2):
                    raise AssertionError("test did not release guarded claim")
                return {"boundary": "claim"}

            def wake_under_guard(**kwargs):
                del kwargs
                wake_entered.set()
                return {"boundary": "wake"}

            def invoke_claim() -> None:
                try:
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project, expected_run_id=RUN_ID
                    )
                except BaseException as exc:  # pragma: no cover - assertion path
                    failures.append(exc)

            def invoke_wake() -> None:
                try:
                    composition.run_v32_target_wake_v1(
                        project_root=project, expected_run_id=RUN_ID
                    )
                except BaseException as exc:  # pragma: no cover - assertion path
                    failures.append(exc)

            with (
                mock.patch.object(
                    composition,
                    "_load_verified_target_context",
                    return_value=(project.resolve(), _fake_replay(run_root), run_root),
                ),
                mock.patch.object(
                    composition,
                    "_read_and_claim_v32_target_agent_request_under_guard",
                    side_effect=claim_under_guard,
                ),
                mock.patch.object(
                    composition,
                    "_run_v32_target_wake_under_guard",
                    side_effect=wake_under_guard,
                ),
            ):
                claim_thread = threading.Thread(target=invoke_claim)
                wake_thread = threading.Thread(target=invoke_wake)
                claim_thread.start()
                self.assertTrue(claim_entered.wait(timeout=1))
                wake_thread.start()
                self.assertFalse(wake_entered.wait(timeout=0.1))
                release_claim.set()
                claim_thread.join(timeout=2)
                wake_thread.join(timeout=2)

            self.assertFalse(claim_thread.is_alive())
            self.assertFalse(wake_thread.is_alive())
            self.assertTrue(wake_entered.is_set())
            self.assertEqual(failures, [])

    def test_target_claim_integrates_real_supervisor_outcome_and_mailbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(project=project)
            run_id = prepared["run_id"]
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(prepared["run_root"], run_id),
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:50Z",
                            "2026-08-07T00:15:51Z",
                            "2026-08-07T00:15:52Z",
                        ]
                    ),
                ),
            ):
                result = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )

            pending = prepared["mailbox"].next_pending_request(
                run_id=run_id, cycle_index=1
            )
            self.assertEqual(pending["stage_status"], "CLAIMED")
            self.assertEqual(
                result["request"], prepared["queued"]["request"]
            )
            self.assertEqual(
                result["control_context"]["supervisor_checkpoint_digest"],
                prepared["opened"]["tick_supervisor_checkpoint_digest"],
            )
            self.assertEqual(
                prepared["outcome_store"].load_schedule_sets(run_id=run_id), []
            )
            self.assertEqual(
                result["control_context"]["agent_boundary_at"],
                "2026-08-07T00:15:51Z",
            )
            verify_v32_current_codex_presentation_envelope_v1(result)
            self.assertLessEqual(
                len(canonical_bytes(result)),
                MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
            )
            packet = result["request"]["agent_input_context"][
                "canonical_packet"
            ]
            self.assertEqual(
                canonical_bytes(result).count(canonical_bytes(packet)), 1
            )

    def test_target_claim_response_loss_replays_identical_envelope_without_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(project=project)
            run_id = prepared["run_id"]
            replay = _fake_replay(prepared["run_root"], run_id)
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:50Z",
                            "2026-08-07T00:15:51Z",
                        ]
                    ),
                ),
            ):
                first = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )
            checkpoint_before = prepared["mailbox"].load_checkpoint(
                run_id=run_id, cycle_index=1
            )
            json_before = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )

            # Simulate loss of the first response after the claim CAS.  The
            # next call must use the unique historical CLAIMED snapshot and
            # original claimed_at; allocating a new clock would be attempt two.
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    side_effect=AssertionError(
                        "CLAIMED replay must not allocate a new clock"
                    ),
                ),
            ):
                second = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )

            checkpoint_after = prepared["mailbox"].load_checkpoint(
                run_id=run_id, cycle_index=1
            )
            json_after = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )
            self.assertEqual(first, second)
            self.assertEqual(checkpoint_before, checkpoint_after)
            self.assertEqual(json_before, json_after)
            self.assertEqual(
                "CLAIMED",
                prepared["mailbox"].next_pending_request(
                    run_id=run_id, cycle_index=1
                )["stage_status"],
            )
            verify_v32_current_codex_presentation_envelope_v1(second)

    def test_target_wake_replays_lost_claim_envelope_accepted_by_submit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(project=project)
            run_id = prepared["run_id"]
            replay = _fake_replay(prepared["run_root"], run_id)
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:50Z",
                            "2026-08-07T00:15:51Z",
                        ]
                    ),
                ),
            ):
                lost = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )

            files_after_lost_claim = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )
            qualified_revision_store = mock.Mock()
            qualified_revision_store.load_audit_bundle.return_value = {
                "qualification_audit": "present"
            }
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "_load_verified_analysis_materials",
                    return_value={
                        "theory_semantic_document": {},
                        "theory_semantic_document_binding": {},
                        "support_documents": {},
                        "support_bindings": {},
                    },
                ),
                mock.patch.object(
                    composition,
                    "LocalV32AnalysisMaterialAdapter",
                    return_value=_UnusedMaterial(),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32AuthorizedRevisionStore",
                    return_value=qualified_revision_store,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32BoundaryAuditLane",
                    return_value=mock.Mock(),
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_FixedClock("2026-08-07T00:15:52Z"),
                ),
            ):
                recovered = composition.run_v32_target_wake_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )

            self.assertEqual(lost, recovered)
            self.assertEqual(
                files_after_lost_claim,
                tuple(
                    (
                        path.relative_to(prepared["run_root"]).as_posix(),
                        path.read_bytes(),
                    )
                    for path in sorted(prepared["run_root"].rglob("*.json"))
                ),
            )
            self.assertEqual(
                recovered["control_context"]["presentation_kind"],
                "TARGET_AGENT_CLAIM",
            )
            generic_claimed = (
                composition.build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=recovered["mailbox_checkpoint"],
                    request=recovered["request"],
                    claim=recovered["claim"],
                    lossless_context_package=recovered[
                        "lossless_context_package"
                    ],
                    control_context={
                        "presentation_kind": (
                            "PROSPECTIVE_PENDING_AGENT_ACTION"
                        ),
                        "request_kind": (
                            "CURRENT_ROOT_CODEX_AGENT_ACTION_REQUIRED"
                        ),
                        "stage": "PROPOSAL",
                        "stage_status": "CLAIMED",
                        "next_action": (
                            "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
                        ),
                    },
                )
            )
            before_wrong_digest = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:53Z",
                            "2026-08-07T00:15:54Z",
                        ]
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_TARGET_AGENT_PRESENTATION_DIGEST_DRIFT",
                ):
                    composition.submit_v32_target_agent_delivery_v1(
                        project_root=project,
                        expected_run_id=run_id,
                        stage="PROPOSAL",
                        expected_request_digest=generic_claimed["request"][
                            "current_root_agent_mailbox_request_digest"
                        ],
                        expected_current_codex_presentation_digest=(
                            generic_claimed[
                                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                            ]
                        ),
                        payload_utf8=prepared["fixture"][
                            "proposal_payload"
                        ],
                    )
            self.assertEqual(
                before_wrong_digest,
                tuple(
                    (
                        path.relative_to(prepared["run_root"]).as_posix(),
                        path.read_bytes(),
                    )
                    for path in sorted(prepared["run_root"].rglob("*.json"))
                ),
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:53Z",
                            "2026-08-07T00:15:54Z",
                        ]
                    ),
                ),
            ):
                delivered = composition.submit_v32_target_agent_delivery_v1(
                    project_root=project,
                    expected_run_id=run_id,
                    stage="PROPOSAL",
                    expected_request_digest=recovered["request"][
                        "current_root_agent_mailbox_request_digest"
                    ],
                    expected_current_codex_presentation_digest=recovered[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ],
                    payload_utf8=prepared["fixture"]["proposal_payload"],
                )
            self.assertEqual(
                prepared["mailbox"].next_pending_request(
                    run_id=run_id, cycle_index=1
                )["stage_status"],
                "DELIVERED",
            )
            self.assertEqual(
                delivered["delivery_receipt"][
                    "current_codex_presentation_digest"
                ],
                recovered[CURRENT_CODEX_PRESENTATION_DIGEST_FIELD],
            )

    def test_target_delivery_response_loss_replays_first_delivery_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(project=project)
            run_id = prepared["run_id"]
            replay = _fake_replay(prepared["run_root"], run_id)
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:50Z",
                            "2026-08-07T00:15:51Z",
                        ]
                    ),
                ),
            ):
                claim = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=run_id,
                )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-07T00:15:52Z",
                            "2026-08-07T00:15:53Z",
                        ]
                    ),
                ),
            ):
                first = composition.submit_v32_target_agent_delivery_v1(
                    project_root=project,
                    expected_run_id=run_id,
                    stage="PROPOSAL",
                    expected_request_digest=claim["request"][
                        "current_root_agent_mailbox_request_digest"
                    ],
                    expected_current_codex_presentation_digest=claim[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ],
                    payload_utf8=prepared["fixture"]["proposal_payload"],
                )
            json_before = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=replay,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    side_effect=AssertionError(
                        "DELIVERED replay must reuse the first delivered_at"
                    ),
                ),
            ):
                replayed = composition.submit_v32_target_agent_delivery_v1(
                    project_root=project,
                    expected_run_id=run_id,
                    stage="PROPOSAL",
                    expected_request_digest=claim["request"][
                        "current_root_agent_mailbox_request_digest"
                    ],
                    expected_current_codex_presentation_digest=claim[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ],
                    payload_utf8="different retry payload must not overwrite",
                )
            json_after = tuple(
                (path.relative_to(prepared["run_root"]).as_posix(), path.read_bytes())
                for path in sorted(prepared["run_root"].rglob("*.json"))
            )
            self.assertEqual(first, replayed)
            self.assertEqual(json_before, json_after)
            self.assertEqual(
                "2026-08-07T00:15:53Z",
                replayed["agent_delivery"]["delivered_at"],
            )
            self.assertEqual(
                prepared["fixture"]["proposal_payload"],
                replayed["agent_delivery"]["payload_utf8"],
            )

    def test_target_delivery_recovers_both_pre_cas_partial_tails_without_new_clock(
        self,
    ) -> None:
        for crash_kind in ("DELIVERY_ONLY", "DELIVERY_AND_RECEIPT"):
            with self.subTest(crash_kind=crash_kind), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepared = self._prepare_real_request(project=project)
                run_id = prepared["run_id"]
                replay = _fake_replay(prepared["run_root"], run_id)
                with (
                    mock.patch.object(
                        composition,
                        "replay_v32_target_run_from_current_authority_v1",
                        return_value=replay,
                    ),
                    mock.patch.object(
                        composition,
                        "build_v32_system_clock_v1",
                        return_value=_SequenceClock(
                            [
                                "2026-08-07T00:15:50Z",
                                "2026-08-07T00:15:51Z",
                            ]
                        ),
                    ),
                ):
                    claim = composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=run_id,
                    )

                original_write = LocalV32CurrentRootAgentMailbox._write_document

                def crash_before_receipt(store, **kwargs):
                    if str(kwargs["relative_ref"]).endswith(
                        "delivery-receipt.json"
                    ):
                        raise V32CurrentRootAgentMailboxStoreError(
                            "injected-delivery-only-crash"
                        )
                    return original_write(store, **kwargs)

                def crash_before_checkpoint_cas(store, **kwargs):
                    del store, kwargs
                    raise V32CurrentRootAgentMailboxStoreError(
                        "injected-delivery-receipt-pre-cas-crash"
                    )

                crash_patch = (
                    mock.patch.object(
                        LocalV32CurrentRootAgentMailbox,
                        "_write_document",
                        new=crash_before_receipt,
                    )
                    if crash_kind == "DELIVERY_ONLY"
                    else mock.patch.object(
                        LocalV32CurrentRootAgentMailbox,
                        "_commit",
                        new=crash_before_checkpoint_cas,
                    )
                )
                with (
                    mock.patch.object(
                        composition,
                        "replay_v32_target_run_from_current_authority_v1",
                        return_value=replay,
                    ),
                    mock.patch.object(
                        composition,
                        "build_v32_system_clock_v1",
                        return_value=_SequenceClock(
                            [
                                "2026-08-07T00:15:52Z",
                                "2026-08-07T00:15:53Z",
                            ]
                        ),
                    ),
                    crash_patch,
                    self.assertRaises(V32CurrentRootAgentMailboxStoreError),
                ):
                    composition.submit_v32_target_agent_delivery_v1(
                        project_root=project,
                        expected_run_id=run_id,
                        stage="PROPOSAL",
                        expected_request_digest=claim["request"][
                            "current_root_agent_mailbox_request_digest"
                        ],
                        expected_current_codex_presentation_digest=claim[
                            CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                        ],
                        payload_utf8=prepared["fixture"]["proposal_payload"],
                    )

                delivery_path = (
                    prepared["run_root"]
                    / "v32-current-root-agent-mailbox-v1"
                    / "cycles/0001/proposal/agent-delivery.json"
                )
                receipt_path = delivery_path.with_name("delivery-receipt.json")
                first_delivery_bytes = delivery_path.read_bytes()
                first_receipt_bytes = (
                    receipt_path.read_bytes() if receipt_path.is_file() else None
                )
                checkpoint_before = prepared["mailbox"].load_checkpoint(
                    run_id=run_id, cycle_index=1
                )
                self.assertEqual(
                    "CLAIMED",
                    checkpoint_before["stage_states"]["PROPOSAL"]["status"],
                )

                with (
                    mock.patch.object(
                        composition,
                        "replay_v32_target_run_from_current_authority_v1",
                        return_value=replay,
                    ),
                    mock.patch.object(
                        composition,
                        "build_v32_system_clock_v1",
                        side_effect=AssertionError(
                            "partial delivery recovery must not allocate a new clock"
                        ),
                    ),
                ):
                    recovered = composition.submit_v32_target_agent_delivery_v1(
                        project_root=project,
                        expected_run_id=run_id,
                        stage="PROPOSAL",
                        expected_request_digest=claim["request"][
                            "current_root_agent_mailbox_request_digest"
                        ],
                        expected_current_codex_presentation_digest=claim[
                            CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                        ],
                        payload_utf8="retry payload must never replace first delivery",
                    )

                self.assertEqual(first_delivery_bytes, delivery_path.read_bytes())
                if first_receipt_bytes is not None:
                    self.assertEqual(first_receipt_bytes, receipt_path.read_bytes())
                self.assertEqual(
                    "2026-08-07T00:15:53Z",
                    recovered["agent_delivery"]["delivered_at"],
                )
                self.assertEqual(
                    prepared["fixture"]["proposal_payload"],
                    recovered["agent_delivery"]["payload_utf8"],
                )
                self.assertEqual(
                    claim[CURRENT_CODEX_PRESENTATION_DIGEST_FIELD],
                    recovered["delivery_receipt"][
                        "current_codex_presentation_digest"
                    ],
                )
                self.assertEqual(
                    "DELIVERED",
                    recovered["checkpoint"]["stage_states"]["PROPOSAL"][
                        "status"
                    ],
                )

    def test_real_claim_rejects_packet_decision_stale_to_active_permit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(
                project=project,
                permit_decision_at="2026-08-07T00:14:59Z",
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(
                        prepared["run_root"], prepared["run_id"]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_FixedClock("2026-08-07T00:15:50Z"),
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_TARGET_AGENT_REQUEST_NOT_BOUND_TO_ACTIVE_PERMIT",
                ):
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=prepared["run_id"],
                    )
            pending = prepared["mailbox"].next_pending_request(
                run_id=prepared["run_id"], cycle_index=1
            )
            self.assertEqual(pending["stage_status"], "REQUESTED")

    def test_real_claim_rejects_non_owning_dynamic_input_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepared = self._prepare_real_request(
                project=project,
                use_non_owning_request_binding=True,
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(
                        prepared["run_root"], prepared["run_id"]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_FixedClock("2026-08-07T00:15:50Z"),
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_TARGET_AGENT_REQUEST_NOT_BOUND_TO_ACTIVE_PERMIT",
                ):
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=prepared["run_id"],
                    )
            pending = prepared["mailbox"].next_pending_request(
                run_id=prepared["run_id"], cycle_index=1
            )
            self.assertEqual(pending["stage_status"], "REQUESTED")

    def test_target_agent_claim_replays_authority_and_binds_active_permit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            supervisor_checkpoint, permit, predecessor = (
                _active_analysis_boundary()
            )
            supervisor = mock.Mock()
            supervisor.load_checkpoint.return_value = supervisor_checkpoint
            supervisor.load_permit.return_value = permit
            supervisor.load_checkpoint_by_digest.return_value = predecessor
            outcome = mock.Mock()
            outcome.load_schedule_sets.return_value = []
            pending = _pending_request(stage="PROPOSAL", status="REQUESTED")
            claim = {"claim": "bound"}
            claimed = {
                "checkpoint": {
                    "current_root_agent_mailbox_checkpoint_digest": (
                        MAILBOX_AFTER_DIGEST
                    )
                },
                "request": pending["request"],
                "claim": claim,
            }
            mailbox = mock.Mock()
            mailbox.next_pending_request.return_value = pending
            mailbox.claim_request.return_value = claimed
            mailbox.load_checkpoint.return_value = {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
            }
            chain_before = {
                "stage_status": "REQUESTED",
                "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
                "request": pending["request"],
                "canonical_packet_original": {"packet": "complete"},
                "lossless_context_package": None,
            }
            chain_after = {
                "stage_status": "CLAIMED",
                "checkpoint_digest": MAILBOX_AFTER_DIGEST,
                "request": pending["request"],
                "claim": claim,
                "canonical_packet_original": {"packet": "complete"},
                "lossless_context_package": {"context": "lossless"},
                "ordered_agent_input_delivery_units": [{"unit": 1}],
            }
            mailbox.load_stage_chain.side_effect = [chain_before, chain_after]
            events: list[str] = []
            anchor = {"anchor": "stable"}

            def replay(**kwargs):
                del kwargs
                events.append("authority-replay")
                return _fake_replay(run_root)

            def build_supervisor(*args, **kwargs):
                del args, kwargs
                events.append("supervisor")
                return supervisor

            def build_mailbox(*args, **kwargs):
                del args, kwargs
                events.append("mailbox")
                return mailbox

            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    side_effect=replay,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    side_effect=build_supervisor,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    side_effect=build_mailbox,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=outcome,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-08T00:01:00Z",
                            "2026-08-08T00:01:01Z",
                        ]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition, "V32OkxPublicBundleTransport"
                ) as source_transport,
                mock.patch.object(
                    composition, "V32OkxPublicMarkCaptureAdapter"
                ) as outcome_adapter,
                mock.patch.object(
                    composition,
                    "build_v32_current_root_agent_mailbox_claim_v1",
                    return_value=claim,
                ),
                mock.patch.object(
                    composition,
                    "claim_v32_current_root_agent_mailbox_request_v1",
                    return_value=claimed["checkpoint"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                result = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=RUN_ID,
                )

            self.assertEqual(events, ["authority-replay", "supervisor", "mailbox"])
            mailbox.claim_request.assert_called_once_with(
                run_id=RUN_ID,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=MAILBOX_BEFORE_DIGEST,
                claimed_at="2026-08-08T00:01:01Z",
            )
            self.assertEqual(
                result["control_context"]["active_analysis_permit_digest"],
                permit["tick_supervisor_permit_digest"],
            )
            self.assertEqual(
                result["control_context"]["supervisor_checkpoint_digest"],
                supervisor_checkpoint["tick_supervisor_checkpoint_digest"],
            )
            self.assertEqual(
                result["control_context"]["agent_boundary_at"],
                "2026-08-08T00:01:01Z",
            )
            self.assertEqual(supervisor.load_checkpoint.call_count, 5)
            self.assertEqual(supervisor.load_permit.call_count, 3)
            self.assertEqual(
                supervisor.load_checkpoint_by_digest.call_count, 2
            )
            self.assertEqual(outcome.load_schedule_sets.call_count, 2)
            source_transport.assert_not_called()
            outcome_adapter.assert_not_called()
            self.assertFalse(result["executable"])

    def test_target_claim_exactly_recovers_orphan_with_original_claim_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            supervisor_checkpoint, permit, predecessor = (
                _active_analysis_boundary()
            )
            supervisor = mock.Mock()
            supervisor.load_checkpoint.return_value = supervisor_checkpoint
            supervisor.load_permit.return_value = permit
            supervisor.load_checkpoint_by_digest.return_value = predecessor
            outcome = mock.Mock()
            outcome.load_schedule_sets.return_value = []
            pending = _pending_request(stage="PROPOSAL", status="REQUESTED")
            orphan_claim = {
                "claim": "first-immutable-bytes",
                "claimed_at": "2026-08-08T00:01:01Z",
            }
            pending["claim"] = orphan_claim
            chain = {
                "stage_status": "REQUESTED",
                "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
                "request": pending["request"],
                "claim": orphan_claim,
                "canonical_packet_original": {"packet": "complete"},
                "lossless_context_package": None,
            }
            preview_checkpoint = {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_AFTER_DIGEST
            }
            mailbox = mock.Mock()
            mailbox.next_pending_request.return_value = pending
            mailbox.load_stage_chain.return_value = chain
            mailbox.load_checkpoint.return_value = {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
            }
            mailbox.claim_request.return_value = {
                "checkpoint": preview_checkpoint,
                "request": pending["request"],
                "claim": orphan_claim,
            }
            clock = mock.Mock(
                side_effect=AssertionError(
                    "orphan tail recovery must not invent a new wall-clock boundary"
                )
            )
            anchor = {"anchor": "stable"}
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=supervisor,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=outcome,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=mailbox,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=clock,
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_root_agent_mailbox_claim_v1",
                ) as build_claim,
                mock.patch.object(
                    composition,
                    "claim_v32_current_root_agent_mailbox_request_v1",
                    return_value=preview_checkpoint,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                result = composition.read_and_claim_v32_target_agent_request_v1(
                    project_root=project,
                    expected_run_id=RUN_ID,
                )
            clock.assert_not_called()
            build_claim.assert_not_called()
            mailbox.claim_request.assert_called_once_with(
                run_id=RUN_ID,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=MAILBOX_BEFORE_DIGEST,
                claimed_at="2026-08-08T00:01:01Z",
            )
            self.assertEqual(result["claim"], orphan_claim)
            self.assertEqual(
                result["control_context"]["agent_boundary_at"],
                orphan_claim["claimed_at"],
            )

    def test_target_agent_submit_checks_request_and_replays_delivery_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            supervisor_checkpoint, permit, predecessor = (
                _active_analysis_boundary()
            )
            supervisor = mock.Mock()
            supervisor.load_checkpoint.return_value = supervisor_checkpoint
            supervisor.load_permit.return_value = permit
            supervisor.load_checkpoint_by_digest.return_value = predecessor
            outcome = mock.Mock()
            outcome.load_schedule_sets.return_value = []
            pending = _pending_request(stage="SELECTION", status="CLAIMED")
            delivery = {"delivery": "explicit"}
            receipt = {"receipt": "bound"}
            delivered = {
                "checkpoint": {
                    "current_root_agent_mailbox_checkpoint_digest": (
                        MAILBOX_AFTER_DIGEST
                    )
                },
                "request": pending["request"],
                "claim": pending["claim"],
                "agent_delivery": delivery,
                "delivery_receipt": receipt,
            }
            chain_before = {
                "stage_status": "CLAIMED",
                "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
                "request": pending["request"],
                "claim": pending["claim"],
                "lossless_context_package": None,
            }
            chain_after = {
                **chain_before,
                "stage_status": "DELIVERED",
                "checkpoint_digest": MAILBOX_AFTER_DIGEST,
                "agent_delivery": delivery,
                "delivery_receipt": receipt,
            }
            mailbox = mock.Mock()
            mailbox.next_pending_request.return_value = pending
            mailbox.load_stage_chain.side_effect = [chain_before, chain_after]
            mailbox.load_checkpoint.return_value = {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
            }
            mailbox.submit_delivery.return_value = delivered
            anchor = {"anchor": "stable"}
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ) as replay,
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=supervisor,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=mailbox,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=outcome,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-08T00:01:00Z",
                            "2026-08-08T00:01:01Z",
                        ]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                result = composition.submit_v32_target_agent_delivery_v1(
                    project_root=project,
                    expected_run_id=RUN_ID,
                    stage="SELECTION",
                    expected_request_digest=REQUEST_DIGEST,
                    expected_current_codex_presentation_digest=(
                        PRESENTATION_DIGEST
                    ),
                    payload_utf8='{"selected":"WAIT"}',
                )

            replay.assert_called_once_with(
                project_root=project.resolve(), expected_run_id=RUN_ID
            )
            mailbox.submit_delivery.assert_called_once_with(
                run_id=RUN_ID,
                cycle_index=1,
                stage="SELECTION",
                expected_checkpoint_digest=MAILBOX_BEFORE_DIGEST,
                current_codex_presentation_envelope=mock.ANY,
                expected_current_codex_presentation_digest=(
                    PRESENTATION_DIGEST
                ),
                delivered_at="2026-08-08T00:01:01Z",
                payload_utf8='{"selected":"WAIT"}',
            )
            self.assertEqual(result["agent_delivery"], delivery)
            self.assertEqual(result, delivered)
            self.assertEqual(supervisor.load_checkpoint.call_count, 5)
            self.assertEqual(supervisor.load_permit.call_count, 3)
            self.assertEqual(
                supervisor.load_checkpoint_by_digest.call_count, 2
            )
            self.assertEqual(outcome.load_schedule_sets.call_count, 2)

    def test_target_agent_entry_refuses_without_active_analysis_permit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            supervisor_checkpoint, _, _ = _active_analysis_boundary()
            supervisor_checkpoint["status"] = "READY"
            supervisor_checkpoint["active_permit_kind"] = None
            supervisor_checkpoint["active_permit_digest"] = None
            supervisor = mock.Mock()
            supervisor.load_checkpoint.return_value = supervisor_checkpoint
            mailbox_constructor = mock.Mock()
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ) as replay,
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=supervisor,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    mailbox_constructor,
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_TARGET_AGENT_ANALYSIS_PERMIT_REQUIRED",
                ):
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=RUN_ID,
                    )
            replay.assert_called_once()
            supervisor.load_permit.assert_not_called()
            mailbox_constructor.assert_not_called()

    def test_target_agent_claim_detects_supervisor_change_before_mailbox_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project / ".runtime" / "theory-paper-v32" / "runs" / RUN_ID
            )
            run_root.mkdir(parents=True)
            supervisor_checkpoint, permit, predecessor = (
                _active_analysis_boundary()
            )
            changed_checkpoint = open_v32_tick_supervisor_permit(
                checkpoint=predecessor,
                permit=permit,
                schedule_sets=[],
                updated_at="2026-08-08T00:00:03Z",
            )
            supervisor = mock.Mock()
            supervisor.load_checkpoint.side_effect = [
                supervisor_checkpoint,
                supervisor_checkpoint,
                supervisor_checkpoint,
                changed_checkpoint,
                changed_checkpoint,
            ]
            supervisor.load_permit.return_value = permit
            supervisor.load_checkpoint_by_digest.return_value = predecessor
            outcome = mock.Mock()
            outcome.load_schedule_sets.return_value = []
            pending = _pending_request(stage="PROPOSAL", status="REQUESTED")
            claim = {"claim": "bound"}
            mailbox = mock.Mock()
            mailbox.next_pending_request.return_value = pending
            claimed = {
                "checkpoint": {
                    "current_root_agent_mailbox_checkpoint_digest": (
                        MAILBOX_AFTER_DIGEST
                    )
                },
                "request": pending["request"],
                "claim": claim,
            }
            mailbox.claim_request.return_value = claimed
            mailbox.load_checkpoint.return_value = {
                MAILBOX_CHECKPOINT_DIGEST_FIELD: MAILBOX_BEFORE_DIGEST
            }
            chain_before = {
                "stage_status": "REQUESTED",
                "checkpoint_digest": MAILBOX_BEFORE_DIGEST,
                "request": pending["request"],
                "canonical_packet_original": {},
                "lossless_context_package": None,
            }
            chain_after = {
                "stage_status": "CLAIMED",
                "checkpoint_digest": MAILBOX_AFTER_DIGEST,
                "request": pending["request"],
                "claim": claim,
                "canonical_packet_original": {},
                "lossless_context_package": {},
                "ordered_agent_input_delivery_units": [],
            }
            mailbox.load_stage_chain.side_effect = [chain_before, chain_after]
            anchor = {"anchor": "stable"}
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "LocalV32TickSupervisorStore",
                    return_value=supervisor,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32CurrentRootAgentMailbox",
                    return_value=mailbox,
                ),
                mock.patch.object(
                    composition,
                    "LocalV32OutcomeTickStore",
                    return_value=outcome,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_system_clock_v1",
                    return_value=_SequenceClock(
                        [
                            "2026-08-08T00:01:00Z",
                            "2026-08-08T00:01:01Z",
                        ]
                    ),
                ),
                mock.patch.object(
                    composition,
                    "_verify_target_agent_request_anchor",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "_assert_target_agent_anchor_unchanged",
                    return_value=anchor,
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_root_agent_mailbox_claim_v1",
                    return_value=claim,
                ),
                mock.patch.object(
                    composition,
                    "claim_v32_current_root_agent_mailbox_request_v1",
                    return_value=claimed["checkpoint"],
                ),
                mock.patch.object(
                    composition,
                    "build_v32_current_codex_presentation_envelope_v1",
                    side_effect=_fake_presentation_preview,
                ),
            ):
                with self.assertRaisesRegex(
                    composition.V32TargetWakeCompositionError,
                    "V32_TARGET_AGENT_SUPERVISOR_BOUNDARY_CHANGED",
                ):
                    composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=RUN_ID,
                    )
            mailbox.claim_request.assert_not_called()

    def test_missing_qualification_audit_blocks_before_public_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project
                / ".runtime"
                / "theory-paper-v32"
                / "runs"
                / RUN_ID
            )
            run_root.mkdir(parents=True)
            policy = _policy()
            initialize_v32_prospective_runtime_v1(
                dynamic_store=LocalV32DynamicStore(run_root),
                outcome_store=LocalV32OutcomeTickStore(run_root),
                supervisor_store=LocalV32TickSupervisorStore(run_root),
                run_id=RUN_ID,
                experiment_contract_digest=CONTRACT_DIGEST,
                active_authority_digest=AUTHORITY_DIGEST,
                initial_timeframe_cache_digest=TIMEFRAME_DIGEST,
                cycle_audit_policy=policy,
                created_at=CREATED_AT,
            )
            source_network = mock.Mock(
                side_effect=AssertionError("source network must remain closed")
            )
            outcome_network = mock.Mock(
                side_effect=AssertionError("outcome network must remain closed")
            )
            with (
                mock.patch.object(
                    composition,
                    "replay_v32_target_run_from_current_authority_v1",
                    return_value=_fake_replay(run_root),
                ),
                mock.patch.object(
                    composition,
                    "_load_verified_analysis_materials",
                    return_value={
                        "theory_semantic_document": {},
                        "theory_semantic_document_binding": {},
                        "support_documents": {},
                        "support_bindings": {},
                    },
                ),
                mock.patch.object(
                    composition,
                    "LocalV32AnalysisMaterialAdapter",
                    return_value=_UnusedMaterial(),
                ),
                mock.patch(
                    "trade_system.theory_paper_v2.infrastructure."
                    "v32_public_source_collector."
                    "V32RawFirstOkxPublicBundleCollector.collect_and_qualify",
                    source_network,
                ),
                mock.patch(
                    "trade_system.theory_paper_v2.infrastructure."
                    "v32_okx_public_outcome_adapter."
                    "V32OkxPublicMarkCaptureAdapter.capture_public_mark",
                    outcome_network,
                ),
            ):
                with self.assertRaisesRegex(
                    V32ProspectiveRuntimeError,
                    "V32_RUNTIME_QUALIFICATION_AUDIT_REQUIRED_BEFORE_ANALYSIS",
                ):
                    composition.run_v32_target_wake_v1(
                        project_root=project, expected_run_id=RUN_ID
                    )
            source_network.assert_not_called()
            outcome_network.assert_not_called()

    def test_terminal_and_supervision_ports_are_fixed_into_router(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = (
                project
                / ".runtime"
                / "theory-paper-v32"
                / "runs"
                / RUN_ID
            )
            run_root.mkdir(parents=True)
            replay = _fake_replay(run_root)
            sentinels = {
                name: object()
                for name in (
                    "dynamic",
                    "outcome",
                    "supervisor",
                    "mailbox",
                    "source",
                    "admitted",
                    "revision",
                    "completion",
                    "audit",
                    "supervision",
                    "terminal",
                    "transport",
                    "collector",
                    "material",
                    "analysis",
                    "capture",
                    "outcome_lane",
                )
            }
            clock = _Clock()
            route = mock.Mock(
                return_value={"run_id": RUN_ID, "runtime_status": "NOT_DUE"}
            )
            source_store_constructor = mock.Mock(
                side_effect=[sentinels["source"], sentinels["admitted"]]
            )
            replacements = {
                "_load_verified_analysis_materials": {
                    "theory_semantic_document": {},
                    "theory_semantic_document_binding": {},
                    "support_documents": {},
                    "support_bindings": {},
                },
                "_active_authority_projection": {"active": "projection"},
                "build_v32_system_clock_v1": clock,
                "LocalV32DynamicStore": sentinels["dynamic"],
                "LocalV32OutcomeTickStore": sentinels["outcome"],
                "LocalV32TickSupervisorStore": sentinels["supervisor"],
                "LocalV32CurrentRootAgentMailbox": sentinels["mailbox"],
                "LocalV32AuthorizedRevisionStore": sentinels["revision"],
                "LocalV32CycleAuditCompletionStore": sentinels["completion"],
                "LocalV32BoundaryAuditLane": sentinels["audit"],
                "LocalV32RecoverySupervisionStore": sentinels["supervision"],
                "LocalV32TerminalSealStore": sentinels["terminal"],
                "V32OkxPublicBundleTransport": sentinels["transport"],
                "V32RawFirstOkxPublicBundleCollector": sentinels["collector"],
                "LocalV32AnalysisMaterialAdapter": sentinels["material"],
                "LocalV32AnalysisLane": sentinels["analysis"],
                "V32OkxPublicMarkCaptureAdapter": sentinels["capture"],
                "LocalV32OutcomeLane": sentinels["outcome_lane"],
            }
            with ExitStack() as stack:
                replay_call = stack.enter_context(
                    mock.patch.object(
                        composition,
                        "replay_v32_target_run_from_current_authority_v1",
                        return_value=replay,
                    )
                )
                material_constructor = None
                for attribute, return_value in replacements.items():
                    constructor = stack.enter_context(
                        mock.patch.object(
                            composition, attribute, return_value=return_value
                        )
                    )
                    if attribute == "LocalV32AnalysisMaterialAdapter":
                        material_constructor = constructor
                stack.enter_context(
                    mock.patch.object(
                        composition,
                        "LocalV32CycleSourceAdmissionStore",
                        source_store_constructor,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        composition, "route_v32_prospective_wake_v1", route
                    )
                )
                result = composition.run_v32_target_wake_v1(
                    project_root=project, expected_run_id=RUN_ID
                )

            replay_call.assert_called_once_with(
                project_root=project.resolve(), expected_run_id=RUN_ID
            )
            routed = route.call_args.kwargs
            self.assertIs(
                routed["supervisor_alert_port"], sentinels["supervision"]
            )
            self.assertIs(
                routed["supervision_evidence_port"], sentinels["supervision"]
            )
            self.assertIs(routed["terminal_seal_port"], sentinels["terminal"])
            self.assertIs(routed["analysis_port"], sentinels["analysis"])
            self.assertIs(routed["outcome_port"], sentinels["outcome_lane"])
            self.assertIs(routed["clock"], clock)
            self.assertIsNotNone(material_constructor)
            material_kwargs = material_constructor.call_args.kwargs
            self.assertIs(
                material_kwargs["strategy_revision_observation_clock"], clock
            )
            self.assertIsInstance(
                material_kwargs["strategy_revision_material_reader"],
                composition.LocalV32NoRevisionInputMaterialReader,
            )
            self.assertNotIn("wake_runner", routed)
            self.assertEqual(
                source_store_constructor.call_args_list,
                [
                    mock.call(run_root.resolve() / "v32-public-source-store-v1"),
                    mock.call(run_root.resolve()),
                ],
            )
            self.assertEqual(result["runtime_status"], "NOT_DUE")
            self.assertTrue(result["full_authority_and_genesis_replayed"])
            self.assertFalse(result["executable"])


if __name__ == "__main__":
    unittest.main()
