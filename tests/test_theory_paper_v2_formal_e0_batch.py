from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.formal_e0_batch import (
    FormalE0BatchError,
    FormalE0BatchRunner,
    assess_formal_transport,
    build_decision_input_package,
    parse_index_expression,
    score_generation_arm,
)
from trade_system.theory_paper_v2.application.generative_topology_run import (
    ModelTransportCapability,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.formal_e0_replay import (
    ACTION_EXIT_REENTRY,
    ACTION_OPEN_CORE,
    FormalE0ReplayError,
    account_policy_from_documents,
    initial_episode_state,
    preview_action,
    replay_action_one_hour,
)
from trade_system.theory_paper_v2.infrastructure.formal_e0_batch_store import (
    load_prepared_formal_e0_run,
    prepare_formal_e0_run,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "theory_agent_v2.formal_e0_experiment.v1.json"


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bar(index: int, start: datetime) -> dict[str, object]:
    opened = start + timedelta(hours=index)
    available = opened + timedelta(hours=1)
    price = Decimal("100") + Decimal(index) / Decimal("10")
    value = {
        "availability_basis": "PROVIDER_CLOSED_BAR_PROTOCOL",
        "availability_status": "DERIVED",
        "available_at": _iso(available),
        "bar_id": f"TESTUSDT-1h-{index:03d}",
        "captured_at": "2026-07-31T00:00:00.000Z",
        "close": str(price),
        "close_time_ms": index * 3_600_000 + 3_599_999,
        "decision_contemporaneous_reason": (
            "ARCHIVE_CAPTURE_AFTER_HISTORICAL_DECISION"
        ),
        "decision_contemporaneous_status": "UNKNOWN",
        "high": str(price + Decimal("1")),
        "interval": "1h",
        "low": str(price - Decimal("1")),
        "observed_at": _iso(available - timedelta(milliseconds=1)),
        "open": str(price),
        "open_time_ms": index * 3_600_000,
        "provider_ignored_field": "0",
        "quote_asset_volume": "100000",
        "source_raw_body_sha256": "a" * 64,
        "source_request_id": "test-klines",
        "symbol": "TESTUSDT",
        "taker_buy_base_volume": "400",
        "taker_buy_quote_volume": "40000",
        "trade_count": 1000 + index,
        "usage_scope": "COUNTERFACTUAL_MARKET_REPLAY",
        "volume": "1000",
    }
    value["bar_digest"] = canonical_digest(value)
    return value


def _slot(index: int, bars: list[dict[str, object]]) -> dict[str, object]:
    bar = bars[index]
    return self_digest(
        {
            "contemporaneous_agent_input_reason": (
                "ARCHIVE_CAPTURE_AFTER_HISTORICAL_DECISION"
            ),
            "contemporaneous_agent_input_status": "UNKNOWN",
            "decision_at": bar["available_at"],
            "interface_fields": [
                {
                    "field_name": "close",
                    "reason_code": None,
                    "status": "OBSERVED",
                    "unit": "USDT",
                    "value": bar["close"],
                },
                {
                    "field_name": "funding_rate",
                    "reason_code": "UNKNOWN_NOT_REQUESTED",
                    "status": "UNKNOWN",
                    "unit": "rate",
                    "value": None,
                },
                {
                    "field_name": "participant_psychology",
                    "reason_code": (
                        "UNKNOWN_UNIDENTIFIABLE_FROM_PUBLIC_AGGREGATES"
                    ),
                    "status": "UNKNOWN",
                    "unit": None,
                    "value": None,
                },
            ],
            "slot_id": f"TESTUSDT-decision-{index:03d}",
            "slot_index": index - 96,
            "source_raw_body_sha256": "a" * 64,
            "source_request_id": "test-klines",
            "usage_scope": "COUNTERFACTUAL_MARKET_REPLAY",
            "visible_bar_ids": [
                str(item["bar_id"]) for item in bars[: index + 1]
            ],
            "visible_through_bar_id": bar["bar_id"],
        },
        "slot_digest",
    )


def _make_bundle(root: Path) -> Path:
    bundle = root / "bundle-test-20260731"
    normalized = bundle / "normalized"
    normalized.mkdir(parents=True)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    bars = [_bar(index, start) for index in range(256)]
    dataset = {
        "bars": bars,
        "dataset_type": "HISTORICAL_COUNTERFACTUAL_REPLAY",
        "decision_indices_inclusive": [96, 191],
        "decision_slots": [_slot(index, bars) for index in range(96, 192)],
        "derived_1d_bars": [],
        "derived_4h_bars": [],
        "executable": False,
        "experiment_contract_digest": (
            "92a3ef3cfb150e6f17bbc0ded71bdb5674531effab05990084e366397344ec3a"
        ),
        "external_execution_authority": "NONE_E0",
        "forming_or_future_rows_excluded": 0,
        "interval": "1h",
        "outcome_bindings": [],
        "outcome_horizons_hours": [1, 4, 8, 24],
        "provider_id": "TEST_PROVIDER",
        "quality_receipt_digest": "b" * 64,
        "quality_receipt_id": "quality-test",
        "replay_admissibility_receipt_digest": "c" * 64,
        "replay_admissibility_receipt_id": "replay-test",
        "request_ids": ["test-klines"],
        "requested_closed_bar_count": 256,
        "server_time_ms": 1,
        "symbol": "TESTUSDT",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
    }
    payload = canonical_bytes(dataset)
    dataset_path = normalized / "dataset.json"
    dataset_path.write_bytes(payload)
    manifest = self_digest(
        {
            "artifacts": [
                {
                    "byte_length": len(payload),
                    "media_type": "application/json",
                    "relative_path": "normalized/dataset.json",
                    "sha256": canonical_digest(dataset),
                }
            ],
            "availability_basis": "PROVIDER_CLOSED_BAR_PROTOCOL",
            "availability_status": "DERIVED",
            "base_interval": "1h",
            "bundle_id": "bundle-test-20260731",
            "contemporaneous_agent_input_status": "UNKNOWN",
            "decision_indices_inclusive": [96, 191],
            "derived_timeframes": ["4h", "1d"],
            "end_time_rule": "TEST",
            "executable": False,
            "experiment_contract_digest": (
                "92a3ef3cfb150e6f17bbc0ded71bdb5674531effab05990084e366397344ec3a"
            ),
            "experiment_contract_id": "TA2-FORMAL-E0-20260731",
            "external_execution_authority": "NONE_E0",
            "instrument_type": "PERPETUAL",
            "outcome_horizons_hours": [1, 4, 8, 24],
            "permitted_usage_scope": "HISTORICAL_COUNTERFACTUAL_REPLAY",
            "physical_capture_status": "CAPTURED_NOW",
            "provider_id": "TEST_PROVIDER",
            "quality_receipt_digest": "d" * 64,
            "quality_status": "PASS",
            "raw_response_storage": "WRITE_ONCE_EXACT_BYTES",
            "replay_admissibility_receipt_digest": "e" * 64,
            "replay_admissibility_status": "PASS",
            "requested_closed_bar_count": 256,
            "schema_id": "theory_agent_v2_fresh_market_bundle",
            "schema_version": "1.0.0",
            "source_base_url": "https://example.invalid",
            "symbol": "TESTUSDT",
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        },
        "manifest_digest",
    )
    write_once_json(bundle / "manifest.json", manifest)
    return bundle


class _NoGoPort:
    def capability(self) -> ModelTransportCapability:
        return ModelTransportCapability(
            adapter_id="test-no-go",
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
            hard_token_limit_available=False,
            served_model_attestation_available=False,
            reason_codes=("HARD_CAP_UNKNOWN",),
        )

    def invoke(self, request):  # pragma: no cover - must never be reached
        raise AssertionError("NO_GO preflight must prevent model invocation")


class FormalE0BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = _make_bundle(self.root)
        self.prepared = prepare_formal_e0_run(
            runtime_root=self.root / "runs",
            run_id="formal-e0-test-20260731",
            formal_contract_path=CONTRACT,
            dataset_bundle_root=self.bundle,
            frozen_at="2026-07-31T10:00:00Z",
        )
        self.account = account_policy_from_documents(
            load_json_strict(self.prepared.initial_account_path),
            load_json_strict(self.prepared.cost_policy_path),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_policies_are_frozen_and_bound_before_any_session(self) -> None:
        loaded = load_prepared_formal_e0_run(self.prepared.run_root)
        self.assertEqual(
            self.prepared.run_bindings_digest,
            loaded.run_bindings_digest,
        )
        bindings = load_json_strict(loaded.run_bindings_path)
        self.assertTrue(bindings["served_model_attestation_required"])
        self.assertTrue(
            bindings["hard_generation_limit_mechanism_required"]
        )
        self.assertFalse((loaded.run_root / "sessions").exists())

    def test_role_input_contains_only_slot_visible_bars_and_typed_unknowns(self):
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        current = runner.dataset.current_bar(160)
        state = initial_episode_state(
            cohort="FORMAL_EXPERIMENT",
            first_mark=Decimal(str(current["close"])),
            account=self.account,
            episode_id="formal-genesis",
        )
        package = build_decision_input_package(
            prepared=self.prepared,
            dataset=runner.dataset,
            state=state,
            sample_index=160,
            account=self.account,
        )
        context = package.context_document
        visible = context["market"]["visible_bars"]
        self.assertEqual("ORDERED_FIELDS_AND_ROWS_V1", visible["encoding"])
        self.assertEqual(96, visible["row_count"])
        self.assertEqual(96, len(visible["rows"]))
        self.assertNotIn("source_raw_body_sha256", visible["fields"])
        self.assertEqual(
            161, context["pit_authority"]["slot_visible_bar_count"]
        )
        self.assertEqual(
            96, context["pit_authority"]["projected_1h_bar_count"]
        )
        self.assertEqual(
            65,
            context["pit_authority"][
                "earlier_visible_not_projected_count"
            ],
        )
        self.assertEqual(
            "FROZEN_ROLLING_WARMUP_LIMIT_96_BARS",
            context["pit_authority"][
                "earlier_visible_not_projected_reason"
            ],
        )
        self.assertEqual(
            current["bar_id"],
            context["pit_authority"]["role_visible_through_bar_id"],
        )
        self.assertEqual(
            0, context["pit_authority"]["future_visibility_count"]
        )
        context_bytes = canonical_bytes(context)
        self.assertNotIn(b"outcome_bindings", context_bytes)
        self.assertNotIn(
            str(runner.dataset.next_bar(160)["bar_id"]).encode(),
            context_bytes,
        )
        self.assertTrue(
            all(item["value"] is None for item in context["typed_unknowns"])
        )
        self.assertEqual(
            "GENESIS",
            context["prior_accepted_analysis"]["continuity_kind"],
        )

    def test_exit_with_surviving_thesis_atomically_opens_reentry(self) -> None:
        bar0 = _bar(160, datetime(2026, 7, 1, tzinfo=UTC))
        bar1 = _bar(161, datetime(2026, 7, 1, tzinfo=UTC))
        bar2 = _bar(162, datetime(2026, 7, 1, tzinfo=UTC))
        state = initial_episode_state(
            cohort="FORMAL_EXPERIMENT",
            first_mark=Decimal(str(bar0["close"])),
            account=self.account,
            episode_id="formal-genesis",
        )
        opened = replay_action_one_hour(
            state,
            selected_action_id=ACTION_OPEN_CORE,
            sample_index=160,
            current_bar=bar0,
            next_bar=bar1,
            account=self.account,
            control_mode="MODEL_SELECTED",
        )
        self.assertEqual(Decimal("0.5"), opened.primary_path_capture)
        exited = replay_action_one_hour(
            opened.state_after,
            selected_action_id=ACTION_EXIT_REENTRY,
            sample_index=161,
            current_bar=bar1,
            next_bar=bar2,
            account=self.account,
            control_mode="MODEL_SELECTED",
        )
        self.assertEqual("FLAT", exited.state_after.position_state)
        self.assertEqual("ACTIVE", exited.state_after.thesis_status)
        self.assertEqual("OPEN", exited.state_after.reentry_status)
        self.assertTrue(exited.preview.reentry_symmetry_valid)

    def test_non_exact_action_is_not_allowed_to_mutate_state(self) -> None:
        state = initial_episode_state(
            cohort="FORMAL_EXPERIMENT",
            first_mark=Decimal("100"),
            account=self.account,
            episode_id="formal-genesis",
        )
        preview = preview_action(
            state,
            selected_action_id="open a small core position",
            current_mark=Decimal("100"),
            account=self.account,
        )
        self.assertFalse(preview.admitted)
        self.assertIn(
            "SELECTED_ACTION_NOT_EXACT_FEASIBLE_ID",
            preview.error_codes,
        )

    def test_transport_unknown_model_and_hard_cap_fail_closed_pre_call(self):
        receipt = assess_formal_transport(
            prepared=self.prepared,
            model_port=_NoGoPort(),
        )
        self.assertEqual("NO_GO", receipt["status"])
        self.assertIn(
            "SERVED_MODEL_ATTESTATION_UNAVAILABLE",
            receipt["reason_codes"],
        )
        self.assertIn(
            "HARD_GENERATION_LIMIT_UNVERIFIED",
            receipt["reason_codes"],
        )
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        with self.assertRaisesRegex(
            ValueError, "FORMAL_GENERATIVE_CALL_NO_GO"
        ):
            runner.run_selection(indices=(96,), concurrency=1)
        self.assertFalse((self.prepared.run_root / "sessions").exists())

    def test_scorer_reads_archived_wrappers_and_requires_exact_action(self):
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        current = runner.dataset.current_bar(96)
        state = initial_episode_state(
            cohort="TOPOLOGY_SELECTION",
            first_mark=Decimal(str(current["close"])),
            account=self.account,
            episode_id="selection-reference",
        )
        package = build_decision_input_package(
            prepared=self.prepared,
            dataset=runner.dataset,
            state=state,
            sample_index=96,
            account=self.account,
        )
        session = self.root / "scoring-session"
        topology = "CLUSTER_POST_PROPOSAL"
        common_bytes = b'{"common":"context"}'
        common_path = (
            session / "shared" / "byte-identical-common-context.json"
        )
        common_path.parent.mkdir(parents=True)
        common_path.write_bytes(common_bytes)
        common_digest = hashlib.sha256(common_bytes).hexdigest()
        phases = ("PROPOSE", "CHALLENGE_POST", "SELECT")
        payloads = (
            {
                "primary_path": "up",
                "alternative_paths": ["range"],
                "null_path": "no edge",
                "other_or_unknown_path": "unknown",
                "challenge_claims": [],
                "selected_action": None,
            },
            {
                "primary_path": None,
                "alternative_paths": [],
                "null_path": None,
                "other_or_unknown_path": None,
                "challenge_claims": [
                    {"category": name, "summary": name}
                    for name in (
                        "STATE_CONTINUITY",
                        "TIME_SCALE_OVERREACH",
                        "EXIT_REENTRY_ASYMMETRY",
                        "UNKNOWN_COERCION",
                        "ACTION_SPACE_COLLAPSE",
                        "ROLE_OVERREACH",
                    )
                ],
                "selected_action": None,
            },
            {
                "primary_path": "up",
                "alternative_paths": ["range"],
                "null_path": "no edge",
                "other_or_unknown_path": "unknown",
                "challenge_claims": [],
                "selected_action": ACTION_OPEN_CORE,
            },
        )
        turns = []
        for ordinal, (phase, semantic) in enumerate(zip(phases, payloads)):
            turn_root = (
                session
                / "arms"
                / topology
                / f"turn-{ordinal:02d}-{phase.lower()}"
            )
            provider_bytes = f"provider-{ordinal}".encode()
            provider_path = turn_root / "provider-input.bin"
            provider_path.parent.mkdir(parents=True)
            provider_path.write_bytes(provider_bytes)
            digest = hashlib.sha256(provider_bytes).hexdigest()
            raw_event_bytes = f"event-{ordinal}".encode()
            raw_stderr_bytes = b""
            raw_output_bytes = canonical_bytes(semantic)
            attempt_root = turn_root / "attempt-00"
            attempt_root.mkdir()
            (attempt_root / "raw-events.jsonl").write_bytes(
                raw_event_bytes
            )
            (attempt_root / "raw-stderr.bin").write_bytes(
                raw_stderr_bytes
            )
            (attempt_root / "raw-output.bin").write_bytes(
                raw_output_bytes
            )
            wrapper = self_digest(
                {
                    "schema_id": "deterministic_semantic_agent_envelope",
                    "schema_version": "1.0.0",
                    "source_input_digest": digest,
                    "semantic_payload": semantic,
                },
                "record_digest",
            )
            path = (
                turn_root
                / "deterministic-wrapper.json"
            )
            wrapper_bytes = canonical_bytes(wrapper)
            path.write_bytes(wrapper_bytes)
            turns.append(
                {
                    "turn_ordinal": ordinal,
                    "phase_id": phase,
                    "status": "COMPLETE",
                    "provider_input_digest": digest,
                    "raw_event_digest": hashlib.sha256(
                        raw_event_bytes
                    ).hexdigest(),
                    "raw_stderr_digest": hashlib.sha256(
                        raw_stderr_bytes
                    ).hexdigest(),
                    "raw_output_digest": hashlib.sha256(
                        raw_output_bytes
                    ).hexdigest(),
                    "deterministic_wrapper_digest": hashlib.sha256(
                        wrapper_bytes
                    ).hexdigest(),
                }
            )
        arm = {
            "topology_id": topology,
            "status": "COMPLETE",
            "turn_receipts": turns,
            "common_context_digest": common_digest,
            "raw_input_ref": (
                "paired-generative-run:test:shared/"
                f"byte-identical-common-context.json:{common_digest}"
            ),
        }
        generation = self_digest(
            {
                "schema_id": "paired_generative_topology_run_receipt",
                "schema_version": "1.0.0",
                "arm_receipts": [arm],
                "common_context_digest": common_digest,
            },
            "receipt_digest",
        )
        score = score_generation_arm(
            session_root=session,
            generation_receipt=generation,
            topology_id=topology,
            package=package,
            account=self.account,
        )
        self.assertEqual(ACTION_OPEN_CORE, score.selected_action_id)
        self.assertEqual(Decimal("1"), score.dynamic_candidate_coverage)
        self.assertEqual(Decimal("1"), score.material_challenge_coverage)
        self.assertEqual(Decimal("1"), score.action_quality_score)
        self.assertEqual(0, score.hard_constraint_error_count)
        self.assertEqual(0, score.reproducibility_difference_count)

    def test_three_cohorts_have_independent_genesis(self) -> None:
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        (
            qualification,
            qualification_baseline,
            qualification_continuity,
        ) = runner._load_prior_states(
            cohort="POLICY_QUALIFICATION", sample_index=128
        )
        formal, formal_baseline, formal_continuity = (
            runner._load_prior_states(
            cohort="FORMAL_EXPERIMENT", sample_index=160
            )
        )
        self.assertIsNone(qualification_baseline)
        self.assertIsNotNone(formal_baseline)
        self.assertNotEqual(
            qualification.prior_accepted_head,
            formal.prior_accepted_head,
        )
        self.assertEqual(Decimal("0"), qualification.quantity)
        self.assertEqual(Decimal("0"), formal.quantity)
        self.assertEqual(Decimal("0"), formal.realized_pnl_before_cost)
        self.assertEqual(
            "GENESIS", qualification_continuity["continuity_kind"]
        )
        self.assertEqual("GENESIS", formal_continuity["continuity_kind"])

    def test_selection_reference_handoff_is_bound_and_breaks_closed(self):
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        packages = runner._selection_reference_packages()
        package = packages[97][0]
        continuity = package.context_document["prior_accepted_analysis"]
        self.assertEqual(
            "PRE_FROZEN_SELECTION_REFERENCE",
            continuity["continuity_kind"],
        )
        self.assertEqual(
            package.state.prior_accepted_head,
            continuity["previous_transition_head"],
        )
        bad_payload = {
            key: value
            for key, value in continuity.items()
            if key != "continuity_digest"
        }
        bad_payload["previous_transition_head"] = "f" * 64
        broken = self_digest(bad_payload, "continuity_digest")
        with self.assertRaisesRegex(
            FormalE0BatchError, "PRIOR_ANALYSIS_CHAIN_BROKEN"
        ):
            build_decision_input_package(
                prepared=self.prepared,
                dataset=runner.dataset,
                state=package.state,
                sample_index=97,
                account=self.account,
                continuity_evidence=broken,
            )

    def test_continuity_field_injection_fails_closed(self) -> None:
        runner = FormalE0BatchRunner(
            prepared_run_root=self.prepared.run_root,
            model_port=_NoGoPort(),
        )
        current = runner.dataset.current_bar(160)
        state = initial_episode_state(
            cohort="FORMAL_EXPERIMENT",
            first_mark=Decimal(str(current["close"])),
            account=self.account,
            episode_id="formal-genesis",
        )
        first = build_decision_input_package(
            prepared=self.prepared,
            dataset=runner.dataset,
            state=state,
            sample_index=160,
            account=self.account,
        )
        payload = {
            key: value
            for key, value in first.context_document[
                "prior_accepted_analysis"
            ].items()
            if key != "continuity_digest"
        }
        payload["future_market_override"] = "FORBIDDEN"
        injected = self_digest(payload, "continuity_digest")
        with self.assertRaisesRegex(
            FormalE0BatchError, "PRIOR_ANALYSIS_FIELD_SET_INVALID"
        ):
            build_decision_input_package(
                prepared=self.prepared,
                dataset=runner.dataset,
                state=state,
                sample_index=160,
                account=self.account,
                continuity_evidence=injected,
            )

    def test_index_expression_is_bounded_to_selected_cohort(self) -> None:
        self.assertEqual(
            (96, 97, 101),
            parse_index_expression(
                "96-97,101", cohort="TOPOLOGY_SELECTION"
            ),
        )
        with self.assertRaisesRegex(ValueError, "INDEX_EXPRESSION_INVALID"):
            parse_index_expression(
                "95-96", cohort="TOPOLOGY_SELECTION"
            )


if __name__ == "__main__":
    unittest.main()
