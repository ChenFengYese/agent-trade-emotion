from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v31_semantic_compiler as semantic_fixture
from trade_system.theory_paper_v2.domain import v311_agent_lifecycle_v1 as lifecycle
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    build_outcome_clock_policy,
)
from trade_system.theory_paper_v2.domain.v31_agent_transport import (
    build_v31_agent_claim,
    build_v31_agent_delivery,
    build_v31_agent_request,
    build_v31_consume_receipt,
    reserve_v31_agent_attempt,
    seal_v31_transport_evidence,
)
from trade_system.theory_paper_v2.domain.v31_cycle_authoring import (
    seal_v31_proposal_authoring_packet,
)
from trade_system.theory_paper_v2.domain.v311_agent_lifecycle_v1 import (
    AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    V311_QUALIFICATION_AGENT_SUPPORT_SPECS,
    V311_QUALIFICATION_AGENT_SUPPORT_KEYS,
    V311_QUALIFICATION_CONTEXT_PROFILE,
    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
    build_v311_agent_context_consumption_v1,
    build_v311_agent_input_context_v1,
    build_v311_successor_commit_envelope_v1,
    build_v311_theory_addendum_semantic_document_v1,
    verify_v311_agent_context_consumption_v1,
    verify_v311_agent_input_context_with_packet_v1,
    verify_v311_successor_commit_envelope_v1,
    verify_v311_successor_commit_envelope_full_v1,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)


def _binding(
    name: str,
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
) -> dict[str, str]:
    return {
        "relative_ref": f"fixtures/{name}.json",
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic_digest,
        "physical_sha256": "f" * 64,
    }


def _support(
    addendum_binding: dict[str, str],
) -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    documents: dict[str, dict] = {}
    bindings: dict[str, dict[str, str]] = {}
    for index, name in enumerate(sorted(V311_QUALIFICATION_AGENT_SUPPORT_KEYS)):
        if name == "theory_addendum":
            document = build_v311_theory_addendum_semantic_document_v1(
                theory_addendum_binding=addendum_binding,
                markdown_utf8="# Frozen V3.1.1 addendum\n\nExact Agent input.\n",
            )
            documents[name] = document
            bindings[name] = _binding(
                name,
                document["schema_id"],
                THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
                document[THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD],
            )
            continue
        schema_id, digest_field = V311_QUALIFICATION_AGENT_SUPPORT_SPECS[name]
        document = self_digest(
            {
                "schema_id": schema_id,
                "schema_version": "1.0.0",
                "ordinal": index,
            },
            digest_field,
        )
        documents[name] = document
        bindings[name] = _binding(
            name,
            schema_id,
            digest_field,
            document[digest_field],
        )
    return documents, bindings


class V311AgentLifecycleV1Tests(unittest.TestCase):
    def _fixture(self):
        typed_patcher = patch.object(
            lifecycle,
            "_verify_typed_support_document",
            side_effect=lambda *, name, document, support_documents: (
                verify_self_digest(
                    document,
                    V311_QUALIFICATION_AGENT_SUPPORT_SPECS[name][1],
                )
            ),
        )
        typed_patcher.start()
        self.addCleanup(typed_patcher.stop)
        temporary = tempfile.TemporaryDirectory()
        store = LocalV31AgentTransportStore(Path(temporary.name))
        qualification_packet, dataset, mark_id = semantic_fixture._materials(
            store,
            qualification_root=Path(temporary.name) / "qualification",
        )
        current_authority_binding = _binding(
            "current-authority",
            "theory_paper_v31_current_research_authority",
            "authority_digest",
            "a" * 64,
        )
        packet = seal_v31_proposal_authoring_packet(
            run_id=qualification_packet["run_id"],
            cycle_index=qualification_packet["cycle_index"],
            decision_at=qualification_packet["decision_at"],
            symbol=qualification_packet["symbol"],
            cycle_source_admission_binding=_binding(
                "cycle-source-admission",
                "theory_paper_v31_cycle_source_admission",
                "cycle_source_admission_digest",
                "c" * 64,
            ),
            source_qualification_completion_binding=qualification_packet[
                "source_qualification_completion_binding"
            ],
            information_event_bindings=qualification_packet[
                "information_event_bindings"
            ],
            pit_dataset_binding=qualification_packet["pit_dataset_binding"],
            association_estimation_receipt_bindings=qualification_packet[
                "association_estimation_receipt_bindings"
            ],
            authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
            theory_approval_binding=qualification_packet["authority_context"][
                "theory_approval_binding"
            ],
            experiment_subject_binding=qualification_packet[
                "authority_context"
            ]["experiment_subject_binding"],
            active_authority_binding=current_authority_binding,
            previous_head_bindings=qualification_packet[
                "previous_head_bindings"
            ],
        )
        envelope = semantic_fixture._envelope(packet, dataset, mark_id)
        packet_binding = _binding(
            "authoring-packet",
            packet["schema_id"],
            "authoring_packet_digest",
            packet["authoring_packet_digest"],
        )
        addendum_text = "# Frozen V3.1.1 addendum\n\nExact Agent input.\n"
        addendum_binding = {
            "path": "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md",
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED",
            "physical_sha256": hashlib.sha256(
                addendum_text.encode("utf-8")
            ).hexdigest(),
        }
        documents, bindings = _support(addendum_binding)
        context = build_v311_agent_input_context_v1(
            run_id=packet["run_id"],
            cycle_index=1,
            context_profile=V311_QUALIFICATION_CONTEXT_PROFILE,
            created_at="2026-08-07T00:00:00Z",
            base_authoring_packet=packet,
            base_authoring_packet_binding=packet_binding,
            current_authority_binding=current_authority_binding,
            theory_addendum_binding=addendum_binding,
            support_documents=documents,
            support_bindings=bindings,
        )
        context_binding = _binding(
            "agent-input-context",
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
            context[AGENT_INPUT_CONTEXT_DIGEST_FIELD],
        )
        return temporary, packet, envelope, packet_binding, context, context_binding

    def test_input_context_reconstructs_and_rejects_support_drift(self) -> None:
        temporary, packet, _envelope, _packet_binding, context, _binding_value = (
            self._fixture()
        )
        self.addCleanup(temporary.cleanup)
        verify_v311_agent_input_context_with_packet_v1(
            context, base_authoring_packet=packet
        )
        tampered = copy.deepcopy(context)
        first = next(iter(tampered["support_documents"]))
        tampered["support_documents"][first]["ordinal"] = 999
        with self.assertRaises(ValueError):
            verify_v311_agent_input_context_with_packet_v1(
                tampered, base_authoring_packet=packet
            )
        addendum_tampered = copy.deepcopy(context)
        addendum_tampered["support_documents"]["theory_addendum"][
            "markdown_utf8"
        ] += "tampered"
        with self.assertRaises(ValueError):
            verify_v311_agent_input_context_with_packet_v1(
                addendum_tampered, base_authoring_packet=packet
            )
        cross_drifted = copy.deepcopy(context)
        cross_drifted["theory_addendum_binding"]["version"] = "3.1.1-drift"
        cross_drifted = self_digest(
            {
                key: value
                for key, value in cross_drifted.items()
                if key != AGENT_INPUT_CONTEXT_DIGEST_FIELD
            },
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(ValueError, "ADDENDUM_CROSS_BINDING"):
            verify_v311_agent_input_context_with_packet_v1(
                cross_drifted, base_authoring_packet=packet
            )

        for name in V311_QUALIFICATION_AGENT_SUPPORT_SPECS:
            type_confused = copy.deepcopy(context)
            support = self_digest(
                {
                    "schema_id": f"fixture:wrong_role:{name}",
                    "schema_version": "1.0.0",
                    "claimed_role": name,
                },
                "fixture_digest",
            )
            type_confused["support_documents"][name] = support
            type_confused["support_bindings"][name].update(
                {
                    "schema_id": support["schema_id"],
                    "digest_field": "fixture_digest",
                    "semantic_digest": support["fixture_digest"],
                }
            )
            type_confused.pop(AGENT_INPUT_CONTEXT_DIGEST_FIELD)
            type_confused = self_digest(
                type_confused, AGENT_INPUT_CONTEXT_DIGEST_FIELD
            )
            with self.subTest(role=name), self.assertRaisesRegex(
                ValueError, "SUPPORT_BINDING_INVALID"
            ):
                verify_v311_agent_input_context_with_packet_v1(
                    type_confused, base_authoring_packet=packet
                )

    def test_typed_support_rejects_minimal_same_schema_impostor(self) -> None:
        clock = build_outcome_clock_policy()
        self.assertEqual(
            clock["clock_policy_digest"],
            lifecycle._verify_typed_support_document(
                name="clock_policy",
                document=clock,
                support_documents={"clock_policy": clock},
            ),
        )
        impostor = self_digest(
            {
                "schema_id": "theory_paper_v31_outcome_clock_policy_v2",
                "schema_version": "2.0.0",
                "claimed_role": "clock_policy",
            },
            "clock_policy_digest",
        )
        with self.assertRaises(ValueError):
            lifecycle._verify_typed_support_document(
                name="clock_policy",
                document=impostor,
                support_documents={"clock_policy": impostor},
            )

    def test_consumption_binds_single_proposal_delivery_and_root_role(self) -> None:
        temporary, packet, envelope, packet_binding, context, context_binding = (
            self._fixture()
        )
        self.addCleanup(temporary.cleanup)
        attempt = reserve_v31_agent_attempt(
            run_id=packet["run_id"],
            cycle_index=1,
            stage="PROPOSAL",
            reserved_at="2026-08-07T00:01:00Z",
            checkpoint_digest_before_reservation="1" * 64,
        )
        request = build_v31_agent_request(
            attempt=attempt,
            created_at="2026-08-07T00:01:01Z",
            authoring_packet_binding=packet_binding,
        )
        claim = build_v31_agent_claim(
            request=request,
            attempt=attempt,
            claimed_at="2026-08-07T00:01:02Z",
        )
        delivery = build_v31_agent_delivery(
            request=request,
            attempt=attempt,
            claim=claim,
            payload=envelope,
            delivered_at="2026-08-07T00:01:03Z",
            authoring_packet=packet,
        )
        consume = build_v31_consume_receipt(
            request=request,
            attempt=attempt,
            claim=claim,
            delivery=delivery,
            consumed_at="2026-08-07T00:01:04Z",
            authoring_packet=packet,
        )
        proposal_bindings = {
            "attempt_binding": _binding(
                "proposal-attempt",
                attempt["schema_id"],
                "attempt_digest",
                attempt["attempt_digest"],
            ),
            "request_binding": _binding(
                "proposal-request",
                request["schema_id"],
                "request_digest",
                request["request_digest"],
            ),
            "claim_binding": _binding(
                "proposal-claim",
                claim["schema_id"],
                "claim_digest",
                claim["claim_digest"],
            ),
            "delivery_binding": _binding(
                "proposal-delivery",
                delivery["schema_id"],
                "delivery_digest",
                delivery["delivery_digest"],
            ),
            "consume_binding": _binding(
                "proposal-consume",
                consume["schema_id"],
                "consume_digest",
                consume["consume_digest"],
            ),
            "attempt_count": 1,
        }
        selection_bindings = {
            "attempt_binding": _binding(
                "selection-attempt",
                "theory_paper_v31_agent_attempt",
                "attempt_digest",
                "2" * 64,
            ),
            "request_binding": _binding(
                "selection-request",
                "theory_paper_v31_agent_request",
                "request_digest",
                "3" * 64,
            ),
            "claim_binding": _binding(
                "selection-claim",
                "theory_paper_v31_agent_claim",
                "claim_digest",
                "4" * 64,
            ),
            "delivery_binding": _binding(
                "selection-delivery",
                "theory_paper_v31_agent_delivery",
                "delivery_digest",
                "5" * 64,
            ),
            "consume_binding": _binding(
                "selection-consume",
                "theory_paper_v31_agent_consume_receipt",
                "consume_digest",
                "6" * 64,
            ),
            "attempt_count": 1,
        }
        evidence = seal_v31_transport_evidence(
            run_id=packet["run_id"],
            cycle_index=1,
            completed_at="2026-08-07T00:02:00Z",
            stages={
                "PROPOSAL": proposal_bindings,
                "SELECTION": selection_bindings,
            },
            proposal_payload_digest=envelope[
                "agent_authoring_envelope_digest"
            ],
            selection_payload_digest="7" * 64,
        )
        evidence_binding = _binding(
            "transport-evidence",
            evidence["schema_id"],
            "transport_evidence_digest",
            evidence["transport_evidence_digest"],
        )
        consumption = build_v311_agent_context_consumption_v1(
            agent_input_context=context,
            agent_input_context_binding=context_binding,
            base_authoring_packet=packet,
            proposal_attempt=attempt,
            proposal_attempt_binding=proposal_bindings["attempt_binding"],
            proposal_request=request,
            proposal_request_binding=proposal_bindings["request_binding"],
            proposal_claim=claim,
            proposal_delivery=delivery,
            proposal_delivery_binding=proposal_bindings["delivery_binding"],
            proposal_consume=consume,
            proposal_consume_binding=proposal_bindings["consume_binding"],
            transport_evidence=evidence,
            transport_evidence_binding=evidence_binding,
        )
        verify_v311_agent_context_consumption_v1(
            consumption,
            agent_input_context=context,
            base_authoring_packet=packet,
            proposal_attempt=attempt,
            proposal_request=request,
            proposal_claim=claim,
            proposal_delivery=delivery,
            proposal_consume=consume,
            transport_evidence=evidence,
        )
        self.assertEqual(
            "PRACTICAL_CODEX_NOT_MODEL_ATTESTED",
            consumption["transport_attestation_level"],
        )
        self.assertTrue(consumption["single_attempt_verified"])
        self.assertNotIn("current_root_identity_verified", consumption)

        base_digest = "8" * 64
        base_material = {
            "run_id": packet["run_id"],
            "cycle_index": 1,
            "authoring_packet_digest": packet["authoring_packet_digest"],
            "transport_evidence_binding": evidence_binding,
            "assembly_bundle": {
                "expected_artifact_digests": {"STATE_ACCEPTED": "9" * 64}
            },
            "support_bindings": {"fixture": context_binding},
        }
        base_binding = _binding(
            "base-commit-material",
            "theory_paper_v31_successor_cycle_commit_material",
            "successor_commit_material_digest",
            base_digest,
        )
        consumption_binding = _binding(
            "agent-context-consumption",
            AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
            consumption[AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD],
        )
        with patch(
            "trade_system.theory_paper_v2.domain.v311_agent_lifecycle_v1."
            "verify_v31_successor_cycle_commit_material_v2",
            return_value=base_digest,
        ):
            commit_envelope = build_v311_successor_commit_envelope_v1(
                base_successor_commit_material=base_material,
                base_successor_commit_material_binding=base_binding,
                experiment_contract={},
                agent_input_context=context,
                agent_input_context_binding=context_binding,
                agent_context_consumption=consumption,
                agent_context_consumption_binding=consumption_binding,
                sealed_at="2026-08-07T00:03:00Z",
            )
            verify_v311_successor_commit_envelope_v1(
                commit_envelope,
                base_successor_commit_material=base_material,
                experiment_contract={},
                agent_input_context=context,
                agent_context_consumption=consumption,
            )
            verify_v311_successor_commit_envelope_full_v1(
                commit_envelope,
                base_successor_commit_material=base_material,
                experiment_contract={},
                agent_input_context=context,
                agent_context_consumption=consumption,
                base_authoring_packet=packet,
                proposal_attempt=attempt,
                proposal_request=request,
                proposal_claim=claim,
                proposal_delivery=delivery,
                proposal_consume=consume,
                transport_evidence=evidence,
            )
            drifted = copy.deepcopy(commit_envelope)
            drifted["agent_context_consumption_digest"] = "0" * 64
            drifted = self_digest(
                {
                    key: value
                    for key, value in drifted.items()
                    if key != V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD
                },
                V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
            )
            with self.assertRaises(ValueError):
                verify_v311_successor_commit_envelope_v1(
                    drifted,
                    base_successor_commit_material=base_material,
                    experiment_contract={},
                    agent_input_context=context,
                    agent_context_consumption=consumption,
                )
        self.assertEqual(
            V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
            commit_envelope["schema_id"],
        )
        self.assertEqual(
            commit_envelope[V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD],
            commit_envelope["successor_commit_envelope_digest"],
        )


if __name__ == "__main__":
    unittest.main()
