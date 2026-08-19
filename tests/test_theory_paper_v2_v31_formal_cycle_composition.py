from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_theory_paper_v2_v31_cycle_source_admission import (
    _accept_cycle_one,
    _admit_cycle_one,
    _prior_open_interest_digest,
    _sealed_source,
)
from tests.test_theory_paper_v2_v31_semantic_compiler import _envelope
from trade_system.theory_paper_v2.application.v31_agent_transport import (
    initialize_v31_agent_transport,
    run_v31_authoring_compilation,
    run_v31_authoring_transport,
    run_v31_selection_transport,
)
from trade_system.theory_paper_v2.application.v31_cycle_source_admission import (
    admit_fresh_v31_source_to_authorized_cycle,
)
from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    v31_cycle_authoring_head_bindings,
)
from trade_system.theory_paper_v2.application.v31_formal_cycle import (
    ABSOLUTE_MARK_PRICE_OBSERVABLE,
    V31FormalCycleCompositionError,
    complete_v31_formal_authoring_cycle,
    prepare_v31_formal_authoring_cycle,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    seal_action_selection,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v31_cycle_authoring import (
    validate_v31_agent_open_analysis_envelope,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
)
from trade_system.theory_paper_v2.infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_monitor_store import (
    LocalV31MonitorStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_semantic_compiler import (
    LocalV31SemanticCompiler,
)
from trade_system.theory_paper_v2.presentation.v31_formal_cycle_composition import (
    prepare_local_v31_formal_cycle,
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stage_times(moment: datetime) -> dict[str, str]:
    return {
        "reserved_at": _iso(moment),
        "requested_at": _iso(moment + timedelta(seconds=1)),
        "claimed_at": _iso(moment + timedelta(seconds=2)),
        "delivered_at": _iso(moment + timedelta(seconds=3)),
        "consumed_at": _iso(moment + timedelta(seconds=4)),
    }


def _absolute_rules() -> tuple[FrozenMonitorRule, ...]:
    return (
        FrozenMonitorRule(
            rule_id="absolute-confirmation",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
            operator=MonitorOperator.GT,
            expected="65000",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="absolute-contradiction",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
            operator=MonitorOperator.LT,
            expected="64500",
            unit="USDT_PER_BTC",
        ),
        FrozenMonitorRule(
            rule_id="absolute-falsifier",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
            operator=MonitorOperator.LTE,
            expected="64000",
            unit="USDT_PER_BTC",
        ),
    )


class V31FormalCycleCompositionTests(unittest.TestCase):
    def test_presentation_prepare_initializes_cursor_without_agent_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store, _source_store, _admission = (
                _admit_cycle_one(root)
            )
            with patch(
                "trade_system.theory_paper_v2.presentation."
                "v31_formal_cycle_composition."
                "load_v31_active_authorization_chain",
                return_value=active_chain,
            ):
                prepared = prepare_local_v31_formal_cycle(
                    project_root=root / "project",
                    run_root=run_store.run_root,
                    transport_created_at="2026-08-06T17:02:10Z",
                    owner_id="presentation-formal-initializer",
                    lease_expires_at="2026-08-06T17:02:40Z",
                )
            self.assertEqual("READY_FOR_PROPOSAL", prepared["transport_checkpoint"]["status"])
            self.assertFalse(prepared["agent_invoked"])
            self.assertFalse(prepared["outcome_collection_performed"])

    def test_cycle_one_packet_is_checkpoint_and_source_derived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            active_chain, run_store, _source_store, admission = (
                _admit_cycle_one(Path(directory))
            )
            prepared = prepare_v31_formal_authoring_cycle(
                store=run_store, active_chain=active_chain
            )

            self.assertEqual(
                "FORMAL_AUTHORING_PACKET_READY_NOT_INVOKED",
                prepared["status"],
            )
            self.assertEqual(1, prepared["cycle_index"])
            self.assertEqual(
                admission["cycle_source_admission_binding"],
                prepared["authoring_packet"][
                    "cycle_source_admission_binding"
                ],
            )
            self.assertTrue(
                all(
                    value is None
                    for value in prepared["authoring_packet"][
                        "previous_head_bindings"
                    ].values()
                )
            )
            self.assertEqual(
                "RESEARCH_CHECKPOINT_ONLY", prepared["previous_heads_source"]
            )
            self.assertFalse(prepared["executable"])

    def test_cycle_two_packet_uses_all_eight_checkpoint_heads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                active_chain,
                run_store,
                _cycle_one_source,
                first_admission,
                expected_heads,
            ) = _accept_cycle_one(root)
            run_id = str(active_chain["authority"]["authorized_run_id"])
            second_source = _sealed_source(
                root / "qualification-cycle2-formal-composition",
                qualification_id=(
                    "v31-source-qualification-formal-composition-cycle2"
                ),
                capture_start=datetime(2026, 8, 6, 18, 0, tzinfo=UTC),
                server_shift_hours=1,
                workflow_time="2026-08-06T18:01:00Z",
            )
            admit_fresh_v31_source_to_authorized_cycle(
                source_store=second_source,
                run_store=run_store,
                active_chain=active_chain,
                qualification_id=(
                    "v31-source-qualification-formal-composition-cycle2"
                ),
                run_id=run_id,
                cycle_index=2,
                admitted_at="2026-08-06T18:02:00Z",
                previous_cycle_source_admission_binding=first_admission[
                    "cycle_source_admission_binding"
                ],
                prior_snapshot_binding=first_admission[
                    "authoring_source_bindings"
                ]["market_snapshot_binding"],
                prior_open_interest_datum_digest=_prior_open_interest_digest(
                    run_store, first_admission
                ),
            )

            prepared = prepare_v31_formal_authoring_cycle(
                store=run_store, active_chain=active_chain
            )
            checkpoint_heads = v31_cycle_authoring_head_bindings(
                store=run_store, run_id=run_id, cycle_index=1
            )

            self.assertEqual(2, prepared["cycle_index"])
            self.assertEqual(expected_heads, checkpoint_heads)
            self.assertEqual(
                checkpoint_heads,
                prepared["authoring_packet"]["previous_head_bindings"],
            )
            self.assertEqual(8, len(checkpoint_heads))

    def test_completed_transport_becomes_six_objects_and_absolute_monitor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store, _source_store, admission = (
                _admit_cycle_one(root)
            )
            prepared = prepare_v31_formal_authoring_cycle(
                store=run_store, active_chain=active_chain
            )
            packet = prepared["authoring_packet"]
            packet_binding = prepared["authoring_packet_binding"]
            decision = datetime.fromisoformat(
                str(packet["decision_at"]).replace("Z", "+00:00")
            )
            review_at = _iso(decision + timedelta(hours=1))
            expiry_at = _iso(decision + timedelta(hours=2))
            sources = admission["authoring_source_bindings"]
            dataset = run_store.read_document(
                relative_ref=str(sources["pit_dataset_binding"]["relative_ref"]),
                digest_field="dataset_digest",
                expected_semantic_digest=str(
                    sources["pit_dataset_binding"]["semantic_digest"]
                ),
            )
            mark = next(
                row for row in dataset["data"] if row["metric"] == "mark-price"
            )
            with (
                patch(
                    "tests.test_theory_paper_v2_v31_semantic_compiler.REVIEW_AT",
                    review_at,
                ),
                patch(
                    "tests.test_theory_paper_v2_v31_semantic_compiler.EXPIRY_AT",
                    expiry_at,
                ),
            ):
                envelope = copy.deepcopy(
                    _envelope(packet, dataset, str(mark["datum_id"]))
                )
            envelope.pop("agent_authoring_envelope_digest")
            for delta in envelope["expectation_deltas"]:
                expectation = delta["expectation"]
                if expectation["expectation_id"] == "expectation:lead":
                    for field in (
                        "expected_observations",
                        "falsifying_observations",
                    ):
                        expectation[field][0][
                            "metric"
                        ] = ABSOLUTE_MARK_PRICE_OBSERVABLE
            for path in envelope["scenario_path_set_spec"]["paths"]:
                path["probability_cloud_refs"] = [
                    f"cloud:{packet['run_id']}:0001"
                ]
                if path["path_id"] == envelope["scenario_path_set_spec"][
                    "lead_path_id"
                ]:
                    path["expectations"][0][
                        "observable_ref"
                    ] = ABSOLUTE_MARK_PRICE_OBSERVABLE
            envelope = self_digest(
                envelope, "agent_authoring_envelope_digest"
            )
            validate_v31_agent_open_analysis_envelope(
                envelope, authoring_packet=packet
            )

            transport = LocalV31AgentTransportStore(run_store.run_root)
            initialize_v31_agent_transport(
                store=transport,
                run_id=str(packet["run_id"]),
                cycle_index=1,
                created_at=_iso(decision + timedelta(minutes=1)),
                owner_id="formal-composition-initializer",
                lease_expires_at=_iso(decision + timedelta(minutes=1, seconds=30)),
            )
            run_v31_authoring_transport(
                store=transport,
                run_id=str(packet["run_id"]),
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                owner_id="formal-composition-author",
                lease_acquired_at=_iso(decision + timedelta(minutes=2)),
                lease_expires_at=_iso(decision + timedelta(minutes=2, seconds=30)),
                stage_times=_stage_times(decision + timedelta(minutes=2)),
                agent_call=lambda _request: envelope,
            )
            compiled = run_v31_authoring_compilation(
                store=transport,
                run_id=str(packet["run_id"]),
                cycle_index=1,
                authoring_packet_binding=packet_binding,
                compiled_at=_iso(decision + timedelta(minutes=3)),
                compiler=LocalV31SemanticCompiler(store=transport),
                owner_id="formal-composition-compiler",
                lease_acquired_at=_iso(decision + timedelta(minutes=3)),
                lease_expires_at=_iso(decision + timedelta(minutes=3, seconds=30)),
            )
            evaluation = transport.read_bound_document(
                compiled["action_evaluation_binding"]
            )
            wait = next(
                row for row in evaluation["candidates"] if row["action"] == "WAIT"
            )
            selected_at = _iso(decision + timedelta(minutes=4, seconds=2))

            def select(_request):
                return seal_action_selection(
                    evaluation=evaluation,
                    selected_candidate_id=wait["candidate_id"],
                    reason="Uncalibrated conflict keeps WAIT reversible.",
                    alternative_explanations={
                        row["candidate_id"]: "The competing path remains possible."
                        for row in evaluation["candidates"]
                        if row["candidate_id"] != wait["candidate_id"]
                    },
                    failure_conditions=(
                        "The admitted absolute-price thesis is invalidated.",
                    ),
                    next_review_at=wait["next_review_at"],
                    selected_at=selected_at,
                )

            run_v31_selection_transport(
                store=transport,
                run_id=str(packet["run_id"]),
                cycle_index=1,
                preselection_binding=compiled["preselection_binding"],
                action_evaluation_binding=compiled[
                    "action_evaluation_binding"
                ],
                owner_id="formal-composition-selector",
                lease_acquired_at=_iso(decision + timedelta(minutes=4)),
                lease_expires_at=_iso(decision + timedelta(minutes=4, seconds=30)),
                stage_times=_stage_times(decision + timedelta(minutes=4)),
                agent_call=select,
            )
            completed_at = _iso(decision + timedelta(minutes=5))
            recorded_at = _iso(decision + timedelta(minutes=6))
            result = complete_v31_formal_authoring_cycle(
                research_store=LocalV31ResearchStore(run_store.run_root),
                transport_store=LocalV31AgentTransportStore(run_store.run_root),
                monitor_store=LocalV31MonitorStore(run_store.run_root),
                active_chain=active_chain,
                completed_at=completed_at,
                recorded_at=recorded_at,
                monitor_runtime_created_at=_iso(
                    decision + timedelta(seconds=1)
                ),
                monitor_rules=_absolute_rules(),
            )

            self.assertEqual(
                "FORMAL_CYCLE_ACCEPTED_MONITOR_SCHEDULED", result["status"]
            )
            self.assertEqual(6, len(result["documents"]))
            self.assertEqual(
                "metric:mark-price-usdt",
                result["monitor_plan"]["observable"]["observable_ref"],
            )
            self.assertEqual(
                {"USDT_PER_BTC"},
                {row["unit"] for row in result["monitor_plan"]["rules"]},
            )
            self.assertFalse(result["return_or_change_inferred"])
            self.assertFalse(result["unknown_zero_imputed"])
            self.assertFalse(result["outcome_collection_performed"])
            self.assertEqual(
                1, len(result["monitor_checkpoint"]["plan_bindings"])
            )
            self.assertEqual(
                1, result["research_checkpoint"]["completed_cycles"]
            )
            self.assertFalse(result["executable"])

    def test_percentage_monitor_rule_fails_before_any_terminal_replay(self) -> None:
        invalid = list(_absolute_rules())
        invalid[0] = FrozenMonitorRule(
            rule_id="percentage-is-not-an-absolute-mark",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
            operator=MonitorOperator.GT,
            expected="1",
            unit="PERCENT",
        )
        with self.assertRaisesRegex(
            V31FormalCycleCompositionError,
            "V31_FORMAL_MONITOR_ABSOLUTE_MARK_RULE_REQUIRED",
        ):
            # This focused preflight has no store side effect and is reached by
            # the public completion function before terminal replay.
            from trade_system.theory_paper_v2.application.v31_formal_cycle import (
                _absolute_monitor_rules,
            )

            _absolute_monitor_rules(invalid)


if __name__ == "__main__":
    unittest.main()
