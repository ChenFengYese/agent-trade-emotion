"""Production orchestration for one authorized, non-executable V3.1 cycle.

This module closes the gap between the already-frozen authority/source chain,
the durable two-stage Agent transport, the six-object research chronology, and
the delayed public monitor.  It deliberately has no collector, account,
credential, order, paper-trading, live-trading, or portfolio mutation port.

The next cycle index and every cycle-2--8 predecessor head are derived from the
research checkpoint.  Caller-supplied predecessor state is not an input.
Monitor thresholds remain explicit Agent/controller inputs, but they must be
absolute OKX BTC-USDT-SWAP mark-price levels; this layer never fabricates a
return from an unbound baseline and never turns UNKNOWN into zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .ports import V31MonitorStorePort, V31ResearchStorePort
from .v31_agent_transport import (
    V31AgentTransportStorePort,
    verify_completed_v31_authoring_transport,
)
from .v31_cycle_source_admission import (
    verify_durable_v31_cycle_source_admission,
)
from .v31_durable_cycle import (
    persist_completed_v31_cycle,
    v31_cycle_authoring_head_bindings,
)
from .v31_monitor_runtime import (
    initialize_v31_monitor_runtime,
    schedule_v31_monitor_plan,
)
from .v31_research_cycle import (
    complete_v31_research_cycle,
    select_v31_cycle_action,
    verify_v31_accepted_state,
)
from ..domain.behavior_planning import seal_action_selection
from ..domain.contracts.canonical import canonical_digest, verify_self_digest
from ..domain.governance.v31_authorization import validate_v31_active_authority
from ..domain.v31_cycle_authoring import (
    AUTHORING_PACKET_DIGEST_FIELD,
    AUTHORING_PACKET_SCHEMA_ID,
    seal_v31_proposal_authoring_packet,
    validate_v31_proposal_authoring_packet,
)
from ..domain.v31_experiment_contracts import (
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    build_typed_path_monitor_plan,
    verify_minimal_experiment_contract,
    verify_typed_path_monitor_plan,
)
from ..domain.v31_run_genesis import (
    GENESIS_SOURCE_SPECS,
    checkpoint_genesis_bindings,
    verify_v31_run_genesis_receipt,
)


class V31FormalCycleCompositionError(ValueError):
    """The formal-cycle composition could not preserve its frozen boundary."""


FORMAL_AUTHORING_PACKET_REF_TEMPLATE = (
    "cycles/{cycle_index:04d}/proposal-authoring-packet.json"
)
ABSOLUTE_MARK_PRICE_OBSERVABLE = "metric:mark-price-usdt"
ABSOLUTE_MARK_PRICE_UNIT = "USDT_PER_BTC"
_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
_PREVIOUS_HEAD_KEYS = (
    "previous_accepted_state",
    "previous_information_revision_registry",
    "previous_pit_dataset",
    "previous_datum_revision_registry",
    "previous_sentiment_state",
    "previous_hypothesis_registry",
    "previous_expectation_ledger",
    "previous_probability_cloud",
)
_CHAIN_DOCUMENT_KEYS = {
    "theory_approval": "theory_approval",
    "experiment_contract": "experiment_contract",
    "experiment_manifest": "manifest",
    "experiment_authorization": "authorization_receipt",
    "current_authority": "authority",
}
_NUMERIC_MONITOR_OPERATORS = frozenset(
    {
        MonitorOperator.GT,
        MonitorOperator.GTE,
        MonitorOperator.LT,
        MonitorOperator.LTE,
    }
)
_FORBIDDEN_TRUE_FIELDS = frozenset(
    {
        "account_access",
        "account_data_accessed",
        "paper_trading",
        "live_trading",
        "order_submission",
        "order_data_accessed",
        "credential_access",
        "credentials_accessed",
        "credential_use",
        "funds_access",
        "portfolio_mutation",
        "executable",
    }
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31FormalCycleCompositionError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31FormalCycleCompositionError(code) from exc
    if parsed.tzinfo is None:
        raise V31FormalCycleCompositionError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31FormalCycleCompositionError(code)
    return normalized


def _assert_non_executable(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "external_execution_authority" and nested != (
                "NONE_LOCAL_SIMULATION"
            ):
                raise V31FormalCycleCompositionError(
                    "V31_FORMAL_CYCLE_AUTHORITY_EXPANSION_FORBIDDEN"
                )
            if key in _FORBIDDEN_TRUE_FIELDS and nested is True:
                raise V31FormalCycleCompositionError(
                    "V31_FORMAL_CYCLE_EXECUTION_CAPABILITY_FORBIDDEN"
                )
            _assert_non_executable(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_non_executable(nested)


def _validate_active_chain(
    active_chain: Mapping[str, Any],
) -> tuple[str, str, str, Mapping[str, Any], Mapping[str, Any]]:
    try:
        approval = active_chain["theory_approval"]
        contract = active_chain["experiment_contract"]
        manifest = active_chain["manifest"]
        authorization = active_chain["authorization_receipt"]
        authority = active_chain["authority"]
        contract_digest = verify_minimal_experiment_contract(contract)
        authority_digest = validate_v31_active_authority(
            authority,
            theory_approval=approval,
            manifest=manifest,
            experiment_contract=contract,
            authorization_receipt=authorization,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_ACTIVE_CHAIN_INVALID"
        ) from exc
    run_id = contract.get("run_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or authority.get("authorized_run_id") != run_id
        or authority.get("status") != "ACTIVE_FROZEN_RESEARCH"
        or authority.get("experiment_start_authorized") is not True
        or authority.get("data_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or authority.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or authority.get("executable") is not False
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_ACTIVE_CHAIN_SCOPE_INVALID"
        )
    _assert_non_executable(active_chain)
    return run_id, contract_digest, authority_digest, contract, authority


def _typed_run_binding(
    *,
    store: V31ResearchStorePort,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
    expected_semantic_digest: str,
) -> dict[str, str]:
    document = store.read_document(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=expected_semantic_digest,
    )
    if document.get("schema_id") != schema_id:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_GENESIS_SCHEMA_MISMATCH"
        )
    binding = store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=expected_semantic_digest,
    )
    return {
        "relative_ref": str(binding["relative_ref"]),
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def _checkpoint_cycle_and_genesis_bindings(
    *,
    store: V31ResearchStorePort,
    active_chain: Mapping[str, Any],
    run_id: str,
) -> tuple[int, Mapping[str, Any], dict[str, dict[str, str]]]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    cycle_index = checkpoint.get("next_cycle_index")
    if (
        checkpoint.get("schema_id") != "theory_paper_v31_research_checkpoint"
        or checkpoint.get("schema_version") != "1.2.0"
        or checkpoint.get("run_id") != run_id
        or checkpoint.get("status") != "READY_FOR_CYCLE"
        or checkpoint.get("active_cycle_index") is not None
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
        or checkpoint.get("completed_cycles") != cycle_index - 1
        or checkpoint.get("total_cycles") != 8
        or checkpoint.get("failure_digest") is not None
        or checkpoint.get("resume_allowed") is not True
        or checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or checkpoint.get("executable") is not False
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_CHECKPOINT_NOT_READY"
        )

    documents: dict[str, Mapping[str, Any]] = {}
    local_bindings: dict[str, dict[str, str]] = {}
    for spec in GENESIS_SOURCE_SPECS:
        chain_key = _CHAIN_DOCUMENT_KEYS[spec.role]
        expected = active_chain[chain_key]
        expected_digest = expected.get(spec.digest_field)
        if not isinstance(expected_digest, str):
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_CYCLE_ACTIVE_CHAIN_DIGEST_INVALID"
            )
        binding = _typed_run_binding(
            store=store,
            relative_ref=spec.local_ref,
            schema_id=spec.schema_id,
            digest_field=spec.digest_field,
            expected_semantic_digest=expected_digest,
        )
        document = store.read_document(
            relative_ref=spec.local_ref,
            digest_field=spec.digest_field,
            expected_semantic_digest=expected_digest,
        )
        if dict(document) != dict(expected):
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_CYCLE_GENESIS_ACTIVE_CHAIN_DRIFT"
            )
        documents[spec.role] = document
        local_bindings[spec.role] = binding

    run_genesis = store.read_document(
        relative_ref=str(checkpoint["run_genesis_ref"]),
        digest_field="run_genesis_digest",
        expected_semantic_digest=str(checkpoint["run_genesis_digest"]),
    )
    rows = run_genesis.get("genesis_artifacts")
    if not isinstance(rows, list):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_RUN_GENESIS_INVALID"
        )
    global_bindings: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(
            row.get("source_role"), str
        ):
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_CYCLE_RUN_GENESIS_INVALID"
            )
        global_bindings[str(row["source_role"])] = {
            "path": str(row["global_ref"]),
            "schema_id": str(row["schema_id"]),
            "digest_field": str(row["digest_field"]),
            "semantic_digest": str(row["semantic_digest"]),
            "physical_sha256": str(row["global_physical_sha256"]),
        }
    try:
        verify_v31_run_genesis_receipt(
            run_genesis,
            documents=documents,
            global_bindings=global_bindings,
        )
        expected_checkpoint_bindings = checkpoint_genesis_bindings(
            run_genesis,
            documents=documents,
            global_bindings=global_bindings,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_RUN_GENESIS_INVALID"
        ) from exc
    if any(
        checkpoint.get(field) != expected
        for field, expected in expected_checkpoint_bindings.items()
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_CHECKPOINT_GENESIS_MISMATCH"
        )
    return cycle_index, checkpoint, local_bindings


def _build_formal_authoring_packet(
    *,
    store: V31ResearchStorePort,
    active_chain: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    run_id, contract_digest, authority_digest, _contract, _authority = (
        _validate_active_chain(active_chain)
    )
    cycle_index, checkpoint, genesis = (
        _checkpoint_cycle_and_genesis_bindings(
            store=store, active_chain=active_chain, run_id=run_id
        )
    )
    try:
        source = verify_durable_v31_cycle_source_admission(
            run_store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            expected_authority_digest=authority_digest,
            expected_experiment_contract_digest=contract_digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_SOURCE_ADMISSION_INVALID"
        ) from exc

    if cycle_index == 1:
        previous_heads: dict[str, Mapping[str, str] | None] = {
            key: None for key in _PREVIOUS_HEAD_KEYS
        }
    else:
        # This is intentionally the only predecessor-state authority.  For the
        # next cycle it resolves the latest eight accepted heads through the
        # checkpoint's live content-addressed pointers.
        try:
            previous_heads = dict(
                v31_cycle_authoring_head_bindings(
                    store=store,
                    run_id=run_id,
                    cycle_index=cycle_index - 1,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_CYCLE_PREVIOUS_HEADS_INVALID"
            ) from exc
    if (
        set(previous_heads) != set(_PREVIOUS_HEAD_KEYS)
        or source.get("previous_head_bindings") != previous_heads
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_SOURCE_PREVIOUS_HEAD_MISMATCH"
        )
    admission = source["cycle_source_admission"]
    sources = source["authoring_source_bindings"]
    try:
        packet = seal_v31_proposal_authoring_packet(
            run_id=run_id,
            cycle_index=cycle_index,
            decision_at=str(admission["decision_at"]),
            symbol=str(admission["symbol"]),
            cycle_source_admission_binding=source[
                "cycle_source_admission_binding"
            ],
            source_qualification_completion_binding=sources[
                "source_qualification_completion_binding"
            ],
            information_event_bindings=sources[
                "information_event_bindings"
            ],
            pit_dataset_binding=sources["pit_dataset_binding"],
            association_estimation_receipt_bindings=(),
            authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
            theory_approval_binding=genesis["theory_approval"],
            experiment_subject_binding=genesis["experiment_contract"],
            active_authority_binding=genesis["current_authority"],
            previous_head_bindings=previous_heads,
        )
        validate_v31_proposal_authoring_packet(packet)
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_AUTHORING_PACKET_INVALID"
        ) from exc
    _assert_non_executable(packet)
    return packet, checkpoint


def prepare_v31_formal_authoring_cycle(
    *,
    store: V31ResearchStorePort,
    active_chain: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and persist the sole packet for the checkpoint's next cycle."""

    packet, checkpoint = _build_formal_authoring_packet(
        store=store, active_chain=active_chain
    )
    cycle_index = int(packet["cycle_index"])
    relative_ref = FORMAL_AUTHORING_PACKET_REF_TEMPLATE.format(
        cycle_index=cycle_index
    )
    binding = store.write_document(
        relative_ref=relative_ref,
        document=packet,
        digest_field=AUTHORING_PACKET_DIGEST_FIELD,
    )
    typed_binding = {
        "relative_ref": str(binding["relative_ref"]),
        "schema_id": AUTHORING_PACKET_SCHEMA_ID,
        "digest_field": AUTHORING_PACKET_DIGEST_FIELD,
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }
    durable = store.read_document(
        relative_ref=relative_ref,
        digest_field=AUTHORING_PACKET_DIGEST_FIELD,
        expected_semantic_digest=str(packet[AUTHORING_PACKET_DIGEST_FIELD]),
    )
    if dict(durable) != packet:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_AUTHORING_PACKET_READBACK_DRIFT"
        )
    return {
        "status": "FORMAL_AUTHORING_PACKET_READY_NOT_INVOKED",
        "run_id": packet["run_id"],
        "cycle_index": cycle_index,
        "authoring_packet": packet,
        "authoring_packet_binding": typed_binding,
        "research_checkpoint_digest": checkpoint["checkpoint_digest"],
        "previous_heads_source": "RESEARCH_CHECKPOINT_ONLY",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def _to_document(value: Any, *, code: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    method = getattr(value, "to_document", None)
    if not callable(method):
        raise V31FormalCycleCompositionError(code)
    document = method()
    if not isinstance(document, Mapping):
        raise V31FormalCycleCompositionError(code)
    return dict(document)


def _monitor_origin_bindings(
    *, accepted_state: Mapping[str, Any], assembly_inputs: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    try:
        accepted_digest = verify_v31_accepted_state(accepted_state)
        path_set = _to_document(
            assembly_inputs["scenario_paths"],
            code="V31_FORMAL_MONITOR_PATH_SET_INVALID",
        )
        path_set_digest = verify_self_digest(path_set, "path_set_digest")
        registry = assembly_inputs["hypothesis_registry"]
        ledger = assembly_inputs["expectation_ledger"]
        registry_digest = verify_self_digest(
            registry, "hypothesis_registry_digest"
        )
        ledger_digest = verify_self_digest(ledger, "expectation_ledger_digest")
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_ORIGIN_INPUT_INVALID"
        ) from exc
    if (
        accepted_state.get("scenario_path_set_digest") != path_set_digest
        or accepted_state.get("hypothesis_registry_digest") != registry_digest
        or accepted_state.get("expectation_ledger_digest") != ledger_digest
        or path_set.get("decision_at") != accepted_state.get("decision_at")
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_ORIGIN_ACCEPTED_MISMATCH"
        )
    paths = path_set.get("paths")
    lead_path_id = path_set.get("lead_path_id")
    if not isinstance(paths, list) or not isinstance(lead_path_id, str):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_LEAD_PATH_INVALID"
        )
    lead_rows = [row for row in paths if row.get("path_id") == lead_path_id]
    if len(lead_rows) != 1:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_LEAD_PATH_INVALID"
        )
    lead_path = lead_rows[0]
    lead_path_digest = verify_self_digest(lead_path, "path_digest")

    hypotheses = {
        row.get("hypothesis_id"): row
        for row in registry.get("hypotheses", [])
        if isinstance(row, Mapping) and isinstance(row.get("hypothesis_id"), str)
    }
    active_ids = set(registry.get("active_hypothesis_ids", []))
    hypothesis_ids = []
    for hypothesis_id in (
        lead_path_id,
        *lead_path.get("mechanism_hypothesis_refs", []),
    ):
        if hypothesis_id in hypotheses and hypothesis_id not in hypothesis_ids:
            hypothesis_ids.append(hypothesis_id)
    expectations = {
        row.get("expectation_id"): row
        for row in ledger.get("expectations", [])
        if isinstance(row, Mapping) and isinstance(row.get("expectation_id"), str)
    }
    horizon = _time(
        accepted_state["decision_at"], "V31_FORMAL_MONITOR_TIME_INVALID"
    ) + timedelta(hours=1)
    horizon_text = horizon.isoformat().replace("+00:00", "Z")
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
    for path_expectation in lead_path.get("expect_by_horizon", []):
        if (
            not isinstance(path_expectation, Mapping)
            or path_expectation.get("hypothesis_id") not in hypothesis_ids
            or path_expectation.get("hypothesis_id") not in active_ids
            or path_expectation.get("observable_ref")
            != ABSOLUTE_MARK_PRICE_OBSERVABLE
            or path_expectation.get("horizon_at") != horizon_text
        ):
            continue
        hypothesis = hypotheses[path_expectation["hypothesis_id"]]
        expectation = expectations.get(path_expectation.get("observation_id"))
        if (
            not isinstance(expectation, Mapping)
            or expectation.get("hypothesis_id")
            != path_expectation.get("hypothesis_id")
            or expectation.get("status") not in {"OPEN", "PARTIAL"}
            or canonical_digest(expectation)
            != path_expectation.get("expectation_revision_digest")
        ):
            continue
        candidates.append((hypothesis, expectation, path_expectation))
    if len(candidates) != 1:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_LEAD_EXPECTATION_AMBIGUOUS_OR_MISSING"
        )
    hypothesis, expectation, _path_expectation = candidates[0]
    cycle_index = int(accepted_state["cycle_index"])
    return {
        "accepted_state": {
            "ref": f"cycles/{cycle_index:04d}/accepted-research-state.json",
            "digest": accepted_digest,
        },
        "path_set": {
            "ref": f"scenario-path-set:{path_set['set_id']}",
            "digest": path_set_digest,
        },
        "path": {
            "ref": f"scenario-path:{lead_path_id}",
            "digest": lead_path_digest,
        },
        "hypothesis_revision": {
            "ref": (
                f"hypothesis:{hypothesis['hypothesis_id']}:"
                f"revision:{hypothesis['revision']}"
            ),
            "digest": canonical_digest(hypothesis),
        },
        "expectation_revision": {
            "ref": (
                f"expectation:{expectation['expectation_id']}:"
                f"revision:{expectation['revision']}"
            ),
            "digest": canonical_digest(expectation),
        },
    }


def _absolute_monitor_rules(
    rules: Sequence[FrozenMonitorRule],
) -> tuple[FrozenMonitorRule, ...]:
    if isinstance(rules, (str, bytes)):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_RULES_INVALID"
        )
    rows = tuple(rules)
    if (
        len(rows) != 3
        or any(not isinstance(row, FrozenMonitorRule) for row in rows)
        or {row.role for row in rows} != set(MonitorRuleRole)
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_MONITOR_RULES_INVALID"
        )
    for row in rows:
        if (
            row.observable_ref != ABSOLUTE_MARK_PRICE_OBSERVABLE
            or row.unit != ABSOLUTE_MARK_PRICE_UNIT
            or row.operator not in _NUMERIC_MONITOR_OPERATORS
        ):
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_MONITOR_ABSOLUTE_MARK_RULE_REQUIRED"
            )
        try:
            threshold = Decimal(str(row.expected))
        except (InvalidOperation, ValueError) as exc:
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_MONITOR_ABSOLUTE_MARK_THRESHOLD_INVALID"
            ) from exc
        if not threshold.is_finite() or threshold <= 0:
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_MONITOR_ABSOLUTE_MARK_THRESHOLD_INVALID"
            )
    return rows


def complete_v31_formal_authoring_cycle(
    *,
    research_store: V31ResearchStorePort,
    transport_store: V31AgentTransportStorePort,
    monitor_store: V31MonitorStorePort,
    active_chain: Mapping[str, Any],
    completed_at: str,
    recorded_at: str,
    monitor_runtime_created_at: str,
    monitor_rules: Sequence[FrozenMonitorRule],
) -> dict[str, Any]:
    """Replay terminal Agent evidence, persist six objects, and schedule 1H.

    The function performs no Agent call and no outcome collection.  The
    monitor adapter can only be invoked later by the separate due-resolution
    workflow after its one-hour horizon.
    """

    run_id, _contract_digest, _authority_digest, contract, _authority = (
        _validate_active_chain(active_chain)
    )
    expected_packet, checkpoint_before = _build_formal_authoring_packet(
        store=research_store, active_chain=active_chain
    )
    cycle_index = int(expected_packet["cycle_index"])
    completed = _time(completed_at, "V31_FORMAL_CYCLE_COMPLETED_AT_INVALID")
    recorded = _time(recorded_at, "V31_FORMAL_CYCLE_RECORDED_AT_INVALID")
    _time(
        monitor_runtime_created_at,
        "V31_FORMAL_MONITOR_CREATED_AT_INVALID",
    )
    if recorded < completed:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_RECORD_PRECEDES_COMPLETION"
        )
    rules = _absolute_monitor_rules(monitor_rules)
    try:
        terminal = verify_completed_v31_authoring_transport(
            store=transport_store,
            run_id=run_id,
            cycle_index=cycle_index,
            expected_authoring_purpose="AUTHORIZED_RESEARCH_CYCLE",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TRANSPORT_NOT_COMPLETED"
        ) from exc
    if (
        terminal.get("authoring_packet") != expected_packet
        or terminal.get("authoring_purpose") != "AUTHORIZED_RESEARCH_CYCLE"
        or terminal.get("experiment_start_authorized") is not True
        or terminal.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or terminal.get("executable") is not False
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TRANSPORT_PACKET_MISMATCH"
        )
    assembly_inputs = terminal.get("assembly_inputs")
    action_selection = terminal.get("action_selection")
    if not isinstance(assembly_inputs, Mapping) or not isinstance(
        action_selection, Mapping
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TERMINAL_ASSEMBLY_INVALID"
        )
    action_evaluation = terminal.get("action_evaluation")
    preselection = terminal.get("preselection")
    try:
        selection = seal_action_selection(
            evaluation=action_evaluation,
            selected_candidate_id=action_selection["selected_candidate_id"],
            reason=action_selection["reason"],
            alternative_explanations=action_selection[
                "alternative_explanations"
            ],
            failure_conditions=action_selection["failure_conditions"],
            next_review_at=action_selection["next_review_at"],
            selected_at=action_selection["selected_at"],
        )
        if selection != dict(action_selection):
            raise V31FormalCycleCompositionError(
                "V31_FORMAL_CYCLE_SELECTION_REPLAY_MISMATCH"
            )
        accepted = select_v31_cycle_action(
            preselection=preselection,
            action_evaluation=action_evaluation,
            selected_candidate_id=selection["selected_candidate_id"],
            alternative_explanations=selection["alternative_explanations"],
            selection_rationale=selection["reason"],
            failure_conditions=selection["failure_conditions"],
            next_review_at=selection["next_review_at"],
            selected_at=selection["selected_at"],
        )
        completion = complete_v31_research_cycle(
            accepted_state=accepted, completed_at=completed_at
        )
    except V31FormalCycleCompositionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_SIX_OBJECT_REPLAY_FAILED"
        ) from exc
    documents = {
        "INPUTS_ADMITTED": terminal["inputs_receipt"],
        "PROPOSAL_SEALED": terminal["agent_proposal"],
        "EVALUATION_SEALED": preselection,
        "SELECTION_SEALED": selection,
        "STATE_ACCEPTED": accepted,
        "COMPLETION_SEALED": completion,
    }
    if (
        assembly_inputs.get("inputs_receipt") != documents["INPUTS_ADMITTED"]
        or assembly_inputs.get("agent_proposal") != documents["PROPOSAL_SEALED"]
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_ASSEMBLY_SOURCE_MISMATCH"
        )
    _assert_non_executable(documents)
    origin_bindings = _monitor_origin_bindings(
        accepted_state=accepted, assembly_inputs=assembly_inputs
    )
    plan = build_typed_path_monitor_plan(
        experiment_contract=contract,
        monitor_plan_id=(
            f"monitor:{run_id}:{cycle_index:04d}:absolute-mark-1h"
        ),
        cycle_id=f"{run_id}:cycle:{cycle_index:04d}",
        cycle_index=cycle_index,
        origin_bindings=origin_bindings,
        decision_at=str(accepted["decision_at"]),
        observable_ref=ABSOLUTE_MARK_PRICE_OBSERVABLE,
        source_request_id=(
            f"okx-public-mark-price:{run_id}:{cycle_index:04d}:1h"
        ),
        rules=rules,
    )
    verify_typed_path_monitor_plan(
        plan,
        experiment_contract=contract,
        expected_origin_bindings=origin_bindings,
    )
    _assert_non_executable(plan)

    evidence_binding = terminal.get("transport_evidence_binding")
    if not isinstance(evidence_binding, Mapping):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TRANSPORT_EVIDENCE_BINDING_INVALID"
        )
    try:
        durable_evidence = research_store.read_document(
            relative_ref=str(evidence_binding["relative_ref"]),
            digest_field="transport_evidence_digest",
            expected_semantic_digest=str(evidence_binding["semantic_digest"]),
        )
        run_local_evidence_binding = research_store.artifact_binding(
            relative_ref=str(evidence_binding["relative_ref"]),
            digest_field="transport_evidence_digest",
            expected_semantic_digest=str(evidence_binding["semantic_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TRANSPORT_EVIDENCE_NOT_RUN_LOCAL"
        ) from exc
    if (
        dict(durable_evidence) != terminal.get("transport_evidence")
        or any(
            run_local_evidence_binding.get(field)
            != evidence_binding.get(field)
            for field in (
                "relative_ref",
                "semantic_digest",
                "physical_sha256",
            )
        )
        or durable_evidence.get("run_id") != run_id
        or durable_evidence.get("cycle_index") != cycle_index
        or durable_evidence.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or durable_evidence.get("executable") is not False
    ):
        raise V31FormalCycleCompositionError(
            "V31_FORMAL_CYCLE_TRANSPORT_EVIDENCE_MISMATCH"
        )

    event_times = {event_type: recorded_at for event_type in _EVENT_ORDER}
    checkpoint = persist_completed_v31_cycle(
        store=research_store,
        run_id=run_id,
        cycle_index=cycle_index,
        total_cycles=int(checkpoint_before["total_cycles"]),
        created_at=str(checkpoint_before["created_at"]),
        documents=documents,
        assembly_inputs=assembly_inputs,
        recorded_at_by_event=event_times,
        transport_evidence_binding=evidence_binding,
    )
    initialize_v31_monitor_runtime(
        store=monitor_store,
        experiment_contract=contract,
        created_at=monitor_runtime_created_at,
    )
    monitor_checkpoint = schedule_v31_monitor_plan(
        store=monitor_store,
        research_store=research_store,
        experiment_contract=contract,
        accepted_state=accepted,
        monitor_plan=plan,
        scheduled_at=recorded_at,
    )
    return {
        "status": "FORMAL_CYCLE_ACCEPTED_MONITOR_SCHEDULED",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "documents": documents,
        "research_checkpoint": dict(checkpoint),
        "monitor_plan": plan,
        "monitor_checkpoint": dict(monitor_checkpoint),
        "monitor_origin_bindings": origin_bindings,
        "monitor_observable_semantics": "ABSOLUTE_MARK_PRICE_USDT_PER_BTC",
        "return_or_change_inferred": False,
        "unknown_zero_imputed": False,
        "outcome_collection_performed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


__all__ = [
    "ABSOLUTE_MARK_PRICE_OBSERVABLE",
    "ABSOLUTE_MARK_PRICE_UNIT",
    "FORMAL_AUTHORING_PACKET_REF_TEMPLATE",
    "V31FormalCycleCompositionError",
    "complete_v31_formal_authoring_cycle",
    "prepare_v31_formal_authoring_cycle",
]
