from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.infrastructure.agent_adapter import (
    AgentAdapterError,
    AgentTransportResult,
    OneShotAgentAdapter,
)
from trade_system.theory_paper_v2.infrastructure.content_store import (
    ContentAddressedStore,
)


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_id", "schema_version", "path_refs"],
    "properties": {
        "schema_id": {"const": "agent_proposal_envelope"},
        "schema_version": {"const": "1.0.0"},
        "path_refs": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
}


def receipt(role: str = "PROPOSER") -> dict:
    return self_digest(
        {
            "role_id": role,
            "verdict": "PASS",
            "callable": True,
            "allowed_caller": "APPLICATION_DECISION_SESSION",
            "execution_kind": "GENERATIVE_AGENT_ROLE",
        },
        "receipt_digest",
    )


class AgentAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ContentAddressedStore(Path(self.temp.name))
        self.input_bytes = canonical_bytes({"role": "PROPOSER"})
        import hashlib

        self.input_digest = hashlib.sha256(self.input_bytes).hexdigest()
        self.output = canonical_bytes(
            {
                "schema_id": "agent_proposal_envelope",
                "schema_version": "1.0.0",
                "path_refs": ["primary", "null", "unknown"],
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def adapter(self, result: AgentTransportResult) -> OneShotAgentAdapter:
        calls = []

        def transport(role: str, payload: bytes, schema: str) -> AgentTransportResult:
            calls.append((role, payload, schema))
            if len(calls) > 1:
                raise AssertionError("role called more than once")
            return result

        return OneShotAgentAdapter(content_store=self.store, transport=transport)

    def invoke(self, adapter: OneShotAgentAdapter):
        return adapter.invoke(
            decision_session_id="session-1",
            role_id="PROPOSER",
            canonical_input=self.input_bytes,
            expected_input_digest=self.input_digest,
            expected_output_schema_id="agent_proposal_envelope",
            output_schema=OUTPUT_SCHEMA,
            skill_resolution_receipt=receipt(),
        )

    def test_one_shot_valid_output_is_archived_exactly(self) -> None:
        result = self.invoke(
            self.adapter(AgentTransportResult(output_bytes=self.output))
        )
        self.assertEqual("PROPOSER", result.role_id)
        archived = self.store.get(
            "session-1/PROPOSER",
            f"raw-agent-result-{self.input_digest}",
            result.archived_blob_digest,
        )
        self.assertEqual(self.output, archived)

    def test_tool_or_repository_access_fails_closed(self) -> None:
        for result in (
            AgentTransportResult(self.output, tool_call_names=("browser",)),
            AgentTransportResult(self.output, repository_accessed=True),
            AgentTransportResult(self.output, reused_thread=True),
            AgentTransportResult(self.output, execution_attempted=True),
        ):
            with self.assertRaisesRegex(
                AgentAdapterError, "ROLE_INPUT_PROJECTION_INVALID_NO_COMMIT"
            ):
                self.invoke(self.adapter(result))

    def test_bad_skill_receipt_or_input_digest_fails_before_model(self) -> None:
        adapter = self.adapter(AgentTransportResult(self.output))
        with self.assertRaisesRegex(
            AgentAdapterError, "ROLE_INPUT_BYTES_DIGEST_MISMATCH_NO_COMMIT"
        ):
            adapter.invoke(
                decision_session_id="session-1",
                role_id="PROPOSER",
                canonical_input=self.input_bytes,
                expected_input_digest="0" * 64,
                expected_output_schema_id="agent_proposal_envelope",
                output_schema=OUTPUT_SCHEMA,
                skill_resolution_receipt=receipt(),
            )
        with self.assertRaisesRegex(
            AgentAdapterError, "ROLE_UNAVAILABLE_SESSION_INCOMPLETE"
        ):
            self.adapter(AgentTransportResult(self.output)).invoke(
                decision_session_id="session-1",
                role_id="PROPOSER",
                canonical_input=self.input_bytes,
                expected_input_digest=self.input_digest,
                expected_output_schema_id="agent_proposal_envelope",
                output_schema=OUTPUT_SCHEMA,
                skill_resolution_receipt=receipt("SELECTOR"),
            )

    def test_schema_escape_fails_closed(self) -> None:
        invalid = canonical_bytes(
            {
                "schema_id": "agent_proposal_envelope",
                "schema_version": "1.0.0",
                "path_refs": ["primary"],
                "commit": True,
            }
        )
        with self.assertRaisesRegex(ValueError, "SCHEMA_ADDITIONAL_PROPERTY"):
            self.invoke(self.adapter(AgentTransportResult(invalid)))


if __name__ == "__main__":
    unittest.main()
