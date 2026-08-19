"""Four-cycle native-Codex BTC market-pilot workflow.

The controller owns collection sealing, deterministic finance, acceptance and
the cursor.  Codex owns only one proposal and one deliberation delivery for the
active cycle through the write-once mailbox.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.governance.research_authority import (
    assert_research_start_authorized,
)
from ..domain.dynamic_research import build_sentiment_state
from ..domain.native_agent_transport import (
    NATIVE_AGENT_ID,
    NATIVE_EVIDENCE_LEVEL,
    build_native_agent_claim,
    build_native_agent_delivery,
    build_native_agent_request,
    build_native_consume_receipt,
    validate_native_agent_claim,
    validate_native_agent_delivery,
    validate_native_agent_request,
)
from ..domain.native_market_cycle import (
    SENTIMENT_DIMENSIONS,
    SENTIMENT_REQUIRED_DEPENDENCY_GROUPS,
    build_shadow_action_evaluation,
    validate_native_market_deliberation_payload,
    validate_native_market_proposal_payload,
)
from .ports import NativeMarketPilotStorePort


class NativeMarketPilotWorkflowError(ValueError):
    """The market pilot must stop before committing the next transition."""


_CONFIG_DIGEST = "native_market_pilot_config_digest"
_MANIFEST_DIGEST = "native_market_pilot_manifest_digest"
_SNAPSHOT_DIGEST = "native_market_snapshot_digest"
_PROPOSAL_INPUT_DIGEST = "native_market_proposal_input_digest"
_DELIBERATION_INPUT_DIGEST = "native_market_deliberation_input_digest"
_EVALUATION_DIGEST = "native_shadow_action_evaluation_digest"
_ACCEPTED_DIGEST = "native_market_accepted_state_digest"
_CYCLE_COMPLETION_DIGEST = "native_market_cycle_completion_digest"

_DIRECTLY_SIGNED_NUMERIC_FACTS = frozenset(
    {
        "book-top5-imbalance",
        "recent-trade-side-imbalance",
        "funding-rate",
        "open-interest-change-pct",
    }
)
_TIMEFRAME_RETURN_FACTS = {
    "15m": "candle-15m-return-pct",
    "1h": "candle-1h-return-pct",
    "4h": "candle-4h-return-pct",
    "1d": "candle-1d-return-pct",
}


def _cycle_ref(cycle_index: int, suffix: str) -> str:
    return f"cycles/{cycle_index:04d}/{suffix}"


def _request_ref(cycle_index: int, stage: str) -> str:
    return _cycle_ref(cycle_index, f"mailbox/requests/{stage.casefold()}.json")


def _claim_ref(cycle_index: int, stage: str) -> str:
    return _cycle_ref(cycle_index, f"mailbox/claims/{stage.casefold()}.json")


def _delivery_ref(cycle_index: int, stage: str) -> str:
    return _cycle_ref(cycle_index, f"mailbox/deliveries/{stage.casefold()}.json")


def _seal_ref(cycle_index: int, stage: str, kind: str) -> str:
    return _cycle_ref(
        cycle_index,
        f"mailbox/seals/{stage.casefold()}-{kind.casefold()}.json",
    )


def _consume_ref(cycle_index: int, stage: str) -> str:
    return _cycle_ref(
        cycle_index,
        f"receipts/{stage.casefold()}-consumed.json",
    )


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_TIME_INVALID")
    return parsed


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _is_directly_signed_numeric_fact(fact_id: str) -> bool:
    return (
        fact_id in _DIRECTLY_SIGNED_NUMERIC_FACTS
        or fact_id.startswith("candle-")
        and fact_id.endswith("-return-pct")
    )


def _numeric_fact_sign(*, fact: Mapping[str, Any], reason: str) -> int:
    value = fact.get("value")
    if not isinstance(value, str):
        raise NativeMarketPilotWorkflowError(reason)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise NativeMarketPilotWorkflowError(reason) from exc
    if not parsed.is_finite():
        raise NativeMarketPilotWorkflowError(reason)
    return -1 if parsed < 0 else 1 if parsed > 0 else 0


def _validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        verify_self_digest(config, _CONFIG_DIGEST)
    except ValueError as exc:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_DIGEST_INVALID") from exc
    if (
        config.get("schema_id") != "native_codex_market_pilot_config"
        or config.get("schema_version") != "1.0.0"
        or config.get("theory_authority_path") != "archive/authority/CORE_TRADING_THEORY_v2_1.md"
        or config.get("theory_authority_sha256")
        != "2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d"
        or config.get("candidate_theory_status") != "DRAFT_NOT_AUTHORITY"
        or config.get("sentiment_standard_path")
        != "theory/history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_2.md"
        or config.get("sentiment_standard_sha256")
        != "b67bc8fc24e5c5bef1f47a25eca31be7e994e9b7cc2354a6b1fb31dc0348a4ea"
        or config.get("agent_id") != NATIVE_AGENT_ID
        or config.get("evidence_level") != NATIVE_EVIDENCE_LEVEL
        or config.get("instrument_id") != "BTC-USDT-SWAP"
        or config.get("data_scope") != "OFFICIAL_PUBLIC_MARKET_ONLY"
        or config.get("total_cycles") != 4
        or config.get("cadence_seconds") != 3600
        or config.get("sentiment_dimensions") != list(SENTIMENT_DIMENSIONS)
        or config.get("sentiment_required_dependency_groups")
        != {
            axis: list(groups)
            for axis, groups in SENTIMENT_REQUIRED_DEPENDENCY_GROUPS.items()
        }
        or config.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or config.get("executable") is not False
        or config.get("account_access") is not False
        or config.get("order_submission") is not False
        or config.get("api_key_required") is not False
        or config.get("sub_agents_allowed") is not False
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_INVALID")
    if not isinstance(config.get("max_output_bytes"), int) or int(
        config["max_output_bytes"]
    ) < 1:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_INVALID")
    for field in (
        "probe_notional_usdt",
        "fee_rate",
        "slippage_rate",
        "max_probe_risk_usdt",
        "min_net_rr",
    ):
        value = config.get(field)
        if not isinstance(value, str) or not value:
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_INVALID")
    return dict(config)


def _validate_phase_b_gate(
    completion: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    try:
        verify_self_digest(completion, "native_transport_completion_receipt_digest")
    except ValueError as exc:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_PHASE_B_GATE_INVALID") from exc
    if (
        completion.get("schema_id") != "native_codex_transport_completion_receipt"
        or completion.get("durable_boundaries_verified")
        != ["PROPOSAL", "DELIBERATION", "POST_ACCEPT_TAIL"]
        or completion.get("proposal_reinvocation_count_after_consume") != 0
        or completion.get("deliberation_reinvocation_count_after_consume") != 0
        or completion.get("postaccept_agent_invocation_count") != 0
        or completion.get("market_data_accessed") is not False
        or completion.get("model_api_called") is not False
        or completion.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or binding.get("semantic_digest")
        != completion.get("native_transport_completion_receipt_digest")
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_PHASE_B_GATE_INVALID")


def initialize_native_market_pilot(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    created_at: str,
    config: Mapping[str, Any],
    config_physical_sha256: str,
    authority: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    phase_b_completion: Mapping[str, Any],
    phase_b_completion_binding: Mapping[str, Any],
    implementation_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    validated_config = _validate_config(config)
    if validated_config.get("run_id") != run_id:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_RUN_BINDING_INVALID")
    assert_research_start_authorized(
        authority,
        operation="RUN_NATIVE_MARKET_PILOT",
        run_id=run_id,
        template_sha256=config_physical_sha256,
        authorization_receipt=authorization_receipt,
    )
    _validate_phase_b_gate(phase_b_completion, phase_b_completion_binding)
    config_binding = store.write_document(
        relative_ref="frozen/market-pilot-config.json",
        document=validated_config,
        digest_field=_CONFIG_DIGEST,
    )
    authority_envelope = self_digest(
        {
            "schema_id": "native_market_frozen_authority_envelope",
            "schema_version": "1.0.0",
            "authority": dict(authority),
        },
        "native_market_frozen_authority_digest",
    )
    authority_binding = store.write_document(
        relative_ref="frozen/current-research-authority.json",
        document=authority_envelope,
        digest_field="native_market_frozen_authority_digest",
    )
    receipt_binding = store.write_document(
        relative_ref="frozen/research-authorization-receipt.json",
        document=authorization_receipt,
        digest_field="authorization_receipt_digest",
    )
    phase_b_binding = store.write_document(
        relative_ref="frozen/phase-b-completion.json",
        document=phase_b_completion,
        digest_field="native_transport_completion_receipt_digest",
    )
    if phase_b_binding["semantic_digest"] != phase_b_completion_binding["semantic_digest"]:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_PHASE_B_GATE_INVALID")
    first_due_at = str(validated_config["first_due_at"])
    _parse_time(first_due_at)
    manifest = self_digest(
        {
            "schema_id": "native_codex_market_pilot_manifest",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "created_at": created_at,
            "config_binding": dict(config_binding),
            "config_source_physical_sha256": config_physical_sha256,
            "authority_binding": dict(authority_binding),
            "authorization_receipt_binding": dict(receipt_binding),
            "phase_b_completion_binding": dict(phase_b_binding),
            "implementation_bindings": dict(implementation_bindings),
            "theory_authority_sha256": validated_config[
                "theory_authority_sha256"
            ],
            "sentiment_standard_sha256": validated_config[
                "sentiment_standard_sha256"
            ],
            "agent_id": NATIVE_AGENT_ID,
            "evidence_level": NATIVE_EVIDENCE_LEVEL,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        _MANIFEST_DIGEST,
    )
    store.write_document(
        relative_ref="manifest.json",
        document=manifest,
        digest_field=_MANIFEST_DIGEST,
    )
    checkpoint = store.initialize_market_checkpoint(
        run_id=run_id,
        created_at=created_at,
        first_due_at=first_due_at,
        total_cycles=4,
        cadence_seconds=3600,
    )
    return {
        "run_id": run_id,
        "status": checkpoint["status"],
        "cycle_index": checkpoint["cycle_index"],
        "manifest_digest": manifest[_MANIFEST_DIGEST],
        "checkpoint_digest": checkpoint["native_market_checkpoint_digest"],
        "next_due_at": first_due_at,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
    }


def _load_config(
    *, store: NativeMarketPilotStorePort, run_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    manifest = store.read_document(
        relative_ref="manifest.json", digest_field=_MANIFEST_DIGEST
    )
    if (
        manifest.get("run_id") != run_id
        or manifest.get("agent_id") != NATIVE_AGENT_ID
        or manifest.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or manifest.get("executable") is not False
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_MANIFEST_INVALID")
    binding = manifest.get("config_binding")
    if not isinstance(binding, Mapping):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_BINDING_INVALID")
    config = store.read_document(
        relative_ref=str(binding.get("relative_ref")),
        digest_field=_CONFIG_DIGEST,
        expected_semantic_digest=str(binding.get("semantic_digest")),
    )
    if store.artifact_binding(
        relative_ref=str(binding.get("relative_ref")),
        digest_field=_CONFIG_DIGEST,
        expected_semantic_digest=str(binding.get("semantic_digest")),
    ) != binding:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CONFIG_PHYSICAL_DRIFT")
    authority_binding = manifest.get("authority_binding")
    receipt_binding = manifest.get("authorization_receipt_binding")
    phase_b_binding = manifest.get("phase_b_completion_binding")
    if not all(
        isinstance(item, Mapping)
        for item in (authority_binding, receipt_binding, phase_b_binding)
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_AUTHORITY_BINDING_INVALID")
    authority_envelope = store.read_document(
        relative_ref=str(authority_binding.get("relative_ref")),
        digest_field="native_market_frozen_authority_digest",
        expected_semantic_digest=str(authority_binding.get("semantic_digest")),
    )
    if store.artifact_binding(
        relative_ref=str(authority_binding.get("relative_ref")),
        digest_field="native_market_frozen_authority_digest",
        expected_semantic_digest=str(authority_binding.get("semantic_digest")),
    ) != authority_binding:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_AUTHORITY_PHYSICAL_DRIFT")
    receipt = store.read_document(
        relative_ref=str(receipt_binding.get("relative_ref")),
        digest_field="authorization_receipt_digest",
        expected_semantic_digest=str(receipt_binding.get("semantic_digest")),
    )
    if store.artifact_binding(
        relative_ref=str(receipt_binding.get("relative_ref")),
        digest_field="authorization_receipt_digest",
        expected_semantic_digest=str(receipt_binding.get("semantic_digest")),
    ) != receipt_binding:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_AUTHORITY_PHYSICAL_DRIFT")
    phase_b = store.read_document(
        relative_ref=str(phase_b_binding.get("relative_ref")),
        digest_field="native_transport_completion_receipt_digest",
        expected_semantic_digest=str(phase_b_binding.get("semantic_digest")),
    )
    if store.artifact_binding(
        relative_ref=str(phase_b_binding.get("relative_ref")),
        digest_field="native_transport_completion_receipt_digest",
        expected_semantic_digest=str(phase_b_binding.get("semantic_digest")),
    ) != phase_b_binding:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_PHASE_B_PHYSICAL_DRIFT")
    authority = authority_envelope.get("authority")
    if not isinstance(authority, Mapping):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_AUTHORITY_BINDING_INVALID")
    assert_research_start_authorized(
        authority,
        operation="RUN_NATIVE_MARKET_PILOT",
        run_id=run_id,
        template_sha256=str(manifest["config_source_physical_sha256"]),
        authorization_receipt=receipt,
    )
    _validate_phase_b_gate(phase_b, phase_b_binding)
    return _validate_config(config), manifest


def _transition(
    *,
    store: NativeMarketPilotStorePort,
    checkpoint: Mapping[str, Any],
    updated_at: str,
    **changes: Any,
) -> Mapping[str, Any]:
    candidate = dict(checkpoint)
    candidate.update(changes)
    candidate["revision"] = int(checkpoint["revision"]) + 1
    candidate["updated_at"] = updated_at
    return store.replace_market_checkpoint(
        run_id=str(checkpoint["run_id"]),
        expected_checkpoint_digest=str(checkpoint["native_market_checkpoint_digest"]),
        checkpoint=candidate,
    )


def _write_seal(
    *,
    store: NativeMarketPilotStorePort,
    cycle_index: int,
    stage: str,
    kind: str,
    request_digest: str,
    binding: Mapping[str, Any],
) -> None:
    seal = self_digest(
        {
            "schema_id": "native_codex_market_mailbox_seal",
            "schema_version": "1.0.0",
            "cycle_index": cycle_index,
            "stage": stage,
            "artifact_kind": kind,
            "request_digest": request_digest,
            "artifact_binding": dict(binding),
        },
        "native_market_mailbox_seal_digest",
    )
    store.write_document(
        relative_ref=_seal_ref(cycle_index, stage, kind),
        document=seal,
        digest_field="native_market_mailbox_seal_digest",
    )


def _verify_seal(
    *,
    store: NativeMarketPilotStorePort,
    cycle_index: int,
    stage: str,
    kind: str,
    request_digest: str,
    binding: Mapping[str, Any],
) -> None:
    seal = store.read_document(
        relative_ref=_seal_ref(cycle_index, stage, kind),
        digest_field="native_market_mailbox_seal_digest",
    )
    if (
        seal.get("cycle_index") != cycle_index
        or seal.get("stage") != stage
        or seal.get("artifact_kind") != kind
        or seal.get("request_digest") != request_digest
        or seal.get("artifact_binding") != dict(binding)
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_MAILBOX_PHYSICAL_DRIFT")


def _seal_collection(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    cycle_index: int,
    snapshot: Mapping[str, Any],
    raw_body_by_request_id: Mapping[str, bytes],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        verify_self_digest(snapshot, _SNAPSHOT_DIGEST)
    except ValueError as exc:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SNAPSHOT_DIGEST_INVALID") from exc
    if (
        snapshot.get("run_id") != run_id
        or snapshot.get("cycle_index") != cycle_index
        or snapshot.get("point_in_time") is not True
        or snapshot.get("missing_is_zero") is not False
        or snapshot.get("account_data_accessed") is not False
        or snapshot.get("order_data_accessed") is not False
        or snapshot.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SNAPSHOT_INVALID")
    market_information = snapshot.get("market_information_snapshot")
    if not isinstance(market_information, Mapping):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_INFORMATION_SNAPSHOT_MISSING"
        )
    try:
        verify_self_digest(
            market_information, "market_information_snapshot_digest"
        )
    except ValueError as exc:
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_INFORMATION_SNAPSHOT_DIGEST_INVALID"
        ) from exc
    if (
        market_information.get("run_id") != run_id
        or market_information.get("cycle_index") != cycle_index
        or market_information.get("missing_values_are_zero") is not False
        or market_information.get("probability_status")
        != "NO_UNCALIBRATED_PROBABILITY"
    ):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_INFORMATION_SNAPSHOT_INVALID"
        )
    prior_snapshot = native_market_prior_snapshot(
        store=store,
        run_id=run_id,
        cycle_index=cycle_index,
    )
    expected_prior_digest = (
        prior_snapshot.get(_SNAPSHOT_DIGEST) if prior_snapshot else None
    )
    if snapshot.get("prior_market_snapshot_digest") != expected_prior_digest:
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_PRIOR_SNAPSHOT_BINDING_INVALID"
        )
    information_facts = market_information.get("facts")
    if not isinstance(information_facts, list):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_INFORMATION_SNAPSHOT_INVALID"
        )
    information_by_id = {
        str(row.get("fact_id")): row
        for row in information_facts
        if isinstance(row, Mapping)
    }
    change_fact = information_by_id.get("open-interest-change-pct")
    if not isinstance(change_fact, Mapping):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_OPEN_INTEREST_CHANGE_MISSING"
        )
    if cycle_index == 1:
        if (
            change_fact.get("value") is not None
            or "prior-cycle-open-interest-btc" in information_by_id
        ):
            raise NativeMarketPilotWorkflowError(
                "NATIVE_MARKET_FIRST_CYCLE_OI_CHANGE_INVALID"
            )
    elif "prior-cycle-open-interest-btc" not in information_by_id:
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_PRIOR_OPEN_INTEREST_FACT_MISSING"
        )
    captures = snapshot.get("source_captures")
    if not isinstance(captures, list) or not captures:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SOURCE_CAPTURE_INVALID")
    raw_bindings: dict[str, Mapping[str, str]] = {}
    capture_ids: set[str] = set()
    for capture in captures:
        if not isinstance(capture, Mapping):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SOURCE_CAPTURE_INVALID")
        request_id = str(capture.get("request_id") or "")
        raw = raw_body_by_request_id.get(request_id)
        if not request_id or request_id in capture_ids or not isinstance(raw, bytes):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_RAW_COVERAGE_INVALID")
        capture_ids.add(request_id)
        if hashlib.sha256(raw).hexdigest() != capture.get("raw_body_sha256"):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_RAW_DIGEST_MISMATCH")
        raw_bindings[request_id] = store.write_raw(
            relative_ref=_cycle_ref(
                cycle_index, f"market/raw/{request_id}.body"
            ),
            payload=raw,
        )
    required_ids = snapshot.get("required_request_ids")
    if (
        not isinstance(required_ids, list)
        or not required_ids
        or any(not isinstance(item, str) or not item for item in required_ids)
        or not set(required_ids).issubset(capture_ids)
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_REQUIRED_SOURCE_MISSING")
    if capture_ids != set(raw_body_by_request_id):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_RAW_COVERAGE_INVALID")
    snapshot_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "market/snapshot.json"),
        document=snapshot,
        digest_field=_SNAPSHOT_DIGEST,
    )
    receipt = self_digest(
        {
            "schema_id": "native_market_collection_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "snapshot_binding": dict(snapshot_binding),
            "raw_bindings": raw_bindings,
            "required_request_ids": snapshot.get("required_request_ids"),
            "optional_failures": snapshot.get("optional_failures"),
            "point_in_time": True,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_market_collection_receipt_digest",
    )
    store.write_document(
        relative_ref=_cycle_ref(cycle_index, "receipts/market-collected.json"),
        document=receipt,
        digest_field="native_market_collection_receipt_digest",
    )
    return snapshot_binding, receipt


def _prior_state(
    *, store: NativeMarketPilotStorePort, cycle_index: int
) -> Mapping[str, Any] | None:
    if cycle_index == 1:
        return None
    return store.read_document(
        relative_ref=_cycle_ref(cycle_index - 1, "state/accepted.json"),
        digest_field=_ACCEPTED_DIGEST,
    )


def native_market_prior_snapshot(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any] | None:
    """Load the previous completed snapshot through accepted/completion bindings."""

    if cycle_index == 1:
        return None
    if cycle_index < 1:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CYCLE_INDEX_INVALID")
    prior_cycle = cycle_index - 1
    accepted = _prior_state(store=store, cycle_index=cycle_index)
    if accepted is None:
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_PRIOR_ACCEPTED_STATE_MISSING"
        )
    completion = store.read_document(
        relative_ref=_cycle_ref(prior_cycle, "receipts/cycle-completed.json"),
        digest_field=_CYCLE_COMPLETION_DIGEST,
    )
    snapshot = store.read_document(
        relative_ref=_cycle_ref(prior_cycle, "market/snapshot.json"),
        digest_field=_SNAPSHOT_DIGEST,
        expected_semantic_digest=str(accepted.get("market_snapshot_digest")),
    )
    if (
        accepted.get("run_id") != run_id
        or accepted.get("cycle_index") != prior_cycle
        or completion.get("run_id") != run_id
        or completion.get("cycle_index") != prior_cycle
        or completion.get("accepted_state_digest")
        != accepted.get(_ACCEPTED_DIGEST)
        or snapshot.get("run_id") != run_id
        or snapshot.get("cycle_index") != prior_cycle
    ):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_PRIOR_COMPLETION_BINDING_INVALID"
        )
    return snapshot


def _open_proposal_request(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    cycle_index: int,
    now: str,
    config: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
) -> Mapping[str, Any]:
    prior = _prior_state(store=store, cycle_index=cycle_index)
    proposal_input = self_digest(
        {
            "schema_id": "native_codex_market_proposal_input",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "created_at": now,
            "market_snapshot_binding": dict(snapshot_binding),
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "mark_price": snapshot["mark_price"],
            "market_information_snapshot": snapshot[
                "market_information_snapshot"
            ],
            "facts": snapshot["market_information_snapshot"]["facts"],
            "prior_accepted_state_digest": (
                prior.get(_ACCEPTED_DIGEST) if prior else None
            ),
            "prior_hypothesis_registry": (
                prior.get("hypothesis_registry", {}) if prior else {}
            ),
            "prior_expectation_registry": (
                prior.get("expectation_registry", {}) if prior else {}
            ),
            "required_sentiment_dimensions": list(SENTIMENT_DIMENSIONS),
            "required_sentiment_dependency_groups": {
                axis: list(groups)
                for axis, groups in SENTIMENT_REQUIRED_DEPENDENCY_GROUPS.items()
            },
            "required_candidate_actions": ["WAIT", "OPEN_LONG", "OPEN_SHORT"],
            "dynamic_hypothesis_operations": ["CREATE", "UPDATE", "CLOSE"],
            "uncalibrated_numeric_probability_forbidden": True,
            "missing_must_remain_unknown": True,
            "private_chain_of_thought_requested": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        _PROPOSAL_INPUT_DIGEST,
    )
    input_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "inputs/proposal-input.json"),
        document=proposal_input,
        digest_field=_PROPOSAL_INPUT_DIGEST,
    )
    request = build_native_agent_request(
        run_id=run_id,
        cycle_index=cycle_index,
        stage="PROPOSAL",
        created_at=now,
        input_binding=input_binding,
        input_schema_id="native_codex_market_proposal_input",
        expected_output_schema_id="native_codex_market_proposal_payload",
        max_output_bytes=int(config["max_output_bytes"]),
        context_bindings={
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST]
        },
    )
    binding = store.write_document(
        relative_ref=_request_ref(cycle_index, "PROPOSAL"),
        document=request,
        digest_field="native_agent_request_digest",
    )
    _write_seal(
        store=store,
        cycle_index=cycle_index,
        stage="PROPOSAL",
        kind="REQUEST",
        request_digest=request["native_agent_request_digest"],
        binding=binding,
    )
    return request


def _read_stage(
    *,
    store: NativeMarketPilotStorePort,
    cycle_index: int,
    stage: str,
    consumed_at: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    request = store.read_document(
        relative_ref=_request_ref(cycle_index, stage),
        digest_field="native_agent_request_digest",
    )
    claim = store.read_document(
        relative_ref=_claim_ref(cycle_index, stage),
        digest_field="native_agent_claim_digest",
    )
    delivery = store.read_document(
        relative_ref=_delivery_ref(cycle_index, stage),
        digest_field="native_agent_delivery_digest",
    )
    validate_native_agent_request(request)
    validate_native_agent_claim(request=request, claim=claim)
    validate_native_agent_delivery(request=request, claim=claim, delivery=delivery)
    bindings = {
        "REQUEST": store.artifact_binding(
            relative_ref=_request_ref(cycle_index, stage),
            digest_field="native_agent_request_digest",
        ),
        "CLAIM": store.artifact_binding(
            relative_ref=_claim_ref(cycle_index, stage),
            digest_field="native_agent_claim_digest",
        ),
        "DELIVERY": store.artifact_binding(
            relative_ref=_delivery_ref(cycle_index, stage),
            digest_field="native_agent_delivery_digest",
        ),
    }
    for kind, binding in bindings.items():
        _verify_seal(
            store=store,
            cycle_index=cycle_index,
            stage=stage,
            kind=kind,
            request_digest=str(request["native_agent_request_digest"]),
            binding=binding,
        )
    input_digest_field = (
        _PROPOSAL_INPUT_DIGEST if stage == "PROPOSAL" else _DELIBERATION_INPUT_DIGEST
    )
    input_binding = store.artifact_binding(
        relative_ref=str(request["input_binding"]["relative_ref"]),
        digest_field=input_digest_field,
        expected_semantic_digest=str(request["input_binding"]["semantic_digest"]),
    )
    if input_binding != request["input_binding"]:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_INPUT_PHYSICAL_DRIFT")
    receipt = build_native_consume_receipt(
        request=request,
        request_binding=bindings["REQUEST"],
        claim=claim,
        claim_binding=bindings["CLAIM"],
        delivery=delivery,
        delivery_binding=bindings["DELIVERY"],
        consumed_at=consumed_at,
        next_status=(
            "WAITING_FOR_DELIBERATION"
            if stage == "PROPOSAL"
            else "POST_ACCEPT_PENDING"
        ),
    )
    store.write_document(
        relative_ref=_consume_ref(cycle_index, stage),
        document=receipt,
        digest_field="native_transport_consume_receipt_digest",
    )
    return request, delivery, receipt


def _validate_proposal_grounding(
    *,
    proposal: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
) -> None:
    market_information = snapshot.get("market_information_snapshot")
    if not isinstance(market_information, Mapping):
        raise NativeMarketPilotWorkflowError(
            "NATIVE_MARKET_INFORMATION_SNAPSHOT_MISSING"
        )
    facts = market_information.get("facts")
    if not isinstance(facts, list):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_FACT_CATALOG_INVALID")
    fact_by_id = {
        str(row.get("fact_id")): row
        for row in facts
        if isinstance(row, Mapping)
    }
    if len(fact_by_id) != len(facts):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_FACT_CATALOG_INVALID")
    all_refs = set(fact_by_id)
    observed_refs = {
        fact_id
        for fact_id, row in fact_by_id.items()
        if row.get("value") is not None
        and not fact_id.startswith("source-anchor-")
    }
    for row in proposal["sentiment_dimension_inputs"]:
        contributors = row.get("contributors", [])
        refs = {
            str(contributor.get("fact_id"))
            for contributor in contributors
            if isinstance(contributor, Mapping)
        }
        if not refs.issubset(observed_refs):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SENTIMENT_REF_INVALID")
        if row.get("axis") == "TIMEFRAME_COHERENCE":
            contributor_by_id = {
                str(contributor.get("fact_id")): contributor
                for contributor in contributors
                if isinstance(contributor, Mapping)
            }
            if (
                len(contributors) != len(_TIMEFRAME_RETURN_FACTS)
                or set(contributor_by_id) != set(_TIMEFRAME_RETURN_FACTS.values())
            ):
                raise NativeMarketPilotWorkflowError(
                    "NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID"
                )
            expected_states: dict[str, int] = {}
            for timeframe, fact_id in _TIMEFRAME_RETURN_FACTS.items():
                sign = _numeric_fact_sign(
                    fact=fact_by_id[fact_id],
                    reason="NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID",
                )
                if contributor_by_id[fact_id].get("ordinal_contribution") != sign:
                    raise NativeMarketPilotWorkflowError(
                        "NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID"
                    )
                expected_states[timeframe] = sign
            if row.get("timeframe_states") != expected_states:
                raise NativeMarketPilotWorkflowError(
                    "NATIVE_MARKET_TIMEFRAME_COHERENCE_GROUNDING_INVALID"
                )
            continue
        for contributor in contributors:
            fact_id = str(contributor.get("fact_id"))
            ordinal = contributor.get("ordinal_contribution")
            if (
                _is_directly_signed_numeric_fact(fact_id)
                and isinstance(ordinal, int)
                and not isinstance(ordinal, bool)
                and ordinal != 0
            ):
                numeric_sign = _numeric_fact_sign(
                    fact=fact_by_id[fact_id],
                    reason="NATIVE_MARKET_SENTIMENT_NUMERIC_SIGN_MISMATCH",
                )
                if numeric_sign == 0 or (ordinal > 0) != (numeric_sign > 0):
                    raise NativeMarketPilotWorkflowError(
                        "NATIVE_MARKET_SENTIMENT_NUMERIC_SIGN_MISMATCH"
                    )
    for row in proposal["public_inference_claims"]:
        if not (
            set(row["supporting_evidence_refs"]).issubset(all_refs)
            and set(row["counter_evidence_refs"]).issubset(all_refs)
        ):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_INFERENCE_REF_INVALID")
    for row in proposal["hypothesis_updates"]:
        if not set(row["evidence_refs"]).issubset(all_refs):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_HYPOTHESIS_REF_INVALID")
    for row in proposal["expectation_updates"]:
        if not set(row["evidence_refs"]).issubset(all_refs):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_EXPECTATION_REF_INVALID")
    for row in proposal["candidate_proposals"]:
        if not set(row["evidence_refs"]).issubset(observed_refs):
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CANDIDATE_REF_INVALID")
    prior_hypotheses = set((prior or {}).get("hypothesis_registry", {}))
    resulting = set(prior_hypotheses)
    resulting_status = {
        key: value.get("status")
        for key, value in (prior or {}).get("hypothesis_registry", {}).items()
        if isinstance(value, Mapping)
    }
    for row in proposal["hypothesis_updates"]:
        identifier, operation = row["hypothesis_id"], row["operation"]
        if operation == "CREATE":
            if identifier in resulting:
                raise NativeMarketPilotWorkflowError("NATIVE_MARKET_HYPOTHESIS_CREATE_CONFLICT")
            resulting.add(identifier)
        elif identifier not in resulting:
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_HYPOTHESIS_UPDATE_MISSING")
        resulting_status[identifier] = row["status"]
    competition = proposal["path_competition"]
    if not {
        competition["lead_path_id"],
        competition["runner_up_path_id"],
        competition["other_path_id"],
    }.issubset(
        {key for key in resulting if resulting_status.get(key) != "CLOSED"}
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_PATH_NOT_REGISTERED")
    if any(
        row["hypothesis_id"] not in resulting
        or resulting_status.get(row["hypothesis_id"]) == "CLOSED"
        for row in proposal["candidate_proposals"]
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CANDIDATE_HYPOTHESIS_INVALID")


def _open_deliberation_request(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    cycle_index: int,
    now: str,
    config: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    proposal = proposal_delivery["payload"]
    sentiment_state = build_sentiment_state(
        market_snapshot=snapshot["market_information_snapshot"],
        dimension_inputs=proposal["sentiment_dimension_inputs"],
        operational_synthesis=proposal["operational_synthesis"],
    )
    sentiment_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "analysis/sentiment-state.json"),
        document=sentiment_state,
        digest_field="sentiment_state_digest",
    )
    evaluation = build_shadow_action_evaluation(
        run_id=run_id,
        cycle_index=cycle_index,
        market_snapshot_digest=str(snapshot[_SNAPSHOT_DIGEST]),
        mark_price=str(snapshot["mark_price"]),
        valid_evidence_refs=[
            str(row["fact_id"])
            for row in snapshot["market_information_snapshot"]["facts"]
            if row["value"] is not None
            and not str(row["fact_id"]).startswith("source-anchor-")
        ],
        candidate_proposals=proposal["candidate_proposals"],
        notional_usdt=str(config["probe_notional_usdt"]),
        fee_rate=str(config["fee_rate"]),
        slippage_rate=str(config["slippage_rate"]),
        max_probe_risk_usdt=str(config["max_probe_risk_usdt"]),
        min_net_rr=str(config["min_net_rr"]),
    )
    evaluation_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "evaluation/shadow-actions.json"),
        document=evaluation,
        digest_field=_EVALUATION_DIGEST,
    )
    deliberation_input = self_digest(
        {
            "schema_id": "native_codex_market_deliberation_input",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "created_at": now,
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "proposal_payload_digest": proposal_delivery["payload_digest"],
            "sentiment_state_binding": dict(sentiment_binding),
            "evaluation_binding": dict(evaluation_binding),
            "candidate_evaluations": evaluation["candidates"],
            "selection_rule": "SELECT_ONE_FEASIBLE_CANDIDATE_AND_EXPLAIN_ALL_OTHERS",
            "private_chain_of_thought_requested": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        _DELIBERATION_INPUT_DIGEST,
    )
    input_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "inputs/deliberation-input.json"),
        document=deliberation_input,
        digest_field=_DELIBERATION_INPUT_DIGEST,
    )
    request = build_native_agent_request(
        run_id=run_id,
        cycle_index=cycle_index,
        stage="DELIBERATION",
        created_at=now,
        input_binding=input_binding,
        input_schema_id="native_codex_market_deliberation_input",
        expected_output_schema_id="native_codex_market_deliberation_payload",
        max_output_bytes=int(config["max_output_bytes"]),
        context_bindings={
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "evaluation_digest": evaluation[_EVALUATION_DIGEST],
        },
    )
    request_binding = store.write_document(
        relative_ref=_request_ref(cycle_index, "DELIBERATION"),
        document=request,
        digest_field="native_agent_request_digest",
    )
    _write_seal(
        store=store,
        cycle_index=cycle_index,
        stage="DELIBERATION",
        kind="REQUEST",
        request_digest=request["native_agent_request_digest"],
        binding=request_binding,
    )
    return request, evaluation, sentiment_state


def _apply_registry(
    *, prior: Mapping[str, Any], rows: list[Mapping[str, Any]], id_field: str, cycle_index: int
) -> dict[str, Any]:
    registry = {key: dict(value) for key, value in prior.items()}
    for row in rows:
        identifier = str(row[id_field])
        if row["operation"] == "CREATE" and identifier in registry:
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_REGISTRY_CREATE_CONFLICT")
        if row["operation"] != "CREATE" and identifier not in registry:
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_REGISTRY_UPDATE_MISSING")
        registry[identifier] = {**dict(row), "last_update_cycle": cycle_index}
    return registry


def _prior_shadow_observation(
    *, prior: Mapping[str, Any] | None, current_mark: str
) -> list[dict[str, Any]]:
    if prior is None:
        return []
    candidate = prior.get("selected_candidate")
    if not isinstance(candidate, Mapping) or candidate.get("action_class") == "WAIT":
        return [
            {
                "source_cycle_index": prior.get("cycle_index"),
                "action_class": "WAIT",
                "status": "NO_POSITION_WAIT_WAS_SELECTED",
                "current_mark_price": current_mark,
                "directional_move_pct": None,
            }
        ]
    entry = Decimal(str(candidate["entry_reference_price"]))
    mark = Decimal(current_mark)
    direction = Decimal("1") if candidate["action_class"] == "OPEN_LONG" else Decimal("-1")
    move = (mark / entry - Decimal("1")) * Decimal("100") * direction
    from ..domain.contracts.canonical import canonical_decimal

    return [
        {
            "source_cycle_index": prior.get("cycle_index"),
            "action_class": candidate["action_class"],
            "status": "OBSERVED_NOT_FINAL_OUTCOME",
            "current_mark_price": current_mark,
            "directional_move_pct": canonical_decimal(move),
        }
    ]


def _accept_cycle(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    cycle_index: int,
    now: str,
    snapshot: Mapping[str, Any],
    deliberation_delivery: Mapping[str, Any],
) -> Mapping[str, Any]:
    proposal_delivery = store.read_document(
        relative_ref=_delivery_ref(cycle_index, "PROPOSAL"),
        digest_field="native_agent_delivery_digest",
    )
    proposal = proposal_delivery["payload"]
    deliberation = deliberation_delivery["payload"]
    evaluation = store.read_document(
        relative_ref=_cycle_ref(cycle_index, "evaluation/shadow-actions.json"),
        digest_field=_EVALUATION_DIGEST,
    )
    by_id = {row["candidate_id"]: row for row in proposal["candidate_proposals"]}
    eval_by_id = {row["candidate_id"]: row for row in evaluation["candidates"]}
    selected_id = deliberation["selected_candidate_id"]
    if (
        selected_id not in by_id
        or selected_id not in eval_by_id
        or eval_by_id[selected_id]["feasible"] is not True
        or set(deliberation["ranked_alternative_ids"])
        != set(by_id) - {selected_id}
    ):
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_SELECTION_INVALID")
    prior = _prior_state(store=store, cycle_index=cycle_index)
    hypothesis_registry = _apply_registry(
        prior=(prior or {}).get("hypothesis_registry", {}),
        rows=proposal["hypothesis_updates"],
        id_field="hypothesis_id",
        cycle_index=cycle_index,
    )
    expectation_registry = _apply_registry(
        prior=(prior or {}).get("expectation_registry", {}),
        rows=proposal["expectation_updates"],
        id_field="expectation_id",
        cycle_index=cycle_index,
    )
    preaccept = self_digest(
        {
            "schema_id": "native_market_preaccept_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "proposal_delivery_digest": proposal_delivery[
                "native_agent_delivery_digest"
            ],
            "evaluation_digest": evaluation[_EVALUATION_DIGEST],
            "deliberation_delivery_digest": deliberation_delivery[
                "native_agent_delivery_digest"
            ],
            "selected_candidate_id": selected_id,
            "selected_feasible": True,
            "financial_recalculation_owner": "DETERMINISTIC_DOMAIN",
            "current_cycle_grounding_verified": True,
            "complete_action_set_verified": True,
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "recorded_at": now,
        },
        "native_market_preaccept_receipt_digest",
    )
    preaccept_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "receipts/preaccept.json"),
        document=preaccept,
        digest_field="native_market_preaccept_receipt_digest",
    )
    accepted = self_digest(
        {
            "schema_id": "native_codex_market_accepted_state",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "accepted_at": now,
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "mark_price": snapshot["mark_price"],
            "sentiment_state": store.read_document(
                relative_ref=_cycle_ref(cycle_index, "analysis/sentiment-state.json"),
                digest_field="sentiment_state_digest",
            ),
            "public_inference_claims": proposal["public_inference_claims"],
            "path_competition": proposal["path_competition"],
            "hypothesis_registry": hypothesis_registry,
            "expectation_registry": expectation_registry,
            "candidate_proposals": proposal["candidate_proposals"],
            "candidate_evaluations": evaluation["candidates"],
            "selected_candidate": by_id[selected_id],
            "selected_candidate_evaluation": eval_by_id[selected_id],
            "selection_rationale": deliberation["selection_rationale"],
            "why_not_selected": deliberation["why_not_selected"],
            "next_review_condition": deliberation["next_review_condition"],
            "prior_shadow_observations": _prior_shadow_observation(
                prior=prior, current_mark=str(snapshot["mark_price"])
            ),
            "preaccept_binding": dict(preaccept_binding),
            "shadow_only": True,
            "order_sent": False,
            "account_accessed": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "predictive_validity_claimed": False,
            "profitability_claimed": False,
        },
        _ACCEPTED_DIGEST,
    )
    store.write_document(
        relative_ref=_cycle_ref(cycle_index, "state/accepted.json"),
        document=accepted,
        digest_field=_ACCEPTED_DIGEST,
    )
    return accepted


def _complete_cycle(
    *,
    store: NativeMarketPilotStorePort,
    checkpoint: Mapping[str, Any],
    now: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    cycle_index = int(checkpoint["cycle_index"])
    snapshot = store.read_document(
        relative_ref=_cycle_ref(cycle_index, "market/snapshot.json"),
        digest_field=_SNAPSHOT_DIGEST,
    )
    accepted = store.read_document(
        relative_ref=_cycle_ref(cycle_index, "state/accepted.json"),
        digest_field=_ACCEPTED_DIGEST,
    )
    report = self_digest(
        {
            "schema_id": "native_market_cycle_report",
            "schema_version": "1.0.0",
            "run_id": checkpoint["run_id"],
            "cycle_index": cycle_index,
            "reported_at": now,
            "market_snapshot_digest": snapshot[_SNAPSHOT_DIGEST],
            "captured_through": snapshot["captured_through"],
            "market_information_snapshot": snapshot[
                "market_information_snapshot"
            ],
            "optional_source_failures": snapshot["optional_failures"],
            "sentiment_state": accepted["sentiment_state"],
            "public_inference_claims": accepted["public_inference_claims"],
            "path_competition": accepted["path_competition"],
            "hypothesis_registry": accepted["hypothesis_registry"],
            "expectation_registry": accepted["expectation_registry"],
            "candidate_proposals": accepted["candidate_proposals"],
            "candidate_evaluations": accepted["candidate_evaluations"],
            "selected_candidate": accepted["selected_candidate"],
            "selection_rationale": accepted["selection_rationale"],
            "why_not_selected": accepted["why_not_selected"],
            "prior_shadow_observations": accepted["prior_shadow_observations"],
            "next_review_condition": accepted["next_review_condition"],
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_market_cycle_report_digest",
    )
    report_binding = store.write_document(
        relative_ref=_cycle_ref(cycle_index, "report/cycle-report.json"),
        document=report,
        digest_field="native_market_cycle_report_digest",
    )
    completion = self_digest(
        {
            "schema_id": "native_market_cycle_completion_receipt",
            "schema_version": "1.0.0",
            "run_id": checkpoint["run_id"],
            "cycle_index": cycle_index,
            "completed_at": now,
            "accepted_state_digest": accepted[_ACCEPTED_DIGEST],
            "report_binding": dict(report_binding),
            "proposal_reinvocation_count_after_consume": 0,
            "deliberation_reinvocation_count_after_consume": 0,
            "postaccept_agent_invocation_count": 0,
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        _CYCLE_COMPLETION_DIGEST,
    )
    store.write_document(
        relative_ref=_cycle_ref(cycle_index, "receipts/cycle-completed.json"),
        document=completion,
        digest_field=_CYCLE_COMPLETION_DIGEST,
    )
    return accepted, completion


def advance_native_market_pilot(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    now: str,
    snapshot: Mapping[str, Any] | None = None,
    raw_body_by_request_id: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    config, _ = _load_config(store=store, run_id=run_id)
    checkpoint = store.load_market_checkpoint(run_id=run_id)
    status = str(checkpoint["status"])
    cycle_index = int(checkpoint["cycle_index"])
    if status == "READY_FOR_CYCLE":
        if _parse_time(now) < _parse_time(checkpoint["next_due_at"]):
            return native_market_pilot_status(store=store, run_id=run_id, now=now)
        if snapshot is None or raw_body_by_request_id is None:
            raise NativeMarketPilotWorkflowError("NATIVE_MARKET_COLLECTION_REQUIRED")
        snapshot_binding, collection_receipt = _seal_collection(
            store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            snapshot=snapshot,
            raw_body_by_request_id=raw_body_by_request_id,
        )
        request = _open_proposal_request(
            store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            now=now,
            config=config,
            snapshot=snapshot,
            snapshot_binding=snapshot_binding,
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="WAITING_FOR_PROPOSAL",
            active_stage="PROPOSAL",
            active_request_digest=request["native_agent_request_digest"],
            active_market_snapshot_digest=snapshot[_SNAPSHOT_DIGEST],
            last_consume_receipt_digest=collection_receipt[
                "native_market_collection_receipt_digest"
            ],
        )
    elif status == "WAITING_FOR_PROPOSAL":
        _, delivery, receipt = _read_stage(
            store=store,
            cycle_index=cycle_index,
            stage="PROPOSAL",
            consumed_at=now,
        )
        snapshot = store.read_document(
            relative_ref=_cycle_ref(cycle_index, "market/snapshot.json"),
            digest_field=_SNAPSHOT_DIGEST,
            expected_semantic_digest=str(checkpoint["active_market_snapshot_digest"]),
        )
        proposal = validate_native_market_proposal_payload(
            request=store.read_document(
                relative_ref=_request_ref(cycle_index, "PROPOSAL"),
                digest_field="native_agent_request_digest",
            ),
            payload=delivery["payload"],
        )
        _validate_proposal_grounding(
            proposal=proposal,
            snapshot=snapshot,
            prior=_prior_state(store=store, cycle_index=cycle_index),
        )
        request, _, _ = _open_deliberation_request(
            store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            now=now,
            config=config,
            snapshot=snapshot,
            proposal_delivery=delivery,
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="WAITING_FOR_DELIBERATION",
            active_stage="DELIBERATION",
            active_request_digest=request["native_agent_request_digest"],
            last_consume_receipt_digest=receipt[
                "native_transport_consume_receipt_digest"
            ],
        )
    elif status == "WAITING_FOR_DELIBERATION":
        request, delivery, receipt = _read_stage(
            store=store,
            cycle_index=cycle_index,
            stage="DELIBERATION",
            consumed_at=now,
        )
        validate_native_market_deliberation_payload(
            request=request, payload=delivery["payload"]
        )
        snapshot = store.read_document(
            relative_ref=_cycle_ref(cycle_index, "market/snapshot.json"),
            digest_field=_SNAPSHOT_DIGEST,
            expected_semantic_digest=str(checkpoint["active_market_snapshot_digest"]),
        )
        accepted = _accept_cycle(
            store=store,
            run_id=run_id,
            cycle_index=cycle_index,
            now=now,
            snapshot=snapshot,
            deliberation_delivery=delivery,
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="POST_ACCEPT_PENDING",
            active_stage=None,
            active_request_digest=None,
            last_consume_receipt_digest=receipt[
                "native_transport_consume_receipt_digest"
            ],
            last_accepted_state_digest=accepted[_ACCEPTED_DIGEST],
        )
    elif status == "POST_ACCEPT_PENDING":
        _, completion = _complete_cycle(
            store=store, checkpoint=checkpoint, now=now
        )
        terminal = cycle_index == int(checkpoint["total_cycles"])
        next_due = _parse_time(checkpoint["next_due_at"]) + timedelta(
            seconds=int(checkpoint["cadence_seconds"])
        )
        checkpoint = _transition(
            store=store,
            checkpoint=checkpoint,
            updated_at=now,
            status="COMPLETED" if terminal else "READY_FOR_CYCLE",
            cycle_index=cycle_index if terminal else cycle_index + 1,
            next_due_at=_time(next_due),
            active_stage=None,
            active_request_digest=None,
            active_market_snapshot_digest=None,
            last_completion_receipt_digest=completion[_CYCLE_COMPLETION_DIGEST],
        )
    elif status == "COMPLETED":
        return native_market_pilot_status(store=store, run_id=run_id, now=now)
    else:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CHECKPOINT_STATUS_INVALID")
    return native_market_pilot_status(store=store, run_id=run_id, now=now)


def claim_native_market_request(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    stage: str,
    claimed_at: str,
) -> dict[str, Any]:
    checkpoint = store.load_market_checkpoint(run_id=run_id)
    expected_status = (
        "WAITING_FOR_PROPOSAL" if stage == "PROPOSAL" else "WAITING_FOR_DELIBERATION"
    )
    if checkpoint.get("status") != expected_status or checkpoint.get("active_stage") != stage:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_CLAIM_STAGE_INVALID")
    cycle_index = int(checkpoint["cycle_index"])
    request = store.read_document(
        relative_ref=_request_ref(cycle_index, stage),
        digest_field="native_agent_request_digest",
        expected_semantic_digest=str(checkpoint["active_request_digest"]),
    )
    validate_native_agent_request(request)
    ref = _claim_ref(cycle_index, stage)
    if store.document_exists(relative_ref=ref):
        claim = store.read_document(
            relative_ref=ref, digest_field="native_agent_claim_digest"
        )
        validate_native_agent_claim(request=request, claim=claim)
    else:
        claim = build_native_agent_claim(
            request=request,
            claim_id=canonical_digest(
                {
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "stage": stage,
                    "request_digest": request["native_agent_request_digest"],
                }
            ),
            claimed_at=claimed_at,
        )
        store.write_document(
            relative_ref=ref,
            document=claim,
            digest_field="native_agent_claim_digest",
        )
    binding = store.artifact_binding(
        relative_ref=ref, digest_field="native_agent_claim_digest"
    )
    seal_ref = _seal_ref(cycle_index, stage, "CLAIM")
    if not store.document_exists(relative_ref=seal_ref):
        _write_seal(
            store=store,
            cycle_index=cycle_index,
            stage=stage,
            kind="CLAIM",
            request_digest=str(request["native_agent_request_digest"]),
            binding=binding,
        )
    else:
        _verify_seal(
            store=store,
            cycle_index=cycle_index,
            stage=stage,
            kind="CLAIM",
            request_digest=str(request["native_agent_request_digest"]),
            binding=binding,
        )
    return dict(claim)


def submit_native_market_delivery(
    *,
    store: NativeMarketPilotStorePort,
    run_id: str,
    stage: str,
    payload: Mapping[str, Any],
    delivered_at: str,
) -> dict[str, Any]:
    checkpoint = store.load_market_checkpoint(run_id=run_id)
    expected_status = (
        "WAITING_FOR_PROPOSAL" if stage == "PROPOSAL" else "WAITING_FOR_DELIBERATION"
    )
    if checkpoint.get("status") != expected_status or checkpoint.get("active_stage") != stage:
        raise NativeMarketPilotWorkflowError("NATIVE_MARKET_DELIVERY_STAGE_INVALID")
    cycle_index = int(checkpoint["cycle_index"])
    request = store.read_document(
        relative_ref=_request_ref(cycle_index, stage),
        digest_field="native_agent_request_digest",
        expected_semantic_digest=str(checkpoint["active_request_digest"]),
    )
    claim = store.read_document(
        relative_ref=_claim_ref(cycle_index, stage),
        digest_field="native_agent_claim_digest",
    )
    delivery = build_native_agent_delivery(
        request=request,
        claim=claim,
        payload=payload,
        delivered_at=delivered_at,
    )
    ref = _delivery_ref(cycle_index, stage)
    if store.document_exists(relative_ref=ref):
        existing = store.read_document(
            relative_ref=ref, digest_field="native_agent_delivery_digest"
        )
        if existing.get("payload_digest") != delivery.get("payload_digest"):
            raise NativeMarketPilotWorkflowError(
                "NATIVE_MARKET_DELIVERY_WRITE_ONCE_CONFLICT"
            )
        delivery = dict(existing)
    else:
        store.write_document(
            relative_ref=ref,
            document=delivery,
            digest_field="native_agent_delivery_digest",
        )
    binding = store.artifact_binding(
        relative_ref=ref, digest_field="native_agent_delivery_digest"
    )
    seal_ref = _seal_ref(cycle_index, stage, "DELIVERY")
    if not store.document_exists(relative_ref=seal_ref):
        _write_seal(
            store=store,
            cycle_index=cycle_index,
            stage=stage,
            kind="DELIVERY",
            request_digest=str(request["native_agent_request_digest"]),
            binding=binding,
        )
    else:
        _verify_seal(
            store=store,
            cycle_index=cycle_index,
            stage=stage,
            kind="DELIVERY",
            request_digest=str(request["native_agent_request_digest"]),
            binding=binding,
        )
    return dict(delivery)


def native_market_pilot_status(
    *, store: NativeMarketPilotStorePort, run_id: str, now: str
) -> dict[str, Any]:
    _, manifest = _load_config(store=store, run_id=run_id)
    checkpoint = store.load_market_checkpoint(run_id=run_id)
    status = str(checkpoint["status"])
    if status == "READY_FOR_CYCLE":
        next_action = (
            "COLLECT_ONE_DUE_CYCLE"
            if _parse_time(now) >= _parse_time(checkpoint["next_due_at"])
            else "WAIT_UNTIL_DUE"
        )
    elif status == "WAITING_FOR_PROPOSAL":
        next_action = "CURRENT_CODEX_CLAIM_AND_SUBMIT_PROPOSAL"
    elif status == "WAITING_FOR_DELIBERATION":
        next_action = "CURRENT_CODEX_CLAIM_AND_SUBMIT_DELIBERATION"
    elif status == "POST_ACCEPT_PENDING":
        next_action = "RUN_DETERMINISTIC_POST_ACCEPT_TAIL"
    elif status == "COMPLETED":
        next_action = "NOOP_PILOT_COMPLETE"
    else:
        next_action = "FAIL_CLOSED_UNKNOWN_STATUS"
    return {
        "run_id": run_id,
        "manifest_digest": manifest[_MANIFEST_DIGEST],
        "checkpoint_digest": checkpoint["native_market_checkpoint_digest"],
        "revision": checkpoint["revision"],
        "status": status,
        "cycle_index": checkpoint["cycle_index"],
        "total_cycles": checkpoint["total_cycles"],
        "next_due_at": checkpoint["next_due_at"],
        "active_stage": checkpoint["active_stage"],
        "active_request_digest": checkpoint["active_request_digest"],
        "last_accepted_state_digest": checkpoint["last_accepted_state_digest"],
        "last_completion_receipt_digest": checkpoint[
            "last_completion_receipt_digest"
        ],
        "next_action": next_action,
        "agent_id": NATIVE_AGENT_ID,
        "evidence_level": NATIVE_EVIDENCE_LEVEL,
        "actual_state_verified": True,
        "chat_history_is_authority": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "order_sent": False,
    }


__all__ = [
    "NativeMarketPilotWorkflowError",
    "advance_native_market_pilot",
    "claim_native_market_request",
    "initialize_native_market_pilot",
    "native_market_prior_snapshot",
    "native_market_pilot_status",
    "submit_native_market_delivery",
]
