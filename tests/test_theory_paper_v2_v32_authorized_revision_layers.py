from __future__ import annotations

import ast
import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trade_system.theory_paper_v2.application.v32_authorized_revision_orchestration import (
    CYCLE_REGISTRY_DIGEST_FIELD,
    CYCLE_REGISTRY_SCHEMA_VERSION_V2,
    SUPPORT_BUNDLE_DIGEST_FIELD,
    V32AuthorizedRevisionOrchestrationError,
    build_v32_authorized_revision_cycle_registry_v1,
    build_v32_authorized_revision_support_bundle_v1,
    build_v32_revision_input_state_v1,
    verify_v32_authorized_revision_cycle_registry_v1,
    verify_v32_authorized_revision_cycle_registry_receipt_v1,
    verify_v32_authorized_revision_support_bundle_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_compaction_policy_v1,
    build_v32_context_shard_selection_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    REQUIRED_SECTION_IDS,
    build_v32_cycle_audit_narrative_bundle_v1,
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_data_gap_escalation import (
    build_v32_data_gap_manual_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    build_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.domain.v32_unknown_assessment import (
    build_v32_unknown_subjective_policy_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
    STORE_ROOT,
    V32AuthorizedRevisionStoreError,
)
from trade_system.theory_paper_v2 import (
    v32_durable_json as durable_json_module,
)


PROJECT = Path(__file__).resolve().parents[1]
RUN_ID = "v32-authorized-revision-test"
T0 = "2026-08-08T01:00:00Z"
T1 = "2026-08-08T01:01:00Z"


def _physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


def _binding(document: dict, digest_field: str, relative_ref: str) -> dict:
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": _physical(document),
    }


def _capabilities() -> list[dict]:
    return [
        {
            "category": category,
            "status": "AVAILABLE",
            "observed_value": f"observed:{category}",
            "limit": "LOCAL_ONLY",
            "evidence_refs": [f"local:{category.lower()}"],
            "claim_ceiling": "CAPABILITY_ONLY",
        }
        for category in CAPABILITY_CATEGORIES
    ]


def _support_components() -> tuple[dict, dict, dict, dict, dict]:
    return (
        build_v32_context_compaction_policy_v1(
            policy_id="context-policy", run_scope_id=RUN_ID, frozen_at=T0
        ),
        build_v32_unknown_subjective_policy_v1(
            policy_id="unknown-policy", run_scope_id=RUN_ID, frozen_at=T0
        ),
        build_v32_data_gap_manual_policy_v1(
            policy_id="gap-policy", run_scope_id=RUN_ID, frozen_at=T0
        ),
        build_v32_cycle_audit_policy_v1(
            policy_id="audit-policy", run_scope_id=RUN_ID, frozen_at=T0
        ),
        build_v32_environment_capability_profile_v1(
            profile_id="environment-profile",
            run_scope_id=RUN_ID,
            frozen_at=T0,
            capabilities=_capabilities(),
            localization_adapters=[],
        ),
    )


def _context_package() -> dict:
    original = self_digest(
        {
            "schema_id": "test_cycle_registry_original_v1",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "unknown_state": "UNKNOWN",
            "hypothesis": {
                "hypothesis_id": "h-one",
                "falsifier": "price fails",
                "hazard": "stop through",
            },
        },
        "artifact_digest",
    )
    original_binding = _binding(
        original, "artifact_digest", "originals/registry-source.json"
    )
    bundle = build_v32_context_compaction_bundle_v1(
        run_id=RUN_ID,
        cycle_index=1,
        created_at=T0,
        source_artifacts=[
            {
                "artifact_binding": original_binding,
                "canonical_bytes": len(canonical_bytes(original)),
            }
        ],
        original_documents=[original],
    )
    manifest = bundle["manifest"]
    manifest_binding = _binding(
        manifest, MANIFEST_DIGEST_FIELD, "context/manifest.json"
    )
    selection = build_v32_context_shard_selection_v1(
        manifest=manifest,
        manifest_binding=manifest_binding,
        shards=bundle["shards"],
        original_documents=[original],
        caller_required_member_ids=[],
        selected_at=T0,
        max_agent_context_canonical_bytes=262_144,
    )
    return {
        "manifest": manifest,
        "shards": bundle["shards"],
        "original_documents": [original],
        "selection": selection,
        "manifest_binding": manifest_binding,
        "shard_bindings": [
            _binding(
                shard,
                CONTEXT_SHARD_DIGEST_FIELD,
                f"context/shards/{index}.json",
            )
            for index, shard in enumerate(bundle["shards"])
        ],
        "selection_binding": _binding(
            selection,
            "context_shard_selection_digest",
            "context/selection.json",
        ),
    }


class AuthorizedRevisionAggregateTests(unittest.TestCase):
    def test_support_bundle_binds_five_owned_components_and_store(self) -> None:
        context, unknown, gap, audit, environment = _support_components()
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalV32AuthorizedRevisionStore(Path(temporary))
            bindings = {
                "context": store.persist_document(
                    role="context_compaction_policy", document=context
                ),
                "unknown": store.persist_document(
                    role="unknown_subjective_policy", document=unknown
                ),
                "gap": store.persist_document(
                    role="data_gap_manual_policy", document=gap
                ),
                "audit": store.persist_document(
                    role="cycle_audit_policy", document=audit
                ),
                "environment": store.persist_document(
                    role="environment_capability_profile", document=environment
                ),
            }
            support = build_v32_authorized_revision_support_bundle_v1(
                support_bundle_id="support-bundle",
                run_scope_id=RUN_ID,
                frozen_at=T1,
                context_compaction_policy=context,
                context_compaction_policy_binding=bindings["context"],
                unknown_subjective_policy=unknown,
                unknown_subjective_policy_binding=bindings["unknown"],
                data_gap_manual_policy=gap,
                data_gap_manual_policy_binding=bindings["gap"],
                cycle_audit_policy=audit,
                cycle_audit_policy_binding=bindings["audit"],
                environment_capability_profile=environment,
                environment_capability_profile_binding=bindings["environment"],
            )
            self.assertEqual(
                verify_v32_authorized_revision_support_bundle_v1(
                    support,
                    context_compaction_policy=context,
                    unknown_subjective_policy=unknown,
                    data_gap_manual_policy=gap,
                    cycle_audit_policy=audit,
                    environment_capability_profile=environment,
                ),
                support[SUPPORT_BUNDLE_DIGEST_FIELD],
            )
            support_binding = store.persist_document(
                role="authorized_revision_support_bundle", document=support
            )
            self.assertEqual(
                support_binding["semantic_digest"],
                support[SUPPORT_BUNDLE_DIGEST_FIELD],
            )

    def test_support_bundle_resigned_binding_tamper_fails(self) -> None:
        context, unknown, gap, audit, environment = _support_components()
        bindings = [
            _binding(context, "context_compaction_policy_digest", "p/context.json"),
            _binding(unknown, "unknown_subjective_policy_digest", "p/unknown.json"),
            _binding(gap, "data_gap_manual_policy_digest", "p/gap.json"),
            _binding(audit, "cycle_audit_policy_digest", "p/audit.json"),
            _binding(
                environment,
                ENVIRONMENT_DIGEST_FIELD,
                "p/environment.json",
            ),
        ]
        support = build_v32_authorized_revision_support_bundle_v1(
            support_bundle_id="support-tamper",
            run_scope_id=RUN_ID,
            frozen_at=T1,
            context_compaction_policy=context,
            context_compaction_policy_binding=bindings[0],
            unknown_subjective_policy=unknown,
            unknown_subjective_policy_binding=bindings[1],
            data_gap_manual_policy=gap,
            data_gap_manual_policy_binding=bindings[2],
            cycle_audit_policy=audit,
            cycle_audit_policy_binding=bindings[3],
            environment_capability_profile=environment,
            environment_capability_profile_binding=bindings[4],
        )
        support["components"][0]["binding"]["physical_sha256"] = "0" * 64
        support = self_digest(support, SUPPORT_BUNDLE_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_support_bundle_v1(
                support,
                context_compaction_policy=context,
                unknown_subjective_policy=unknown,
                data_gap_manual_policy=gap,
                cycle_audit_policy=audit,
                environment_capability_profile=environment,
            )

    def test_zero_item_cycle_registry_is_explicit_and_replayable(self) -> None:
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="empty-cycle-registry",
            run_id=RUN_ID,
            cycle_index=1,
            created_at=T1,
            proposal_context=None,
            selection_context=None,
            unknown_tracks=[],
            data_gap_entries=[],
            manual_evidence_entries=[],
            environment_conformance=None,
            recovery_traces=[],
        )
        self.assertTrue(registry["zero_item_registries_are_explicit"])
        self.assertEqual(registry["unknown_track_count"], 0)
        self.assertEqual(registry["component_semantic_digests"], [])
        self.assertEqual(
            verify_v32_authorized_revision_cycle_registry_receipt_v1(registry),
            registry[CYCLE_REGISTRY_DIGEST_FIELD],
        )
        self.assertEqual(
            verify_v32_authorized_revision_cycle_registry_v1(
                registry,
                proposal_context=None,
                selection_context=None,
                unknown_tracks=[],
                data_gap_entries=[],
                manual_evidence_entries=[],
                environment_conformance=None,
                recovery_traces=[],
            ),
            registry[CYCLE_REGISTRY_DIGEST_FIELD],
        )
        with tempfile.TemporaryDirectory() as temporary:
            stored = LocalV32AuthorizedRevisionStore(
                Path(temporary)
            ).persist_document(
                role="authorized_revision_cycle_registry", document=registry
            )
            self.assertEqual(
                stored["semantic_digest"],
                registry[CYCLE_REGISTRY_DIGEST_FIELD],
            )
        registry["unknown_track_count"] = 1
        registry = self_digest(registry, CYCLE_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_cycle_registry_v1(
                registry,
                proposal_context=None,
                selection_context=None,
                unknown_tracks=[],
                data_gap_entries=[],
                manual_evidence_entries=[],
                environment_conformance=None,
                recovery_traces=[],
            )

    def test_v2_cycle_registry_requires_explicit_non_imputed_reader_state(self) -> None:
        reader_binding = {
            "reader_id": "TEST_LOCAL_REVISION_READER_V1",
            "reader_version": "1.0.0",
            "reader_kind": "LOCAL_EXPLICIT_NO_REVISION_INPUT",
            "configuration_digest": canonical_digest(
                {"revision_source_configured": False}
            ),
        }
        input_state = build_v32_revision_input_state_v1(
            run_id=RUN_ID,
            cycle_index=1,
            state="NO_REVISION_INPUT",
            observed_at=T1,
            reason="NO_LOCAL_REVISION_INPUT_SOURCE_CONFIGURED",
            reader_binding=reader_binding,
        )
        inputs = {
            "proposal_context": None,
            "selection_context": None,
            "unknown_tracks": [],
            "data_gap_entries": [],
            "manual_evidence_entries": [],
            "environment_conformance": None,
            "recovery_traces": [],
            "revision_input_state": input_state,
        }
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="explicit-no-input-cycle-registry",
            run_id=RUN_ID,
            cycle_index=1,
            created_at=T1,
            **inputs,
        )
        self.assertEqual(
            CYCLE_REGISTRY_SCHEMA_VERSION_V2, registry["schema_version"]
        )
        self.assertEqual("NO_REVISION_INPUT", registry["revision_input_state"]["state"])
        self.assertFalse(registry["revision_input_state"]["zero_imputed"])
        verify_v32_authorized_revision_cycle_registry_receipt_v1(registry)
        verify_v32_authorized_revision_cycle_registry_v1(registry, **inputs)

        unavailable = build_v32_revision_input_state_v1(
            run_id=RUN_ID,
            cycle_index=1,
            state="UNKNOWN_READER_UNAVAILABLE",
            observed_at=T1,
            reason="REVISION_READER_CALL_FAILED",
            reader_binding=reader_binding,
        )
        unavailable_inputs = {**inputs, "revision_input_state": unavailable}
        unavailable_registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="unavailable-reader-cycle-registry",
            run_id=RUN_ID,
            cycle_index=1,
            created_at=T1,
            **unavailable_inputs,
        )
        verify_v32_authorized_revision_cycle_registry_v1(
            unavailable_registry, **unavailable_inputs
        )

        present_without_material = build_v32_revision_input_state_v1(
            run_id=RUN_ID,
            cycle_index=1,
            state="PRESENT",
            observed_at=T1,
            reason="READER_REPORTED_PRESENT",
            reader_binding=reader_binding,
        )
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            build_v32_authorized_revision_cycle_registry_v1(
                registry_id="false-present-cycle-registry",
                run_id=RUN_ID,
                cycle_index=1,
                created_at=T1,
                **{**inputs, "revision_input_state": present_without_material},
            )

        forged = copy.deepcopy(registry)
        forged["revision_input_state"]["zero_imputed"] = True
        forged["revision_input_state"] = self_digest(
            forged["revision_input_state"], "revision_input_state_digest"
        )
        forged = self_digest(forged, CYCLE_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_cycle_registry_receipt_v1(forged)

    def test_receipt_verifier_rejects_resigned_nested_and_index_tamper(self) -> None:
        package = _context_package()
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="receipt-tamper",
            run_id=RUN_ID,
            cycle_index=1,
            created_at=T1,
            proposal_context=package,
            selection_context=None,
            unknown_tracks=[],
            data_gap_entries=[],
            manual_evidence_entries=[],
            environment_conformance=None,
            recovery_traces=[],
        )
        nested = copy.deepcopy(registry)
        nested["proposal_context"]["manifest_binding"]["schema_id"] = (
            "forged_manifest_v1"
        )
        nested = self_digest(nested, CYCLE_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_cycle_registry_receipt_v1(nested)

        index = copy.deepcopy(registry)
        index["component_semantic_digest_index_digest"] = "0" * 64
        index = self_digest(index, CYCLE_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_cycle_registry_receipt_v1(index)

        declaration = copy.deepcopy(registry)
        declaration["receipt_integrity_verifier_replays_nested_artifacts"] = True
        declaration = self_digest(declaration, CYCLE_REGISTRY_DIGEST_FIELD)
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            verify_v32_authorized_revision_cycle_registry_receipt_v1(declaration)

    def test_cycle_registry_replays_context_originals_and_rejects_tamper(self) -> None:
        package = _context_package()
        registry = build_v32_authorized_revision_cycle_registry_v1(
            registry_id="context-cycle-registry",
            run_id=RUN_ID,
            cycle_index=1,
            created_at=T1,
            proposal_context=package,
            selection_context=None,
            unknown_tracks=[],
            data_gap_entries=[],
            manual_evidence_entries=[],
            environment_conformance=None,
            recovery_traces=[],
        )
        self.assertTrue(
            registry["proposal_context"]["complete_original_replay_verified"]
        )
        self.assertFalse(registry["cycle_audit_narrative_included"])
        self.assertFalse(
            registry["receipt_integrity_verifier_replays_nested_artifacts"]
        )
        verify_v32_authorized_revision_cycle_registry_receipt_v1(registry)
        verify_v32_authorized_revision_cycle_registry_v1(
            registry,
            proposal_context=package,
            selection_context=None,
            unknown_tracks=[],
            data_gap_entries=[],
            manual_evidence_entries=[],
            environment_conformance=None,
            recovery_traces=[],
        )
        tampered = copy.deepcopy(package)
        tampered["original_documents"][0]["unknown_state"] = "KNOWN"
        with self.assertRaises(V32AuthorizedRevisionOrchestrationError):
            build_v32_authorized_revision_cycle_registry_v1(
                registry_id="tampered-context",
                run_id=RUN_ID,
                cycle_index=1,
                created_at=T1,
                proposal_context=tampered,
                selection_context=None,
                unknown_tracks=[],
                data_gap_entries=[],
                manual_evidence_entries=[],
                environment_conformance=None,
                recovery_traces=[],
            )


class AuthorizedRevisionStorePathSafetyTests(unittest.TestCase):
    def test_root_is_lexical_absolute_and_relative_refs_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            supplied = Path(os.path.relpath(temporary, Path.cwd()))
            store = LocalV32AuthorizedRevisionStore(supplied)
            self.assertEqual(
                store.root,
                Path(os.path.abspath(os.fspath(supplied))),
            )
            for invalid in (
                f"{STORE_ROOT}//run/cycles/0000/item.json",
                f"{STORE_ROOT}/./run/cycles/0000/item.json",
                f"{STORE_ROOT}/../item.json",
                f"{STORE_ROOT}\\run\\item.json",
                f" {STORE_ROOT}/run/item.json",
                f"{STORE_ROOT}/run/item.json ",
                "/absolute/item.json",
                "different-root/run/item.json",
            ):
                with self.subTest(relative_ref=invalid):
                    with self.assertRaises(V32AuthorizedRevisionStoreError):
                        store._path(invalid)

    def test_root_and_root_ancestor_symlinks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            actual_root = sandbox / "actual-root"
            actual_root.mkdir()
            root_alias = sandbox / "root-alias"
            root_alias.symlink_to(actual_root, target_is_directory=True)
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                LocalV32AuthorizedRevisionStore(root_alias)

            actual_parent = sandbox / "actual-parent"
            nested_root = actual_parent / "store"
            nested_root.mkdir(parents=True)
            parent_alias = sandbox / "parent-alias"
            parent_alias.symlink_to(actual_parent, target_is_directory=True)
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                LocalV32AuthorizedRevisionStore(parent_alias / "store")

    def test_store_ancestor_and_leaf_symlinks_fail_closed_without_mutation(
        self,
    ) -> None:
        context = _support_components()[0]
        digest = context["context_compaction_policy_digest"]
        relative_ref = (
            f"{STORE_ROOT}/{RUN_ID}/cycles/0000/context_compaction_policy/"
            f"{digest}.json"
        )
        payload = canonical_bytes(context) + b"\n"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = LocalV32AuthorizedRevisionStore(root)
            redirected = root / "redirected-namespace"
            redirected.mkdir()
            (root / STORE_ROOT).symlink_to(
                redirected, target_is_directory=True
            )
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.persist_document(
                    role="context_compaction_policy", document=context
                )
            self.assertEqual(list(redirected.iterdir()), [])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = LocalV32AuthorizedRevisionStore(root)
            target = root / relative_ref
            target.parent.mkdir(parents=True)
            redirected = root / "redirected-document.json"
            redirected.write_bytes(payload)
            target.symlink_to(redirected)
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.persist_document(
                    role="context_compaction_policy", document=context
                )
            self.assertEqual(redirected.read_bytes(), payload)

    def test_audit_read_rejects_a_symlinked_boundary_leaf(self) -> None:
        sections = [
            {
                "section_id": section_id,
                "title_zh": f"审计章节：{section_id}",
                "content_zh": f"记录{section_id}的事实与未知。",
                "source_bindings": [
                    {
                        "relative_ref": "accepted/cycle.json",
                        "schema_id": "test_accepted_cycle_v1",
                        "digest_field": "accepted_cycle_digest",
                        "semantic_digest": "a" * 64,
                        "physical_sha256": "b" * 64,
                    }
                ],
            }
            for section_id in REQUIRED_SECTION_IDS
        ]
        bundle = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="path-safety-audit",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=T1,
            sections=sections,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = LocalV32AuthorizedRevisionStore(root)
            store.persist_audit_bundle(
                directory=bundle["directory"], shards=bundle["shards"]
            )
            base = (
                root
                / STORE_ROOT
                / RUN_ID
                / "cycles"
                / "0001"
                / "audit"
                / "acceptance"
            )
            redirected = root / "redirected-audit-boundary"
            base.rename(redirected)
            base.symlink_to(redirected, target_is_directory=True)
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.load_audit_bundle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                )

    def test_audit_bundle_crash_before_publish_exposes_no_partial_boundary(self) -> None:
        sections = [
            {
                "section_id": section_id,
                "title_zh": f"审计章节：{section_id}",
                "content_zh": f"记录{section_id}的事实与未知。",
                "source_bindings": [
                    {
                        "relative_ref": "accepted/cycle.json",
                        "schema_id": "test_accepted_cycle_v1",
                        "digest_field": "accepted_cycle_digest",
                        "semantic_digest": "a" * 64,
                        "physical_sha256": "b" * 64,
                    }
                ],
            }
            for section_id in REQUIRED_SECTION_IDS
        ]
        bundle = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="atomic-audit",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=T1,
            sections=sections,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = LocalV32AuthorizedRevisionStore(root)
            base = (
                root
                / STORE_ROOT
                / RUN_ID
                / "cycles/0001/audit/acceptance"
            )
            with mock.patch.object(
                durable_json_module,
                "rename_directory_noreplace_at",
                side_effect=OSError("injected pre-publication crash"),
            ), self.assertRaisesRegex(
                V32AuthorizedRevisionStoreError,
                "V32_REVISION_STORE_WRITE_ONCE_FAILED",
            ):
                store.persist_audit_bundle(
                    directory=bundle["directory"], shards=bundle["shards"]
                )
            self.assertFalse(base.exists())
            self.assertEqual(
                [],
                list(base.parent.glob(".v32-write-once-directory-*.tmp")),
            )

            created = store.persist_audit_bundle(
                directory=bundle["directory"], shards=bundle["shards"]
            )
            replay = store.load_audit_bundle(
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
            )
            self.assertEqual(
                {"directory": bundle["directory"], "shards": bundle["shards"]},
                replay,
            )
            self.assertEqual(
                created,
                store.persist_audit_bundle(
                    directory=bundle["directory"], shards=bundle["shards"]
                ),
            )


class LayerBoundaryTests(unittest.TestCase):
    def _imports(self, relative: str) -> set[str]:
        tree = ast.parse((PROJECT / relative).read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_four_layer_dependency_direction(self) -> None:
        domain_files = [
            "trade_system/theory_paper_v2/domain/v32_authorized_revision_common.py",
            "trade_system/theory_paper_v2/domain/v32_context_compaction.py",
            "trade_system/theory_paper_v2/domain/v32_unknown_assessment.py",
            "trade_system/theory_paper_v2/domain/v32_data_gap_escalation.py",
            "trade_system/theory_paper_v2/domain/v32_environment_capability.py",
            "trade_system/theory_paper_v2/domain/v32_cycle_audit_narrative.py",
        ]
        for relative in domain_files:
            imports = self._imports(relative)
            self.assertFalse(
                any(
                    layer in name
                    for name in imports
                    for layer in ("application", "infrastructure", "presentation")
                ),
                relative,
            )
        application_imports = self._imports(
            "trade_system/theory_paper_v2/application/v32_authorized_revision_orchestration.py"
        )
        self.assertFalse(
            any(
                layer in name
                for name in application_imports
                for layer in ("infrastructure", "presentation")
            )
        )
        presentation_imports = self._imports(
            "trade_system/theory_paper_v2/presentation/v32_cycle_audit_presenter.py"
        )
        self.assertFalse(
            any(
                forbidden in name
                for name in presentation_imports
                for forbidden in ("infrastructure", "pathlib", "requests", "urllib")
            )
        )


if __name__ == "__main__":
    unittest.main()
