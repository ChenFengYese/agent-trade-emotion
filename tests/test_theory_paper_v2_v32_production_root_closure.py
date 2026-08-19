from __future__ import annotations

import ast
from pathlib import Path
import unittest

from trade_system.theory_paper_v2.domain.governance.v32_preflight_gate_subject import (
    GATE_IMPLEMENTATION_PATHS,
    PRODUCTION_ROOT_PATHS,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_runtime_closure_v2 import (
    build_v31_runtime_closure_bindings_v2,
    collect_v31_static_runtime_closure_v2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_V32_PRODUCTION_ENTRYPOINTS = frozenset(
    {
        "trade_system/theory_paper_v2/infrastructure/authority/v32_current_research.py",
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification_controller.py",
        "trade_system/theory_paper_v2/presentation/v32_qualification_composition.py",
        "trade_system/theory_paper_v2/presentation/v32_target_run_composition.py",
        "trade_system/theory_paper_v2/presentation/v32_target_wake_composition.py",
    }
)

REQUIRED_REACHABLE_V32_PATHS = frozenset(
    {
        "trade_system/theory_paper_v2/application/v32_action_plan_continuity.py",
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification.py",
        "trade_system/theory_paper_v2/application/v32_dynamic_state_continuity.py",
        "trade_system/theory_paper_v2/application/v32_prospective_runtime.py",
        "trade_system/theory_paper_v2/domain/governance/v311_fresh_process_trace_v2.py",
        "trade_system/theory_paper_v2/domain/v32_current_root_agent_mailbox.py",
        "trade_system/theory_paper_v2/domain/v32_dynamic_research.py",
        "trade_system/theory_paper_v2/domain/v32_outcome_window_expiry.py",
        "trade_system/theory_paper_v2/domain/v32_qualification_monitor_probe.py",
        "trade_system/theory_paper_v2/domain/v32_timeframe_cache.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_actual_capability_attempt_ports.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_actual_capability_replay.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v311_fresh_process_trace_v2.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_materializer.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_monitor_probe_store.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_runtime_namespace.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_secure_write_once_store.py",
        "trade_system/theory_paper_v2/domain/governance/v32_qualification_identity.py",
        "trade_system/theory_paper_v2/infrastructure/v32_analysis_material_adapter.py",
        "trade_system/theory_paper_v2/infrastructure/v32_authorized_revision_store.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
        "trade_system/theory_paper_v2/infrastructure/v32_incremental_market_graph.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_audit_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_public_market_graph_projection.py",
        "trade_system/theory_paper_v2/infrastructure/v32_public_https_route.py",
        "trade_system/theory_paper_v2/infrastructure/v32_recovery_supervision_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_read_only_status.py",
        "trade_system/theory_paper_v2/infrastructure/v32_terminal_seal_store.py",
    }
)


class V32ProductionRootClosureTests(unittest.TestCase):
    def test_v32_runtime_has_no_path_based_lock_or_temp_replace_regression(self):
        forbidden = (
            '.open("a+b")',
            ".open('a+b')",
            "tempfile.mkstemp(",
            "tempfile.mkdtemp(",
            "secure_open_lock_file(",
        )
        findings: list[tuple[str, str]] = []
        production_root = PROJECT_ROOT / "trade_system" / "theory_paper_v2"
        for path in production_root.rglob("*v32*.py"):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in source:
                    findings.append((relative, marker))
        self.assertEqual([], findings)

    def test_raw_dynamic_artifact_mutator_requires_one_lane_capability(self):
        """The Store does not expose an ordinary document write entry point."""

        claim = "_claim_local_analysis_lane_artifact_writer"
        persist = "persist_verified_artifact"
        gated_store_method = "_persist_artifact_with_lane_capability"
        locked_store_method = "_persist_artifact_locked"
        construction_marker = "_formally_constructing_local_v32_analysis_lane"
        construction_verifier = (
            "_is_formally_constructing_local_v32_analysis_lane"
        )
        writer_type = "_LocalV32AnalysisLaneArtifactWriter"
        registry_names = {
            "_FORMAL_LANE_CONSTRUCTION_GUARD",
            "_FORMAL_LANE_CONSTRUCTION_REGISTRY",
        }
        production_root = PROJECT_ROOT / "trade_system" / "theory_paper_v2"
        references = {
            claim: [],
            persist: [],
            gated_store_method: [],
            locked_store_method: [],
        }
        sensitive_names = {
            claim,
            persist,
            gated_store_method,
            locked_store_method,
            construction_marker,
            construction_verifier,
            writer_type,
            *registry_names,
        }
        name_reference_modules = {name: set() for name in sensitive_names}
        reflective_names: list[tuple[str, str]] = []
        forged_lane_allocations: list[str] = []
        for path in production_root.rglob("*.py"):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in references:
                    references[node.attr].append(relative)
                if isinstance(node, ast.Name) and node.id in sensitive_names:
                    name_reference_modules[node.id].add(relative)
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name in sensitive_names:
                            name_reference_modules[alias.name].add(relative)
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in sensitive_names
                ):
                    reflective_names.append((relative, node.value))
                if (
                    isinstance(node, ast.Call)
                    and (
                        (
                            isinstance(node.func, ast.Name)
                            and node.func.id in {"getattr", "vars"}
                        )
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr
                            in {"getattr", "__getattribute__", "attrgetter"}
                        )
                    )
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in references
                ):
                    reflective_names.append((relative, node.args[1].value))
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__new__"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "LocalV32AnalysisLane"
                ):
                    forged_lane_allocations.append(relative)
        self.assertEqual(
            references[claim],
            [
                "trade_system/theory_paper_v2/infrastructure/"
                "v32_local_analysis_lane.py"
            ],
        )
        self.assertEqual(
            references[persist],
            [
                "trade_system/theory_paper_v2/infrastructure/"
                "v32_local_analysis_lane.py"
            ],
        )
        self.assertEqual(
            references[gated_store_method],
            [
                "trade_system/theory_paper_v2/infrastructure/"
                "v32_dynamic_store.py"
            ],
        )
        self.assertEqual(
            set(references[locked_store_method]),
            {
                "trade_system/theory_paper_v2/infrastructure/"
                "v32_dynamic_store.py"
            },
        )
        self.assertEqual([], reflective_names)
        self.assertEqual([], forged_lane_allocations)
        lane_module = (
            "trade_system/theory_paper_v2/infrastructure/"
            "v32_local_analysis_lane.py"
        )
        store_module = (
            "trade_system/theory_paper_v2/infrastructure/v32_dynamic_store.py"
        )
        self.assertEqual(
            {lane_module}, name_reference_modules[construction_marker]
        )
        self.assertEqual(
            {store_module},
            name_reference_modules[construction_verifier],
        )
        self.assertEqual({store_module}, name_reference_modules[writer_type])
        for registry_name in registry_names:
            self.assertEqual(
                {lane_module}, name_reference_modules[registry_name]
            )

        dynamic_store = (
            PROJECT_ROOT
            / "trade_system/theory_paper_v2/infrastructure/v32_dynamic_store.py"
        )
        tree = ast.parse(dynamic_store.read_text(encoding="utf-8"))
        public_methods = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        self.assertNotIn("persist_artifact", public_methods)

    def test_every_local_path_reachable_from_real_entrypoints_is_frozen(self):
        self.assertTrue(
            REQUIRED_V32_PRODUCTION_ENTRYPOINTS.issubset(PRODUCTION_ROOT_PATHS)
        )
        self.assertTrue(
            all((PROJECT_ROOT / path).is_file() for path in PRODUCTION_ROOT_PATHS)
        )
        closure = collect_v31_static_runtime_closure_v2(
            project_root=PROJECT_ROOT,
            production_root_paths=PRODUCTION_ROOT_PATHS,
        )
        bindings = build_v31_runtime_closure_bindings_v2(
            project_root=PROJECT_ROOT,
            production_root_paths=PRODUCTION_ROOT_PATHS,
            # A later actual qualification supplies an observed fresh-process
            # trace.  This deterministic regression uses the exact roots as
            # the minimum trace and proves the full AST closure is still bound.
            trace_paths=PRODUCTION_ROOT_PATHS,
        )
        self.assertEqual(43, len(PRODUCTION_ROOT_PATHS))
        self.assertEqual(196, len(closure))
        self.assertEqual(196, len(bindings))
        self.assertEqual(closure, tuple(bindings))
        self.assertTrue(REQUIRED_REACHABLE_V32_PATHS.issubset(closure))
        self.assertTrue(
            all(
                path == "trade_system/__init__.py"
                or path.startswith("trade_system/theory_paper_v2/")
                for path in closure
            )
        )
        self.assertNotIn(
            "trade_system/theory_paper_v2/application/bootstrap.py", closure
        )
        self.assertNotIn(
            "trade_system/theory_paper_v2/presentation/report.py", closure
        )

    def test_capability_and_wake_roots_are_bound_to_relevant_preflight_gates(self):
        controller = (
            "trade_system/theory_paper_v2/application/"
            "v32_actual_capability_qualification_controller.py"
        )
        wake = (
            "trade_system/theory_paper_v2/presentation/"
            "v32_target_wake_composition.py"
        )
        for gate_id in ("Q2", "Q3", "Q6", "Q7"):
            with self.subTest(gate_id=gate_id):
                self.assertIn(controller, GATE_IMPLEMENTATION_PATHS[gate_id])
        for gate_id in ("Q5", "Q7"):
            with self.subTest(gate_id=gate_id):
                self.assertIn(wake, GATE_IMPLEMENTATION_PATHS[gate_id])
        durable_writer = (
            "trade_system/theory_paper_v2/v32_durable_json.py"
        )
        for gate_id in ("Q1", "Q2", "Q3", "Q5", "Q6", "Q7", "Q8"):
            with self.subTest(gate_id=gate_id):
                self.assertIn(durable_writer, GATE_IMPLEMENTATION_PATHS[gate_id])

    def test_legacy_report_apis_remain_available_by_direct_module_import(self):
        from trade_system.theory_paper_v2.presentation.formal_report import (
            build_formal_experiment_markdown_zh,
        )
        from trade_system.theory_paper_v2.presentation.report import (
            MaterializedRound1Report,
            build_round1_markdown_zh,
            materialize_round1_report,
        )

        self.assertTrue(callable(build_formal_experiment_markdown_zh))
        self.assertTrue(callable(build_round1_markdown_zh))
        self.assertTrue(callable(materialize_round1_report))
        self.assertIsNotNone(MaterializedRound1Report)


if __name__ == "__main__":
    unittest.main()
