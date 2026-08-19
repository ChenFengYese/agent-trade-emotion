from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v31_authorization import (
    V31AuthorizationError,
)
from trade_system.theory_paper_v2.domain.governance.v311_successor_authority_envelope_v2 import (
    V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
    V311_TARGET_ACTIVE_AUTHORITY_PATH,
    V311SuccessorAuthorityEnvelopeV2Error,
    build_v311_runtime_closure_receipt_v2,
    build_v311_successor_authority_envelope_v2,
    build_v311_supervisor_policy_v2,
    project_v311_application_authority_chain_v2,
    verify_v311_runtime_closure_receipt_v2,
    verify_v311_successor_authority_envelope_v2,
    verify_v311_supervisor_policy_v2,
)
from trade_system.theory_paper_v2.domain.governance.v311_fresh_process_trace_v2 import (
    build_v311_fresh_process_trace_receipt_v2,
)
from trade_system.theory_paper_v2.domain.governance.v311_qualification_retirement_v2 import (
    build_v311_qualification_retirement_receipt_v2,
)
from trade_system.theory_paper_v2.domain.governance.v311_successor_user_approval_v2 import (
    REQUIRED_USER_APPROVAL_STATEMENTS,
    SUCCESSOR_USER_APPROVAL_PATH,
    build_v311_successor_user_approval_receipt_v2,
)
from trade_system.theory_paper_v2.domain.v31_association_preregistration_v2 import (
    build_v31_association_preregistration_v2,
)
from trade_system.theory_paper_v2.domain.v31_evaluation_contract_v2 import (
    build_v31_evaluation_contract_v2,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    build_outcome_clock_policy,
)
from trade_system.theory_paper_v2.domain.v31_sentiment_native_projection_v2 import (
    build_v31_native_sentiment_source_registry,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_runtime_closure_v2 import (
    V31RuntimeClosureError,
    build_v31_runtime_closure_bindings_v2,
    collect_v31_static_runtime_closure_v2,
    verify_v31_runtime_closure_bindings_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v311_successor_current_research_v2 import (
    load_v311_successor_authorization_chain_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v311_successor_authority_composition_v2 import (
    QUALIFICATION_V3,
    TARGET_V4,
    seal_v311_runtime_closure_from_fresh_process_v2,
    seal_v311_successor_user_approval_v2,
    v311_versioned_authority_paths_v2,
)


_PROJECT = Path(__file__).resolve().parents[1]
_LEGACY_RUN_ID = "v31-prospective-btcusdt-20260806t183742z"


def _binding(path: str, document: dict, digest_field: str) -> dict:
    return {
        "path": path,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


def _legacy_failure_fixture(legacy_chain: dict) -> dict:
    run_id = _LEGACY_RUN_ID
    research = self_digest(
        {
            "schema_id": "theory_paper_v31_research_checkpoint",
            "run_id": run_id,
            "status": "READY_FOR_CYCLE",
            "completed_cycles": 1,
            "next_cycle_index": 2,
            "resume_allowed": True,
            "current_authority_digest": legacy_chain["authority"][
                "authority_digest"
            ],
        },
        "checkpoint_digest",
    )
    failure = self_digest(
        {
            "schema_id": "theory_paper_v31_monitor_failure",
            "run_id": run_id,
            "occurred_at": "2026-08-06T19:57:31Z",
            "failure_code": "V31_MONITOR_PUBLIC_OBSERVATION_OR_RESOLUTION_FAILED",
            "resume_allowed": False,
            "planned_cycles": 1,
            "reserved_attempts": 1,
            "resolved_cycles": 0,
        },
        "failure_digest",
    )
    attempt = self_digest(
        {
            "schema_id": "theory_paper_v31_monitor_resolution_attempt",
            "run_id": run_id,
            "cycle_index": 1,
            "attempt_number": 1,
            "retry_allowed": False,
        },
        "monitor_attempt_digest",
    )
    monitor = self_digest(
        {
            "schema_id": "theory_paper_v31_monitor_checkpoint",
            "run_id": run_id,
            "status": "FAILED_CLOSED",
            "resume_allowed": False,
            "failure_digest": failure["failure_digest"],
            "experiment_contract_digest": legacy_chain["experiment_contract"][
                "experiment_contract_digest"
            ],
            "plan_bindings": [{"cycle_index": 1}],
            "resolution_attempt_bindings": [{"cycle_index": 1}],
            "outcome_bindings": [],
        },
        "checkpoint_digest",
    )
    documents = {
        "research_checkpoint": research,
        "monitor_checkpoint": monitor,
        "monitor_failure": failure,
        "resolution_attempt": attempt,
    }
    return {
        **documents,
        "bindings": {
            name: _binding(
                f"legacy/{name}.json",
                document,
                {
                    "research_checkpoint": "checkpoint_digest",
                    "monitor_checkpoint": "checkpoint_digest",
                    "monitor_failure": "failure_digest",
                    "resolution_attempt": "monitor_attempt_digest",
                }[name],
            )
            for name, document in documents.items()
        },
    }


class V311SuccessorAuthorityEnvelopeV2Tests(unittest.TestCase):
    def test_supervisor_policy_is_exact_and_permission_expansion_is_rejected(self) -> None:
        policy = build_v311_supervisor_policy_v2()
        self.assertEqual(
            policy["supervisor_policy_digest"],
            verify_v311_supervisor_policy_v2(policy),
        )
        tampered = copy.deepcopy(policy)
        tampered.pop("supervisor_policy_digest")
        tampered["authority_boundary"]["paper_trading"] = True
        tampered = self_digest(tampered, "supervisor_policy_digest")
        with self.assertRaises(V311SuccessorAuthorityEnvelopeV2Error):
            verify_v311_supervisor_policy_v2(tampered)

    def test_runtime_closure_receipt_needs_infrastructure_physical_replay(self) -> None:
        roots = (
            "trade_system/theory_paper_v2/domain/v31_experiment_supervisor_v2.py",
        )
        bindings = build_v31_runtime_closure_bindings_v2(
            project_root=_PROJECT,
            production_root_paths=roots,
            trace_paths=roots,
        )
        trace = build_v311_fresh_process_trace_receipt_v2(
            trace_id="v311-runtime-trace-20260807t000000z",
            started_at="2026-08-06T23:59:58Z",
            completed_at="2026-08-06T23:59:59Z",
            parent_pid=100,
            worker_pid=101,
            invocation_nonce="nonce-12345678",
            echoed_nonce="nonce-12345678",
            python_executable="/opt/homebrew/bin/python3.12",
            python_version="3.12-test",
            production_root_paths=roots,
            imported_root_modules=(
                "trade_system.theory_paper_v2.domain.v31_experiment_supervisor_v2",
            ),
            observed_project_python_paths=roots,
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_empty=True,
        )
        trace_binding = _binding(
            "config/v311-contracts/fresh-trace.json",
            trace,
            "fresh_process_trace_digest",
        )
        receipt = build_v311_runtime_closure_receipt_v2(
            run_scope_id="v311-target-btcusdt-20260807t000000z",
            frozen_at="2026-08-07T00:00:00Z",
            production_root_paths=roots,
            fresh_process_trace=trace,
            fresh_process_trace_binding=trace_binding,
            frozen_bindings=bindings,
        )
        verify_v311_runtime_closure_receipt_v2(receipt)
        self.assertEqual(
            bindings,
            verify_v31_runtime_closure_bindings_v2(
                project_root=_PROJECT,
                production_root_paths=receipt["production_root_paths"],
                trace_paths=receipt["fresh_process_trace_paths"],
                frozen_bindings=receipt["frozen_bindings"],
            ),
        )

        drifted_bindings = dict(bindings)
        first = next(iter(drifted_bindings))
        drifted_bindings[first] = "0" * 64
        semantically_well_formed_but_untrue = build_v311_runtime_closure_receipt_v2(
            run_scope_id="v311-target-btcusdt-20260807t000000z",
            frozen_at="2026-08-07T00:00:00Z",
            production_root_paths=roots,
            fresh_process_trace=trace,
            fresh_process_trace_binding=trace_binding,
            frozen_bindings=drifted_bindings,
        )
        verify_v311_runtime_closure_receipt_v2(
            semantically_well_formed_but_untrue
        )
        with self.assertRaises(V31RuntimeClosureError):
            verify_v31_runtime_closure_bindings_v2(
                project_root=_PROJECT,
                production_root_paths=roots,
                trace_paths=roots,
                frozen_bindings=drifted_bindings,
            )

    def test_successor_loader_static_closure_includes_new_core_and_dependencies(self) -> None:
        roots = (
            "trade_system/theory_paper_v2/domain/governance/"
            "v311_successor_authority_envelope_v2.py",
            "trade_system/theory_paper_v2/infrastructure/authority/"
            "v311_successor_current_research_v2.py",
            "trade_system/theory_paper_v2/infrastructure/authority/"
            "v311_successor_authority_composition_v2.py",
        )
        closure = collect_v31_static_runtime_closure_v2(
            project_root=_PROJECT, production_root_paths=roots
        )
        self.assertTrue(set(roots).issubset(closure))
        self.assertIn(
            "trade_system/theory_paper_v2/domain/governance/"
            "v31_successor_qualification_v2.py",
            closure,
        )
        self.assertIn(
            "trade_system/theory_paper_v2/infrastructure/authority/"
            "v311_fresh_process_trace_v2.py",
            closure,
        )
        self.assertIn(
            "trade_system/theory_paper_v2/infrastructure/authority/"
            "v31_runtime_closure_v2.py",
            closure,
        )
        self.assertGreater(len(closure), 74)

    def test_loader_replays_legacy_before_opening_any_successor_document(self) -> None:
        target = (
            "trade_system.theory_paper_v2.infrastructure.authority."
            "v311_successor_current_research_v2"
        )
        with patch(
            f"{target}.load_v31_active_authorization_chain",
            side_effect=V31AuthorizationError("legacy-drift"),
        ), patch(f"{target}._contained_regular_file") as contained:
            with self.assertRaisesRegex(
                V311SuccessorAuthorityEnvelopeV2Error,
                "V311_LEGACY_FULL_LOADER_FAILED",
            ):
                load_v311_successor_authorization_chain_v2(_PROJECT)
        contained.assert_not_called()

    def _projection_fixture(self, target_chain: dict) -> dict:
        return {
            "envelope": {},
            "legacy_active_chain": {},
            "legacy_failure_evidence": {},
            "qualification_v3_chain": {},
            "qualification_run_genesis": {},
            "target_v4_chain": target_chain,
            "theory_addendum_binding": {},
            "successor_user_approval": {},
            "clock_policy": {},
            "supervisor_policy": {},
            "runtime_closure": {},
            "sentiment_source_registry": {},
            "association_preregistration": {},
            "evaluation_contract": {},
            "successor_qualifications": {},
            "qualification_retirement": {},
        }

    def test_envelope_reconstruction_enforces_two_run_lineage(self) -> None:
        qualification_run = "v311-qualification-btcusdt-20260807t000000z"
        target_run = "v311-target-btcusdt-20260807t000400z"
        gate_receipts = {
            f"Q{index}": self_digest(
                {
                    "schema_id": "test_v31_qualification_receipt",
                    "gate_id": f"Q{index}",
                },
                "qualification_receipt_digest",
            )
            for index in range(9)
        }

        def fake_chain(run_id: str, recorded_at: str, tag: str) -> dict:
            specs = {
                "theory_approval": (
                    "theory_paper_v31_user_approval_receipt",
                    "approval_receipt_digest",
                ),
                "experiment_contract": (
                    "theory_paper_v2_v31_minimal_experiment_contract",
                    "experiment_contract_digest",
                ),
                "manifest": (
                    "theory_paper_v31_frozen_experiment_manifest",
                    "manifest_digest",
                ),
                "authorization_receipt": (
                    "theory_paper_v31_experiment_authorization_receipt",
                    "authorization_receipt_digest",
                ),
                "authority": (
                    "theory_paper_v31_current_research_authority",
                    "authority_digest",
                ),
            }
            documents = {}
            for name, (schema_id, digest_field) in specs.items():
                body = {"schema_id": schema_id, "tag": tag}
                if name == "authority":
                    body.update(
                        {
                            "authorized_run_id": run_id,
                            "authority_id": f"v311-{tag}-authority",
                            "recorded_at": recorded_at,
                        }
                    )
                elif name == "manifest":
                    body["implementation_bindings"] = {
                        f"legacy/path-{index:02d}.py": hashlib.sha256(
                            f"legacy:{index}".encode("utf-8")
                        ).hexdigest()
                        for index in range(74)
                    }
                documents[name] = self_digest(body, digest_field)
            return {
                "authority": documents["authority"],
                "authorization_receipt": documents["authorization_receipt"],
                "manifest": documents["manifest"],
                "experiment_contract": documents["experiment_contract"],
                "predecessor_authority": {},
                "qualification_receipts": copy.deepcopy(gate_receipts),
                "theory_approval": documents["theory_approval"],
            }

        legacy_chain = fake_chain(
            _LEGACY_RUN_ID, "2026-08-06T18:51:35Z", "legacy"
        )
        legacy_evidence = _legacy_failure_fixture(legacy_chain)
        qualification_chain = fake_chain(
            qualification_run, "2026-08-07T00:00:00Z", "qualification"
        )
        target_chain = fake_chain(
            target_run, "2026-08-07T00:04:00Z", "target"
        )

        def binding(path: str, document: dict, digest_field: str) -> dict:
            return {
                "path": path,
                "schema_id": document["schema_id"],
                "digest_field": digest_field,
                "semantic_digest": document[digest_field],
                "physical_sha256": hashlib.sha256(
                    canonical_bytes(document) + b"\n"
                ).hexdigest(),
            }

        digest_fields = {
            "theory_approval": "approval_receipt_digest",
            "experiment_contract": "experiment_contract_digest",
            "manifest": "manifest_digest",
            "authorization_receipt": "authorization_receipt_digest",
            "authority": "authority_digest",
        }
        qualification_bindings = {
            name: binding(
                (
                    V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH
                    if name == "authority"
                    else f"config/v311-qualification/{name}.json"
                ),
                qualification_chain[name],
                digest_fields[name],
            )
            for name in digest_fields
        }
        target_bindings = {
            name: binding(
                (
                    V311_TARGET_ACTIVE_AUTHORITY_PATH
                    if name == "authority"
                    else f"config/v311-target/{name}.json"
                ),
                target_chain[name],
                digest_fields[name],
            )
            for name in digest_fields
        }
        translated = {
            "relative_ref": "genesis/current-authority.json",
            **{
                key: qualification_bindings["authority"][key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        }
        qualification_authority = qualification_chain["authority"]
        run_genesis = self_digest(
            {
                "schema_id": "theory_paper_v31_run_genesis",
                "schema_version": "1.0.0",
                "run_id": qualification_run,
                "genesis_artifacts": [
                    {
                        "source_role": "current_authority",
                        "global_ref": V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
                        "local_ref": "genesis/current-authority.json",
                        "schema_id": qualification_authority["schema_id"],
                        "digest_field": "authority_digest",
                        "semantic_digest": qualification_authority[
                            "authority_digest"
                        ],
                        "global_physical_sha256": qualification_bindings[
                            "authority"
                        ]["physical_sha256"],
                        "local_physical_sha256": qualification_bindings[
                            "authority"
                        ]["physical_sha256"],
                        "exact_bytes_copied": True,
                    }
                ],
            },
            "run_genesis_digest",
        )
        run_genesis_binding = binding(
            f"agent-cluster/experiments/{qualification_run}/"
            "genesis/run-genesis.json",
            run_genesis,
            "run_genesis_digest",
        )
        genesis_evidence = {
            "run_genesis_digest": run_genesis["run_genesis_digest"],
            "run_id": qualification_run,
            "local_copy_bindings": {"current_authority": translated},
            "authority_copy_binding": translated,
        }
        clock = build_outcome_clock_policy()
        source = self_digest(
            {
                "schema_id": "theory_paper_v31_successor_public_source_qualification_v2",
                "run_id": qualification_run,
                "predecessor_run_id": _LEGACY_RUN_ID,
                "authority_digest": qualification_authority["authority_digest"],
                "authority_binding": translated,
                "authority_recorded_at": qualification_authority["recorded_at"],
                "qualified_at": "2026-08-07T00:01:00Z",
                "expires_at": "2026-08-07T00:06:00Z",
            },
            "source_qualification_v2_digest",
        )
        codex = self_digest(
            {
                "schema_id": "theory_paper_v311_codex_durable_delivery_qualification_v3",
                "run_id": qualification_run,
                "predecessor_run_id": _LEGACY_RUN_ID,
                "authority_digest": qualification_authority["authority_digest"],
                "authority_binding": translated,
                "authority_recorded_at": qualification_authority["recorded_at"],
                "qualified_at": "2026-08-07T00:02:00Z",
                "cycle_index": 1,
                "accepted_state_digest": "a" * 64,
                "source_qualification_v2_digest": source[
                    "source_qualification_v2_digest"
                ],
            },
            "codex_qualification_v3_digest",
        )
        monitor = self_digest(
            {
                "schema_id": "theory_paper_v31_successor_outcome_monitor_qualification_v2",
                "run_id": qualification_run,
                "predecessor_run_id": _LEGACY_RUN_ID,
                "authority_digest": qualification_authority["authority_digest"],
                "authority_binding": translated,
                "authority_recorded_at": qualification_authority["recorded_at"],
                "qualified_at": "2026-08-07T00:03:00Z",
                "clock_policy": clock,
                "raw_first_probe": {
                    "clock_policy_digest": clock["clock_policy_digest"]
                },
            },
            "monitor_qualification_v2_digest",
        )
        qualifications = {
            "public_source": source,
            "codex_durable_delivery": codex,
            "outcome_monitor": monitor,
        }
        qualification_digest_fields = {
            "public_source": "source_qualification_v2_digest",
            "codex_durable_delivery": "codex_qualification_v3_digest",
            "outcome_monitor": "monitor_qualification_v2_digest",
        }
        qualification_document_bindings = {
            name: binding(
                f"agent-cluster/experiments/v311-qualification/{name}.json",
                document,
                qualification_digest_fields[name],
            )
            for name, document in qualifications.items()
        }
        supervisor = build_v311_supervisor_policy_v2()
        roots = (
            "trade_system/theory_paper_v2/domain/v31_experiment_supervisor_v2.py",
        )
        closure_bindings = build_v31_runtime_closure_bindings_v2(
            project_root=_PROJECT,
            production_root_paths=roots,
            trace_paths=roots,
        )
        fresh_trace = build_v311_fresh_process_trace_receipt_v2(
            trace_id="v311-envelope-trace-20260807t000000z",
            started_at="2026-08-06T23:59:57Z",
            completed_at="2026-08-06T23:59:58Z",
            parent_pid=200,
            worker_pid=201,
            invocation_nonce="nonce-envelope-12345678",
            echoed_nonce="nonce-envelope-12345678",
            python_executable="/opt/homebrew/bin/python3.12",
            python_version="3.12-test",
            production_root_paths=roots,
            imported_root_modules=(
                "trade_system.theory_paper_v2.domain.v31_experiment_supervisor_v2",
            ),
            observed_project_python_paths=roots,
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_empty=True,
        )
        fresh_trace_binding = binding(
            "config/v311-contracts/fresh-trace.json",
            fresh_trace,
            "fresh_process_trace_digest",
        )
        closure = build_v311_runtime_closure_receipt_v2(
            run_scope_id=target_run,
            frozen_at="2026-08-07T00:00:00Z",
            production_root_paths=roots,
            fresh_process_trace=fresh_trace,
            fresh_process_trace_binding=fresh_trace_binding,
            frozen_bindings=closure_bindings,
        )
        registry = build_v31_native_sentiment_source_registry()
        association = build_v31_association_preregistration_v2(
            run_scope_id=target_run, frozen_at="2026-08-07T00:00:00Z"
        )
        evaluation = build_v31_evaluation_contract_v2(
            association_preregistration=association,
            run_scope_id=target_run,
            frozen_at="2026-08-07T00:00:01Z",
        )
        auxiliary = {
            "clock_policy": clock,
            "supervisor_policy": supervisor,
            "runtime_closure": closure,
            "sentiment_source_registry": registry,
            "association_preregistration": association,
            "evaluation_contract": evaluation,
        }
        auxiliary_digest_fields = {
            "clock_policy": "clock_policy_digest",
            "supervisor_policy": "supervisor_policy_digest",
            "runtime_closure": "runtime_closure_receipt_digest",
            "sentiment_source_registry": "registry_digest",
            "association_preregistration": "association_preregistration_digest",
            "evaluation_contract": "evaluation_contract_digest",
        }
        auxiliary_bindings = {
            name: binding(
                f"config/v311-contracts/{name}.json",
                document,
                auxiliary_digest_fields[name],
            )
            for name, document in auxiliary.items()
        }
        addendum_binding = {
            "path": "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md",
            "version": "3.1.1",
            "review_status": "FROZEN_APPROVED_SUCCESSOR",
            "physical_sha256": "1" * 64,
        }
        successor_approval = build_v311_successor_user_approval_receipt_v2(
            approval_id="v311-successor-approval-20260806t235900z",
            approved_at="2026-08-06T23:59:00Z",
            theory_addendum_binding=addendum_binding,
            user_statements=REQUIRED_USER_APPROVAL_STATEMENTS,
        )
        successor_approval_binding = binding(
            SUCCESSOR_USER_APPROVAL_PATH,
            successor_approval,
            "successor_user_approval_digest",
        )
        qualification_checkpoint = self_digest(
            {
                "schema_id": "theory_paper_v31_research_checkpoint",
                "schema_version": "1.2.0",
                "run_id": qualification_run,
                "status": "READY_FOR_CYCLE",
                "revision": 2,
                "completed_cycles": 1,
                "next_cycle_index": 2,
                "accepted_state_ref": (
                    "cycles/0001/accepted-research-state.json"
                ),
                "accepted_state_digest": "a" * 64,
                "current_authority_digest": qualification_authority[
                    "authority_digest"
                ],
                "current_authority_ref": "genesis/current-authority.json",
                "run_genesis_ref": "genesis/run-genesis.json",
                "run_genesis_digest": run_genesis["run_genesis_digest"],
                "resume_allowed": True,
                "updated_at": "2026-08-07T00:03:30Z",
            },
            "checkpoint_digest",
        )
        qualification_checkpoint_binding = binding(
            f"agent-cluster/experiments/{qualification_run}/checkpoint.json",
            qualification_checkpoint,
            "checkpoint_digest",
        )
        qualification_monitor_checkpoint = self_digest(
            {
                "schema_id": "theory_paper_v31_monitor_checkpoint",
                "schema_version": "1.0.0",
                "run_id": qualification_run,
                "status": "ACTIVE",
                "resume_allowed": True,
                "plan_bindings": [{"cycle_index": 1}],
                "resolution_attempt_bindings": [],
                "outcome_bindings": [],
                "failure_ref": None,
                "failure_digest": None,
                "experiment_contract_digest": qualification_chain[
                    "experiment_contract"
                ]["experiment_contract_digest"],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
                "updated_at": "2026-08-07T00:03:35Z",
            },
            "checkpoint_digest",
        )
        qualification_monitor_checkpoint_binding = binding(
            f"agent-cluster/experiments/{qualification_run}/"
            "monitor/checkpoint.json",
            qualification_monitor_checkpoint,
            "checkpoint_digest",
        )
        retirement_module = (
            "trade_system.theory_paper_v2.domain.governance."
            "v311_qualification_retirement_v2"
        )
        with patch(
            f"{retirement_module}.verify_successor_public_source_qualification_v2",
            return_value=source["source_qualification_v2_digest"],
        ), patch(
            f"{retirement_module}.verify_successor_codex_durable_qualification_v3",
            return_value=codex["codex_qualification_v3_digest"],
        ), patch(
            f"{retirement_module}.verify_successor_monitor_qualification_v2",
            return_value=monitor["monitor_qualification_v2_digest"],
        ), patch(
            f"{retirement_module}.verify_v311_qualification_run_genesis_v2",
            return_value=genesis_evidence,
        ):
            retirement = build_v311_qualification_retirement_receipt_v2(
                retirement_id="v311-qualification-retirement-20260807t000340z",
                retired_at="2026-08-07T00:03:40Z",
                target_run_id=target_run,
                qualification_v3_chain=qualification_chain,
                qualification_v3_document_bindings=qualification_bindings,
                qualification_run_genesis=run_genesis,
                qualification_run_genesis_binding=run_genesis_binding,
                research_checkpoint=qualification_checkpoint,
                research_checkpoint_binding=qualification_checkpoint_binding,
                monitor_checkpoint=qualification_monitor_checkpoint,
                monitor_checkpoint_binding=(
                    qualification_monitor_checkpoint_binding
                ),
                successor_qualifications=qualifications,
                successor_qualification_bindings=qualification_document_bindings,
            )
        retirement_binding = binding(
            f"agent-cluster/experiments/{qualification_run}/"
            "qualification-retirement.v2.json",
            retirement,
            "qualification_retirement_digest",
        )

        module = (
            "trade_system.theory_paper_v2.domain.governance."
            "v311_successor_authority_envelope_v2"
        )

        def project_fake(chain: dict) -> dict:
            return {
                name: chain[name]
                for name in (
                    "theory_approval",
                    "experiment_contract",
                    "manifest",
                    "authorization_receipt",
                    "authority",
                )
            }

        with patch(
            f"{module}.project_v31_application_authority_chain_v2",
            side_effect=project_fake,
        ), patch(
            f"{module}.verify_v311_qualification_run_genesis_v2",
            return_value=genesis_evidence,
        ), patch(
            f"{module}.verify_successor_public_source_qualification_v2",
            return_value=source["source_qualification_v2_digest"],
        ), patch(
            f"{module}.verify_successor_codex_durable_qualification_v3",
            return_value=codex["codex_qualification_v3_digest"],
        ), patch(
            f"{module}.verify_successor_monitor_qualification_v2",
            return_value=monitor["monitor_qualification_v2_digest"],
        ):
            envelope = build_v311_successor_authority_envelope_v2(
                envelope_id="v311-successor-envelope-20260807t000500z",
                created_at="2026-08-07T00:05:00Z",
                legacy_active_chain=legacy_chain,
                legacy_failure_evidence=legacy_evidence,
                qualification_v3_chain=qualification_chain,
                qualification_v3_document_bindings=qualification_bindings,
                qualification_run_root_ref=(
                    f"agent-cluster/experiments/{qualification_run}"
                ),
                qualification_run_genesis=run_genesis,
                qualification_run_genesis_binding=run_genesis_binding,
                target_v4_chain=target_chain,
                target_v4_document_bindings=target_bindings,
                theory_addendum_binding=addendum_binding,
                successor_user_approval=successor_approval,
                successor_user_approval_binding=successor_approval_binding,
                clock_policy=clock,
                supervisor_policy=supervisor,
                runtime_closure=closure,
                sentiment_source_registry=registry,
                association_preregistration=association,
                evaluation_contract=evaluation,
                auxiliary_document_bindings=auxiliary_bindings,
                successor_qualifications=qualifications,
                successor_qualification_bindings=qualification_document_bindings,
                qualification_retirement=retirement,
                qualification_retirement_binding=retirement_binding,
            )
            verify_v311_successor_authority_envelope_v2(
                envelope,
                legacy_active_chain=legacy_chain,
                legacy_failure_evidence=legacy_evidence,
                qualification_v3_chain=qualification_chain,
                qualification_run_genesis=run_genesis,
                target_v4_chain=target_chain,
                theory_addendum_binding=envelope["theory_addendum_binding"],
                successor_user_approval=successor_approval,
                clock_policy=clock,
                supervisor_policy=supervisor,
                runtime_closure=closure,
                sentiment_source_registry=registry,
                association_preregistration=association,
                evaluation_contract=evaluation,
                successor_qualifications=qualifications,
                qualification_retirement=retirement,
            )
            # Regression: call the real successor projection, including its
            # unmocked envelope verifier.  The former implementation omitted
            # approval/retirement arguments and raised TypeError here.
            loaded = {
                "envelope": envelope,
                "legacy_active_chain": legacy_chain,
                "legacy_failure_evidence": legacy_evidence,
                "qualification_v3_chain": qualification_chain,
                "qualification_run_genesis": run_genesis,
                "target_v4_chain": target_chain,
                "theory_addendum_binding": addendum_binding,
                "successor_user_approval": successor_approval,
                "clock_policy": clock,
                "supervisor_policy": supervisor,
                "runtime_closure": closure,
                "sentiment_source_registry": registry,
                "association_preregistration": association,
                "evaluation_contract": evaluation,
                "successor_qualifications": qualifications,
                "qualification_retirement": retirement,
            }
            projected = project_v311_application_authority_chain_v2(loaded)
            self.assertEqual(
                (
                    "theory_approval",
                    "experiment_contract",
                    "manifest",
                    "authorization_receipt",
                    "authority",
                ),
                tuple(projected),
            )
        self.assertEqual(qualification_run, envelope["qualification_run_id"])
        self.assertEqual(target_run, envelope["target_run_id"])
        self.assertFalse(
            envelope["qualification_v3_authority"][
                "accepted_cycles_count_toward_target"
            ]
        )

        same_target = copy.deepcopy(target_chain)
        same_target["authority"] = qualification_chain["authority"]
        with patch(
            f"{module}.project_v31_application_authority_chain_v2",
            side_effect=project_fake,
        ), patch(
            f"{module}.verify_v311_qualification_run_genesis_v2",
            return_value=genesis_evidence,
        ), patch(
            f"{module}.verify_successor_public_source_qualification_v2",
            return_value=source["source_qualification_v2_digest"],
        ), patch(
            f"{module}.verify_successor_codex_durable_qualification_v3",
            return_value=codex["codex_qualification_v3_digest"],
        ), patch(
            f"{module}.verify_successor_monitor_qualification_v2",
            return_value=monitor["monitor_qualification_v2_digest"],
        ), self.assertRaises(V311SuccessorAuthorityEnvelopeV2Error):
            build_v311_successor_authority_envelope_v2(
                envelope_id="v311-successor-envelope-20260807t000500z",
                created_at="2026-08-07T00:05:00Z",
                legacy_active_chain=legacy_chain,
                legacy_failure_evidence=legacy_evidence,
                qualification_v3_chain=qualification_chain,
                qualification_v3_document_bindings=qualification_bindings,
                qualification_run_root_ref=(
                    f"agent-cluster/experiments/{qualification_run}"
                ),
                qualification_run_genesis=run_genesis,
                qualification_run_genesis_binding=run_genesis_binding,
                target_v4_chain=same_target,
                target_v4_document_bindings=target_bindings,
                theory_addendum_binding=envelope["theory_addendum_binding"],
                successor_user_approval=successor_approval,
                successor_user_approval_binding=successor_approval_binding,
                clock_policy=clock,
                supervisor_policy=supervisor,
                runtime_closure=closure,
                sentiment_source_registry=registry,
                association_preregistration=association,
                evaluation_contract=evaluation,
                auxiliary_document_bindings=auxiliary_bindings,
                successor_qualifications=qualifications,
                successor_qualification_bindings=qualification_document_bindings,
                qualification_retirement=retirement,
                qualification_retirement_binding=retirement_binding,
            )

    def test_projection_rejects_missing_target(self) -> None:
        loaded = self._projection_fixture({})
        incomplete = dict(loaded)
        incomplete.pop("target_v4_chain")
        with self.assertRaises(V311SuccessorAuthorityEnvelopeV2Error):
            project_v311_application_authority_chain_v2(incomplete)

    def test_qualification_and_target_authority_paths_are_distinct_versions(self) -> None:
        self.assertNotEqual(
            V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
            V311_TARGET_ACTIVE_AUTHORITY_PATH,
        )
        self.assertTrue(V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH.endswith(".v3.json"))
        self.assertTrue(V311_TARGET_ACTIVE_AUTHORITY_PATH.endswith(".v4.json"))

    def test_production_paths_and_real_fresh_process_trace_are_not_fixtures(self) -> None:
        qualification = v311_versioned_authority_paths_v2(
            authority_version=QUALIFICATION_V3,
            run_id="v311-qualification-production-test",
        )
        target = v311_versioned_authority_paths_v2(
            authority_version=TARGET_V4,
            run_id="v311-target-production-test",
        )
        self.assertEqual(
            V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
            qualification["active_authority"],
        )
        self.assertEqual(
            V311_TARGET_ACTIVE_AUTHORITY_PATH, target["active_authority"]
        )
        self.assertNotEqual(qualification["root"], target["root"])

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "pkg").mkdir()
            (project / "pkg/__init__.py").write_text("", encoding="utf-8")
            (project / "pkg/root.py").write_text(
                "from . import dependency\n", encoding="utf-8"
            )
            (project / "pkg/dependency.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            sealed = seal_v311_runtime_closure_from_fresh_process_v2(
                project_root=project,
                python_executable=Path("/opt/homebrew/bin/python3.12"),
                run_scope_id="v311-target-production-test",
                trace_id="v311-fresh-process-production-test",
                trace_relative_path="evidence/fresh-trace.json",
                closure_relative_path="evidence/runtime-closure.json",
                production_root_paths=("pkg/root.py",),
            )
            trace = sealed["fresh_process_trace"]
            self.assertTrue(trace["fresh_process_proven"])
            self.assertNotEqual(trace["parent_pid"], trace["worker_pid"])
            self.assertIn("pkg/root.py", trace["observed_project_python_paths"])
            self.assertIn(
                "pkg/dependency.py",
                sealed["runtime_closure"]["frozen_bindings"],
            )

    def test_successor_approval_is_write_once_and_binds_exact_user_statements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "theory/history/RESEARCH_THEORY_v3_1_1_SUCCESSOR.md").write_text(
                "# frozen successor\n", encoding="utf-8"
            )
            first = seal_v311_successor_user_approval_v2(
                project_root=project,
                approval_id="v311-successor-user-approval-test",
                approved_at="2026-08-07T00:00:00Z",
            )
            second = seal_v311_successor_user_approval_v2(
                project_root=project,
                approval_id="v311-successor-user-approval-test",
                approved_at="2026-08-07T00:00:00Z",
            )
            self.assertEqual(first, second)
            self.assertEqual(
                list(REQUIRED_USER_APPROVAL_STATEMENTS),
                first["receipt"]["user_statements"],
            )
            self.assertFalse(first["receipt"]["executable"])


if __name__ == "__main__":
    unittest.main()
