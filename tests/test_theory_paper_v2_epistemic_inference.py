from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.epistemic_inference import (
    EpistemicInferenceError,
    build_public_inference_trace,
)
from trade_system.theory_paper_v2.presentation.continuous_fixture_composition import (
    run_continuous_fixture,
)


class PublicEpistemicInferenceTests(unittest.TestCase):
    def _cycle_documents(self, root: Path, cycle_index: int) -> dict[str, dict]:
        receipt = load_json_strict(
            root / f"evidence-receipts/cycle-{cycle_index:04d}.json"
        )
        names = {
            "market_snapshot": "market_information_snapshot_digest",
            "sentiment_state": "sentiment_state_digest",
            "hypothesis_registry": "hypothesis_registry_digest",
            "expectation_ledger": "expectation_ledger_digest",
            "agent_context": "agent_context_digest",
            "agent_proposal": "agent_proposal_digest",
            "trace": "public_inference_trace_digest",
        }
        return {
            name: load_json_strict(root / receipt["artifact_refs"][binding])
            for name, binding in names.items()
        }

    @staticmethod
    def _reseal_proposal(proposal: dict, claims: list[dict]) -> dict:
        changed = {**proposal, "public_inference_claims": claims}
        changed.pop("agent_proposal_digest")
        return self_digest(changed, "agent_proposal_digest")

    @staticmethod
    def _build(documents: dict[str, dict], proposal: dict, claims: list[dict]) -> dict:
        return build_public_inference_trace(
            market_snapshot=documents["market_snapshot"],
            sentiment_state=documents["sentiment_state"],
            hypothesis_registry=documents["hypothesis_registry"],
            expectation_ledger=documents["expectation_ledger"],
            agent_context=documents["agent_context"],
            agent_proposal=proposal,
            claims=claims,
            decision_at=documents["market_snapshot"]["as_of"],
        )

    def test_trace_is_proposal_bound_and_public_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(runtime_root=runtime_root, run_id="trace-contract")
            documents = self._cycle_documents(
                runtime_root / "trace-contract", cycle_index=2
            )
            proposal = documents["agent_proposal"]
            rebuilt = self._build(
                documents,
                proposal,
                copy.deepcopy(proposal["public_inference_claims"]),
            )
            verify_self_digest(rebuilt, "public_inference_trace_digest")
            self.assertEqual(
                documents["trace"]["public_inference_trace_digest"],
                rebuilt["public_inference_trace_digest"],
            )
            self.assertEqual(
                "PUBLIC_AUDITABLE_JUSTIFICATION_ONLY", rebuilt["trace_scope"]
            )
            self.assertFalse(rebuilt["private_chain_of_thought_recorded"])

            unbound = copy.deepcopy(proposal["public_inference_claims"])
            unbound.reverse()
            with self.assertRaisesRegex(
                EpistemicInferenceError, "INFERENCE_CLAIMS_NOT_PROPOSAL_BOUND"
            ):
                self._build(documents, proposal, unbound)

            quantified = {**proposal, "probability_pct": "60"}
            quantified.pop("agent_proposal_digest")
            quantified = self_digest(quantified, "agent_proposal_digest")
            with self.assertRaisesRegex(
                EpistemicInferenceError,
                "INFERENCE_UNCALIBRATED_QUANTIFICATION_FORBIDDEN",
            ):
                self._build(
                    documents,
                    quantified,
                    copy.deepcopy(quantified["public_inference_claims"]),
                )

            private_reasoning = {**proposal, "chain_of_thought": "not admissible"}
            private_reasoning.pop("agent_proposal_digest")
            private_reasoning = self_digest(
                private_reasoning, "agent_proposal_digest"
            )
            with self.assertRaisesRegex(
                EpistemicInferenceError, "INFERENCE_PRIVATE_REASONING_FORBIDDEN"
            ):
                self._build(
                    documents,
                    private_reasoning,
                    copy.deepcopy(private_reasoning["public_inference_claims"]),
                )

    def test_unknown_cannot_be_relabelled_as_support_and_claim_graph_is_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(runtime_root=runtime_root, run_id="trace-fail-closed")
            documents = self._cycle_documents(
                runtime_root / "trace-fail-closed", cycle_index=2
            )
            claims = copy.deepcopy(
                documents["agent_proposal"]["public_inference_claims"]
            )
            claims[0]["supporting_fact_ids"] = ["fact:c2:6"]
            proposal = self._reseal_proposal(documents["agent_proposal"], claims)
            with self.assertRaisesRegex(
                EpistemicInferenceError, "INFERENCE_FACT_ROLE_INVALID"
            ):
                self._build(documents, proposal, claims)

            claims = copy.deepcopy(
                documents["agent_proposal"]["public_inference_claims"]
            )
            claims[0]["prior_claim_ids"] = ["inference:c2:mechanism"]
            proposal = self._reseal_proposal(documents["agent_proposal"], claims)
            with self.assertRaisesRegex(
                EpistemicInferenceError, "INFERENCE_PRIOR_CLAIMS_INVALID"
            ):
                self._build(documents, proposal, claims)


if __name__ == "__main__":
    unittest.main()
