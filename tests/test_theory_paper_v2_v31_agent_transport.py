from __future__ import annotations

import copy
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from tests.test_theory_paper_v2_v31_durable_bundle import completed_cycle_fixture
from trade_system.theory_paper_v2.application.v31_agent_transport import (
    V31AgentTransportWorkflowError,
    initialize_v31_agent_transport,
    run_v31_proposal_transport,
    run_v31_selection_transport,
    verify_v31_transport_evidence_bundle,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v31_agent_transport import (
    validate_v31_transport_evidence,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
    V31AgentTransportStoreError,
)
from trade_system.theory_paper_v2.presentation.v31_agent_transport_worker import (
    CanonicalStdioV31AgentWorker,
)


RUN_ID = "run:v31"
CYCLE = 1


def _times(prefix: int) -> dict[str, str]:
    return {
        "reserved_at": f"2026-08-06T10:{prefix:02d}:00Z",
        "requested_at": f"2026-08-06T10:{prefix:02d}:01Z",
        "claimed_at": f"2026-08-06T10:{prefix:02d}:02Z",
        "delivered_at": f"2026-08-06T10:{prefix:02d}:03Z",
        "consumed_at": f"2026-08-06T10:{prefix:02d}:04Z",
    }


def _write_source(
    store: LocalV31AgentTransportStore,
    *,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
    minute: int,
) -> dict[str, str]:
    with store.owner_lease(
        owner_id=f"fixture-seed-{minute}",
        acquired_at=f"2026-08-06T09:{minute:02d}:00Z",
        expires_at=f"2026-08-06T09:{minute:02d}:30Z",
    ) as lease:
        return store.write_document(
            lease=lease,
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )


def _initialize(
    store: LocalV31AgentTransportStore,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs, documents, _ = completed_cycle_fixture()
    initialize_v31_agent_transport(
        store=store,
        run_id=RUN_ID,
        cycle_index=CYCLE,
        created_at="2026-08-06T09:10:00Z",
        owner_id="initializer",
        lease_expires_at="2026-08-06T09:10:30Z",
    )
    return inputs, documents, inputs["action_evaluation"]


def _proposal_binding(
    store: LocalV31AgentTransportStore, inputs: Mapping[str, Any]
) -> dict[str, str]:
    return _write_source(
        store,
        relative_ref="cycles/0001/inputs-receipt.json",
        document=inputs["inputs_receipt"],
        digest_field="inputs_receipt_digest",
        minute=11,
    )


def _run_proposal(
    store: LocalV31AgentTransportStore,
    inputs: Mapping[str, Any],
    callback: Any | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    binding = _proposal_binding(store, inputs)
    result = run_v31_proposal_transport(
        store=store,
        run_id=RUN_ID,
        cycle_index=CYCLE,
        inputs_receipt_binding=binding,
        owner_id="proposal-owner",
        lease_acquired_at="2026-08-06T10:10:00Z",
        lease_expires_at="2026-08-06T10:19:59Z",
        stage_times=_times(11),
        agent_call=(callback or (lambda request: inputs["agent_proposal"])),
    )
    return result, binding


def _selection_bindings(
    store: LocalV31AgentTransportStore,
    documents: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    preselection = _write_source(
        store,
        relative_ref="cycles/0001/cycle-preselection.json",
        document=documents["EVALUATION_SEALED"],
        digest_field="preselection_digest",
        minute=12,
    )
    action_evaluation = _write_source(
        store,
        relative_ref="cycles/0001/action-evaluation.json",
        document=evaluation,
        digest_field="action_evaluation_digest",
        minute=13,
    )
    return preselection, action_evaluation


class _CrashAfterDeliveryStore(LocalV31AgentTransportStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.injected = False

    def replace_checkpoint(self, **kwargs: Any) -> dict[str, Any]:
        checkpoint = kwargs["checkpoint"]
        proposal = checkpoint["stage_states"]["PROPOSAL"]
        if not self.injected and proposal["status"] == "DELIVERED":
            self.injected = True
            raise V31AgentTransportStoreError("INJECTED_CRASH_AFTER_DELIVERY")
        return super().replace_checkpoint(**kwargs)


class _HardCrashBeforeFailureReceiptStore(LocalV31AgentTransportStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.injected = False

    def write_document(self, **kwargs: Any) -> dict[str, str]:
        document = kwargs["document"]
        if (
            not self.injected
            and document.get("schema_id")
            == "theory_paper_v31_agent_transport_failure"
        ):
            self.injected = True
            raise V31AgentTransportStoreError(
                "INJECTED_PROCESS_LOSS_BEFORE_FAILURE_RECEIPT"
            )
        return super().write_document(**kwargs)


class V31AgentTransportTests(unittest.TestCase):
    def test_two_stage_transport_is_durable_single_attempt_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, documents, evaluation = _initialize(store)
            proposal_calls: list[str] = []

            def proposal_agent(request: Mapping[str, Any]) -> Mapping[str, Any]:
                proposal_calls.append(request["request_digest"])
                checkpoint = store.read_checkpoint(
                    relative_ref="cycles/0001/agent-transport/checkpoint.json"
                )
                self.assertEqual("PROPOSAL_IN_PROGRESS", checkpoint["status"])
                self.assertTrue(
                    store.document_exists(
                        relative_ref="cycles/0001/agent-transport/proposal/attempt.json"
                    )
                )
                self.assertTrue(
                    store.document_exists(
                        relative_ref="cycles/0001/agent-transport/proposal/claim.json"
                    )
                )
                self.assertNotIn("selected_candidate_id", request)
                return inputs["agent_proposal"]

            proposal, _ = _run_proposal(store, inputs, proposal_agent)
            self.assertEqual("READY_FOR_SELECTION", proposal["status"])
            self.assertEqual(1, len(proposal_calls))

            preselection_binding, evaluation_binding = _selection_bindings(
                store, documents, evaluation
            )
            selection_calls: list[str] = []

            def selection_agent(request: Mapping[str, Any]) -> Mapping[str, Any]:
                selection_calls.append(request["request_digest"])
                self.assertEqual("SELECTION", request["stage"])
                self.assertEqual(
                    documents["EVALUATION_SEALED"][
                        "selectable_candidate_ids"
                    ],
                    request["selectable_candidate_ids"],
                )
                self.assertEqual(
                    proposal["consume_receipt"]["consume_digest"],
                    request["proposal_consume_binding"]["semantic_digest"],
                )
                self.assertEqual(
                    preselection_binding,
                    request["preselection_binding"],
                )
                return documents["SELECTION_SEALED"]

            completed = run_v31_selection_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=CYCLE,
                preselection_binding=preselection_binding,
                action_evaluation_binding=evaluation_binding,
                owner_id="selection-owner",
                lease_acquired_at="2026-08-06T10:20:00Z",
                lease_expires_at="2026-08-06T10:29:59Z",
                stage_times=_times(21),
                agent_call=selection_agent,
            )
            self.assertEqual("COMPLETED", completed["status"])
            self.assertEqual(1, len(selection_calls))
            binding = completed["transport_evidence_binding"]
            expected_ref = (
                "cycles/0001/transport-evidence/"
                f"{binding['semantic_digest']}.json"
            )
            self.assertEqual(expected_ref, binding["relative_ref"])
            evidence = store.artifact_binding(
                relative_ref=expected_ref,
                digest_field="transport_evidence_digest",
            )
            document = store.read_bound_document(evidence)
            validate_v31_transport_evidence(document)
            self.assertEqual(
                binding["semantic_digest"],
                verify_v31_transport_evidence_bundle(
                    store=store, evidence_binding=binding
                ),
            )
            self.assertEqual(10, len(document["chronology"]))
            self.assertEqual(1, document["stages"]["PROPOSAL"]["attempt_count"])
            self.assertEqual(1, document["stages"]["SELECTION"]["attempt_count"])
            self.assertFalse(document["agent_output_is_execution_authority"])
            self.assertFalse(document["paper_trading"])
            self.assertFalse(document["executable"])

    def test_invalid_selected_first_proposal_permanently_fails_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, _, _ = _initialize(store)
            calls = 0

            def invalid_agent(_: Mapping[str, Any]) -> Mapping[str, Any]:
                nonlocal calls
                calls += 1
                proposal = copy.deepcopy(inputs["agent_proposal"])
                proposal.pop("agent_proposal_digest")
                proposal["selected_candidate_id"] = "candidate:WAIT"
                return self_digest(proposal, "agent_proposal_digest")

            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_AGENT_STAGE_FAILED_CLOSED",
            ):
                _run_proposal(store, inputs, invalid_agent)
            self.assertEqual(1, calls)
            checkpoint = store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])
            self.assertFalse(checkpoint["resume_allowed"])
            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_PERMANENTLY_FAILED_CLOSED",
            ):
                run_v31_proposal_transport(
                    store=store,
                    run_id=RUN_ID,
                    cycle_index=CYCLE,
                    inputs_receipt_binding=store.artifact_binding(
                        relative_ref="cycles/0001/inputs-receipt.json",
                        digest_field="inputs_receipt_digest",
                    ),
                    owner_id="forbidden-retry",
                    lease_acquired_at="2026-08-06T10:30:00Z",
                    lease_expires_at="2026-08-06T10:39:59Z",
                    stage_times=_times(31),
                    agent_call=lambda request: inputs["agent_proposal"],
                )
            self.assertEqual(1, calls)

    def test_agent_crash_without_delivery_is_permanent_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, _, _ = _initialize(store)
            calls = 0

            def crash(_: Mapping[str, Any]) -> Mapping[str, Any]:
                nonlocal calls
                calls += 1
                raise KeyboardInterrupt("simulated hard interruption")

            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_AGENT_STAGE_FAILED_CLOSED",
            ):
                _run_proposal(store, inputs, crash)
            self.assertEqual(1, calls)
            self.assertFalse(
                store.document_exists(
                    relative_ref="cycles/0001/agent-transport/proposal/delivery.json"
                )
            )
            checkpoint = store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])

    def test_durable_delivery_recovers_without_second_agent_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crashing_store = _CrashAfterDeliveryStore(root)
            inputs, _, _ = _initialize(crashing_store)
            calls = 0

            def agent(_: Mapping[str, Any]) -> Mapping[str, Any]:
                nonlocal calls
                calls += 1
                return inputs["agent_proposal"]

            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_DURABLE_DELIVERY_PENDING_DETERMINISTIC_RECOVERY",
            ):
                _run_proposal(crashing_store, inputs, agent)
            self.assertEqual(1, calls)
            recovered_store = LocalV31AgentTransportStore(root)
            binding = recovered_store.artifact_binding(
                relative_ref="cycles/0001/inputs-receipt.json",
                digest_field="inputs_receipt_digest",
            )

            def forbidden(_: Mapping[str, Any]) -> Mapping[str, Any]:
                self.fail("durable recovery must not reinvoke the Agent")

            recovered = run_v31_proposal_transport(
                store=recovered_store,
                run_id=RUN_ID,
                cycle_index=CYCLE,
                inputs_receipt_binding=binding,
                owner_id="recovery-owner",
                lease_acquired_at="2026-08-06T10:40:00Z",
                lease_expires_at="2026-08-06T10:49:59Z",
                stage_times=_times(41),
                agent_call=forbidden,
            )
            self.assertEqual("READY_FOR_SELECTION", recovered["status"])
            self.assertEqual(1, calls)

    def test_restart_fails_orphan_claim_without_reinvocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crashing_store = _HardCrashBeforeFailureReceiptStore(root)
            inputs, _, _ = _initialize(crashing_store)
            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_FAILURE_PERSISTENCE_FAILED",
            ):
                _run_proposal(
                    crashing_store,
                    inputs,
                    lambda request: (_ for _ in ()).throw(
                        KeyboardInterrupt("process lost before delivery")
                    ),
                )
            recovered_store = LocalV31AgentTransportStore(root)
            input_binding = recovered_store.artifact_binding(
                relative_ref="cycles/0001/inputs-receipt.json",
                digest_field="inputs_receipt_digest",
            )
            reinvocations = 0

            def forbidden(_: Mapping[str, Any]) -> Mapping[str, Any]:
                nonlocal reinvocations
                reinvocations += 1
                return inputs["agent_proposal"]

            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_INCOMPLETE_ATTEMPT_FAILED_CLOSED",
            ):
                run_v31_proposal_transport(
                    store=recovered_store,
                    run_id=RUN_ID,
                    cycle_index=CYCLE,
                    inputs_receipt_binding=input_binding,
                    owner_id="orphan-recovery",
                    lease_acquired_at="2026-08-06T10:50:00Z",
                    lease_expires_at="2026-08-06T10:59:59Z",
                    stage_times=_times(51),
                    agent_call=forbidden,
                )
            self.assertEqual(0, reinvocations)
            checkpoint = recovered_store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])

    def test_selection_request_is_not_created_for_physically_drifted_preselection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, documents, evaluation = _initialize(store)
            _run_proposal(store, inputs)
            preselection, action_evaluation = _selection_bindings(
                store, documents, evaluation
            )
            path = Path(directory) / preselection["relative_ref"]
            path.write_bytes(path.read_bytes() + b" ")
            calls = 0

            def forbidden(_: Mapping[str, Any]) -> Mapping[str, Any]:
                nonlocal calls
                calls += 1
                return documents["SELECTION_SEALED"]

            with self.assertRaisesRegex(
                V31AgentTransportStoreError,
                "V31_TRANSPORT_BOUND_DOCUMENT_PHYSICAL_DRIFT",
            ):
                run_v31_selection_transport(
                    store=store,
                    run_id=RUN_ID,
                    cycle_index=CYCLE,
                    preselection_binding=preselection,
                    action_evaluation_binding=action_evaluation,
                    owner_id="selection-must-not-start",
                    lease_acquired_at="2026-08-06T10:50:00Z",
                    lease_expires_at="2026-08-06T10:59:59Z",
                    stage_times=_times(51),
                    agent_call=forbidden,
                )
            self.assertEqual(0, calls)
            self.assertFalse(
                store.document_exists(
                    relative_ref="cycles/0001/agent-transport/selection/request.json"
                )
            )

    def test_stdio_worker_authors_only_after_request_is_durable_and_supports_both_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, documents, evaluation = _initialize(store)
            proposal_output = StringIO()
            proposal_worker = CanonicalStdioV31AgentWorker(
                input_stream=StringIO(
                    canonical_bytes(inputs["agent_proposal"]).decode("utf-8")
                    + "\n"
                ),
                output_stream=proposal_output,
            )
            proposal, _ = _run_proposal(store, inputs, proposal_worker)
            emitted_proposal_request = loads_json_strict(
                proposal_output.getvalue().strip()
            )
            durable_proposal_request = store.read_bound_document(
                store.artifact_binding(
                    relative_ref="cycles/0001/agent-transport/proposal/request.json",
                    digest_field="request_digest",
                )
            )
            self.assertEqual(durable_proposal_request, emitted_proposal_request)
            self.assertEqual(
                canonical_bytes(durable_proposal_request).decode("utf-8") + "\n",
                proposal_output.getvalue(),
            )
            self.assertEqual(1, proposal_worker.invocation_count)

            preselection, action_evaluation = _selection_bindings(
                store, documents, evaluation
            )
            selection_output = StringIO()
            selection_worker = CanonicalStdioV31AgentWorker(
                input_stream=StringIO(
                    canonical_bytes(documents["SELECTION_SEALED"]).decode("utf-8")
                    + "\n"
                ),
                output_stream=selection_output,
            )
            completed = run_v31_selection_transport(
                store=store,
                run_id=RUN_ID,
                cycle_index=CYCLE,
                preselection_binding=preselection,
                action_evaluation_binding=action_evaluation,
                owner_id="manual-selection",
                lease_acquired_at="2026-08-06T11:20:00Z",
                lease_expires_at="2026-08-06T11:29:59Z",
                stage_times=_times(22),
                agent_call=selection_worker,
            )
            emitted_selection_request = loads_json_strict(
                selection_output.getvalue().strip()
            )
            self.assertEqual("COMPLETED", completed["status"])
            self.assertEqual("SELECTION", emitted_selection_request["stage"])
            self.assertEqual(
                proposal["consume_receipt"]["consume_digest"],
                emitted_selection_request["proposal_consume_binding"][
                    "semantic_digest"
                ],
            )
            self.assertEqual(1, selection_worker.invocation_count)

    def test_stdio_worker_eof_is_permanent_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, _, _ = _initialize(store)
            worker = CanonicalStdioV31AgentWorker(
                input_stream=StringIO(""), output_stream=StringIO()
            )
            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_AGENT_STAGE_FAILED_CLOSED",
            ):
                _run_proposal(store, inputs, worker)
            checkpoint = store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])
            self.assertEqual(1, worker.invocation_count)
            self.assertFalse(
                store.document_exists(
                    relative_ref="cycles/0001/agent-transport/proposal/delivery.json"
                )
            )

    def test_stdio_worker_invalid_json_is_permanent_failed_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, _, _ = _initialize(store)
            worker = CanonicalStdioV31AgentWorker(
                input_stream=StringIO("{not-json}\n"),
                output_stream=StringIO(),
            )
            with self.assertRaisesRegex(
                V31AgentTransportWorkflowError,
                "V31_TRANSPORT_AGENT_STAGE_FAILED_CLOSED",
            ):
                _run_proposal(store, inputs, worker)
            checkpoint = store.read_checkpoint(
                relative_ref="cycles/0001/agent-transport/checkpoint.json"
            )
            self.assertEqual("FAILED_CLOSED", checkpoint["status"])
            self.assertEqual(1, worker.invocation_count)

    def test_single_owner_lease_rejects_concurrent_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = LocalV31AgentTransportStore(Path(directory))
            second = LocalV31AgentTransportStore(Path(directory))
            with first.owner_lease(
                owner_id="first-owner",
                acquired_at="2026-08-06T11:00:00Z",
                expires_at="2026-08-06T11:10:00Z",
            ):
                with self.assertRaisesRegex(
                    V31AgentTransportStoreError,
                    "V31_TRANSPORT_OWNER_LEASE_HELD",
                ):
                    with second.owner_lease(
                        owner_id="second-owner",
                        acquired_at="2026-08-06T11:00:01Z",
                        expires_at="2026-08-06T11:10:01Z",
                    ):
                        pass

    def test_business_mutation_without_owner_lease_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV31AgentTransportStore(Path(directory))
            inputs, _, _ = completed_cycle_fixture()
            with self.assertRaisesRegex(
                V31AgentTransportStoreError,
                "V31_TRANSPORT_MUTATION_WITHOUT_OWNER_LEASE",
            ):
                store.write_document(
                    lease=object(),
                    relative_ref="cycles/0001/forbidden.json",
                    document=inputs["inputs_receipt"],
                    digest_field="inputs_receipt_digest",
                )


if __name__ == "__main__":
    unittest.main()
