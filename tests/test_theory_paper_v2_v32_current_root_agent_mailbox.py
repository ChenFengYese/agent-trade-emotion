from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from tests.test_theory_paper_v2_v32_agent_semantic_compiler import _full_fixture
from trade_system.theory_paper_v2.application.v32_agent_semantic_compiler import (
    build_v32_selection_semantic_output_v1,
    canonical_v32_agent_semantic_json_v1,
    compile_v32_proposal_delivery_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    build_v32_agent_input_context_v1,
    build_v32_selection_canonical_packet_v1,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
    build_v32_current_codex_presentation_envelope_v1,
    build_v32_current_root_agent_mailbox_claim_v1,
    claim_v32_current_root_agent_mailbox_request_v1,
    verify_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain import (
    v32_current_root_agent_mailbox as presentation,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)


class V32CurrentRootAgentMailboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = _full_fixture()

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = LocalV32CurrentRootAgentMailbox(self.root)
        self.run_id = self.fx["proposal_context"]["run_id"]
        self.cycle_index = self.fx["proposal_context"]["cycle_index"]
        self.checkpoint = self.store.initialize_checkpoint(
            mailbox_id=f"mailbox::{self.run_id}::{self.cycle_index}",
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            created_at="2026-08-07T00:16:00Z",
        )

    def _enqueue_proposal(self) -> dict:
        return dict(
            self.store.enqueue_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                expected_checkpoint_digest=self.checkpoint[
                    CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=self.fx["proposal_context"],
                agent_input_context_binding=self.fx[
                    "proposal_context_binding"
                ],
                reserved_at="2026-08-07T00:16:05Z",
            )
        )

    @staticmethod
    def _mailbox_claim_presentation(claimed: dict) -> dict:
        return build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=claimed["checkpoint"],
            request=claimed["request"],
            claim=claimed["claim"],
            lossless_context_package=None,
            control_context={
                "presentation_kind": "MAILBOX_AGENT_CLAIM",
                "stage": claimed["request"]["stage"],
                "stage_status": "CLAIMED",
                "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
            },
        )

    def _complete_proposal(self) -> dict:
        opened = self._enqueue_proposal()
        claimed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:16:10Z",
        )
        current_codex_presentation = self._mailbox_claim_presentation(claimed)
        delivered = self.store.submit_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=claimed["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:16:20Z",
            payload_utf8=self.fx["proposal_payload"],
        )
        return dict(
            self.store.consume_delivery(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=delivered["checkpoint"][
                    CHECKPOINT_DIGEST_FIELD
                ],
                consumed_at="2026-08-07T00:16:30Z",
            )
        )

    def _selection_context(
        self, proposal: dict, *, forge_delivery_ref: bool = False
    ) -> tuple[dict, dict, str]:
        proposal_receipt = compile_v32_proposal_delivery_v1(
            proposal_input_context=self.fx["proposal_context"],
            proposal_delivery=proposal["agent_delivery"],
            proposal_consumption=proposal["agent_consumption"],
            compiled_at="2026-08-07T00:16:40Z",
        )
        dynamic = proposal_receipt["compiled_dynamic_research_state"]
        evaluation = proposal_receipt["sealed_action_evaluation"]
        dynamic_binding = lifecycle_fixture._embedded(
            "mailbox-selection/compiled-dynamic.json",
            dynamic,
            "theory_paper_v32_dynamic_research_state_v1",
            "dynamic_research_state_digest",
        )
        evaluation_binding = lifecycle_fixture._embedded(
            "mailbox-selection/sealed-action-evaluation.json",
            evaluation,
            ACTION_EVALUATION_SCHEMA_ID,
            ACTION_EVALUATION_DIGEST_FIELD,
        )
        delivery_binding = dict(proposal["agent_delivery_binding"])
        if forge_delivery_ref:
            delivery_binding["relative_ref"] = (
                "mailbox-selection/forged-proposal-delivery.json"
            )
        packet = build_v32_selection_canonical_packet_v1(
            proposal_input_context=self.fx["proposal_context"],
            proposal_input_context_binding=self.fx[
                "proposal_context_binding"
            ],
            proposal_delivery=proposal["agent_delivery"],
            proposal_delivery_binding=delivery_binding,
            proposal_consumption=proposal["agent_consumption"],
            proposal_consumption_binding=proposal[
                "agent_consumption_binding"
            ],
            compiled_dynamic_research_state=dynamic,
            compiled_dynamic_research_state_binding=dynamic_binding,
            sealed_action_evaluation=evaluation,
            sealed_action_evaluation_binding=evaluation_binding,
            prepared_at="2026-08-07T00:16:45Z",
        )
        packet_binding = lifecycle_fixture._embedded(
            "mailbox-selection/selection-packet.json",
            packet,
            SELECTION_PACKET_SCHEMA_ID,
            SELECTION_PACKET_DIGEST_FIELD,
        )
        context = build_v32_agent_input_context_v1(
            agent_stage="SELECTION",
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
            created_at="2026-08-07T00:16:50Z",
        )
        context_binding = lifecycle_fixture._embedded(
            "mailbox-selection/selection-context.json",
            context,
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )
        output = build_v32_selection_semantic_output_v1(
            selection_input_context=context,
            selected_candidate_id="open-short",
        )
        return context, context_binding, canonical_v32_agent_semantic_json_v1(
            output
        )

    def test_compact_presentation_binds_claim_and_carries_packet_once(self) -> None:
        opened = self._enqueue_proposal()
        claim = build_v32_current_root_agent_mailbox_claim_v1(
            request=opened["request"], claimed_at="2026-08-07T00:16:10Z"
        )
        after = claim_v32_current_root_agent_mailbox_request_v1(
            checkpoint=opened["checkpoint"],
            request=opened["request"],
            claim=claim,
        )
        controls = {
            "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
            "stage": "PROPOSAL",
            "stage_status": "CLAIMED",
            "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
        }
        envelope = build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=after,
            request=opened["request"],
            claim=claim,
            lossless_context_package=None,
            control_context=controls,
        )
        verify_v32_current_codex_presentation_envelope_v1(envelope)
        self.assertLessEqual(
            len(canonical_bytes(envelope)),
            MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES,
        )
        packet = self.fx["proposal_context"]["canonical_packet"]
        self.assertEqual(
            canonical_bytes(envelope).count(canonical_bytes(packet)), 1
        )

        wrong_stage = {**controls, "stage": "SELECTION"}
        with self.assertRaisesRegex(
            ValueError, "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID"
        ):
            build_v32_current_codex_presentation_envelope_v1(
                mailbox_checkpoint=after,
                request=opened["request"],
                claim=claim,
                lossless_context_package=None,
                control_context=wrong_stage,
            )
        with self.assertRaisesRegex(
            ValueError, "V32_CURRENT_CODEX_PRESENTATION_CONTROL_INVALID"
        ):
            build_v32_current_codex_presentation_envelope_v1(
                mailbox_checkpoint=after,
                request=opened["request"],
                claim=claim,
                lossless_context_package=None,
                control_context={**controls, "foo": packet},
            )

    def test_enqueue_capacity_failure_writes_no_request_or_material(self) -> None:
        with mock.patch.object(
            presentation,
            "MAX_CURRENT_CODEX_PRESENTATION_CANONICAL_BYTES",
            1,
        ), self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError,
            "V32_MAILBOX_STORE_ENQUEUE_INVALID",
        ):
            self._enqueue_proposal()
        self.assertEqual(
            self.store.load_checkpoint(
                run_id=self.run_id, cycle_index=self.cycle_index
            ),
            self.checkpoint,
        )
        self.assertFalse(any(self.root.rglob("request.json")))
        self.assertFalse(any(self.root.rglob("input-material")))
        self.assertFalse(any(self.root.rglob("canonical-packet-original.json")))

    def test_two_stage_round_trip_is_write_once_and_complete(self) -> None:
        proposal = self._complete_proposal()
        selection_context, selection_binding, selection_payload = (
            self._selection_context(proposal)
        )
        opened = self.store.enqueue_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            expected_checkpoint_digest=proposal["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            agent_input_context=selection_context,
            agent_input_context_binding=selection_binding,
            reserved_at="2026-08-07T00:16:55Z",
        )
        claimed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="SELECTION",
            expected_checkpoint_digest=opened["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:17:00Z",
        )
        current_codex_presentation = self._mailbox_claim_presentation(claimed)
        delivered = self.store.submit_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="SELECTION",
            expected_checkpoint_digest=claimed["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:17:10Z",
            payload_utf8=selection_payload,
        )
        consumed = self.store.consume_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="SELECTION",
            expected_checkpoint_digest=delivered["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            consumed_at="2026-08-07T00:17:20Z",
        )

        final = consumed["checkpoint"]
        self.assertEqual(final["status"], "COMPLETE")
        self.assertIsNone(final["active_stage"])
        self.assertEqual(
            {stage: final["stage_states"][stage]["attempt_count"] for stage in ("PROPOSAL", "SELECTION")},
            {"PROPOSAL": 1, "SELECTION": 1},
        )
        self.assertEqual(opened["request"]["agent_input_context"], selection_context)
        self.assertEqual(
            opened["request"]["agent_input_context"]["canonical_packet"],
            selection_context["canonical_packet"],
        )
        for document in (
            opened["request"],
            claimed["claim"],
            final,
        ):
            self.assertEqual(document["network_request_count"], 0)
        for document in (
            opened["request"],
            claimed["claim"],
            delivered["agent_delivery"],
            consumed["agent_consumption"],
            final,
        ):
            self.assertIs(document["account_access"], False)
            self.assertIs(document["order_submission"], False)
            self.assertIs(document["executable"], False)
            self.assertEqual(document["source_scope"], "PUBLIC_NON_ACCOUNT_ONLY")
        self.assertIsNone(
            self.store.next_pending_request(
                run_id=self.run_id, cycle_index=self.cycle_index
            )
        )

    def test_pending_reader_tracks_claim_delivery_and_controller_consume(self) -> None:
        opened = self._enqueue_proposal()
        pending = self.store.next_pending_request(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(pending["next_action"], "CURRENT_ROOT_CODEX_CLAIM")
        self.assertIsNone(pending["claim"])
        self.assertEqual(
            pending["request"]["agent_input_context"]["canonical_packet"],
            self.fx["proposal_context"]["canonical_packet"],
        )

        claimed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:16:10Z",
        )
        pending = self.store.next_pending_request(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(
            pending["next_action"], "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
        )
        self.assertEqual(pending["claim"], claimed["claim"])
        self.assertFalse(
            (
                self.root
                / "v32-current-root-agent-mailbox-v1/cycles/0001/proposal/agent-delivery.json"
            ).exists()
        )

        current_codex_presentation = self._mailbox_claim_presentation(claimed)
        delivered = self.store.submit_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=claimed["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:16:20Z",
            payload_utf8=self.fx["proposal_payload"],
        )
        pending = self.store.next_pending_request(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(pending["next_action"], "CONTROLLER_CONSUME_DELIVERY")
        self.assertEqual(pending["stage_status"], "DELIVERED")

        consumed = self.store.consume_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=delivered["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            consumed_at="2026-08-07T00:16:30Z",
        )
        self.assertEqual(consumed["checkpoint"]["status"], "READY_FOR_SELECTION")
        self.assertIsNone(
            self.store.next_pending_request(
                run_id=self.run_id, cycle_index=self.cycle_index
            )
        )

    def test_stale_cas_and_second_attempt_fail_closed(self) -> None:
        genesis_digest = self.checkpoint[CHECKPOINT_DIGEST_FIELD]
        opened = self._enqueue_proposal()
        with self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError, "V32_MAILBOX_STORE_CAS_CONFLICT"
        ):
            self.store.claim_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=genesis_digest,
                claimed_at="2026-08-07T00:16:10Z",
            )
        claimed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:16:10Z",
        )
        with self.assertRaises(V32CurrentRootAgentMailboxStoreError):
            self.store.claim_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=claimed["checkpoint"][
                    CHECKPOINT_DIGEST_FIELD
                ],
                claimed_at="2026-08-07T00:16:11Z",
            )
        current = self.store.load_checkpoint(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(current, claimed["checkpoint"])
        self.assertEqual(current["stage_states"]["PROPOSAL"]["attempt_count"], 1)

    def test_selection_is_blocked_until_exact_proposal_chain_is_consumed(self) -> None:
        context = self.fx["selection_context"]
        binding = self.fx["selection_context_binding"]
        with self.assertRaises(V32CurrentRootAgentMailboxStoreError):
            self.store.enqueue_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                expected_checkpoint_digest=self.checkpoint[
                    CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=context,
                agent_input_context_binding=binding,
                reserved_at="2026-08-07T00:16:55Z",
            )
        current = self.store.load_checkpoint(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(current, self.checkpoint)

        proposal = self._complete_proposal()
        forged_context, forged_binding, _ = self._selection_context(
            proposal, forge_delivery_ref=True
        )
        with self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError,
            "V32_MAILBOX_STORE_SELECTION_PROPOSAL_CHAIN_INVALID",
        ):
            self.store.enqueue_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                expected_checkpoint_digest=proposal["checkpoint"][
                    CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=forged_context,
                agent_input_context_binding=forged_binding,
                reserved_at="2026-08-07T00:16:55Z",
            )
        current = self.store.load_checkpoint(
            run_id=self.run_id, cycle_index=self.cycle_index
        )
        self.assertEqual(current, proposal["checkpoint"])

    def test_tampered_write_once_artifact_fails_closed(self) -> None:
        self._enqueue_proposal()
        request_path = (
            self.root
            / "v32-current-root-agent-mailbox-v1/cycles/0001/proposal/request.json"
        )
        request_path.write_bytes(request_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError,
            "V32_MAILBOX_STORE_NONCANONICAL_FILE",
        ):
            self.store.next_pending_request(
                run_id=self.run_id, cycle_index=self.cycle_index
            )

    def test_enqueue_and_claim_recover_one_exact_transition_tail(self) -> None:
        genesis_digest = self.checkpoint[CHECKPOINT_DIGEST_FIELD]
        with mock.patch.object(
            self.store,
            "_commit",
            side_effect=V32CurrentRootAgentMailboxStoreError("injected"),
        ), self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError, "injected"
        ):
            self._enqueue_proposal()

        opened = self.store.enqueue_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            expected_checkpoint_digest=genesis_digest,
            agent_input_context=self.fx["proposal_context"],
            agent_input_context_binding=self.fx["proposal_context_binding"],
            reserved_at="2026-08-07T00:16:09Z",
        )
        self.assertEqual(opened["request"]["reserved_at"], "2026-08-07T00:16:05Z")
        opened_digest = opened["checkpoint"][CHECKPOINT_DIGEST_FIELD]

        original_commit = self.store._commit

        def commit_then_lose_response(**kwargs):
            original_commit(**kwargs)
            raise V32CurrentRootAgentMailboxStoreError("response-lost")

        with mock.patch.object(
            self.store, "_commit", side_effect=commit_then_lose_response
        ), self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError, "response-lost"
        ):
            self.store.claim_request(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=opened_digest,
                claimed_at="2026-08-07T00:16:10Z",
            )

        replayed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened_digest,
            claimed_at="2026-08-07T00:16:19Z",
        )
        self.assertEqual(replayed["claim"]["claimed_at"], "2026-08-07T00:16:10Z")
        self.assertEqual(
            replayed["checkpoint"]["stage_states"]["PROPOSAL"]["attempt_count"],
            1,
        )

    def test_delivery_and_consumption_recover_exact_partial_tails(self) -> None:
        opened = self._enqueue_proposal()
        claimed = self.store.claim_request(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened["checkpoint"][
                CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:16:10Z",
        )
        claimed_digest = claimed["checkpoint"][CHECKPOINT_DIGEST_FIELD]
        current_codex_presentation = self._mailbox_claim_presentation(claimed)
        original_write = self.store._write_document

        def fail_delivery_receipt_once(**kwargs):
            if str(kwargs["relative_ref"]).endswith("delivery-receipt.json"):
                raise V32CurrentRootAgentMailboxStoreError("receipt-interrupted")
            return original_write(**kwargs)

        with mock.patch.object(
            self.store, "_write_document", side_effect=fail_delivery_receipt_once
        ), self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError, "receipt-interrupted"
        ):
            self.store.submit_delivery(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=claimed_digest,
                current_codex_presentation_envelope=current_codex_presentation,
                expected_current_codex_presentation_digest=current_codex_presentation[
                    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                ],
                delivered_at="2026-08-07T00:16:20Z",
                payload_utf8=self.fx["proposal_payload"],
            )

        delivered = self.store.submit_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=claimed_digest,
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:16:29Z",
            payload_utf8='{"different":"payload-must-not-win"}',
        )
        self.assertEqual(
            delivered["agent_delivery"]["delivered_at"],
            "2026-08-07T00:16:20Z",
        )
        self.assertEqual(
            delivered["agent_delivery"]["payload_utf8"],
            self.fx["proposal_payload"],
        )

        delivered_digest = delivered["checkpoint"][CHECKPOINT_DIGEST_FIELD]
        original_commit = self.store._commit

        def commit_then_lose_response(**kwargs):
            original_commit(**kwargs)
            raise V32CurrentRootAgentMailboxStoreError("response-lost")

        with mock.patch.object(
            self.store, "_commit", side_effect=commit_then_lose_response
        ), self.assertRaisesRegex(
            V32CurrentRootAgentMailboxStoreError, "response-lost"
        ):
            self.store.consume_delivery(
                run_id=self.run_id,
                cycle_index=self.cycle_index,
                stage="PROPOSAL",
                expected_checkpoint_digest=delivered_digest,
                consumed_at="2026-08-07T00:16:30Z",
            )

        consumed = self.store.consume_delivery(
            run_id=self.run_id,
            cycle_index=self.cycle_index,
            stage="PROPOSAL",
            expected_checkpoint_digest=delivered_digest,
            consumed_at="2026-08-07T00:16:39Z",
        )
        self.assertEqual(
            consumed["agent_consumption"]["consumed_at"],
            "2026-08-07T00:16:30Z",
        )
        self.assertEqual(
            consumed["checkpoint"]["stage_states"]["PROPOSAL"]["attempt_count"],
            1,
        )

    def test_verified_recovery_view_repairs_all_four_pre_cas_tails(self) -> None:
        for tail_kind in (
            "DELIVERY_ONLY",
            "DELIVERY_RECEIPT_PRE_CAS",
            "CONSUMPTION_ONLY",
            "CONSUMPTION_RECEIPT_PRE_CAS",
        ):
            with self.subTest(tail_kind=tail_kind), TemporaryDirectory() as folder:
                store = LocalV32CurrentRootAgentMailbox(Path(folder))
                initial = store.initialize_checkpoint(
                    mailbox_id=f"mailbox::{self.run_id}::{self.cycle_index}",
                    run_id=self.run_id,
                    cycle_index=self.cycle_index,
                    created_at="2026-08-07T00:16:00Z",
                )
                opened = store.enqueue_request(
                    run_id=self.run_id,
                    cycle_index=self.cycle_index,
                    expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                    agent_input_context=self.fx["proposal_context"],
                    agent_input_context_binding=self.fx[
                        "proposal_context_binding"
                    ],
                    reserved_at="2026-08-07T00:16:05Z",
                )
                claimed = store.claim_request(
                    run_id=self.run_id,
                    cycle_index=self.cycle_index,
                    stage="PROPOSAL",
                    expected_checkpoint_digest=opened["checkpoint"][
                        CHECKPOINT_DIGEST_FIELD
                    ],
                    claimed_at="2026-08-07T00:16:10Z",
                )
                presentation_envelope = self._mailbox_claim_presentation(claimed)

                def submit() -> dict:
                    return dict(
                        store.submit_delivery(
                            run_id=self.run_id,
                            cycle_index=self.cycle_index,
                            stage="PROPOSAL",
                            expected_checkpoint_digest=claimed["checkpoint"][
                                CHECKPOINT_DIGEST_FIELD
                            ],
                            current_codex_presentation_envelope=(
                                presentation_envelope
                            ),
                            expected_current_codex_presentation_digest=(
                                presentation_envelope[
                                    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                                ]
                            ),
                            delivered_at="2026-08-07T00:16:20Z",
                            payload_utf8=self.fx["proposal_payload"],
                        )
                    )

                original_write = store._write_document

                def fail_receipt(*, relative_ref, **kwargs):
                    expected_name = (
                        "delivery-receipt.json"
                        if tail_kind == "DELIVERY_ONLY"
                        else "consumption-receipt.json"
                    )
                    if str(relative_ref).endswith(expected_name):
                        raise V32CurrentRootAgentMailboxStoreError(
                            f"injected:{tail_kind}"
                        )
                    return original_write(relative_ref=relative_ref, **kwargs)

                def fail_checkpoint(**kwargs):
                    del kwargs
                    raise V32CurrentRootAgentMailboxStoreError(
                        f"injected:{tail_kind}"
                    )

                if tail_kind.startswith("DELIVERY"):
                    failure = (
                        mock.patch.object(
                            store, "_write_document", side_effect=fail_receipt
                        )
                        if tail_kind == "DELIVERY_ONLY"
                        else mock.patch.object(
                            store, "_commit", side_effect=fail_checkpoint
                        )
                    )
                    with failure, self.assertRaisesRegex(
                        V32CurrentRootAgentMailboxStoreError, "injected"
                    ):
                        submit()
                    recovery = store.load_verified_recovery_stage_view(
                        run_id=self.run_id,
                        cycle_index=self.cycle_index,
                        stage="PROPOSAL",
                    )
                    self.assertEqual(tail_kind, recovery["recovery_tail_kind"])
                    delivery_path = (
                        Path(folder)
                        / "v32-current-root-agent-mailbox-v1"
                        / "cycles/0001/proposal/agent-delivery.json"
                    )
                    delivery_bytes = delivery_path.read_bytes()
                    recovered = store.submit_delivery(
                        run_id=self.run_id,
                        cycle_index=self.cycle_index,
                        stage="PROPOSAL",
                        expected_checkpoint_digest=claimed["checkpoint"][
                            CHECKPOINT_DIGEST_FIELD
                        ],
                        current_codex_presentation_envelope=(
                            presentation_envelope
                        ),
                        expected_current_codex_presentation_digest=(
                            presentation_envelope[
                                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                            ]
                        ),
                        delivered_at="2026-08-07T00:16:29Z",
                        payload_utf8="second payload must lose",
                    )
                    self.assertEqual(delivery_bytes, delivery_path.read_bytes())
                    self.assertEqual(
                        "2026-08-07T00:16:20Z",
                        recovered["agent_delivery"]["delivered_at"],
                    )
                    self.assertEqual(
                        self.fx["proposal_payload"],
                        recovered["agent_delivery"]["payload_utf8"],
                    )
                    continue

                delivered = submit()
                failure = (
                    mock.patch.object(
                        store, "_write_document", side_effect=fail_receipt
                    )
                    if tail_kind == "CONSUMPTION_ONLY"
                    else mock.patch.object(
                        store, "_commit", side_effect=fail_checkpoint
                    )
                )
                with failure, self.assertRaisesRegex(
                    V32CurrentRootAgentMailboxStoreError, "injected"
                ):
                    store.consume_delivery(
                        run_id=self.run_id,
                        cycle_index=self.cycle_index,
                        stage="PROPOSAL",
                        expected_checkpoint_digest=delivered["checkpoint"][
                            CHECKPOINT_DIGEST_FIELD
                        ],
                        consumed_at="2026-08-07T00:16:30Z",
                    )
                recovery = store.load_verified_recovery_stage_view(
                    run_id=self.run_id,
                    cycle_index=self.cycle_index,
                    stage="PROPOSAL",
                )
                self.assertEqual(tail_kind, recovery["recovery_tail_kind"])
                consumption_path = (
                    Path(folder)
                    / "v32-current-root-agent-mailbox-v1"
                    / "cycles/0001/proposal/agent-consumption.json"
                )
                consumption_bytes = consumption_path.read_bytes()
                recovered = store.consume_delivery(
                    run_id=self.run_id,
                    cycle_index=self.cycle_index,
                    stage="PROPOSAL",
                    expected_checkpoint_digest=delivered["checkpoint"][
                        CHECKPOINT_DIGEST_FIELD
                    ],
                    consumed_at="2026-08-07T00:16:39Z",
                )
                self.assertEqual(
                    consumption_bytes, consumption_path.read_bytes()
                )
                self.assertEqual(
                    "2026-08-07T00:16:30Z",
                    recovered["agent_consumption"]["consumed_at"],
                )
                self.assertEqual(
                    "CONSUMED",
                    recovered["checkpoint"]["stage_states"]["PROPOSAL"][
                        "status"
                    ],
                )


if __name__ == "__main__":
    unittest.main()
