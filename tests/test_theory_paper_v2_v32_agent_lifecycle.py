from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v32_dynamic_action_plan as action_fixture
from tests import test_theory_paper_v2_v32_timeframe_cache as cache_fixture
from tests import test_theory_paper_v2_v32_public_source_collector as collector_fixture
from trade_system.theory_paper_v2.application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
)
from trade_system.theory_paper_v2.application.v32_durable_source_replay import (
    compose_and_persist_v32_durable_source_replay_receipt,
)
from trade_system.theory_paper_v2.application.v32_dynamic_state_continuity import (
    build_v32_verified_pit_evidence_availability_registry_v1,
)
from trade_system.theory_paper_v2.application.v32_agent_market_graph_view import (
    build_v32_agent_market_graph_view_v1,
    verify_v32_agent_market_graph_view_v1,
)
from trade_system.theory_paper_v2.application.v32_authorized_revision_orchestration import (
    build_v32_authorized_revision_support_bundle_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_SCHEMA_ID,
    PHASE_A_DIGEST_FIELD,
    PHASE_A_SCHEMA_ID,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_SCHEMA_ID,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    RUNTIME_MANIFEST_SCHEMA_ID,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    THEORY_APPROVAL_SCHEMA_ID,
    build_v32_authority_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_SCHEMA_ID,
    SUPPORT_BINDING_KEYS,
    build_v32_experiment_contract_v1,
)
from trade_system.theory_paper_v2.domain.v31_sentiment_native_projection_v2 import (
    build_v31_native_sentiment_projection,
    build_v31_native_sentiment_source_registry,
)
from trade_system.theory_paper_v2.domain.v32_association_preregistration import (
    build_v32_association_preregistration,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    CAPTURE_SCHEMA_ID,
    FULL_LOADER_DIGEST_FIELD,
    FULL_LOADER_SCHEMA_ID,
    QUALIFICATION_DIGEST_FIELD,
    QUALIFICATION_SCHEMA_ID,
    SNAPSHOT_DIGEST_FIELD,
    SNAPSHOT_SCHEMA_ID,
    build_v32_active_authority_projection,
    seal_v32_cycle_source_admission,
    verify_v32_cycle_source_admission,
)
from trade_system.theory_paper_v2.domain.v32_agent_market_graph_view import (
    MAX_CANONICAL_BYTES as AGENT_MARKET_VIEW_MAX_BYTES,
    SCHEMA_VERSION as AGENT_MARKET_VIEW_SCHEMA_VERSION,
    VIEW_POLICY as AGENT_MARKET_VIEW_POLICY,
    project_v32_agent_market_graph_closure_record_v1,
    seal_v32_agent_market_graph_view_v1,
    verify_v32_agent_market_graph_view_intrinsic_v1,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    build_v32_context_compaction_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_data_gap_escalation import (
    build_v32_data_gap_manual_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    build_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.domain.v32_evaluation_contract import (
    build_v32_evaluation_contract,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    build_v32_clock_and_tick_policy_v1,
    build_v32_public_outcome_adapter_contract_v1,
)
from trade_system.theory_paper_v2.domain.v32_recovery_supervision import (
    build_v32_recovery_supervision_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_unknown_assessment import (
    build_v32_unknown_subjective_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    ASSOCIATION_PREREGISTRATION_DIGEST_FIELD,
    COMMIT_ENVELOPE_DIGEST_FIELD,
    EVALUATION_CONTRACT_DIGEST_FIELD,
    GRAPH_REGISTRY_DIGEST_FIELD,
    GRAPH_REGISTRY_SCHEMA_ID,
    MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
    MAX_PROPOSAL_CANONICAL_PACKET_BYTES,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    PROPOSAL_SUPPORT_SPECS,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    THEORY_DOCUMENT_DIGEST_FIELD,
    THEORY_DOCUMENT_SCHEMA_ID,
    V32_QUALIFICATION_CONTEXT_PROFILE,
    V32_TARGET_CONTEXT_PROFILE,
    V32AgentLifecycleError,
    agent_commit_envelope_ref_v1,
    agent_consumption_ref_v1,
    agent_delivery_ref_v1,
    agent_input_context_ref_v1,
    build_v32_action_evaluation_v1,
    build_v32_agent_consumption_v1,
    build_v32_agent_delivery_v1,
    build_v32_agent_input_context_v1,
    build_v32_embedded_document_binding_v1,
    build_v32_proposal_canonical_packet_v1,
    build_v32_selection_canonical_packet_v1,
    build_v32_theory_semantic_document_v1,
    build_v32_two_stage_commit_envelope_v1,
    verify_v32_action_evaluation_v1,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_v1,
    verify_v32_proposal_canonical_packet_v1,
    verify_v32_selection_canonical_packet_v1,
    verify_v32_theory_semantic_document_v1,
    verify_v32_two_stage_commit_envelope_v1,
    v32_lifecycle_verification_scope_v1,
)
from trade_system.theory_paper_v2.domain import v32_agent_lifecycle as lifecycle
from trade_system.theory_paper_v2.domain.v32_dynamic_action_plan import (
    build_v32_dynamic_action_plan_v1,
    legal_v32_dynamic_action_keys_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_timeframe_cache import (
    build_v32_context_frame_v1,
    build_v32_timeframe_context_state_v1,
    project_v32_refreshed_frame_policy_v1,
    project_v32_timeframe_payloads_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_market_graph_projection import (
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_PROJECTION_SCHEMA_ID,
    build_v32_public_market_graph_projection_v1,
    build_v32_verified_graph_dependency_registry_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)


RUN_ID = "v32-test-run"
THEORY_TEXT = "# V3.2 完整理论\n\n动态进攻、可撤销风险与严格事实边界。\n"
_FORMAL_MARKET_CHAIN_CACHE: dict[tuple[str, int, str], dict] = {}
_FORMAL_MARKET_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []
_PROPOSAL_PACKET_TEMPLATE_CACHE: dict[str, dict] = {}


def _external_binding(
    ref: str, schema_id: str, digest_field: str, digest: str
) -> dict[str, str]:
    return {
        "relative_ref": ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": digest,
        "physical_sha256": "f" * 64,
    }


def _authority_chain_binding(
    path: str, schema_id: str, digest_field: str, digest: str
) -> dict[str, str]:
    return {
        "path": path,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": digest,
        "physical_sha256": "f" * 64,
    }


def _authority_document(
    *,
    profile: str,
    run_id: str,
    target_run_id: str,
    experiment_contract: dict,
) -> dict:
    experiment_digest = experiment_contract[EXPERIMENT_DIGEST_FIELD]
    experiment_physical = hashlib.sha256(
        canonical_bytes(experiment_contract) + b"\n"
    ).hexdigest()
    experiment_binding = _authority_chain_binding(
        "config/v32/experiment-contract.json",
        EXPERIMENT_SCHEMA_ID,
        EXPERIMENT_DIGEST_FIELD,
        experiment_digest,
    )
    experiment_binding["physical_sha256"] = experiment_physical
    qualification = profile == QUALIFICATION_PROFILE
    return build_v32_authority_v1(
        authority_id=f"authority:{profile.lower()}:{run_id}",
        profile=profile,
        recorded_at="2026-08-07T00:13:00Z",
        run_id=run_id,
        target_run_id=target_run_id,
        predecessor_authority_binding=_authority_chain_binding(
            "config/v31/predecessor-authority.json",
            "theory_paper_v31_predecessor_authority_v1",
            "authority_digest",
            "9" * 64,
        ),
        theory_approval_binding=_authority_chain_binding(
            "config/v32/theory-approval.json",
            THEORY_APPROVAL_SCHEMA_ID,
            THEORY_APPROVAL_DIGEST_FIELD,
            "1" * 64,
        ),
        experiment_contract_binding=experiment_binding,
        runtime_manifest_binding=_authority_chain_binding(
            "config/v32/runtime-manifest.json",
            RUNTIME_MANIFEST_SCHEMA_ID,
            RUNTIME_MANIFEST_DIGEST_FIELD,
            "2" * 64,
        ),
        phase_a_receipt_binding=_authority_chain_binding(
            "config/v32/phase-a.json",
            PHASE_A_SCHEMA_ID,
            PHASE_A_DIGEST_FIELD,
            "3" * 64,
        ),
        authorization_receipt_binding=_authority_chain_binding(
            "config/v32/authorization.json",
            AUTHORIZATION_RECEIPT_SCHEMA_ID,
            AUTHORIZATION_RECEIPT_DIGEST_FIELD,
            "4" * 64,
        ),
        qualification_retirement_binding=(
            None
            if qualification
            else _authority_chain_binding(
                "config/v32/qualification-retirement.json",
                QUALIFICATION_RETIREMENT_SCHEMA_ID,
                QUALIFICATION_RETIREMENT_DIGEST_FIELD,
                "5" * 64,
            )
        ),
    )


def _embedded(name: str, document: dict, schema_id: str, digest_field: str) -> dict:
    return build_v32_embedded_document_binding_v1(
        relative_ref=f"artifacts/{name}.json",
        document=document,
        schema_id=schema_id,
        digest_field=digest_field,
    )


def _formal_source_admission(
    *,
    cycle: int,
    decision_time: str,
    admitted_at: str,
    experiment_contract_digest: str,
    pit_registry_binding: dict,
    previous_source_context: dict,
    current_open_interest_status: str = "OBSERVED",
    run_id: str = RUN_ID,
    active_authority_projection_digest: str = "a" * 64,
    governing_authority_digest: str = "b" * 64,
) -> dict:
    return seal_v32_cycle_source_admission(
        run_id=run_id,
        cycle_index=cycle,
        decision_time=decision_time,
        admitted_at=admitted_at,
        active_authority_projection_digest=active_authority_projection_digest,
        governing_authority_digest=governing_authority_digest,
        experiment_contract_digest=experiment_contract_digest,
        qualification_binding=_external_binding(
            f"cycles/{cycle:04d}/market/v32-source-admission/qualification.json",
            QUALIFICATION_SCHEMA_ID,
            QUALIFICATION_DIGEST_FIELD,
            "1" * 64,
        ),
        capture_binding=_external_binding(
            f"cycles/{cycle:04d}/market/v32-source-admission/capture.json",
            CAPTURE_SCHEMA_ID,
            CAPTURE_DIGEST_FIELD,
            "2" * 64,
        ),
        current_snapshot_binding=_external_binding(
            f"cycles/{cycle:04d}/market/v32-source-admission/snapshot.json",
            SNAPSHOT_SCHEMA_ID,
            SNAPSHOT_DIGEST_FIELD,
            "3" * 64,
        ),
        pit_registry_binding=pit_registry_binding,
        previous_source_context=previous_source_context,
        full_loader_receipt_binding=_external_binding(
            f"cycles/{cycle:04d}/market/v32-source-admission/full-loader.json",
            FULL_LOADER_SCHEMA_ID,
            FULL_LOADER_DIGEST_FIELD,
            "4" * 64,
        ),
        current_open_interest_datum_digest="5" * 64,
        current_open_interest_status=current_open_interest_status,
    )


def _dynamic_registry_members(*, dependency_members: bool) -> list[str]:
    state = action_fixture._dynamic_state()
    pit_members: set[str] = set()
    graph_members: set[str] = set()
    for row in state["unknowns"]:
        graph_members.update(row["dependency_refs"])
    for row in state["zones"]:
        for field in (
            "evidence_refs",
            "touch_refs",
            "reaction_refs",
            "volume_at_price_refs",
            "dwell_time_refs",
            "round_number_refs",
            "orderbook_flow_refs",
            "leverage_refs",
            "options_refs",
        ):
            pit_members.update(row[field])
        graph_members.update(row["dependency_groups"])
    for row in state["hypotheses"]:
        for field in (
            "source_refs",
            "supporting_refs",
            "opposing_refs",
            "tier_update_refs",
            "renewal_evidence_refs",
        ):
            pit_members.update(row[field])
        graph_members.update(row["dependency_groups"])
    for field in (
        "evidence_refs",
        "counter_evidence_refs",
        "transition_evidence_refs",
    ):
        pit_members.update(state["market_regime_state"][field])
    for row in state["path_modifiers"]:
        pit_members.update(row["source_refs"])
        graph_members.update(row["dependency_groups"])
    for row in state["dependency_clusters"]:
        graph_members.update(row["shared_dependency_groups"])
    return sorted(graph_members if dependency_members else pit_members)


def _registry(
    schema_id: str,
    digest_field: str,
    *,
    cycle: int,
    as_of: str,
    run_id: str = RUN_ID,
) -> dict:
    dependency_members = schema_id == GRAPH_REGISTRY_SCHEMA_ID
    return self_digest(
        {
            "schema_id": schema_id,
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle,
            "as_of": as_of,
            "members": _dynamic_registry_members(
                dependency_members=dependency_members
            ),
            "upstream_schema_id": "verified-upstream-v1",
            "upstream_digest_field": "upstream_digest",
            "upstream_semantic_digest": "a" * 64,
            "full_verification_receipt_digest": "b" * 64,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        digest_field,
    )


def _theory() -> tuple[dict, dict]:
    document = build_v32_theory_semantic_document_v1(
        theory_source_binding={
            "path": "theory/current/V3_2_DYNAMIC_AGGRESSIVE.md",
            "version": "3.2.1",
            "review_status": "FROZEN_APPROVED",
            "physical_sha256": hashlib.sha256(THEORY_TEXT.encode()).hexdigest(),
        },
        markdown_utf8=THEORY_TEXT,
    )
    return document, _embedded(
        "theory",
        document,
        THEORY_DOCUMENT_SCHEMA_ID,
        THEORY_DOCUMENT_DIGEST_FIELD,
    )


def _agent_market_graph_view(*, run_id: str, cycle: int, as_of: str) -> dict:
    """Small intrinsic fixture; full upstream reconstruction is acceptance-owned."""

    return seal_v32_agent_market_graph_view_v1(
        {
            "schema_id": "theory_paper_v32_agent_market_graph_view_v1",
            "schema_version": AGENT_MARKET_VIEW_SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle,
            "as_of": as_of,
            "available_at": as_of,
            "instrument": {"instrument_id": "BTC-USDT-SWAP"},
            "upstream_digests": {
                "public_market_analysis_bundle_digest": "1" * 64,
                "public_market_graph_projection_digest": "2" * 64,
                "graph_dependency_registry_digest": "3" * 64,
                "pit_evidence_availability_registry_digest": "4" * 64,
            },
            "closed_bar_series": {
                "15M": [
                    {
                        "open_time": "2026-08-07T00:00:00Z",
                        "close_time": as_of,
                        "open": "60000",
                        "high": "60010",
                        "low": "59990",
                        "close": "60005",
                        "volume": "100",
                    }
                ]
            },
            "closed_bar_evidence": {
                "15M": {
                    "source_component_id": "CLOSED_CANDLES_15M",
                    "public_source_event_digest": "5" * 64,
                    "available_at": as_of,
                }
            },
            "current_non_bar_datums": [],
            "source_event_claim_ceilings": [],
            "axis_source_evidence": [],
            "citable_evidence_records": [],
            "evidence_dependency_policy": {},
            "graph_delta_summary": {
                "graph_delta_digest": "6" * 64,
                "base_graph_revision": 0,
                "base_graph_digest": None,
                "revision": 1,
                "occurred_at": as_of,
                "available_at": as_of,
                "node_revision_count": 0,
                "association_revision_count": 0,
                "dependency_group_ids": [],
            },
            "content_counts": {
                "closed_bar_count": 1,
                "current_non_bar_datum_count": 0,
                "source_event_count": 0,
                "axis_evidence_count": 0,
                "citable_evidence_count": 0,
                "durable_pit_member_count": 0,
            },
            "unknown_retained": True,
            "other_retained": True,
            "causal_claim": "NONE_PROVENANCE_ASSOCIATIONS_ONLY",
            "view_policy": dict(AGENT_MARKET_VIEW_POLICY),
            "canonical_payload_bytes": 0,
            "max_canonical_payload_bytes": AGENT_MARKET_VIEW_MAX_BYTES,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
        }
    )


def _formal_market_chain(
    *,
    run_id: str,
    cycle: int,
    decision_time: str,
    authority_projection: dict,
) -> dict:
    """Build/cache the exact raw-first source, graph, availability and Agent view."""

    cache_key = (
        run_id,
        cycle,
        authority_projection[ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD],
    )
    cached = _FORMAL_MARKET_CHAIN_CACHE.get(cache_key)
    if cached is not None:
        return deepcopy(cached)

    previous = None
    if cycle > 1:
        previous = _formal_market_chain(
            run_id=run_id,
            cycle=cycle - 1,
            decision_time="2026-08-07T00:15:00Z",
            authority_projection=authority_projection,
        )

    decision = datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
    base = decision - timedelta(seconds=6)
    old_base = collector_fixture.BASE
    old_server_ms = collector_fixture.SERVER_MS
    try:
        collector_fixture.BASE = base
        collector_fixture.SERVER_MS = int(
            (base + timedelta(seconds=3)).timestamp() * 1000
        )
        raw = collector_fixture.raw_bundle()
        clock = collector_fixture.SequenceClock()
    finally:
        collector_fixture.BASE = old_base
        collector_fixture.SERVER_MS = old_server_ms

    if previous is None:
        temporary = tempfile.TemporaryDirectory()
        _FORMAL_MARKET_TEMP_DIRS.append(temporary)
        root = Path(temporary.name)
        source_root = root / "source"
        run_root = root / "run"
    else:
        source_root = Path(previous["source_store_root"])
        run_root = Path(previous["run_store_root"])
    source_store = collector_fixture.RecordingStore(source_root)
    run_store = LocalV32CycleSourceAdmissionStore(run_root)
    qualification_id = f"q-{run_id.replace(':', '-')}-{cycle:04d}"
    collected = V32RawFirstOkxPublicBundleCollector(
        transport=collector_fixture.BundleTransport(raw),
        clock=clock,
        store=source_store,
    ).collect_and_qualify(
        qualification_id=qualification_id,
        run_id=run_id,
        cycle_index=cycle,
        active_authority=authority_projection,
    )
    prior = {}
    if previous is not None:
        prior_result = previous["admission_result"]
        prior = {
            "previous_cycle_source_admission_binding": prior_result[
                "cycle_source_admission_binding"
            ],
            "prior_snapshot_binding": prior_result["current_snapshot_binding"],
            "prior_open_interest_datum_digest": prior_result[
                "current_open_interest_datum_digest"
            ],
            "prior_open_interest_status": prior_result[
                "current_open_interest_status"
            ],
            "prior_open_interest_zero_imputed": False,
        }
    admission_result = admit_fresh_v32_source_to_cycle(
        source_store=source_store,
        run_store=run_store,
        active_authority=authority_projection,
        qualification_id=qualification_id,
        run_id=run_id,
        cycle_index=cycle,
        decision_time=decision_time,
        admitted_at=(decision + timedelta(microseconds=500_000))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        **prior,
    )
    replay_result = compose_and_persist_v32_durable_source_replay_receipt(
        public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
        source_store=source_store,
        run_store=run_store,
        active_authority=authority_projection,
        qualification_id=qualification_id,
        run_id=run_id,
        cycle_index=cycle,
        replayed_at=(decision + timedelta(seconds=2))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
    )

    analysis = collected.public_market_analysis_bundle
    previous_projection = None if previous is None else previous["graph_projection"]
    graph_projection = build_v32_public_market_graph_projection_v1(
        analysis,
        previous_projection=previous_projection,
    )
    if cycle == 1:
        graph_registry = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=graph_projection,
            analysis_bundle=analysis,
            decision_time=decision_time,
            previous_projection=previous_projection,
        )
    else:
        # Lifecycle cycle-2 tests exercise exact prior source bindings only.
        # Full cumulative graph transition is covered by the graph/acceptance
        # suites; use an intrinsic bounded view here to avoid duplicating that
        # large replay fixture in every lifecycle assertion.
        graph_registry = previous["graph_registry"]
    pit = collected.pit_registry
    availability = build_v32_verified_pit_evidence_availability_registry_v1(
        public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
        public_market_analysis_bundle=analysis,
        pit_evidence_registry=pit,
    )
    market_view = (
        build_v32_agent_market_graph_view_v1(
            public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
            public_market_analysis_bundle=analysis,
            public_market_graph_projection=graph_projection,
            pit_evidence_registry=pit,
            graph_dependency_registry=graph_registry,
            pit_evidence_availability_registry=availability,
            previous_public_market_graph_projection=previous_projection,
        )
        if cycle == 1
        else _agent_market_graph_view(
            run_id=run_id, cycle=cycle, as_of=decision_time
        )
    )
    result = {
        "analysis_bundle": analysis,
        "analysis_bundle_binding": collected.public_market_analysis_bundle_binding,
        "pit_registry": pit,
        "pit_registry_binding": collected.pit_registry_binding,
        "graph_projection": graph_projection,
        "graph_projection_binding": _embedded(
            "graph-projection",
            graph_projection,
            GRAPH_PROJECTION_SCHEMA_ID,
            GRAPH_PROJECTION_DIGEST_FIELD,
        ),
        "graph_registry": graph_registry,
        "graph_registry_binding": _embedded(
            "graph-registry",
            graph_registry,
            GRAPH_REGISTRY_SCHEMA_ID,
            GRAPH_REGISTRY_DIGEST_FIELD,
        ),
        "availability_registry": availability,
        "market_view": market_view,
        "admission_result": admission_result,
        "source_admission": admission_result["cycle_source_admission"],
        "source_admission_binding": admission_result[
            "cycle_source_admission_binding"
        ],
        "source_replay_receipt": replay_result[
            "durable_source_replay_receipt"
        ],
        "source_replay_receipt_binding": replay_result[
            "durable_source_replay_receipt_binding"
        ],
        "source_store_root": str(source_root),
        "run_store_root": str(run_root),
    }
    _FORMAL_MARKET_CHAIN_CACHE[cache_key] = deepcopy(result)
    return result
def _timeframe_genesis(
    *, run_id: str = RUN_ID, public_market_analysis_bundle: dict | None = None
) -> dict:
    original = cache_fixture._genesis()
    frames = original["frames"]
    if public_market_analysis_bundle is not None:
        payloads = project_v32_timeframe_payloads_v1(
            public_market_analysis_bundle
        )
        rebuilt = []
        for row in frames:
            role = row["role"]
            policy = project_v32_refreshed_frame_policy_v1(
                role=role,
                run_id=run_id,
                decision_time=original["decision_time"],
                public_market_analysis_bundle=public_market_analysis_bundle,
            )
            rebuilt.append(
                build_v32_context_frame_v1(
                    frame_id=policy["frame_id"],
                    role=role,
                    update_mode="REFRESHED",
                    created_at=policy["created_at"],
                    as_of=policy["as_of"],
                    available_at=policy["available_at"],
                    expires_at=policy["expires_at"],
                    payload_digest=canonical_digest(payloads[role]),
                    source_refs=policy["source_refs"],
                    dependency_groups=policy["dependency_groups"],
                    invalidation_event_types=policy[
                        "invalidation_event_types"
                    ],
                    previous_frame=None,
                    decision_time=original["decision_time"],
                )
            )
        frames = rebuilt
    return build_v32_timeframe_context_state_v1(
        run_id=run_id,
        cycle_index=1,
        decision_time=original["decision_time"],
        state_mode="FULL_CONTEXT",
        previous_state=None,
        frames=frames,
        observed_invalidation_events=[],
    )


def _timeframe_delta(
    previous: dict,
    *,
    run_id: str = RUN_ID,
    public_market_analysis_bundle: dict | None = None,
) -> dict:
    # The reused fixture has its own outer run id.  Frame digests are run-id
    # independent, so build its exact transition first and then rebuild the
    # outer state against this test's exact predecessor.
    original = cache_fixture._delta(cache_fixture._genesis())
    frames = original["frames"]
    if public_market_analysis_bundle is not None:
        payloads = project_v32_timeframe_payloads_v1(
            public_market_analysis_bundle
        )
        prior = {row["role"]: row for row in previous["frames"]}
        rebuilt = []
        for row in frames:
            role = row["role"]
            expected = canonical_digest(payloads[role])
            previous_frame = prior[role]
            carry = role == "STRATEGIC_CONTEXT" and previous_frame[
                "payload_digest"
            ] == expected
            policy = project_v32_refreshed_frame_policy_v1(
                role=role,
                run_id=run_id,
                decision_time=original["decision_time"],
                public_market_analysis_bundle=public_market_analysis_bundle,
            )
            rebuilt.append(
                build_v32_context_frame_v1(
                    frame_id=(
                        previous_frame["frame_id"]
                        if carry
                        else policy["frame_id"]
                    ),
                    role=role,
                    update_mode="CARRIED_FORWARD" if carry else "REFRESHED",
                    created_at=(
                        previous_frame["created_at"]
                        if carry
                        else policy["created_at"]
                    ),
                    as_of=(
                        previous_frame["as_of"]
                        if carry
                        else policy["as_of"]
                    ),
                    available_at=(
                        previous_frame["available_at"]
                        if carry
                        else policy["available_at"]
                    ),
                    expires_at=(
                        previous_frame["expires_at"]
                        if carry
                        else policy["expires_at"]
                    ),
                    payload_digest=(
                        previous_frame["payload_digest"] if carry else expected
                    ),
                    source_refs=(
                        previous_frame["source_refs"]
                        if carry
                        else policy["source_refs"]
                    ),
                    dependency_groups=(
                        previous_frame["dependency_groups"]
                        if carry
                        else policy["dependency_groups"]
                    ),
                    invalidation_event_types=(
                        previous_frame["invalidation_event_types"]
                        if carry
                        else policy["invalidation_event_types"]
                    ),
                    previous_frame=previous_frame,
                    decision_time=original["decision_time"],
                )
            )
        frames = rebuilt
    return build_v32_timeframe_context_state_v1(
        run_id=run_id,
        cycle_index=2,
        decision_time=original["decision_time"],
        state_mode="DELTA_UPDATE",
        previous_state=previous,
        frames=frames,
        observed_invalidation_events=[],
    )


def _verified_policy_documents(
    *, run_id: str = RUN_ID
) -> tuple[dict, dict, dict, dict]:
    association = build_v32_association_preregistration(
        run_scope_id=run_id,
        frozen_at="2026-08-07T00:00:00Z",
    )
    evaluation = build_v32_evaluation_contract(
        association_preregistration=association,
        run_scope_id=run_id,
        frozen_at="2026-08-07T00:00:00Z",
    )
    clock = build_v32_clock_and_tick_policy_v1(
        run_scope_id=run_id,
        frozen_at="2026-08-07T00:00:00Z",
    )
    adapter = build_v32_public_outcome_adapter_contract_v1(
        run_scope_id=run_id,
        frozen_at="2026-08-07T00:00:00Z",
    )
    return association, evaluation, clock, adapter


def _authorized_revision_support_documents(
    *, run_id: str = RUN_ID
) -> dict[str, dict]:
    frozen_at = "2026-08-07T00:00:00Z"
    context_policy = build_v32_context_compaction_policy_v1(
        policy_id="v32-agent-context-policy",
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    unknown_policy = build_v32_unknown_subjective_policy_v1(
        policy_id="v32-agent-unknown-policy",
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    data_gap_policy = build_v32_data_gap_manual_policy_v1(
        policy_id="v32-agent-data-gap-policy",
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    audit_policy = build_v32_cycle_audit_policy_v1(
        policy_id="v32-agent-audit-policy",
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    environment_profile = build_v32_environment_capability_profile_v1(
        profile_id="v32-agent-environment-profile",
        run_scope_id=run_id,
        frozen_at=frozen_at,
        capabilities=[
            {
                "category": category,
                "status": "AVAILABLE",
                "observed_value": f"fixture:{category}",
                "limit": "LOCAL_PUBLIC_NON_EXECUTABLE",
                "evidence_refs": [f"fixture:{category.lower()}"],
                "claim_ceiling": "CAPABILITY_ONLY",
            }
            for category in CAPABILITY_CATEGORIES
        ],
        localization_adapters=[],
    )
    components = {
        "context_compaction_policy": context_policy,
        "unknown_subjective_policy": unknown_policy,
        "data_gap_manual_policy": data_gap_policy,
        "cycle_audit_policy": audit_policy,
        "environment_capability_profile": environment_profile,
    }
    component_bindings = {
        name: _embedded(name, document, *PROPOSAL_SUPPORT_SPECS[name])
        for name, document in components.items()
    }
    support_bundle = build_v32_authorized_revision_support_bundle_v1(
        support_bundle_id="v32-agent-support-bundle",
        run_scope_id=run_id,
        frozen_at=frozen_at,
        context_compaction_policy=context_policy,
        context_compaction_policy_binding=component_bindings[
            "context_compaction_policy"
        ],
        unknown_subjective_policy=unknown_policy,
        unknown_subjective_policy_binding=component_bindings[
            "unknown_subjective_policy"
        ],
        data_gap_manual_policy=data_gap_policy,
        data_gap_manual_policy_binding=component_bindings[
            "data_gap_manual_policy"
        ],
        cycle_audit_policy=audit_policy,
        cycle_audit_policy_binding=component_bindings["cycle_audit_policy"],
        environment_capability_profile=environment_profile,
        environment_capability_profile_binding=component_bindings[
            "environment_capability_profile"
        ],
    )
    recovery_policy = build_v32_recovery_supervision_policy_v1(
        policy_id="v32-agent-recovery-policy", frozen_at=frozen_at
    )
    return {
        **components,
        "authorized_revision_support_bundle": support_bundle,
        "recovery_supervision_policy": recovery_policy,
    }


def _build_proposal_packet(
    *,
    cycle: int = 1,
    profile: str = V32_TARGET_CONTEXT_PROFILE,
    matured_receipts: list[dict] | None = None,
) -> dict:
    qualification_context = profile == V32_QUALIFICATION_CONTEXT_PROFILE
    packet_run_id = "v32-qualification-run" if qualification_context else RUN_ID
    authority_profile = (
        QUALIFICATION_PROFILE if qualification_context else TARGET_PROFILE
    )
    theory, theory_binding = _theory()
    sentiment_registry = build_v31_native_sentiment_source_registry()
    association, evaluation, clock, adapter = _verified_policy_documents()
    revision_supports = _authorized_revision_support_documents()
    experiment = build_v32_experiment_contract_v1(
        contract_id="v32-contract-test",
        run_id=RUN_ID,
        frozen_at="2026-08-07T00:00:00Z",
        theory_relative_ref="theory/current/V3_2_DYNAMIC_AGGRESSIVE.md",
        theory_physical_sha256=theory["physical_sha256"],
        theory_semantic_digest=theory[THEORY_DOCUMENT_DIGEST_FIELD],
        support_bindings={
            **{key: "e" * 64 for key in SUPPORT_BINDING_KEYS},
            "association_preregistration_digest": association[
                ASSOCIATION_PREREGISTRATION_DIGEST_FIELD
            ],
            "evaluation_contract_digest": evaluation[
                EVALUATION_CONTRACT_DIGEST_FIELD
            ],
            "clock_policy_digest": clock["clock_policy_digest"],
            "outcome_adapter_contract_digest": adapter[
                "outcome_adapter_contract_digest"
            ],
            "twelve_axis_source_registry_digest": sentiment_registry[
                "registry_digest"
            ],
            "authorized_revision_support_bundle_digest": revision_supports[
                "authorized_revision_support_bundle"
            ]["authorized_revision_support_bundle_digest"],
            "recovery_supervision_policy_digest": revision_supports[
                "recovery_supervision_policy"
            ]["recovery_supervision_policy_digest"],
        },
    )
    authority_document = _authority_document(
        profile=authority_profile,
        run_id=packet_run_id,
        target_run_id=RUN_ID,
        experiment_contract=experiment,
    )
    authority_binding = _embedded(
        f"authority-{authority_profile.lower()}",
        authority_document,
        AUTHORITY_SCHEMA_ID,
        AUTHORITY_DIGEST_FIELD,
    )
    authority_projection = build_v32_active_authority_projection(
        run_id=packet_run_id,
        recorded_at="2026-08-07T00:13:00Z",
        experiment_contract_digest=experiment[EXPERIMENT_DIGEST_FIELD],
        governing_authority_binding=authority_binding,
    )
    previous_dynamic = None
    previous_action = None
    previous_timeframe = None
    decision = (
        "2026-08-07T00:15:00Z"
        if cycle == 1
        else "2026-08-07T00:30:00Z"
    )
    mode = "FULL_CONTEXT" if cycle == 1 else "DELTA_CONTEXT"
    if cycle > 1:
        previous_dynamic = action_fixture._dynamic_state()
        previous_action = build_v32_dynamic_action_plan_v1(
            **action_fixture._flat_args(dynamic_state=previous_dynamic)
        )
    market_chain = _formal_market_chain(
        run_id=packet_run_id,
        cycle=cycle,
        decision_time=decision,
        authority_projection=authority_projection,
    )
    if cycle == 1:
        timeframe = _timeframe_genesis(
            run_id=packet_run_id,
            public_market_analysis_bundle=market_chain["analysis_bundle"],
        )
    else:
        previous_market_chain = _formal_market_chain(
            run_id=packet_run_id,
            cycle=cycle - 1,
            decision_time="2026-08-07T00:15:00Z",
            authority_projection=authority_projection,
        )
        previous_timeframe = _timeframe_genesis(
            run_id=packet_run_id,
            public_market_analysis_bundle=previous_market_chain[
                "analysis_bundle"
            ],
        )
        timeframe = _timeframe_delta(
            previous_timeframe,
            run_id=packet_run_id,
            public_market_analysis_bundle=market_chain["analysis_bundle"],
        )
    source = market_chain["source_admission"]
    market_view = market_chain["market_view"]
    documents = {
        "active_authority_projection": authority_projection,
        "experiment_contract": experiment,
        "timeframe_context_state": timeframe,
        "agent_market_graph_view": market_view,
        "twelve_axis_source_registry": sentiment_registry,
        "association_preregistration": association,
        "evaluation_contract": evaluation,
        "clock_and_tick_policy": clock,
        "outcome_adapter_contract": adapter,
        "cycle_source_admission": source,
        **revision_supports,
    }
    bindings = {
        name: _embedded(name, document, *PROPOSAL_SUPPORT_SPECS[name])
        for name, document in documents.items()
    }
    return build_v32_proposal_canonical_packet_v1(
        run_id=packet_run_id,
        cycle_index=cycle,
        context_profile=profile,
        context_mode=mode,
        prepared_at=(
            "2026-08-07T00:14:30Z"
            if cycle == 1
            else "2026-08-07T00:29:30Z"
        ),
        decision_time=decision,
        authority_document=authority_document,
        authority_binding=authority_binding,
        theory_semantic_document=theory,
        theory_semantic_document_binding=theory_binding,
        support_documents=documents,
        support_bindings=bindings,
        previous_dynamic_research_state=previous_dynamic,
        previous_dynamic_research_state_binding=(
            None
            if previous_dynamic is None
            else _embedded(
                "previous-dynamic",
                previous_dynamic,
                "theory_paper_v32_dynamic_research_state_v1",
                "dynamic_research_state_digest",
            )
        ),
        previous_dynamic_action_plan=previous_action,
        previous_dynamic_action_plan_binding=(
            None
            if previous_action is None
            else _embedded(
                "previous-action",
                previous_action,
                "theory_paper_v32_dynamic_action_plan_v1",
                "dynamic_action_plan_digest",
            )
        ),
        previous_timeframe_context_state=previous_timeframe,
        previous_timeframe_context_state_binding=(
            None
            if previous_timeframe is None
            else _embedded(
                "previous-timeframe",
                previous_timeframe,
                "theory_paper_v32_timeframe_context_state_v1",
                "timeframe_context_state_digest",
            )
        ),
        matured_outcome_receipts=matured_receipts or [],
        matured_outcome_receipt_bindings=[
            _embedded(
                f"matured-outcome-{index}",
                receipt,
                "theory_paper_v32_public_market_outcome_receipt_v1",
                "public_market_outcome_receipt_digest",
            )
            for index, receipt in enumerate(matured_receipts or [])
        ],
    )


def _proposal_packet(
    *,
    cycle: int = 1,
    profile: str = V32_TARGET_CONTEXT_PROFILE,
    matured_receipts: list[dict] | None = None,
) -> dict:
    """Return isolated clones for the two common immutable fixture shapes."""
    cacheable = (
        cycle == 1
        and matured_receipts is None
        and profile
        in {V32_TARGET_CONTEXT_PROFILE, V32_QUALIFICATION_CONTEXT_PROFILE}
    )
    if not cacheable:
        return _build_proposal_packet(
            cycle=cycle,
            profile=profile,
            matured_receipts=matured_receipts,
        )
    cached = _PROPOSAL_PACKET_TEMPLATE_CACHE.get(profile)
    if cached is None:
        cached = _build_proposal_packet(
            cycle=cycle,
            profile=profile,
            matured_receipts=None,
        )
        _PROPOSAL_PACKET_TEMPLATE_CACHE[profile] = deepcopy(cached)
    return deepcopy(cached)


def _matured_outcome_receipt(
    *,
    available_at: str = "2026-08-07T00:15:30Z",
    resolved_at: str = "2026-08-07T00:16:00Z",
) -> dict:
    return self_digest(
        {
            "schema_id": "theory_paper_v32_public_market_outcome_receipt_v1",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "schedule_id": "schedule-cycle-1-15m",
            "schedule_digest": "1" * 64,
            "schedule_set_digest": "2" * 64,
            "decision_id": "decision-1",
            "cycle_index": 1,
            "horizon": "15M",
            "outcome_not_before": "2026-08-07T00:15:00Z",
            "batch_intent_digest": "3" * 64,
            "observation_tick_digest": "4" * 64,
            "raw_evidence_digest": "5" * 64,
            "resolved_at": resolved_at,
            "resolution_status": "OBSERVED",
            "coverage_loss_reason": None,
            "observable_ref": "metric:okx-public-mark-price-usdt",
            "value": "100000",
            "provider_as_of": "2026-08-07T00:15:20Z",
            "available_at": available_at,
            "quality": "HIGH",
            "missingness": "OBSERVED",
            "terminal": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "shared_tick_request": True,
            "observation_scope": "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE",
            "stop_trigger_semantics": "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL",
            "trigger_is_fill": False,
            "fill_claim": False,
            "position_claim": False,
            "pnl_claim": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "public_market_outcome_receipt_digest",
    )


def _stage_chain(stage: str, packet: dict, *, offset: str = "00:16"):
    packet_schema = (
        PROPOSAL_PACKET_SCHEMA_ID if stage == "PROPOSAL" else SELECTION_PACKET_SCHEMA_ID
    )
    packet_digest_field = (
        PROPOSAL_PACKET_DIGEST_FIELD
        if stage == "PROPOSAL"
        else SELECTION_PACKET_DIGEST_FIELD
    )
    packet_binding = _embedded(
        f"{stage.lower()}-packet", packet, packet_schema, packet_digest_field
    )
    context = build_v32_agent_input_context_v1(
        agent_stage=stage,
        canonical_packet=packet,
        canonical_packet_binding=packet_binding,
        created_at=f"2026-08-07T{offset}:00Z",
    )
    context_binding = _embedded(
        f"{stage.lower()}-context",
        context,
        AGENT_INPUT_CONTEXT_SCHEMA_ID,
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    delivery = build_v32_agent_delivery_v1(
        agent_input_context=context,
        agent_input_context_binding=context_binding,
        reserved_at=f"2026-08-07T{offset}:10Z",
        delivered_at=f"2026-08-07T{offset}:20Z",
        payload_utf8=f'{{"stage":"{stage}","语言":"中文"}}',
    )
    delivery_binding = _embedded(
        f"{stage.lower()}-delivery",
        delivery,
        AGENT_DELIVERY_SCHEMA_ID,
        AGENT_DELIVERY_DIGEST_FIELD,
    )
    consumption = build_v32_agent_consumption_v1(
        agent_input_context=context,
        agent_input_context_binding=context_binding,
        agent_delivery=delivery,
        agent_delivery_binding=delivery_binding,
        consumed_at=f"2026-08-07T{offset}:30Z",
    )
    consumption_binding = _embedded(
        f"{stage.lower()}-consumption",
        consumption,
        AGENT_CONSUMPTION_SCHEMA_ID,
        AGENT_CONSUMPTION_DIGEST_FIELD,
    )
    return context, context_binding, delivery, delivery_binding, consumption, consumption_binding


def _risk_arithmetic() -> dict[str, str]:
    return {
        "reference_risk_upper_bound": "1",
        "subjective_plausibility_tier": "HIGH",
        "residual_uncertainty_tier": "LOW",
        "agent_reference_risk_ceiling": "0.5",
        "calculation_policy": (
            "AGENT_CEILING_ONLY_UPPER_BOUND_TIMES_MIN_SUBJECTIVE_TIER_CAP_"
            "AND_COMPLEMENT_OF_RESIDUAL_UNCERTAINTY_TIER_DERIVED_BY_"
            "SEALED_PLAN"
        ),
    }


def _candidate_rows(reference_context: str) -> list[dict]:
    risk_digest = canonical_digest(_risk_arithmetic())
    rows = []
    for index, (action, direction) in enumerate(
        legal_v32_dynamic_action_keys_v1(reference_context)
    ):
        rows.append(
            {
                "candidate_id": f"candidate-{index}-{action.lower()}-{direction.lower()}",
                "action_kind": action,
                "direction": direction,
                "action_key": f"{action}:{direction}",
                "feasibility": "ELIGIBLE",
                "block_reasons": ["NONE"],
                "evidence_refs": [f"evidence:{action.lower()}:{direction.lower()}"],
                "risk_reference_units": (
                    "0.2" if action in {"OPEN_PROBE", "ADD", "REENTER", "REVERSE"} else "0"
                ),
                "risk_arithmetic_digest": risk_digest,
            }
        )
    return rows


def _full_lifecycle():
    proposal_packet = _proposal_packet()
    proposal = _stage_chain("PROPOSAL", proposal_packet)
    proposal_context, proposal_context_binding, proposal_delivery, proposal_delivery_binding, proposal_consumption, proposal_consumption_binding = proposal
    dynamic = action_fixture._dynamic_state()
    dynamic_binding = _embedded(
        "compiled-dynamic",
        dynamic,
        "theory_paper_v32_dynamic_research_state_v1",
        "dynamic_research_state_digest",
    )
    evaluation = build_v32_action_evaluation_v1(
        run_id=RUN_ID,
        cycle_index=1,
        evaluated_at="2026-08-07T00:16:40Z",
        proposal_consumption_digest=proposal_consumption[
            AGENT_CONSUMPTION_DIGEST_FIELD
        ],
        compiled_dynamic_state_digest=dynamic["dynamic_research_state_digest"],
        reference_context="FLAT_RESEARCH_INTENT",
        risk_arithmetic=_risk_arithmetic(),
        candidate_rows=_candidate_rows("FLAT_RESEARCH_INTENT"),
    )
    evaluation_binding = _embedded(
        "action-evaluation",
        evaluation,
        ACTION_EVALUATION_SCHEMA_ID,
        ACTION_EVALUATION_DIGEST_FIELD,
    )
    selection_packet = build_v32_selection_canonical_packet_v1(
        proposal_input_context=proposal_context,
        proposal_input_context_binding=proposal_context_binding,
        proposal_delivery=proposal_delivery,
        proposal_delivery_binding=proposal_delivery_binding,
        proposal_consumption=proposal_consumption,
        proposal_consumption_binding=proposal_consumption_binding,
        compiled_dynamic_research_state=dynamic,
        compiled_dynamic_research_state_binding=dynamic_binding,
        sealed_action_evaluation=evaluation,
        sealed_action_evaluation_binding=evaluation_binding,
        prepared_at="2026-08-07T00:16:45Z",
    )
    selection = _stage_chain("SELECTION", selection_packet, offset="00:17")
    action = build_v32_dynamic_action_plan_v1(
        **action_fixture._flat_args(dynamic_state=dynamic)
    )
    action_binding = _embedded(
        "final-action",
        action,
        "theory_paper_v32_dynamic_action_plan_v1",
        "dynamic_action_plan_digest",
    )
    experiment = proposal_packet["support_documents"]["experiment_contract"]
    schedule = build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id="decision-1",
        cycle_index=1,
        decision_time=proposal_packet["decision_time"],
        scheduled_at="2026-08-07T00:17:40Z",
        sealed_decision_digest=action["dynamic_action_plan_digest"],
        evaluation_contract_digest=experiment["support_bindings"][
            "evaluation_contract_digest"
        ],
    )
    schedule_binding = _embedded(
        "outcome-schedule",
        schedule,
        "theory_paper_v32_outcome_schedule_set_v1",
        "outcome_schedule_set_digest",
    )
    return proposal_packet, proposal, selection_packet, selection, action, action_binding, schedule, schedule_binding


class V32AgentLifecycleFixtureCacheTests(unittest.TestCase):
    def test_common_packets_are_cached_by_profile_and_return_isolated_clones(
        self,
    ) -> None:
        saved = deepcopy(_PROPOSAL_PACKET_TEMPLATE_CACHE)
        _PROPOSAL_PACKET_TEMPLATE_CACHE.clear()

        def fake_builder(*, cycle, profile, matured_receipts):
            return {
                "cycle": cycle,
                "profile": profile,
                "matured": deepcopy(matured_receipts),
                "nested": {"value": "original"},
            }

        try:
            with patch(
                f"{__name__}._build_proposal_packet", side_effect=fake_builder
            ) as builder:
                first = _proposal_packet()
                first["nested"]["value"] = "mutated"
                second = _proposal_packet()
                qualification_first = _proposal_packet(
                    profile=V32_QUALIFICATION_CONTEXT_PROFILE
                )
                qualification_second = _proposal_packet(
                    profile=V32_QUALIFICATION_CONTEXT_PROFILE
                )
                _proposal_packet(cycle=2)
                _proposal_packet(cycle=2)
                _proposal_packet(matured_receipts=[{"receipt": "matured"}])

            self.assertEqual("original", second["nested"]["value"])
            self.assertIsNot(first, second)
            self.assertIsNot(qualification_first, qualification_second)
            self.assertEqual(V32_TARGET_CONTEXT_PROFILE, second["profile"])
            self.assertEqual(
                V32_QUALIFICATION_CONTEXT_PROFILE,
                qualification_second["profile"],
            )
            self.assertEqual(5, builder.call_count)
        finally:
            _PROPOSAL_PACKET_TEMPLATE_CACHE.clear()
            _PROPOSAL_PACKET_TEMPLATE_CACHE.update(saved)


class _FlippingMapping(Mapping[str, object]):
    """Expose one mapping on first iteration and a different one afterwards."""

    def __init__(self, before: dict, after: dict) -> None:
        self._before = before
        self._after = after
        self._iterations = 0

    def __iter__(self) -> Iterator[str]:
        self._iterations += 1
        return iter(self._before if self._iterations == 1 else self._after)

    def __len__(self) -> int:
        return len(self._before if self._iterations <= 1 else self._after)

    def __getitem__(self, key: str) -> object:
        source = self._before if self._iterations <= 1 else self._after
        return source[key]


class V32AgentLifecycleMemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        packet = _proposal_packet()
        chain = _stage_chain("PROPOSAL", packet)
        cls.context = chain[0]
        cls.delivery = chain[2]

    def test_lifecycle_memo_is_scope_local_content_bound_and_failures_are_not_cached(
        self,
    ) -> None:
        context = self.context
        delivery = self.delivery
        original_builder = lifecycle.build_v32_agent_delivery_v1
        with patch.object(
            lifecycle,
            "build_v32_agent_delivery_v1",
            wraps=original_builder,
        ) as builder:
            with v32_lifecycle_verification_scope_v1():
                verify_v32_agent_delivery_v1(
                    delivery, agent_input_context=context
                )
                with v32_lifecycle_verification_scope_v1():
                    verify_v32_agent_delivery_v1(
                        delivery, agent_input_context=context
                    )
                self.assertEqual(builder.call_count, 1)

                same_digest_tamper = deepcopy(delivery)
                same_digest_tamper["payload_utf8"] += "tamper"
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        same_digest_tamper,
                        agent_input_context=context,
                    )
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        same_digest_tamper,
                        agent_input_context=context,
                    )

                resigned_binding_tamper = deepcopy(delivery)
                resigned_binding_tamper["agent_input_context_binding"][
                    "physical_sha256"
                ] = "0" * 64
                resigned_binding_tamper = self_digest(
                    resigned_binding_tamper,
                    AGENT_DELIVERY_DIGEST_FIELD,
                )
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        resigned_binding_tamper,
                        agent_input_context=context,
                    )
                failed_call_count = builder.call_count
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        resigned_binding_tamper,
                        agent_input_context=context,
                    )
                self.assertGreater(builder.call_count, failed_call_count)

                flipping_after = deepcopy(delivery)
                flipping_after["payload_utf8"] += "flip-after-key"
                flipping = _FlippingMapping(delivery, flipping_after)
                with patch.object(
                    lifecycle,
                    "verify_self_digest",
                    wraps=lifecycle.verify_self_digest,
                ) as self_digest_verifier:
                    with self.assertRaises(V32AgentLifecycleError):
                        verify_v32_agent_delivery_v1(
                            flipping,
                            agent_input_context=context,
                        )
                    first_failure_calls = self_digest_verifier.call_count
                    with self.assertRaises(V32AgentLifecycleError):
                        verify_v32_agent_delivery_v1(
                            _FlippingMapping(delivery, flipping_after),
                            agent_input_context=context,
                        )
                    self.assertGreater(
                        self_digest_verifier.call_count,
                        first_failure_calls,
                    )

            before_out_of_scope = builder.call_count
            verify_v32_agent_delivery_v1(
                delivery, agent_input_context=context
            )
            self.assertGreater(builder.call_count, before_out_of_scope)

    def test_lifecycle_memo_async_child_cannot_reuse_parent_scope(self) -> None:
        context = self.context
        delivery = self.delivery
        original_builder = lifecycle.build_v32_agent_delivery_v1

        async def scenario() -> None:
            child_ready = asyncio.Event()
            release_child = asyncio.Event()

            async def child() -> None:
                child_ready.set()
                await release_child.wait()
                verify_v32_agent_delivery_v1(
                    delivery, agent_input_context=context
                )

            with v32_lifecycle_verification_scope_v1():
                verify_v32_agent_delivery_v1(
                    delivery, agent_input_context=context
                )
                task = asyncio.create_task(child())
                await child_ready.wait()
            release_child.set()
            await task

        with patch.object(
            lifecycle,
            "build_v32_agent_delivery_v1",
            wraps=original_builder,
        ) as builder:
            asyncio.run(scenario())
            self.assertEqual(builder.call_count, 2)

    def test_lifecycle_memo_key_and_verifier_share_one_strict_snapshot(
        self,
    ) -> None:
        context = self.context
        delivery = deepcopy(self.delivery)
        delivery_before_mutation = deepcopy(delivery)
        original_builder = lifecycle.build_v32_agent_delivery_v1
        original_canonical_bytes = lifecycle.canonical_bytes
        key_completed = False

        def canonicalize_then_mutate_original(value):
            nonlocal key_completed
            encoded = original_canonical_bytes(value)
            if (
                not key_completed
                and type(value) is dict
                and set(value) == {"args", "kwargs"}
            ):
                key_completed = True
                delivery["payload_utf8"] += "mutated-after-key"
            return encoded

        with patch.object(
            lifecycle,
            "build_v32_agent_delivery_v1",
            wraps=original_builder,
        ) as builder, v32_lifecycle_verification_scope_v1(), patch.object(
            lifecycle,
            "canonical_bytes",
            side_effect=canonicalize_then_mutate_original,
        ):
            self.assertEqual(
                verify_v32_agent_delivery_v1(
                    delivery, agent_input_context=context
                ),
                delivery_before_mutation[AGENT_DELIVERY_DIGEST_FIELD],
            )
            self.assertTrue(key_completed)
            self.assertEqual(builder.call_count, 1)

            # The later mutation of the caller-owned dict cannot alter the
            # already-verified snapshot or its content key.
            verify_v32_agent_delivery_v1(
                delivery_before_mutation,
                agent_input_context=context,
            )
            self.assertEqual(builder.call_count, 1)

            with patch.object(
                lifecycle,
                "verify_self_digest",
                wraps=lifecycle.verify_self_digest,
            ) as self_digest_verifier:
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        delivery,
                        agent_input_context=context,
                    )
                first_failure_calls = self_digest_verifier.call_count
                with self.assertRaises(V32AgentLifecycleError):
                    verify_v32_agent_delivery_v1(
                        delivery,
                        agent_input_context=context,
                    )
                self.assertGreater(
                    self_digest_verifier.call_count,
                    first_failure_calls,
                )

    def test_lifecycle_memo_concurrent_tasks_have_independent_stores(self) -> None:
        context = self.context
        delivery = self.delivery
        original_builder = lifecycle.build_v32_agent_delivery_v1

        async def scenario() -> None:
            release = asyncio.Event()
            ready: list[bool] = []

            async def worker() -> None:
                with v32_lifecycle_verification_scope_v1():
                    ready.append(True)
                    if len(ready) == 2:
                        release.set()
                    await release.wait()
                    verify_v32_agent_delivery_v1(
                        delivery, agent_input_context=context
                    )
                    verify_v32_agent_delivery_v1(
                        delivery, agent_input_context=context
                    )

            await asyncio.gather(
                asyncio.create_task(worker()),
                asyncio.create_task(worker()),
            )

        with patch.object(
            lifecycle,
            "build_v32_agent_delivery_v1",
            wraps=original_builder,
        ) as builder:
            asyncio.run(scenario())
            self.assertEqual(builder.call_count, 2)



class V32AgentLifecycleTests(unittest.TestCase):
    def test_inline_gate_uses_complete_input_not_a_stage_packet_magic_number(self):
        packet = _proposal_packet()
        packet_binding = _embedded(
            "proposal-packet-capacity",
            packet,
            PROPOSAL_PACKET_SCHEMA_ID,
            PROPOSAL_PACKET_DIGEST_FIELD,
        )
        context = build_v32_agent_input_context_v1(
            agent_stage="PROPOSAL",
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
            created_at=packet["prepared_at"],
        )
        packet_bytes = len(canonical_bytes(packet))
        context_bytes = len(canonical_bytes(context))
        self.assertEqual(
            MAX_PROPOSAL_CANONICAL_PACKET_BYTES,
            MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES,
        )
        self.assertLess(packet_bytes, context_bytes)
        self.assertLessEqual(context_bytes, MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES)
        self.assertEqual("INLINE", context["context_delivery_mode"])
        # A packet may be below the configured total while the complete input
        # wrapper is above it.  Only the latter is the admission truth.
        between = packet_bytes + ((context_bytes - packet_bytes) // 2)
        with patch.object(
            lifecycle, "MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES", between
        ), self.assertRaisesRegex(
            V32AgentLifecycleError, "CONTEXT_CAPACITY_UNRESOLVED"
        ):
            build_v32_agent_input_context_v1(
                agent_stage="PROPOSAL",
                canonical_packet=packet,
                canonical_packet_binding=packet_binding,
                created_at=packet["prepared_at"],
            )

    def test_action_risk_uses_residual_tier_complement_and_rejects_legacy_quality(
        self,
    ) -> None:
        risk = _risk_arithmetic()
        evaluation = build_v32_action_evaluation_v1(
            run_id=RUN_ID,
            cycle_index=1,
            evaluated_at="2026-08-07T00:16:40Z",
            proposal_consumption_digest="a" * 64,
            compiled_dynamic_state_digest="b" * 64,
            reference_context="FLAT_RESEARCH_INTENT",
            risk_arithmetic=risk,
            candidate_rows=_candidate_rows("FLAT_RESEARCH_INTENT"),
        )
        self.assertEqual(
            "LOW", evaluation["risk_arithmetic"]["residual_uncertainty_tier"]
        )
        self.assertEqual(
            "0.5",
            evaluation["risk_arithmetic"]["agent_reference_risk_ceiling"],
        )

        legacy = deepcopy(risk)
        legacy["residual_uncertainty_quality"] = legacy.pop(
            "residual_uncertainty_tier"
        )
        with self.assertRaisesRegex(
            V32AgentLifecycleError,
            "V32_AGENT_ACTION_EVALUATION_RISK_INVALID",
        ):
            build_v32_action_evaluation_v1(
                run_id=RUN_ID,
                cycle_index=1,
                evaluated_at="2026-08-07T00:16:40Z",
                proposal_consumption_digest="a" * 64,
                compiled_dynamic_state_digest="b" * 64,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=legacy,
                candidate_rows=_candidate_rows("FLAT_RESEARCH_INTENT"),
            )

    def test_complete_theory_uses_exact_utf8_bytes(self) -> None:
        theory, _ = _theory()
        self.assertEqual(
            verify_v32_theory_semantic_document_v1(theory),
            theory[THEORY_DOCUMENT_DIGEST_FIELD],
        )
        drifted = deepcopy(theory)
        drifted["markdown_utf8"] += "篡改"
        drifted = self_digest(drifted, THEORY_DOCUMENT_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "THEORY_BYTES_MISMATCH"):
            verify_v32_theory_semantic_document_v1(drifted)

    def test_market_view_closure_index_is_exact_and_tamper_evident(self) -> None:
        expanded = [
            {
                "evidence_digest": "a" * 64,
                "available_at": "2026-08-07T00:15:00Z",
                "closure_status": "VERIFIED_COMPLETE_GRAPH_CLOSURE",
                "evidence_refs": ["analysis:information-event:candles"],
                "node_ids": ["node:candles"],
                "association_ids": [
                    "provenance:event-to-datum:bar-15m-1786174200000-close",
                    "provenance:event-to-datum:bar-15m-1786174200000-return-pct",
                    "provenance:event-to-axis:CLOSED_CANDLES_15M:OTHER",
                ],
                "dependency_group_ids": [
                    "BAR:15M:1786174200000",
                    "AXIS:OTHER",
                    "UNKNOWN:LIQUIDATIONS",
                ],
            },
            {
                "evidence_digest": "b" * 64,
                "available_at": "2026-08-07T00:15:00Z",
                "closure_status": "VERIFIED_COMPLETE_GRAPH_CLOSURE",
                "evidence_refs": ["analysis:datum:open-interest"],
                "node_ids": ["node:open-interest"],
                "association_ids": [
                    "provenance:event-to-datum:open-interest-btc"
                ],
                "dependency_group_ids": [
                    "AXIS:OTHER",
                    "UNKNOWN:LIQUIDATIONS",
                ],
            },
        ]
        closure_index = [
            project_v32_agent_market_graph_closure_record_v1(row)
            for row in expanded
        ]
        view = _agent_market_graph_view(
            run_id=RUN_ID, cycle=1, as_of="2026-08-07T00:15:00Z"
        )
        candidate = dict(view)
        candidate.pop("agent_market_graph_view_digest")
        candidate["citable_evidence_records"] = closure_index
        candidate["content_counts"] = {
            **candidate["content_counts"],
            "citable_evidence_count": len(expanded),
        }
        view = seal_v32_agent_market_graph_view_v1(candidate)
        self.assertEqual(
            view["citable_evidence_records"], closure_index
        )
        self.assertEqual(
            view["citable_evidence_records"][0]["dependency_group_ids"],
            expanded[0]["dependency_group_ids"],
        )
        self.assertEqual(
            view["citable_evidence_records"][0]["exact_closure_digest"],
            canonical_digest(expanded[0]),
        )
        self.assertTrue(view["unknown_retained"])
        self.assertTrue(view["other_retained"])
        tampered = deepcopy(view)
        tampered["citable_evidence_records"][0][
            "dependency_group_id_count"
        ] += 1
        tampered = self_digest(tampered, "agent_market_graph_view_digest")
        with self.assertRaisesRegex(
            ValueError, "MARKET_GRAPH_VIEW_INVALID"
        ):
            verify_v32_agent_market_graph_view_intrinsic_v1(tampered)

    def test_market_view_owning_replay_rejects_closure_digest_forgery(
        self,
    ) -> None:
        packet = _proposal_packet()
        chain = _formal_market_chain(
            run_id=packet["run_id"],
            cycle=1,
            decision_time=packet["decision_time"],
            authority_projection=packet["support_documents"][
                "active_authority_projection"
            ],
        )
        forged = deepcopy(chain["market_view"])
        forged["citable_evidence_records"][0]["exact_closure_digest"] = (
            "f" * 64
        )
        forged = self_digest(forged, "agent_market_graph_view_digest")
        verify_v32_agent_market_graph_view_intrinsic_v1(forged)
        with self.assertRaisesRegex(
            ValueError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_agent_market_graph_view_v1(
                forged,
                public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
                public_market_analysis_bundle=chain["analysis_bundle"],
                public_market_graph_projection=chain["graph_projection"],
                pit_evidence_registry=chain["pit_registry"],
                graph_dependency_registry=chain["graph_registry"],
                pit_evidence_availability_registry=chain[
                    "availability_registry"
                ],
                previous_public_market_graph_projection=None,
            )

    def test_proposal_packet_has_exact_predecision_support_and_no_current_outputs(self) -> None:
        packet = _proposal_packet()
        self.assertEqual(
            verify_v32_proposal_canonical_packet_v1(packet),
            packet[PROPOSAL_PACKET_DIGEST_FIELD],
        )
        self.assertEqual(set(packet["support_documents"]), set(PROPOSAL_SUPPORT_SPECS))
        self.assertNotIn("dynamic_research_state", packet["support_documents"])
        self.assertNotIn("dynamic_action_plan", packet["support_documents"])
        self.assertNotIn("outcome_schedule_set", packet["support_documents"])
        self.assertIn("agent_market_graph_view", packet["support_documents"])
        self.assertIn(
            "HOLD",
            packet["support_documents"]["experiment_contract"]["action_policy"][
                "legal_research_actions"
            ],
        )
        supports = packet["support_documents"]
        self.assertFalse(
            supports["context_compaction_policy"][
                "top_k_or_truncation_allowed"
            ]
        )
        self.assertEqual(
            supports["context_compaction_policy"]["capacity_failure_status"],
            "CONTEXT_CAPACITY_UNRESOLVED",
        )
        self.assertFalse(
            supports["unknown_subjective_policy"][
                "objective_zero_imputation_allowed"
            ]
        )
        self.assertFalse(
            supports["unknown_subjective_policy"][
                "subjective_assessment_may_replace_objective_unknown"
            ]
        )
        self.assertEqual(
            supports["data_gap_manual_policy"]["failure_value_status"],
            "UNKNOWN",
        )
        self.assertFalse(
            supports["data_gap_manual_policy"]["historical_backfill_allowed"]
        )
        self.assertTrue(
            supports["environment_capability_profile"]["theory_core_unchanged"]
        )
        self.assertEqual(
            supports["recovery_supervision_policy"]["supervisor_role"],
            "READ_ONLY_INDEPENDENT_OBSERVER",
        )
        self.assertFalse(
            supports["recovery_supervision_policy"][
                "supervisor_may_mutate_state"
            ]
        )
        self.assertNotIn("workspace_freeze_receipt", supports)
        self.assertLessEqual(
            len(canonical_bytes(packet)), MAX_PROPOSAL_CANONICAL_PACKET_BYTES
        )

    def test_new_revision_support_missing_or_digest_drift_fails_closed(self) -> None:
        packet = _proposal_packet()
        missing = deepcopy(packet)
        del missing["support_documents"]["context_compaction_policy"]
        del missing["support_bindings"]["context_compaction_policy"]
        missing["support_bindings_digest"] = canonical_digest(
            missing["support_bindings"]
        )
        missing = self_digest(missing, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "SUPPORT_SET"):
            verify_v32_proposal_canonical_packet_v1(missing)

        digest_drift = deepcopy(packet)
        digest_drift["support_bindings"]["recovery_supervision_policy"][
            "semantic_digest"
        ] = "0" * 64
        digest_drift["support_bindings_digest"] = canonical_digest(
            digest_drift["support_bindings"]
        )
        digest_drift = self_digest(
            digest_drift, PROPOSAL_PACKET_DIGEST_FIELD
        )
        with self.assertRaises(ValueError):
            verify_v32_proposal_canonical_packet_v1(digest_drift)

    def test_new_revision_support_semantic_and_aggregate_drift_fails_closed(self) -> None:
        packet = _proposal_packet()
        semantic_drift = deepcopy(packet)
        policy = semantic_drift["support_documents"][
            "context_compaction_policy"
        ]
        policy["top_k_or_truncation_allowed"] = True
        policy = self_digest(policy, "context_compaction_policy_digest")
        semantic_drift["support_documents"]["context_compaction_policy"] = policy
        semantic_drift["support_bindings"]["context_compaction_policy"] = _embedded(
            "context_compaction_policy",
            policy,
            *PROPOSAL_SUPPORT_SPECS["context_compaction_policy"],
        )
        semantic_drift["support_bindings_digest"] = canonical_digest(
            semantic_drift["support_bindings"]
        )
        semantic_drift = self_digest(
            semantic_drift, PROPOSAL_PACKET_DIGEST_FIELD
        )
        with self.assertRaises(ValueError):
            verify_v32_proposal_canonical_packet_v1(semantic_drift)

        aggregate_drift = deepcopy(packet)
        support = aggregate_drift["support_documents"][
            "authorized_revision_support_bundle"
        ]
        support["recovery_and_workspace_policies_included"] = True
        support = self_digest(
            support, "authorized_revision_support_bundle_digest"
        )
        aggregate_drift["support_documents"][
            "authorized_revision_support_bundle"
        ] = support
        aggregate_drift["support_bindings"][
            "authorized_revision_support_bundle"
        ] = _embedded(
            "authorized_revision_support_bundle",
            support,
            *PROPOSAL_SUPPORT_SPECS["authorized_revision_support_bundle"],
        )
        aggregate_drift["support_bindings_digest"] = canonical_digest(
            aggregate_drift["support_bindings"]
        )
        aggregate_drift = self_digest(
            aggregate_drift, PROPOSAL_PACKET_DIGEST_FIELD
        )
        with self.assertRaisesRegex(ValueError, "REVISION_SUPPORT_BUNDLE"):
            verify_v32_proposal_canonical_packet_v1(aggregate_drift)

    def test_revision_bundle_component_physical_binding_drift_fails_closed(self) -> None:
        packet = _proposal_packet()
        drifted = deepcopy(packet)
        support = drifted["support_documents"][
            "authorized_revision_support_bundle"
        ]
        support["components"][0]["binding"]["physical_sha256"] = "0" * 64
        support = self_digest(
            support, "authorized_revision_support_bundle_digest"
        )
        drifted["support_documents"][
            "authorized_revision_support_bundle"
        ] = support
        drifted["support_bindings"]["authorized_revision_support_bundle"] = (
            _embedded(
                "authorized_revision_support_bundle",
                support,
                *PROPOSAL_SUPPORT_SPECS[
                    "authorized_revision_support_bundle"
                ],
            )
        )
        drifted["support_bindings_digest"] = canonical_digest(
            drifted["support_bindings"]
        )
        drifted = self_digest(drifted, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "REVISION_SUPPORT_BUNDLE"):
            verify_v32_proposal_canonical_packet_v1(drifted)

    def test_proposal_rejects_final_action_or_schedule_as_support(self) -> None:
        packet = _proposal_packet()
        drifted = deepcopy(packet)
        drifted["support_documents"]["dynamic_action_plan"] = {"forbidden": True}
        drifted["support_bindings"]["dynamic_action_plan"] = _external_binding(
            "forbidden.json", "wrong", "wrong_digest", "0" * 64
        )
        drifted = self_digest(drifted, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "SUPPORT_SET"):
            verify_v32_proposal_canonical_packet_v1(drifted)

    def test_v31_admission_schema_cannot_impersonate_v32(self) -> None:
        packet = _proposal_packet()
        drifted = deepcopy(packet)
        source = drifted["support_documents"]["cycle_source_admission"]
        source["schema_id"] = "theory_paper_v31_cycle_source_admission"
        source = self_digest(source, SOURCE_ADMISSION_DIGEST_FIELD)
        drifted["support_documents"]["cycle_source_admission"] = source
        drifted["support_bindings"]["cycle_source_admission"] = _embedded(
            "wrong-v31-source",
            source,
            "theory_paper_v31_cycle_source_admission",
            SOURCE_ADMISSION_DIGEST_FIELD,
        )
        drifted = self_digest(drifted, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaises(ValueError):
            verify_v32_proposal_canonical_packet_v1(drifted)

    def test_v32_source_admission_and_refs_support_cycle_sixteen_only(self) -> None:
        previous = {
            "status": "BOUND_TO_PREVIOUS_ACCEPTED_V32_CYCLE",
            "previous_cycle_source_admission_binding": _external_binding(
                "cycles/0015/source.json",
                SOURCE_ADMISSION_SCHEMA_ID,
                SOURCE_ADMISSION_DIGEST_FIELD,
                "1" * 64,
            ),
            "prior_snapshot_binding": _external_binding(
                "cycles/0015/snapshot.json",
                "native_btc_public_market_snapshot",
                "native_market_snapshot_digest",
                "2" * 64,
            ),
            "prior_open_interest_datum_digest": "3" * 64,
            "prior_open_interest_status": "UNKNOWN",
            "prior_open_interest_zero_imputed": False,
        }
        source = _formal_source_admission(
            cycle=16,
            decision_time="2026-08-07T04:00:00Z",
            admitted_at="2026-08-07T03:59:00Z",
            experiment_contract_digest="0" * 64,
            pit_registry_binding=_external_binding(
                "cycles/0016/pit.json",
                PIT_REGISTRY_SCHEMA_ID,
                PIT_REGISTRY_DIGEST_FIELD,
                "5" * 64,
            ),
            previous_source_context=previous,
            current_open_interest_status="UNKNOWN",
        )
        verify_v32_cycle_source_admission(source)
        self.assertIn("0016", agent_input_context_ref_v1(16, "PROPOSAL"))
        self.assertIn("0016", agent_delivery_ref_v1(16, "SELECTION"))
        self.assertIn("0016", agent_consumption_ref_v1(16, "SELECTION"))
        self.assertIn("0016", agent_commit_envelope_ref_v1(16))
        with self.assertRaises(ValueError):
            agent_input_context_ref_v1(17, "PROPOSAL")

    def test_cycle_two_binds_previous_state_plan_cache_and_source_triplet(self) -> None:
        packet = _proposal_packet(cycle=2)
        verify_v32_proposal_canonical_packet_v1(packet)
        self.assertEqual(packet["context_mode"], "DELTA_CONTEXT")
        self.assertIsNotNone(packet["previous_dynamic_research_state"])
        self.assertIsNotNone(packet["previous_dynamic_action_plan"])
        previous = packet["support_documents"]["cycle_source_admission"][
            "previous_source_context"
        ]
        self.assertEqual(
            previous["previous_cycle_source_admission_binding"]["schema_id"],
            SOURCE_ADMISSION_SCHEMA_ID,
        )
        self.assertRegex(
            previous["prior_snapshot_binding"]["semantic_digest"],
            r"^[0-9a-f]{64}$",
        )
        self.assertRegex(
            previous["prior_open_interest_datum_digest"], r"^[0-9a-f]{64}$"
        )

    def test_proposal_admits_only_already_matured_outcome_receipts(self) -> None:
        matured = _matured_outcome_receipt()
        packet = _proposal_packet(cycle=2, matured_receipts=[matured])
        verify_v32_proposal_canonical_packet_v1(packet)
        self.assertEqual(len(packet["matured_outcome_receipts"]), 1)
        self.assertFalse(packet["matured_outcome_receipts"][0]["trigger_is_fill"])

        future = _matured_outcome_receipt(
            available_at="2026-08-07T00:30:30Z",
            resolved_at="2026-08-07T00:30:40Z",
        )
        with self.assertRaisesRegex(ValueError, "MATURED_OUTCOME"):
            _proposal_packet(cycle=2, matured_receipts=[future])

    def test_support_version_digest_and_physical_bytes_fail_closed(self) -> None:
        packet = _proposal_packet()
        for mutation in ("version", "digest", "bytes"):
            drifted = deepcopy(packet)
            if mutation == "version":
                drifted["support_documents"]["association_preregistration"][
                    "schema_version"
                ] = "2.0.0"
                drifted["support_documents"]["association_preregistration"] = self_digest(
                    drifted["support_documents"]["association_preregistration"],
                    ASSOCIATION_PREREGISTRATION_DIGEST_FIELD,
                )
            elif mutation == "digest":
                drifted["support_bindings"]["evaluation_contract"][
                    "semantic_digest"
                ] = "0" * 64
            else:
                drifted["support_bindings"]["agent_market_graph_view"][
                    "physical_sha256"
                ] = "0" * 64
            drifted = self_digest(drifted, PROPOSAL_PACKET_DIGEST_FIELD)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_v32_proposal_canonical_packet_v1(drifted)

    def test_each_agent_stage_is_one_terminal_exact_utf8_delivery(self) -> None:
        _proposal_packet_value, proposal, selection_packet, selection, *_ = _full_lifecycle()
        for stage, chain in (("PROPOSAL", proposal), ("SELECTION", selection)):
            context, _context_binding, delivery, _delivery_binding, consumption, _ = chain
            self.assertEqual(context["agent_stage"], stage)
            verify_v32_agent_input_context_v1(context)
            verify_v32_agent_delivery_v1(delivery, agent_input_context=context)
            verify_v32_agent_consumption_v1(
                consumption,
                agent_input_context=context,
                agent_delivery=delivery,
            )
            self.assertEqual(delivery["attempt_number"], 1)
            self.assertEqual(delivery["max_attempts"], 1)
            self.assertFalse(delivery["retry_allowed"])
            self.assertTrue(consumption["terminal_delivery_verified"])
        self.assertFalse(selection_packet["future_outcome_visible"])

    def test_action_evaluation_forbids_preselected_plan_and_future_outcome(self) -> None:
        proposal_packet = _proposal_packet()
        proposal = _stage_chain("PROPOSAL", proposal_packet)
        proposal_consumption = proposal[4]
        for forbidden_key in (
            "selected_candidate_id",
            "future_outcome",
            "pnl",
        ):
            rows = _candidate_rows("FLAT_RESEARCH_INTENT")
            rows[0][forbidden_key] = "forbidden"
            with self.subTest(forbidden_key=forbidden_key), self.assertRaisesRegex(ValueError, "ACTION_EVALUATION"):
                build_v32_action_evaluation_v1(
                    run_id=RUN_ID,
                    cycle_index=1,
                    evaluated_at="2026-08-07T00:16:40Z",
                    proposal_consumption_digest=proposal_consumption[
                        AGENT_CONSUMPTION_DIGEST_FIELD
                    ],
                    compiled_dynamic_state_digest="a" * 64,
                    reference_context="FLAT_RESEARCH_INTENT",
                    risk_arithmetic=_risk_arithmetic(),
                    candidate_rows=rows,
                )

    def test_long_intent_action_grid_keeps_hold_distinct_from_wait(self) -> None:
        evaluation = build_v32_action_evaluation_v1(
            run_id=RUN_ID,
            cycle_index=1,
            evaluated_at="2026-08-07T00:16:40Z",
            proposal_consumption_digest="a" * 64,
            compiled_dynamic_state_digest="b" * 64,
            reference_context="LONG_RESEARCH_INTENT",
            risk_arithmetic=_risk_arithmetic(),
            candidate_rows=_candidate_rows("LONG_RESEARCH_INTENT"),
        )
        verify_v32_action_evaluation_v1(evaluation)
        keys = {row["action_key"] for row in evaluation["candidate_rows"]}
        self.assertIn("HOLD:LONG", keys)
        self.assertNotIn("WAIT:NONE", keys)

    def test_selection_packet_has_compiled_state_not_final_plan_or_schedule(self) -> None:
        _, _, selection_packet, _, *_ = _full_lifecycle()
        self.assertEqual(
            verify_v32_selection_canonical_packet_v1(selection_packet),
            selection_packet[SELECTION_PACKET_DIGEST_FIELD],
        )
        self.assertIn("compiled_dynamic_research_state", selection_packet)
        self.assertIn("sealed_action_evaluation", selection_packet)
        self.assertNotIn("final_dynamic_action_plan", selection_packet)
        self.assertNotIn("outcome_schedule_set", selection_packet)
        self.assertFalse(selection_packet["future_outcome_visible"])

    def test_selection_rejects_future_visibility_or_wrong_proposal_chain(self) -> None:
        _, _, selection_packet, _, *_ = _full_lifecycle()
        future = deepcopy(selection_packet)
        future["future_outcome_visible"] = True
        future = self_digest(future, SELECTION_PACKET_DIGEST_FIELD)
        with self.assertRaises(ValueError):
            verify_v32_selection_canonical_packet_v1(future)

        wrong = deepcopy(selection_packet)
        wrong["proposal_consumption"]["agent_stage"] = "SELECTION"
        wrong["proposal_consumption"] = self_digest(
            wrong["proposal_consumption"], AGENT_CONSUMPTION_DIGEST_FIELD
        )
        wrong = self_digest(wrong, SELECTION_PACKET_DIGEST_FIELD)
        with self.assertRaises(ValueError):
            verify_v32_selection_canonical_packet_v1(wrong)

    def test_commit_is_first_object_to_bind_final_plan_and_schedule(self) -> None:
        proposal_packet, proposal, selection_packet, selection, action, action_binding, schedule, schedule_binding = _full_lifecycle()
        proposal_context, _, proposal_delivery, _, proposal_consumption, _ = proposal
        selection_context, _, selection_delivery, _, selection_consumption, _ = selection
        commit = build_v32_two_stage_commit_envelope_v1(
            proposal_input_context=proposal_context,
            proposal_delivery=proposal_delivery,
            proposal_consumption=proposal_consumption,
            selection_input_context=selection_context,
            selection_delivery=selection_delivery,
            selection_consumption=selection_consumption,
            final_dynamic_action_plan=action,
            final_dynamic_action_plan_binding=action_binding,
            outcome_schedule_set=schedule,
            outcome_schedule_set_binding=schedule_binding,
            sealed_at="2026-08-07T00:17:50Z",
            previous_commit_envelope_digest=None,
        )
        self.assertEqual(
            verify_v32_two_stage_commit_envelope_v1(
                commit,
                proposal_input_context=proposal_context,
                proposal_delivery=proposal_delivery,
                proposal_consumption=proposal_consumption,
                selection_input_context=selection_context,
                selection_delivery=selection_delivery,
                selection_consumption=selection_consumption,
            ),
            commit[COMMIT_ENVELOPE_DIGEST_FIELD],
        )
        self.assertNotIn("outcome_schedule_set", proposal_packet)
        self.assertNotIn("outcome_schedule_set", selection_packet)
        self.assertIn("outcome_schedule_set", commit)
        self.assertIn("final_dynamic_action_plan", commit)
        self.assertFalse(commit["executable"])

    def test_commit_rejects_wrong_stage_or_action_schedule_binding(self) -> None:
        _, proposal, _, selection, action, action_binding, schedule, schedule_binding = _full_lifecycle()
        proposal_context, _, proposal_delivery, _, proposal_consumption, _ = proposal
        selection_context, _, selection_delivery, _, selection_consumption, _ = selection
        wrong_action_binding = deepcopy(action_binding)
        wrong_action_binding["semantic_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "FINAL_BINDING"):
            build_v32_two_stage_commit_envelope_v1(
                proposal_input_context=proposal_context,
                proposal_delivery=proposal_delivery,
                proposal_consumption=proposal_consumption,
                selection_input_context=selection_context,
                selection_delivery=selection_delivery,
                selection_consumption=selection_consumption,
                final_dynamic_action_plan=action,
                final_dynamic_action_plan_binding=wrong_action_binding,
                outcome_schedule_set=schedule,
                outcome_schedule_set_binding=schedule_binding,
                sealed_at="2026-08-07T00:17:50Z",
                previous_commit_envelope_digest=None,
            )

    def test_wrong_profile_authority_run_and_packet_digest_fail_closed(self) -> None:
        packet = _proposal_packet()
        profile = deepcopy(packet)
        profile["context_profile"] = V32_QUALIFICATION_CONTEXT_PROFILE
        profile = self_digest(profile, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "AUTHORITY"):
            verify_v32_proposal_canonical_packet_v1(profile)

        run = deepcopy(packet)
        run["run_id"] = "wrong-run"
        run = self_digest(run, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaises(ValueError):
            verify_v32_proposal_canonical_packet_v1(run)

        digest = deepcopy(packet)
        digest[PROPOSAL_PACKET_DIGEST_FIELD] = "0" * 64
        with self.assertRaises(ValueError):
            verify_v32_proposal_canonical_packet_v1(digest)

    def test_real_public_authority_schema_routes_both_profiles(self) -> None:
        target = _proposal_packet()
        qualification = _proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )
        for packet, authority_profile in (
            (target, TARGET_PROFILE),
            (qualification, QUALIFICATION_PROFILE),
        ):
            self.assertEqual(
                packet["authority_document"]["schema_id"],
                AUTHORITY_SCHEMA_ID,
            )
            self.assertEqual(
                packet["authority_binding"]["schema_id"],
                AUTHORITY_SCHEMA_ID,
            )
            self.assertEqual(
                packet["authority_document"]["profile"], authority_profile
            )
            self.assertEqual(
                packet["authority_document"]["run_id"], packet["run_id"]
            )
            self.assertEqual(
                verify_v32_proposal_canonical_packet_v1(packet),
                packet[PROPOSAL_PACKET_DIGEST_FIELD],
            )

        wrong_profile = deepcopy(qualification)
        wrong_profile["authority_document"] = target["authority_document"]
        wrong_profile["authority_binding"] = target["authority_binding"]
        wrong_profile = self_digest(
            wrong_profile, PROPOSAL_PACKET_DIGEST_FIELD
        )
        with self.assertRaisesRegex(ValueError, "AUTHORITY_SCOPE"):
            verify_v32_proposal_canonical_packet_v1(wrong_profile)

        wrong_schema = deepcopy(target)
        wrong_schema["authority_binding"] = dict(
            wrong_schema["authority_binding"]
        )
        wrong_schema["authority_binding"]["schema_id"] = (
            "theory_paper_v32_qualification_authority_v1"
        )
        wrong_schema = self_digest(wrong_schema, PROPOSAL_PACKET_DIGEST_FIELD)
        with self.assertRaisesRegex(ValueError, "AUTHORITY_INVALID"):
            verify_v32_proposal_canonical_packet_v1(wrong_schema)

    def test_all_lifecycle_receipts_preserve_nonexecution_claim_boundary(self) -> None:
        packet, proposal, selection_packet, selection, *_ = _full_lifecycle()
        documents = [packet, selection_packet, proposal[0], proposal[2], proposal[4], selection[0], selection[2], selection[4]]
        for document in documents:
            self.assertFalse(document["executable"])
            self.assertFalse(document["account_access"])
            self.assertFalse(document["order_submission"])
            self.assertIn("NO_FILL", document["fill_claim"])
            self.assertIn("NO_PNL", document["pnl_claim"])
            self.assertNotIn("attention_verified", document)
            self.assertNotIn("prediction_valid", document)


if __name__ == "__main__":
    unittest.main()
