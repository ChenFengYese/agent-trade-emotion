from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import inspect
import json
import os
import unittest
from unittest.mock import Mock, patch

from tests import test_theory_paper_v2_v32_agent_semantic_compiler as semantic_fixture
from tests import test_theory_paper_v2_v32_current_research_authority as authority_fixture
from tests import test_theory_paper_v2_v32_public_source_collector as source_fixture
from tests.test_theory_paper_v2_v32_actual_capability_qualification import (
    SequenceClock,
)
from trade_system.theory_paper_v2.application.v32_agent_semantic_compiler import (
    build_v32_proposal_semantic_output_v1,
    build_v32_selection_semantic_output_v1,
    canonical_v32_agent_semantic_json_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.governance.v32_qualification_identity import (
    EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
    EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
    EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
    EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID,
    FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
    FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
    FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
    FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
    FAILED_V32_FUNDING_TIME_TARGET_RUN_ID,
    FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE,
    FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
    FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
    FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
    FAILED_V32_PHASE_A_CHRONOLOGY_QUALIFICATION_RUN_ID,
    FAILED_V32_PHASE_A_CHRONOLOGY_TARGET_RUN_ID,
    FAILED_V32_POSTCOMMIT_REGRESSION_QUALIFICATION_RUN_ID,
    FAILED_V32_POSTCOMMIT_REGRESSION_TARGET_RUN_ID,
    FAILED_V32_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
    FAILED_V32_TARGET_RUN_ID,
    EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS,
    FAILED_V32_QUALIFICATION_IDENTITY_PAIRS,
    HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS,
    is_exact_failed_v32_qualification_preflight_identity_v1,
    is_exact_historical_v32_qualification_preflight_identity_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
    MAX_PROPOSAL_CANONICAL_PACKET_BYTES,
    MAX_SELECTION_CANONICAL_PACKET_BYTES,
    V32_QUALIFICATION_CONTEXT_PROFILE,
    resolve_v32_agent_canonical_packet_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_market_graph_view import (
    MAX_CANONICAL_BYTES as MAX_AGENT_MARKET_GRAPH_VIEW_CANONICAL_BYTES,
    seal_v32_agent_market_graph_view_v1,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    REQUEST_DIGEST_FIELD,
    build_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    V32ContextCompactionError,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    build_v32_active_authority_projection,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_actual_capability_attempt_ports import (
    V32ActualCapabilityAttemptAdapterError,
    V32CurrentCodexQualificationAttemptPort,
    V32PublicSourceQualificationAttemptPort,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_runtime_namespace import (
    V32QualificationRuntimeNamespaceError,
    create_v32_qualification_runtime_namespace_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    v32_qualification_runtime_namespace as namespace_module,
)
from trade_system.theory_paper_v2.infrastructure import (
    v32_public_market_graph_projection as graph_projection_module,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_actual_capability_replay import (
    LocalV32ActualCapabilityEvidenceStore,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_materializer import (
    LocalV32QualificationMaterialStore,
    LocalV32QualificationMaterializer,
    V32QualificationMaterializerError,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    V32CurrentRootAgentMailboxStoreError,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.presentation import (
    v32_qualification_composition as qualification_composition,
)
from trade_system.theory_paper_v2.presentation import (
    v32_target_run_composition as target_run_composition,
)
from trade_system.theory_paper_v2.presentation import (
    v32_target_wake_composition as target_wake_composition,
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class StepClock:
    def __init__(self, current: datetime) -> None:
        self.current = current
        self.queued: list[datetime] = []

    def __call__(self) -> str:
        if self.queued:
            value = self.queued.pop(0)
        else:
            value = self.current
            self.current += timedelta(seconds=1)
        return iso(value)


class PublicMarkCapture:
    def __init__(self, clock: StepClock) -> None:
        self.clock = clock
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        requested = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
        received = max(self.clock.current, requested + timedelta(seconds=1))
        self.clock.current = received + timedelta(seconds=1)
        provider = received - timedelta(seconds=1)
        raw = json.dumps(
            {
                "code": "0",
                "msg": "",
                "data": [{
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                    "markPx": "60020.1",
                    "ts": str(int(provider.timestamp() * 1000)),
                }],
            },
            separators=(",", ":"),
        ).encode()
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": attempt["source_request_id"],
            "received_at": iso(received),
            "captured_at": iso(self.clock.current),
            "final_url": OKX_V32_MARK_PRICE_URL,
            "http_status": 200,
            "raw_payload": raw,
        }


def normalized_binding(binding: dict) -> dict:
    return {
        "relative_ref": binding["path"],
        "schema_id": binding["schema_id"],
        "digest_field": binding["digest_field"],
        "semantic_digest": binding["semantic_digest"],
        "physical_sha256": binding["physical_sha256"],
    }


def capacity_regression_candle_rows(interval_ms: int) -> list[list[str]]:
    """Fixed sanitized shape matching the sealed 96/168/90/60-bar failure."""

    counts = {
        900_000: 96,
        3_600_000: 168,
        14_400_000: 90,
        86_400_000: 60,
    }
    count = counts[interval_ms]
    bucket = (source_fixture.SERVER_MS // interval_ms) * interval_ms
    rows: list[list[str]] = []
    for index in range(count):
        opened = bucket - ((count - index) * interval_ms)
        close = 60_000 + index
        rows.append(
            [
                str(opened),
                str(close - 1),
                str(close + 3),
                str(close - 4),
                str(close),
                str(100 + index),
                str(100 + index),
                str((100 + index) * close),
                "1",
            ]
        )
    return rows


LEGACY_FAILED_RUNTIME_ROOT = ".runtime/v32/qualification"


def tree_fingerprint(root: Path) -> tuple[tuple[str, str, str], ...]:
    """Hash a whole tree without following links or normalizing its paths."""

    if not root.exists() and not root.is_symlink():
        return ()
    rows: list[tuple[str, str, str]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in sorted((*directories, *files)):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                rows.append((relative, "SYMLINK", os.readlink(path)))
            elif path.is_dir():
                rows.append((relative, "DIRECTORY", ""))
            else:
                rows.append(
                    (
                        relative,
                        "FILE",
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
    return tuple(rows)


class V32QualificationMaterializerEndToEndTests(unittest.TestCase):
    def test_qualification_material_burst_stops_at_agent_boundary(self):
        materializer = Mock()
        materializer.verification_scope.return_value = nullcontext()
        materializer.advance_once.side_effect = [
            {
                "status": "PENDING",
                "boundary_kind": "QUALIFICATION_MATERIAL_PERSISTED:first",
                "state_changed": True,
                "observed_state_digest": "a" * 64,
            },
            {
                "status": "PENDING",
                "boundary_kind": "QUALIFICATION_PROPOSAL_ENQUEUED",
                "state_changed": True,
                "observed_state_digest": "b" * 64,
            },
            {
                "status": "AWAITING_AGENT",
                "boundary_kind": "NO_ADVANCE_AWAITING_PROPOSAL",
                "state_changed": False,
                "observed_state_digest": "b" * 64,
            },
        ]
        result = qualification_composition._advance_v32_qualification_material_burst_v1(
            materializer
        )
        self.assertEqual("AWAITING_AGENT", result["status"])
        self.assertEqual("AGENT_REQUIRED", result["burst_stop_reason"])
        self.assertEqual(3, result["burst_step_count"])
        self.assertEqual(2, result["internal_append_only_substage_count"])
        self.assertEqual(
            [
                "QUALIFICATION_MATERIAL_PERSISTED:first",
                "QUALIFICATION_PROPOSAL_ENQUEUED",
                "NO_ADVANCE_AWAITING_PROPOSAL",
            ],
            result["burst_step_boundaries"],
        )
        self.assertEqual(3, materializer.advance_once.call_count)

    def test_qualification_material_burst_has_hard_sixty_four_step_cap(self):
        materializer = Mock()
        materializer.verification_scope.return_value = nullcontext()
        materializer.advance_once.side_effect = [
            {
                "status": "PENDING",
                "boundary_kind": f"QUALIFICATION_MATERIAL_PERSISTED:r{index}",
                "state_changed": True,
                "observed_state_digest": f"{index:064x}",
            }
            for index in range(
                qualification_composition.MAX_ANALYSIS_SUBSTAGES_PER_WAKE
            )
        ]
        result = qualification_composition._advance_v32_qualification_material_burst_v1(
            materializer
        )
        self.assertEqual("PENDING", result["status"])
        self.assertEqual(
            "SUBSTAGE_LIMIT_REACHED", result["burst_stop_reason"]
        )
        self.assertEqual(
            qualification_composition.MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
            result["burst_step_count"],
        )
        self.assertEqual(
            qualification_composition.MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
            materializer.advance_once.call_count,
        )

    def test_qualification_material_burst_stops_at_probe_boundary(self):
        materializer = Mock()
        materializer.verification_scope.return_value = nullcontext()
        materializer.advance_once.side_effect = [
            {
                "status": "PENDING",
                "boundary_kind": "QUALIFICATION_MATERIAL_PERSISTED:action_plan",
                "state_changed": True,
                "observed_state_digest": "a" * 64,
            },
            {
                "status": "PENDING",
                "boundary_kind": "QUALIFICATION_MONITOR_PROBE_SCHEDULED",
                "state_changed": True,
                "observed_state_digest": "b" * 64,
            },
            {
                "status": "READY",
                "boundary_kind": "NO_ADVANCE_MATERIAL_COMPLETE",
                "state_changed": False,
                "observed_state_digest": "c" * 64,
            },
        ]
        result = qualification_composition._advance_v32_qualification_material_burst_v1(
            materializer
        )
        self.assertEqual(
            "PROBE_BOUNDARY_COMPLETED", result["burst_stop_reason"]
        )
        self.assertEqual(2, result["burst_step_count"])
        self.assertEqual(1, result["internal_append_only_substage_count"])
        self.assertTrue(result["qualification_probe_boundary_completed"])
        self.assertEqual(2, materializer.advance_once.call_count)

    def test_qualification_material_burst_outer_controller_boundary_policy(self):
        base = {
            "status": "PENDING",
            "boundary_kind": "QUALIFICATION_MONITOR_PROBE_SCHEDULED",
            "state_changed": True,
            "burst_stop_reason": "PROBE_BOUNDARY_COMPLETED",
        }
        self.assertTrue(
            qualification_composition._v32_qualification_material_burst_stops_before_controller_v1(
                base
            )
        )
        self.assertFalse(
            qualification_composition._v32_qualification_material_burst_stops_before_controller_v1(
                {
                    **base,
                    "boundary_kind": "QUALIFICATION_MONITOR_PROBE_ALREADY_SCHEDULED",
                    "state_changed": False,
                }
            )
        )
        self.assertFalse(
            qualification_composition._v32_qualification_material_burst_stops_before_controller_v1(
                {
                    **base,
                    "status": "READY",
                    "boundary_kind": "NO_ADVANCE_MATERIAL_COMPLETE",
                    "state_changed": False,
                    "burst_stop_reason": "MATERIAL_READY",
                }
            )
        )
        for stop_reason in ("SUBSTAGE_LIMIT_REACHED", "NO_PROGRESS"):
            with self.subTest(stop_reason=stop_reason):
                self.assertTrue(
                    qualification_composition._v32_qualification_material_burst_stops_before_controller_v1(
                        {
                            **base,
                            "state_changed": False,
                            "burst_stop_reason": stop_reason,
                        }
                    )
                )

    def test_qualification_material_burst_stops_on_pending_no_progress(self):
        materializer = Mock()
        materializer.verification_scope.return_value = nullcontext()
        materializer.advance_once.return_value = {
            "status": "PENDING",
            "boundary_kind": "NO_ADVANCE_NO_PROGRESS",
            "state_changed": False,
            "observed_state_digest": "a" * 64,
        }
        result = qualification_composition._advance_v32_qualification_material_burst_v1(
            materializer
        )
        self.assertEqual("PENDING", result["status"])
        self.assertEqual("NO_PROGRESS", result["burst_stop_reason"])
        self.assertEqual(1, materializer.advance_once.call_count)

    def test_qualification_material_burst_rejects_unknown_future_boundary(self):
        for state_changed in (False, True):
            materializer = Mock()
            materializer.verification_scope.return_value = nullcontext()
            materializer.advance_once.return_value = {
                "status": "PENDING",
                "boundary_kind": "FUTURE_UNCLASSIFIED_HIGH_LEVEL_BOUNDARY",
                "state_changed": state_changed,
                "observed_state_digest": "a" * 64,
            }
            with self.subTest(
                state_changed=state_changed
            ), self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "MATERIAL_BURST_BOUNDARY_INVALID",
            ):
                qualification_composition._advance_v32_qualification_material_burst_v1(
                    materializer
                )
            self.assertEqual(1, materializer.advance_once.call_count)

    def test_formal_production_api_signatures_expose_no_runtime_injection(self):
        expected = {
            qualification_composition.prepare_v32_qualification_from_committed_workspace_v1: (
                "target_run_id",
                "qualification_run_id",
            ),
            qualification_composition.advance_v32_qualification_once_v1: (
                "target_run_id",
                "qualification_run_id",
            ),
            qualification_composition.read_and_claim_v32_qualification_agent_request_v1: (
                "target_run_id",
                "qualification_run_id",
            ),
            qualification_composition.submit_v32_qualification_agent_delivery_v1: (
                "target_run_id",
                "qualification_run_id",
                "stage",
                "expected_request_digest",
                "expected_current_codex_presentation_digest",
                "payload_utf8",
            ),
            qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1: (
                "target_run_id",
                "qualification_run_id",
            ),
        }
        forbidden = {
            "project_root",
            "runtime_root_relative_ref",
            "controller_store",
            "clock",
            "capability_verifiers",
            "qualification_authority_binding",
            "qualification_receipt_binding",
        }
        for function, names in expected.items():
            with self.subTest(function=function.__name__):
                signature = inspect.signature(function)
                self.assertEqual(names, tuple(signature.parameters))
                self.assertFalse(forbidden.intersection(signature.parameters))
                self.assertTrue(
                    all(
                        parameter.kind is inspect.Parameter.KEYWORD_ONLY
                        and parameter.default is inspect.Parameter.empty
                        for parameter in signature.parameters.values()
                    )
                )

    def test_production_run_ids_cannot_inject_or_reuse_runtime_paths(self):
        invalid = (
            "../qualification",
            "v32/qualification",
            "V32-QUALIFICATION",
            "v32 qualification",
            ".runtime",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "RUN_ID_INVALID",
            ):
                qualification_composition._ids(
                    "v32-production-api-target", value
                )
        first = qualification_composition._runtime_paths(
            "v32-qualification-one"
        )
        second = qualification_composition._runtime_paths(
            "v32-qualification-two"
        )
        self.assertNotEqual(first["root"], second["root"])
        self.assertTrue(first["root"].startswith(".runtime/v32/qualifications/"))
        for target, qualification in (
            (FAILED_V32_TARGET_RUN_ID, "v32-new-qualification"),
            ("v32-new-target", FAILED_V32_QUALIFICATION_RUN_ID),
            (FAILED_V32_QUALIFICATION_RUN_ID, "v32-new-qualification"),
            (
                FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                FAILED_V32_FUNDING_TIME_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
            ),
            (
                FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
            (
                EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                "v32-new-qualification",
            ),
            (
                "v32-new-target",
                EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
            ),
            (
                EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                "v32-new-qualification",
            ),
        ):
            with self.subTest(
                target=target, qualification=qualification
            ), self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "RUN_ID_TOMBSTONED",
            ):
                qualification_composition._ids(target, qualification)

    def test_moved_fifth_failure_identity_is_rejected_before_every_fixed_api_access(self):
        with TemporaryDirectory() as folder:
            project = Path(folder)
            moved = project / ".runtime/v32/moved-failed-materialization"
            moved.mkdir(parents=True)
            (moved / "historical.json").write_text(
                '{"status":"FAILED_CLOSED"}\n', encoding="utf-8"
            )
            before = tree_fingerprint(moved)
            calls = (
                lambda: qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                    target_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                ),
                lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                    target_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
            )
            with patch.object(
                qualification_composition, "PROJECT_ROOT", project
            ), patch.object(
                qualification_composition,
                "_runtime_paths",
                side_effect=AssertionError("tombstone must precede runtime access"),
            ), patch.object(
                qualification_composition,
                "_qualification_composition_guard_v1",
                side_effect=AssertionError("tombstone must precede guard access"),
            ):
                for call in calls:
                    with self.subTest(call=call), self.assertRaisesRegex(
                        qualification_composition.V32QualificationCompositionError,
                        "RUN_ID_TOMBSTONED",
                    ):
                        call()
            with patch.object(
                target_run_composition,
                "load_v32_current_research_authority",
                side_effect=AssertionError("tombstone must precede authority access"),
            ):
                for call in (
                    target_run_composition.replay_v32_target_run_from_current_authority_v1,
                    target_run_composition.seal_v32_cycle_zero_qualification_audit_v1,
                    target_run_composition.initialize_v32_target_run_from_current_authority_v1,
                ):
                    with self.subTest(target_call=call), self.assertRaisesRegex(
                        target_run_composition.V32TargetRunCompositionError,
                        "RUN_ID_TOMBSTONED",
                    ):
                        call(
                            project_root=project,
                            expected_run_id=FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                        )
            self.assertEqual(before, tree_fingerprint(moved))

    def test_sixth_failed_identity_is_tombstoned_before_runtime_or_authority_access(self):
        with patch.object(
            qualification_composition,
            "_runtime_paths",
            side_effect=AssertionError("tombstone must precede runtime access"),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            side_effect=AssertionError("tombstone must precede guard access"),
        ):
            calls = (
                lambda: qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                    target_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                ),
                lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                    target_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                ),
            )
            for call in calls:
                with self.subTest(call=call), self.assertRaisesRegex(
                    qualification_composition.V32QualificationCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call()
        with patch.object(
            target_run_composition,
            "load_v32_current_research_authority",
            side_effect=AssertionError("tombstone must precede authority access"),
        ):
            for call in (
                target_run_composition.replay_v32_target_run_from_current_authority_v1,
                target_run_composition.seal_v32_cycle_zero_qualification_audit_v1,
                target_run_composition.initialize_v32_target_run_from_current_authority_v1,
            ):
                with self.subTest(target_call=call), self.assertRaisesRegex(
                    target_run_composition.V32TargetRunCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call(
                        project_root=Path("/definitely-not-accessed"),
                        expected_run_id=FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                    )

    def test_seventh_expired_agent_identity_is_tombstoned_before_fixed_api_access(self):
        with patch.object(
            qualification_composition,
            "_runtime_paths",
            side_effect=AssertionError("tombstone must precede runtime access"),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            side_effect=AssertionError("tombstone must precede guard access"),
        ):
            calls = (
                lambda: qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.run_v32_postcommit_regressions_for_qualification_once_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                ),
                lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                    target_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    qualification_run_id=EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                ),
            )
            for call in calls:
                with self.subTest(call=call), self.assertRaisesRegex(
                    qualification_composition.V32QualificationCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call()
        with patch.object(
            target_run_composition,
            "load_v32_current_research_authority",
            side_effect=AssertionError("tombstone must precede authority access"),
        ):
            for call in (
                target_run_composition.replay_v32_target_run_from_current_authority_v1,
                target_run_composition.seal_v32_cycle_zero_qualification_audit_v1,
                target_run_composition.initialize_v32_target_run_from_current_authority_v1,
            ):
                with self.subTest(target_call=call), self.assertRaisesRegex(
                    target_run_composition.V32TargetRunCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call(
                        project_root=Path("/definitely-not-accessed"),
                        expected_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    )
            with TemporaryDirectory() as folder:
                project = Path(folder)
                for call in (
                    lambda: target_wake_composition.read_and_claim_v32_target_agent_request_v1(
                        project_root=project,
                        expected_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    ),
                    lambda: target_wake_composition.submit_v32_target_agent_delivery_v1(
                        project_root=project,
                        expected_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                        stage="PROPOSAL",
                        expected_request_digest="a" * 64,
                        expected_current_codex_presentation_digest="b" * 64,
                        payload_utf8="{}",
                    ),
                    lambda: target_wake_composition.run_v32_target_wake_v1(
                        project_root=project,
                        expected_run_id=EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                    ),
                ):
                    with self.subTest(
                        target_wake_call=call
                    ), self.assertRaisesRegex(
                        ValueError,
                        "RUN_ID_TOMBSTONED",
                    ):
                        call()

    def test_eighth_concurrent_failure_identity_is_tombstoned_before_any_live_api(self):
        runtime_root = (
            Path(__file__).resolve().parents[1]
            / ".runtime/v32/qualifications"
            / FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID
        )
        incident_tree_before = (
            tree_fingerprint(runtime_root) if runtime_root.is_dir() else None
        )
        with patch.object(
            qualification_composition,
            "_runtime_paths",
            side_effect=AssertionError("tombstone must precede runtime access"),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            side_effect=AssertionError("tombstone must precede guard access"),
        ):
            calls = (
                lambda: qualification_composition.prepare_v32_qualification_from_committed_workspace_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.run_v32_postcommit_regressions_for_qualification_once_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.advance_v32_qualification_once_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
                lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                ),
                lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                    target_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    qualification_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                ),
            )
            for call in calls:
                with self.subTest(call=call), self.assertRaisesRegex(
                    qualification_composition.V32QualificationCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call()

        with patch.object(
            target_run_composition,
            "load_v32_current_research_authority",
            side_effect=AssertionError("tombstone must precede authority access"),
        ):
            for call in (
                target_run_composition.replay_v32_target_run_from_current_authority_v1,
                target_run_composition.seal_v32_cycle_zero_qualification_audit_v1,
                target_run_composition.initialize_v32_target_run_from_current_authority_v1,
            ):
                with self.subTest(target_call=call), self.assertRaisesRegex(
                    target_run_composition.V32TargetRunCompositionError,
                    "RUN_ID_TOMBSTONED",
                ):
                    call(
                        project_root=Path("/definitely-not-accessed"),
                        expected_run_id=FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                    )

        if runtime_root.is_dir():
            controller_paths = sorted(
                (runtime_root / "controller/checkpoints").glob("*.json")
            )
            self.assertTrue(controller_paths)
            controller = json.loads(
                controller_paths[-1].read_text(encoding="utf-8")
            )
            failure = json.loads(
                (
                    runtime_root / "controller/materialization-failure.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(4, controller["revision"])
            self.assertEqual("FAILED_CLOSED", controller["status"])
            self.assertEqual(
                "MATERIALIZATION_FAILED:CURRENT_CODEX:"
                "V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID",
                controller["failure_code"],
            )
            self.assertEqual(
                ["V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID"],
                failure["failure_codes"],
            )
            self.assertFalse(failure["retry_allowed"])
            self.assertEqual(14, failure["material_predecessor_count"])
            self.assertEqual([], failure["mailbox_prefix_bindings"])
            actual_roles = sorted(
                (
                    runtime_root
                    / "material/v32-qualification-material-v1/roles"
                ).glob("*.json")
            )
            self.assertEqual(15, len(actual_roles))
            self.assertIn("proposal_input", {path.stem for path in actual_roles})
            mailbox_cycle = (
                runtime_root
                / "mailbox/v32-current-root-agent-mailbox-v1/cycles/0001"
            )
            self.assertTrue((mailbox_cycle / "checkpoint.json").is_file())
            self.assertTrue(
                (mailbox_cycle / "proposal/request.json").is_file()
            )
            self.assertEqual(
                incident_tree_before, tree_fingerprint(runtime_root)
            )

    def test_terminal_identity_classes_are_disjoint_and_runtime_truth_is_unchanged(self):
        expired_pair = (
            EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
            EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
        )
        failed_concurrent_pair = (
            FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
            FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
        )
        latest_terminal_pairs = {
            (
                FAILED_V32_POSTCOMMIT_REGRESSION_QUALIFICATION_RUN_ID,
                FAILED_V32_POSTCOMMIT_REGRESSION_TARGET_RUN_ID,
            ),
            (
                EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
                EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID,
            ),
            (
                FAILED_V32_PHASE_A_CHRONOLOGY_QUALIFICATION_RUN_ID,
                FAILED_V32_PHASE_A_CHRONOLOGY_TARGET_RUN_ID,
            ),
        }
        self.assertEqual(9, len(FAILED_V32_QUALIFICATION_IDENTITY_PAIRS))
        self.assertEqual(2, len(EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS))
        self.assertTrue(
            FAILED_V32_QUALIFICATION_IDENTITY_PAIRS.isdisjoint(
                EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS
            )
        )
        self.assertEqual(
            FAILED_V32_QUALIFICATION_IDENTITY_PAIRS
            | EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS,
            HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS,
        )
        self.assertEqual(
            11, len(HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS)
        )
        self.assertIn(expired_pair, EXPIRED_V32_QUALIFICATION_IDENTITY_PAIRS)
        self.assertIn(
            failed_concurrent_pair,
            FAILED_V32_QUALIFICATION_IDENTITY_PAIRS,
        )
        self.assertTrue(
            latest_terminal_pairs.issubset(
                HISTORICAL_TERMINAL_V32_QUALIFICATION_IDENTITY_PAIRS
            )
        )
        for qualification, target in latest_terminal_pairs:
            with self.subTest(qualification=qualification), self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "RUN_ID_TOMBSTONED",
            ):
                qualification_composition._ids(target, qualification)
        self.assertFalse(
            is_exact_failed_v32_qualification_preflight_identity_v1(
                profile=FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE,
                run_id=expired_pair[0],
                target_run_id=expired_pair[1],
            )
        )
        self.assertTrue(
            is_exact_historical_v32_qualification_preflight_identity_v1(
                profile=FAILED_V32_QUALIFICATION_PREFLIGHT_PROFILE,
                run_id=expired_pair[0],
                target_run_id=expired_pair[1],
            )
        )

        runtime_root = (
            Path(__file__).resolve().parents[1]
            / ".runtime/v32/qualifications"
            / EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID
        )
        if not runtime_root.is_dir():
            return
        before = tree_fingerprint(runtime_root)
        controller_paths = sorted(
            (runtime_root / "controller/checkpoints").glob("*.json")
        )
        self.assertTrue(controller_paths)
        controller = json.loads(
            controller_paths[-1].read_text(encoding="utf-8")
        )
        mailbox = json.loads(
            (
                runtime_root
                / "mailbox/v32-current-root-agent-mailbox-v1/cycles/0001/checkpoint.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual("RUNNING", controller["status"])
        self.assertEqual(3, controller["revision"])
        self.assertEqual("WAITING_FOR_PROPOSAL", mailbox["status"])
        self.assertEqual(
            "REQUESTED", mailbox["stage_states"]["PROPOSAL"]["status"]
        )
        self.assertEqual(
            "BLOCKED", mailbox["stage_states"]["SELECTION"]["status"]
        )
        self.assertIsNone(mailbox["stage_states"]["PROPOSAL"]["claim_digest"])
        self.assertIsNone(
            mailbox["stage_states"]["PROPOSAL"]["delivery_receipt_digest"]
        )
        self.assertEqual(before, tree_fingerprint(runtime_root))

    def test_runtime_namespace_write_boundary_rejects_tombstone_before_mkdir(self):
        for qualification_run_id in (
            FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
            EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
            FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
        ):
            with self.subTest(
                qualification_run_id=qualification_run_id
            ), TemporaryDirectory() as folder:
                project = Path(folder)
                with patch("os.mkdir") as mkdir, self.assertRaisesRegex(
                    V32QualificationRuntimeNamespaceError,
                    "V32_QUALIFICATION_RUN_ID_TOMBSTONED",
                ):
                    create_v32_qualification_runtime_namespace_v1(
                        project_root=project,
                        qualification_run_id=qualification_run_id,
                    )
                mkdir.assert_not_called()
                self.assertFalse((project / ".runtime").exists())

    def test_runtime_namespace_repairs_parent_fsync_failure_on_retry(self):
        qualification = "v32-qualification-btcusdt-20260810t000000z"
        with TemporaryDirectory() as folder:
            project = Path(folder)
            real_fsync = namespace_module.os.fsync
            failed = False

            def fail_first_parent_sync(descriptor):
                nonlocal failed
                if not failed:
                    failed = True
                    raise OSError("injected namespace parent fsync failure")
                real_fsync(descriptor)

            with patch.object(
                namespace_module.os,
                "fsync",
                side_effect=fail_first_parent_sync,
            ), self.assertRaisesRegex(
                V32QualificationRuntimeNamespaceError,
                "V32_QUALIFICATION_NAMESPACE_CREATE_FAILED",
            ):
                create_v32_qualification_runtime_namespace_v1(
                    project_root=project,
                    qualification_run_id=qualification,
                )

            paths = create_v32_qualification_runtime_namespace_v1(
                project_root=project,
                qualification_run_id=qualification,
            )
            self.assertTrue((project / paths["root"]).is_dir())

    def test_runtime_namespace_rejects_lexical_root_swap_after_creation(self):
        qualification = "v32-qualification-btcusdt-20260810t000100z"
        with TemporaryDirectory() as folder:
            project = Path(folder)
            real_verify = namespace_module._reopen_verify_and_sync_components

            def swap_then_verify(project_root, *, parts, identities):
                runtime_root = project_root.joinpath(*parts)
                moved = runtime_root.with_name(f"{runtime_root.name}-moved")
                runtime_root.rename(moved)
                runtime_root.mkdir()
                return real_verify(
                    project_root, parts=parts, identities=identities
                )

            with patch.object(
                namespace_module,
                "_reopen_verify_and_sync_components",
                side_effect=swap_then_verify,
            ), self.assertRaisesRegex(
                V32QualificationRuntimeNamespaceError,
                "V32_QUALIFICATION_NAMESPACE_IDENTITY_CHANGED",
            ):
                create_v32_qualification_runtime_namespace_v1(
                    project_root=project,
                    qualification_run_id=qualification,
                )

    def test_finalize_reentry_reuses_sealed_phase_times_without_new_clock(self):
        target = "v32-target-reentry"
        qualification = "v32-qualification-reentry"
        authority_binding = {
            "path": "runtime/qualification/authority.json",
            "schema_id": "authority",
            "digest_field": "authority_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        }
        receipt_binding = {
            "path": "runtime/qualification-receipt.json",
            "schema_id": "qualification-receipt",
            "digest_field": "qualification_receipt_digest",
            "semantic_digest": "c" * 64,
            "physical_sha256": "d" * 64,
        }
        paths = {"root": "runtime", "controller": "runtime/controller"}
        controller_document = {
            "status": "COMPLETE",
            "qualification_run_id": qualification,
            "target_run_id": target,
            "qualification_authority_binding": authority_binding,
            "qualification_receipt_binding": receipt_binding,
        }
        sealed_times = {
            "retired_at": "2026-08-07T00:09:00Z",
            "target_gate_evaluated_at": "2026-08-07T00:10:00Z",
            "target_phase_evaluated_at": "2026-08-07T00:10:00Z",
            "target_authorization_issued_at": "2026-08-07T00:11:00Z",
            "target_authority_recorded_at": "2026-08-07T00:12:00Z",
        }
        controller = Mock()
        controller.load.return_value = controller_document
        expected = {"status": "TARGET_AUTHORITY_READY"}
        with patch.object(
            qualification_composition,
            "_ids",
            return_value=(target, qualification),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            return_value=nullcontext(),
        ), patch.object(
            qualification_composition,
            "_load_authority",
            return_value=({}, authority_binding, {}, paths),
        ), patch.object(
            qualification_composition,
            "LocalV32ActualCapabilityQualificationControllerStore",
            return_value=controller,
        ), patch.object(
            qualification_composition,
            "load_v32_target_finalization_phase_times_if_started",
            return_value=sealed_times,
        ), patch.object(
            qualification_composition,
            "build_v32_system_clock_v1",
            side_effect=AssertionError("reentry must not allocate a new clock"),
        ), patch.object(
            qualification_composition,
            "finalize_v32_target_authority",
            return_value=expected,
        ) as finalize, patch.object(
            qualification_composition,
            "_assert_namespace",
            return_value=paths,
        ):
            result = qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                target_run_id=target,
                qualification_run_id=qualification,
            )
        self.assertEqual(expected, result)
        self.assertEqual(sealed_times, finalize.call_args.kwargs["phase_times"])

    def test_materializer_revalidates_each_generated_time_at_and_after_hard_boundary(self):
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        authority = packet["authority_document"]
        with TemporaryDirectory() as folder:
            project = Path(folder)
            evidence = LocalV32ActualCapabilityEvidenceStore(project, "evidence")
            reserved = evidence.reserve_attempt(
                capability="CURRENT_CODEX",
                qualification_run_id=authority["run_id"],
                target_run_id=authority["target_run_id"],
                qualification_authority_digest=authority[AUTHORITY_DIGEST_FIELD],
                reserved_at="2026-08-07T00:15:00Z",
            )["reservation"]
            clock = StepClock(datetime(2026, 8, 7, 0, 26, tzinfo=UTC))
            materializer = object.__new__(LocalV32QualificationMaterializer)
            materializer.authority = authority
            materializer.current_codex_attempt_reservation = reserved
            materializer.clock = clock
            self.assertEqual(
                materializer._current_codex_time(), "2026-08-07T00:26:00Z"
            )
            with self.assertRaisesRegex(
                V32ActualCapabilityAttemptAdapterError, "ATTEMPT_EXPIRED"
            ):
                materializer._current_codex_time()

    def test_materializer_failure_uses_entered_phase_and_hint_includes_action_evaluation(self):
        materializer = object.__new__(LocalV32QualificationMaterializer)
        materializer.authority = {"run_id": "qualification-phase-test"}
        materializer.public = V32InfrastructurePublicEvidenceVerifier()
        materializer._current_codex_time = Mock(
            side_effect=V32ContextCompactionError(
                "CONTEXT_CAPACITY_UNRESOLVED"
            )
        )
        with self.assertRaises(V32QualificationMaterializerError) as raised:
            materializer.advance_once()
        self.assertEqual(
            "TIME:CURRENT_CODEX_WINDOW",
            raised.exception.materialization_phase,
        )
    def _assert_composition_seals_materializer_failure(
        self, *, scan_failure: str | None
    ) -> None:
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        authority = packet["authority_document"]
        authority_binding = {
            "path": packet["authority_binding"]["relative_ref"],
            **{
                key: packet["authority_binding"][key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        }
        target = authority["target_run_id"]
        qualification = authority["run_id"]
        paths = {
            key: f"runtime/{key}"
            for key in (
                "root",
                "evidence",
                "controller",
                "probe",
                "source",
                "run_source",
                "mailbox",
                "material",
            )
        }
        checkpoint = {
            "revision": 3,
            "updated_at": "2026-08-07T00:14:00Z",
            "capability_states": {
                "PUBLIC_SOURCE": {"status": "COMPLETE"},
                "CURRENT_CODEX": {"status": "PENDING"},
                "OUTCOME_MONITOR": {"status": "READY"},
            },
        }
        reservation_binding = {
            "path": "runtime/evidence/attempts/current-codex.json",
            "schema_id": "attempt",
            "digest_field": "attempt_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        }
        current_attempt = {
            "reservation": {
                "reserved_at": "2026-08-07T00:14:00Z",
                "capability": "CURRENT_CODEX",
                "qualification_run_id": qualification,
                "target_run_id": target,
                "qualification_authority_digest": authority[
                    AUTHORITY_DIGEST_FIELD
                ],
                "attempt_number": 1,
                "retry_allowed": False,
            },
            "reservation_binding": reservation_binding,
        }
        failure_receipt = {
            "materialization_stage": "PERSIST:PROPOSAL_INPUT",
            "failure_codes": ["CONTEXT_CAPACITY_UNRESOLVED"],
            "failure_time_status": "OBSERVED",
            "failed_at": "2026-08-07T00:14:01Z",
            "last_known_at": "2026-08-07T00:14:01Z",
            "attempt_reservation_binding": reservation_binding,
            "material_store_root": paths["material"],
            "material_prefix_status": (
                "UNKNOWN_REPLAY_FAILED"
                if scan_failure == "material"
                else "VERIFIED_EXACT"
            ),
            "material_scan_failure_codes": (
                ["MATERIAL_PREFIX_REPLAY_FAILED"]
                if scan_failure == "material"
                else []
            ),
            "material_predecessor_bindings": {},
            "mailbox_store_root": paths["mailbox"],
            "mailbox_prefix_status": (
                "UNKNOWN_REPLAY_FAILED"
                if scan_failure == "mailbox"
                else "VERIFIED_EXACT"
            ),
            "mailbox_scan_failure_codes": (
                ["MAILBOX_PREFIX_REPLAY_FAILED"]
                if scan_failure == "mailbox"
                else []
            ),
            "mailbox_prefix_bindings": [],
            "probe_store_root": paths["probe"],
            "probe_prefix_status": (
                "UNKNOWN_REPLAY_FAILED"
                if scan_failure == "probe"
                else "VERIFIED_EXACT"
            ),
            "probe_scan_failure_codes": (
                ["PROBE_PREFIX_REPLAY_FAILED"]
                if scan_failure == "probe"
                else []
            ),
            "probe_schedule_binding": None,
        }
        failure_binding = {"semantic_digest": "c" * 64}
        failed = {
            "runtime_status": "FAILED_CLOSED",
            "boundary_kind": "MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX",
            "checkpoint": {**checkpoint, "status": "FAILED_CLOSED"},
        }
        terminal = {
            **failed,
            "boundary_kind": "NO_ADVANCE_TERMINAL",
        }
        evidence = Mock()
        evidence.load_attempt_reservation.return_value = current_attempt
        controller = Mock()
        controller.load.return_value = checkpoint
        controller.load_materialization_failure.side_effect = [
            None,
            (failure_receipt, failure_binding),
        ]
        controller.seal_materialization_failure.side_effect = [failed, terminal]
        material_store = Mock()
        post_material_binding = {
            "path": "runtime/material/v32-qualification-material-v1/roles/agent_market_graph_view.json",
            "schema_id": "market-view",
            "digest_field": "market_view_digest",
            "semantic_digest": "1" * 64,
            "physical_sha256": "2" * 64,
        }
        material_store.predecessor_bindings.side_effect = [
            {},
            (
                RuntimeError("recovery scan failed")
                if scan_failure == "material"
                else {"agent_market_graph_view": post_material_binding}
            ),
        ]
        materializer = Mock()
        materializer.verification_scope.return_value = nullcontext()
        capacity = V32ContextCompactionError("CONTEXT_CAPACITY_UNRESOLVED")
        capacity.materialization_phase = "CONTEXT_PACKAGE:PROPOSAL"
        materializer.advance_once.side_effect = [
            {
                "status": "PENDING",
                "boundary_kind": (
                    "QUALIFICATION_MATERIAL_PERSISTED:agent_market_graph_view"
                ),
                "state_changed": True,
                "observed_state_digest": "1" * 64,
            },
            capacity,
        ]
        mailbox_binding = {
            "relative_ref": "v32-current-root-agent-mailbox-v1/cycles/0001/checkpoint.json",
            "schema_id": "mailbox-checkpoint",
            "digest_field": "mailbox_checkpoint_digest",
            "semantic_digest": "3" * 64,
            "physical_sha256": "4" * 64,
        }
        mailbox = Mock()
        if scan_failure == "mailbox":
            mailbox.json_prefix_inventory_v1.side_effect = RuntimeError(
                "recovery scan failed"
            )
        else:
            mailbox.json_prefix_inventory_v1.return_value = [mailbox_binding]
        probe_binding = {
            "relative_ref": "v32-qualification-monitor-probe-v1/schedule.json",
            "schema_id": "probe-schedule",
            "digest_field": "probe_schedule_digest",
            "semantic_digest": "5" * 64,
            "physical_sha256": "6" * 64,
        }
        probe = Mock()
        if scan_failure == "probe":
            probe.schedule_binding_v1.side_effect = RuntimeError(
                "recovery scan failed"
            )
        else:
            probe.schedule_binding_v1.return_value = probe_binding
        clock = StepClock(datetime(2026, 8, 7, 0, 14, 1, tzinfo=UTC))
        with patch.object(
            qualification_composition,
            "_load_authority",
            return_value=(
                authority,
                authority_binding,
                {"v32_experiment_contract_digest": "d" * 64},
                paths,
            ),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            return_value=nullcontext(),
        ), patch.object(
            qualification_composition,
            "_assert_namespace",
            return_value=paths,
        ), patch.object(
            qualification_composition,
            "build_v32_system_clock_v1",
            return_value=clock,
        ), patch.object(
            qualification_composition,
            "LocalV32ActualCapabilityEvidenceStore",
            return_value=evidence,
        ), patch.object(
            qualification_composition,
            "LocalV32ActualCapabilityQualificationControllerStore",
            return_value=controller,
        ), patch.object(
            qualification_composition,
            "LocalV32QualificationMaterialStore",
            return_value=material_store,
        ), patch.object(
            qualification_composition,
            "LocalV32QualificationMaterializer",
            return_value=materializer,
        ) as materializer_type, patch.object(
            qualification_composition,
            "V32OkxPublicMarkCaptureAdapter",
            return_value=Mock(),
        ) as capture_type, patch.object(
            qualification_composition,
            "LocalV32QualificationMonitorProbeStore",
            return_value=probe,
        ) as monitor_type, patch.object(
            qualification_composition,
            "V32PublicSourceQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32CurrentCodexQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32OutcomeMonitorQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "LocalV32CycleSourceAdmissionStore",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "LocalV32CurrentRootAgentMailbox",
            return_value=mailbox,
        ), patch.object(
            qualification_composition,
            "advance_v32_actual_capability_qualification_controller_once",
            side_effect=AssertionError("controller attempt lane must not advance"),
        ):
            first = qualification_composition.advance_v32_qualification_once_v1(
                target_run_id=target,
                qualification_run_id=qualification,
            )
            self.assertEqual("FAILED_CLOSED", first["runtime_status"])
            self.assertEqual(2, materializer.advance_once.call_count)
            capture_type.reset_mock()
            monitor_type.reset_mock()
            materializer_type.reset_mock()
            second = qualification_composition.advance_v32_qualification_once_v1(
                target_run_id=target,
                qualification_run_id=qualification,
            )
            self.assertEqual("NO_ADVANCE_TERMINAL", second["boundary_kind"])
            capture_type.assert_not_called()
            monitor_type.assert_not_called()
            materializer_type.assert_not_called()
        first_seal = controller.seal_materialization_failure.call_args_list[0].kwargs
        self.assertEqual(
            ("CONTEXT_CAPACITY_UNRESOLVED",), first_seal["failure_codes"]
        )
        self.assertEqual(
            "CONTEXT_PACKAGE:PROPOSAL", first_seal["materialization_stage"]
        )
        prefix_expectations = {
            "material": (
                first_seal["material_prefix_status"],
                first_seal["material_scan_failure_codes"],
                first_seal["material_predecessor_bindings"],
            ),
            "mailbox": (
                first_seal["mailbox_prefix_status"],
                first_seal["mailbox_scan_failure_codes"],
                first_seal["mailbox_prefix_bindings"],
            ),
            "probe": (
                first_seal["probe_prefix_status"],
                first_seal["probe_scan_failure_codes"],
                first_seal["probe_schedule_binding"],
            ),
        }
        for prefix, (status, codes, inventory) in prefix_expectations.items():
            if scan_failure == prefix:
                self.assertEqual("UNKNOWN_REPLAY_FAILED", status)
                self.assertEqual(
                    f"{prefix.upper()}_PREFIX_REPLAY_FAILED", codes[0]
                )
                self.assertEqual(1, len(codes))
                self.assertIn(inventory, ({}, [], None))
            else:
                self.assertEqual("VERIFIED_EXACT", status)
                self.assertEqual((), codes)

    def test_composition_seals_any_materializer_exception_and_terminal_wake_skips_all_lanes(self):
        self._assert_composition_seals_materializer_failure(scan_failure=None)

    def test_recovery_scan_failures_each_seal_once_and_terminal_wake_skips_materializer(self):
        for scan_failure in ("material", "mailbox", "probe"):
            with self.subTest(scan_failure=scan_failure):
                self._assert_composition_seals_materializer_failure(
                    scan_failure=scan_failure
                )

    def test_agent_fixed_apis_replay_failed_controller_before_mailbox_access(self):
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        authority = packet["authority_document"]
        authority_binding = {
            "path": packet["authority_binding"]["relative_ref"],
            **{
                key: packet["authority_binding"][key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        }
        paths = {"mailbox": "runtime/mailbox"}
        terminal = qualification_composition.V32QualificationCompositionError(
            "V32_QUALIFICATION_CONTROLLER_FAILED_CLOSED"
        )
        with patch.object(
            qualification_composition,
            "_load_authority",
            return_value=(
                authority,
                authority_binding,
                {"v32_experiment_contract_digest": "d" * 64},
                paths,
            ),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            return_value=nullcontext(),
        ), patch.object(
            qualification_composition,
            "_replay_controller_before_agent_v1",
            side_effect=terminal,
        ) as replay, patch.object(
            qualification_composition,
            "LocalV32CurrentRootAgentMailbox",
            side_effect=AssertionError("mailbox must remain untouched"),
        ):
            with self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "CONTROLLER_FAILED_CLOSED",
            ):
                qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=authority["target_run_id"],
                    qualification_run_id=authority["run_id"],
                )
            with self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "CONTROLLER_FAILED_CLOSED",
            ):
                qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=authority["target_run_id"],
                    qualification_run_id=authority["run_id"],
                    stage="PROPOSAL",
                    expected_request_digest="a" * 64,
                    expected_current_codex_presentation_digest="b" * 64,
                    payload_utf8="{}",
                )
        self.assertEqual(2, replay.call_count)

    def test_agent_fixed_api_rejects_non_running_controller_before_mailbox_access(self):
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        authority = packet["authority_document"]
        authority_binding = {
            "path": packet["authority_binding"]["relative_ref"],
            **{
                key: packet["authority_binding"][key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        }
        paths = {
            "evidence": "runtime/evidence",
            "probe": "runtime/probe",
            "source": "runtime/source",
            "run_source": "runtime/run-source",
            "mailbox": "runtime/mailbox",
            "controller": "runtime/controller",
        }
        reservation_binding = {
            "path": "runtime/evidence/current-codex-attempt.json",
            "schema_id": "test_attempt_v1",
            "digest_field": "test_attempt_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        }
        non_running = {
            "status": "COMPLETE",
            "capability_states": {
                "PUBLIC_SOURCE": {"status": "COMPLETE"},
                "CURRENT_CODEX": {
                    "status": "PENDING",
                    "reservation_binding": reservation_binding,
                },
                "OUTCOME_MONITOR": {"status": "READY"},
            },
        }
        with patch.object(
            qualification_composition,
            "_load_authority",
            return_value=(
                authority,
                authority_binding,
                {"v32_experiment_contract_digest": "d" * 64},
                paths,
            ),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            return_value=nullcontext(),
        ), patch.object(
            qualification_composition,
            "build_v32_system_clock_v1",
            return_value=lambda: "2026-08-07T00:14:00Z",
        ), patch.object(
            qualification_composition,
            "build_v32_active_authority_projection",
            return_value={},
        ), patch.object(
            qualification_composition,
            "LocalV32ActualCapabilityEvidenceStore",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32OkxPublicMarkCaptureAdapter",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "LocalV32QualificationMonitorProbeStore",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32OkxPublicBundleTransport",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32PublicSourceQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32CurrentCodexQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "V32OutcomeMonitorQualificationAttemptPort",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "LocalV32ActualCapabilityQualificationControllerStore",
            return_value=Mock(),
        ), patch.object(
            qualification_composition,
            "replay_v32_actual_capability_qualification_controller_v1",
            return_value=non_running,
        ), patch.object(
            qualification_composition,
            "LocalV32CurrentRootAgentMailbox",
            side_effect=AssertionError("mailbox must remain untouched"),
        ):
            with self.assertRaisesRegex(
                qualification_composition.V32QualificationCompositionError,
                "AGENT_CONTROLLER_STATE_INVALID",
            ):
                qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                    target_run_id=authority["target_run_id"],
                    qualification_run_id=authority["run_id"],
                )

    def test_qualification_claim_recovers_orphan_before_single_cas(self):
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        authority = packet["authority_document"]
        authority_binding = {
            "path": packet["authority_binding"]["relative_ref"],
            **{
                key: packet["authority_binding"][key]
                for key in (
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                )
            },
        }
        reservation_binding = {"semantic_digest": "a" * 64}
        reservation = {"reserved_at": "2026-08-07T00:00:00Z"}
        controller = {
            "capability_states": {
                "CURRENT_CODEX": {
                    "reservation_binding": reservation_binding
                }
            }
        }
        evidence = Mock()
        evidence.load_attempt_reservation.return_value = {
            "reservation": reservation,
            "reservation_binding": reservation_binding,
        }
        checkpoint = {
            MAILBOX_CHECKPOINT_DIGEST_FIELD: "b" * 64,
        }
        request = {"request": "first"}
        orphan_claim = {
            "claimed_at": "2026-08-07T00:01:00Z",
            "claim": "first-immutable-bytes",
        }
        pending = {
            "stage": "PROPOSAL",
            "stage_status": "REQUESTED",
            "next_action": "CURRENT_ROOT_CODEX_CLAIM",
            "request": request,
            "claim": orphan_claim,
        }
        chain = {
            "stage_status": "REQUESTED",
            "checkpoint_digest": checkpoint[
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            "request": request,
            "claim": orphan_claim,
            "canonical_packet_original": {
                "authority_document": authority
            },
            "lossless_context_package": None,
        }
        preview_checkpoint = {
            MAILBOX_CHECKPOINT_DIGEST_FIELD: "c" * 64,
        }
        mailbox = Mock()
        mailbox.load_checkpoint.return_value = checkpoint
        mailbox.next_pending_request.return_value = pending
        mailbox.load_stage_chain.return_value = chain
        mailbox.claim_request.return_value = {
            "checkpoint": preview_checkpoint,
            "request": request,
            "claim": orphan_claim,
        }
        events: list[str] = []

        def assert_namespace(run_id: str) -> dict:
            self.assertEqual(run_id, authority["run_id"])
            events.append("namespace")
            return {}

        def claim_request(**kwargs):
            events.append("claim-cas")
            return {
                "checkpoint": preview_checkpoint,
                "request": request,
                "claim": orphan_claim,
            }

        mailbox.claim_request.side_effect = claim_request
        with patch.object(
            qualification_composition,
            "_load_authority",
            return_value=(
                authority,
                authority_binding,
                {"v32_experiment_contract_digest": "d" * 64},
                {"mailbox": "runtime/mailbox"},
            ),
        ), patch.object(
            qualification_composition,
            "_qualification_composition_guard_v1",
            return_value=nullcontext(),
        ), patch.object(
            qualification_composition,
            "_replay_controller_before_agent_v1",
            return_value=(controller, evidence),
        ), patch.object(
            qualification_composition,
            "LocalV32CurrentRootAgentMailbox",
            return_value=mailbox,
        ), patch.object(
            qualification_composition,
            "build_v32_system_clock_v1",
            side_effect=AssertionError(
                "orphan recovery must not allocate a new claim time"
            ),
        ), patch.object(
            qualification_composition,
            "verify_v32_current_codex_attempt_time_v1",
        ) as verify_time, patch.object(
            qualification_composition,
            "build_v32_current_root_agent_mailbox_claim_v1",
        ) as build_claim, patch.object(
            qualification_composition,
            "claim_v32_current_root_agent_mailbox_request_v1",
            return_value=preview_checkpoint,
        ), patch.object(
            qualification_composition,
            "build_v32_current_codex_presentation_envelope_v1",
            return_value={"presentation": "exact"},
        ), patch.object(
            qualification_composition,
            "_assert_namespace",
            side_effect=assert_namespace,
        ):
            result = qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                target_run_id=authority["target_run_id"],
                qualification_run_id=authority["run_id"],
            )
        self.assertEqual(result, {"presentation": "exact"})
        self.assertEqual(events, ["namespace", "claim-cas"])
        build_claim.assert_not_called()
        verify_time.assert_called_once_with(
            qualification_authority=authority,
            reservation=reservation,
            observed_at=orphan_claim["claimed_at"],
        )
        mailbox.claim_request.assert_called_once_with(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="PROPOSAL",
            expected_checkpoint_digest=checkpoint[
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at=orphan_claim["claimed_at"],
        )

    def test_qualification_delivery_response_loss_replays_first_delivery_bytes(
        self,
    ) -> None:
        packet = semantic_fixture.lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        context, context_binding = semantic_fixture._context(
            "PROPOSAL",
            packet,
            created_at="2026-08-07T00:16:00Z",
        )
        authority = packet["authority_document"]
        run_id = authority["run_id"]
        reservation_binding = {"semantic_digest": "a" * 64}
        controller = {
            "capability_states": {
                "CURRENT_CODEX": {
                    "reservation_binding": reservation_binding
                }
            }
        }
        evidence = Mock()
        evidence.load_attempt_reservation.return_value = {
            "reservation": {"reserved_at": "2026-08-07T00:15:00Z"},
            "reservation_binding": reservation_binding,
        }
        with TemporaryDirectory() as folder:
            project = Path(folder)
            mailbox = LocalV32CurrentRootAgentMailbox(
                project / "runtime/mailbox"
            )
            initial = mailbox.initialize_checkpoint(
                mailbox_id=f"mailbox::{run_id}::1",
                run_id=run_id,
                cycle_index=1,
                created_at="2026-08-07T00:16:00Z",
            )
            opened = mailbox.enqueue_request(
                run_id=run_id,
                cycle_index=1,
                expected_checkpoint_digest=initial[
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                agent_input_context=context,
                agent_input_context_binding=context_binding,
                reserved_at="2026-08-07T00:16:05Z",
            )
            claimed = mailbox.claim_request(
                run_id=run_id,
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=opened["checkpoint"][
                    MAILBOX_CHECKPOINT_DIGEST_FIELD
                ],
                claimed_at="2026-08-07T00:16:10Z",
            )
            presentation = build_v32_current_codex_presentation_envelope_v1(
                mailbox_checkpoint=claimed["checkpoint"],
                request=claimed["request"],
                claim=claimed["claim"],
                lossless_context_package=None,
                control_context={
                    "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                    "stage": "PROPOSAL",
                    "stage_status": "CLAIMED",
                    "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                },
            )
            common_patches = (
                patch.object(qualification_composition, "PROJECT_ROOT", project),
                patch.object(
                    qualification_composition,
                    "_load_authority",
                    return_value=(
                        authority,
                        {"binding": "authority"},
                        {"contract": "verified"},
                        {"mailbox": "runtime/mailbox"},
                    ),
                ),
                patch.object(
                    qualification_composition,
                    "_replay_controller_before_agent_v1",
                    return_value=(controller, evidence),
                ),
                patch.object(
                    qualification_composition,
                    "verify_v32_current_codex_attempt_time_v1",
                ),
                patch.object(qualification_composition, "_assert_namespace"),
                patch.object(
                    qualification_composition,
                    "assert_v32_qualification_runtime_root_components_v1",
                    return_value={},
                ),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], patch.object(
                qualification_composition,
                "build_v32_system_clock_v1",
                return_value=lambda: "2026-08-07T00:16:20Z",
            ):
                first = qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=authority["target_run_id"],
                    qualification_run_id=run_id,
                    stage="PROPOSAL",
                    expected_request_digest=claimed["request"][
                        REQUEST_DIGEST_FIELD
                    ],
                    expected_current_codex_presentation_digest=presentation[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ],
                    payload_utf8="first immutable payload",
                )
            json_before = tuple(
                (path.relative_to(project).as_posix(), path.read_bytes())
                for path in sorted(project.rglob("*.json"))
            )
            common_patches = (
                patch.object(qualification_composition, "PROJECT_ROOT", project),
                patch.object(
                    qualification_composition,
                    "_load_authority",
                    return_value=(
                        authority,
                        {"binding": "authority"},
                        {"contract": "verified"},
                        {"mailbox": "runtime/mailbox"},
                    ),
                ),
                patch.object(
                    qualification_composition,
                    "_replay_controller_before_agent_v1",
                    return_value=(controller, evidence),
                ),
                patch.object(
                    qualification_composition,
                    "verify_v32_current_codex_attempt_time_v1",
                ),
                patch.object(qualification_composition, "_assert_namespace"),
                patch.object(
                    qualification_composition,
                    "assert_v32_qualification_runtime_root_components_v1",
                    return_value={},
                ),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], patch.object(
                qualification_composition,
                "build_v32_system_clock_v1",
                side_effect=AssertionError(
                    "DELIVERED replay must reuse the first delivered_at"
                ),
            ):
                replayed = qualification_composition.submit_v32_qualification_agent_delivery_v1(
                    target_run_id=authority["target_run_id"],
                    qualification_run_id=run_id,
                    stage="PROPOSAL",
                    expected_request_digest=claimed["request"][
                        REQUEST_DIGEST_FIELD
                    ],
                    expected_current_codex_presentation_digest=presentation[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ],
                    payload_utf8="different retry payload must not overwrite",
                )
            json_after = tuple(
                (path.relative_to(project).as_posix(), path.read_bytes())
                for path in sorted(project.rglob("*.json"))
            )
            self.assertEqual(first, replayed)
            self.assertEqual(json_before, json_after)
            self.assertEqual(
                "2026-08-07T00:16:20Z",
                replayed["agent_delivery"]["delivered_at"],
            )
            self.assertEqual(
                "first immutable payload",
                replayed["agent_delivery"]["payload_utf8"],
            )

    def test_qualification_delivery_recovers_both_partial_tails_without_new_clock(
        self,
    ) -> None:
        for crash_kind in ("DELIVERY_ONLY", "DELIVERY_AND_RECEIPT"):
            with self.subTest(crash_kind=crash_kind), TemporaryDirectory() as folder:
                packet = semantic_fixture.lifecycle_fixture._proposal_packet(
                    profile=V32_QUALIFICATION_CONTEXT_PROFILE
                )
                context, context_binding = semantic_fixture._context(
                    "PROPOSAL",
                    packet,
                    created_at="2026-08-07T00:16:00Z",
                )
                authority = packet["authority_document"]
                run_id = authority["run_id"]
                reservation_binding = {"semantic_digest": "a" * 64}
                controller = {
                    "capability_states": {
                        "CURRENT_CODEX": {
                            "reservation_binding": reservation_binding
                        }
                    }
                }
                evidence = Mock()
                evidence.load_attempt_reservation.return_value = {
                    "reservation": {"reserved_at": "2026-08-07T00:15:00Z"},
                    "reservation_binding": reservation_binding,
                }
                project = Path(folder)
                mailbox = LocalV32CurrentRootAgentMailbox(
                    project / "runtime/mailbox"
                )
                initial = mailbox.initialize_checkpoint(
                    mailbox_id=f"mailbox::{run_id}::1",
                    run_id=run_id,
                    cycle_index=1,
                    created_at="2026-08-07T00:16:00Z",
                )
                opened = mailbox.enqueue_request(
                    run_id=run_id,
                    cycle_index=1,
                    expected_checkpoint_digest=initial[
                        MAILBOX_CHECKPOINT_DIGEST_FIELD
                    ],
                    agent_input_context=context,
                    agent_input_context_binding=context_binding,
                    reserved_at="2026-08-07T00:16:05Z",
                )
                claimed = mailbox.claim_request(
                    run_id=run_id,
                    cycle_index=1,
                    stage="PROPOSAL",
                    expected_checkpoint_digest=opened["checkpoint"][
                        MAILBOX_CHECKPOINT_DIGEST_FIELD
                    ],
                    claimed_at="2026-08-07T00:16:10Z",
                )
                presentation = build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=claimed["checkpoint"],
                    request=claimed["request"],
                    claim=claimed["claim"],
                    lossless_context_package=None,
                    control_context={
                        "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                        "stage": "PROPOSAL",
                        "stage_status": "CLAIMED",
                        "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                    },
                )

                common_patches = (
                    patch.object(qualification_composition, "PROJECT_ROOT", project),
                    patch.object(
                        qualification_composition,
                        "_load_authority",
                        return_value=(
                            authority,
                            {"binding": "authority"},
                            {"contract": "verified"},
                            {"mailbox": "runtime/mailbox"},
                        ),
                    ),
                    patch.object(
                        qualification_composition,
                        "_replay_controller_before_agent_v1",
                        return_value=(controller, evidence),
                    ),
                    patch.object(
                        qualification_composition,
                        "verify_v32_current_codex_attempt_time_v1",
                    ),
                    patch.object(qualification_composition, "_assert_namespace"),
                    patch.object(
                        qualification_composition,
                        "assert_v32_qualification_runtime_root_components_v1",
                        return_value={},
                    ),
                )
                original_write = LocalV32CurrentRootAgentMailbox._write_document

                def crash_before_receipt(store, **kwargs):
                    if str(kwargs["relative_ref"]).endswith(
                        "delivery-receipt.json"
                    ):
                        raise V32CurrentRootAgentMailboxStoreError(
                            "injected-delivery-only-crash"
                        )
                    return original_write(store, **kwargs)

                def crash_before_checkpoint_cas(store, **kwargs):
                    del store, kwargs
                    raise V32CurrentRootAgentMailboxStoreError(
                        "injected-delivery-receipt-pre-cas-crash"
                    )

                crash_patch = (
                    patch.object(
                        LocalV32CurrentRootAgentMailbox,
                        "_write_document",
                        new=crash_before_receipt,
                    )
                    if crash_kind == "DELIVERY_ONLY"
                    else patch.object(
                        LocalV32CurrentRootAgentMailbox,
                        "_commit",
                        new=crash_before_checkpoint_cas,
                    )
                )
                with (
                    common_patches[0],
                    common_patches[1],
                    common_patches[2],
                    common_patches[3],
                    common_patches[4],
                    common_patches[5],
                    patch.object(
                        qualification_composition,
                        "build_v32_system_clock_v1",
                        return_value=lambda: "2026-08-07T00:16:20Z",
                    ),
                    crash_patch,
                    self.assertRaises(V32CurrentRootAgentMailboxStoreError),
                ):
                    qualification_composition.submit_v32_qualification_agent_delivery_v1(
                        target_run_id=authority["target_run_id"],
                        qualification_run_id=run_id,
                        stage="PROPOSAL",
                        expected_request_digest=claimed["request"][
                            REQUEST_DIGEST_FIELD
                        ],
                        expected_current_codex_presentation_digest=presentation[
                            CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                        ],
                        payload_utf8="first immutable payload",
                    )

                delivery_path = (
                    project
                    / "runtime/mailbox/v32-current-root-agent-mailbox-v1"
                    / "cycles/0001/proposal/agent-delivery.json"
                )
                receipt_path = delivery_path.with_name("delivery-receipt.json")
                first_delivery_bytes = delivery_path.read_bytes()
                first_receipt_bytes = (
                    receipt_path.read_bytes() if receipt_path.is_file() else None
                )
                with (
                    common_patches[0],
                    common_patches[1],
                    common_patches[2],
                    common_patches[3],
                    common_patches[4],
                    common_patches[5],
                    patch.object(
                        qualification_composition,
                        "build_v32_system_clock_v1",
                        side_effect=AssertionError(
                            "partial delivery recovery must not allocate a new clock"
                        ),
                    ),
                ):
                    recovered = qualification_composition.submit_v32_qualification_agent_delivery_v1(
                        target_run_id=authority["target_run_id"],
                        qualification_run_id=run_id,
                        stage="PROPOSAL",
                        expected_request_digest=claimed["request"][
                            REQUEST_DIGEST_FIELD
                        ],
                        expected_current_codex_presentation_digest=presentation[
                            CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                        ],
                        payload_utf8="retry payload must not replace first bytes",
                    )
                self.assertEqual(first_delivery_bytes, delivery_path.read_bytes())
                if first_receipt_bytes is not None:
                    self.assertEqual(first_receipt_bytes, receipt_path.read_bytes())
                self.assertEqual(
                    "2026-08-07T00:16:20Z",
                    recovered["agent_delivery"]["delivered_at"],
                )
                self.assertEqual(
                    "first immutable payload",
                    recovered["agent_delivery"]["payload_utf8"],
                )
                self.assertEqual(
                    presentation[CURRENT_CODEX_PRESENTATION_DIGEST_FIELD],
                    recovered["delivery_receipt"][
                        "current_codex_presentation_digest"
                    ],
                )

    def test_public_replay_two_external_agent_stages_final_plan_and_dedicated_probe(self):
        with TemporaryDirectory() as folder:
            project = Path(folder)
            theory_bytes = (
                Path(__file__).resolve().parents[1]
                / "theory/current/V3_2_DYNAMIC_AGGRESSIVE.md"
            ).read_bytes()
            fixture = authority_fixture.build_fixture(
                project, theory_bytes=theory_bytes
            )
            authority = fixture["qualification_authority"]
            authority_binding = fixture["qualification_authority_binding"]
            contract = fixture["contract"]
            projection = build_v32_active_authority_projection(
                run_id=authority["run_id"],
                recorded_at=authority["recorded_at"],
                experiment_contract_digest=fixture["contract_binding"][
                    "semantic_digest"
                ],
                governing_authority_binding=normalized_binding(authority_binding),
            )
            evidence = LocalV32ActualCapabilityEvidenceStore(project, "runtime/evidence")
            public_reservation = evidence.reserve_attempt(
                capability="PUBLIC_SOURCE",
                qualification_run_id=authority["run_id"],
                target_run_id=authority["target_run_id"],
                qualification_authority_digest=authority[AUTHORITY_DIGEST_FIELD],
                reserved_at="2026-08-07T00:13:59Z",
            )
            source_root = "runtime/public-source"
            admitted_root = "runtime/admitted-source"
            source_id = f"{authority['run_id']}:public-source"
            base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
            source_times = [
                iso(base + timedelta(seconds=value))
                for value in (1, 2, 4, 5, 6, 7)
            ]
            with patch.object(source_fixture, "BASE", base), patch.object(
                source_fixture,
                "SERVER_MS",
                int((base + timedelta(seconds=3)).timestamp() * 1000),
            ), patch.object(
                source_fixture,
                "candle_rows",
                side_effect=capacity_regression_candle_rows,
            ):
                transport = source_fixture.BundleTransport(source_fixture.raw_bundle())
                public = V32PublicSourceQualificationAttemptPort(
                    project_root=project,
                    evidence_store=evidence,
                    source_store_root=source_root,
                    run_store_root=admitted_root,
                    source_qualification_id=source_id,
                    active_authority_projection=projection,
                    transport=transport,
                    clock=SequenceClock(source_times),
                ).advance_once(
                    qualification_authority=authority,
                    reservation=public_reservation["reservation"],
                    reservation_binding=public_reservation["reservation_binding"],
                    resume_token=None,
                    resume_requested_at=None,
                )
            self.assertEqual(public["status"], "COMPLETE")
            self.assertEqual(transport.calls, 1)

            current_reservation = evidence.reserve_attempt(
                capability="CURRENT_CODEX",
                qualification_run_id=authority["run_id"],
                target_run_id=authority["target_run_id"],
                qualification_authority_digest=authority[AUTHORITY_DIGEST_FIELD],
                reserved_at="2026-08-07T00:14:10Z",
            )
            clock = StepClock(datetime(2026, 8, 7, 0, 14, 11, tzinfo=UTC))
            capture = PublicMarkCapture(clock)
            mailbox = LocalV32CurrentRootAgentMailbox(project / "runtime/mailbox")
            probe = LocalV32QualificationMonitorProbeStore(
                project / "runtime/probe", capture_port=capture, clock=clock
            )
            material_store = LocalV32QualificationMaterialStore(
                project, "runtime/material"
            )
            materializer = LocalV32QualificationMaterializer(
                project_root=project,
                authority_root_relative_ref=authority_fixture.AUTHORITY_ROOT,
                material_store=material_store,
                source_store=LocalV32CycleSourceAdmissionStore(project / source_root),
                admitted_source_store=LocalV32CycleSourceAdmissionStore(
                    project / admitted_root
                ),
                mailbox=mailbox,
                probe_store=probe,
                qualification_authority=authority,
                qualification_authority_binding=authority_binding,
                current_codex_attempt_reservation=current_reservation["reservation"],
                active_authority_projection=projection,
                source_qualification_id=source_id,
                clock=clock,
            )

            original_graph_builder = (
                graph_projection_module._build_evidence_dependency_closure
            )
            with patch.object(
                graph_projection_module,
                "_build_evidence_dependency_closure",
                wraps=original_graph_builder,
            ) as graph_builder:
                result = qualification_composition._advance_v32_qualification_material_burst_v1(
                    materializer
                )
                self.assertEqual("AWAITING_AGENT", result["status"])
                self.assertEqual("AGENT_REQUIRED", result["burst_stop_reason"])
                self.assertIn(
                    "QUALIFICATION_MATERIAL_PERSISTED:agent_market_graph_view",
                    result["burst_step_boundaries"],
                )
                # One build creates the projection.  The owner-bound burst
                # then verifies that exact projection once for registry and
                # market-view work; the latter must reuse the same success.
                self.assertEqual(2, graph_builder.call_count)
            boundaries = list(result["burst_step_boundaries"])
            self.assertEqual(
                "NO_ADVANCE_AWAITING_PROPOSAL",
                result["burst_step_boundaries"][-1],
            )
            self.assertEqual(
                mailbox.next_pending_request(
                    run_id=authority["run_id"], cycle_index=1
                )["stage"],
                "PROPOSAL",
            )
            self.assertEqual(0, capture.calls)
            self.assertIsNone(probe.schedule_binding_v1())

            checkpoint = mailbox.load_checkpoint(
                run_id=authority["run_id"], cycle_index=1
            )
            claim = mailbox.claim_request(
                run_id=authority["run_id"],
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                claimed_at=clock(),
            )
            proposal_chain = mailbox.load_stage_chain(
                run_id=authority["run_id"], cycle_index=1, stage="PROPOSAL"
            )
            proposal_presentation = (
                build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=claim["checkpoint"],
                    request=claim["request"],
                    claim=claim["claim"],
                    lossless_context_package=proposal_chain[
                        "lossless_context_package"
                    ],
                    control_context={
                        "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                        "stage": "PROPOSAL",
                        "stage_status": "CLAIMED",
                        "next_action": (
                            "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
                        ),
                    },
                )
            )
            proposal_context = claim["request"]["agent_input_context"]
            proposal_packet = proposal_chain["canonical_packet_original"]
            market_view = material_store.load("agent_market_graph_view")
            self.assertLessEqual(
                len(canonical_bytes(market_view)),
                MAX_AGENT_MARKET_GRAPH_VIEW_CANONICAL_BYTES,
            )
            self.assertEqual(
                market_view["canonical_payload_bytes"],
                len(canonical_bytes(market_view)),
            )
            self.assertEqual(
                {
                    "15M": 96,
                    "1H": 168,
                    "4H": 90,
                    "1D": 60,
                },
                {
                    timeframe: len(rows)
                    for timeframe, rows in market_view[
                        "closed_bar_series"
                    ].items()
                },
            )
            cycle_sixteen_capacity_shape = deepcopy(market_view)
            cycle_sixteen_capacity_shape.pop(
                "agent_market_graph_view_digest"
            )
            cycle_sixteen_capacity_shape["cycle_index"] = 16
            cycle_sixteen_capacity_shape["graph_delta_summary"] = {
                **cycle_sixteen_capacity_shape["graph_delta_summary"],
                "base_graph_revision": 15,
                "base_graph_digest": "f" * 64,
                "revision": 16,
            }
            cycle_sixteen_capacity_shape = (
                seal_v32_agent_market_graph_view_v1(
                    cycle_sixteen_capacity_shape
                )
            )
            self.assertLessEqual(
                len(canonical_bytes(cycle_sixteen_capacity_shape)),
                192 * 1024,
            )
            graph_registry = material_store.load("support_graph_registry")
            owning_closures = {
                row["evidence_digest"]: row
                for row in graph_registry["evidence_dependency_closure"]
            }
            for row in market_view["citable_evidence_records"]:
                owning = owning_closures.get(row["evidence_digest"])
                if owning is None:
                    self.assertEqual(
                        row["closure_status"], "BUNDLE_ROOT_NO_GRAPH_NODE"
                    )
                    continue
                self.assertEqual(
                    row["dependency_group_ids"],
                    owning["dependency_group_ids"],
                )
                self.assertEqual(
                    row["exact_closure_digest"],
                    owning["evidence_dependency_closure_digest"],
                )
                self.assertEqual(
                    {
                        "evidence_ref_count": len(owning["evidence_refs"]),
                        "node_id_count": len(owning["node_ids"]),
                        "association_id_count": len(owning["association_ids"]),
                        "dependency_group_id_count": len(
                            owning["dependency_group_ids"]
                        ),
                    },
                    {
                        field: row[field]
                        for field in (
                            "evidence_ref_count",
                            "node_id_count",
                            "association_id_count",
                            "dependency_group_id_count",
                        )
                    },
                )
            self.assertTrue(market_view["unknown_retained"])
            self.assertTrue(market_view["other_retained"])
            self.assertGreater(
                len(canonical_bytes(proposal_packet)), 512 * 1024
            )
            self.assertLessEqual(
                len(canonical_bytes(proposal_packet)),
                MAX_PROPOSAL_CANONICAL_PACKET_BYTES,
            )
            self.assertLessEqual(
                len(canonical_bytes(proposal_context)),
                MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
            )
            lossless = proposal_chain["lossless_context_package"]
            self.assertEqual(proposal_context["context_delivery_mode"], "INLINE")
            self.assertIsNone(lossless)
            self.assertEqual(
                proposal_packet["theory_semantic_document"]["markdown_utf8"].encode(),
                theory_bytes,
            )
            self.assertEqual(
                resolve_v32_agent_canonical_packet_v1(proposal_context),
                proposal_packet,
            )
            self.assertEqual(
                [
                    row["unit_kind"]
                    for row in proposal_context[
                        "ordered_input_delivery_units"
                    ]
                ],
                ["CANONICAL_PACKET"],
            )
            # The frozen 256 KiB compaction-policy value constrains each
            # sharded delivery unit; it is not the direct-inline input cap.
            self.assertGreater(
                len(canonical_bytes(proposal_context)),
                proposal_packet["support_documents"][
                    "context_compaction_policy"
                ]["max_agent_context_canonical_bytes"],
            )
            actual_chain = {
                "graph_registry": graph_registry,
                "pit_registry": material_store.load("support_pit_registry"),
                "analysis_bundle": material_store.load(
                    "public_market_analysis_bundle"
                ),
            }
            with patch.object(
                semantic_fixture.lifecycle_fixture,
                "_formal_market_chain",
                return_value=actual_chain,
            ):
                dynamic = semantic_fixture._market_bound_dynamic_state(
                    proposal_packet
                )
            with patch.object(
                semantic_fixture.action_fixture,
                "REENTRY_BUDGET_ID",
                f"instrument-churn::{authority['run_id']}::BTC-USDT-SWAP",
            ):
                variants = semantic_fixture._plan_variants(dynamic)
            proposal_output = build_v32_proposal_semantic_output_v1(
                proposal_input_context=proposal_context,
                current_dynamic_research_state=dynamic,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=semantic_fixture._risk_arithmetic(),
                candidate_rows=semantic_fixture._candidate_rows(
                    variants[0]["dynamic_action_plan"]
                ),
                sealed_plan_variants=variants,
                proposal_lossless_context_package=proposal_chain[
                    "lossless_context_package"
                ],
            )
            checkpoint = mailbox.load_checkpoint(
                run_id=authority["run_id"], cycle_index=1
            )
            mailbox.submit_delivery(
                run_id=authority["run_id"],
                cycle_index=1,
                stage="PROPOSAL",
                expected_checkpoint_digest=checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                current_codex_presentation_envelope=proposal_presentation,
                expected_current_codex_presentation_digest=(
                    proposal_presentation[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ]
                ),
                delivered_at=clock(),
                payload_utf8=canonical_v32_agent_semantic_json_v1(proposal_output),
            )

            while True:
                result = materializer.advance_once()
                boundaries.append(result["boundary_kind"])
                if result["status"] == "AWAITING_AGENT":
                    break
                self.assertTrue(result["state_changed"])
            pending = mailbox.next_pending_request(
                run_id=authority["run_id"], cycle_index=1
            )
            self.assertEqual(pending["stage"], "SELECTION")
            checkpoint = mailbox.load_checkpoint(
                run_id=authority["run_id"], cycle_index=1
            )
            claim = mailbox.claim_request(
                run_id=authority["run_id"],
                cycle_index=1,
                stage="SELECTION",
                expected_checkpoint_digest=checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                claimed_at=clock(),
            )
            selection_chain = mailbox.load_stage_chain(
                run_id=authority["run_id"], cycle_index=1, stage="SELECTION"
            )
            selection_presentation = (
                build_v32_current_codex_presentation_envelope_v1(
                    mailbox_checkpoint=claim["checkpoint"],
                    request=claim["request"],
                    claim=claim["claim"],
                    lossless_context_package=selection_chain[
                        "lossless_context_package"
                    ],
                    control_context={
                        "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                        "stage": "SELECTION",
                        "stage_status": "CLAIMED",
                        "next_action": (
                            "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY"
                        ),
                    },
                )
            )
            selection_context = claim["request"]["agent_input_context"]
            selection_packet = selection_chain["canonical_packet_original"]
            self.assertLessEqual(
                len(canonical_bytes(selection_packet)),
                MAX_SELECTION_CANONICAL_PACKET_BYTES,
            )
            self.assertLessEqual(
                len(canonical_bytes(selection_context)),
                MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
            )
            self.assertEqual(
                selection_context["context_delivery_mode"], "INLINE"
            )
            self.assertIsNone(
                selection_chain["lossless_context_package"]
            )
            self.assertEqual(
                resolve_v32_agent_canonical_packet_v1(selection_context),
                selection_packet,
            )
            self.assertEqual(
                [
                    row["unit_kind"]
                    for row in selection_context[
                        "ordered_input_delivery_units"
                    ]
                ],
                ["CANONICAL_PACKET"],
            )
            self.assertGreater(
                len(canonical_bytes(selection_context)),
                proposal_packet["support_documents"][
                    "context_compaction_policy"
                ]["max_agent_context_canonical_bytes"],
            )
            selection_output = build_v32_selection_semantic_output_v1(
                selection_input_context=selection_context,
                selected_candidate_id="open-short",
                selection_lossless_context_package=selection_chain[
                    "lossless_context_package"
                ],
                proposal_lossless_context_package=proposal_chain[
                    "lossless_context_package"
                ],
            )
            checkpoint = mailbox.load_checkpoint(
                run_id=authority["run_id"], cycle_index=1
            )
            mailbox.submit_delivery(
                run_id=authority["run_id"],
                cycle_index=1,
                stage="SELECTION",
                expected_checkpoint_digest=checkpoint[
                    "current_root_agent_mailbox_checkpoint_digest"
                ],
                current_codex_presentation_envelope=selection_presentation,
                expected_current_codex_presentation_digest=(
                    selection_presentation[
                        CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
                    ]
                ),
                delivered_at=clock(),
                payload_utf8=canonical_v32_agent_semantic_json_v1(selection_output),
            )

            while True:
                result = materializer.advance_once()
                boundaries.append(result["boundary_kind"])
                if result["status"] == "READY":
                    break
                self.assertTrue(result["state_changed"])
            plan = material_store.load("action_plan")
            self.assertEqual(plan["selected_candidate_id"], "open-short")
            self.assertEqual(
                proposal_context["context_profile"],
                V32_QUALIFICATION_CONTEXT_PROFILE,
            )
            self.assertEqual(
                probe.load_prefix()["schedule"]["outcome_schedule_count"], 0
            )
            self.assertEqual(probe.advance_once()["status"], "NOT_DUE")
            self.assertEqual(capture.calls, 0)

            current = V32CurrentCodexQualificationAttemptPort(
                project_root=project,
                evidence_store=evidence,
                mailbox_store_root="runtime/mailbox",
                clock=clock,
            ).advance_once(
                qualification_authority=authority,
                reservation=current_reservation["reservation"],
                reservation_binding=current_reservation["reservation_binding"],
                resume_token=None,
                resume_requested_at=None,
            )
            self.assertEqual(current["status"], "COMPLETE")
            self.assertIn("QUALIFICATION_PROPOSAL_ENQUEUED", boundaries)
            self.assertIn("QUALIFICATION_SELECTION_ENQUEUED", boundaries)
            self.assertIn(
                "QUALIFICATION_MONITOR_PROBE_SCHEDULED", boundaries
            )

if __name__ == "__main__":
    unittest.main()
