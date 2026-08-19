from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import (
    test_theory_paper_v2_v31_successor_qualification_v2 as qualification_fixture,
)
from tests.v311_typed_support_materials import (
    build_real_typed_qualification_supports,
)

from trade_system.theory_paper_v2.application.v31_agent_transport import (
    verify_completed_v31_authoring_transport,
)
from trade_system.theory_paper_v2.application.v31_successor_qualification_v2 import (
    compose_current_codex_durable_qualification_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    build_successor_codex_durable_qualification_v3,
    verify_successor_codex_durable_qualification_v3,
)
from trade_system.theory_paper_v2.domain.v311_agent_lifecycle_v1 import (
    AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD,
    V311_QUALIFICATION_AGENT_SUPPORT_KEYS,
    V311_QUALIFICATION_AGENT_SUPPORT_SPECS,
    V311_QUALIFICATION_CONTEXT_PROFILE,
    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
    build_v311_agent_context_consumption_v1,
    build_v311_agent_input_context_v1,
    build_v311_successor_commit_envelope_v1,
    build_v311_theory_addendum_semantic_document_v1,
)
from trade_system.theory_paper_v2.domain.v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as BASE_COMMIT_DIGEST_FIELD,
    SCHEMA_ID as BASE_COMMIT_SCHEMA_ID,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)
from trade_system.theory_paper_v2.presentation import (
    v311_successor_qualification_composition_v3 as qualification_composition,
)


PROJECT = Path(__file__).resolve().parents[1]
RUN_ID = "v31-prospective-btcusdt-20260806t183742z"
RUN_REF = f"agent-cluster/experiments/{RUN_ID}"
PREDECESSOR = "v31-earlier-permanently-failed-run"


def _binding(
    relative_ref: str,
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    physical_sha256: str = "f" * 64,
) -> dict[str, str]:
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic_digest,
        "physical_sha256": physical_sha256,
    }


class V311CodexDurableQualificationV3Tests(unittest.TestCase):
    def _material(self) -> tuple[dict, dict]:
        root = PROJECT / RUN_REF
        transport_store = LocalV31AgentTransportStore(root)
        research_store = LocalV31ResearchStore(root)
        terminal = verify_completed_v31_authoring_transport(
            store=transport_store,
            run_id=RUN_ID,
            cycle_index=1,
            expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        )
        packet = terminal["authoring_packet"]
        authority = research_store.read_document(
            relative_ref="genesis/current-authority.json",
            digest_field="authority_digest",
        )
        authority_binding = packet["authority_context"][
            "active_authority_binding"
        ]
        qualified_at = "2026-08-07T10:03:00Z"
        receipt_fixture = (
            qualification_fixture.V31SuccessorQualificationV2Tests()
        )
        public_source = receipt_fixture._source(
            run_id=RUN_ID,
            authority=authority,
            authority_binding=authority_binding,
            predecessor=PREDECESSOR,
        )
        with tempfile.TemporaryDirectory() as monitor_directory:
            outcome_monitor = receipt_fixture._monitor(
                run_id=RUN_ID,
                authority=authority,
                authority_binding=authority_binding,
                run_root=Path(monitor_directory),
                predecessor=PREDECESSOR,
            )
        schema_compatibility = (
            qualification_composition._build_schema_compatibility_receipt(
                project_root=PROJECT,
                source_qualification=public_source,
                clock_policy=outcome_monitor["clock_policy"],
                sealed_at="2026-08-07T10:02:30Z",
            )
        )
        base = compose_current_codex_durable_qualification_v2(
            project_root=PROJECT,
            run_root_ref=RUN_REF,
            run_id=RUN_ID,
            predecessor_run_id=PREDECESSOR,
            cycle_index=1,
            authority=authority,
            authority_binding=authority_binding,
            validated_authority_digest=authority["authority_digest"],
            source_qualification_v2_digest=public_source[
                "source_qualification_v2_digest"
            ],
            qualified_at=qualified_at,
        )

        addendum_bytes = (
            PROJECT / "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md"
        ).read_bytes()
        addendum_binding = {
            "path": "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md",
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED_TEST_INPUT",
            "physical_sha256": hashlib.sha256(addendum_bytes).hexdigest(),
        }
        supports: dict[str, dict] = {}
        support_bindings: dict[str, dict[str, str]] = {}
        typed_supports = build_real_typed_qualification_supports(
            project_root=PROJECT,
            run_id=RUN_ID,
            public_source_qualification=public_source,
            outcome_monitor_qualification=outcome_monitor,
            schema_compatibility=schema_compatibility,
        )
        for index, name in enumerate(
            sorted(V311_QUALIFICATION_AGENT_SUPPORT_KEYS)
        ):
            if name == "theory_addendum":
                document = build_v311_theory_addendum_semantic_document_v1(
                    theory_addendum_binding=addendum_binding,
                    markdown_utf8=addendum_bytes.decode("utf-8"),
                )
                digest_field = THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD
            else:
                schema_id, digest_field = (
                    V311_QUALIFICATION_AGENT_SUPPORT_SPECS[name]
                )
                document = typed_supports[name]
            supports[name] = document
            support_bindings[name] = _binding(
                f"qualification-support/{name}.json",
                document["schema_id"],
                digest_field,
                document[digest_field],
            )
        context = build_v311_agent_input_context_v1(
            run_id=RUN_ID,
            cycle_index=1,
            context_profile=V311_QUALIFICATION_CONTEXT_PROFILE,
            created_at="2026-08-06T19:06:45Z",
            base_authoring_packet=packet,
            base_authoring_packet_binding=terminal["authoring_packet_binding"],
            current_authority_binding=authority_binding,
            theory_addendum_binding=addendum_binding,
            support_documents=supports,
            support_bindings=support_bindings,
        )
        context_binding = _binding(
            "successor-v311-agent-context/cycles/0001/agent-input-context.json",
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
            context[AGENT_INPUT_CONTEXT_DIGEST_FIELD],
        )
        proposal_state = terminal["checkpoint"]["stage_states"]["PROPOSAL"]
        proposal = {
            name: transport_store.read_bound_document(
                proposal_state[f"{name}_binding"]
            )
            for name in ("attempt", "request", "claim", "delivery", "consume")
        }
        evidence_ref = terminal["transport_evidence_binding"]["relative_ref"]
        evidence_binding = transport_store.artifact_binding(
            relative_ref=evidence_ref,
            digest_field="transport_evidence_digest",
        )
        consumption = build_v311_agent_context_consumption_v1(
            agent_input_context=context,
            agent_input_context_binding=context_binding,
            base_authoring_packet=packet,
            proposal_attempt=proposal["attempt"],
            proposal_attempt_binding=proposal_state["attempt_binding"],
            proposal_request=proposal["request"],
            proposal_request_binding=proposal_state["request_binding"],
            proposal_claim=proposal["claim"],
            proposal_delivery=proposal["delivery"],
            proposal_delivery_binding=proposal_state["delivery_binding"],
            proposal_consume=proposal["consume"],
            proposal_consume_binding=proposal_state["consume_binding"],
            transport_evidence=terminal["transport_evidence"],
            transport_evidence_binding=evidence_binding,
        )
        consumption_binding = _binding(
            "successor-v311-agent-context/cycles/0001/agent-context-consumption.json",
            AGENT_CONTEXT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
            consumption[AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD],
        )
        base_material = self_digest({
            "run_id": RUN_ID,
            "cycle_index": 1,
            "active_authority_digest": authority["authority_digest"],
            "authoring_packet_digest": packet["authoring_packet_digest"],
            "transport_evidence_binding": evidence_binding,
            "assembly_bundle": {
                "expected_artifact_digests": {
                    "STATE_ACCEPTED": base["accepted_state_digest"]
                }
            },
            "support_bindings": {
                "qualification_context": context_binding
            },
        }, BASE_COMMIT_DIGEST_FIELD)
        base_commit_digest = base_material[BASE_COMMIT_DIGEST_FIELD]
        base_commit_binding = _binding(
            "successor-commit-v2/cycles/0001/commit-material.json",
            BASE_COMMIT_SCHEMA_ID,
            BASE_COMMIT_DIGEST_FIELD,
            base_commit_digest,
        )
        with patch(
            "trade_system.theory_paper_v2.domain.v311_agent_lifecycle_v1."
            "verify_v31_successor_cycle_commit_material_v2",
            return_value=base_commit_digest,
        ):
            commit = build_v311_successor_commit_envelope_v1(
                base_successor_commit_material=base_material,
                base_successor_commit_material_binding=base_commit_binding,
                experiment_contract=terminal["experiment_subject"],
                agent_input_context=context,
                agent_input_context_binding=context_binding,
                agent_context_consumption=consumption,
                agent_context_consumption_binding=consumption_binding,
                sealed_at="2026-08-07T10:02:00Z",
            )
            artifacts = {
                **base["artifact_bindings"],
                "agent_input_context": context_binding,
                "agent_context_consumption": consumption_binding,
                "base_successor_commit_material": base_commit_binding,
                "successor_commit_envelope": _binding(
                    "successor-v311-agent-context/cycles/0001/successor-commit-envelope.json",
                    V311_SUCCESSOR_COMMIT_ENVELOPE_SCHEMA_ID,
                    V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
                    commit[V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD],
                ),
            }
            receipt = build_successor_codex_durable_qualification_v3(
                base_codex_qualification_v2=base,
                qualified_at=qualified_at,
                experiment_contract=terminal["experiment_subject"],
                canonical_packet=packet,
                proposal_attempt=proposal["attempt"],
                proposal_request=proposal["request"],
                proposal_claim=proposal["claim"],
                proposal_delivery=proposal["delivery"],
                proposal_consume=proposal["consume"],
                transport_evidence=terminal["transport_evidence"],
                agent_input_context=context,
                agent_context_consumption=consumption,
                base_successor_commit_material=base_material,
                successor_commit_envelope=commit,
                artifact_bindings=artifacts,
            )
        return base, receipt

    def test_v3_binds_context_consumption_commit_and_base_acceptance(self) -> None:
        base, receipt = self._material()
        self.assertEqual(
            receipt[CODEX_QUALIFICATION_V3_DIGEST_FIELD],
            verify_successor_codex_durable_qualification_v3(receipt),
        )
        self.assertEqual(
            base["accepted_state_digest"], receipt["accepted_state_digest"]
        )
        self.assertEqual(
            {
                "agent_input_context",
                "agent_context_consumption",
                "base_successor_commit_material",
                "successor_commit_envelope",
            },
            set(receipt["artifact_bindings"]) - set(base["artifact_bindings"]),
        )
        self.assertTrue(
            receipt["qualification_summary"]["v2_only_receipt_rejected"]
        )

    def test_closed_receipt_rejects_binding_drift_and_v2_document(self) -> None:
        base, receipt = self._material()
        tampered = copy.deepcopy(receipt)
        tampered["artifact_bindings"]["agent_input_context"][
            "semantic_digest"
        ] = "0" * 64
        tampered = self_digest(
            {
                key: value
                for key, value in tampered.items()
                if key != CODEX_QUALIFICATION_V3_DIGEST_FIELD
            },
            CODEX_QUALIFICATION_V3_DIGEST_FIELD,
        )
        with self.assertRaises(ValueError):
            verify_successor_codex_durable_qualification_v3(tampered)
        with self.assertRaises(ValueError):
            verify_successor_codex_durable_qualification_v3(base)


if __name__ == "__main__":
    unittest.main()
