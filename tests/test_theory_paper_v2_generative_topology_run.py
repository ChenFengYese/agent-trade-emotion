from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trade_system.theory_paper_v2.application.generative_topology_run import (
    FORMAL_CONTRACT_DIGEST,
    FORMAL_TOPOLOGY_IDS,
    FormalObservationScores,
    FrozenInstruction,
    GenerativeTopologyRunError,
    ModelAttemptResult,
    ModelAttemptStatus,
    ModelCallRequest,
    ModelTransportCapability,
    PairedGenerativeRunRequest,
    ProjectionValue,
    ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA,
    RunEvidenceClass,
    SEMANTIC_MODEL_OUTPUT_SCHEMA,
    UsageRecord,
    admit_formal_generation_receipt,
    build_paired_observation_from_generation,
    build_resolved_role_input_document,
    make_deterministic_object_ref,
    role_input_transport_repair_receipt,
    run_paired_generative_topologies,
    validate_formal_experiment_contract,
    wrap_semantic_model_output,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    verify_self_digest,
)
from trade_system.theory_paper_v2.infrastructure.generative_topology import (
    CodexExecGenerativeTransport,
    PairedRunArchiveError,
    WriteOncePairedRunArchive,
    parse_codex_exec_jsonl,
)


ROOT = Path(__file__).resolve().parents[1]


def _ref(name: str) -> dict:
    return make_deterministic_object_ref(
        schema_id=f"{name}_manifest",
        schema_version="1.0.0",
        object_id=f"{name}:frozen:1",
        payload={"name": name, "frozen": True},
    )


def _instruction(name: str) -> FrozenInstruction:
    payload = (
        f"Frozen reasoning strategy {name}. Use only supplied bytes; "
        "emit semantic JSON and use no tools."
    ).encode()
    return FrozenInstruction(
        instruction_id=f"instruction:{name}:1",
        instruction_bytes=payload,
        instruction_digest=hashlib.sha256(payload).hexdigest(),
    )


def _semantic_output(kind: str) -> bytes:
    value = {
        "schema_id": "topology_semantic_payload",
        "schema_version": "1.0.0",
        "output_kind": kind,
        "analysis_summary": f"bounded semantic result for {kind}",
        "primary_path": "primary" if kind == "PROPOSAL" else None,
        "alternative_paths": ["alternative"] if kind == "PROPOSAL" else [],
        "null_path": "no action" if kind == "PROPOSAL" else None,
        "other_or_unknown_path": (
            "other or unknown" if kind == "PROPOSAL" else None
        ),
        "challenge_claims": (
            [{"category": "UNKNOWN_COERCION", "summary": "retain unknown"}]
            if "CHALLENGE" in kind or kind == "SELF_REVIEW"
            else []
        ),
        "selected_action": "candidate:primary" if kind == "SELECTION" else None,
        "unknowns": ["served model is not response-attested"],
    }
    return canonical_bytes(value)


def _formal_capability(**changes) -> ModelTransportCapability:
    value = ModelTransportCapability(
        adapter_id="ATTESTED_TEST_TRANSPORT:1.0.0",
        transport_evidence_class="REAL_GENERATIVE",
        provider_transport="CODEX_EXEC_CHATGPT_LOGIN",
        cli_version="codex-cli 0.146.0-alpha.3.1",
        authenticated=True,
        real_generative=True,
        ephemeral_sessions=True,
        read_only_workspace=True,
        empty_temporary_workspace=True,
        tool_calls_detectable=True,
        usage_available=True,
        hard_token_limit_available=True,
        served_model_attestation_available=False,
        reason_codes=(),
    )
    return replace(value, **changes)


class _RecordingTransport:
    def __init__(
        self,
        capability: ModelTransportCapability | None = None,
        *,
        total_tokens: int = 100,
        tool_call_names: tuple[str, ...] = (),
    ) -> None:
        self._capability = capability or _formal_capability()
        self.total_tokens = total_tokens
        self.tool_call_names = tool_call_names
        self.calls: list[ModelCallRequest] = []

    def capability(self) -> ModelTransportCapability:
        return self._capability

    def invoke(self, request: ModelCallRequest) -> ModelAttemptResult:
        self.calls.append(request)
        output = _semantic_output(request.expected_output_kind)
        event = {
            "type": "turn.completed",
            "usage": {
                "input_tokens": max(0, self.total_tokens - 20),
                "cached_input_tokens": 0,
                "output_tokens": 20,
                "reasoning_output_tokens": 0,
            },
        }
        return ModelAttemptResult(
            status=ModelAttemptStatus.COMPLETE,
            raw_event_bytes=canonical_bytes(event) + b"\n",
            raw_stderr_bytes=b"provider warning retained\n",
            raw_output_bytes=output,
            requested_model=request.model,
            served_model_attestation=None,
            usage=UsageRecord(
                input_tokens=max(0, self.total_tokens - 20),
                cached_input_tokens=0,
                output_tokens=20,
                reasoning_output_tokens=0,
                total_tokens=self.total_tokens,
            ),
            tool_call_names=self.tool_call_names,
            retry_count=0,
            latency_ms=25,
        )


class GenerativeTopologyRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_json_strict(
            ROOT / "config" / "theory_agent_v2.formal_e0_experiment.v1.json"
        )
        self.transport_schema_digest = canonical_digest(
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
        )

    def request(
        self,
        *,
        evidence_class: RunEvidenceClass = RunEvidenceClass.FORMAL_GENERATIVE,
        dataset_kind: str = "FROZEN_REAL_MARKET",
        session_id: str = "paired-session-001",
        sample_cohort: str = "TOPOLOGY_SELECTION",
        sample_index: int = 96,
        selected_topology_id: str | None = None,
        topology_selection_result_digest: str | None = None,
    ) -> PairedGenerativeRunRequest:
        source = _ref("market_source")
        requested_topology_ids = (
            FORMAL_TOPOLOGY_IDS
            if sample_cohort == "TOPOLOGY_SELECTION"
            else (selected_topology_id,)
        )
        return PairedGenerativeRunRequest(
            paired_session_id=session_id,
            evidence_class=evidence_class,
            dataset_kind=dataset_kind,
            sample_cohort=sample_cohort,
            sample_index=sample_index,
            requested_topology_ids=requested_topology_ids,
            selected_topology_id=selected_topology_id,
            topology_selection_result_digest=(
                topology_selection_result_digest
            ),
            dataset_manifest_ref=_ref("dataset"),
            dataset_transport_contract_verdict="PASS",
            dataset_transport_schema_digest=self.transport_schema_digest,
            decision_context_ref=_ref("decision_context"),
            common_projection_values=(
                ProjectionValue(
                    source_object_ref=source,
                    json_pointer="/bars",
                    value=[
                        {
                            "open_time": 0,
                            "close": "938471.123456789",
                            "available_at": "2026-07-31T00:00:00Z",
                        }
                    ],
                ),
            ),
            formal_contract=self.contract,
            reasoning_instructions={
                key: _instruction(key)
                for key in (
                    "SINGLE_STRONG",
                    "PROPOSER",
                    "CHALLENGER",
                    "SELECTOR",
                )
            },
        )

    @staticmethod
    def clock():
        start = datetime(2026, 7, 31, 10, tzinfo=UTC)
        values = iter((start, start + timedelta(seconds=1)))
        return lambda: next(values)

    def execute_run(
        self,
        directory: str,
        transport: _RecordingTransport,
        **request_changes,
    ):
        request = self.request(**request_changes)
        archive = WriteOncePairedRunArchive(
            Path(directory), request.paired_session_id
        )
        receipt = run_paired_generative_topologies(
            request,
            model_port=transport,
            archive=archive,
            clock=self.clock(),
        )
        return request, archive, receipt

    def test_frozen_contract_is_exact_and_tamper_fails_closed(self) -> None:
        self.assertEqual(
            validate_formal_experiment_contract(self.contract),
            FORMAL_CONTRACT_DIGEST,
        )
        tampered = dict(self.contract)
        tampered["contract_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SELF_DIGEST_MISMATCH"):
            validate_formal_experiment_contract(tampered)

    def test_v12_role_input_binds_values_without_duplicating_them(self):
        projection = self.request().common_projection_values
        common_context_digest = canonical_digest(
            {
                "projection_values": [
                    {
                        "source_object_ref": dict(
                            item.source_object_ref
                        ),
                        "json_pointer": item.json_pointer,
                        "value": item.value,
                    }
                    for item in projection
                ]
            }
        )
        payload = build_resolved_role_input_document(
            decision_context_ref=_ref("decision"),
            role_context_view_ref=_ref("role_context"),
            role_id="PROPOSER",
            common_context_digest=common_context_digest,
            projection_values=projection,
        )
        decoded = json.loads(payload)
        self.assertEqual(
            decoded["projection_bindings"][0]["value_digest"],
            canonical_digest(projection[0].value),
        )
        self.assertNotIn("projection_values", decoded)
        self.assertNotIn(
            canonical_bytes(projection[0].value),
            payload,
        )
        self.assertEqual(
            common_context_digest,
            decoded["common_context_digest"],
        )
        self.assertEqual(
            set(decoded["decision_context_ref"]),
            {
                "schema_id",
                "schema_version",
                "object_id",
                "payload_digest",
                "object_digest",
            },
        )
        repair = role_input_transport_repair_receipt()
        verify_self_digest(repair, "receipt_digest")
        self.assertEqual(
            "INCOMPATIBLE_MISSING_INLINE_PROJECTION_VALUES",
            repair["legacy_verdict"],
        )
        self.assertEqual(
            self.transport_schema_digest, repair["repair_schema_digest"]
        )

    def test_model_cannot_supply_identifier_reference_or_digest_fields(self):
        valid = _semantic_output("PROPOSAL")
        wrapper = wrap_semantic_model_output(
            paired_session_id="session",
            topology_id="SINGLE_STRONG",
            turn_ordinal=0,
            role_id="PROPOSER",
            role_context_view_ref=_ref("role_context"),
            source_input_digest="a" * 64,
            expected_output_kind="PROPOSAL",
            raw_output=valid,
        )
        verify_self_digest(wrapper, "record_digest")
        self.assertNotIn("record_id", json.loads(valid))
        malicious = json.loads(valid)
        malicious["record_digest"] = "0" * 64
        with self.assertRaisesRegex(
            ValueError, "SCHEMA_ADDITIONAL_PROPERTY"
        ):
            wrap_semantic_model_output(
                paired_session_id="session",
                topology_id="SINGLE_STRONG",
                turn_ordinal=0,
                role_id="PROPOSER",
                role_context_view_ref=_ref("role_context"),
                source_input_digest="a" * 64,
                expected_output_kind="PROPOSAL",
                raw_output=canonical_bytes(malicious),
            )

    def test_formal_three_arm_run_is_byte_paired_and_fully_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = _RecordingTransport()
            _, archive, receipt = self.execute_run(directory, transport)

            self.assertEqual(FORMAL_TOPOLOGY_IDS, tuple(receipt["topology_ids"]))
            self.assertEqual(9, len(transport.calls))
            self.assertTrue(receipt["formal_evidence"])
            self.assertTrue(receipt["formal_observation_eligible"])
            self.assertEqual([], receipt["reason_codes"])
            self.assertIsNone(receipt["served_model_attestation"])
            self.assertEqual(
                "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT",
                receipt["served_model_attestation_status"],
            )
            common = (
                archive.root_path
                / "shared"
                / "byte-identical-common-context.json"
            ).read_bytes()
            output_refs: list[str] = []
            for arm in receipt["arm_receipts"]:
                self.assertEqual("COMPLETE", arm["status"])
                self.assertEqual(3, arm["calls_attempted"])
                self.assertIsNone(arm["cost_microunits"])
                self.assertEqual(
                    receipt["raw_input_ref"], arm["raw_input_ref"]
                )
                output_refs.extend(arm["raw_output_refs"])
                for turn in arm["turn_receipts"]:
                    provider_path = (
                        archive.root_path
                        / "arms"
                        / arm["topology_id"]
                        / (
                            f"turn-{turn['turn_ordinal']:02d}-"
                            f"{turn['phase_id'].lower()}"
                        )
                        / "provider-input.bin"
                    )
                    provider_bytes = provider_path.read_bytes()
                    start, end = turn["common_context_byte_range"]
                    self.assertEqual(common, provider_bytes[start:end])
                    self.assertEqual(
                        1,
                        provider_bytes.count(b'"938471.123456789"'),
                    )
                    self.assertTrue(turn["raw_event_ref"])
                    self.assertTrue(turn["raw_output_ref"])
                    self.assertIsNone(turn["served_model_attestation"])
            self.assertEqual(9, len(output_refs))
            self.assertEqual(9, len(set(output_refs)))
            post = receipt["arm_receipts"][1]["turn_receipts"][1]
            blind = receipt["arm_receipts"][2]["turn_receipts"][1]
            self.assertEqual([0], post["visible_prior_turns"])
            self.assertEqual([], blind["visible_prior_turns"])
            self.assertTrue(
                (archive.root_path / "paired-run-receipt.json").is_file()
            )

    def test_post_selection_cohorts_run_only_frozen_selected_topology(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = _RecordingTransport()
            _, _, receipt = self.execute_run(
                directory,
                transport,
                session_id="policy-session-128",
                sample_cohort="POLICY_QUALIFICATION",
                sample_index=128,
                selected_topology_id="CLUSTER_POST_PROPOSAL",
                topology_selection_result_digest="5" * 64,
            )
        self.assertEqual(3, len(transport.calls))
        self.assertEqual(
            ["CLUSTER_POST_PROPOSAL"],
            receipt["topology_ids"],
        )
        self.assertEqual(
            "5" * 64,
            receipt["topology_selection_result_digest"],
        )
        self.assertEqual("POLICY_QUALIFICATION", receipt["sample_cohort"])
        self.assertTrue(receipt["formal_observation_eligible"])

    def test_post_selection_cohort_rejects_unfrozen_or_multiarm_request(self):
        valid = self.request(
            sample_cohort="FORMAL_EXPERIMENT",
            sample_index=160,
            selected_topology_id="CLUSTER_BLIND",
            topology_selection_result_digest="6" * 64,
        )
        with self.assertRaisesRegex(
            GenerativeTopologyRunError,
            "POST_SELECTION_REQUIRES_FROZEN_SELECTED_TOPOLOGY",
        ):
            replace(valid, requested_topology_ids=FORMAL_TOPOLOGY_IDS)
        with self.assertRaisesRegex(
            GenerativeTopologyRunError,
            "POST_SELECTION_REQUIRES_FROZEN_SELECTED_TOPOLOGY",
        ):
            replace(valid, topology_selection_result_digest=None)

    def test_mock_run_is_archived_but_never_formal_observation(self) -> None:
        capability = _formal_capability(
            transport_evidence_class="MOCK",
            real_generative=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            _, _, receipt = self.execute_run(
                directory,
                _RecordingTransport(capability),
                evidence_class=RunEvidenceClass.NON_FORMAL_MOCK,
                dataset_kind="SYNTHETIC",
            )
        self.assertEqual(9, sum(
            arm["calls_attempted"] for arm in receipt["arm_receipts"]
        ))
        self.assertFalse(receipt["formal_evidence"])
        self.assertIn("NON_FORMAL_EVIDENCE_EXCLUDED", receipt["reason_codes"])
        with self.assertRaisesRegex(
            GenerativeTopologyRunError,
            "NON_FORMAL_GENERATION_RECEIPT_NOT_ADMISSIBLE",
        ):
            admit_formal_generation_receipt(receipt)

    def test_formal_transport_without_hard_cap_blocks_before_model(self):
        capability = _formal_capability(
            hard_token_limit_available=False,
            reason_codes=("CODEX_HARD_TOKEN_CAP_NOT_ATTESTED",),
        )
        transport = _RecordingTransport(capability)
        with tempfile.TemporaryDirectory() as directory:
            _, _, receipt = self.execute_run(directory, transport)
        self.assertEqual([], transport.calls)
        self.assertFalse(receipt["formal_observation_eligible"])
        self.assertIn(
            "CODEX_HARD_TOKEN_CAP_NOT_ATTESTED",
            receipt["reason_codes"],
        )

    def test_tool_call_or_token_overrun_invalidates_formal_arm(self) -> None:
        for transport, code in (
            (
                _RecordingTransport(tool_call_names=("command_execution",)),
                "MODEL_TOOL_CALL_FORBIDDEN",
            ),
            (
                _RecordingTransport(total_tokens=40_000),
                "TOPOLOGY_TOKEN_BUDGET_EXCEEDED",
            ),
        ):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                _, _, receipt = self.execute_run(directory, transport)
                self.assertFalse(receipt["formal_observation_eligible"])
                self.assertIn(code, receipt["reason_codes"])

    def test_complete_generation_adapts_only_with_explicit_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, generation = self.execute_run(
                directory, _RecordingTransport()
            )
        observation = build_paired_observation_from_generation(
            generation_receipt=generation,
            topology_id="SINGLE_STRONG",
            scoring_policy_digest="1" * 64,
            cost_policy_digest="2" * 64,
            initial_account_digest="3" * 64,
            termination_policy_digest="4" * 64,
            scores=FormalObservationScores(
                sample_index=96,
                sample_cohort="TOPOLOGY_SELECTION",
                qualification_verdict="NOT_APPLICABLE",
                dynamic_candidate_coverage=Decimal("1"),
                material_challenge_coverage=Decimal("0.5"),
                action_quality_score=Decimal("0.75"),
                safety_state_pit_authority_failures=0,
                role_overreach_failures=0,
                hard_constraint_error_count=0,
                state_continuity_error_count=0,
                reproducibility_difference_count=0,
            ),
        )
        self.assertIsNone(observation.cost_microunits)
        self.assertIsNone(observation.served_model_attestation)
        self.assertEqual(
            "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT",
            observation.served_model_attestation_status,
        )
        self.assertEqual(
            self.transport_schema_digest,
            observation.transport_schema_digest,
        )
        self.assertEqual(
            generation["dataset_digest"],
            observation.dataset_digest,
        )
        self.assertEqual(
            generation["formal_contract_digest"],
            observation.formal_contract_digest,
        )
        self.assertEqual(generation["raw_input_ref"], observation.raw_input_ref)

    def test_write_once_archive_rejects_duplicate_run_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = WriteOncePairedRunArchive(
                Path(directory), "paired-session"
            )
            archive.write_bytes("shared/input.bin", b"one")
            with self.assertRaisesRegex(
                PairedRunArchiveError,
                "WRITE_ONCE_RUN_ARTIFACT_CONFLICT",
            ):
                archive.write_bytes("shared/input.bin", b"two")
            with self.assertRaisesRegex(
                PairedRunArchiveError,
                "PAIRED_RUN_DIRECTORY_ALREADY_EXISTS",
            ):
                WriteOncePairedRunArchive(
                    Path(directory), "paired-session"
                )

    def test_codex_jsonl_parser_matches_observed_probe_shape(self) -> None:
        events = b"\n".join(
            (
                b'{"type":"thread.started","thread_id":"redacted"}',
                b'{"type":"turn.started"}',
                (
                    b'{"type":"item.completed","item":{"id":"item_0",'
                    b'"type":"agent_message","text":"{\\"ok\\":true}"}}'
                ),
                (
                    b'{"type":"turn.completed","usage":{'
                    b'"input_tokens":18338,"cached_input_tokens":0,'
                    b'"cache_write_input_tokens":0,"output_tokens":23,'
                    b'"reasoning_output_tokens":0}}'
                ),
            )
        )
        output, usage, tools, retries, rerouted = parse_codex_exec_jsonl(
            events
        )
        self.assertEqual(b'{"ok":true}', output)
        self.assertEqual(18361, usage.total_tokens)
        self.assertEqual((), tools)
        self.assertEqual(0, retries)
        self.assertFalse(rerouted)

    def test_codex_transport_binds_ephemeral_read_only_config_and_usage(self):
        captured: list[list[str]] = []
        stdout = b"\n".join(
            canonical_bytes(item)
            for item in (
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": _semantic_output("PROPOSAL").decode(),
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 0,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 0,
                    },
                },
            )
        )

        def runner(command, **kwargs):
            captured.append(command)
            workspace = Path(command[command.index("--cd") + 1])
            schema = Path(command[command.index("--output-schema") + 1])
            self.assertEqual([], list(workspace.iterdir()))
            self.assertTrue(schema.is_file())
            return subprocess.CompletedProcess(
                command, 0, stdout=stdout, stderr=b"warning\n"
            )

        transport = CodexExecGenerativeTransport(
            codex_binary="/usr/local/bin/codex-fixture",
            command_runner=runner,
        )
        prompt = b"prompt"
        result = transport.invoke(
            ModelCallRequest(
                paired_session_id="session",
                topology_id="SINGLE_STRONG",
                turn_ordinal=0,
                phase_id="PROPOSE",
                role_id="PROPOSER",
                expected_output_kind="PROPOSAL",
                provider_input_bytes=prompt,
                provider_input_digest=hashlib.sha256(prompt).hexdigest(),
                semantic_output_schema_bytes=canonical_bytes(
                    SEMANTIC_MODEL_OUTPUT_SCHEMA
                ),
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                token_limit=30_000,
                timeout_seconds=120,
            )
        )
        command = captured[0]
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("read-only", command)
        self.assertIn("token_budget.limit_tokens=30000", command)
        self.assertIn("token_budget", command)
        self.assertEqual(ModelAttemptStatus.COMPLETE, result.status)
        self.assertEqual(120, result.usage.total_tokens)
        self.assertIsNone(result.served_model_attestation)
        self.assertEqual(b"warning\n", result.raw_stderr_bytes)

    def test_codex_capability_uses_exact_token_budget_feature_as_hard_cap(
        self,
    ):
        def runner(command, **kwargs):
            if "--version" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b"codex-cli 0.146.0-alpha.3.1\n",
                    stderr=b"",
                )
            if command[-2:] == ["login", "status"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b"Logged in using ChatGPT\n",
                    stderr=b"",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    b"rollout_budget under development false\n"
                    b"token_budget under development false\n"
                ),
                stderr=b"",
            )

        capability = CodexExecGenerativeTransport(
            codex_binary="/usr/local/bin/codex-fixture",
            command_runner=runner,
        ).capability()
        self.assertTrue(capability.real_generative)
        self.assertTrue(capability.hard_token_limit_available)
        self.assertEqual((), capability.reason_codes)

    def test_provider_output_schema_const_fields_have_explicit_types(self):
        for schema in (
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA,
            SEMANTIC_MODEL_OUTPUT_SCHEMA,
        ):
            for field in ("schema_id", "schema_version"):
                definition = schema["properties"][field]
                self.assertEqual("string", definition["type"])
                self.assertIsInstance(definition["const"], str)


if __name__ == "__main__":
    unittest.main()
