from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v311_successor_authority_envelope_v2 import (
    V311_LEGACY_RUN_ID,
)
from trade_system.theory_paper_v2.domain.governance.v311_fresh_process_trace_v2 import (
    build_v311_fresh_process_trace_receipt_v2,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    CAPABILITY_GATE_MAP,
    CAPABILITY_KEYS,
    QUALIFICATION_RECEIPT_DIGEST_FIELD,
    build_v32_actual_capability_receipt_v1,
    build_v32_fresh_capability_qualification_receipt_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_preflight_gate_subject import (
    PRODUCTION_ROOT_PATHS,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_authority_lifecycle import (
    V32AuthorityLifecycleComposerError,
    finalize_v32_target_authority,
    prepare_v32_qualification_authority,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    v32_authority_lifecycle as authority_lifecycle,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_current_research import (
    V32_CURRENT_RESEARCH_AUTHORITY_PATH,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    v32_secure_write_once_store as secure_store,
)
from trade_system.theory_paper_v2.presentation import (
    v32_qualification_composition as qualification_composition,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_secure_write_once_store import (
    secure_write_once_json,
)
from tests.v32_postcommit_regression_support import (
    write_valid_postcommit_regression_support,
)


TARGET_RUN = "v32-target-btcusdt-20260807t000600z"
QUALIFICATION_RUN = "v32-qualification-btcusdt-20260807t000600z"
RUNTIME_ROOT = f".runtime/v32/qualifications/{QUALIFICATION_RUN}"
THEORY_PATH = "theory/current/V3_2_DYNAMIC_AGGRESSIVE.md"
LOADER_MODULE = (
    "trade_system.theory_paper_v2.infrastructure.authority.v32_current_research"
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def legacy_materials(root: Path) -> tuple[dict, dict]:
    authority = self_digest(
        {
            "schema_id": "theory_paper_v31_current_research_authority",
            "authorized_run_id": V311_LEGACY_RUN_ID,
        },
        "authority_digest",
    )
    path = root / V31_CURRENT_RESEARCH_AUTHORITY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(authority) + b"\n")
    chain = {
        "authority": authority,
        "qualification_receipts": {f"Q{index}": {} for index in range(9)},
        "manifest": {
            "implementation_bindings": {
                f"legacy/path-{index:02d}.py": hashlib.sha256(
                    str(index).encode()
                ).hexdigest()
                for index in range(74)
            }
        },
    }
    failure = {
        "research_checkpoint": {
            "status": "READY_FOR_CYCLE",
            "completed_cycles": 1,
        },
        "monitor_checkpoint": {
            "status": "FAILED_CLOSED",
            "resume_allowed": False,
            "outcome_bindings": [],
        },
        "monitor_failure": {
            "resume_allowed": False,
            "reserved_attempts": 1,
            "resolved_cycles": 0,
        },
        "resolution_attempt": {"attempt_number": 1, "retry_allowed": False},
    }
    return chain, failure


def fresh_trace_receipt(paths: tuple[str, ...]) -> dict:
    modules = tuple(
        sorted(
            f"trace_root_{index}"
            for index, _ in enumerate(paths)
        )
    )
    return build_v311_fresh_process_trace_receipt_v2(
        trace_id="v32-lifecycle-fixture-trace",
        started_at="2026-08-06T23:58:00Z",
        completed_at="2026-08-06T23:58:01Z",
        parent_pid=100,
        worker_pid=101,
        invocation_nonce="fixture-nonce",
        echoed_nonce="fixture-nonce",
        python_executable="/opt/homebrew/bin/python3.12",
        python_version="3.12-fixture",
        production_root_paths=paths,
        imported_root_modules=modules,
        observed_project_python_paths=paths,
        stderr_sha256=hashlib.sha256(b"").hexdigest(),
        stderr_empty=True,
    )


class V32QualificationCompositionClockTests(unittest.TestCase):
    def test_phase_b_retries_only_until_the_real_strict_successor_arrives(self):
        observed = iter(
            [
                "2026-08-11T00:00:01.000001Z",
                "2026-08-11T00:00:01.000001Z",
                "2026-08-11T00:00:01.000002Z",
                "2026-08-11T00:00:01.000002Z",
                "2026-08-11T00:00:01.000002Z",
                "2026-08-11T00:00:01.000002Z",
            ]
        )

        result = qualification_composition._acquire_lifecycle_phase_times_v1(
            lambda: next(observed),
            keys=qualification_composition._PHASE_B_TIME_KEYS,
            strict_successors=frozenset({"target_gate_evaluated_at"}),
            not_before="2026-08-11T00:00:01Z",
        )

        self.assertEqual(
            "2026-08-11T00:00:01.000001Z", result["retired_at"]
        )
        self.assertEqual(
            "2026-08-11T00:00:01.000002Z",
            result["target_gate_evaluated_at"],
        )
        self.assertEqual(
            result["target_gate_evaluated_at"],
            result["target_authority_recorded_at"],
        )

    def test_phase_clock_can_recover_from_a_transient_backward_read(self):
        observed = iter(
            [
                "2026-08-11T00:00:01.000001Z",
                "2026-08-11T00:00:00.999999Z",
                "2026-08-11T00:00:01.000001Z",
            ]
        )

        result = qualification_composition._acquire_lifecycle_phase_times_v1(
            lambda: next(observed),
            keys=("weak_first", "weak_second"),
            strict_successors=frozenset(),
            not_before="2026-08-11T00:00:01Z",
        )

        self.assertEqual(
            "2026-08-11T00:00:01.000001Z", result["weak_second"]
        )

    def test_phase_clock_fails_closed_when_real_time_never_advances(self):
        with patch.object(
            qualification_composition, "_PHASE_TIME_MAX_READS_PER_KEY", 3
        ), self.assertRaisesRegex(
            qualification_composition.V32QualificationCompositionError,
            "V32_QUALIFICATION_PHASE_CLOCK_DID_NOT_ADVANCE",
        ):
            qualification_composition._acquire_lifecycle_phase_times_v1(
                lambda: "2026-08-11T00:00:01Z",
                keys=("strict_edge",),
                strict_successors=frozenset({"strict_edge"}),
                not_before="2026-08-11T00:00:01Z",
            )

    def test_new_phase_a_route_retires_before_clock_replay_or_write(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(
                qualification_composition, "PROJECT_ROOT", root
            ), patch.object(
                qualification_composition,
                "build_v32_system_clock_v1",
            ) as clock_factory, patch.object(
                qualification_composition, "_replayed_phase_a_result"
            ) as replay, self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "V32_LEGACY_NEW_QUALIFICATION_ROUTE_RETIRED",
            ):
                qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                    target_run_id=TARGET_RUN,
                    qualification_run_id=QUALIFICATION_RUN,
                )
            clock_factory.assert_not_called()
            replay.assert_not_called()
            self.assertEqual([], list(root.iterdir()))

    def test_phase_clock_rejects_noncanonical_or_naive_values(self):
        for invalid in (
            "2026-08-11T00:00:01+00:00",
            "2026-08-11T00:00:01",
            "not-a-time",
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "V32_QUALIFICATION_PHASE_CLOCK_INVALID",
            ):
                qualification_composition._acquire_lifecycle_phase_times_v1(
                    lambda: invalid,
                    keys=("weak_edge",),
                    strict_successors=frozenset(),
                    not_before="2026-08-11T00:00:00Z",
                )


class V32AuthorityLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._template_temp = TemporaryDirectory()
        cls.addClassCleanup(cls._template_temp.cleanup)
        cls._template_root = Path(cls._template_temp.name)
        (cls._template_root / ".gitignore").write_text(
            ".runtime/\n"
            "config/theory_paper_v32.current_research_authority.v1.json\n",
            encoding="utf-8",
        )
        theory_path = cls._template_root / THEORY_PATH
        theory_path.parent.mkdir(parents=True, exist_ok=True)
        theory_path.write_text(
            "# V3.2\n\npublic-only local non-executable theory\n",
            encoding="utf-8",
        )
        for relative_ref in PRODUCTION_ROOT_PATHS:
            path = cls._template_root / relative_ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f'"""Committed production path {relative_ref}."""\n',
                encoding="utf-8",
            )
        (
            cls._template_legacy_chain,
            cls._template_legacy_failure,
        ) = legacy_materials(cls._template_root)
        git(cls._template_root, "init", "-b", "codex/v32-lifecycle-test")
        git(
            cls._template_root,
            "config",
            "user.email",
            "v32@example.invalid",
        )
        git(cls._template_root, "config", "user.name", "V32 Test")
        git(cls._template_root, "add", ".")
        git(
            cls._template_root,
            "commit",
            "-m",
            "committed v32 lifecycle input",
        )

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(
            self._template_root,
            self.root,
            dirs_exist_ok=True,
        )
        self.legacy_chain = copy.deepcopy(self._template_legacy_chain)
        self.legacy_failure = copy.deepcopy(self._template_legacy_failure)

    def phase_a(self):
        aggregate = (
            self.root
            / ".runtime/v32/prequalification-regression"
            / QUALIFICATION_RUN
            / "aggregate.json"
        )
        if not aggregate.exists():
            status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                    "--ignored=no",
                ],
                check=True,
                capture_output=True,
            ).stdout
            rows = [row for row in status.split(b"\0") if row]
            allowed = {
                "archive/user-preserved/THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md"
            }
            if all(
                row[:2] == b"??"
                and row[3:].decode("utf-8") in allowed
                for row in rows
            ):
                write_valid_postcommit_regression_support(
                    self.root,
                    target_run_id=TARGET_RUN,
                    qualification_run_id=QUALIFICATION_RUN,
                )
        return prepare_v32_qualification_authority(
            project_root=self.root,
            runtime_root_relative_ref=RUNTIME_ROOT,
            target_run_id=TARGET_RUN,
            qualification_run_id=QUALIFICATION_RUN,
            theory_relative_ref=THEORY_PATH,
            phase_times={
                "workspace_observed_at": "2026-08-06T23:59:00Z",
                "support_frozen_at": "2026-08-07T00:00:00Z",
                "runtime_frozen_at": "2026-08-07T00:01:00Z",
                "approved_at": "2026-08-07T00:02:00Z",
                "manifest_created_at": "2026-08-07T00:03:00Z",
                "qualification_gate_evaluated_at": "2026-08-07T00:04:00Z",
                "qualification_phase_evaluated_at": "2026-08-07T00:04:00Z",
                "qualification_authorization_issued_at": "2026-08-07T00:05:00Z",
                "qualification_authority_recorded_at": "2026-08-07T00:06:00Z",
            },
            fresh_process_trace_receipt=fresh_trace_receipt(
                PRODUCTION_ROOT_PATHS
            ),
            public_network_status="UNKNOWN",
            codex_delivery_status="UNKNOWN",
            automation_status="UNKNOWN",
            tool_names=["git"],
            localization_adapters=[],
        )

    def actual_qualification(self, phase_a: dict) -> tuple[dict, dict]:
        authority = phase_a["qualification_authority"]
        authority_binding = phase_a["qualification_authority_binding"]
        receipt_bindings: dict[str, dict] = {}
        windows = {
            "CURRENT_CODEX": ("2026-08-07T00:07:00Z", "2026-08-07T00:07:15Z"),
            "OUTCOME_MONITOR": ("2026-08-07T00:07:15Z", "2026-08-07T00:07:30Z"),
            "PUBLIC_SOURCE": ("2026-08-07T00:07:30Z", "2026-08-07T00:07:45Z"),
        }
        for capability in CAPABILITY_KEYS:
            evidence = self_digest(
                {
                    "schema_id": f"test_v32_{capability.lower()}_owning_root_v1",
                    "capability": capability,
                    "qualification_run_id": QUALIFICATION_RUN,
                    "qualification_authority_digest": authority[
                        AUTHORITY_DIGEST_FIELD
                    ],
                    "full_replay_verified": True,
                    "replay_network_calls": 0,
                },
                "owning_root_digest",
            )
            slug = capability.lower().replace("_", "-")
            root_ref = f"{RUNTIME_ROOT}/evidence/roots/{slug}.json"
            root_binding = secure_write_once_json(
                self.root,
                root_ref,
                evidence,
                digest_field="owning_root_digest",
            )
            started_at, completed_at = windows[capability]
            receipt = build_v32_actual_capability_receipt_v1(
                capability=capability,
                receipt_id=f"{QUALIFICATION_RUN}:{capability.lower()}:actual",
                qualification_run_id=QUALIFICATION_RUN,
                target_run_id=TARGET_RUN,
                started_at=started_at,
                completed_at=completed_at,
                qualification_authority_binding=authority_binding,
                evidence_root_binding=root_binding,
            )
            receipt_ref = (
                f"{RUNTIME_ROOT}/evidence/seal-bundle/receipts/{slug}.json"
            )
            receipt_bindings[capability] = secure_write_once_json(
                self.root,
                receipt_ref,
                receipt,
                digest_field=next(
                    key for key in receipt if key.endswith("receipt_digest")
                ),
            )
        qualification = build_v32_fresh_capability_qualification_receipt_v1(
            qualification_id=f"{QUALIFICATION_RUN}:actual-capability",
            qualification_run_id=QUALIFICATION_RUN,
            target_run_id=TARGET_RUN,
            started_at="2026-08-07T00:07:00Z",
            completed_at="2026-08-07T00:08:00Z",
            qualification_authority_binding=authority_binding,
            capability_evidence_bindings=receipt_bindings,
        )
        qualification_binding = secure_write_once_json(
            self.root,
            f"{RUNTIME_ROOT}/evidence/seal-bundle/qualification-receipt.json",
            qualification,
            digest_field=QUALIFICATION_RECEIPT_DIGEST_FIELD,
        )
        return qualification, qualification_binding

    def verifiers(self):
        def verifier_for(capability: str):
            def verify(**kwargs):
                receipt = kwargs["capability_receipt"]
                binding = kwargs["evidence_root_binding"]
                authority = kwargs["qualification_authority"]
                document = load_json_strict(kwargs["project_root"] / binding["path"])
                payload = (kwargs["project_root"] / binding["path"]).read_bytes()
                if (
                    receipt.get("capability") != capability
                    or document.get("capability") != capability
                    or document.get("qualification_authority_digest")
                    != authority[AUTHORITY_DIGEST_FIELD]
                    or hashlib.sha256(payload).hexdigest()
                    != binding["physical_sha256"]
                    or document.get("owning_root_digest")
                    != binding["semantic_digest"]
                ):
                    raise ValueError("owning replay invalid")
                return {
                    "capability": capability,
                    "evidence_root_semantic_digest": binding["semantic_digest"],
                    "full_replay_verified": True,
                    "replay_network_calls": 0,
                }

            return verify

        return {capability: verifier_for(capability) for capability in CAPABILITY_KEYS}

    def phase_b_times(self) -> dict[str, str]:
        return {
            "retired_at": "2026-08-07T00:09:00Z",
            "target_gate_evaluated_at": "2026-08-07T00:10:00Z",
            "target_phase_evaluated_at": "2026-08-07T00:10:00Z",
            "target_authorization_issued_at": "2026-08-07T00:11:00Z",
            "target_authority_recorded_at": "2026-08-07T00:12:00Z",
        }

    def phase_b(
        self,
        phase_a: dict,
        qualification_binding: dict,
        *,
        phase_times: dict[str, str] | None = None,
    ):
        return finalize_v32_target_authority(
            project_root=self.root,
            runtime_root_relative_ref=RUNTIME_ROOT,
            expected_target_run_id=TARGET_RUN,
            expected_qualification_run_id=QUALIFICATION_RUN,
            qualification_authority_binding=phase_a[
                "qualification_authority_binding"
            ],
            qualification_receipt_binding=qualification_binding,
            phase_times=phase_times or self.phase_b_times(),
            capability_verifiers=self.verifiers(),
        )

    def test_two_phase_composer_seals_exact_chain_and_full_loader_projection(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            first = self.phase_a()
            self.assertEqual(
                "2.0.0", first["runtime_manifest"]["schema_version"]
            )
            fresh_trace_binding = first["runtime_manifest"][
                "fresh_process_trace_binding"
            ]
            self.assertEqual(
                f"{RUNTIME_ROOT}/support/fresh-process-trace.json",
                fresh_trace_binding["path"],
            )
            self.assertTrue((self.root / fresh_trace_binding["path"]).is_file())
            replayed = self.phase_a()
            self.assertEqual(
                first["qualification_authority_binding"],
                replayed["qualification_authority_binding"],
            )
            _, qualification_binding = self.actual_qualification(first)
            target = self.phase_b(first, qualification_binding)
        self.assertTrue(target["full_loader_verified"])
        for capability_key, gate_id in CAPABILITY_GATE_MAP.items():
            self.assertEqual(
                target["qualification_replay"][
                    "actual_capability_receipt_bindings"
                ][capability_key],
                target["target_gates"][gate_id]["subject_bindings"][0],
            )
        self.assertTrue((self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).is_file())
        self.assertEqual(
            TARGET_RUN,
            target["application_projection"]["authority"]["run_id"],
        )
        self.assertEqual("", git(self.root, "status", "--porcelain"))

    def test_phase_a_entry_replays_an_existing_runtime_without_new_clock(self):
        (self.root / RUNTIME_ROOT).mkdir(parents=True)
        expected = {"phase_a_recovery_status": "EXISTING_FULL_REPLAY"}
        with patch.object(
            qualification_composition, "PROJECT_ROOT", self.root
        ), patch.object(
            qualification_composition,
            "_replayed_phase_a_result",
            return_value=expected,
        ) as replay, patch.object(
            qualification_composition, "build_v32_system_clock_v1"
        ) as clock_factory:
            recovered = qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                target_run_id=TARGET_RUN,
                qualification_run_id=QUALIFICATION_RUN,
            )
        self.assertEqual(expected, recovered)
        replay.assert_called_once_with(
            target_run_id=TARGET_RUN,
            qualification_run_id=QUALIFICATION_RUN,
        )
        clock_factory.assert_not_called()

    def test_phase_b_recovers_after_retirement_before_target_tail(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            real_persist = authority_lifecycle._persist_batch
            calls = 0

            def stop_after_prefix(*args, **kwargs):
                nonlocal calls
                calls += 1
                result = real_persist(*args, **kwargs)
                if calls == 1:
                    raise RuntimeError("simulated process interruption")
                return result

            with patch.object(
                authority_lifecycle,
                "_persist_batch",
                side_effect=stop_after_prefix,
            ), self.assertRaisesRegex(RuntimeError, "process interruption"):
                self.phase_b(phase_a, qualification_binding)

            intent_path = (
                self.root / RUNTIME_ROOT / "target/finalization-intent.json"
            )
            retirement_path = (
                self.root / RUNTIME_ROOT / "qualification/retirement.json"
            )
            self.assertTrue(intent_path.is_file())
            self.assertTrue(retirement_path.is_file())
            intent = load_json_strict(intent_path)
            self.assertEqual(
                {
                    "schema_id",
                    "schema_version",
                    "target_run_id",
                    "qualification_run_id",
                    "qualification_authority_binding",
                    "qualification_receipt_binding",
                    "phase_times",
                    "qualification_retirement_binding",
                    "recovery_policy",
                    "network_calls",
                    "authority_boundary",
                    "target_finalization_intent_digest",
                },
                set(intent),
            )
            self.assertNotIn("target_tail_bindings", intent)
            self.assertFalse(
                (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists()
            )

            recovered_times = authority_lifecycle.load_v32_target_finalization_phase_times_if_started(
                project_root=self.root,
                runtime_root_relative_ref=RUNTIME_ROOT,
                expected_target_run_id=TARGET_RUN,
                expected_qualification_run_id=QUALIFICATION_RUN,
                qualification_authority_binding=phase_a[
                    "qualification_authority_binding"
                ],
                qualification_receipt_binding=qualification_binding,
            )
            self.assertEqual(self.phase_b_times(), recovered_times)
            recovered = self.phase_b(
                phase_a,
                qualification_binding,
                phase_times=recovered_times,
            )
        self.assertEqual("TARGET_AUTHORITY_READY", recovered["status"])
        self.assertEqual(0, recovered["network_calls"])
        self.assertTrue(recovered["full_loader_verified"])

    def test_phase_b_recovers_when_intent_exists_before_retirement(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            failed = False

            def stop_at_retirement(root, path, document, *, digest_field):
                nonlocal failed
                if not failed and path.endswith(
                    "/qualification/retirement.json"
                ):
                    failed = True
                    raise OSError("simulated retirement write interruption")
                return secure_write_once_json(
                    root,
                    path,
                    document,
                    digest_field=digest_field,
                )

            with patch.object(
                authority_lifecycle,
                "secure_write_once_json",
                side_effect=stop_at_retirement,
            ), self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "WRITE_ONCE_FAILED",
            ):
                self.phase_b(phase_a, qualification_binding)

            self.assertTrue(
                (
                    self.root
                    / RUNTIME_ROOT
                    / "target/finalization-intent.json"
                ).is_file()
            )
            self.assertFalse(
                (
                    self.root
                    / RUNTIME_ROOT
                    / "qualification/retirement.json"
                ).exists()
            )
            self.assertFalse(
                (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists()
            )
            recovered = self.phase_b(phase_a, qualification_binding)
        self.assertEqual("TARGET_AUTHORITY_READY", recovered["status"])
        self.assertTrue(recovered["full_loader_verified"])

    def test_phase_b_recovers_after_partial_target_tail_write(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            failed = False

            def stop_at_phase(root, path, document, *, digest_field):
                nonlocal failed
                if not failed and path.endswith("/target/phase-a.json"):
                    failed = True
                    raise OSError("simulated tail write interruption")
                return secure_write_once_json(
                    root,
                    path,
                    document,
                    digest_field=digest_field,
                )

            with patch.object(
                authority_lifecycle,
                "secure_write_once_json",
                side_effect=stop_at_phase,
            ), self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "WRITE_ONCE_FAILED",
            ):
                self.phase_b(phase_a, qualification_binding)

            target_root = self.root / RUNTIME_ROOT / "target"
            self.assertTrue(
                (target_root / "finalization-intent.json").is_file()
            )
            self.assertTrue(
                (self.root / RUNTIME_ROOT / "qualification/retirement.json").is_file()
            )
            self.assertTrue(any((target_root / "gates").glob("*.json")))
            self.assertFalse((target_root / "phase-a.json").exists())
            self.assertFalse(
                (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists()
            )

            recovered = self.phase_b(phase_a, qualification_binding)
        self.assertEqual("TARGET_AUTHORITY_READY", recovered["status"])
        self.assertTrue(recovered["full_loader_verified"])

    def test_phase_b_recovers_when_pointer_was_written_before_return(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            real_persist = authority_lifecycle._persist_batch
            calls = 0

            def stop_after_pointer(*args, **kwargs):
                nonlocal calls
                calls += 1
                result = real_persist(*args, **kwargs)
                if calls == 2:
                    raise RuntimeError("simulated interruption after pointer")
                return result

            with patch.object(
                authority_lifecycle,
                "_persist_batch",
                side_effect=stop_after_pointer,
            ), self.assertRaisesRegex(RuntimeError, "after pointer"):
                self.phase_b(phase_a, qualification_binding)

            self.assertTrue(
                (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).is_file()
            )
            recovered = self.phase_b(phase_a, qualification_binding)
        self.assertEqual("TARGET_AUTHORITY_READY", recovered["status"])
        self.assertTrue(recovered["full_loader_verified"])

    def test_phase_b_reentry_rejects_time_plan_drift_after_retirement(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            real_persist = authority_lifecycle._persist_batch

            def stop_after_prefix(*args, **kwargs):
                result = real_persist(*args, **kwargs)
                raise RuntimeError("simulated process interruption")

            with patch.object(
                authority_lifecycle,
                "_persist_batch",
                side_effect=stop_after_prefix,
            ), self.assertRaises(RuntimeError):
                self.phase_b(phase_a, qualification_binding)

            drifted_times = self.phase_b_times()
            drifted_times["target_authority_recorded_at"] = (
                "2026-08-07T00:13:00Z"
            )
            with self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "FINALIZATION_INTENT_DRIFT",
            ):
                self.phase_b(
                    phase_a,
                    qualification_binding,
                    phase_times=drifted_times,
                )
            drifted_binding = dict(qualification_binding)
            drifted_binding["semantic_digest"] = "f" * 64
            with self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "FINALIZATION_INTENT_DRIFT",
            ):
                authority_lifecycle.load_v32_target_finalization_phase_times_if_started(
                    project_root=self.root,
                    runtime_root_relative_ref=RUNTIME_ROOT,
                    expected_target_run_id=TARGET_RUN,
                    expected_qualification_run_id=QUALIFICATION_RUN,
                    qualification_authority_binding=phase_a[
                        "qualification_authority_binding"
                    ],
                    qualification_receipt_binding=drifted_binding,
                )
        self.assertFalse((self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists())

    def test_phase_b_retirement_without_intent_fails_before_target_tail(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            real_persist = authority_lifecycle._persist_batch

            def stop_after_prefix(*args, **kwargs):
                result = real_persist(*args, **kwargs)
                raise RuntimeError("simulated process interruption")

            with patch.object(
                authority_lifecycle,
                "_persist_batch",
                side_effect=stop_after_prefix,
            ), self.assertRaises(RuntimeError):
                self.phase_b(phase_a, qualification_binding)

            target_root = self.root / RUNTIME_ROOT / "target"
            (target_root / "finalization-intent.json").unlink()
            with self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "FINALIZATION_INTENT_MISSING",
            ):
                authority_lifecycle.load_v32_target_finalization_phase_times_if_started(
                    project_root=self.root,
                    runtime_root_relative_ref=RUNTIME_ROOT,
                    expected_target_run_id=TARGET_RUN,
                    expected_qualification_run_id=QUALIFICATION_RUN,
                    qualification_authority_binding=phase_a[
                        "qualification_authority_binding"
                    ],
                    qualification_receipt_binding=qualification_binding,
                )
            with self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "FINALIZATION_INTENT_MISSING",
            ):
                self.phase_b(phase_a, qualification_binding)

        self.assertFalse((target_root / "gates").exists())
        self.assertFalse((target_root / "phase-a.json").exists())
        self.assertFalse((target_root / "authorization.json").exists())
        self.assertFalse((self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists())

    def test_phase_b_completed_reentry_returns_same_sealed_authority(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            first = self.phase_b(phase_a, qualification_binding)
            second = self.phase_b(phase_a, qualification_binding)
        self.assertEqual(
            first["target_authority"], second["target_authority"]
        )
        self.assertEqual(
            first["current_pointer_binding"],
            second["current_pointer_binding"],
        )
        self.assertEqual(
            first["target_finalization_intent"],
            second["target_finalization_intent"],
        )
        self.assertEqual(0, second["network_calls"])

    def test_target_phase_fails_closed_before_pointer_without_actual_receipt(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            with self.assertRaises(ValueError):
                self.phase_b(
                    phase_a,
                    {
                        "path": f"{RUNTIME_ROOT}/actual/missing.json",
                        "schema_id": "missing",
                        "digest_field": "missing_digest",
                        "semantic_digest": "0" * 64,
                        "physical_sha256": "0" * 64,
                    },
                )
        self.assertFalse((self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists())

    def test_phase_a_rejects_dirty_workspace_before_any_runtime_write(self):
        (self.root / "dirty.txt").write_text("dirty", encoding="utf-8")
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ), self.assertRaisesRegex(
            V32AuthorityLifecycleComposerError, "WORKSPACE_NOT_CLEAN"
        ):
            self.phase_a()
        self.assertFalse((self.root / RUNTIME_ROOT).exists())

    def test_phase_a_rejects_symlinked_per_id_root_without_old_tree_write(self):
        old_root = self.root / ".runtime/v32/qualification"
        marker = old_root / "controller/permanent-failure.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b'{"status":"FAILED_CLOSED"}\n')
        before = {
            path.relative_to(old_root).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        }
        injected = self.root / RUNTIME_ROOT
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.symlink_to(old_root, target_is_directory=True)
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ), self.assertRaisesRegex(
            V32AuthorityLifecycleComposerError, "SYMLINK_FORBIDDEN"
        ):
            self.phase_a()
        after = {
            path.relative_to(old_root).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_dirfd_publication_cannot_be_redirected_by_parent_swap(self):
        old_root = self.root / ".runtime/v32/qualification"
        old_file = old_root / "permanent/state.bin"
        old_file.parent.mkdir(parents=True, exist_ok=True)
        old_file.write_bytes(b"immutable-old-tree")
        old_before = {
            path.relative_to(old_root).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        }
        parent = self.root / "race/new-parent"
        parent.mkdir(parents=True)
        parked = self.root / "race/anchored-parent"
        document = self_digest(
            {"schema_id": "v32_dirfd_race_fixture_v1", "value": "new"},
            "fixture_digest",
        )
        real_link = secure_store.os.link
        swapped = False

        def swap_then_link(*args, **kwargs):
            nonlocal swapped
            if not swapped:
                swapped = True
                parent.rename(parked)
                parent.symlink_to(old_root, target_is_directory=True)
            return real_link(*args, **kwargs)

        with patch.object(
            secure_store.os, "link", side_effect=swap_then_link
        ), self.assertRaisesRegex(ValueError, "PARENT_INVALID"):
            secure_write_once_json(
                self.root,
                "race/new-parent/document.json",
                document,
                digest_field="fixture_digest",
            )
        self.assertTrue((parked / "document.json").is_file())
        self.assertFalse((old_root / "document.json").exists())
        old_after = {
            path.relative_to(old_root).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(old_before, old_after)

    def test_secure_write_once_rejects_short_write_and_rechecks_directory_durability(self):
        document = self_digest(
            {"schema_id": "v32_secure_durability_fixture_v1", "value": "fixed"},
            "fixture_digest",
        )
        relative_ref = "durability/nested/document.json"
        target = self.root / relative_ref
        real_fdopen = secure_store.os.fdopen

        class ShortWriteHandle:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def write(self, payload):
                return self.handle.write(payload[: max(1, len(payload) // 2)])

            def flush(self):
                self.handle.flush()

            def fileno(self):
                return self.handle.fileno()

        with patch.object(
            secure_store.os,
            "fdopen",
            side_effect=lambda *args, **kwargs: ShortWriteHandle(
                real_fdopen(*args, **kwargs)
            ),
        ), self.assertRaisesRegex(ValueError, "PUBLICATION_FAILED"):
            secure_write_once_json(
                self.root,
                relative_ref,
                document,
                digest_field="fixture_digest",
            )
        self.assertFalse(target.exists())
        self.assertEqual([], list(target.parent.glob(".*.tmp")))

        cleanup_ref = "durability/nested/cleanup-failure.json"
        cleanup_target = self.root / cleanup_ref
        with patch.object(
            secure_store,
            "_unlink_at_missing_ok",
            side_effect=OSError("injected temp cleanup failure"),
        ), self.assertRaisesRegex(
            ValueError, "V32_SECURE_STORE_PUBLICATION_FAILED"
        ) as captured:
            secure_write_once_json(
                self.root,
                cleanup_ref,
                document,
                digest_field="fixture_digest",
            )
        self.assertTrue(cleanup_target.is_file())
        self.assertIsInstance(captured.exception.__cause__, OSError)
        self.assertIn(
            "injected temp cleanup failure",
            str(captured.exception.__cause__),
        )

        secure_write_once_json(
            self.root,
            relative_ref,
            document,
            digest_field="fixture_digest",
        )
        with patch.object(
            secure_store.os,
            "fsync",
            side_effect=OSError("injected identical directory fsync failure"),
        ), self.assertRaisesRegex(ValueError, "PUBLICATION_FAILED"):
            secure_write_once_json(
                self.root,
                relative_ref,
                document,
                digest_field="fixture_digest",
            )
        self.assertEqual(
            target.read_bytes(),
            canonical_bytes(document) + b"\n",
        )
        secure_write_once_json(
            self.root,
            relative_ref,
            document,
            digest_field="fixture_digest",
        )

    def test_secure_exclusive_lock_rejects_post_flock_inode_swap(self):
        relative_ref = "locks/qualification.lock"
        lock_path = self.root / relative_ref
        moved = self.root / "locks/qualification-original.lock"
        real_flock = secure_store.fcntl.flock
        swapped = False

        def flock_then_swap(descriptor, operation):
            nonlocal swapped
            real_flock(descriptor, operation)
            if operation == secure_store.fcntl.LOCK_EX and not swapped:
                swapped = True
                lock_path.rename(moved)
                lock_path.write_bytes(b"replacement")

        with patch.object(
            secure_store.fcntl,
            "flock",
            side_effect=flock_then_swap,
        ), self.assertRaisesRegex(ValueError, "LOCK_IDENTITY_CHANGED"):
            with secure_store.secure_exclusive_lock_file(
                self.root, relative_ref
            ):
                self.fail("replaced secure lock must not guard the critical section")

    def test_secure_bundle_fsyncs_each_new_nested_directory_entry(self):
        stage = self.root / "bundle-stage"
        stage.mkdir()
        base_fd = os.open(stage, os.O_RDONLY)
        fsynced_inodes: list[int] = []
        real_fsync = secure_store.os.fsync

        def record_fsync(descriptor: int) -> None:
            fsynced_inodes.append(os.fstat(descriptor).st_ino)
            real_fsync(descriptor)

        try:
            with patch.object(
                secure_store.os,
                "fsync",
                side_effect=record_fsync,
            ):
                nested_fd = secure_store._ensure_relative_directory(
                    base_fd,
                    ("qualification", "gates"),
                )
                os.close(nested_fd)
            self.assertEqual(
                [
                    stage.stat().st_ino,
                    (stage / "qualification").stat().st_ino,
                ],
                fsynced_inodes,
            )
        finally:
            os.close(base_fd)

    def _secure_bundle_recovery_fixture(
        self, bundle_ref: str
    ) -> list[dict]:
        first = self_digest(
            {
                "schema_id": "v32_secure_bundle_recovery_first_v1",
                "value": "first",
            },
            "fixture_digest",
        )
        second = self_digest(
            {
                "schema_id": "v32_secure_bundle_recovery_second_v1",
                "value": "second",
            },
            "fixture_digest",
        )
        return [
            {
                "relative_ref": f"{bundle_ref}/first.json",
                "document": first,
                "schema_id": first["schema_id"],
                "digest_field": "fixture_digest",
            },
            {
                "relative_ref": f"{bundle_ref}/nested/second.json",
                "document": second,
                "schema_id": second["schema_id"],
                "digest_field": "fixture_digest",
            },
        ]

    def test_secure_bundle_adopts_complete_stage_after_pre_rename_crash(self):
        bundle_ref = "stage-recovery/complete-seal"
        documents = self._secure_bundle_recovery_fixture(bundle_ref)
        real_activate = secure_store.rename_directory_noreplace_at

        def crash_before_publish(**kwargs):
            if kwargs["source_name"].startswith(".complete-seal-stage-"):
                raise KeyboardInterrupt("simulated process loss before rename")
            return real_activate(**kwargs)

        with patch.object(
            secure_store,
            "rename_directory_noreplace_at",
            side_effect=crash_before_publish,
        ), self.assertRaises(KeyboardInterrupt):
            secure_store.secure_publish_json_directory_bundle(
                self.root,
                bundle_relative_ref=bundle_ref,
                documents=documents,
            )
        parent = self.root / "stage-recovery"
        stages = list(parent.glob(".complete-seal-stage-*"))
        self.assertEqual(1, len(stages))
        staged_identity = (stages[0].stat().st_dev, stages[0].stat().st_ino)

        with patch.object(
            secure_store,
            "_write_new_payload_at",
            side_effect=AssertionError(
                "complete recovery must not rematerialize the sealed bundle"
            ),
        ):
            bindings = secure_store.secure_publish_json_directory_bundle(
                self.root,
                bundle_relative_ref=bundle_ref,
                documents=documents,
            )
        final = self.root / bundle_ref
        self.assertEqual(
            staged_identity,
            (final.stat().st_dev, final.stat().st_ino),
        )
        self.assertEqual([], list(parent.glob(".complete-seal-stage-*")))
        self.assertEqual(
            {item["relative_ref"] for item in documents}, set(bindings)
        )

    def test_secure_bundle_rebuilds_partial_or_different_single_stage(self):
        for kind in ("partial", "different"):
            with self.subTest(kind=kind):
                bundle_ref = f"stage-recovery/{kind}-seal"
                documents = self._secure_bundle_recovery_fixture(bundle_ref)
                real_write = secure_store._write_new_payload_at
                real_activate = secure_store.rename_directory_noreplace_at
                writes = 0

                def leave_stage(parent_fd, leaf, payload):
                    nonlocal writes
                    writes += 1
                    if kind == "partial" and writes == 2:
                        raise KeyboardInterrupt("simulated partial stage")
                    return real_write(parent_fd, leaf, payload)

                def crash_before_publish(**kwargs):
                    if kwargs["source_name"].startswith(f".{kind}-seal-stage-"):
                        raise KeyboardInterrupt("simulated complete stage")
                    return real_activate(**kwargs)

                with patch.object(
                    secure_store,
                    "_write_new_payload_at",
                    side_effect=leave_stage,
                ), patch.object(
                    secure_store,
                    "rename_directory_noreplace_at",
                    side_effect=crash_before_publish,
                ), self.assertRaises(KeyboardInterrupt):
                    secure_store.secure_publish_json_directory_bundle(
                        self.root,
                        bundle_relative_ref=bundle_ref,
                        documents=documents,
                    )

                parent = self.root / "stage-recovery"
                stage = next(parent.glob(f".{kind}-seal-stage-*"))
                stale_identity = (stage.stat().st_dev, stage.stat().st_ino)
                if kind == "different":
                    (stage / "first.json").write_bytes(b"{}\n")

                secure_store.secure_publish_json_directory_bundle(
                    self.root,
                    bundle_relative_ref=bundle_ref,
                    documents=documents,
                )
                final = self.root / bundle_ref
                self.assertNotEqual(
                    stale_identity,
                    (final.stat().st_dev, final.stat().st_ino),
                )
                self.assertEqual([], list(parent.glob(f".{kind}-seal-stage-*")))
                for item in documents:
                    self.assertEqual(
                        canonical_bytes(item["document"]) + b"\n",
                        (self.root / item["relative_ref"]).read_bytes(),
                    )

    def test_secure_bundle_does_not_replace_raced_empty_final(self):
        bundle_ref = "stage-recovery/raced-empty-final"
        documents = self._secure_bundle_recovery_fixture(bundle_ref)
        real_activate = secure_store.rename_directory_noreplace_at

        def install_empty_final_then_activate(**kwargs):
            os.mkdir(
                kwargs["destination_name"],
                dir_fd=kwargs["destination_parent_fd"],
            )
            real_activate(**kwargs)

        with patch.object(
            secure_store,
            "rename_directory_noreplace_at",
            side_effect=install_empty_final_then_activate,
        ), self.assertRaisesRegex(ValueError, "BUNDLE_CONFLICT"):
            secure_store.secure_publish_json_directory_bundle(
                self.root,
                bundle_relative_ref=bundle_ref,
                documents=documents,
            )

        final = self.root / bundle_ref
        self.assertTrue(final.is_dir())
        self.assertEqual([], list(final.iterdir()))
        self.assertEqual(
            [], list(final.parent.glob(".raced-empty-final-stage-*"))
        )

    def test_secure_bundle_stage_ambiguity_and_unsafe_objects_fail_closed(self):
        cases = ("multiple", "non-directory", "foreign-name", "unsafe-child")
        for kind in cases:
            with self.subTest(kind=kind):
                bundle_ref = f"unsafe-stage/{kind}/seal"
                documents = self._secure_bundle_recovery_fixture(bundle_ref)
                parent = (self.root / bundle_ref).parent
                parent.mkdir(parents=True)
                prefix = ".seal-stage-"
                first = parent / f"{prefix}{'1' * 32}"
                if kind == "multiple":
                    first.mkdir()
                    (parent / f"{prefix}{'2' * 32}").mkdir()
                    expected_error = "STAGE_AMBIGUOUS"
                elif kind == "non-directory":
                    first.write_bytes(b"not a directory")
                    expected_error = "STAGE_UNSAFE"
                elif kind == "foreign-name":
                    (parent / f"{prefix}foreign").mkdir()
                    expected_error = "STAGE_UNSAFE"
                else:
                    first.mkdir()
                    (first / "unsafe-link").symlink_to(self.root)
                    expected_error = "BUNDLE_INVALID"
                (parent / ".seal.v32-bundle-publish.lock").touch()
                before = sorted(path.name for path in parent.iterdir())
                with self.assertRaisesRegex(ValueError, expected_error):
                    secure_store.secure_publish_json_directory_bundle(
                        self.root,
                        bundle_relative_ref=bundle_ref,
                        documents=documents,
                    )
                self.assertFalse((self.root / bundle_ref).exists())
                self.assertEqual(
                    before,
                    sorted(path.name for path in parent.iterdir()),
                )

    def test_phase_a_binds_the_one_preserved_untracked_user_artifact(self):
        relative_ref = "archive/user-preserved/THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md"
        artifact = self.root / relative_ref
        artifact.write_text("user-owned duplicate\n", encoding="utf-8")
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
        receipt = phase_a["support_documents"][
            "workspace_freeze_receipt_digest"
        ]
        self.assertEqual(
            [
                {
                    "relative_ref": relative_ref,
                    "physical_sha256": hashlib.sha256(
                        artifact.read_bytes()
                    ).hexdigest(),
                }
            ],
            receipt["allowed_untracked_user_artifacts"],
        )
        self.assertEqual(
            f"?? {relative_ref}",
            git(
                self.root,
                "-c",
                "core.quotePath=false",
                "status",
                "--porcelain",
            ),
        )

    def test_qualification_wake_replays_postcommit_before_any_runtime_port(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            self.phase_a()
        aggregate = load_json_strict(
            self.root
            / RUNTIME_ROOT
            / "support/postcommit-regression/aggregate.json"
        )
        receipt = self.root / next(
            iter(aggregate["execution_receipt_bindings"].values())
        )["path"]
        receipt.write_bytes(receipt.read_bytes() + b" ")
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in (self.root / RUNTIME_ROOT).rglob("*")
            if path.is_file()
        }
        with patch.object(
            qualification_composition, "PROJECT_ROOT", self.root
        ), patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ), patch.object(
            qualification_composition, "V32OkxPublicBundleTransport"
        ) as transport:
            with self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "POSTCOMMIT_REPLAY_FAILED",
            ):
                qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=TARGET_RUN,
                    qualification_run_id=QUALIFICATION_RUN,
                )
        self.assertEqual(0, transport.call_count)
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in (self.root / RUNTIME_ROOT).rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_target_finalize_replays_postcommit_before_any_retirement_or_target_write(self):
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.legacy_chain,
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.legacy_failure,
        ):
            phase_a = self.phase_a()
            _, qualification_binding = self.actual_qualification(phase_a)
            aggregate = load_json_strict(
                self.root
                / RUNTIME_ROOT
                / "support/postcommit-regression/aggregate.json"
            )
            receipt = self.root / next(
                iter(aggregate["execution_receipt_bindings"].values())
            )["path"]
            receipt.write_bytes(receipt.read_bytes() + b" ")
            before = {
                path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in (self.root / RUNTIME_ROOT).rglob("*")
                if path.is_file()
            }
            with self.assertRaisesRegex(
                V32AuthorityLifecycleComposerError,
                "BINDING_INVALID|POSTCOMMIT_REGRESSION_REPLAY_INVALID",
            ):
                self.phase_b(phase_a, qualification_binding)
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in (self.root / RUNTIME_ROOT).rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertFalse(
            (self.root / RUNTIME_ROOT / "target/finalization-intent.json").exists()
        )
        self.assertFalse(
            (self.root / RUNTIME_ROOT / "qualification/retirement.json").exists()
        )
        self.assertFalse((self.root / RUNTIME_ROOT / "target/gates").exists())
        self.assertFalse((self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).exists())

if __name__ == "__main__":
    unittest.main()
