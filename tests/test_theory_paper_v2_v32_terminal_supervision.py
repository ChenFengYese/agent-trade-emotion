from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.application.v32_prospective_runtime import (
    route_v32_prospective_wake_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    DIRECTORY_SCHEMA_ID,
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_recovery_supervision import (
    build_v32_deterministic_recovery_receipt_v1,
    build_v32_recovery_supervision_policy_v1,
    build_v32_supervisor_observation_v1,
)
from trade_system.theory_paper_v2.domain.v32_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_SCHEMA_ID,
    build_v32_current_run_pointer_v1,
)
from trade_system.theory_paper_v2.domain.v32_terminal_seal import (
    REQUIRED_AUDIT_DIRECTORY_COUNT,
    TERMINAL_POINTER_DIGEST_FIELD,
    build_v32_terminal_pointer_v1,
    build_v32_terminal_receipt_v1,
    verify_v32_terminal_pointer_v1,
    verify_v32_terminal_receipt_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_recovery_supervision_store import (
    LocalV32RecoverySupervisionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_terminal_seal_store import (
    LocalV32TerminalSealStore,
)


RUN_ID = "v32-terminal-test"
T0 = "2026-08-08T00:00:00Z"
T1 = "2026-08-08T00:01:00Z"
T2 = "2026-08-08T00:02:00Z"


def fixture_digest(seed: str) -> str:
    return canonical_digest({"seed": seed})


def physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


def binding(document: dict, field: str, ref: str) -> dict[str, str]:
    return {
        "relative_ref": ref,
        "schema_id": document["schema_id"],
        "digest_field": field,
        "semantic_digest": document[field],
        "physical_sha256": physical(document),
    }


def evidence_binding(ref: str, seed: str) -> dict[str, str]:
    return {
        "relative_ref": ref,
        "schema_id": "fixture_v1",
        "digest_field": "fixture_digest",
        "semantic_digest": fixture_digest(seed),
        "physical_sha256": fixture_digest(f"{seed}-physical"),
    }


def terminal_checkpoints() -> tuple[dict, dict, dict]:
    outcome = self_digest(
        {
            "schema_id": "theory_paper_v32_outcome_tick_checkpoint_v1",
            "run_id": RUN_ID,
            "status": "TERMINAL",
            "schedule_set_bindings": [
                {"cycle": cycle} for cycle in range(1, 17)
            ],
            "outcome_receipt_bindings": [
                {"outcome": index, "schedule_id": f"schedule-{index:02d}"}
                for index in range(1, 49)
            ],
            "updated_at": T1,
        },
        "checkpoint_digest",
    )
    predecessor = fixture_digest("dynamic-preterminal")
    supervisor = self_digest(
        {
            "schema_id": "theory_paper_v32_tick_supervisor_checkpoint_v1",
            "run_id": RUN_ID,
            "status": "TERMINAL_COMPLETE",
            "accepted_analysis_cycles": 16,
            "terminal_outcomes": 48,
            "accepted_state_digests": [
                fixture_digest(f"accepted-{cycle}") for cycle in range(1, 17)
            ],
            "terminal_schedule_ids": [
                f"schedule-{index:02d}" for index in range(1, 49)
            ],
            "current_research_checkpoint_digest": predecessor,
            "current_outcome_checkpoint_digest": outcome["checkpoint_digest"],
            "updated_at": T1,
        },
        "tick_supervisor_checkpoint_digest",
    )
    dynamic = self_digest(
        {
            "schema_id": "theory_paper_v32_dynamic_research_checkpoint_v1",
            "run_id": RUN_ID,
            "status": "TERMINAL",
            "accepted_analysis_cycles": 16,
            "predecessor_checkpoint_digest": predecessor,
            "terminal_outcome_checkpoint_digest": outcome["checkpoint_digest"],
            "updated_at": T1,
        },
        "dynamic_research_checkpoint_digest",
    )
    return supervisor, dynamic, outcome


def required_audit_bindings() -> list[dict]:
    identities = [("QUALIFICATION", 0)] + [
        (boundary, cycle)
        for cycle in range(1, 17)
        for boundary in ("ANALYSIS", "ACCEPTANCE", "OUTCOME")
    ]
    return [
        {
            "boundary_type": boundary,
            "cycle_index": cycle,
            "binding": evidence_binding(
                f"audits/{cycle:04d}/{boundary.lower()}.json",
                f"audit-{boundary}-{cycle}",
            ),
        }
        for boundary, cycle in identities
    ]


class TerminalContractTests(unittest.TestCase):
    def test_receipt_requires_all_49_audits_and_exact_terminal_counts(self) -> None:
        supervisor, dynamic, outcome = terminal_checkpoints()
        genesis = evidence_binding("genesis/run-genesis.json", "genesis")
        active = evidence_binding("current-target-run.json", "active")
        receipt = build_v32_terminal_receipt_v1(
            run_id=RUN_ID,
            sealed_at=T2,
            run_genesis_binding=genesis,
            active_genesis_pointer_binding=active,
            supervisor_checkpoint=supervisor,
            supervisor_checkpoint_binding=binding(
                supervisor,
                "tick_supervisor_checkpoint_digest",
                "v32-tick-supervisor-v1/checkpoint.json",
            ),
            dynamic_checkpoint=dynamic,
            dynamic_checkpoint_binding=binding(
                dynamic,
                "dynamic_research_checkpoint_digest",
                "v32-dynamic-cycle-v1/checkpoint.json",
            ),
            outcome_checkpoint=outcome,
            outcome_checkpoint_binding=binding(
                outcome, "checkpoint_digest", "outcome-v32/checkpoint.json"
            ),
            required_audit_directory_bindings=required_audit_bindings(),
            recovery_audit_directory_bindings=[],
            supervisor_observation_bindings=[],
            deterministic_recovery_receipt_bindings=[],
        )
        verify_v32_terminal_receipt_v1(
            receipt,
            supervisor_checkpoint=supervisor,
            dynamic_checkpoint=dynamic,
            outcome_checkpoint=outcome,
        )
        self.assertEqual(
            REQUIRED_AUDIT_DIRECTORY_COUNT,
            receipt["required_audit_directory_count"],
        )
        pointer = build_v32_terminal_pointer_v1(
            run_id=RUN_ID,
            published_at=T2,
            run_genesis_binding=genesis,
            terminal_receipt_binding=binding(
                receipt,
                "v32_terminal_receipt_digest",
                "terminal/terminal-receipt.json",
            ),
            active_genesis_pointer_binding=active,
        )
        self.assertEqual(
            pointer[TERMINAL_POINTER_DIGEST_FIELD],
            verify_v32_terminal_pointer_v1(pointer, terminal_receipt=receipt),
        )
        with self.assertRaisesRegex(ValueError, "V32_TERMINAL_REQUIRED_AUDITS_INVALID"):
            build_v32_terminal_receipt_v1(
                run_id=RUN_ID,
                sealed_at=T2,
                run_genesis_binding=genesis,
                active_genesis_pointer_binding=active,
                supervisor_checkpoint=supervisor,
                supervisor_checkpoint_binding=receipt["supervisor_checkpoint_binding"],
                dynamic_checkpoint=dynamic,
                dynamic_checkpoint_binding=receipt["dynamic_checkpoint_binding"],
                outcome_checkpoint=outcome,
                outcome_checkpoint_binding=receipt["outcome_checkpoint_binding"],
                required_audit_directory_bindings=required_audit_bindings()[:-1],
                recovery_audit_directory_bindings=[],
                supervisor_observation_bindings=[],
                deterministic_recovery_receipt_bindings=[],
            )

    def test_receipt_counts_typed_expiry_rows_as_terminal_schedules(self) -> None:
        supervisor, dynamic, legacy_outcome = terminal_checkpoints()
        outcome_payload = {
            key: deepcopy(value)
            for key, value in legacy_outcome.items()
            if key != "checkpoint_digest"
        }
        outcome_payload["schema_id"] = (
            "theory_paper_v32_outcome_tick_checkpoint_v2"
        )
        outcome_payload["schema_version"] = "2.0.0"
        outcome_payload["outcome_receipt_bindings"] = outcome_payload[
            "outcome_receipt_bindings"
        ][:-1]
        outcome_payload["expiry_terminal_bindings"] = [
            {"terminal_schedule_ids": ["schedule-48"]}
        ]
        outcome = self_digest(outcome_payload, "checkpoint_digest")
        supervisor_payload = {
            key: deepcopy(value)
            for key, value in supervisor.items()
            if key != "tick_supervisor_checkpoint_digest"
        }
        supervisor_payload["current_outcome_checkpoint_digest"] = outcome[
            "checkpoint_digest"
        ]
        supervisor = self_digest(
            supervisor_payload, "tick_supervisor_checkpoint_digest"
        )
        dynamic_payload = {
            key: deepcopy(value)
            for key, value in dynamic.items()
            if key != "dynamic_research_checkpoint_digest"
        }
        dynamic_payload["terminal_outcome_checkpoint_digest"] = outcome[
            "checkpoint_digest"
        ]
        dynamic = self_digest(
            dynamic_payload, "dynamic_research_checkpoint_digest"
        )
        receipt = build_v32_terminal_receipt_v1(
            run_id=RUN_ID,
            sealed_at=T2,
            run_genesis_binding=evidence_binding("genesis/run-genesis.json", "genesis"),
            active_genesis_pointer_binding=evidence_binding(
                "current-target-run.json", "active"
            ),
            supervisor_checkpoint=supervisor,
            supervisor_checkpoint_binding=binding(
                supervisor,
                "tick_supervisor_checkpoint_digest",
                "v32-tick-supervisor-v1/checkpoint.json",
            ),
            dynamic_checkpoint=dynamic,
            dynamic_checkpoint_binding=binding(
                dynamic,
                "dynamic_research_checkpoint_digest",
                "v32-dynamic-cycle-v1/checkpoint.json",
            ),
            outcome_checkpoint=outcome,
            outcome_checkpoint_binding=binding(
                outcome, "checkpoint_digest", "outcome-v32/checkpoint.json"
            ),
            required_audit_directory_bindings=required_audit_bindings(),
            recovery_audit_directory_bindings=[],
            supervisor_observation_bindings=[],
            deterministic_recovery_receipt_bindings=[],
        )
        self.assertEqual(48, receipt["terminal_outcomes"])


class SupervisionStoreTests(unittest.TestCase):
    def test_alert_projection_and_recovery_receipt_are_independent(self) -> None:
        policy = build_v32_recovery_supervision_policy_v1(
            policy_id="policy", frozen_at=T0
        )
        observation = build_v32_supervisor_observation_v1(
            observation_id="observation-1",
            policy=policy,
            run_id=RUN_ID,
            cycle_index=1,
            observed_at=T1,
            lane="AUDIT",
            severity="WARNING",
            failure_code="MISSING_DERIVED_INDEX",
            summary="Sealed shards have no derived index.",
            evidence_bindings=[evidence_binding("sealed/shard.json", "shard")],
            disposition="SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED",
            proposed_action="REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR",
            reason="The repair derives only an index from sealed bytes.",
        )
        receipt = build_v32_deterministic_recovery_receipt_v1(
            receipt_id="recovery-1",
            policy=policy,
            observation=observation,
            action="REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR",
            started_at=T2,
            completed_at="2026-08-08T00:02:01Z",
            input_bindings=[evidence_binding("sealed/shard.json", "shard")],
            output_bindings=[evidence_binding("derived/index.json", "index")],
            result="COMPLETED",
            state_change_boundaries=1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalV32RecoverySupervisionStore(Path(temporary))
            persisted = store.persist_observation(
                policy=policy, observation=observation
            )
            self.assertEqual(0, persisted["formal_state_mutations"])
            self.assertEqual(
                "RECOVERY_PENDING", store.load_alert_status(run_id=RUN_ID)["status"]
            )
            recovery = store.persist_recovery_receipt(
                policy=policy, observation=observation, receipt=receipt
            )
            self.assertEqual(0, recovery["network_requests"])
            self.assertEqual("CLEAR", store.load_alert_status(run_id=RUN_ID)["status"])
            audit_materials = store.load_recovery_audit_materials(run_id=RUN_ID)
            self.assertEqual(1, len(audit_materials))
            self.assertEqual(2, len(audit_materials[0]["sealed_sources"]))
            terminal_materials = store.load_material_bindings(run_id=RUN_ID)
            self.assertEqual(
                1, len(terminal_materials["supervisor_observation_bindings"])
            )
            self.assertEqual(
                1,
                len(terminal_materials["deterministic_recovery_receipt_bindings"]),
            )


class TerminalSealStoreTests(unittest.TestCase):
    @staticmethod
    def _write(path: Path, document: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(document) + b"\n")

    def test_terminal_pointer_is_separate_and_idempotent(self) -> None:
        supervisor, dynamic, outcome = terminal_checkpoints()
        with tempfile.TemporaryDirectory() as temporary:
            control = Path(temporary) / ".runtime" / "theory-paper-v32"
            run_root = control / "runs" / RUN_ID
            run_root.mkdir(parents=True)
            genesis = self_digest(
                {
                    "schema_id": RUN_GENESIS_SCHEMA_ID,
                    "run_id": RUN_ID,
                    "created_at": T0,
                },
                RUN_GENESIS_DIGEST_FIELD,
            )
            genesis_binding = binding(
                genesis,
                RUN_GENESIS_DIGEST_FIELD,
                f"runs/{RUN_ID}/genesis/run-genesis.json",
            )
            active = build_v32_current_run_pointer_v1(
                published_at=T0,
                run_id=RUN_ID,
                run_genesis_binding=genesis_binding,
                experiment_contract_digest=fixture_digest("contract"),
                active_authority_digest=fixture_digest("authority"),
            )
            self._write(run_root / "genesis/run-genesis.json", genesis)
            self._write(control / "current-target-run.json", active)
            self._write(
                run_root / "v32-tick-supervisor-v1/checkpoint.json", supervisor
            )
            self._write(
                run_root / "v32-dynamic-cycle-v1/checkpoint.json", dynamic
            )
            self._write(run_root / "outcome-v32/checkpoint.json", outcome)
            materials: list[dict] = []
            identities = [("QUALIFICATION", 0)] + [
                (boundary, cycle)
                for cycle in range(1, 17)
                for boundary in ("ANALYSIS", "ACCEPTANCE", "OUTCOME")
            ]
            for boundary, cycle in identities:
                directory = self_digest(
                    {
                        "schema_id": DIRECTORY_SCHEMA_ID,
                        "run_id": RUN_ID,
                        "cycle_index": cycle,
                        "boundary_type": boundary,
                    },
                    DIRECTORY_DIGEST_FIELD,
                )
                ref = (
                    f"v32-authorized-revisions-v1/{RUN_ID}/cycles/{cycle:04d}/"
                    f"audit/{boundary.lower()}/{directory[DIRECTORY_DIGEST_FIELD]}.json"
                )
                self._write(run_root / ref, directory)
                materials.append(
                    {
                        "boundary_type": boundary,
                        "cycle_index": cycle,
                        "directory": directory,
                    }
                )
            active_bytes = (control / "current-target-run.json").read_bytes()
            store = LocalV32TerminalSealStore(run_root)
            first = store.seal_terminal(
                run_id=RUN_ID,
                sealed_at=T2,
                supervisor_checkpoint=supervisor,
                dynamic_checkpoint=dynamic,
                outcome_checkpoint=outcome,
                required_audit_materials=materials,
                recovery_audit_materials=[],
            )
            second = store.seal_terminal(
                run_id=RUN_ID,
                sealed_at="2026-08-08T00:03:00Z",
                supervisor_checkpoint=supervisor,
                dynamic_checkpoint=dynamic,
                outcome_checkpoint=outcome,
                required_audit_materials=materials,
                recovery_audit_materials=[],
            )
            self.assertEqual("CREATED", first["terminal_pointer_write_status"])
            self.assertEqual(
                "EXISTING_IDENTICAL", second["terminal_pointer_write_status"]
            )
            self.assertEqual(
                active_bytes, (control / "current-target-run.json").read_bytes()
            )
            self.assertTrue((control / "terminal-target-run.json").is_file())
            first_audit = materials[0]["directory"]
            first_ref = (
                f"v32-authorized-revisions-v1/{RUN_ID}/cycles/0000/audit/"
                f"qualification/{first_audit[DIRECTORY_DIGEST_FIELD]}.json"
            )
            tampered_payload = deepcopy(first_audit)
            tampered_payload.pop(DIRECTORY_DIGEST_FIELD)
            tampered_payload["boundary_type"] = "ANALYSIS"
            tampered = self_digest(tampered_payload, DIRECTORY_DIGEST_FIELD)
            self._write(run_root / first_ref, tampered)
            with self.assertRaisesRegex(ValueError, "BINDING_DRIFT"):
                store.load_terminal_pointer(run_id=RUN_ID)


class _Clock:
    def __call__(self) -> str:
        return T2


class _SupervisorStore:
    def __init__(self, checkpoint: dict) -> None:
        self.checkpoint = checkpoint

    def load_checkpoint(self, *, run_id: str) -> dict:
        return deepcopy(self.checkpoint)


class _DynamicStore:
    def __init__(self, checkpoint: dict) -> None:
        self.checkpoint = checkpoint
        self.mark_calls = 0

    def load_checkpoint(self, *, run_id: str) -> dict:
        return deepcopy(self.checkpoint)

    def mark_terminal(self, **kwargs) -> dict:
        self.mark_calls += 1
        self.checkpoint["status"] = "TERMINAL"
        self.checkpoint["dynamic_research_checkpoint_digest"] = fixture_digest(
            "marked-dynamic"
        )
        return deepcopy(self.checkpoint)


class _OutcomeStore:
    def __init__(self, checkpoint: dict) -> None:
        self.checkpoint = checkpoint

    def load_checkpoint(self, *, run_id: str) -> dict:
        return deepcopy(self.checkpoint)

    def load_schedule_sets(self, *, run_id: str) -> list:
        return []


class _RevisionStore:
    def load_audit_bundle(self, *, run_id: str, cycle_index: int, boundary_type: str):
        if boundary_type == "RECOVERY":
            return None
        return {
            "directory": {
                "schema_id": DIRECTORY_SCHEMA_ID,
                "run_id": run_id,
                "cycle_index": cycle_index,
                "boundary_type": boundary_type,
            },
            "shards": [{}],
        }


class _TerminalPort:
    def __init__(self) -> None:
        self.pointer = None
        self.seal_calls = 0

    def load_terminal_pointer(self, *, run_id: str):
        return deepcopy(self.pointer)

    def seal_terminal(self, **kwargs):
        self.seal_calls += 1
        self.pointer = {
            "v32_terminal_pointer_digest": fixture_digest("terminal-pointer")
        }
        return {
            "status": "TERMINAL_SEALED",
            "terminal_pointer_digest": self.pointer[
                "v32_terminal_pointer_digest"
            ],
        }


class RuntimeTerminalRoutingTests(unittest.TestCase):
    def test_dynamic_mark_and_final_seal_are_separate_wakes(self) -> None:
        supervisor, dynamic, outcome = terminal_checkpoints()
        supervisor.update(
            {
                "outcome_schedule_set_digests": [],
                "active_permit_digest": None,
                "active_permit_kind": None,
            }
        )
        dynamic["status"] = "OUTCOME_TAIL"
        dynamic_store = _DynamicStore(dynamic)
        terminal = _TerminalPort()
        kwargs = {
            "supervisor_store": _SupervisorStore(supervisor),
            "dynamic_store": dynamic_store,
            "outcome_store": _OutcomeStore(outcome),
            "mailbox": object(),
            "revision_store": _RevisionStore(),
            "audit_completion_store": object(),
            "audit_lane": object(),
            "analysis_port": object(),
            "outcome_port": object(),
            "cycle_audit_policy": build_v32_cycle_audit_policy_v1(
                policy_id="audit", run_scope_id=RUN_ID, frozen_at=T0
            ),
            "run_id": RUN_ID,
            "clock": _Clock(),
            "terminal_seal_port": terminal,
        }
        with (
            patch(
                "trade_system.theory_paper_v2.application.v32_prospective_runtime.verify_v32_tick_supervisor_checkpoint",
                return_value=fixture_digest("supervisor"),
            ),
            patch(
                "trade_system.theory_paper_v2.application.v32_prospective_runtime._audit_gate_or_next",
                return_value=None,
            ),
            patch(
                "trade_system.theory_paper_v2.application.v32_prospective_runtime._outcome_audit_or_next",
                return_value=None,
            ),
        ):
            first = route_v32_prospective_wake_v1(**kwargs)
            second = route_v32_prospective_wake_v1(**kwargs)
        self.assertEqual("DYNAMIC_TERMINAL_MARKED", first["boundary_kind"])
        self.assertEqual(
            "FINAL_TERMINAL_RECEIPT_AND_POINTER_SEALED", second["boundary_kind"]
        )
        self.assertEqual(1, dynamic_store.mark_calls)
        self.assertEqual(1, terminal.seal_calls)
        self.assertEqual(1, first["high_level_boundaries_completed_this_wake"])
        self.assertEqual(1, second["high_level_boundaries_completed_this_wake"])


if __name__ == "__main__":
    unittest.main()
