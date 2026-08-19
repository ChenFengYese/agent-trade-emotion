from __future__ import annotations

import copy
import unittest

from trade_system.theory_paper_v2.domain.agent_research_contract import (
    AgentResearchContractError,
    seal_v31_agent_proposal,
    seal_v31_inputs_receipt,
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest


def inputs_receipt() -> dict:
    return seal_v31_inputs_receipt(
        run_id="v31-local-qualification",
        cycle_index=1,
        decision_at="2026-08-06T10:00:00Z",
        symbol="BTCUSDT",
        information_event_digests=("a" * 64,),
        information_revision_registry_digest="7" * 64,
        pit_dataset_digest="b" * 64,
        datum_revision_registry_digest="8" * 64,
        sentiment_state_digest="9" * 64,
        sentiment_change_digest="0" * 64,
        prior_graph_digest="c" * 64,
        previous_accepted_state_digest=None,
        authority_snapshot_sha256="d" * 64,
    )


def proposal() -> dict:
    return seal_v31_agent_proposal(
        inputs_receipt=inputs_receipt(),
        sentiment_state_digest="9" * 64,
        sentiment_change_digest="0" * 64,
        graph_delta_digest="1" * 64,
        hypothesis_registry_digest="2" * 64,
        expectation_ledger_digest="3" * 64,
        probability_cloud_digest="4" * 64,
        scenario_path_set_digest="5" * 64,
        candidate_bindings={"candidate:wait": "6" * 64},
        information_interpretations=(
            "The observed communication can have more than one audience response.",
        ),
        competing_explanations=("The reaction may reflect a common shock.",),
        unknowns=("Audience positions remain unknown.",),
        requested_observations=("Observe the next closed public bar.",),
        hypothesis_novelty_rationales={
            "hypothesis:new": "It adds a distinct observable falsifier."
        },
        limitations=("Local non-executable qualification only.",),
    )


class V31AgentResearchContractTests(unittest.TestCase):
    def test_inputs_and_proposal_are_canonical_and_non_executable(self) -> None:
        admitted_inputs = inputs_receipt()
        admitted_proposal = proposal()
        self.assertEqual(
            admitted_inputs["inputs_receipt_digest"],
            verify_v31_inputs_receipt(admitted_inputs),
        )
        self.assertEqual(
            admitted_proposal["agent_proposal_digest"],
            verify_v31_agent_proposal(
                admitted_proposal, inputs_receipt=admitted_inputs
            ),
        )
        self.assertFalse(admitted_proposal["selection_fields_admitted"])
        self.assertFalse(admitted_proposal["executable"])

    def test_proposal_cannot_bind_a_different_input_boundary(self) -> None:
        different_inputs = seal_v31_inputs_receipt(
            run_id="v31-local-qualification",
            cycle_index=1,
            decision_at="2026-08-06T10:00:00Z",
            symbol="BTCUSDT",
            information_event_digests=("f" * 64,),
            information_revision_registry_digest="7" * 64,
            pit_dataset_digest="b" * 64,
            datum_revision_registry_digest="8" * 64,
            sentiment_state_digest="9" * 64,
            sentiment_change_digest="0" * 64,
            prior_graph_digest="c" * 64,
            previous_accepted_state_digest=None,
            authority_snapshot_sha256="d" * 64,
        )
        with self.assertRaisesRegex(
            AgentResearchContractError, "PROPOSAL_CANONICAL_FORM_INVALID"
        ):
            verify_v31_agent_proposal(
                proposal(), inputs_receipt=different_inputs
            )

    def test_re_signed_selected_field_is_still_forbidden(self) -> None:
        forged = copy.deepcopy(proposal())
        forged["information_interpretations"] = [
            {"selected_candidate_id": "candidate:wait"}
        ]
        forged = self_digest(forged, "agent_proposal_digest")
        with self.assertRaisesRegex(
            AgentResearchContractError, "SELECTION_FIELD_FORBIDDEN"
        ):
            verify_v31_agent_proposal(forged, inputs_receipt=inputs_receipt())


if __name__ == "__main__":
    unittest.main()
