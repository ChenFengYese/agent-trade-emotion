"""Application coordinator for one already-computed V3.1 research cycle.

The coordinator has no Agent, market-data, account, order, or execution port.
It only verifies six completed research artifacts, persists them write-once,
appends the fixed chronology, and advances the compare-and-swap checkpoint.
Re-running with the same artifacts resumes at the first missing durable event.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from .ports import V31ResearchStorePort
from .v31_durable_bundle import (
    ASSEMBLY_BUNDLE_DIRECTORY,
    V31DurableBundleError,
    assembly_bundle_relative_ref,
    rebuild_v31_documents_from_bundle,
    seal_v31_durable_assembly_bundle,
)
from .v31_research_cycle import (
    V31ResearchCycleError,
    assemble_v31_cycle_evaluation,
    complete_v31_research_cycle,
    select_v31_cycle_action,
    verify_v31_accepted_state,
    verify_v31_completion_receipt,
    verify_v31_cycle_evaluation,
)
from ..domain.agent_research_contract import (
    AgentResearchContractError,
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from ..domain.contracts.canonical import CanonicalContractError, verify_self_digest
from ..domain.behavior_planning import (
    BehaviorPlanningError,
    seal_action_selection,
)
from ..domain.market_knowledge_graph import apply_graph_delta


class V31DurableCycleError(ValueError):
    """The prepared cycle cannot be admitted to the durable chronology."""


_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ARTIFACT = {
    "INPUTS_ADMITTED": (
        "inputs-receipt.json",
        "theory_paper_v2_v31_inputs_receipt",
        "inputs_receipt_digest",
    ),
    "PROPOSAL_SEALED": (
        "agent-proposal.json",
        "theory_paper_v2_v31_agent_proposal",
        "agent_proposal_digest",
    ),
    "EVALUATION_SEALED": (
        "cycle-preselection.json",
        "theory_paper_v2_v31_cycle_preselection",
        "preselection_digest",
    ),
    "SELECTION_SEALED": (
        "action-selection.json",
        "theory_paper_v2_v31_action_selection",
        "action_selection_digest",
    ),
    "STATE_ACCEPTED": (
        "accepted-research-state.json",
        "theory_paper_v2_v31_accepted_research_state",
        "accepted_state_digest",
    ),
    "COMPLETION_SEALED": (
        "completion-receipt.json",
        "theory_paper_v2_v31_completion_receipt",
        "completion_receipt_digest",
    ),
}
_AUTHORING_HEAD_SPECS = {
    "previous_accepted_state": (
        "accepted-research-state.json",
        "theory_paper_v2_v31_accepted_research_state",
        "accepted_state_digest",
        "accepted_state_ref",
        "accepted_state_digest",
        "accepted_state_digest",
    ),
    "previous_information_revision_registry": (
        "information-revision-registry.json",
        "theory_paper_v2_v31_information_revision_registry",
        "information_revision_registry_digest",
        "accepted_information_revision_registry_ref",
        "accepted_information_revision_registry_digest",
        "information_revision_registry_digest",
    ),
    "previous_pit_dataset": (
        "pit-dataset.json",
        "theory_paper_v2_v31_point_in_time_dataset",
        "dataset_digest",
        "accepted_pit_dataset_ref",
        "accepted_pit_dataset_digest",
        "pit_dataset_digest",
    ),
    "previous_datum_revision_registry": (
        "datum-revision-registry.json",
        "theory_paper_v2_v31_datum_revision_registry",
        "datum_revision_registry_digest",
        "accepted_datum_revision_registry_ref",
        "accepted_datum_revision_registry_digest",
        "datum_revision_registry_digest",
    ),
    "previous_sentiment_state": (
        "sentiment-state.json",
        "theory_paper_v2_v31_multidimensional_market_sentiment_state",
        "sentiment_state_digest",
        "accepted_sentiment_state_ref",
        "accepted_sentiment_state_digest",
        "sentiment_state_digest",
    ),
    "previous_hypothesis_registry": (
        "hypothesis-registry.json",
        "dynamic_hypothesis_registry",
        "hypothesis_registry_digest",
        "accepted_hypothesis_registry_ref",
        "accepted_hypothesis_registry_digest",
        "hypothesis_registry_digest",
    ),
    "previous_expectation_ledger": (
        "expectation-ledger.json",
        "append_only_expectation_ledger",
        "expectation_ledger_digest",
        "accepted_expectation_ledger_ref",
        "accepted_expectation_ledger_digest",
        "expectation_ledger_digest",
    ),
    "previous_probability_cloud": (
        "probability-cloud.json",
        "theory_paper_v2_v31_probability_cloud",
        "cloud_digest",
        "accepted_probability_cloud_ref",
        "accepted_probability_cloud_digest",
        "probability_cloud_digest",
    ),
}


def v31_cycle_graph_state_relative_ref(*, cycle_index: int) -> str:
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise V31DurableCycleError("V31_DURABLE_CYCLE_INDEX_INVALID")
    return f"cycles/{cycle_index:04d}/graph-state.json"


def v31_cycle_authoring_head_bindings(
    *,
    store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
) -> dict[str, dict[str, str]]:
    """Return the eight accepted heads for composing cycle ``N + 1``.

    The latest accepted cycle is resolved through the checkpoint's live head
    pointers.  An earlier cycle is resolved through its immutable six-event
    chronology and cycle-local head files, but only when the current
    checkpoint still proves a contiguous content-addressed assembly lineage
    through that cycle.  This permits recursive source-receipt replay without
    weakening the single-head rule used for a new cycle.
    """

    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
    ):
        raise V31DurableCycleError("V31_DURABLE_AUTHORING_IDENTITY_INVALID")
    checkpoint = store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("status") not in {"READY_FOR_CYCLE", "TERMINAL"}
        or isinstance(checkpoint.get("completed_cycles"), bool)
        or not isinstance(checkpoint.get("completed_cycles"), int)
        or cycle_index > checkpoint["completed_cycles"]
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_HEAD_CHECKPOINT_NOT_ACCEPTED"
        )
    completed_cycles = int(checkpoint["completed_cycles"])
    bundle_rows = checkpoint.get("assembly_bundle_bindings")
    if (
        not isinstance(bundle_rows, list)
        or [row.get("cycle_index") for row in bundle_rows]
        != list(range(1, completed_cycles + 1))
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_ASSEMBLY_LINEAGE_INVALID"
        )
    bundle_row = bundle_rows[cycle_index - 1]
    try:
        bundle = store.read_document(
            relative_ref=str(bundle_row["relative_ref"]),
            digest_field="assembly_bundle_digest",
            expected_semantic_digest=str(bundle_row["semantic_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_ASSEMBLY_LINEAGE_INVALID"
        ) from exc
    if (
        bundle.get("run_id") != run_id
        or bundle.get("cycle_index") != cycle_index
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_ASSEMBLY_LINEAGE_INVALID"
        )

    events = store.read_events(run_id=run_id, cycle_index=cycle_index)
    if [row.get("event_type") for row in events] != list(_EVENT_ORDER):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_EVENT_CHAIN_INCOMPLETE"
        )
    accepted_event = events[_EVENT_ORDER.index("STATE_ACCEPTED")]
    accepted_ref = accepted_event.get("artifact_ref")
    accepted_digest = accepted_event.get("artifact_semantic_digest")
    if cycle_index == completed_cycles and (
        accepted_ref != checkpoint.get("accepted_state_ref")
        or accepted_digest != checkpoint.get("accepted_state_digest")
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_LATEST_HEAD_CHECKPOINT_MISMATCH"
        )
    if not isinstance(accepted_ref, str) or not isinstance(accepted_digest, str):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_ACCEPTED_STATE_MISSING"
        )
    accepted = store.read_document(
        relative_ref=accepted_ref,
        digest_field="accepted_state_digest",
        expected_semantic_digest=accepted_digest,
    )
    verify_v31_accepted_state(accepted)
    if (
        accepted.get("run_id") != run_id
        or accepted.get("cycle_index") != cycle_index
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_AUTHORING_ACCEPTED_STATE_IDENTITY_INVALID"
        )
    result: dict[str, dict[str, str]] = {}
    for key, (
        _filename,
        schema_id,
        digest_field,
        ref_field,
        checkpoint_digest_field,
        accepted_digest_field,
    ) in _AUTHORING_HEAD_SPECS.items():
        if key == "previous_accepted_state":
            relative_ref = accepted_ref
            expected_digest = accepted_digest
        elif cycle_index == completed_cycles:
            relative_ref = checkpoint.get(ref_field)
            expected_digest = checkpoint.get(checkpoint_digest_field)
        else:
            relative_ref = f"cycles/{cycle_index:04d}/{_filename}"
            expected_digest = accepted.get(accepted_digest_field)
        if (
            not isinstance(relative_ref, str)
            or not isinstance(expected_digest, str)
            or accepted.get(accepted_digest_field) != expected_digest
        ):
            raise V31DurableCycleError(
                "V31_DURABLE_AUTHORING_HEAD_CHECKPOINT_MISMATCH"
            )
        binding = store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_digest,
        )
        document = store.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_digest,
        )
        if document.get("schema_id") != schema_id:
            raise V31DurableCycleError(
                "V31_DURABLE_AUTHORING_HEAD_SCHEMA_INVALID"
            )
        result[key] = {
            "relative_ref": str(binding["relative_ref"]),
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": str(binding["semantic_digest"]),
            "physical_sha256": str(binding["physical_sha256"]),
        }
    return result


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31DurableCycleError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31DurableCycleError(code) from exc
    if parsed.tzinfo is None:
        raise V31DurableCycleError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31DurableCycleError(code)
    return parsed.astimezone(UTC)


def _verify_prepared_documents(
    *,
    run_id: str,
    cycle_index: int,
    documents: Mapping[str, Mapping[str, Any]],
    assembly_inputs: Mapping[str, Any],
) -> dict[str, str]:
    if set(documents) != set(_EVENT_ORDER):
        raise V31DurableCycleError("V31_DURABLE_ARTIFACT_SET_INCOMPLETE")
    digests: dict[str, str] = {}
    for event_type in _EVENT_ORDER:
        document = documents[event_type]
        if not isinstance(document, Mapping):
            raise V31DurableCycleError("V31_DURABLE_ARTIFACT_INVALID")
        _, schema_id, digest_field = _EVENT_ARTIFACT[event_type]
        if (
            document.get("schema_id") != schema_id
            or document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
        ):
            raise V31DurableCycleError("V31_DURABLE_ARTIFACT_IDENTITY_INVALID")
        try:
            digests[event_type] = verify_self_digest(document, digest_field)
        except (CanonicalContractError, ValueError) as exc:
            raise V31DurableCycleError("V31_DURABLE_ARTIFACT_DIGEST_INVALID") from exc
    try:
        verify_v31_inputs_receipt(documents["INPUTS_ADMITTED"])
        verify_v31_agent_proposal(
            documents["PROPOSAL_SEALED"],
            inputs_receipt=documents["INPUTS_ADMITTED"],
        )
        verify_v31_cycle_evaluation(documents["EVALUATION_SEALED"])
        verify_v31_accepted_state(documents["STATE_ACCEPTED"])
        verify_v31_completion_receipt(documents["COMPLETION_SEALED"])
    except (AgentResearchContractError, V31ResearchCycleError) as exc:
        raise V31DurableCycleError("V31_DURABLE_ARTIFACT_CONTRACT_INVALID") from exc

    # Cross-document hashes are necessary but not sufficient: a caller can
    # re-sign a mutually consistent fiction.  Re-run the complete Application
    # admission from the original typed bundle, then deterministically rebuild
    # selection, accepted state, and completion before durability is granted.
    if not isinstance(assembly_inputs, Mapping):
        raise V31DurableCycleError("V31_DURABLE_SEMANTIC_INPUTS_REQUIRED")
    try:
        if (
            documents["INPUTS_ADMITTED"]
            != assembly_inputs.get("inputs_receipt")
            or documents["PROPOSAL_SEALED"]
            != assembly_inputs.get("agent_proposal")
        ):
            raise V31DurableCycleError(
                "V31_DURABLE_SEMANTIC_SOURCE_BINDING_MISMATCH"
            )
        rebuilt_preselection = assemble_v31_cycle_evaluation(
            **dict(assembly_inputs)
        )
        if rebuilt_preselection != dict(documents["EVALUATION_SEALED"]):
            raise V31DurableCycleError(
                "V31_DURABLE_PRESELECTION_REPLAY_MISMATCH"
            )
        selection = documents["SELECTION_SEALED"]
        action_evaluation = assembly_inputs["action_evaluation"]
        rebuilt_selection = seal_action_selection(
            evaluation=action_evaluation,
            selected_candidate_id=selection["selected_candidate_id"],
            reason=selection["reason"],
            alternative_explanations=selection["alternative_explanations"],
            failure_conditions=selection["failure_conditions"],
            next_review_at=selection["next_review_at"],
            selected_at=selection["selected_at"],
        )
        if rebuilt_selection != dict(selection):
            raise V31DurableCycleError(
                "V31_DURABLE_SELECTION_REPLAY_MISMATCH"
            )
        rebuilt_accepted = select_v31_cycle_action(
            preselection=rebuilt_preselection,
            action_evaluation=action_evaluation,
            selected_candidate_id=selection["selected_candidate_id"],
            alternative_explanations=selection["alternative_explanations"],
            selection_rationale=selection["reason"],
            failure_conditions=selection["failure_conditions"],
            next_review_at=selection["next_review_at"],
            selected_at=selection["selected_at"],
        )
        if rebuilt_accepted != dict(documents["STATE_ACCEPTED"]):
            raise V31DurableCycleError(
                "V31_DURABLE_ACCEPTED_STATE_REPLAY_MISMATCH"
            )
        rebuilt_completion = complete_v31_research_cycle(
            accepted_state=rebuilt_accepted,
            completed_at=documents["COMPLETION_SEALED"]["completed_at"],
        )
        if rebuilt_completion != dict(documents["COMPLETION_SEALED"]):
            raise V31DurableCycleError(
                "V31_DURABLE_COMPLETION_REPLAY_MISMATCH"
            )
    except V31DurableCycleError:
        raise
    except (
        AgentResearchContractError,
        BehaviorPlanningError,
        CanonicalContractError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V31DurableCycleError("V31_DURABLE_SEMANTIC_REPLAY_FAILED") from exc
    return digests


def _verify_existing_events(
    *,
    store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
    bindings: Mapping[str, Mapping[str, str]],
    recorded_at_by_event: Mapping[str, str],
) -> Sequence[Mapping[str, Any]]:
    events = store.read_events(run_id=run_id, cycle_index=cycle_index)
    if len(events) > len(_EVENT_ORDER):
        raise V31DurableCycleError("V31_DURABLE_EVENT_CHAIN_TOO_LONG")
    for sequence, event in enumerate(events):
        event_type = _EVENT_ORDER[sequence]
        binding = bindings[event_type]
        if (
            event.get("event_type") != event_type
            or event.get("artifact_ref") != binding["relative_ref"]
            or event.get("artifact_semantic_digest") != binding["semantic_digest"]
            or event.get("artifact_physical_sha256") != binding["physical_sha256"]
            or event.get("recorded_at") != recorded_at_by_event[event_type]
        ):
            raise V31DurableCycleError("V31_DURABLE_RECOVERY_CONFLICT")
    return events


def persist_completed_v31_cycle(
    *,
    store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
    total_cycles: int,
    created_at: str,
    documents: Mapping[str, Mapping[str, Any]],
    assembly_inputs: Mapping[str, Any],
    recorded_at_by_event: Mapping[str, str],
    transport_evidence_binding: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Persist one complete non-executable cycle and return its checkpoint.

    All analytical and Agent work must already be complete.  This function is
    intentionally unable to invoke or re-invoke an Agent during recovery.
    """

    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
        or isinstance(total_cycles, bool)
        or not isinstance(total_cycles, int)
        or total_cycles < cycle_index
    ):
        raise V31DurableCycleError("V31_DURABLE_IDENTITY_INVALID")
    _timestamp(created_at, "V31_DURABLE_CREATED_AT_INVALID")
    if set(recorded_at_by_event) != set(_EVENT_ORDER):
        raise V31DurableCycleError("V31_DURABLE_EVENT_TIMES_INCOMPLETE")
    event_times = [
        _timestamp(recorded_at_by_event[event_type], "V31_DURABLE_EVENT_TIME_INVALID")
        for event_type in _EVENT_ORDER
    ]
    if any(current < prior for prior, current in zip(event_times, event_times[1:])):
        raise V31DurableCycleError("V31_DURABLE_EVENT_TIME_ORDER_INVALID")
    if transport_evidence_binding is not None and (
        not isinstance(transport_evidence_binding, Mapping)
        or not {
            "relative_ref",
            "semantic_digest",
            "physical_sha256",
        }.issubset(transport_evidence_binding)
        or _HEX_64.fullmatch(
            str(transport_evidence_binding.get("semantic_digest") or "")
        )
        is None
        or _HEX_64.fullmatch(
            str(transport_evidence_binding.get("physical_sha256") or "")
        )
        is None
        or (
            "schema_id" in transport_evidence_binding
            and transport_evidence_binding.get("schema_id")
            != "theory_paper_v31_agent_transport_evidence"
        )
        or (
            "digest_field" in transport_evidence_binding
            and transport_evidence_binding.get("digest_field")
            != "transport_evidence_digest"
        )
    ):
        raise V31DurableCycleError(
            "V31_DURABLE_TRANSPORT_EVIDENCE_BINDING_INVALID"
        )

    # Reject a semantically fabricated six-document set before creating any
    # durable artifact.  The same admission is repeated below from decoded
    # durable inputs so this early check is diagnostic, not an authority cache.
    _verify_prepared_documents(
        run_id=run_id,
        cycle_index=cycle_index,
        documents=documents,
        assembly_inputs=assembly_inputs,
    )

    # Build and replay the portable bundle before writing anything.  Then write
    # it once, read the canonical bytes back through the store, and replay a
    # second time from that durable representation.  The second replay is the
    # exact path used by a fresh-process recovery.
    try:
        assembly_bundle = seal_v31_durable_assembly_bundle(
            assembly_inputs=assembly_inputs,
            documents=documents,
            recorded_at_by_event=recorded_at_by_event,
        )
        (
            _preflight_inputs,
            preflight_documents,
            preflight_event_times,
        ) = rebuild_v31_documents_from_bundle(assembly_bundle)
        if (
            preflight_documents != dict(documents)
            or preflight_event_times != dict(recorded_at_by_event)
        ):
            raise V31DurableCycleError("V31_DURABLE_BUNDLE_PREFLIGHT_MISMATCH")
        bundle_binding = store.write_document(
            relative_ref=assembly_bundle_relative_ref(
                cycle_index=cycle_index,
                bundle_digest=assembly_bundle["assembly_bundle_digest"],
            ),
            document=assembly_bundle,
            digest_field="assembly_bundle_digest",
        )
        durable_bundle = store.read_document(
            relative_ref=bundle_binding["relative_ref"],
            digest_field="assembly_bundle_digest",
            expected_semantic_digest=bundle_binding["semantic_digest"],
        )
        (
            durable_assembly_inputs,
            durable_documents,
            durable_event_times,
        ) = rebuild_v31_documents_from_bundle(durable_bundle)
        if (
            durable_documents != dict(documents)
            or durable_event_times != dict(recorded_at_by_event)
        ):
            raise V31DurableCycleError("V31_DURABLE_BUNDLE_READBACK_MISMATCH")
    except V31DurableCycleError:
        raise
    except (V31DurableBundleError, KeyError, TypeError, ValueError) as exc:
        raise V31DurableCycleError("V31_DURABLE_BUNDLE_INVALID") from exc

    semantic_digests = _verify_prepared_documents(
        run_id=run_id,
        cycle_index=cycle_index,
        documents=durable_documents,
        assembly_inputs=durable_assembly_inputs,
    )
    store.register_semantic_admission(
        run_id=run_id,
        cycle_index=cycle_index,
        artifact_digests={
            **semantic_digests,
            "ASSEMBLY_BUNDLE": bundle_binding["semantic_digest"],
        },
    )
    try:
        graph_state = apply_graph_delta(
            durable_assembly_inputs["prior_graph"],
            durable_assembly_inputs["graph_delta"],
            decision_at=durable_assembly_inputs["decision_at"],
        )
        head_documents: dict[str, Mapping[str, Any]] = {
            "previous_information_revision_registry": durable_assembly_inputs[
                "information_revision_registry"
            ],
            "previous_pit_dataset": durable_assembly_inputs["pit_dataset"],
            "previous_datum_revision_registry": durable_assembly_inputs[
                "datum_revision_registry"
            ],
            "previous_sentiment_state": durable_assembly_inputs[
                "sentiment_state"
            ],
            "previous_hypothesis_registry": durable_assembly_inputs[
                "hypothesis_registry"
            ],
            "previous_expectation_ledger": durable_assembly_inputs[
                "expectation_ledger"
            ],
            "previous_probability_cloud": durable_assembly_inputs[
                "probability_cloud"
            ].to_document(),
        }
        head_bindings: dict[str, Mapping[str, str]] = {}
        for key, document in head_documents.items():
            filename, _schema_id, digest_field, *_ = _AUTHORING_HEAD_SPECS[key]
            head_bindings[key] = store.write_document(
                relative_ref=f"cycles/{cycle_index:04d}/{filename}",
                document=document,
                digest_field=digest_field,
            )
        graph_state_binding = store.write_document(
            relative_ref=v31_cycle_graph_state_relative_ref(
                cycle_index=cycle_index
            ),
            document=graph_state,
            digest_field="graph_digest",
        )
        information_registry_binding = head_bindings[
            "previous_information_revision_registry"
        ]
        datum_registry_binding = head_bindings[
            "previous_datum_revision_registry"
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise V31DurableCycleError(
            "V31_DURABLE_REVISION_REGISTRY_PERSISTENCE_FAILED"
        ) from exc

    checkpoint = store.initialize_checkpoint(
        run_id=run_id,
        total_cycles=total_cycles,
        created_at=created_at,
    )
    authority_bound = checkpoint.get("run_genesis_digest") is not None
    if authority_bound and transport_evidence_binding is None:
        try:
            evidence = store.discover_content_addressed_document(
                relative_dir=(
                    f"cycles/{cycle_index:04d}/transport-evidence"
                ),
                digest_field="transport_evidence_digest",
            )
            evidence_digest = str(evidence["transport_evidence_digest"])
            transport_evidence_binding = store.artifact_binding(
                relative_ref=(
                    f"cycles/{cycle_index:04d}/transport-evidence/"
                    f"{evidence_digest}.json"
                ),
                digest_field="transport_evidence_digest",
                expected_semantic_digest=evidence_digest,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V31DurableCycleError(
                "V31_DURABLE_TRANSPORT_EVIDENCE_REQUIRED"
            ) from exc
    if not authority_bound and transport_evidence_binding is not None:
        raise V31DurableCycleError(
            "V31_DURABLE_TRANSPORT_EVIDENCE_WITHOUT_GENESIS_FORBIDDEN"
        )
    normalized_transport_binding = (
        None
        if transport_evidence_binding is None
        else {
            "cycle_index": cycle_index,
            "relative_ref": str(transport_evidence_binding["relative_ref"]),
            "semantic_digest": str(
                transport_evidence_binding["semantic_digest"]
            ),
            "physical_sha256": str(
                transport_evidence_binding["physical_sha256"]
            ),
        }
    )
    if checkpoint.get("total_cycles") != total_cycles:
        raise V31DurableCycleError("V31_DURABLE_TOTAL_CYCLES_CONFLICT")
    if checkpoint.get("status") == "FAILED_CLOSED":
        raise V31DurableCycleError("V31_DURABLE_CHECKPOINT_FAILED_CLOSED")
    if int(checkpoint.get("completed_cycles", -1)) < cycle_index:
        if (
            checkpoint.get("status") == "READY_FOR_CYCLE"
            and checkpoint.get("next_cycle_index") == cycle_index
        ):
            checkpoint = store.replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
                checkpoint={
                    **checkpoint,
                    "revision": int(checkpoint["revision"]) + 1,
                    "status": "CYCLE_IN_PROGRESS",
                    "active_cycle_index": cycle_index,
                    "updated_at": recorded_at_by_event["INPUTS_ADMITTED"],
                },
            )
        elif not (
            checkpoint.get("status") == "CYCLE_IN_PROGRESS"
            and checkpoint.get("active_cycle_index") == cycle_index
        ):
            raise V31DurableCycleError("V31_DURABLE_CHECKPOINT_CYCLE_MISMATCH")

    bindings: dict[str, Mapping[str, str]] = {}
    for event_type in _EVENT_ORDER:
        filename, _, digest_field = _EVENT_ARTIFACT[event_type]
        relative_ref = f"cycles/{cycle_index:04d}/{filename}"
        bindings[event_type] = store.write_document(
            relative_ref=relative_ref,
            document=durable_documents[event_type],
            digest_field=digest_field,
        )

    events = _verify_existing_events(
        store=store,
        run_id=run_id,
        cycle_index=cycle_index,
        bindings=bindings,
        recorded_at_by_event=recorded_at_by_event,
    )
    if int(checkpoint.get("completed_cycles", -1)) >= cycle_index:
        if len(events) != len(_EVENT_ORDER):
            raise V31DurableCycleError("V31_DURABLE_COMPLETED_EVENT_CHAIN_INCOMPLETE")
        return checkpoint

    for sequence in range(len(events), len(_EVENT_ORDER)):
        event_type = _EVENT_ORDER[sequence]
        store.append_event(
            run_id=run_id,
            cycle_index=cycle_index,
            event_type=event_type,
            artifact_binding=bindings[event_type],
            recorded_at=recorded_at_by_event[event_type],
        )

    checkpoint = store.load_checkpoint(run_id=run_id)
    if int(checkpoint.get("completed_cycles", -1)) >= cycle_index:
        return checkpoint
    if (
        checkpoint.get("status") != "CYCLE_IN_PROGRESS"
        or checkpoint.get("active_cycle_index") != cycle_index
    ):
        raise V31DurableCycleError("V31_DURABLE_CHECKPOINT_CYCLE_MISMATCH")
    accepted_binding = bindings["STATE_ACCEPTED"]
    completion_binding = bindings["COMPLETION_SEALED"]
    accepted_document = durable_documents["STATE_ACCEPTED"]
    completed_cycles = cycle_index
    return store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        checkpoint={
            **checkpoint,
            "revision": int(checkpoint["revision"]) + 1,
            "status": (
                "TERMINAL" if completed_cycles == total_cycles else "READY_FOR_CYCLE"
            ),
            "completed_cycles": completed_cycles,
            "next_cycle_index": completed_cycles + 1,
            "active_cycle_index": None,
            "accepted_state_ref": accepted_binding["relative_ref"],
            "accepted_state_digest": accepted_binding["semantic_digest"],
            "accepted_pit_dataset_ref": head_bindings[
                "previous_pit_dataset"
            ]["relative_ref"],
            "accepted_pit_dataset_digest": accepted_document[
                "pit_dataset_digest"
            ],
            "accepted_information_revision_registry_ref": (
                information_registry_binding["relative_ref"]
            ),
            "accepted_information_revision_registry_digest": (
                information_registry_binding["semantic_digest"]
            ),
            "accepted_datum_revision_registry_ref": datum_registry_binding[
                "relative_ref"
            ],
            "accepted_datum_revision_registry_digest": datum_registry_binding[
                "semantic_digest"
            ],
            "accepted_sentiment_state_digest": accepted_document[
                "sentiment_state_digest"
            ],
            "accepted_sentiment_state_ref": head_bindings[
                "previous_sentiment_state"
            ]["relative_ref"],
            "accepted_sentiment_change_digest": accepted_document[
                "sentiment_change_digest"
            ],
            "accepted_graph_state_digest": accepted_document[
                "graph_state_digest"
            ],
            "accepted_graph_state_ref": graph_state_binding["relative_ref"],
            "accepted_hypothesis_registry_digest": accepted_document[
                "hypothesis_registry_digest"
            ],
            "accepted_hypothesis_registry_ref": head_bindings[
                "previous_hypothesis_registry"
            ]["relative_ref"],
            "accepted_expectation_ledger_digest": accepted_document[
                "expectation_ledger_digest"
            ],
            "accepted_expectation_ledger_ref": head_bindings[
                "previous_expectation_ledger"
            ]["relative_ref"],
            "accepted_probability_cloud_digest": accepted_document[
                "probability_cloud_digest"
            ],
            "accepted_probability_cloud_ref": head_bindings[
                "previous_probability_cloud"
            ]["relative_ref"],
            "accepted_probability_cloud_transition_digest": accepted_document[
                "probability_cloud_transition_digest"
            ],
            "last_completion_ref": completion_binding["relative_ref"],
            "last_completion_digest": completion_binding["semantic_digest"],
            "assembly_bundle_bindings": [
                *checkpoint["assembly_bundle_bindings"],
                {
                    "cycle_index": cycle_index,
                    "relative_ref": bundle_binding["relative_ref"],
                    "semantic_digest": bundle_binding["semantic_digest"],
                },
            ],
            "transport_evidence_bindings": (
                checkpoint["transport_evidence_bindings"]
                if normalized_transport_binding is None
                else [
                    *checkpoint["transport_evidence_bindings"],
                    normalized_transport_binding,
                ]
            ),
            "updated_at": recorded_at_by_event["COMPLETION_SEALED"],
        },
    )


def recover_persisted_v31_cycle(
    *,
    store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
    total_cycles: int,
    created_at: str,
) -> Mapping[str, Any]:
    """Recover and finish a cycle using only its durable typed bundle.

    No caller supplies typed objects, six chronology documents, selection
    fields, or event times.  All of them are rebuilt and semantically replayed
    from the write-once bundle before the process-local semantic admission is
    re-registered.
    """

    try:
        bundle = store.discover_content_addressed_document(
            relative_dir=(
                f"cycles/{cycle_index:04d}/{ASSEMBLY_BUNDLE_DIRECTORY}"
            ),
            digest_field="assembly_bundle_digest",
        )
        assembly_inputs, documents, event_times = (
            rebuild_v31_documents_from_bundle(bundle)
        )
        if (
            bundle.get("run_id") != run_id
            or bundle.get("cycle_index") != cycle_index
        ):
            raise V31DurableCycleError("V31_DURABLE_RECOVERY_IDENTITY_MISMATCH")
        return persist_completed_v31_cycle(
            store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            total_cycles=total_cycles,
            created_at=created_at,
            documents=documents,
            assembly_inputs=assembly_inputs,
            recorded_at_by_event=event_times,
        )
    except V31DurableCycleError:
        raise
    except (V31DurableBundleError, KeyError, TypeError, ValueError) as exc:
        raise V31DurableCycleError("V31_DURABLE_RECOVERY_FAILED_CLOSED") from exc


__all__ = [
    "V31DurableCycleError",
    "persist_completed_v31_cycle",
    "recover_persisted_v31_cycle",
    "v31_cycle_authoring_head_bindings",
    "v31_cycle_graph_state_relative_ref",
]
