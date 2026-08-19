from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from tests.test_theory_paper_v2_v31_authorization import _make_chain
from tests.test_theory_paper_v2_v31_source_qualification import (
    _NoNetworkOkxTransport,
)
from tests.test_theory_paper_v2_v31_semantic_compiler import (
    _candidate,
    _envelope,
    _expectation,
    _hypothesis,
    _path,
    _reseal_envelope,
)
from trade_system.theory_paper_v2.application.v31_cycle_authoring import (
    V31CycleAuthoringWorkflowError,
    compile_v31_agent_open_analysis,
)
from trade_system.theory_paper_v2.application.v31_cycle_source_admission import (
    V31CycleSourceAdmissionWorkflowError,
    admit_fresh_v31_source_to_authorized_cycle,
    verify_durable_v31_cycle_source_admission,
)
from trade_system.theory_paper_v2.application.v31_run_genesis import (
    initialize_v31_run_genesis,
)
from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    persist_completed_v31_cycle,
    v31_cycle_authoring_head_bindings,
)
from trade_system.theory_paper_v2.application.v31_research_cycle import (
    complete_v31_research_cycle,
    select_v31_cycle_action,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    seal_action_selection,
)
from trade_system.theory_paper_v2.domain.v31_cycle_authoring import (
    seal_v31_agent_open_analysis_envelope,
    seal_v31_proposal_authoring_packet,
)
from trade_system.theory_paper_v2.application.v31_source_qualification import (
    execute_v31_source_qualification,
    initialize_v31_source_qualification,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.market_knowledge_graph import (
    apply_graph_delta,
)
from trade_system.theory_paper_v2.domain.v31_cycle_source_admission import (
    cycle_source_admission_ref,
)
from trade_system.theory_paper_v2.domain.v31_source_qualification import (
    APPROVED_V31_THEORY_SHA256,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.okx_public import (
    OkxPublicFreshCollector,
)
from trade_system.theory_paper_v2.infrastructure.fresh_market.binance_usdm import (
    HttpCapture,
)
from trade_system.theory_paper_v2.infrastructure.native_market_collector import (
    OkxNativeMarketCollector,
)
from trade_system.theory_paper_v2.infrastructure.v31_market_adapter import (
    adapt_native_public_snapshot,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)
from trade_system.theory_paper_v2.infrastructure.v31_semantic_compiler import (
    LocalV31SemanticCompiler,
)
from trade_system.theory_paper_v2.infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)


class _LaterClock:
    def __init__(self, at: datetime) -> None:
        self.current = at

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(milliseconds=250)
        return value


class _ShiftedNoNetworkOkxTransport:
    """Reuse the sealed no-network fixture while shifting source market time."""

    def __init__(self, *, clock: _LaterClock, shift_hours: int) -> None:
        self.delegate = _NoNetworkOkxTransport(clock=clock)
        self.shift_ms = shift_hours * 3_600_000

    def get(self, url: str, timeout: float) -> HttpCapture:
        capture = self.delegate.get(url, timeout)
        if self.shift_ms == 0:
            return capture
        payload = json.loads(capture.body)
        path = urlsplit(url).path
        if path == "/api/v5/public/time":
            payload["data"][0]["ts"] = str(
                int(payload["data"][0]["ts"]) + self.shift_ms
            )
        elif path in {"/api/v5/market/ticker", "/api/v5/public/mark-price"}:
            payload["data"][0]["ts"] = str(
                int(payload["data"][0]["ts"]) + self.shift_ms
            )
        elif path == "/api/v5/market/history-candles":
            for row in payload["data"]:
                row[0] = str(int(row[0]) + self.shift_ms)
        return HttpCapture(
            status=capture.status,
            headers=capture.headers,
            body=json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
            received_at=capture.received_at,
            final_url=capture.final_url,
        )


def _initialize_chain_and_run(root: Path) -> tuple[dict[str, Any], LocalV31ResearchStore]:
    project = root / "project"
    project.mkdir()
    chain = _make_chain(project)
    documents = {
        "theory_approval": chain["approval"],
        "experiment_contract": chain["experiment_contract"],
        "experiment_manifest": chain["manifest"],
        "experiment_authorization": chain["authorization_receipt"],
        "current_authority": chain["authority"],
    }
    authority = chain["authority"]
    current_path = V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    current_raw = (project / current_path).read_bytes()
    global_bindings = {
        "theory_approval": authority["theory_approval_binding"],
        "experiment_contract": authority["experiment_contract_binding"],
        "experiment_manifest": authority["manifest_binding"],
        "experiment_authorization": authority["authorization_receipt_binding"],
        "current_authority": {
            "path": current_path,
            "schema_id": authority["schema_id"],
            "digest_field": "authority_digest",
            "semantic_digest": authority["authority_digest"],
            "physical_sha256": hashlib.sha256(current_raw).hexdigest(),
        },
    }
    global_raw_bytes = {
        role: (project / binding["path"]).read_bytes()
        for role, binding in global_bindings.items()
    }
    run_store = LocalV31ResearchStore(root / "run")
    initialize_v31_run_genesis(
        store=run_store,
        created_at="2026-08-06T16:20:00Z",
        documents=documents,
        global_bindings=global_bindings,
        global_raw_bytes=global_raw_bytes,
    )
    active_chain = {
        "theory_approval": chain["approval"],
        "experiment_contract": chain["experiment_contract"],
        "manifest": chain["manifest"],
        "authorization_receipt": chain["authorization_receipt"],
        "authority": chain["authority"],
    }
    return active_chain, run_store


def _sealed_source(
    root: Path,
    *,
    qualification_id: str,
    capture_start: datetime,
    server_shift_hours: int = 0,
    workflow_time: str = "2026-08-06T17:01:00Z",
) -> LocalV31SourceQualificationStore:
    store = LocalV31SourceQualificationStore(root)
    initialize_v31_source_qualification(
        store=store,
        qualification_id=qualification_id,
        created_at="2026-08-06T16:17:00Z",
        theory_sha256=APPROVED_V31_THEORY_SHA256,
    )
    transport_clock = _LaterClock(capture_start)
    collector = OkxNativeMarketCollector(
        collector=OkxPublicFreshCollector(
            transport=_ShiftedNoNetworkOkxTransport(
                clock=transport_clock, shift_hours=server_shift_hours
            ),
            clock=transport_clock,
            timeout=15.0,
        )
    )
    execute_v31_source_qualification(
        store=store,
        qualification_id=qualification_id,
        collector=collector,
        adapter=adapt_native_public_snapshot,
        clock=lambda: workflow_time,
    )
    return store


class _RunBoundReader:
    """Expose the research store through the compiler's exact binding port."""

    def __init__(self, store: LocalV31ResearchStore) -> None:
        self.store = store

    def read_bound_document(
        self, binding: Mapping[str, Any]
    ) -> dict[str, Any]:
        document = self.store.read_document(
            relative_ref=str(binding["relative_ref"]),
            digest_field=str(binding["digest_field"]),
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
        durable = self.store.artifact_binding(
            relative_ref=str(binding["relative_ref"]),
            digest_field=str(binding["digest_field"]),
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
        expected = {
            "relative_ref": str(binding["relative_ref"]),
            "semantic_digest": str(binding["semantic_digest"]),
            "physical_sha256": str(binding["physical_sha256"]),
        }
        if (
            dict(durable) != expected
            or document.get("schema_id") != binding.get("schema_id")
        ):
            raise ValueError("RUN_BOUND_DOCUMENT_DRIFT")
        return dict(document)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> dict[str, Any]:
        return dict(
            self.store.read_document(
                relative_ref=relative_ref,
                digest_field=digest_field,
                expected_semantic_digest=expected_semantic_digest,
            )
        )


def _typed_run_binding(
    store: LocalV31ResearchStore, *, relative_ref: str, digest_field: str
) -> dict[str, str]:
    document = store.read_document(
        relative_ref=relative_ref, digest_field=digest_field
    )
    binding = store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=str(document[digest_field]),
    )
    return {
        **dict(binding),
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
    }


def _prior_open_interest_digest(
    store: LocalV31ResearchStore, source_admission: Mapping[str, Any]
) -> str:
    binding = source_admission["authoring_source_bindings"][
        "pit_dataset_binding"
    ]
    dataset = store.read_document(
        relative_ref=str(binding["relative_ref"]),
        digest_field="dataset_digest",
        expected_semantic_digest=str(binding["semantic_digest"]),
    )
    rows = [
        row
        for row in dataset["data"]
        if row.get("metric") == "open-interest-btc"
        and row.get("instrument_id") == "BTC-USDT-SWAP"
    ]
    if len(rows) != 1:
        raise AssertionError("test fixture must contain one open-interest datum")
    return str(rows[0]["datum_digest"])


def _admit_cycle_one(
    root: Path,
) -> tuple[dict[str, Any], LocalV31ResearchStore, LocalV31SourceQualificationStore, dict[str, Any]]:
    active_chain, run_store = _initialize_chain_and_run(root)
    run_id = str(active_chain["authority"]["authorized_run_id"])
    source_store = _sealed_source(
        root / "qualification-cycle1",
        qualification_id="v31-source-qualification-formal-cycle1-e2e",
        capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
    )
    admission = admit_fresh_v31_source_to_authorized_cycle(
        source_store=source_store,
        run_store=run_store,
        active_chain=active_chain,
        qualification_id="v31-source-qualification-formal-cycle1-e2e",
        run_id=run_id,
        cycle_index=1,
        admitted_at="2026-08-06T17:02:00Z",
    )
    return active_chain, run_store, source_store, admission


def _accept_cycle_one(
    root: Path,
) -> tuple[dict[str, Any], LocalV31ResearchStore, LocalV31SourceQualificationStore, dict[str, Any], dict[str, dict[str, str]]]:
    active_chain, run_store, source_store, admission = _admit_cycle_one(root)
    run_id = str(active_chain["authority"]["authorized_run_id"])
    sources = admission["authoring_source_bindings"]
    packet = seal_v31_proposal_authoring_packet(
        run_id=run_id,
        cycle_index=1,
        decision_at=str(admission["cycle_source_admission"]["decision_at"]),
        symbol="BTC-USDT-SWAP",
        cycle_source_admission_binding=admission[
            "cycle_source_admission_binding"
        ],
        source_qualification_completion_binding=sources[
            "source_qualification_completion_binding"
        ],
        information_event_bindings=sources["information_event_bindings"],
        pit_dataset_binding=sources["pit_dataset_binding"],
        authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        theory_approval_binding=_typed_run_binding(
            run_store,
            relative_ref="genesis/theory-approval.json",
            digest_field="approval_receipt_digest",
        ),
        experiment_subject_binding=_typed_run_binding(
            run_store,
            relative_ref="genesis/experiment-contract.json",
            digest_field="experiment_contract_digest",
        ),
        active_authority_binding=_typed_run_binding(
            run_store,
            relative_ref="genesis/current-authority.json",
            digest_field="authority_digest",
        ),
        previous_head_bindings=admission["previous_head_bindings"],
    )
    dataset = run_store.read_document(
        relative_ref=str(sources["pit_dataset_binding"]["relative_ref"]),
        digest_field="dataset_digest",
        expected_semantic_digest=str(
            sources["pit_dataset_binding"]["semantic_digest"]
        ),
    )
    mark = next(row for row in dataset["data"] if row["metric"] == "mark-price")
    with (
        patch(
            "tests.test_theory_paper_v2_v31_semantic_compiler.REVIEW_AT",
            "2026-08-06T18:01:00Z",
        ),
        patch(
            "tests.test_theory_paper_v2_v31_semantic_compiler.EXPIRY_AT",
            "2026-08-06T19:01:00Z",
        ),
    ):
        envelope = _envelope(packet, dataset, str(mark["datum_id"]))
    compiled = compile_v31_agent_open_analysis(
        authoring_packet=packet,
        authoring_envelope=envelope,
        compiled_at="2026-08-06T17:03:00Z",
        compiler=LocalV31SemanticCompiler(store=_RunBoundReader(run_store)),
    )
    evaluation = compiled["action_evaluation"]
    wait = next(row for row in evaluation["candidates"] if row["action"] == "WAIT")
    other_ids = {
        row["candidate_id"] for row in evaluation["candidates"]
    } - {wait["candidate_id"]}
    selection_arguments = {
        "selected_candidate_id": wait["candidate_id"],
        "alternative_explanations": {
            candidate_id: "The competing registered path remains possible."
            for candidate_id in other_ids
        },
        "failure_conditions": ("The registered WAIT premise changes.",),
        "next_review_at": wait["next_review_at"],
        "selected_at": "2026-08-06T17:04:00Z",
    }
    selection = seal_action_selection(
        evaluation=evaluation,
        reason="Uncalibrated uncertainty keeps WAIT reversible.",
        **selection_arguments,
    )
    accepted = select_v31_cycle_action(
        preselection=compiled["preselection"],
        action_evaluation=evaluation,
        selection_rationale="Uncalibrated uncertainty keeps WAIT reversible.",
        **selection_arguments,
    )
    if selection["action_selection_digest"] != accepted["action_selection_digest"]:
        raise AssertionError("selection reconstruction must be exact")
    completion = complete_v31_research_cycle(
        accepted_state=accepted, completed_at="2026-08-06T17:05:00Z"
    )
    transport = self_digest(
        {
            "schema_id": "theory_paper_v31_agent_transport_evidence",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": 1,
            "transport_mode": "NO_NETWORK_LOCAL_SEMANTIC_COMPILER",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "transport_evidence_digest",
    )
    transport_ref = (
        "cycles/0001/transport-evidence/"
        f"{transport['transport_evidence_digest']}.json"
    )
    transport_binding = run_store.write_document(
        relative_ref=transport_ref,
        document=transport,
        digest_field="transport_evidence_digest",
    )
    documents = {
        "INPUTS_ADMITTED": compiled["inputs_receipt"],
        "PROPOSAL_SEALED": compiled["agent_proposal"],
        "EVALUATION_SEALED": compiled["preselection"],
        "SELECTION_SEALED": selection,
        "STATE_ACCEPTED": accepted,
        "COMPLETION_SEALED": completion,
    }
    event_times = {
        event_type: f"2026-08-06T17:{minute:02d}:00Z"
        for minute, event_type in enumerate(documents, start=6)
    }
    checkpoint = persist_completed_v31_cycle(
        store=run_store,
        run_id=run_id,
        cycle_index=1,
        total_cycles=8,
        created_at="2026-08-06T16:20:00Z",
        documents=documents,
        assembly_inputs=compiled["assembly_inputs"],
        recorded_at_by_event=event_times,
        transport_evidence_binding=transport_binding,
    )
    if checkpoint.get("status") != "READY_FOR_CYCLE":
        raise AssertionError("cycle one did not become durably accepted")
    heads = v31_cycle_authoring_head_bindings(
        store=run_store, run_id=run_id, cycle_index=1
    )
    return active_chain, run_store, source_store, admission, heads


def _cycle_two_agent_envelope(
    *,
    packet: Mapping[str, Any],
    dataset: Mapping[str, Any],
    mark_id: str,
    previous_hypothesis_registry: Mapping[str, Any],
    previous_expectation_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Author an explicit UPDATE/CREATE/CLOSE transition for cycle two."""

    decision_at = str(packet["decision_at"])
    mark = next(row for row in dataset["data"] if row["datum_id"] == mark_id)
    base = _envelope(packet, dataset, mark_id)
    previous_hypotheses = {
        row["hypothesis_id"]: row
        for row in previous_hypothesis_registry["hypotheses"]
    }
    previous_expectations = {
        row["expectation_id"]: row
        for row in previous_expectation_ledger["expectations"]
    }

    revised_lead = {
        key: copy.deepcopy(value)
        for key, value in previous_hypotheses["path:lead"].items()
        if key != "active_evidence_bindings"
    }
    revised_lead.update(
        {
            "revision": 2,
            "updated_at": decision_at,
            "active_evidence_ids": [mark_id],
            "premises": [
                "The second accepted public window now discriminates path:lead."
            ],
            "agent_rationale": (
                "UPDATE preserves identity while binding the fresh window."
            ),
        }
    )
    new_hypothesis = _hypothesis(
        "path:new", "PATH", "BIDIRECTIONAL", mark_id
    )
    hypothesis_deltas = [
        {
            "delta_id": "delta:revise:path:lead:cycle2",
            "operation": "REVISE",
            "occurred_at": decision_at,
            "target_hypothesis_ids": ["path:lead"],
            "replacement_hypotheses": [revised_lead],
            "evidence_ids": [mark_id],
            "matched_hard_falsifier": None,
            "agent_rationale": "Update one prior hypothesis from fresh evidence.",
        },
        {
            "delta_id": "delta:create:path:new:cycle2",
            "operation": "CREATE",
            "occurred_at": decision_at,
            "target_hypothesis_ids": [],
            "replacement_hypotheses": [new_hypothesis],
            "evidence_ids": [mark_id],
            "matched_hard_falsifier": None,
            "agent_rationale": "Create a distinct new direction without rewriting history.",
        },
    ]

    expectation_deltas: list[dict[str, Any]] = []
    for expectation_id in (
        "expectation:mechanism",
        "expectation:lead",
        "expectation:runner",
    ):
        closed = {
            key: copy.deepcopy(value)
            for key, value in previous_expectations[expectation_id].items()
            if key != "result_evidence_bindings"
        }
        closed.update(
            {
                "revision": 2,
                "updated_at": decision_at,
                "status": "FULFILLED",
                "result_evidence_refs": [mark_id],
                "closed_at": decision_at,
                "result_note": "Closed only from the fresh admitted public window.",
            }
        )
        expectation_deltas.append(
            {
                "delta_id": f"delta:close:{expectation_id}:cycle2",
                "operation": "CLOSE",
                "occurred_at": decision_at,
                "target_expectation_id": expectation_id,
                "expectation": closed,
                "agent_rationale": "Close the due expectation without future outcome access.",
            }
        )
    new_expectations = (
        ("expectation:mechanism:cycle2", "hypothesis:mechanism"),
        ("expectation:lead:cycle2", "path:new"),
        ("expectation:runner:cycle2", "path:runner"),
    )
    for expectation_id, hypothesis_id in new_expectations:
        expectation = _expectation(expectation_id, hypothesis_id, mark_id)
        expectation["observation_start"] = decision_at
        expectation_deltas.append(
            {
                "delta_id": f"delta:create:{expectation_id}",
                "operation": "CREATE",
                "occurred_at": decision_at,
                "target_expectation_id": None,
                "expectation": expectation,
                "agent_rationale": "Create the next open discriminating observation.",
            }
        )

    components = copy.deepcopy(base["probability_cloud_spec"]["components"])
    components.append(
        {
            **copy.deepcopy(
                next(row for row in components if row["hypothesis_id"] == "path:lead")
            ),
            "hypothesis_id": "path:new",
        }
    )
    paths = [
        _path(
            path_id="path:lead",
            hypothesis_id="path:new",
            expectation_id="expectation:lead:cycle2",
            action="OPEN_LONG",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value=mark["value"],
            run_id=str(packet["run_id"]),
        ),
        _path(
            path_id="path:runner",
            hypothesis_id="path:runner",
            expectation_id="expectation:runner:cycle2",
            action="OPEN_SHORT",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value="0",
            run_id=str(packet["run_id"]),
        ),
        _path(
            path_id="OTHER",
            hypothesis_id="hypothesis:mechanism",
            expectation_id="expectation:mechanism:cycle2",
            action="WAIT",
            mark_id=mark_id,
            mark_available_at=mark["available_at"],
            mark_value=mark["value"],
            expected_value=None,
            run_id=str(packet["run_id"]),
        ),
    ]
    for path in paths:
        path["probability_cloud_refs"] = [
            f"cloud:{packet['run_id']}:0002"
        ]
    graph_spec = copy.deepcopy(base["graph_delta_spec"])
    graph_spec["delta_id"] = "delta:graph:semantic-compiler-test:2"
    return seal_v31_agent_open_analysis_envelope(
        authoring_packet=packet,
        information_interpretations=base["information_interpretations"],
        operational_synthesis=base["operational_synthesis"],
        sentiment_axis_analyses=base["sentiment_axis_analyses"],
        graph_delta_spec=graph_spec,
        hypothesis_deltas=hypothesis_deltas,
        expectation_deltas=expectation_deltas,
        probability_cloud_spec={
            **base["probability_cloud_spec"],
            "components": components,
        },
        scenario_path_set_spec={
            **base["scenario_path_set_spec"],
            "paths": paths,
        },
        action_candidate_specs=(
            _candidate("OPEN_LONG", "path:lead", mark_id),
            _candidate("OPEN_SHORT", "path:runner", mark_id),
            _candidate("WAIT", "OTHER", mark_id),
        ),
        competing_explanations=base["competing_explanations"],
        unknowns=base["unknowns"],
        requested_observations=base["requested_observations"],
        hypothesis_novelty_rationales={
            "path:new": "A distinct direction opened only after cycle-two evidence."
        },
        limitations=base["limitations"],
    )


class V31CycleSourceAdmissionTests(unittest.TestCase):
    def test_two_cycle_no_network_source_chain_uses_exact_accepted_heads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                active_chain,
                run_store,
                cycle_one_source,
                first,
                expected_heads,
            ) = _accept_cycle_one(root)
            run_id = str(active_chain["authority"]["authorized_run_id"])
            previous_admission = first["cycle_source_admission_binding"]
            previous_snapshot = first["authoring_source_bindings"][
                "market_snapshot_binding"
            ]
            previous_oi = _prior_open_interest_digest(run_store, first)

            second_source = _sealed_source(
                root / "qualification-cycle2",
                qualification_id="v31-source-qualification-formal-cycle2-e2e",
                capture_start=datetime(2026, 8, 6, 18, 0, tzinfo=UTC),
                server_shift_hours=1,
                workflow_time="2026-08-06T18:01:00Z",
            )

            # Caller values are assertions only.  A self-consistent-looking
            # but non-derived prior OI digest cannot authorize the copy.
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "CALLER_PREVIOUS_BINDING_MISMATCH",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=second_source,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id=(
                        "v31-source-qualification-formal-cycle2-e2e"
                    ),
                    run_id=run_id,
                    cycle_index=2,
                    admitted_at="2026-08-06T18:02:00Z",
                    previous_cycle_source_admission_binding=(
                        previous_admission
                    ),
                    prior_snapshot_binding=previous_snapshot,
                    prior_open_interest_datum_digest="f" * 64,
                )
            wrong_admission = dict(previous_admission)
            wrong_admission["semantic_digest"] = "e" * 64
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "CALLER_PREVIOUS_BINDING_MISMATCH",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=second_source,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id=(
                        "v31-source-qualification-formal-cycle2-e2e"
                    ),
                    run_id=run_id,
                    cycle_index=2,
                    admitted_at="2026-08-06T18:02:00Z",
                    previous_cycle_source_admission_binding=wrong_admission,
                    prior_snapshot_binding=previous_snapshot,
                    prior_open_interest_datum_digest=previous_oi,
                )
            self.assertFalse(
                (run_store.run_root / cycle_source_admission_ref(2)).exists()
            )

            # A fresh qualification ID does not make an old 1H window new.
            stale_source = _sealed_source(
                root / "qualification-cycle2-stale-window",
                qualification_id=(
                    "v31-source-qualification-formal-cycle2-stale-window"
                ),
                capture_start=datetime(2026, 8, 6, 17, 30, tzinfo=UTC),
                workflow_time="2026-08-06T18:01:00Z",
            )
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "CROSS_CYCLE_CHRONOLOGY_INVALID",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=stale_source,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id=(
                        "v31-source-qualification-formal-cycle2-stale-window"
                    ),
                    run_id=run_id,
                    cycle_index=2,
                    admitted_at="2026-08-06T18:02:00Z",
                    previous_cycle_source_admission_binding=(
                        previous_admission
                    ),
                    prior_snapshot_binding=previous_snapshot,
                    prior_open_interest_datum_digest=previous_oi,
                )

            # Reusing the prior qualification is rejected independently of
            # its old capture time.
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "QUALIFICATION_RESURRECTION_FORBIDDEN",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=cycle_one_source,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id=(
                        "v31-source-qualification-formal-cycle1-e2e"
                    ),
                    run_id=run_id,
                    cycle_index=2,
                    admitted_at="2026-08-06T18:02:00Z",
                    previous_cycle_source_admission_binding=(
                        previous_admission
                    ),
                    prior_snapshot_binding=previous_snapshot,
                    prior_open_interest_datum_digest=previous_oi,
                )

            second = admit_fresh_v31_source_to_authorized_cycle(
                source_store=second_source,
                run_store=run_store,
                active_chain=active_chain,
                qualification_id="v31-source-qualification-formal-cycle2-e2e",
                run_id=run_id,
                cycle_index=2,
                admitted_at="2026-08-06T18:02:00Z",
                previous_cycle_source_admission_binding=previous_admission,
                prior_snapshot_binding=previous_snapshot,
                prior_open_interest_datum_digest=previous_oi,
            )
            receipt = second["cycle_source_admission"]
            self.assertEqual(2, receipt["cycle_index"])
            self.assertEqual(
                "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE",
                receipt["previous_source_context"]["status"],
            )
            self.assertEqual(
                previous_admission,
                receipt["previous_source_context"][
                    "previous_cycle_source_admission_binding"
                ],
            )
            self.assertEqual(
                previous_snapshot,
                receipt["previous_source_context"]["prior_snapshot_binding"],
            )
            self.assertEqual(
                previous_oi,
                receipt["previous_source_context"][
                    "prior_open_interest_datum_digest"
                ],
            )
            self.assertEqual(
                "UNKNOWN",
                receipt["previous_source_context"][
                    "prior_open_interest_status"
                ],
            )
            self.assertFalse(
                receipt["previous_source_context"][
                    "prior_open_interest_zero_imputed"
                ]
            )
            previous_closed = datetime.fromisoformat(
                first["cycle_source_admission"]["closed_1h_as_of"].replace(
                    "Z", "+00:00"
                )
            )
            current_closed = datetime.fromisoformat(
                receipt["closed_1h_as_of"].replace("Z", "+00:00")
            )
            self.assertEqual(timedelta(hours=1), current_closed - previous_closed)
            snapshot_binding = second["authoring_source_bindings"][
                "market_snapshot_binding"
            ]
            copied_snapshot = run_store.read_document(
                relative_ref=snapshot_binding["relative_ref"],
                digest_field="native_market_snapshot_digest",
                expected_semantic_digest=snapshot_binding["semantic_digest"],
            )
            self.assertEqual(
                1,
                copied_snapshot["cycle_index"],
                "qualification truth remains internal cycle 1",
            )
            self.assertEqual(expected_heads, second["previous_head_bindings"])

            replay = verify_durable_v31_cycle_source_admission(
                run_store=run_store,
                run_id=run_id,
                cycle_index=2,
                expected_authority_digest=active_chain["authority"][
                    "authority_digest"
                ],
                expected_experiment_contract_digest=active_chain[
                    "experiment_contract"
                ]["experiment_contract_digest"],
            )
            self.assertEqual(
                receipt["cycle_source_admission_digest"],
                replay["cycle_source_admission"][
                    "cycle_source_admission_digest"
                ],
            )
            self.assertEqual(expected_heads, replay["previous_head_bindings"])
            self.assertEqual(1, run_store.load_checkpoint(run_id=run_id)["completed_cycles"])

    def test_cycle_two_agent_lifecycle_compiles_selects_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store, _source, first, cycle_one_heads = (
                _accept_cycle_one(root)
            )
            run_id = str(active_chain["authority"]["authorized_run_id"])
            second_source = _sealed_source(
                root / "qualification-cycle2-compile",
                qualification_id="v31-source-qualification-cycle2-compile",
                capture_start=datetime(2026, 8, 6, 18, 0, tzinfo=UTC),
                server_shift_hours=1,
                workflow_time="2026-08-06T18:01:00Z",
            )
            second = admit_fresh_v31_source_to_authorized_cycle(
                source_store=second_source,
                run_store=run_store,
                active_chain=active_chain,
                qualification_id="v31-source-qualification-cycle2-compile",
                run_id=run_id,
                cycle_index=2,
                admitted_at="2026-08-06T18:02:00Z",
                previous_cycle_source_admission_binding=first[
                    "cycle_source_admission_binding"
                ],
                prior_snapshot_binding=first["authoring_source_bindings"][
                    "market_snapshot_binding"
                ],
                prior_open_interest_datum_digest=_prior_open_interest_digest(
                    run_store, first
                ),
            )
            sources = second["authoring_source_bindings"]
            packet = seal_v31_proposal_authoring_packet(
                run_id=run_id,
                cycle_index=2,
                decision_at=second["cycle_source_admission"]["decision_at"],
                symbol="BTC-USDT-SWAP",
                cycle_source_admission_binding=second[
                    "cycle_source_admission_binding"
                ],
                source_qualification_completion_binding=sources[
                    "source_qualification_completion_binding"
                ],
                information_event_bindings=sources[
                    "information_event_bindings"
                ],
                pit_dataset_binding=sources["pit_dataset_binding"],
                authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
                theory_approval_binding=_typed_run_binding(
                    run_store,
                    relative_ref="genesis/theory-approval.json",
                    digest_field="approval_receipt_digest",
                ),
                experiment_subject_binding=_typed_run_binding(
                    run_store,
                    relative_ref="genesis/experiment-contract.json",
                    digest_field="experiment_contract_digest",
                ),
                active_authority_binding=_typed_run_binding(
                    run_store,
                    relative_ref="genesis/current-authority.json",
                    digest_field="authority_digest",
                ),
                previous_head_bindings=second["previous_head_bindings"],
            )
            dataset = run_store.read_document(
                relative_ref=sources["pit_dataset_binding"]["relative_ref"],
                digest_field="dataset_digest",
                expected_semantic_digest=sources["pit_dataset_binding"][
                    "semantic_digest"
                ],
            )
            mark = next(
                row for row in dataset["data"] if row["metric"] == "mark-price"
            )
            previous_hypothesis_registry = run_store.read_document(
                relative_ref=cycle_one_heads[
                    "previous_hypothesis_registry"
                ]["relative_ref"],
                digest_field="hypothesis_registry_digest",
                expected_semantic_digest=cycle_one_heads[
                    "previous_hypothesis_registry"
                ]["semantic_digest"],
            )
            previous_expectation_ledger = run_store.read_document(
                relative_ref=cycle_one_heads["previous_expectation_ledger"][
                    "relative_ref"
                ],
                digest_field="expectation_ledger_digest",
                expected_semantic_digest=cycle_one_heads[
                    "previous_expectation_ledger"
                ]["semantic_digest"],
            )
            with (
                patch(
                    "tests.test_theory_paper_v2_v31_semantic_compiler.CREATED_AT",
                    "2026-08-06T18:00:30Z",
                ),
                patch(
                    "tests.test_theory_paper_v2_v31_semantic_compiler.REVIEW_AT",
                    "2026-08-06T19:01:00Z",
                ),
                patch(
                    "tests.test_theory_paper_v2_v31_semantic_compiler.EXPIRY_AT",
                    "2026-08-06T20:01:00Z",
                ),
            ):
                envelope = _cycle_two_agent_envelope(
                    packet=packet,
                    dataset=dataset,
                    mark_id=mark["datum_id"],
                    previous_hypothesis_registry=previous_hypothesis_registry,
                    previous_expectation_ledger=previous_expectation_ledger,
                )
            resurrected_deltas = copy.deepcopy(envelope["hypothesis_deltas"])
            resurrected = _hypothesis(
                "path:runner", "PATH", "SHORT", mark["datum_id"]
            )
            resurrected.update(
                {
                    "created_at": packet["decision_at"],
                    "updated_at": packet["decision_at"],
                    "expiry": "2026-08-06T20:01:00Z",
                }
            )
            resurrected_deltas.append(
                {
                    "delta_id": "delta:illegal-resurrection:path:runner",
                    "operation": "CREATE",
                    "occurred_at": packet["decision_at"],
                    "target_hypothesis_ids": [],
                    "replacement_hypotheses": [resurrected],
                    "evidence_ids": [mark["datum_id"]],
                    "matched_hard_falsifier": None,
                    "agent_rationale": "This attempted ID resurrection must fail.",
                }
            )
            with self.assertRaises(V31CycleAuthoringWorkflowError):
                compile_v31_agent_open_analysis(
                    authoring_packet=packet,
                    authoring_envelope=_reseal_envelope(
                        packet,
                        envelope,
                        hypothesis_deltas=resurrected_deltas,
                        hypothesis_novelty_rationales={
                            **envelope["hypothesis_novelty_rationales"],
                            "path:runner": "Illegal reused identity.",
                        },
                    ),
                    compiled_at="2026-08-06T18:03:00Z",
                    compiler=LocalV31SemanticCompiler(
                        store=_RunBoundReader(run_store)
                    ),
                )
            reversed_deltas = copy.deepcopy(envelope["hypothesis_deltas"])
            reversed_deltas[0]["occurred_at"] = previous_hypothesis_registry[
                "decision_at"
            ]
            with self.assertRaises(V31CycleAuthoringWorkflowError):
                compile_v31_agent_open_analysis(
                    authoring_packet=packet,
                    authoring_envelope=_reseal_envelope(
                        packet, envelope, hypothesis_deltas=reversed_deltas
                    ),
                    compiled_at="2026-08-06T18:03:00Z",
                    compiler=LocalV31SemanticCompiler(
                        store=_RunBoundReader(run_store)
                    ),
                )
            compiled = compile_v31_agent_open_analysis(
                authoring_packet=packet,
                authoring_envelope=envelope,
                compiled_at="2026-08-06T18:03:00Z",
                compiler=LocalV31SemanticCompiler(
                    store=_RunBoundReader(run_store)
                ),
            )
            self.assertEqual(2, compiled["preselection"]["cycle_index"])
            self.assertEqual(
                "REPARTITION",
                compiled["preselection"]["probability_cloud_transition"][
                    "transition_kind"
                ],
            )
            hypothesis_node_refs = {
                row["payload_ref"]
                for row in compiled["assembly_inputs"]["graph_delta"][
                    "node_revisions"
                ]
                if row["node_type"]
                in {"MECHANISM_HYPOTHESIS", "PATH_HYPOTHESIS"}
            }
            self.assertNotIn("hypothesis:mechanism", hypothesis_node_refs)
            self.assertNotIn("path:runner", hypothesis_node_refs)
            self.assertIn("path:lead", hypothesis_node_refs)
            self.assertIn("path:new", hypothesis_node_refs)
            graph_state = apply_graph_delta(
                compiled["assembly_inputs"]["prior_graph"],
                compiled["assembly_inputs"]["graph_delta"],
                decision_at=packet["decision_at"],
            )
            latest_nodes = {
                row["node_id"]: row for row in graph_state["node_history"]
            }
            closed_expectation_nodes = [
                row
                for row in latest_nodes.values()
                if row["node_type"] == "EXPECTATION"
                and row["payload_ref"]
                in {
                    "expectation:mechanism",
                    "expectation:lead",
                    "expectation:runner",
                }
            ]
            self.assertTrue(closed_expectation_nodes)
            self.assertTrue(
                all(row["status"] == "RETIRED" for row in closed_expectation_nodes)
            )

            evaluation = compiled["action_evaluation"]
            wait = next(
                row for row in evaluation["candidates"] if row["action"] == "WAIT"
            )
            alternatives = {
                row["candidate_id"]: "The competing registered path remains possible."
                for row in evaluation["candidates"]
                if row["candidate_id"] != wait["candidate_id"]
            }
            selection = seal_action_selection(
                evaluation=evaluation,
                selected_candidate_id=wait["candidate_id"],
                reason="WAIT remains reversible under ordinal uncertainty.",
                alternative_explanations=alternatives,
                failure_conditions=("The WAIT premise changes.",),
                next_review_at=wait["next_review_at"],
                selected_at="2026-08-06T18:04:00Z",
            )
            accepted = select_v31_cycle_action(
                preselection=compiled["preselection"],
                action_evaluation=evaluation,
                selected_candidate_id=wait["candidate_id"],
                alternative_explanations=alternatives,
                selection_rationale=(
                    "WAIT remains reversible under ordinal uncertainty."
                ),
                failure_conditions=("The WAIT premise changes.",),
                next_review_at=wait["next_review_at"],
                selected_at="2026-08-06T18:04:00Z",
            )
            self.assertEqual(
                selection["action_selection_digest"],
                accepted["action_selection_digest"],
            )
            completion = complete_v31_research_cycle(
                accepted_state=accepted,
                completed_at="2026-08-06T18:05:00Z",
            )
            transport = self_digest(
                {
                    "schema_id": "theory_paper_v31_agent_transport_evidence",
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "cycle_index": 2,
                    "transport_mode": "NO_NETWORK_LOCAL_SEMANTIC_COMPILER",
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "transport_evidence_digest",
            )
            transport_binding = run_store.write_document(
                relative_ref=(
                    "cycles/0002/transport-evidence/"
                    f"{transport['transport_evidence_digest']}.json"
                ),
                document=transport,
                digest_field="transport_evidence_digest",
            )
            documents = {
                "INPUTS_ADMITTED": compiled["inputs_receipt"],
                "PROPOSAL_SEALED": compiled["agent_proposal"],
                "EVALUATION_SEALED": compiled["preselection"],
                "SELECTION_SEALED": selection,
                "STATE_ACCEPTED": accepted,
                "COMPLETION_SEALED": completion,
            }
            checkpoint = persist_completed_v31_cycle(
                store=run_store,
                run_id=run_id,
                cycle_index=2,
                total_cycles=8,
                created_at="2026-08-06T16:20:00Z",
                documents=documents,
                assembly_inputs=compiled["assembly_inputs"],
                recorded_at_by_event={
                    event_type: f"2026-08-06T18:{minute:02d}:00Z"
                    for minute, event_type in enumerate(documents, start=6)
                },
                transport_evidence_binding=transport_binding,
            )
            self.assertEqual(2, checkpoint["completed_cycles"])
            self.assertEqual(
                cycle_one_heads,
                v31_cycle_authoring_head_bindings(
                    store=run_store, run_id=run_id, cycle_index=1
                ),
            )
            self.assertEqual(
                8,
                len(
                    v31_cycle_authoring_head_bindings(
                        store=run_store, run_id=run_id, cycle_index=2
                    )
                ),
            )

    def test_cycle_two_missing_semantic_head_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store, _source, first, _heads = _accept_cycle_one(
                root
            )
            run_id = str(active_chain["authority"]["authorized_run_id"])
            source = _sealed_source(
                root / "qualification-cycle2-head-gap",
                qualification_id="v31-source-qualification-cycle2-head-gap",
                capture_start=datetime(2026, 8, 6, 18, 0, tzinfo=UTC),
                server_shift_hours=1,
                workflow_time="2026-08-06T18:01:00Z",
            )
            head = run_store.run_root / "cycles/0001/sentiment-state.json"
            head.rename(head.with_suffix(".json.missing"))
            with self.assertRaises(V31CycleSourceAdmissionWorkflowError):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=source,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id=(
                        "v31-source-qualification-cycle2-head-gap"
                    ),
                    run_id=run_id,
                    cycle_index=2,
                    admitted_at="2026-08-06T18:02:00Z",
                    previous_cycle_source_admission_binding=first[
                        "cycle_source_admission_binding"
                    ],
                    prior_snapshot_binding=first[
                        "authoring_source_bindings"
                    ]["market_snapshot_binding"],
                    prior_open_interest_datum_digest=(
                        _prior_open_interest_digest(run_store, first)
                    ),
                )
            self.assertFalse(
                (run_store.run_root / cycle_source_admission_ref(2)).exists()
            )

    def test_genesis_source_is_exactly_copied_and_run_locally_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store = _initialize_chain_and_run(root)
            run_id = active_chain["authority"]["authorized_run_id"]
            source_root = root / "qualification"
            source_store = _sealed_source(
                source_root,
                qualification_id="v31-source-qualification-formal-cycle1-a",
                capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
            )
            checkpoint_before = run_store.load_checkpoint(run_id=run_id)

            result = admit_fresh_v31_source_to_authorized_cycle(
                source_store=source_store,
                run_store=run_store,
                active_chain=active_chain,
                qualification_id="v31-source-qualification-formal-cycle1-a",
                run_id=run_id,
                cycle_index=1,
                admitted_at="2026-08-06T17:02:00Z",
            )

            receipt = result["cycle_source_admission"]
            self.assertEqual("CYCLE_SOURCE_ADMITTED_NOT_STARTED", result["status"])
            self.assertFalse(receipt["source_qualification_is_start_authority"])
            self.assertTrue(receipt["cycle_source_admitted"])
            self.assertTrue(receipt["source_capture_records_embedded_in_copied_snapshot"])
            self.assertFalse(receipt["executable"])
            self.assertEqual(checkpoint_before, result["checkpoint"])
            self.assertEqual(
                checkpoint_before, run_store.load_checkpoint(run_id=run_id)
            )
            self.assertIn("cycle_source_admission_binding", result)
            self.assertEqual(
                {
                    "relative_ref",
                    "schema_id",
                    "digest_field",
                    "semantic_digest",
                    "physical_sha256",
                },
                set(result["cycle_source_admission_binding"]),
            )
            self.assertEqual(
                {
                    "source_qualification_completion_binding",
                    "market_snapshot_binding",
                    "information_event_bindings",
                    "pit_dataset_binding",
                },
                set(result["authoring_source_bindings"]),
            )

            # The replay API has no qualification-store parameter: copied run
            # bytes form an independent, physically verified closure.
            source_root.rename(root / "qualification-detached")
            replay = verify_durable_v31_cycle_source_admission(
                run_store=run_store,
                run_id=run_id,
                cycle_index=1,
                expected_authority_digest=active_chain["authority"]["authority_digest"],
                expected_experiment_contract_digest=active_chain[
                    "experiment_contract"
                ]["experiment_contract_digest"],
            )
            self.assertEqual(
                receipt["cycle_source_admission_digest"],
                replay["cycle_source_admission"]["cycle_source_admission_digest"],
            )

    def test_capture_at_or_before_active_authority_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store = _initialize_chain_and_run(root)
            run_id = active_chain["authority"]["authorized_run_id"]
            source_store = _sealed_source(
                root / "qualification",
                qualification_id="v31-source-qualification-stale-cycle1",
                capture_start=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
            )
            before = run_store.load_checkpoint(run_id=run_id)
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "CAPTURE_NOT_FRESH_AFTER_AUTHORITY",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=source_store,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id="v31-source-qualification-stale-cycle1",
                    run_id=run_id,
                    cycle_index=1,
                    admitted_at="2026-08-06T17:02:00Z",
                )
            self.assertEqual(before, run_store.load_checkpoint(run_id=run_id))
            self.assertFalse(
                (run_store.run_root / cycle_source_admission_ref(1)).exists()
            )

    def test_wrong_run_cycle_and_source_physical_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store = _initialize_chain_and_run(root)
            run_id = active_chain["authority"]["authorized_run_id"]
            source_store = _sealed_source(
                root / "qualification",
                qualification_id="v31-source-qualification-drift-cycle1",
                capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
            )
            common = {
                "source_store": source_store,
                "run_store": run_store,
                "active_chain": active_chain,
                "qualification_id": "v31-source-qualification-drift-cycle1",
                "admitted_at": "2026-08-06T17:02:00Z",
            }
            with self.assertRaises(V31CycleSourceAdmissionWorkflowError):
                admit_fresh_v31_source_to_authorized_cycle(
                    **common, run_id="wrong-run", cycle_index=1
                )
            with self.assertRaisesRegex(
                V31CycleSourceAdmissionWorkflowError,
                "RUN_CHECKPOINT_NOT_READY",
            ):
                admit_fresh_v31_source_to_authorized_cycle(
                    **common, run_id=run_id, cycle_index=2
                )

            completion = source_store.read_document(
                relative_ref="receipts/source-qualification-completion.json",
                digest_field="source_qualification_completion_digest",
            )
            raw_ref = next(iter(completion["raw_bindings"].values()))["relative_ref"]
            raw_path = source_store.qualification_root / raw_ref
            raw_path.write_bytes(raw_path.read_bytes() + b"drift")
            with self.assertRaises(V31CycleSourceAdmissionWorkflowError):
                admit_fresh_v31_source_to_authorized_cycle(
                    **common, run_id=run_id, cycle_index=1
                )
            self.assertFalse(
                (run_store.run_root / cycle_source_admission_ref(1)).exists()
            )

    def test_old_none_e0_event_and_duplicate_conflict_are_not_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_chain, run_store = _initialize_chain_and_run(root)
            run_id = active_chain["authority"]["authorized_run_id"]
            old_store = _sealed_source(
                root / "old-qualification",
                qualification_id="v31-source-qualification-old-e0-cycle1",
                capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
            )
            completion = old_store.read_document(
                relative_ref="receipts/source-qualification-completion.json",
                digest_field="source_qualification_completion_digest",
            )
            event_ref = completion["information_event_bindings"][0]["relative_ref"]
            event = copy.deepcopy(
                old_store.read_document(
                    relative_ref=event_ref,
                    digest_field="source_qualification_information_event_record_digest",
                )
            )
            event.pop("source_qualification_information_event_record_digest")
            event["external_execution_authority"] = "NONE_E0"
            event["event_document"]["external_execution_authority"] = "NONE_E0"
            event["information_event_digest"] = canonical_digest(event["event_document"])
            event = self_digest(
                event, "source_qualification_information_event_record_digest"
            )
            (old_store.qualification_root / event_ref).write_bytes(
                canonical_bytes(event) + b"\n"
            )
            with self.assertRaises(V31CycleSourceAdmissionWorkflowError):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=old_store,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id="v31-source-qualification-old-e0-cycle1",
                    run_id=run_id,
                    cycle_index=1,
                    admitted_at="2026-08-06T17:02:00Z",
                )
            self.assertFalse(
                (run_store.run_root / cycle_source_admission_ref(1)).exists()
            )

            first = _sealed_source(
                root / "qualification-a",
                qualification_id="v31-source-qualification-duplicate-a",
                capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
            )
            admit_fresh_v31_source_to_authorized_cycle(
                source_store=first,
                run_store=run_store,
                active_chain=active_chain,
                qualification_id="v31-source-qualification-duplicate-a",
                run_id=run_id,
                cycle_index=1,
                admitted_at="2026-08-06T17:02:00Z",
            )
            second = _sealed_source(
                root / "qualification-b",
                qualification_id="v31-source-qualification-duplicate-b",
                capture_start=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
            )
            with self.assertRaises(V31CycleSourceAdmissionWorkflowError):
                admit_fresh_v31_source_to_authorized_cycle(
                    source_store=second,
                    run_store=run_store,
                    active_chain=active_chain,
                    qualification_id="v31-source-qualification-duplicate-b",
                    run_id=run_id,
                    cycle_index=1,
                    admitted_at="2026-08-06T17:02:00Z",
                )
            self.assertEqual(0, run_store.load_checkpoint(run_id=run_id)["revision"])


if __name__ == "__main__":
    unittest.main()
