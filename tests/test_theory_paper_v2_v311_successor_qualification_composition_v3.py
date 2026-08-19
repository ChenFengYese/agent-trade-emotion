from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
from inspect import signature
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from tests import test_theory_paper_v2_v31_source_qualification as source_fixture
from tests.v311_typed_support_materials import (
    build_real_typed_qualification_supports,
)
from trade_system.theory_paper_v2.application.v31_successor_qualification_v2 import (
    compose_current_codex_durable_qualification_v2,
)
from trade_system.theory_paper_v2.application.v31_agent_transport import (
    verify_completed_v31_authoring_transport,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
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
    build_v311_agent_context_consumption_v1,
    build_v311_agent_input_context_v1,
    build_v311_successor_commit_envelope_v1,
    build_v311_theory_addendum_semantic_document_v1,
    agent_context_consumption_ref_v1,
    agent_input_context_ref_v1,
    successor_commit_envelope_ref_v1,
)
from trade_system.theory_paper_v2.domain.v31_successor_cycle_commit_v2 import (
    DIGEST_FIELD as BASE_COMMIT_DIGEST_FIELD,
    SCHEMA_ID as BASE_COMMIT_SCHEMA_ID,
    SUPPORT_BINDING_KEYS,
    successor_commit_material_ref_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    load_v31_active_authorization_chain,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_runtime_closure_v2 import (
    build_v31_runtime_closure_bindings_v2,
    collect_v31_static_runtime_closure_v2,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.okx_public import (
    OkxPublicFreshCollector,
)
from trade_system.theory_paper_v2.infrastructure.v31_successor_probe_store_v2 import (
    PROBE_STORE_MODULE_PATH,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)
import trade_system.theory_paper_v2.presentation.v311_successor_qualification_composition_v3 as composition


PROJECT = Path(__file__).resolve().parents[1]
PREDECESSOR_RUN_ID = "v31-earlier-permanently-failed-run"
QUALIFICATION_ID = "v31-source-qualification-production-composition-20260807"
QUALIFIED_NOW = "2026-08-07T10:02:00Z"


class _OfficialMarkSchemaTransport(source_fixture._NoNetworkOkxTransport):
    """No-socket transport matching the current official mark-price row shape."""

    def get(self, url: str, timeout: float) -> HttpCapture:
        capture = super().get(url, timeout)
        if urlsplit(url).path != "/api/v5/public/mark-price":
            return capture
        decoded = json.loads(capture.body)
        decoded["data"][0]["instType"] = "SWAP"
        return HttpCapture(
            status=capture.status,
            headers=capture.headers,
            body=json.dumps(
                decoded, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
            received_at=capture.received_at,
            final_url=capture.final_url,
        )


class V311SuccessorQualificationCompositionV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chain = load_v31_active_authorization_chain(PROJECT)
        cls.authority = cls.chain["authority"]
        cls.run_id = str(cls.authority["authorized_run_id"])
        cls.run_ref = f"agent-cluster/experiments/{cls.run_id}"
        genesis = load_json_strict(PROJECT / cls.run_ref / "genesis/run-genesis.json")
        authority_row = next(
            row
            for row in genesis["genesis_artifacts"]
            if row["source_role"] == "current_authority"
        )
        # The checked-in completed cycle predates the v3 filename.  Patching
        # only the expected standard path lets this focused test reuse its real
        # completed current-Codex evidence while preserving the exact genesis
        # -> standard-authority bridge that production v3 uses.
        cls.standard_authority_ref = str(authority_row["global_ref"])
        cls.production_roots = (PROBE_STORE_MODULE_PATH,)
        cls.trace_paths = collect_v31_static_runtime_closure_v2(
            project_root=PROJECT,
            production_root_paths=cls.production_roots,
        )
        cls.runtime_bindings = build_v31_runtime_closure_bindings_v2(
            project_root=PROJECT,
            production_root_paths=cls.production_roots,
            trace_paths=cls.trace_paths,
        )

    def _sandbox(self, directory: str, *, with_closure: bool) -> tuple[Path, dict]:
        project = Path(directory)
        run_root = project / self.run_ref
        shutil.copytree(
            PROJECT / self.run_ref,
            run_root,
            ignore=shutil.ignore_patterns(
                "qualification-receipts-v3",
                "qualification-probe-v2",
                "fresh-public-source-v2",
            ),
        )
        if with_closure:
            for relative_ref in self.trace_paths:
                target = project / relative_ref
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(PROJECT / relative_ref, target)
        source = PROJECT / self.standard_authority_ref
        target = project / self.standard_authority_ref
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        raw = target.read_bytes()
        binding = {
            "path": self.standard_authority_ref,
            "schema_id": self.authority["schema_id"],
            "digest_field": "authority_digest",
            "semantic_digest": self.authority["authority_digest"],
            "physical_sha256": hashlib.sha256(raw).hexdigest(),
        }
        return project, binding

    def _common(self, project: Path, authority_binding: dict) -> dict:
        return {
            "project_root": project,
            "qualification_v3_chain": self.chain,
            "qualification_authority_binding": authority_binding,
            "qualification_run_root_ref": self.run_ref,
            "predecessor_run_id": PREDECESSOR_RUN_ID,
        }

    def _seal_source(
        self, common: dict, *, official_schema: bool = True
    ) -> tuple[dict, source_fixture._NoNetworkOkxTransport]:
        server_time_ms = int(
            datetime(2026, 8, 7, 10, 0, 21, tzinfo=UTC).timestamp()
            * 1_000
        )
        clock = source_fixture._AdvancingClock()
        clock.current = datetime(2026, 8, 7, 10, 0, 20, tzinfo=UTC)
        transport_type = (
            _OfficialMarkSchemaTransport
            if official_schema
            else source_fixture._NoNetworkOkxTransport
        )
        transport = transport_type(clock=clock)
        workflow_times = iter(
            (
                "2026-08-07T10:00:00Z",
                "2026-08-07T10:00:10Z",
                "2026-08-07T10:01:00Z",
                "2026-08-07T10:01:01Z",
                "2026-08-07T10:01:02Z",
            )
        )

        def collector_factory(*, timeout: float) -> OkxPublicFreshCollector:
            return OkxPublicFreshCollector(
                transport=transport, clock=clock, timeout=timeout
            )

        with (
            patch.object(source_fixture, "SERVER_TIME_MS", server_time_ms),
            patch(
                "trade_system.theory_paper_v2.presentation."
                "v31_source_qualification_composition.OkxPublicFreshCollector",
                side_effect=collector_factory,
            ),
            patch(
                "trade_system.theory_paper_v2.presentation."
                "v31_source_qualification_composition._now",
                side_effect=lambda: next(workflow_times),
            ),
        ):
            result = (
                composition.initialize_execute_and_seal_public_source_qualification_v3(
                    **common, qualification_id=QUALIFICATION_ID
                )
            )
        return result, transport

    def _monitor(self, common: dict) -> dict:
        return composition.execute_and_seal_monitor_qualification_v3(
            **common,
            production_root_paths=self.production_roots,
            trace_paths=self.trace_paths,
            runtime_closure_bindings=self.runtime_bindings,
        )

    @staticmethod
    def _typed_binding(
        *,
        store: LocalV31ResearchStore,
        relative_ref: str,
        document: dict,
        digest_field: str,
    ) -> dict[str, str]:
        store.write_document(
            relative_ref=relative_ref,
            document=document,
            digest_field=digest_field,
        )
        partial = store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=document[digest_field],
        )
        return {
            "relative_ref": relative_ref,
            "schema_id": document["schema_id"],
            "digest_field": digest_field,
            "semantic_digest": document[digest_field],
            "physical_sha256": partial["physical_sha256"],
        }

    def _install_mechanical_v311_lifecycle(self, project: Path) -> str:
        """Create sandbox-only lifecycle bytes around the historical chain.

        This helper exercises physical replay.  It is never production proof:
        the historical Agent call did not receive this later test context.
        Production composition itself never calls this helper or creates these
        artifacts, and the missing-lifecycle test above proves it fails closed.
        """

        run_root = project / self.run_ref
        research = LocalV31ResearchStore(run_root)
        transport = LocalV31AgentTransportStore(run_root)
        terminal = verify_completed_v31_authoring_transport(
            store=transport,
            run_id=self.run_id,
            cycle_index=1,
            expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        )
        packet = terminal["authoring_packet"]
        addendum_ref = "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md"
        addendum_bytes = (PROJECT / addendum_ref).read_bytes()
        addendum_target = project / addendum_ref
        addendum_target.write_bytes(addendum_bytes)
        addendum_binding = {
            "path": addendum_ref,
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED_TEST_INPUT",
            "physical_sha256": hashlib.sha256(addendum_bytes).hexdigest(),
        }
        support_documents: dict[str, dict] = {}
        support_bindings: dict[str, dict[str, str]] = {}
        typed_supports = build_real_typed_qualification_supports(
            project_root=project,
            run_id=self.run_id,
            public_source_qualification=research.read_document(
                relative_ref=composition.PUBLIC_SOURCE_RECEIPT_REF,
                digest_field=composition.SOURCE_QUALIFICATION_DIGEST_FIELD,
            ),
            outcome_monitor_qualification=research.read_document(
                relative_ref=composition.MONITOR_RECEIPT_REF,
                digest_field=composition.MONITOR_QUALIFICATION_DIGEST_FIELD,
            ),
            schema_compatibility=research.read_document(
                relative_ref=composition.SCHEMA_COMPATIBILITY_RECEIPT_REF,
                digest_field=composition.SCHEMA_COMPATIBILITY_DIGEST_FIELD,
            ),
        )
        for index, name in enumerate(
            sorted(V311_QUALIFICATION_AGENT_SUPPORT_KEYS)
        ):
            schema_id, digest_field = V311_QUALIFICATION_AGENT_SUPPORT_SPECS[
                name
            ]
            if name == "theory_addendum":
                document = build_v311_theory_addendum_semantic_document_v1(
                    theory_addendum_binding=addendum_binding,
                    markdown_utf8=addendum_bytes.decode("utf-8"),
                )
                digest_field = THEORY_ADDENDUM_SEMANTIC_DOCUMENT_DIGEST_FIELD
            else:
                document = typed_supports[name]
            relative_ref = (
                "successor-v311-agent-support/cycles/0001/"
                f"{name}.json"
            )
            support_documents[name] = document
            support_bindings[name] = self._typed_binding(
                store=research,
                relative_ref=relative_ref,
                document=document,
                digest_field=digest_field,
            )
        context = build_v311_agent_input_context_v1(
            run_id=self.run_id,
            cycle_index=1,
            context_profile=V311_QUALIFICATION_CONTEXT_PROFILE,
            created_at="2026-08-06T19:06:45Z",
            base_authoring_packet=packet,
            base_authoring_packet_binding=terminal["authoring_packet_binding"],
            current_authority_binding=packet["authority_context"][
                "active_authority_binding"
            ],
            theory_addendum_binding=addendum_binding,
            support_documents=support_documents,
            support_bindings=support_bindings,
        )
        context_binding = self._typed_binding(
            store=research,
            relative_ref=agent_input_context_ref_v1(1),
            document=context,
            digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )
        proposal_state = terminal["checkpoint"]["stage_states"]["PROPOSAL"]
        proposal = {
            name: transport.read_bound_document(
                proposal_state[f"{name}_binding"]
            )
            for name in ("attempt", "request", "claim", "delivery", "consume")
        }
        evidence_ref = terminal["transport_evidence_binding"]["relative_ref"]
        evidence_binding = transport.artifact_binding(
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
        consumption_binding = self._typed_binding(
            store=research,
            relative_ref=agent_context_consumption_ref_v1(1),
            document=consumption,
            digest_field=AGENT_CONTEXT_CONSUMPTION_DIGEST_FIELD,
        )
        permit = self_digest(
            {
                "schema_id": "theory_paper_v31_experiment_cycle_permit",
                "schema_version": "2.0.0",
                "run_id": self.run_id,
                "cycle_index": 1,
                "sandbox_mechanical_only": True,
            },
            "cycle_permit_digest",
        )
        permit_binding = self._typed_binding(
            store=research,
            relative_ref="supervisor-v2/permits/cycle-0001.json",
            document=permit,
            digest_field="cycle_permit_digest",
        )
        commit_support: dict[str, dict[str, str]] = {}
        for index, name in enumerate(sorted(SUPPORT_BINDING_KEYS)):
            existing = support_bindings.get(name)
            if existing is not None:
                commit_support[name] = existing
                continue
            document = self_digest(
                {
                    "schema_id": f"theory_paper_v311_test_commit_support_{name}",
                    "schema_version": "1.0.0",
                    "ordinal": index,
                },
                "support_digest",
            )
            commit_support[name] = self._typed_binding(
                store=research,
                relative_ref=(
                    "successor-v311-commit-support/cycles/0001/"
                    f"{name}.json"
                ),
                document=document,
                digest_field="support_digest",
            )
        checkpoint = research.load_checkpoint(run_id=self.run_id)
        accepted_digest = checkpoint["accepted_state_digest"]
        authority_digest = packet["authority_context"][
            "active_authority_binding"
        ]["semantic_digest"]
        base_material = self_digest(
            {
                "schema_id": BASE_COMMIT_SCHEMA_ID,
                "schema_version": "2.0.0",
                "run_id": self.run_id,
                "cycle_index": 1,
                "active_authority_digest": authority_digest,
                "authoring_packet_digest": packet["authoring_packet_digest"],
                "transport_evidence_binding": evidence_binding,
                "cycle_permit_binding": permit_binding,
                "assembly_bundle": {
                    "expected_artifact_digests": {
                        "STATE_ACCEPTED": accepted_digest
                    }
                },
                "support_bindings": commit_support,
                "sandbox_mechanical_only": True,
            },
            BASE_COMMIT_DIGEST_FIELD,
        )
        base_ref = successor_commit_material_ref_v2(1)
        base_binding = self._typed_binding(
            store=research,
            relative_ref=base_ref,
            document=base_material,
            digest_field=BASE_COMMIT_DIGEST_FIELD,
        )
        commit = build_v311_successor_commit_envelope_v1(
            base_successor_commit_material=base_material,
            base_successor_commit_material_binding=base_binding,
            experiment_contract=terminal["experiment_subject"],
            agent_input_context=context,
            agent_input_context_binding=context_binding,
            agent_context_consumption=consumption,
            agent_context_consumption_binding=consumption_binding,
            sealed_at="2026-08-07T10:02:00Z",
        )
        self._typed_binding(
            store=research,
            relative_ref=successor_commit_envelope_ref_v1(1),
            document=commit,
            digest_field=V311_SUCCESSOR_COMMIT_ENVELOPE_DIGEST_FIELD,
        )
        return support_bindings["evaluation_contract"]["relative_ref"]

    @staticmethod
    def _file_hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_public_api_has_no_agent_callable_or_caller_supplied_pass(self) -> None:
        for function in (
            composition.initialize_execute_and_seal_public_source_qualification_v3,
            composition.execute_and_seal_monitor_qualification_v3,
            composition.seal_completed_codex_cycle1_qualification_v3,
            composition.seal_successor_qualification_set_v3,
            composition.load_successor_qualification_set_v3,
        ):
            parameters = signature(function).parameters
            self.assertNotIn("agent_call", parameters)
            self.assertNotIn("agent_callable", parameters)
            self.assertNotIn("case_results", parameters)
            self.assertNotIn("passed", parameters)
            self.assertNotIn("outcome", parameters)

    def test_legacy_completed_cycle_without_v311_lifecycle_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            project, authority_binding = self._sandbox(directory, with_closure=True)
            common = self._common(project, authority_binding)
            stack.enter_context(
                patch.object(
                    composition,
                    "V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH",
                    self.standard_authority_ref,
                )
            )
            stack.enter_context(
                patch.object(composition, "_utc_now", return_value=QUALIFIED_NOW)
            )

            source, transport = self._seal_source(common)
            first_get_count = len(transport.urls)
            self.assertEqual(12, first_get_count)
            self.assertEqual(
                1,
                sum(
                    urlsplit(url).path == "/api/v5/public/mark-price"
                    for url in transport.urls
                ),
            )
            source_replay = (
                composition.initialize_execute_and_seal_public_source_qualification_v3(
                    **common, qualification_id=QUALIFICATION_ID
                )
            )
            self.assertEqual(first_get_count, len(transport.urls))
            self.assertEqual("SEALED_REPLAY_NO_GET", source_replay["source_execution"])
            self.assertFalse(source_replay["collector_called_this_invocation"])

            monitor = self._monitor(common)
            self.assertEqual(first_get_count, len(transport.urls))
            self.assertEqual(0, monitor["network_get_count"])
            self.assertEqual(
                "SCHEMA_COMPATIBLE_NOT_OUTCOME",
                monitor["schema_compatibility"]["verdict"],
            )
            self.assertEqual(
                source["qualification"]["completion"]["raw_bindings"]
                ["okx-native-mark-price"]["semantic_digest"],
                monitor["schema_compatibility"]["source_raw_binding"]
                ["semantic_digest"],
            )
            self.assertFalse(
                monitor["schema_compatibility"]["outcome_admitted"]
            )
            monitor_replay = self._monitor(common)
            self.assertEqual(
                "SEALED_REPLAY_NO_PROBE_RERUN",
                monitor_replay["probe_execution"],
            )
            self.assertEqual(first_get_count, len(transport.urls))

            before = self._file_hashes(project / self.run_ref)
            with self.assertRaisesRegex(
                ValueError, "V311_CODEX_V3_LIFECYCLE_ARTIFACT_INVALID"
            ):
                composition.seal_completed_codex_cycle1_qualification_v3(
                    **common
                )
            run_root = project / self.run_ref
            self.assertEqual(before, self._file_hashes(run_root))
            self.assertFalse((run_root / composition.CODEX_RECEIPT_REF).exists())
            self.assertFalse(
                (run_root / composition.QUALIFICATION_SET_RECEIPT_REF).exists()
            )
            self.assertFalse(
                (run_root / self.standard_authority_ref).exists()
            )
            self.assertEqual(first_get_count, len(transport.urls))

    def test_v3_set_physically_replays_lifecycle_support_and_addendum(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            project, authority_binding = self._sandbox(directory, with_closure=True)
            common = self._common(project, authority_binding)
            stack.enter_context(
                patch.object(
                    composition,
                    "V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH",
                    self.standard_authority_ref,
                )
            )
            stack.enter_context(
                patch.object(composition, "_utc_now", return_value=QUALIFIED_NOW)
            )

            def mechanical_commit_verify(document, *, experiment_contract):
                del experiment_contract
                return verify_self_digest(document, BASE_COMMIT_DIGEST_FIELD)

            stack.enter_context(
                patch(
                    "trade_system.theory_paper_v2.domain."
                    "v311_agent_lifecycle_v1."
                    "verify_v31_successor_cycle_commit_material_v2",
                    side_effect=mechanical_commit_verify,
                )
            )
            stack.enter_context(
                patch(
                    "trade_system.theory_paper_v2.infrastructure."
                    "v31_successor_commit_store_v2."
                    "verify_v31_successor_cycle_commit_material_v2",
                    side_effect=mechanical_commit_verify,
                )
            )
            source, transport = self._seal_source(common)
            self._monitor(common)
            tamper_ref = self._install_mechanical_v311_lifecycle(project)

            codex = composition.seal_completed_codex_cycle1_qualification_v3(
                **common
            )
            self.assertEqual(
                "theory_paper_v311_codex_durable_delivery_qualification_v3",
                codex["qualification"]["schema_id"],
            )
            self.assertFalse(codex["agent_invoked"])
            sealed = composition.seal_successor_qualification_set_v3(**common)
            self.assertEqual(
                {
                    "public_source",
                    "codex_durable_delivery",
                    "outcome_monitor",
                },
                set(sealed["qualification_bindings"]),
            )
            before = self._file_hashes(project / self.run_ref)
            loaded = composition.load_successor_qualification_set_v3(**common)
            self.assertEqual(before, self._file_hashes(project / self.run_ref))
            self.assertEqual(0, loaded["network_get_count_during_replay"])
            self.assertFalse(loaded["agent_invoked_during_replay"])
            self.assertFalse(loaded["outcome_read"])
            self.assertEqual(12, len(transport.urls))
            self.assertEqual(
                source["qualification"]["source_qualification_v2_digest"],
                loaded["qualifications"]["codex_durable_delivery"][
                    "source_qualification_v2_digest"
                ],
            )

            tamper = project / self.run_ref / tamper_ref
            tamper.write_bytes(tamper.read_bytes() + b" ")
            with self.assertRaisesRegex(
                ValueError, "V311_CODEX_V3_SUPPORT_PHYSICAL_REPLAY_INVALID"
            ):
                composition.load_successor_qualification_set_v3(**common)

    def test_preexisting_conflicting_schema_receipt_fails_write_once_without_get(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            project, authority_binding = self._sandbox(directory, with_closure=True)
            common = self._common(project, authority_binding)
            stack.enter_context(
                patch.object(
                    composition,
                    "V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH",
                    self.standard_authority_ref,
                )
            )
            stack.enter_context(
                patch.object(composition, "_utc_now", return_value=QUALIFIED_NOW)
            )
            _source, transport = self._seal_source(common)
            first_get_count = len(transport.urls)
            target = (
                project
                / self.run_ref
                / composition.SCHEMA_COMPATIBILITY_RECEIPT_REF
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            conflict = self_digest(
                {
                    "schema_id": "deliberate_write_once_conflict",
                    "schema_version": "1.0.0",
                    "reason": "focused conflict injection",
                },
                composition.SCHEMA_COMPATIBILITY_DIGEST_FIELD,
            )
            conflict_bytes = canonical_bytes(conflict) + b"\n"
            target.write_bytes(conflict_bytes)

            with self.assertRaises(ValueError):
                self._monitor(common)
            self.assertEqual(conflict_bytes, target.read_bytes())
            self.assertEqual(first_get_count, len(transport.urls))
            self.assertFalse(
                (
                    project
                    / self.run_ref
                    / composition.MONITOR_RECEIPT_REF
                ).exists()
            )

    def test_legacy_v2_codex_receipt_cannot_masquerade_as_v3(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            project, authority_binding = self._sandbox(directory, with_closure=False)
            common = self._common(project, authority_binding)
            stack.enter_context(
                patch.object(
                    composition,
                    "V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH",
                    self.standard_authority_ref,
                )
            )
            stack.enter_context(
                patch.object(composition, "_utc_now", return_value=QUALIFIED_NOW)
            )
            source, _transport = self._seal_source(common)
            packet = load_json_strict(
                project
                / self.run_ref
                / "cycles/0001/proposal-authoring-packet.json"
            )
            legacy = compose_current_codex_durable_qualification_v2(
                project_root=project,
                run_root_ref=self.run_ref,
                run_id=self.run_id,
                predecessor_run_id=PREDECESSOR_RUN_ID,
                cycle_index=1,
                authority=self.authority,
                authority_binding=packet["authority_context"][
                    "active_authority_binding"
                ],
                validated_authority_digest=self.authority["authority_digest"],
                source_qualification_v2_digest=source["qualification"][
                    "source_qualification_v2_digest"
                ],
                qualified_at=QUALIFIED_NOW,
            )
            target = project / self.run_ref / composition.CODEX_RECEIPT_REF
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy_bytes = canonical_bytes(legacy) + b"\n"
            target.write_bytes(legacy_bytes)
            with self.assertRaisesRegex(
                ValueError, "V311_QUALIFICATION_RECEIPT_REPLAY_INVALID"
            ):
                composition.seal_completed_codex_cycle1_qualification_v3(
                    **common
                )
            self.assertEqual(legacy_bytes, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
