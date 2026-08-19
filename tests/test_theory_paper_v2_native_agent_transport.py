from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.native_agent_transport import (
    NativeAgentTransportWorkflowError,
    advance_native_transport,
    claim_native_request,
    initialize_native_transport_run,
    native_transport_status,
    submit_native_delivery,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.native_agent_transport import (
    NativeAgentTransportError,
)
from trade_system.theory_paper_v2.infrastructure.native_agent_mailbox import (
    LocalNativeAgentTransportStore,
    NativeAgentMailboxError,
)


def _contract(*, max_output_bytes: int = 65_536) -> dict:
    return self_digest(
        {
            "schema_id": "native_codex_transport_contract",
            "schema_version": "1.0.0",
            "contract_id": "test-native-transport",
            "agent_id": "CURRENT_CODEX_TASK",
            "evidence_level": "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT",
            "required_stages": [
                "PROPOSAL",
                "DELIBERATION",
                "POST_ACCEPT_TAIL",
            ],
            "max_output_bytes": max_output_bytes,
            "api_key_required": False,
            "sub_agents_allowed": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_transport_contract_digest",
    )


def _initialize(root: Path, *, max_output_bytes: int = 65_536) -> None:
    initialize_native_transport_run(
        store=LocalNativeAgentTransportStore(root),
        run_id=root.name,
        created_at="2026-08-06T00:00:00Z",
        contract=_contract(max_output_bytes=max_output_bytes),
        implementation_bindings={
            "test.py": {
                "relative_ref": "test.py",
                "physical_sha256": "1" * 64,
            }
        },
    )


def _proposal_payload(store: LocalNativeAgentTransportStore) -> dict:
    request = store.read_document(
        relative_ref="mailbox/requests/proposal.json",
        digest_field="native_agent_request_digest",
    )
    return {
        "schema_id": "native_codex_transport_proposal_payload",
        "schema_version": "1.0.0",
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "input_digest": request["input_binding"]["semantic_digest"],
        "public_analysis": {
            "facts": ["The request exists as a durable artifact."],
            "unknowns": ["Provider model identity is not locally attested."],
            "hypothesis": "A file mailbox survives controller replacement.",
            "expectation_update": "A new process should consume without reauthoring.",
            "falsifier": "Any digest drift or duplicate Agent output falsifies it.",
            "next_observation": "Consume the proposal from a new store instance.",
        },
        "private_chain_of_thought_recorded": False,
    }


def _deliberation_payload(store: LocalNativeAgentTransportStore) -> dict:
    request = store.read_document(
        relative_ref="mailbox/requests/deliberation.json",
        digest_field="native_agent_request_digest",
    )
    evaluation = store.read_document(
        relative_ref="transport/evaluation.json",
        digest_field="native_transport_evaluation_digest",
    )
    return {
        "schema_id": "native_codex_transport_deliberation_payload",
        "schema_version": "1.0.0",
        "run_id": request["run_id"],
        "cycle_index": request["cycle_index"],
        "input_digest": request["input_binding"]["semantic_digest"],
        "evaluation_digest": evaluation["native_transport_evaluation_digest"],
        "selected_action": "WAIT",
        "reason": "WAIT preserves the transport-only boundary.",
        "opportunity_cost": "No market decision is produced in Phase B.",
        "next_review_condition": "Finalize the deterministic postaccept tail.",
        "private_chain_of_thought_recorded": False,
    }


class NativeAgentTransportIntegrationTests(unittest.TestCase):
    def test_native_codex_transport_resumes_across_all_three_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "native-transport-happy"
            _initialize(run_root)

            first = advance_native_transport(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
                now="2026-08-06T00:01:00Z",
            )
            self.assertEqual("WAITING_FOR_PROPOSAL", first["status"])

            author_store = LocalNativeAgentTransportStore(run_root)
            claim_native_request(
                store=author_store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T00:02:00Z",
            )
            submit_native_delivery(
                store=author_store,
                run_id=run_root.name,
                stage="PROPOSAL",
                payload=_proposal_payload(author_store),
                delivered_at="2026-08-06T00:03:00Z",
            )

            second = advance_native_transport(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
                now="2026-08-06T00:04:00Z",
            )
            self.assertEqual("WAITING_FOR_DELIBERATION", second["status"])
            self.assertTrue(
                (run_root / "transport/receipts/proposal-consumed.json").is_file()
            )

            next_author_store = LocalNativeAgentTransportStore(run_root)
            claim_native_request(
                store=next_author_store,
                run_id=run_root.name,
                stage="DELIBERATION",
                claimed_at="2026-08-06T00:05:00Z",
            )
            submit_native_delivery(
                store=next_author_store,
                run_id=run_root.name,
                stage="DELIBERATION",
                payload=_deliberation_payload(next_author_store),
                delivered_at="2026-08-06T00:06:00Z",
            )

            third = advance_native_transport(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
                now="2026-08-06T00:07:00Z",
            )
            self.assertEqual("POST_ACCEPT_PENDING", third["status"])
            self.assertTrue((run_root / "states/state-0001.json").is_file())
            with self.assertRaisesRegex(
                NativeAgentTransportWorkflowError, "NATIVE_CLAIM_STAGE_INVALID"
            ):
                claim_native_request(
                    store=LocalNativeAgentTransportStore(run_root),
                    run_id=run_root.name,
                    stage="DELIBERATION",
                    claimed_at="2026-08-06T00:08:00Z",
                )

            fourth = advance_native_transport(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
                now="2026-08-06T00:09:00Z",
            )
            self.assertEqual("COMPLETED", fourth["status"])
            completion = load_json_strict(run_root / "completion/receipt.json")
            verify_self_digest(
                completion, "native_transport_completion_receipt_digest"
            )
            self.assertEqual(0, completion["postaccept_agent_invocation_count"])
            self.assertEqual(
                "PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT",
                completion["evidence_level"],
            )
            final = native_transport_status(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
            )
            self.assertEqual("NOOP_PHASE_B_COMPLETE", final["next_action"])

    def test_wrong_input_digest_is_rejected_before_delivery_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "wrong-input"
            _initialize(run_root)
            store = LocalNativeAgentTransportStore(run_root)
            advance_native_transport(
                store=store, run_id=run_root.name, now="2026-08-06T01:00:00Z"
            )
            claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T01:01:00Z",
            )
            payload = _proposal_payload(store)
            payload["input_digest"] = "0" * 64
            with self.assertRaisesRegex(
                NativeAgentTransportError, "NATIVE_PAYLOAD_BINDING_MISMATCH"
            ):
                submit_native_delivery(
                    store=store,
                    run_id=run_root.name,
                    stage="PROPOSAL",
                    payload=payload,
                    delivered_at="2026-08-06T01:02:00Z",
                )
            self.assertFalse(
                (run_root / "mailbox/deliveries/proposal.json").exists()
            )

    def test_delivery_is_write_once_for_one_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "write-once"
            _initialize(run_root)
            store = LocalNativeAgentTransportStore(run_root)
            advance_native_transport(
                store=store, run_id=run_root.name, now="2026-08-06T02:00:00Z"
            )
            first_claim = claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T02:01:00Z",
            )
            second_claim = claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T02:02:00Z",
            )
            self.assertEqual(first_claim, second_claim)
            payload = _proposal_payload(store)
            submit_native_delivery(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                payload=payload,
                delivered_at="2026-08-06T02:03:00Z",
            )
            changed = dict(payload)
            changed["public_analysis"] = dict(payload["public_analysis"])
            changed["public_analysis"]["hypothesis"] = "Conflicting second output."
            with self.assertRaisesRegex(
                NativeAgentTransportWorkflowError,
                "NATIVE_DELIVERY_WRITE_ONCE_CONFLICT",
            ):
                submit_native_delivery(
                    store=store,
                    run_id=run_root.name,
                    stage="PROPOSAL",
                    payload=changed,
                    delivered_at="2026-08-06T02:04:00Z",
                )

    def test_physical_rewrite_after_delivery_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "physical-drift"
            _initialize(run_root)
            store = LocalNativeAgentTransportStore(run_root)
            advance_native_transport(
                store=store, run_id=run_root.name, now="2026-08-06T03:00:00Z"
            )
            claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T03:01:00Z",
            )
            submit_native_delivery(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                payload=_proposal_payload(store),
                delivered_at="2026-08-06T03:02:00Z",
            )
            path = run_root / "mailbox/deliveries/proposal.json"
            document = load_json_strict(path)
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                NativeAgentTransportWorkflowError,
                "NATIVE_MAILBOX_PHYSICAL_BINDING_DRIFT",
            ):
                advance_native_transport(
                    store=LocalNativeAgentTransportStore(run_root),
                    run_id=run_root.name,
                    now="2026-08-06T03:03:00Z",
                )
            self.assertFalse((run_root / "states/state-0001.json").exists())

    def test_claim_seal_can_recover_after_controller_independent_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "claim-seal-recovery"
            _initialize(run_root)
            store = LocalNativeAgentTransportStore(run_root)
            advance_native_transport(
                store=store, run_id=run_root.name, now="2026-08-06T04:00:00Z"
            )
            claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T04:01:00Z",
            )
            (run_root / "mailbox/seals/proposal-claim.json").unlink()
            recovered = claim_native_request(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T04:02:00Z",
            )
            verify_self_digest(recovered, "native_agent_claim_digest")
            self.assertTrue(
                (run_root / "mailbox/seals/proposal-claim.json").is_file()
            )

    def test_checkpoint_digest_tamper_stops_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "checkpoint-tamper"
            _initialize(run_root)
            path = run_root / "native-checkpoint.json"
            checkpoint = load_json_strict(path)
            checkpoint["revision"] = 99
            path.write_text(
                json.dumps(checkpoint, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                NativeAgentMailboxError, "NATIVE_CHECKPOINT_DIGEST_INVALID"
            ):
                native_transport_status(
                    store=LocalNativeAgentTransportStore(run_root),
                    run_id=run_root.name,
                )

    def test_output_budget_is_enforced_before_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "output-budget"
            _initialize(run_root, max_output_bytes=128)
            store = LocalNativeAgentTransportStore(run_root)
            advance_native_transport(
                store=store, run_id=run_root.name, now="2026-08-06T05:00:00Z"
            )
            claim_native_request(
                store=store,
                run_id=run_root.name,
                stage="PROPOSAL",
                claimed_at="2026-08-06T05:01:00Z",
            )
            with self.assertRaisesRegex(
                NativeAgentTransportError, "NATIVE_DELIVERY_TOO_LARGE"
            ):
                submit_native_delivery(
                    store=store,
                    run_id=run_root.name,
                    stage="PROPOSAL",
                    payload=_proposal_payload(store),
                    delivered_at="2026-08-06T05:02:00Z",
                )


if __name__ == "__main__":
    unittest.main()
