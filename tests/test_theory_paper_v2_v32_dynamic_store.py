from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_theory_paper_v2_v32_agent_lifecycle import RUN_ID, _theory
from tests.test_theory_paper_v2_v32_cycle_acceptance import (
    _fixture as _acceptance_fixture,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    build_v32_clock_and_tick_policy_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_dynamic_store import (
    ACCEPTANCE_DIGEST_FIELD,
    ACCEPTANCE_SCHEMA_ID,
    ARTIFACT_ROLE_SPECS,
    CHECKPOINT_DIGEST_FIELD,
    LocalV32DynamicStore,
    STORE_ROOT,
    V32DynamicStoreError,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_dynamic_store as dynamic_store_module,
)


CREATED_AT = "2026-08-07T00:00:00Z"
RECORDED_AT = "2026-08-07T00:18:00Z"


def _initialize(root: Path, *, run_id: str = RUN_ID):
    store = LocalV32DynamicStore(root)
    checkpoint = store.initialize_checkpoint(
        run_id=run_id,
        experiment_contract_digest="a" * 64,
        active_authority_digest="b" * 64,
        created_at=CREATED_AT,
    )
    return store, checkpoint


def _lifecycle_documents(fixture: dict | None = None) -> dict[str, dict]:
    fx = _acceptance_fixture() if fixture is None else fixture
    components = fx["components"]
    semantic = fx["semantic"]
    return {
        "supervisor_checkpoint": fx["checkpoint"],
        "supervisor_permit": components["analysis_tick_permit"],
        "active_authority_projection": components[
            "active_authority_projection"
        ],
        "cycle_source_admission": components["cycle_source_admission"],
        "public_market_analysis_bundle": components[
            "public_market_analysis_bundle"
        ],
        "public_market_graph_projection": components[
            "public_market_graph_projection"
        ],
        "durable_source_replay": components["durable_source_replay_receipt"],
        "support_pit_registry": components["pit_evidence_registry"],
        "support_graph_registry": components[
            "verified_graph_dependency_registry"
        ],
        "verified_pit_evidence_availability_registry": components[
            "verified_pit_evidence_availability_registry"
        ],
        "agent_market_graph_view": components["agent_market_graph_view"],
        "timeframe_context": components["current_timeframe_context_state"],
        "proposal_packet": semantic["proposal_packet"],
        "proposal_input": components["proposal_input_context"],
        "proposal_delivery": components["proposal_delivery"],
        "proposal_consumption": components["proposal_consumption"],
        "proposal_semantic_output": semantic["proposal_output"],
        "proposal_compile_receipt": components[
            "proposal_semantic_compile_receipt"
        ],
        "dynamic_state": components["compiled_dynamic_research_state"],
        "action_evaluation": components["sealed_action_evaluation"],
        "shadow_decision_bundle": components[
            "replayable_shadow_decision_bundle"
        ],
        "dynamic_state_continuity": components[
            "dynamic_state_continuity_receipt"
        ],
        "selection_packet": semantic["selection_packet"],
        "selection_input": components["selection_input_context"],
        "selection_delivery": components["selection_delivery"],
        "selection_consumption": components["selection_consumption"],
        "selection_semantic_output": semantic["selection_output"],
        "selection_compile_receipt": components[
            "selection_semantic_compile_receipt"
        ],
        "action_plan_continuity": components[
            "action_plan_continuity_receipt"
        ],
        "authorized_revision_cycle_registry": components[
            "authorized_revision_cycle_registry"
        ],
        "commit_envelope": components["two_stage_commit_envelope"],
        # action_plan and outcome_schedule are deliberately omitted: recovery
        # must copy those exact documents from the already sealed commit.
    }


def _open(store: LocalV32DynamicStore, checkpoint: dict) -> dict:
    return dict(
        store.open_cycle(
            run_id=checkpoint["run_id"],
            cycle_index=1,
            expected_checkpoint_digest=checkpoint[CHECKPOINT_DIGEST_FIELD],
            opened_at="2026-08-07T00:13:00Z",
        )
    )


def _writer(store: LocalV32DynamicStore):
    writer = getattr(store, "_test_lane_artifact_writer", None)
    if writer is None:
        from trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane import (
            LocalV32AnalysisLane,
        )

        owner = object.__new__(LocalV32AnalysisLane)
        owner._dynamic = store
        # Low-level Store tests replace the trusted constructor attestation
        # explicitly.  Production behavior is covered by the unpatched forged
        # owner rejection below and by LocalV32AnalysisLane integration tests.
        with mock.patch(
            "trade_system.theory_paper_v2.infrastructure."
            "v32_local_analysis_lane."
            "_is_formally_constructing_local_v32_analysis_lane",
            return_value=True,
        ):
            writer = store._claim_local_analysis_lane_artifact_writer(owner=owner)
        setattr(store, "_test_lane_artifact_writer", writer)
    return writer


def _persist_cycle_documents(
    store: LocalV32DynamicStore, checkpoint: dict, documents: dict[str, dict]
) -> dict:
    current = dict(checkpoint)
    for index, (role, document) in enumerate(documents.items(), start=1):
        current = dict(
            _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=1,
                role=role,
                relative_ref=(
                    f"{STORE_ROOT}/cycles/0001/stage/{index:02d}-{role}.json"
                ),
                document=document,
                expected_checkpoint_digest=current[CHECKPOINT_DIGEST_FIELD],
                recorded_at=RECORDED_AT,
            )
        )
    return current


class V32DynamicStoreTests(unittest.TestCase):
    def test_lane_writer_is_single_claim_and_wrong_capability_writes_nothing(
        self,
    ) -> None:
        from trade_system.theory_paper_v2.infrastructure.v32_local_analysis_lane import (
            LocalV32AnalysisLane,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store, initial = _initialize(root)
            with self.assertRaisesRegex(
                V32DynamicStoreError, "LANE_WRITER_OWNER_INVALID"
            ):
                store._claim_local_analysis_lane_artifact_writer(
                    owner=object()
                )
            forged_owner = object.__new__(LocalV32AnalysisLane)
            forged_owner._dynamic = store
            with self.assertRaisesRegex(
                V32DynamicStoreError, "LANE_WRITER_OWNER_INVALID"
            ):
                store._claim_local_analysis_lane_artifact_writer(
                    owner=forged_owner
                )
            self.assertEqual(
                [], store.load_checkpoint(run_id=RUN_ID)["artifact_bindings"]
            )
            writer = _writer(store)
            with self.assertRaisesRegex(
                V32DynamicStoreError, "LANE_WRITER_ALREADY_CLAIMED"
            ):
                second_owner = object.__new__(LocalV32AnalysisLane)
                second_owner._dynamic = store
                with mock.patch(
                    "trade_system.theory_paper_v2.infrastructure."
                    "v32_local_analysis_lane."
                    "_is_formally_constructing_local_v32_analysis_lane",
                    return_value=True,
                ):
                    store._claim_local_analysis_lane_artifact_writer(
                        owner=second_owner
                    )

            theory, _ = _theory()
            ref = f"{STORE_ROOT}/shared/theory/forged.json"
            with self.assertRaisesRegex(
                V32DynamicStoreError, "LANE_WRITE_CAPABILITY_INVALID"
            ):
                store._persist_artifact_with_lane_capability(
                    capability=object(),
                    run_id=RUN_ID,
                    cycle_index=0,
                    role="theory",
                    relative_ref=ref,
                    document=theory,
                    expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                    recorded_at="2026-08-07T00:01:00Z",
                )
            self.assertFalse((root / ref).exists())
            self.assertEqual(
                [], store.load_checkpoint(run_id=RUN_ID)["artifact_bindings"]
            )

            recorded = writer.persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="theory",
                relative_ref=ref,
                document=theory,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            self.assertEqual(1, len(recorded["artifact_bindings"]))

    def test_public_acceptance_replay_returns_detached_verified_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalV32DynamicStore(Path(temporary))
            acceptance = {
                ACCEPTANCE_DIGEST_FIELD: "a" * 64,
                "component_bindings": {
                    "proposal_input_context": {"semantic_digest": "b" * 64}
                },
            }
            acceptance_binding = {
                "role": "analysis_acceptance",
                "cycle_index": 1,
                "relative_ref": f"{STORE_ROOT}/cycles/0001/acceptance.json",
                "schema_id": ACCEPTANCE_SCHEMA_ID,
                "digest_field": ACCEPTANCE_DIGEST_FIELD,
                "semantic_digest": "a" * 64,
                "physical_sha256": "c" * 64,
            }
            required = {
                role: {
                    "role": role,
                    "cycle_index": 1,
                    "relative_ref": f"{STORE_ROOT}/cycles/0001/{role}.json",
                    "schema_id": "fixture",
                    "digest_field": "fixture_digest",
                    "semantic_digest": "d" * 64,
                    "physical_sha256": "e" * 64,
                }
                for role in dynamic_store_module._REQUIRED_ACCEPTANCE_ROLES
            }
            with (
                mock.patch.object(
                    store, "load_checkpoint", return_value={"run_id": RUN_ID}
                ),
                mock.patch.object(
                    store, "_required_acceptance_bindings", return_value=required
                ),
                mock.patch.object(
                    store, "_find_binding", return_value=acceptance_binding
                ),
                mock.patch.object(store, "_read_binding", return_value=acceptance),
                mock.patch.object(
                    store, "_verify_acceptance", return_value="a" * 64
                ) as verifier,
            ):
                replay = store.replay_cycle_acceptance(
                    run_id=RUN_ID, cycle_index=1
                )
            verifier.assert_called_once()
            self.assertEqual(set(replay["required_bindings"]), set(required))
            replay["acceptance"]["component_bindings"][
                "proposal_input_context"
            ]["semantic_digest"] = "0" * 64
            replay["binding"]["semantic_digest"] = "0" * 64
            replay["required_bindings"]["proposal_input"][
                "semantic_digest"
            ] = "0" * 64
            self.assertEqual(
                acceptance["component_bindings"]["proposal_input_context"][
                    "semantic_digest"
                ],
                "b" * 64,
            )
            self.assertEqual(acceptance_binding["semantic_digest"], "a" * 64)
            self.assertEqual(
                required["proposal_input"]["semantic_digest"], "d" * 64
            )

    def test_allowlist_explicitly_covers_all_required_categories(self) -> None:
        required = {
            "theory",
            "support_experiment",
            "support_association",
            "support_evaluation",
            "source_capture",
            "cycle_source_admission",
            "timeframe_context",
            "proposal_packet",
            "proposal_delivery",
            "proposal_consumption",
            "dynamic_state",
            "action_evaluation",
            "action_plan",
            "action_plan_continuity",
            "authorized_revision_cycle_registry",
            "selection_packet",
            "selection_delivery",
            "selection_consumption",
            "commit_envelope",
            "outcome_schedule",
            "analysis_acceptance",
            "active_authority_projection",
            "verified_pit_evidence_availability_registry",
            "agent_market_graph_view",
            "shadow_decision_bundle",
            "supervisor_permit",
            "supervisor_failure",
            "research_failure",
        }
        self.assertTrue(required.issubset(ARTIFACT_ROLE_SPECS))
        self.assertEqual(
            (
                "theory_paper_v32_action_plan_continuity_receipt_v1",
                "action_plan_continuity_receipt_digest",
            ),
            ARTIFACT_ROLE_SPECS["action_plan_continuity"],
        )
        self.assertNotIn("arbitrary_payload", ARTIFACT_ROLE_SPECS)

    def test_checkpoint_is_strict_self_digested_and_cas_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))
            opened = _open(store, dict(initial))
            self.assertEqual(1, opened["revision"])
            self.assertEqual(
                initial[CHECKPOINT_DIGEST_FIELD],
                opened["predecessor_checkpoint_digest"],
            )
            self.assertEqual("OPEN", opened["status"])
            self.assertEqual(1, opened["open_cycle_index"])
            with self.assertRaisesRegex(V32DynamicStoreError, "CAS_CONFLICT"):
                _open(store, dict(initial))

    def test_actual_lifecycle_commit_tail_recovers_without_agent_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _acceptance_fixture()
            store = LocalV32DynamicStore(Path(temporary))
            initial = store.initialize_checkpoint(
                run_id=RUN_ID,
                experiment_contract_digest=fixture["checkpoint"][
                    "experiment_contract_digest"
                ],
                active_authority_digest=fixture["checkpoint"][
                    "active_authority_digest"
                ],
                created_at=CREATED_AT,
            )
            current = _open(store, dict(initial))
            current = _persist_cycle_documents(
                store, current, _lifecycle_documents(fixture)
            )
            self.assertIsNone(
                store._find_binding(current, cycle_index=1, role="action_plan")
            )
            recovered = store.recover_persisted_commit_tail(
                run_id=RUN_ID,
                cycle_index=1,
                expected_checkpoint_digest=current[CHECKPOINT_DIGEST_FIELD],
                recovered_at=RECORDED_AT,
            )
            self.assertEqual("READY", recovered["status"])
            self.assertEqual(1, recovered["accepted_analysis_cycles"])
            self.assertEqual(2, recovered["next_analysis_cycle_index"])
            self.assertIsNotNone(recovered["current_dynamic_state_binding"])
            self.assertIsNotNone(recovered["current_action_plan_binding"])
            self.assertIsNotNone(recovered["current_timeframe_cache_binding"])
            self.assertIsNotNone(recovered["current_source_binding"])
            self.assertIsNotNone(recovered["current_commit_binding"])
            accepted = recovered["accepted_cycle_bindings"][0]
            self.assertEqual(
                "DETERMINISTIC_COMMIT_TAIL_RECOVERY", accepted["recovery_mode"]
            )
            self.assertEqual(0, accepted["tail_recovery_agent_invocations"])
            self.assertEqual(0, accepted["tail_recovery_network_requests"])
            self.assertFalse(accepted["accepted_state_is_fill_or_profit_claim"])
            self.assertEqual("NONE_NO_FILL_MODEL", recovered["fill_claim"])
            self.assertEqual("NONE_NO_PNL_MODEL", recovered["pnl_claim"])
            store._accepted_prefix_replay_cache.clear()
            with mock.patch.object(
                store,
                "_acceptance_replay_material",
                wraps=store._acceptance_replay_material,
            ) as semantic_replay:
                self.assertEqual(
                    recovered,
                    store.load_checkpoint(run_id=RUN_ID),
                )
                self.assertEqual(
                    recovered,
                    store.load_checkpoint(run_id=RUN_ID),
                )
                self.assertEqual(1, semantic_replay.call_count)
                touched = recovered["current_timeframe_cache_binding"]
                touched_path = Path(temporary) / touched["relative_ref"]
                touched_stat = touched_path.stat()
                os.utime(
                    touched_path,
                    ns=(
                        touched_stat.st_atime_ns,
                        touched_stat.st_mtime_ns + 1_000_000,
                    ),
                )
                self.assertEqual(
                    recovered,
                    store.load_checkpoint(run_id=RUN_ID),
                )
                # Same valid bytes with changed metadata invalidate both the
                # artifact cache and the accepted-prefix closure cache.
                self.assertEqual(2, semantic_replay.call_count)
                replay = store.replay_cycle_acceptance(
                    run_id=RUN_ID, cycle_index=1
                )
                # Public replay is an explicit trust boundary and therefore
                # never consumes the accepted-prefix semantic shortcut.
                self.assertEqual(3, semantic_replay.call_count)
            self.assertEqual(
                replay["acceptance"][ACCEPTANCE_DIGEST_FIELD],
                replay["binding"]["semantic_digest"],
            )
            self.assertEqual(replay["binding"]["role"], "analysis_acceptance")
            self.assertEqual(replay["binding"]["cycle_index"], 1)
            self.assertEqual(
                set(replay["required_bindings"]),
                set(accepted["artifact_binding_digests"]),
            )
            original_acceptance_digest = replay["acceptance"][
                ACCEPTANCE_DIGEST_FIELD
            ]
            replay["acceptance"]["component_bindings"][
                "proposal_input_context"
            ]["semantic_digest"] = "0" * 64
            replay["required_bindings"]["proposal_input"][
                "semantic_digest"
            ] = "0" * 64
            with mock.patch.object(
                store,
                "_acceptance_replay_material",
                wraps=store._acceptance_replay_material,
            ) as explicit_replay:
                replay_again = store.replay_cycle_acceptance(
                    run_id=RUN_ID, cycle_index=1
                )
                self.assertEqual(1, explicit_replay.call_count)
            self.assertEqual(
                replay_again["acceptance"][ACCEPTANCE_DIGEST_FIELD],
                original_acceptance_digest,
            )
            self.assertNotEqual(
                replay_again["required_bindings"]["proposal_input"][
                    "semantic_digest"
                ],
                "0" * 64,
            )

    def test_write_once_readback_semantic_and_physical_hash_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))
            theory, _ = _theory()
            ref = f"{STORE_ROOT}/shared/theory/theory.json"
            recorded = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="theory",
                relative_ref=ref,
                document=theory,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            binding = recorded["artifact_bindings"][0]
            self.assertEqual(theory, store.load_artifact(binding))
            self.assertEqual(64, len(binding["semantic_digest"]))
            self.assertEqual(64, len(binding["physical_sha256"]))

            replay = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="theory",
                relative_ref=ref,
                document=theory,
                expected_checkpoint_digest=recorded[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            self.assertEqual(recorded, replay)
            with self.assertRaisesRegex(V32DynamicStoreError, "WRITE_ONCE_CONFLICT"):
                _writer(store).persist_verified_artifact(
                    run_id=RUN_ID,
                    cycle_index=0,
                    role="theory",
                    relative_ref=f"{STORE_ROOT}/shared/theory/other.json",
                    document=theory,
                    expected_checkpoint_digest=recorded[CHECKPOINT_DIGEST_FIELD],
                    recorded_at="2026-08-07T00:01:00Z",
                )

    def test_artifact_read_cache_is_stat_guarded_and_tamper_detecting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store, initial = _initialize(root)
            clock_policy = build_v32_clock_and_tick_policy_v1(
                run_scope_id=RUN_ID,
                frozen_at="2026-08-07T00:00:00Z",
            )
            ref = f"{STORE_ROOT}/shared/clock/policy.json"
            recorded = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="support_clock_policy",
                relative_ref=ref,
                document=clock_policy,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            binding = recorded["artifact_bindings"][0]
            path = root / ref
            original_loader = dynamic_store_module.load_json_strict
            store._artifact_read_cache.clear()
            with mock.patch.object(
                dynamic_store_module,
                "load_json_strict",
                side_effect=original_loader,
            ) as loader:
                self.assertEqual(clock_policy, store.load_artifact(binding))
                self.assertEqual(clock_policy, store.load_artifact(binding))
                self.assertEqual(1, loader.call_count)

                before = path.stat()
                os.utime(
                    path,
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000),
                )
                self.assertEqual(clock_policy, store.load_artifact(binding))
                self.assertEqual(2, loader.call_count)

                # A metadata-only ctime change also invalidates the cache.
                original_mode = before.st_mode & 0o777
                os.chmod(path, original_mode ^ 0o100)
                self.assertEqual(clock_policy, store.load_artifact(binding))
                self.assertEqual(3, loader.call_count)

                # Restore the bound mtime while changing bytes.  ctime/size
                # still invalidate the cache and the physical hash catches it.
                path.write_bytes(path.read_bytes() + b" ")
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                with self.assertRaisesRegex(
                    V32DynamicStoreError, "BINDING_MISMATCH"
                ):
                    store.load_artifact(binding)
                self.assertEqual(4, loader.call_count)

    def test_accepted_prefix_cache_hits_invalidates_and_explicit_replay_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store, initial = _initialize(root)
            clock_policy = build_v32_clock_and_tick_policy_v1(
                run_scope_id=RUN_ID,
                frozen_at="2026-08-07T00:00:00Z",
            )
            ref = f"{STORE_ROOT}/shared/clock/policy.json"
            recorded = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="support_clock_policy",
                relative_ref=ref,
                document=clock_policy,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            binding = recorded["artifact_bindings"][0]
            checkpoint = {
                "run_id": RUN_ID,
                "experiment_contract_digest": "a" * 64,
                "active_authority_digest": "b" * 64,
                "artifact_bindings": [binding],
            }
            acceptance = {
                ACCEPTANCE_DIGEST_FIELD: "c" * 64,
                "run_id": RUN_ID,
                "cycle_index": 1,
            }
            replay_material = {
                "components": {
                    "analysis_tick_permit": {
                        "experiment_contract_digest": "a" * 64,
                        "active_authority_digest": "b" * 64,
                    }
                }
            }
            required = {"support_clock_policy": binding}
            with (
                mock.patch.object(
                    store,
                    "_acceptance_replay_material",
                    return_value=replay_material,
                ) as closure,
                mock.patch.object(
                    dynamic_store_module,
                    "verify_v32_analysis_cycle_acceptance_receipt_v1",
                    return_value="c" * 64,
                ) as verifier,
            ):
                for _ in range(2):
                    self.assertEqual(
                        "c" * 64,
                        store._verify_acceptance(
                            checkpoint,
                            cycle_index=1,
                            required=required,
                            acceptance=acceptance,
                            allow_verified_prefix_cache=True,
                        ),
                    )
                self.assertEqual(1, closure.call_count)
                self.assertEqual(1, verifier.call_count)

                path = root / ref
                before = path.stat()
                os.utime(
                    path,
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000),
                )
                store._verify_acceptance(
                    checkpoint,
                    cycle_index=1,
                    required=required,
                    acceptance=acceptance,
                    allow_verified_prefix_cache=True,
                )
                self.assertEqual(2, closure.call_count)
                self.assertEqual(2, verifier.call_count)

                store._verify_acceptance(
                    checkpoint,
                    cycle_index=1,
                    required=required,
                    acceptance=acceptance,
                )
                self.assertEqual(3, closure.call_count)
                self.assertEqual(3, verifier.call_count)

                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(
                    V32DynamicStoreError, "BINDING_MISMATCH"
                ):
                    store._verify_acceptance(
                        checkpoint,
                        cycle_index=1,
                        required=required,
                        acceptance=acceptance,
                        allow_verified_prefix_cache=True,
                    )

    def test_partial_artifact_before_checkpoint_is_replayable_only_if_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))
            theory, _ = _theory()
            ref = f"{STORE_ROOT}/shared/theory/theory.json"
            with mock.patch.object(
                store, "_replace_checkpoint", side_effect=RuntimeError("crash")
            ):
                with self.assertRaisesRegex(RuntimeError, "crash"):
                    _writer(store).persist_verified_artifact(
                        run_id=RUN_ID,
                        cycle_index=0,
                        role="theory",
                        relative_ref=ref,
                        document=theory,
                        expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                        recorded_at="2026-08-07T00:01:00Z",
                    )
            self.assertTrue((Path(temporary) / ref).is_file())
            self.assertEqual([], store.load_checkpoint(run_id=RUN_ID)["artifact_bindings"])
            recovered = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="theory",
                relative_ref=ref,
                document=theory,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            self.assertEqual(1, len(recovered["artifact_bindings"]))

    def test_tampered_artifact_or_checkpoint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store, initial = _initialize(root)
            theory, _ = _theory()
            ref = f"{STORE_ROOT}/shared/theory/theory.json"
            recorded = _writer(store).persist_verified_artifact(
                run_id=RUN_ID,
                cycle_index=0,
                role="theory",
                relative_ref=ref,
                document=theory,
                expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                recorded_at="2026-08-07T00:01:00Z",
            )
            artifact_path = root / ref
            artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
            with self.assertRaises(V32DynamicStoreError):
                store.load_checkpoint(run_id=RUN_ID)

            # Restore the canonical artifact, then forge a self-consistent but
            # structurally impossible checkpoint.
            artifact_path.write_bytes(canonical_bytes(theory) + b"\n")
            forged = deepcopy(recorded)
            forged["accepted_analysis_cycles"] = 16
            forged["next_analysis_cycle_index"] = 17
            forged["status"] = "OUTCOME_TAIL"
            forged = self_digest(forged, CHECKPOINT_DIGEST_FIELD)
            store.checkpoint_path.write_bytes(canonical_bytes(forged) + b"\n")
            with self.assertRaises(V32DynamicStoreError):
                store.load_checkpoint(run_id=RUN_ID)

    def test_paths_root_and_all_symlinks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / "actual"
            actual.mkdir()
            linked_root = base / "linked"
            linked_root.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(V32DynamicStoreError, "ROOT_SYMLINK"):
                LocalV32DynamicStore(linked_root)

            store, initial = _initialize(actual)
            theory, _ = _theory()
            invalid_refs = (
                "/absolute.json",
                f"{STORE_ROOT}/../escape.json",
                f"{STORE_ROOT}\\shared\\theory.json",
                "different-root/theory.json",
            )
            for ref in invalid_refs:
                with self.subTest(ref=ref):
                    with self.assertRaises(V32DynamicStoreError):
                        _writer(store).persist_verified_artifact(
                            run_id=RUN_ID,
                            cycle_index=0,
                            role="theory",
                            relative_ref=ref,
                            document=theory,
                            expected_checkpoint_digest=initial[
                                CHECKPOINT_DIGEST_FIELD
                            ],
                            recorded_at="2026-08-07T00:01:00Z",
                        )

            outside = base / "outside"
            outside.mkdir()
            link = actual / STORE_ROOT / "shared" / "linked"
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(outside, link)
            with self.assertRaisesRegex(V32DynamicStoreError, "SYMLINK"):
                _writer(store).persist_verified_artifact(
                    run_id=RUN_ID,
                    cycle_index=0,
                    role="theory",
                    relative_ref=f"{STORE_ROOT}/shared/linked/theory.json",
                    document=theory,
                    expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                    recorded_at="2026-08-07T00:01:00Z",
                )

    def test_arbitrary_schema_and_fill_profit_acceptance_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))
            arbitrary = self_digest(
                {"schema_id": "arbitrary_payload_v1", "executable": False},
                "arbitrary_digest",
            )
            with self.assertRaisesRegex(V32DynamicStoreError, "SCHEMA_NOT_ALLOWED"):
                _writer(store).persist_verified_artifact(
                    run_id=RUN_ID,
                    cycle_index=0,
                    role="theory",
                    relative_ref=f"{STORE_ROOT}/shared/theory/arbitrary.json",
                    document=arbitrary,
                    expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                    recorded_at="2026-08-07T00:01:00Z",
                )

            opened = _open(store, dict(initial))
            false_acceptance = self_digest(
                {
                    "schema_id": ACCEPTANCE_SCHEMA_ID,
                    "run_id": RUN_ID,
                    "cycle_index": 1,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                    "fill_claim": True,
                    "pnl_claim": "PROFITABLE",
                },
                ACCEPTANCE_DIGEST_FIELD,
            )
            with self.assertRaisesRegex(V32DynamicStoreError, "MARKET_CLAIM"):
                _writer(store).persist_verified_artifact(
                    run_id=RUN_ID,
                    cycle_index=1,
                    role="analysis_acceptance",
                    relative_ref=f"{STORE_ROOT}/cycles/0001/acceptance.json",
                    document=false_acceptance,
                    expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
                    recorded_at="2026-08-07T00:14:00Z",
                )

    def test_file_and_thread_lock_allow_only_one_concurrent_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))

            def attempt():
                try:
                    return store.open_cycle(
                        run_id=RUN_ID,
                        cycle_index=1,
                        expected_checkpoint_digest=initial[CHECKPOINT_DIGEST_FIELD],
                        opened_at="2026-08-07T00:13:00Z",
                    )["status"]
                except V32DynamicStoreError as exc:
                    return str(exc)

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: attempt(), range(2)))
            self.assertEqual(1, results.count("OPEN"))
            self.assertEqual(1, sum("CAS_CONFLICT" in result for result in results))

    def test_fail_closed_preserves_prefix_and_disables_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, initial = _initialize(Path(temporary))
            opened = _open(store, dict(initial))
            failed = store.fail_closed(
                run_id=RUN_ID,
                expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
                failure_code="COMMIT_SCHEMA_OR_DIGEST_INVALID",
                failure_summary="sealed commit failed deterministic verification",
                failure_evidence_digest="c" * 64,
                failed_at="2026-08-07T00:14:00Z",
            )
            self.assertEqual("FAILED", failed["status"])
            self.assertFalse(failed["resume_allowed"])
            self.assertEqual(0, failed["accepted_analysis_cycles"])
            self.assertIsNotNone(failed["failure_binding"])
            self.assertEqual("NONE_NO_FILL_MODEL", failed["fill_claim"])
            with self.assertRaises(V32DynamicStoreError):
                store.open_cycle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    expected_checkpoint_digest=failed[CHECKPOINT_DIGEST_FIELD],
                    opened_at="2026-08-07T00:15:00Z",
                )


if __name__ == "__main__":
    unittest.main()
