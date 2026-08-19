"""Strict V3.2 Agent semantic-output compilation.

This Application module closes the boundary between a terminal current-root
Agent delivery and the typed V3.2 Domain documents used by the lifecycle.  It
does not invoke an Agent, read files, fetch data, persist state, use an account,
or execute an action.

The causal order is intentional:

* the Proposal payload contains a verified dynamic-research state, unsealed
  preselection material, and one complete action-plan variant for every
  eligible candidate;
* only after Proposal delivery consumption does this compiler seal the Domain
  action evaluation with the real consumption digest;
* the Selection payload can choose exactly one sealed eligible variant and can
  repeat only its deterministically derived reason code and evidence refs;
* only after Selection delivery consumption does this compiler expose the
  exact selected plan as final commit material.

Every Agent payload is a canonical UTF-8 JSON object.  Duplicate keys,
non-canonical byte presentation, extra fields, unsupported self-digests,
candidate/risk/plan drift, and receipt self-digest laundering fail closed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    PROPOSAL_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_DIGEST_FIELD,
    V32AgentLifecycleError,
    build_v32_action_evaluation_v1,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_action_evaluation_v1,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_v1,
    verify_v32_selection_canonical_packet_v1,
)
from ..domain.v32_dynamic_action_plan import (
    CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES,
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    INSTRUMENT_CHURN_ACTION_KINDS,
    NO_NEW_CURRENT_PIT_EVIDENCE_REF,
    OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE_REF,
    RISK_INCREASING_ACTIONS,
    V32DynamicActionPlanError,
    verify_v32_dynamic_action_plan_v1,
)
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    SUBJECTIVE_TIER_RISK_CAP_UNITS,
    V32DynamicResearchError,
    verify_v32_dynamic_research_state_v1,
)


class V32AgentSemanticCompilerError(ValueError):
    """A V3.2 semantic output or deterministic compilation drifted."""


SCHEMA_VERSION = "1.0.0"

PROPOSAL_SEMANTIC_OUTPUT_SCHEMA_ID = (
    "theory_paper_v32_agent_proposal_semantic_output_v1"
)
PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD = "proposal_semantic_output_digest"
PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID = (
    "theory_paper_v32_agent_proposal_semantic_compile_receipt_v1"
)
PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD = "proposal_semantic_compile_receipt_digest"

SELECTION_SEMANTIC_OUTPUT_SCHEMA_ID = (
    "theory_paper_v32_agent_selection_semantic_output_v1"
)
SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD = "selection_semantic_output_digest"
SELECTION_COMPILE_RECEIPT_SCHEMA_ID = (
    "theory_paper_v32_agent_selection_semantic_compile_receipt_v1"
)
SELECTION_COMPILE_RECEIPT_DIGEST_FIELD = "selection_semantic_compile_receipt_digest"

_SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
_AUTHORITY = "NONE_LOCAL_SIMULATION"
_CLAIM = "CANONICAL_AGENT_SEMANTICS_ONLY_NO_EXECUTION_OR_OUTCOME_CLAIM"
_DUMMY_CONSUMPTION_DIGEST = "0" * 64
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_DOMAIN_DERIVED_ZERO_RISK_BLOCK_REASONS = frozenset(
    {
        "PATH_MODIFIER_INVALIDATION",
        "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
        "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
    }
)

_PRESELECTION_FIELDS = frozenset(
    {
        "reference_context",
        "risk_arithmetic",
        "risk_arithmetic_digest",
        "candidate_rows",
        "candidate_rows_digest",
    }
)
_VARIANT_FIELDS = frozenset(
    {
        "variant_id",
        "candidate_id",
        "dynamic_action_plan",
        "dynamic_action_plan_digest",
    }
)
_PROPOSAL_OUTPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "agent_stage",
        "proposal_input_context_digest",
        "proposal_canonical_packet_digest",
        "current_dynamic_research_state",
        "current_dynamic_research_state_digest",
        "preselection_candidate_material",
        "sealed_plan_variants",
        "eligible_candidate_ids",
        "selection_present",
        "source_scope",
        "external_execution_authority",
        "executable",
        "claim",
        PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD,
    }
)
_PROPOSAL_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "compiled_at",
        "proposal_input_context_digest",
        "proposal_delivery_digest",
        "proposal_consumption_digest",
        "proposal_payload_sha256",
        "proposal_semantic_output_digest",
        "compiled_dynamic_research_state",
        "compiled_dynamic_research_state_digest",
        "sealed_action_evaluation",
        "sealed_action_evaluation_digest",
        "sealed_plan_variants",
        "eligible_candidate_ids",
        "compile_status",
        "source_scope",
        "external_execution_authority",
        "executable",
        "claim",
        PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
    }
)
_SELECTION_OUTPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "agent_stage",
        "selection_input_context_digest",
        "selection_canonical_packet_digest",
        "proposal_semantic_output_digest",
        "sealed_action_evaluation_digest",
        "selected_variant_id",
        "selected_candidate_id",
        "selection_reason_code",
        "selection_reason_refs",
        "source_scope",
        "external_execution_authority",
        "executable",
        "claim",
        SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD,
    }
)
_SELECTION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "compiled_at",
        "proposal_semantic_compile_receipt_digest",
        "selection_input_context_digest",
        "selection_delivery_digest",
        "selection_consumption_digest",
        "selection_payload_sha256",
        "selection_semantic_output_digest",
        "compiled_dynamic_research_state_digest",
        "sealed_action_evaluation_digest",
        "selected_variant_id",
        "selected_candidate_id",
        "selection_reason_code",
        "selection_reason_refs",
        "final_dynamic_action_plan",
        "final_dynamic_action_plan_digest",
        "compile_status",
        "source_scope",
        "external_execution_authority",
        "executable",
        "claim",
        SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
    }
)

_VARIANT_ALLOWED_DIFFERENCES = frozenset(
    {
        "selected_candidate_id",
        "selected_candidate_reference_risk_budget",
        "alternative_candidate_rank",
        "wait_assessment",
        ACTION_PLAN_DIGEST_FIELD,
    }
)

_OBJECTIVE_REFERENCE_TRANCHE_FIELDS = (
    "multiplier_reference",
    "fee_stress_reference",
    "slippage_stress_reference",
    "funding_bound_reference",
    "tail_gap_reference",
    "reference_scale_quantum",
)
_PIT_DATUM_SCHEMA_ID = "theory_paper_v32_minimal_pit_datum_v1"
_PIT_DATUM_DIGEST_FIELD = "pit_datum_digest"
_PIT_DATUM_SCHEMA_VERSION = "1.1.0"


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AgentSemanticCompilerError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32AgentSemanticCompilerError(code)
    return value


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32AgentSemanticCompilerError("V32_AGENT_SEMANTIC_CYCLE_INVALID")
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AgentSemanticCompilerError(code) from exc
    if parsed.tzinfo is None:
        raise V32AgentSemanticCompilerError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32AgentSemanticCompilerError(code)
    return canonical


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _strings(value: Any, code: str, *, allow_empty: bool = True) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32AgentSemanticCompilerError(code)
    rows = [_text(item, code) for item in value]
    if (not allow_empty and not rows) or rows != sorted(set(rows)):
        raise V32AgentSemanticCompilerError(code)
    return rows


def _boundary(document: Mapping[str, Any], code: str) -> None:
    if (
        document.get("source_scope") != _SOURCE_SCOPE
        or document.get("external_execution_authority") != _AUTHORITY
        or document.get("executable") is not False
        or document.get("claim") != _CLAIM
    ):
        raise V32AgentSemanticCompilerError(code)


def _validate_contract_hypothesis_ttl(
    *,
    proposal_packet: Mapping[str, Any],
    dynamic_state: Mapping[str, Any],
) -> None:
    """Enforce the frozen run contract at the Agent compilation boundary."""

    code = "V32_AGENT_HYPOTHESIS_TTL_POLICY_INVALID"
    try:
        experiment_contract = proposal_packet["support_documents"][
            "experiment_contract"
        ]
        policy = experiment_contract["hypothesis_policy"]
        required_types = policy["required_types"]
        ttl_by_type = policy["ttl_seconds_by_type"]
        state_required_types = dynamic_state["required_hypothesis_types"]
        hypotheses = dynamic_state["hypotheses"]
        as_of = _moment(dynamic_state["as_of"], code)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(code) from exc

    if (
        isinstance(required_types, (str, bytes))
        or not isinstance(required_types, Sequence)
        or not isinstance(ttl_by_type, Mapping)
        or isinstance(state_required_types, (str, bytes))
        or not isinstance(state_required_types, Sequence)
        or isinstance(hypotheses, (str, bytes))
        or not isinstance(hypotheses, Sequence)
        or set(required_types) != set(ttl_by_type)
        or set(required_types) != set(state_required_types)
    ):
        raise V32AgentSemanticCompilerError(code)

    for hypothesis in hypotheses:
        if not isinstance(hypothesis, Mapping):
            raise V32AgentSemanticCompilerError(code)
        ttl_seconds = ttl_by_type.get(hypothesis.get("hypothesis_type"))
        horizon_seconds = hypothesis.get("horizon_seconds")
        status = hypothesis.get("status")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or ttl_seconds <= 0
            or isinstance(horizon_seconds, bool)
            or not isinstance(horizon_seconds, int)
            or horizon_seconds > ttl_seconds
        ):
            raise V32AgentSemanticCompilerError(code)
        try:
            expires_at = _moment(hypothesis.get("expires_at"), code)
        except (TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(code) from exc

        terminal = status in {"FALSIFIED", "EXPIRED"}
        if not terminal and (
            expires_at <= as_of
            or expires_at - as_of > timedelta(seconds=ttl_seconds)
        ):
            raise V32AgentSemanticCompilerError(code)

        # Terminal evidence may remain queryable but cannot borrow renewal
        # evidence (or an extended expiry) to become actionable again.
        previous_expires_at = hypothesis.get("previous_expires_at")
        renewal_refs = hypothesis.get("renewal_evidence_refs")
        if terminal and renewal_refs:
            raise V32AgentSemanticCompilerError(code)
        if terminal and previous_expires_at is not None:
            try:
                previous_expiry = _moment(previous_expires_at, code)
            except (TypeError, ValueError) as exc:
                raise V32AgentSemanticCompilerError(code) from exc
            if expires_at > previous_expiry:
                raise V32AgentSemanticCompilerError(code)


def _derive_objective_reference_risk_inputs(
    *, proposal_packet: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Derive non-Agent risk inputs from qualified contract datums/policy."""

    try:
        experiment = proposal_packet["support_documents"]["experiment_contract"]
        market_view = proposal_packet["support_documents"][
            "agent_market_graph_view"
        ]
        policy = experiment["risk_policy"][
            "objective_reference_risk_input_policy"
        ]
        datums = market_view["current_non_bar_datums"]
        decision_at = _moment(
            proposal_packet["decision_time"],
            "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_TIME_INVALID",
        )
        instrument_id = experiment["instrument"]["instrument_id"]
    except (KeyError, TypeError, ValueError):
        return None
    if (
        isinstance(datums, (str, bytes))
        or not isinstance(datums, Sequence)
        or market_view.get("instrument", {}).get("instrument_id")
        != instrument_id
    ):
        return None
    rows_by_id: dict[str, Mapping[str, Any]] = {}
    for row in datums:
        if not isinstance(row, Mapping):
            return None
        datum_id = row.get("datum_id")
        if not isinstance(datum_id, str) or datum_id in rows_by_id:
            return None
        rows_by_id[datum_id] = row

    specifications = (
        (
            "contract_value",
            policy.get("contract_value_datum_id"),
            policy.get("contract_value_metric_kind"),
            policy.get("contract_value_unit"),
        ),
        (
            "contract_multiplier",
            policy.get("contract_multiplier_datum_id"),
            policy.get("contract_multiplier_metric_kind"),
            policy.get("contract_multiplier_unit"),
        ),
        (
            "price_tick",
            policy.get("price_tick_datum_id"),
            policy.get("price_tick_metric_kind"),
            policy.get("price_tick_unit"),
        ),
        (
            "quantity_step",
            policy.get("quantity_step_datum_id"),
            policy.get("quantity_step_metric_kind"),
            policy.get("quantity_step_unit"),
        ),
        (
            "minimum_quantity",
            policy.get("minimum_quantity_datum_id"),
            policy.get("minimum_quantity_metric_kind"),
            policy.get("minimum_quantity_unit"),
        ),
    )
    values: dict[str, Decimal] = {}
    for name, datum_id, metric_kind, unit in specifications:
        row = rows_by_id.get(datum_id)
        if row is None:
            return None
        try:
            verify_self_digest(row, _PIT_DATUM_DIGEST_FIELD)
            observed_at = _moment(
                row.get("observed_at"),
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_TIME_INVALID",
            )
            available_at = _moment(
                row.get("available_at"),
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_TIME_INVALID",
            )
            value_text = row.get("value")
            value = Decimal(value_text)
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            row.get("schema_id") != _PIT_DATUM_SCHEMA_ID
            or row.get("schema_version") != _PIT_DATUM_SCHEMA_VERSION
            or row.get("instrument_id") != instrument_id
            or row.get("metric_kind") != metric_kind
            or row.get("status") != "OBSERVED"
            or row.get("unit") != unit
            or not isinstance(row.get("raw_binding"), Mapping)
            or row.get("source_component_id") != "INSTRUMENT"
            or row.get("reason_code") is not None
            or row.get("derivation") != "DIRECT_PUBLIC_FIELD"
            or row.get("point_in_time") is not True
            or row.get("missing_is_zero") is not False
            or not isinstance(value_text, str)
            or not value.is_finite()
            or value <= 0
            or canonical_decimal(value) != value_text
            or observed_at > available_at
            or available_at > decision_at
        ):
            return None
        values[name] = value

    if (
        experiment.get("risk_policy", {}).get("mode")
        != "FIXED_ONE_USDT_STRESS_REFERENCE_NO_ACCOUNT_OR_EXECUTION_CLAIM"
        or experiment.get("risk_policy", {}).get("reference_risk_unit")
        != "NON_ACCOUNT_RESEARCH_STRESS_USDT"
        or policy.get("datum_container")
        != "support_documents.agent_market_graph_view.current_non_bar_datums"
        or policy.get("multiplier_reference_derivation")
        != "CONTRACT_VALUE_TIMES_CONTRACT_MULTIPLIER"
        or policy.get("multiplier_reference_unit") != "BTC_PER_CONTRACT"
        or policy.get("reference_scale_quantum_derivation") != "QUANTITY_STEP"
        or policy.get("derived_reference_scale_minimum_policy")
        != "GREATER_THAN_OR_EQUAL_TO_OBSERVED_MINIMUM_QUANTITY"
        or policy.get("derived_reference_scale_unit") != "CONTRACTS"
        or policy.get("price_tick_alignment_fields")
        != [
            "conditional_entry_reference",
            "protective_stop_reference",
            "previous_stop_reference_WHEN_PRESENT",
            "parent_entry_reference_WHEN_PRESENT",
            "minimum_noise_execution_buffer",
            "take_profit_targets[*].reference_price",
        ]
        or policy.get(
            "positive_risk_requires_observed_qualified_contract_specs"
        )
        is not True
        or policy.get("agent_override_forbidden") is not True
        or policy.get("dimensional_scale_policy")
        != (
            "NON_ACCOUNT_RESEARCH_STRESS_USDT_DIVIDED_BY_"
            "USDT_PER_CONTRACT_EQUALS_CONTRACTS"
        )
    ):
        return None
    stress_policy = policy.get("frozen_non_account_research_stress_policy")
    if (
        not isinstance(stress_policy, Mapping)
        or stress_policy.get("policy_label")
        != (
            "FROZEN_NON_ACCOUNT_RESEARCH_STRESS_NOT_ACTUAL_FEE_"
            "OR_FILL_OR_MAX_LOSS"
        )
        or stress_policy.get("stress_reference_unit") != "USDT_PER_CONTRACT"
        or stress_policy.get("conditional_entry_reference_unit")
        != "USDT_PER_BTC"
        or stress_policy.get("notional_per_contract_derivation")
        != "CONTRACT_EXPOSURE_TIMES_CONDITIONAL_ENTRY_REFERENCE"
        or stress_policy.get("stress_reference_derivation")
        != (
            "CONTRACT_EXPOSURE_TIMES_CONDITIONAL_ENTRY_REFERENCE_"
            "TIMES_FROZEN_RATE"
        )
        or stress_policy.get("rate_source_basis")
        != (
            "PREREGISTERED_CONSERVATIVE_NON_ACCOUNT_RESEARCH_"
            "COMPARATOR_ASSUMPTIONS_NOT_ACCOUNT_OR_FILL_CALIBRATION"
        )
        or stress_policy.get("unknown_retention")
        != {
            "actual_account_fee_tier": "UNKNOWN_NOT_ACCESSED",
            "actual_slippage": "UNKNOWN_NOT_OBSERVED",
            "actual_tail_max_loss": "UNKNOWN_NOT_DEFINED",
        }
        or stress_policy.get("future_account_or_execution_adapter_policy")
        != "SEPARATE_AUTHORIZATION_AND_QUALIFICATION_REQUIRED"
    ):
        return None
    rates = stress_policy.get("rates")
    if not isinstance(rates, Mapping) or set(rates) != {
        "fee_stress_reference",
        "slippage_stress_reference",
        "funding_bound_reference",
        "tail_gap_reference",
    }:
        return None
    normalized_rates: dict[str, Decimal] = {}
    for field, value_text in rates.items():
        try:
            value = Decimal(value_text)
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not isinstance(value_text, str)
            or not value.is_finite()
            or value <= 0
            or value >= 1
            or canonical_decimal(value) != value_text
        ):
            return None
        normalized_rates[field] = value
    multiplier = values["contract_value"] * values["contract_multiplier"]
    return {
        "multiplier_reference": canonical_decimal(multiplier),
        "multiplier": multiplier,
        "stress_rates": normalized_rates,
        "price_tick": values["price_tick"],
        "reference_scale_quantum": canonical_decimal(values["quantity_step"]),
        "minimum_quantity": values["minimum_quantity"],
    }


def _validate_objective_reference_risk_input_binding(
    *,
    proposal_packet: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
) -> None:
    positive_tranches: list[Mapping[str, Any]] = []
    try:
        for variant in variants:
            for tranche in variant["dynamic_action_plan"]["risk_tranches"]:
                if Decimal(tranche["reference_risk_budget"]) > 0:
                    positive_tranches.append(tranche)
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_BINDING_INVALID"
        ) from exc
    if not positive_tranches:
        return
    expected = _derive_objective_reference_risk_inputs(
        proposal_packet=proposal_packet
    )
    if expected is None:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE"
        )
    for tranche in positive_tranches:
        try:
            entry = Decimal(tranche["conditional_entry_reference"])
            derived_scale = Decimal(tranche["derived_reference_scale"])
            price_values = [
                Decimal(tranche["conditional_entry_reference"]),
                Decimal(tranche["protective_stop_reference"]),
                Decimal(tranche["minimum_noise_execution_buffer"]),
            ]
            for nullable_field in (
                "previous_stop_reference",
                "parent_entry_reference",
            ):
                if tranche.get(nullable_field) is not None:
                    price_values.append(Decimal(tranche[nullable_field]))
            targets = tranche["take_profit_targets"]
            if isinstance(targets, (str, bytes)) or not isinstance(
                targets, Sequence
            ):
                raise TypeError("take-profit targets must be a sequence")
            price_values.extend(Decimal(row["reference_price"]) for row in targets)
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_BINDING_INVALID"
            ) from exc
        expected_fields = {
            "multiplier_reference": expected["multiplier_reference"],
            "reference_scale_quantum": expected["reference_scale_quantum"],
            **{
                field: canonical_decimal(
                    expected["multiplier"] * entry * rate
                )
                for field, rate in expected["stress_rates"].items()
            },
        }
        if (
            any(
                tranche.get(field) != expected_fields[field]
                for field in _OBJECTIVE_REFERENCE_TRANCHE_FIELDS
            )
            or not entry.is_finite()
            or entry <= 0
            or not derived_scale.is_finite()
            or derived_scale < expected["minimum_quantity"]
            or any(
                not value.is_finite()
                or value <= 0
                or value % expected["price_tick"] != 0
                for value in price_values
            )
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_BINDING_INVALID"
            )


def _packet_owned_unknown_fact_datums(
    *, proposal_packet: Mapping[str, Any]
) -> dict[str, frozenset[str]]:
    """Return exact UNKNOWN PIT datum digests by concrete request owner.

    A broad graph group such as VENUE or OBSERVABLE_FAMILY cannot own a hard
    feasibility decision.  Only a self-validating current datum whose owning
    public request also failed may support ``FACT_INTEGRITY``.
    """

    try:
        view = proposal_packet["support_documents"]["agent_market_graph_view"]
        decision_at = _moment(
            proposal_packet["decision_time"],
            "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID",
        )
        instrument_id = view["instrument"]["instrument_id"]
        datums = view["current_non_bar_datums"]
        claims = view["source_event_claim_ceilings"]
        closures = view["citable_evidence_records"]
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
        ) from exc
    if any(
        isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence)
        for rows in (datums, claims, closures)
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
        )
    claim_by_component: dict[str, Mapping[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            )
        component = claim.get("component_id")
        if not isinstance(component, str) or component in claim_by_component:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            )
        claim_by_component[component] = claim
    closure_by_digest: dict[str, Mapping[str, Any]] = {}
    for closure in closures:
        if not isinstance(closure, Mapping):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            )
        digest = closure.get("evidence_digest")
        if not isinstance(digest, str) or digest in closure_by_digest:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            )
        closure_by_digest[digest] = closure

    owned: dict[str, set[str]] = {}
    for datum in datums:
        if not isinstance(datum, Mapping) or datum.get("status") != "UNKNOWN":
            continue
        try:
            datum_digest = verify_self_digest(datum, _PIT_DATUM_DIGEST_FIELD)
            available_at = _moment(
                datum.get("available_at"),
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID",
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            ) from exc
        component = datum.get("source_component_id")
        request_group = f"REQUEST:{component}"
        claim = claim_by_component.get(component) if isinstance(component, str) else None
        closure = closure_by_digest.get(datum_digest)
        dependency_groups = datum.get("dependency_group_ids")
        closure_groups = None if closure is None else closure.get("dependency_group_ids")
        if (
            datum.get("schema_id") != _PIT_DATUM_SCHEMA_ID
            or datum.get("schema_version") != _PIT_DATUM_SCHEMA_VERSION
            or datum.get("instrument_id") != instrument_id
            or not isinstance(component, str)
            or not component
            or datum.get("source_event_id")
            != f"okx-public-request:{component.lower()}"
            or datum.get("value") is not None
            or datum.get("unit") is not None
            or datum.get("observed_at") is not None
            or datum.get("provider_observed_at") is not None
            or datum.get("effective_at") is not None
            or datum.get("provider_clock_ahead_milliseconds") is not None
            or datum.get("clock_uncertainty_status") != "UNKNOWN"
            or datum.get("raw_binding") is not None
            or not isinstance(datum.get("reason_code"), str)
            or not datum["reason_code"]
            or datum.get("derivation") != "NOT_DERIVED_SOURCE_UNKNOWN"
            or datum.get("point_in_time") is not True
            or datum.get("missing_is_zero") is not False
            or available_at > decision_at
            or not isinstance(dependency_groups, list)
            or request_group not in dependency_groups
            or claim is None
            or claim.get("status") != "UNKNOWN"
            or closure is None
            or closure.get("closure_status")
            != "VERIFIED_COMPLETE_GRAPH_CLOSURE"
            or not isinstance(closure_groups, list)
            or request_group not in closure_groups
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_FACT_INTEGRITY_OWNER_INVALID"
            )
        owned.setdefault(request_group, set()).add(datum_digest)
    return {key: frozenset(value) for key, value in owned.items()}


def _candidate_actual_pit_evidence_refs(
    *, dynamic_state: Mapping[str, Any], candidate: Mapping[str, Any]
) -> frozenset[str]:
    hypothesis_by_id = {
        row["hypothesis_id"]: row for row in dynamic_state["hypotheses"]
    }
    zone_by_id = {row["zone_id"]: row for row in dynamic_state["zones"]}
    refs: set[str] = set()
    for hypothesis_id in candidate["hypothesis_ids"]:
        hypothesis = hypothesis_by_id[hypothesis_id]
        for field in (
            "source_refs",
            "supporting_refs",
            "opposing_refs",
            "tier_update_refs",
            "renewal_evidence_refs",
        ):
            refs.update(hypothesis[field])
    for zone_id in candidate["zone_ids"]:
        zone = zone_by_id[zone_id]
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
            refs.update(zone[field])
    return frozenset(refs)


def _current_citable_evidence_availability(
    *, proposal_packet: Mapping[str, Any]
) -> dict[str, datetime]:
    """Return the current sealed evidence-digest availability clock.

    Freshness is a property of when the system first had the evidence, not of
    whether an Agent happened to cite it in the predecessor state.  The market
    graph view is already bound to the verified PIT availability registry by
    the proposal-packet verifier; this helper retains only exact evidence
    digests and their sealed availability times.
    """

    try:
        decision_at = _moment(
            proposal_packet["decision_time"],
            "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID",
        )
        records = proposal_packet["support_documents"][
            "agent_market_graph_view"
        ]["citable_evidence_records"]
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID"
        ) from exc
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID"
        )
    result: dict[str, datetime] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID"
            )
        evidence_digest = record.get("evidence_digest")
        try:
            available_at = _moment(
                record.get("available_at"),
                "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID",
            )
        except (TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID"
            ) from exc
        if (
            not isinstance(evidence_digest, str)
            or _HEX_64.fullmatch(evidence_digest) is None
            or evidence_digest in result
            or available_at > decision_at
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID"
            )
        result[evidence_digest] = available_at
    return result


def _candidate_new_risk_support_refs(
    *, dynamic_state: Mapping[str, Any], candidate: Mapping[str, Any]
) -> frozenset[str]:
    """Return positive/fresh refs that may authorize more directional risk.

    Only the hypothesis field explicitly typed as supporting the thesis may
    authorize ADD/REENTER/REVERSE.  Source provenance, counter-evidence, tier
    update evidence, renewal evidence, and untyped zone observations may alter
    research state, but cannot be relabelled as positive action evidence.
    """

    hypothesis_by_id = {
        row["hypothesis_id"]: row for row in dynamic_state["hypotheses"]
    }
    refs: set[str] = set()
    for hypothesis_id in candidate["hypothesis_ids"]:
        hypothesis = hypothesis_by_id[hypothesis_id]
        refs.update(hypothesis["supporting_refs"])
    return frozenset(refs)


def _validate_candidate_new_evidence_binding(
    *,
    proposal_packet: Mapping[str, Any],
    dynamic_state: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
) -> None:
    """Bind add/reentry/reverse evidence to actual fresh sealed PIT refs."""

    if not variants:
        return
    plan = variants[0]["dynamic_action_plan"]
    current_availability = _current_citable_evidence_availability(
        proposal_packet=proposal_packet
    )
    previous_state = proposal_packet.get("previous_dynamic_research_state")
    freshness_cutoff = (
        None
        if previous_state is None
        else _moment(
            previous_state.get("as_of"),
            "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID",
        )
    )
    current_state_as_of = _moment(
        dynamic_state.get("as_of"),
        "V32_AGENT_NEW_EVIDENCE_AVAILABILITY_INVALID",
    )
    for candidate in plan["candidates"]:
        if candidate["action_kind"] not in {"ADD", "REENTER", "REVERSE"}:
            continue
        actual_refs = _candidate_new_risk_support_refs(
            dynamic_state=dynamic_state, candidate=candidate
        )
        fresh_refs = {
            ref
            for ref in actual_refs
            if ref in current_availability
            and current_availability[ref] <= current_state_as_of
            and (
                freshness_cutoff is None
                or current_availability[ref] > freshness_cutoff
            )
        }
        supplied = set(candidate["new_evidence_refs"])
        if candidate["feasibility"] == "ELIGIBLE":
            if not supplied or not supplied.issubset(fresh_refs):
                raise V32AgentSemanticCompilerError(
                    "V32_AGENT_NEW_EVIDENCE_BINDING_INVALID"
                )
        elif candidate["block_reason"] == "NO_NEW_EVIDENCE":
            if (
                supplied
                or fresh_refs
                or candidate["blocking_evidence_refs"]
                != [NO_NEW_CURRENT_PIT_EVIDENCE_REF]
            ):
                raise V32AgentSemanticCompilerError(
                    "V32_AGENT_NEW_EVIDENCE_BINDING_INVALID"
                )


def _validate_packet_owned_fact_and_max_loss_blocks(
    *,
    proposal_packet: Mapping[str, Any],
    dynamic_state: Mapping[str, Any],
    candidate: Mapping[str, Any],
    error_code: str,
) -> bool:
    """Validate the two hard gates that the pure Domain cannot own alone."""

    reason = candidate["block_reason"]
    if reason == "MAX_LOSS":
        # In the current public/local/non-executable pilot, unbounded venue
        # loss is already an instrument-wide future-execution gate.  There is
        # no position or venue receipt that could justify deleting one
        # research direction.
        raise V32AgentSemanticCompilerError(error_code)
    if reason != "FACT_INTEGRITY":
        return False

    owned = _packet_owned_unknown_fact_datums(proposal_packet=proposal_packet)
    unknown_by_id = {
        row["unknown_id"]: row for row in dynamic_state["unknowns"]
    }
    actual_evidence_refs = _candidate_actual_pit_evidence_refs(
        dynamic_state=dynamic_state, candidate=candidate
    )

    for unknown_id in candidate["blocking_unknown_ids"]:
        unknown = unknown_by_id.get(unknown_id)
        if (
            unknown is None
            or unknown.get("unknown_type") != "UNKNOWN_FACT_INTEGRITY"
            or not unknown.get("dependency_refs")
            or any(
                not isinstance(ref, str)
                or not ref.startswith("REQUEST:")
                or ref not in owned
                or not actual_evidence_refs.intersection(owned[ref])
                for ref in unknown["dependency_refs"]
            )
        ):
            raise V32AgentSemanticCompilerError(error_code)
    return True


def _validate_zero_eligible_risk_causes(
    *,
    proposal_packet: Mapping[str, Any],
    dynamic_state: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
) -> None:
    """Reject Agent-authored soft blockers masquerading as objective zero risk.

    A zero-candidate WAIT is lawful only when the owning Domain can derive the
    hard gate, or when this compiler independently proves that the frozen
    objective reference inputs are unavailable.  Cost, geometry, and generic
    prose refs cannot be used to erase otherwise comparable directional
    candidates.
    """

    risk_rows = [
        row
        for row in evaluation["candidate_rows"]
        if row["action_kind"] in RISK_INCREASING_ACTIONS
    ]
    if not risk_rows:
        return
    zero_eligible = not any(
        row["feasibility"] == "ELIGIBLE" for row in risk_rows
    )
    blocked_rows = [
        row for row in risk_rows if row["feasibility"] == "BLOCKED"
    ]
    if not blocked_rows:
        return
    error_code = (
        "V32_AGENT_ZERO_ELIGIBLE_RISK_CAUSE_INVALID"
        if zero_eligible
        else "V32_AGENT_RISK_BLOCK_CAUSE_INVALID"
    )
    if not variants:
        raise V32AgentSemanticCompilerError(error_code)
    regime = dynamic_state["market_regime_state"]["regime"]
    regime_is_nondirectional = (
        regime in CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES
    )

    objective_inputs_unavailable = (
        _derive_objective_reference_risk_inputs(
            proposal_packet=proposal_packet
        )
        is None
    )
    plan = variants[0]["dynamic_action_plan"]
    plan_candidates = {
        row["candidate_id"]: row
        for row in plan["candidates"]
    }
    reentry_budget = plan["reentry_budget_state"]
    for row in blocked_rows:
        candidate = plan_candidates.get(row["candidate_id"])
        if candidate is None or candidate["feasibility"] != "BLOCKED":
            raise V32AgentSemanticCompilerError(error_code)
        reason = candidate["block_reason"]
        if _validate_packet_owned_fact_and_max_loss_blocks(
            proposal_packet=proposal_packet,
            dynamic_state=dynamic_state,
            candidate=candidate,
            error_code=error_code,
        ):
            continue
        if reason == "MARKET_REGIME_NON_DIRECTIONAL" and regime_is_nondirectional:
            # The Domain verifier has already required the exact sealed regime
            # evidence on this candidate.  Other claimed hard gates must still
            # be validated even when the regime independently forces zero risk.
            continue
        if reason == "NO_NEW_EVIDENCE":
            # The packet-relative freshness proof was reconstructed for every
            # plan candidate before this owning-cause pass.
            continue
        if reason in _DOMAIN_DERIVED_ZERO_RISK_BLOCK_REASONS:
            # These causes and their evidence bindings are reconstructed by
            # verify_v32_dynamic_action_plan_v1 from the sealed state.  The
            # risk-quantum reason additionally requires the Domain-derived
            # residual cap to be zero and exact hypothesis source refs.
            continue
        if (
            reason == "REENTRY_COOLDOWN_OR_BUDGET"
            and candidate["action_kind"] in INSTRUMENT_CHURN_ACTION_KINDS
            and reentry_budget["status"] in {"COOLDOWN", "EXHAUSTED"}
            and bool(reentry_budget["failure_evidence_refs"])
            and candidate["blocking_evidence_refs"]
            == reentry_budget["failure_evidence_refs"]
        ):
            # The Domain verifier binds this exact action to the durable,
            # exhausted instrument-wide reentry ledger and failure refs.
            continue
        if (
            reason == "COST_OR_LIQUIDITY"
            and objective_inputs_unavailable
            and candidate["blocking_evidence_refs"]
            == [OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE_REF]
        ):
            continue
        raise V32AgentSemanticCompilerError(error_code)


def _verify_stage_chain(
    *,
    expected_stage: str,
    agent_input_context: Mapping[str, Any],
    agent_delivery: Mapping[str, Any],
    agent_consumption: Mapping[str, Any],
    lossless_context_package: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    try:
        context_digest = verify_v32_agent_input_context_v1(
            agent_input_context,
            lossless_context_package=lossless_context_package,
        )
        delivery_digest = verify_v32_agent_delivery_v1(
            agent_delivery, agent_input_context=agent_input_context
        )
        consumption_digest = verify_v32_agent_consumption_v1(
            agent_consumption,
            agent_input_context=agent_input_context,
            agent_delivery=agent_delivery,
        )
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SEMANTIC_STAGE_CHAIN_INVALID"
        ) from exc
    if (
        agent_input_context.get("agent_stage") != expected_stage
        or agent_delivery.get("agent_stage") != expected_stage
        or agent_consumption.get("agent_stage") != expected_stage
    ):
        raise V32AgentSemanticCompilerError("V32_AGENT_SEMANTIC_STAGE_INVALID")
    return context_digest, delivery_digest, consumption_digest


def _strict_delivery_object(agent_delivery: Mapping[str, Any]) -> dict[str, Any]:
    raw_text = agent_delivery.get("payload_utf8")
    if not isinstance(raw_text, str):
        raise V32AgentSemanticCompilerError("V32_AGENT_SEMANTIC_PAYLOAD_INVALID")
    try:
        raw_bytes = raw_text.encode("utf-8", errors="strict")
        document = loads_json_strict(raw_bytes)
        canonical = canonical_bytes(document)
    except (CanonicalContractError, UnicodeError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SEMANTIC_PAYLOAD_INVALID"
        ) from exc
    if canonical != raw_bytes:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SEMANTIC_PAYLOAD_NOT_CANONICAL"
        )
    return document


def canonical_v32_agent_semantic_json_v1(document: Mapping[str, Any]) -> str:
    """Render one already-built semantic document as exact canonical UTF-8."""

    try:
        return canonical_bytes(document).decode("utf-8", errors="strict")
    except (CanonicalContractError, UnicodeError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SEMANTIC_CANONICAL_ENCODING_INVALID"
        ) from exc


def _validate_evaluation_plan_binding(
    *, evaluation: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    plan_candidates = {row["candidate_id"]: row for row in plan["candidates"]}
    evaluation_rows = {
        row["candidate_id"]: row for row in evaluation["candidate_rows"]
    }
    if set(plan_candidates) != set(evaluation_rows):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_CANDIDATE_COVERAGE_INVALID"
        )
    try:
        risk = evaluation["risk_arithmetic"]
        subjective_tier_by_cap = {
            0: "EXTREME_UNCERTAINTY",
            50: "LOW",
            100: "HIGH",
        }
        if (
            Decimal(str(risk["reference_risk_upper_bound"]))
            != Decimal(str(plan["reference_risk_unit_budget"]))
            or risk["subjective_plausibility_tier"]
            != subjective_tier_by_cap[plan["subjective_tier_cap_units"]]
            or risk["residual_uncertainty_tier"]
            != plan["residual_uncertainty_tier"]
            or plan["residual_uncertainty_cap_units"]
            != 100
            - SUBJECTIVE_TIER_RISK_CAP_UNITS[
                risk["residual_uncertainty_tier"]
            ]
            or Decimal(str(plan["pre_modifier_reference_risk_budget"]))
            > Decimal(str(risk["agent_reference_risk_ceiling"]))
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_RISK_ARITHMETIC_BINDING_INVALID"
            )
        allocations = {
            row["cluster_id"]: Decimal(row["reference_risk"])
            for row in plan["cluster_risk_allocations"]
        }
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentSemanticCompilerError):
            raise
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_RISK_ARITHMETIC_BINDING_INVALID"
        ) from exc

    for candidate_id, candidate in plan_candidates.items():
        row = evaluation_rows[candidate_id]
        expected_reasons = (
            ["NONE"]
            if candidate["feasibility"] == "ELIGIBLE"
            else [candidate["block_reason"]]
        )
        expected_evidence = sorted(
            set(candidate["cluster_ids"])
            | set(candidate["hypothesis_ids"])
            | set(candidate["zone_ids"])
        )
        expected_reference_risk = (
            sum(
                (
                    allocations.get(cluster_id, Decimal("0"))
                    for cluster_id in candidate["cluster_ids"]
                ),
                Decimal("0"),
            )
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS
            and candidate["feasibility"] == "ELIGIBLE"
            else Decimal("0")
        )
        try:
            row_reference_risk = Decimal(row["risk_reference_units"])
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_RISK_ARITHMETIC_BINDING_INVALID"
            ) from exc
        if (
            row["action_kind"] != candidate["action_kind"]
            or row["direction"] != candidate["direction"]
            or row["feasibility"] != candidate["feasibility"]
            or row["block_reasons"] != expected_reasons
            or row["evidence_refs"] != expected_evidence
            or row_reference_risk != expected_reference_risk
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_CANDIDATE_BINDING_INVALID"
            )
    selected_row = evaluation_rows[plan["selected_candidate_id"]]
    if Decimal(plan["selected_candidate_reference_risk_budget"]) != Decimal(
        selected_row["risk_reference_units"]
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_RISK_ARITHMETIC_BINDING_INVALID"
        )


def _variant_id(candidate_id: str) -> str:
    return f"variant::{candidate_id}"


def _normalize_variants(
    *,
    variants: Sequence[Mapping[str, Any]],
    dynamic_state: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(variants, (str, bytes)) or not isinstance(variants, Sequence):
        raise V32AgentSemanticCompilerError("V32_AGENT_PLAN_VARIANTS_INVALID")
    eligible_ids = sorted(
        row["candidate_id"]
        for row in evaluation["candidate_rows"]
        if row["feasibility"] == "ELIGIBLE"
    )
    candidate_order = [row["candidate_id"] for row in evaluation["candidate_rows"]]
    normalized: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for item in variants:
        if not isinstance(item, Mapping) or set(item) != _VARIANT_FIELDS:
            raise V32AgentSemanticCompilerError("V32_AGENT_PLAN_VARIANT_INVALID")
        candidate_id = _text(
            item.get("candidate_id"), "V32_AGENT_PLAN_VARIANT_INVALID"
        )
        plan = item.get("dynamic_action_plan")
        if not isinstance(plan, Mapping):
            raise V32AgentSemanticCompilerError("V32_AGENT_PLAN_VARIANT_INVALID")
        try:
            plan_digest = verify_v32_dynamic_action_plan_v1(
                plan, dynamic_research_state=dynamic_state
            )
        except (V32DynamicActionPlanError, KeyError, TypeError, ValueError) as exc:
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_PLAN_VARIANT_INVALID"
            ) from exc
        if (
            item.get("variant_id") != _variant_id(candidate_id)
            or item.get("dynamic_action_plan_digest") != plan_digest
            or plan.get("selected_candidate_id") != candidate_id
            or plan.get("alternative_candidate_rank")
            != [row for row in candidate_order if row != candidate_id]
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_PLAN_VARIANT_SELECTION_INVALID"
            )
        normalized.append(
            {
                "variant_id": _variant_id(candidate_id),
                "candidate_id": candidate_id,
                "dynamic_action_plan": dict(plan),
                "dynamic_action_plan_digest": plan_digest,
            }
        )
        plans.append(dict(plan))
    normalized.sort(key=lambda row: row["candidate_id"])
    if (
        [row["candidate_id"] for row in normalized] != eligible_ids
        or len({row["variant_id"] for row in normalized}) != len(normalized)
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PLAN_VARIANT_COVERAGE_INVALID"
        )

    baseline = plans[0]
    baseline_fixed = {
        key: value
        for key, value in baseline.items()
        if key not in _VARIANT_ALLOWED_DIFFERENCES
    }
    baseline_wait = {
        key: value
        for key, value in baseline["wait_assessment"].items()
        if key != "dominance_comparisons"
    }
    candidate_actions = {
        row["candidate_id"]: row["action_kind"]
        for row in evaluation["candidate_rows"]
    }
    for plan in plans:
        fixed = {
            key: value
            for key, value in plan.items()
            if key not in _VARIANT_ALLOWED_DIFFERENCES
        }
        wait_fixed = {
            key: value
            for key, value in plan["wait_assessment"].items()
            if key != "dominance_comparisons"
        }
        comparisons = plan["wait_assessment"]["dominance_comparisons"]
        selected_is_wait = candidate_actions[plan["selected_candidate_id"]] == "WAIT"
        if (
            fixed != baseline_fixed
            or wait_fixed != baseline_wait
            or (not selected_is_wait and comparisons)
        ):
            raise V32AgentSemanticCompilerError(
                "V32_AGENT_PLAN_VARIANT_MATERIAL_DRIFT"
            )
        _validate_evaluation_plan_binding(evaluation=evaluation, plan=plan)
    return normalized


def _provisional_evaluation(
    *,
    proposal_input_context: Mapping[str, Any],
    dynamic_state: Mapping[str, Any],
    reference_context: str,
    risk_arithmetic: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        return build_v32_action_evaluation_v1(
            run_id=proposal_input_context["run_id"],
            cycle_index=proposal_input_context["cycle_index"],
            evaluated_at=proposal_input_context["created_at"],
            proposal_consumption_digest=_DUMMY_CONSUMPTION_DIGEST,
            compiled_dynamic_state_digest=dynamic_state[DYNAMIC_STATE_DIGEST_FIELD],
            reference_context=reference_context,
            risk_arithmetic=risk_arithmetic,
            candidate_rows=candidate_rows,
        )
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PRESELECTION_MATERIAL_INVALID"
        ) from exc


def build_v32_proposal_semantic_output_v1(
    *,
    proposal_input_context: Mapping[str, Any],
    current_dynamic_research_state: Mapping[str, Any],
    reference_context: str,
    risk_arithmetic: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
    sealed_plan_variants: Sequence[Mapping[str, Any]],
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the exact JSON object the Proposal Agent must deliver."""

    try:
        context_digest = verify_v32_agent_input_context_v1(
            proposal_input_context,
            lossless_context_package=proposal_lossless_context_package,
        )
        dynamic_digest = verify_v32_dynamic_research_state_v1(
            current_dynamic_research_state
        )
    except (V32AgentLifecycleError, V32DynamicResearchError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_SEMANTIC_INPUT_INVALID"
        ) from exc
    try:
        packet = resolve_v32_agent_canonical_packet_v1(
            proposal_input_context,
            lossless_context_package=proposal_lossless_context_package,
        )
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_SEMANTIC_INPUT_INVALID"
        ) from exc
    if (
        proposal_input_context.get("agent_stage") != "PROPOSAL"
        or not isinstance(packet, Mapping)
        or current_dynamic_research_state.get("run_id")
        != proposal_input_context.get("run_id")
        or current_dynamic_research_state.get("cycle_index")
        != proposal_input_context.get("cycle_index")
        or _moment(
            current_dynamic_research_state.get("as_of"),
            "V32_AGENT_PROPOSAL_SEMANTIC_CROSS_BINDING_INVALID",
        )
        > _moment(
            packet.get("decision_time"),
            "V32_AGENT_PROPOSAL_SEMANTIC_CROSS_BINDING_INVALID",
        )
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_SEMANTIC_CROSS_BINDING_INVALID"
        )
    _validate_contract_hypothesis_ttl(
        proposal_packet=packet,
        dynamic_state=current_dynamic_research_state,
    )
    evaluation = _provisional_evaluation(
        proposal_input_context=proposal_input_context,
        dynamic_state=current_dynamic_research_state,
        reference_context=reference_context,
        risk_arithmetic=risk_arithmetic,
        candidate_rows=candidate_rows,
    )
    variants = _normalize_variants(
        variants=sealed_plan_variants,
        dynamic_state=current_dynamic_research_state,
        evaluation=evaluation,
    )
    _validate_candidate_new_evidence_binding(
        proposal_packet=packet,
        dynamic_state=current_dynamic_research_state,
        variants=variants,
    )
    _validate_zero_eligible_risk_causes(
        proposal_packet=packet,
        dynamic_state=current_dynamic_research_state,
        evaluation=evaluation,
        variants=variants,
    )
    _validate_objective_reference_risk_input_binding(
        proposal_packet=packet,
        variants=variants,
    )
    eligible_ids = sorted(
        row["candidate_id"]
        for row in evaluation["candidate_rows"]
        if row["feasibility"] == "ELIGIBLE"
    )
    material = {
        "reference_context": evaluation["reference_context"],
        "risk_arithmetic": evaluation["risk_arithmetic"],
        "risk_arithmetic_digest": evaluation["risk_arithmetic_digest"],
        "candidate_rows": evaluation["candidate_rows"],
        "candidate_rows_digest": evaluation["candidate_rows_digest"],
    }
    document = {
        "schema_id": PROPOSAL_SEMANTIC_OUTPUT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": proposal_input_context["run_id"],
        "cycle_index": _cycle(proposal_input_context["cycle_index"]),
        "agent_stage": "PROPOSAL",
        "proposal_input_context_digest": context_digest,
        "proposal_canonical_packet_digest": packet[PROPOSAL_PACKET_DIGEST_FIELD],
        "current_dynamic_research_state": dict(current_dynamic_research_state),
        "current_dynamic_research_state_digest": dynamic_digest,
        "preselection_candidate_material": material,
        "sealed_plan_variants": variants,
        "eligible_candidate_ids": eligible_ids,
        "selection_present": False,
        "source_scope": _SOURCE_SCOPE,
        "external_execution_authority": _AUTHORITY,
        "executable": False,
        "claim": _CLAIM,
    }
    return self_digest(document, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD)


def verify_v32_proposal_semantic_output_v1(
    document: Mapping[str, Any],
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _PROPOSAL_OUTPUT_FIELDS:
        raise V32AgentSemanticCompilerError("V32_AGENT_PROPOSAL_OUTPUT_INVALID")
    material = document.get("preselection_candidate_material")
    if not isinstance(material, Mapping) or set(material) != _PRESELECTION_FIELDS:
        raise V32AgentSemanticCompilerError("V32_AGENT_PROPOSAL_OUTPUT_INVALID")
    try:
        supplied = verify_self_digest(
            document, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD
        )
        rebuilt = build_v32_proposal_semantic_output_v1(
            proposal_input_context=proposal_input_context,
            current_dynamic_research_state=document[
                "current_dynamic_research_state"
            ],
            reference_context=material["reference_context"],
            risk_arithmetic=material["risk_arithmetic"],
            candidate_rows=material["candidate_rows"],
            sealed_plan_variants=document["sealed_plan_variants"],
            proposal_lossless_context_package=proposal_lossless_context_package,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentSemanticCompilerError):
            raise
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_OUTPUT_INVALID"
        ) from exc
    _boundary(document, "V32_AGENT_PROPOSAL_OUTPUT_BOUNDARY_INVALID")
    if (
        document.get("selection_present") is not False
        or dict(document) != rebuilt
        or supplied != rebuilt[PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD]
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_OUTPUT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def compile_v32_proposal_delivery_v1(
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consumption: Mapping[str, Any],
    compiled_at: str,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Consume one terminal Proposal delivery and seal its action evaluation."""

    context_digest, delivery_digest, consumption_digest = _verify_stage_chain(
        expected_stage="PROPOSAL",
        agent_input_context=proposal_input_context,
        agent_delivery=proposal_delivery,
        agent_consumption=proposal_consumption,
        lossless_context_package=proposal_lossless_context_package,
    )
    compiled = _time(compiled_at, "V32_AGENT_PROPOSAL_COMPILE_TIME_INVALID")
    if _moment(compiled, "V32_AGENT_PROPOSAL_COMPILE_TIME_INVALID") < _moment(
        proposal_consumption["consumed_at"],
        "V32_AGENT_PROPOSAL_COMPILE_TIME_INVALID",
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_COMPILE_TIME_INVALID"
        )
    output = _strict_delivery_object(proposal_delivery)
    output_digest = verify_v32_proposal_semantic_output_v1(
        output,
        proposal_input_context=proposal_input_context,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    state = output["current_dynamic_research_state"]
    state_digest = output["current_dynamic_research_state_digest"]
    material = output["preselection_candidate_material"]
    try:
        evaluation = build_v32_action_evaluation_v1(
            run_id=proposal_input_context["run_id"],
            cycle_index=proposal_input_context["cycle_index"],
            evaluated_at=compiled,
            proposal_consumption_digest=consumption_digest,
            compiled_dynamic_state_digest=state_digest,
            reference_context=material["reference_context"],
            risk_arithmetic=material["risk_arithmetic"],
            candidate_rows=material["candidate_rows"],
        )
        evaluation_digest = verify_v32_action_evaluation_v1(evaluation)
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_ACTION_EVALUATION_COMPILE_INVALID"
        ) from exc
    variants = _normalize_variants(
        variants=output["sealed_plan_variants"],
        dynamic_state=state,
        evaluation=evaluation,
    )
    document = {
        "schema_id": PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": proposal_input_context["run_id"],
        "cycle_index": proposal_input_context["cycle_index"],
        "compiled_at": compiled,
        "proposal_input_context_digest": context_digest,
        "proposal_delivery_digest": delivery_digest,
        "proposal_consumption_digest": consumption_digest,
        "proposal_payload_sha256": proposal_delivery["payload_sha256"],
        "proposal_semantic_output_digest": output_digest,
        "compiled_dynamic_research_state": dict(state),
        "compiled_dynamic_research_state_digest": state_digest,
        "sealed_action_evaluation": evaluation,
        "sealed_action_evaluation_digest": evaluation_digest,
        "sealed_plan_variants": variants,
        "eligible_candidate_ids": list(output["eligible_candidate_ids"]),
        "compile_status": "PROPOSAL_TERMINAL_CONSUMED_AND_SEMANTICS_SEALED",
        "source_scope": _SOURCE_SCOPE,
        "external_execution_authority": _AUTHORITY,
        "executable": False,
        "claim": _CLAIM,
    }
    return self_digest(document, PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD)


def verify_v32_proposal_semantic_compile_receipt_v1(
    document: Mapping[str, Any],
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consumption: Mapping[str, Any],
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _PROPOSAL_RECEIPT_FIELDS:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_COMPILE_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD
        )
        rebuilt = compile_v32_proposal_delivery_v1(
            proposal_input_context=proposal_input_context,
            proposal_delivery=proposal_delivery,
            proposal_consumption=proposal_consumption,
            compiled_at=document["compiled_at"],
            proposal_lossless_context_package=proposal_lossless_context_package,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentSemanticCompilerError):
            raise
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_COMPILE_RECEIPT_INVALID"
        ) from exc
    _boundary(document, "V32_AGENT_PROPOSAL_COMPILE_BOUNDARY_INVALID")
    if dict(document) != rebuilt or supplied != rebuilt[
        PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD
    ]:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_PROPOSAL_COMPILE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _proposal_output_from_selection_packet(
    selection_packet: Mapping[str, Any],
    *,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    proposal_delivery = selection_packet.get("proposal_delivery")
    if not isinstance(proposal_delivery, Mapping):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PROPOSAL_PAYLOAD_INVALID"
        )
    output = _strict_delivery_object(proposal_delivery)
    proposal_context = selection_packet.get("proposal_input_context")
    if not isinstance(proposal_context, Mapping):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PROPOSAL_PAYLOAD_INVALID"
        )
    verify_v32_proposal_semantic_output_v1(
        output,
        proposal_input_context=proposal_context,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    return output


def _validate_selection_packet_material(
    *, selection_packet: Mapping[str, Any], proposal_output: Mapping[str, Any]
) -> None:
    state = selection_packet["compiled_dynamic_research_state"]
    evaluation = selection_packet["sealed_action_evaluation"]
    material = proposal_output["preselection_candidate_material"]
    if (
        state != proposal_output["current_dynamic_research_state"]
        or evaluation["compiled_dynamic_state_digest"]
        != proposal_output["current_dynamic_research_state_digest"]
        or evaluation["reference_context"] != material["reference_context"]
        or evaluation["risk_arithmetic"] != material["risk_arithmetic"]
        or evaluation["risk_arithmetic_digest"]
        != material["risk_arithmetic_digest"]
        or evaluation["candidate_rows"] != material["candidate_rows"]
        or evaluation["candidate_rows_digest"] != material["candidate_rows_digest"]
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PACKET_MATERIAL_DRIFT"
        )
    _normalize_variants(
        variants=proposal_output["sealed_plan_variants"],
        dynamic_state=state,
        evaluation=evaluation,
    )


def _selection_reason(
    *,
    candidate_id: str,
    proposal_output: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> tuple[str, list[str]]:
    row = next(
        (item for item in evaluation["candidate_rows"] if item["candidate_id"] == candidate_id),
        None,
    )
    if row is None or row["feasibility"] != "ELIGIBLE":
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_CANDIDATE_NOT_ELIGIBLE"
        )
    variant = next(
        (
            item
            for item in proposal_output["sealed_plan_variants"]
            if item["candidate_id"] == candidate_id
        ),
        None,
    )
    if variant is None:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_VARIANT_MISSING"
        )
    action = row["action_kind"]
    refs = set(row["evidence_refs"])
    if action == "WAIT":
        plan = variant["dynamic_action_plan"]
        comparisons = plan["wait_assessment"]["dominance_comparisons"]
        eligible_risk_rows = [
            candidate
            for candidate in evaluation["candidate_rows"]
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS
            and candidate["feasibility"] == "ELIGIBLE"
        ]
        for comparison in comparisons:
            refs.update(comparison["evidence_refs"])
        if eligible_risk_rows:
            code = "WAIT_DOMINANCE_PROVEN_BY_SEALED_VARIANT"
        else:
            if comparisons:
                raise V32AgentSemanticCompilerError(
                    "V32_AGENT_SELECTION_WAIT_ZERO_RISK_COMPARISON_INVALID"
                )
            code = "WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION"
            for candidate in evaluation["candidate_rows"]:
                if (
                    candidate["action_kind"] in RISK_INCREASING_ACTIONS
                    and candidate["feasibility"] == "BLOCKED"
                ):
                    refs.update(candidate["evidence_refs"])
            for candidate in plan["candidates"]:
                if (
                    candidate["action_kind"] in RISK_INCREASING_ACTIONS
                    and candidate["feasibility"] == "BLOCKED"
                ):
                    refs.update(candidate["blocking_evidence_refs"])
            regime = proposal_output["current_dynamic_research_state"][
                "market_regime_state"
            ]
            for field in (
                "evidence_refs",
                "counter_evidence_refs",
                "transition_evidence_refs",
            ):
                refs.update(regime[field])
    elif action == "HOLD":
        code = "HOLD_CONTINUITY_PROVEN_BY_SEALED_VARIANT"
    else:
        code = "CANDIDATE_DOMINANCE_PROVEN_BY_SEALED_VARIANT"
    normalized_refs = sorted(refs)
    if not normalized_refs:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_REASON_REFS_EMPTY"
        )
    return code, normalized_refs


def build_v32_selection_semantic_output_v1(
    *,
    selection_input_context: Mapping[str, Any],
    selected_candidate_id: str,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the only admissible Selection Agent response object."""

    try:
        context_digest = verify_v32_agent_input_context_v1(
            selection_input_context,
            lossless_context_package=selection_lossless_context_package,
        )
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_SEMANTIC_INPUT_INVALID"
        ) from exc
    if selection_input_context.get("agent_stage") != "SELECTION":
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_SEMANTIC_STAGE_INVALID"
        )
    try:
        packet = resolve_v32_agent_canonical_packet_v1(
            selection_input_context,
            lossless_context_package=selection_lossless_context_package,
        )
        packet_digest = verify_v32_selection_canonical_packet_v1(packet)
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PACKET_INVALID"
        ) from exc
    proposal_output = _proposal_output_from_selection_packet(
        packet,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    _validate_selection_packet_material(
        selection_packet=packet, proposal_output=proposal_output
    )
    candidate_id = _text(
        selected_candidate_id, "V32_AGENT_SELECTION_CANDIDATE_INVALID"
    )
    reason_code, reason_refs = _selection_reason(
        candidate_id=candidate_id,
        proposal_output=proposal_output,
        evaluation=packet["sealed_action_evaluation"],
    )
    document = {
        "schema_id": SELECTION_SEMANTIC_OUTPUT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": selection_input_context["run_id"],
        "cycle_index": _cycle(selection_input_context["cycle_index"]),
        "agent_stage": "SELECTION",
        "selection_input_context_digest": context_digest,
        "selection_canonical_packet_digest": packet_digest,
        "proposal_semantic_output_digest": proposal_output[
            PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD
        ],
        "sealed_action_evaluation_digest": packet["sealed_action_evaluation"][
            ACTION_EVALUATION_DIGEST_FIELD
        ],
        "selected_variant_id": _variant_id(candidate_id),
        "selected_candidate_id": candidate_id,
        "selection_reason_code": reason_code,
        "selection_reason_refs": reason_refs,
        "source_scope": _SOURCE_SCOPE,
        "external_execution_authority": _AUTHORITY,
        "executable": False,
        "claim": _CLAIM,
    }
    return self_digest(document, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD)


def verify_v32_selection_semantic_output_v1(
    document: Mapping[str, Any],
    *,
    selection_input_context: Mapping[str, Any],
    selection_lossless_context_package: Mapping[str, Any] | None = None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _SELECTION_OUTPUT_FIELDS:
        raise V32AgentSemanticCompilerError("V32_AGENT_SELECTION_OUTPUT_INVALID")
    try:
        supplied = verify_self_digest(
            document, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD
        )
        rebuilt = build_v32_selection_semantic_output_v1(
            selection_input_context=selection_input_context,
            selected_candidate_id=document["selected_candidate_id"],
            selection_lossless_context_package=selection_lossless_context_package,
            proposal_lossless_context_package=proposal_lossless_context_package,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentSemanticCompilerError):
            raise
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_OUTPUT_INVALID"
        ) from exc
    _boundary(document, "V32_AGENT_SELECTION_OUTPUT_BOUNDARY_INVALID")
    _strings(
        document.get("selection_reason_refs"),
        "V32_AGENT_SELECTION_REASON_REFS_INVALID",
        allow_empty=False,
    )
    if dict(document) != rebuilt or supplied != rebuilt[
        SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD
    ]:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_OUTPUT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _verify_proposal_receipt_against_selection_packet(
    *,
    proposal_compile_receipt: Mapping[str, Any],
    selection_packet: Mapping[str, Any],
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    digest = verify_v32_proposal_semantic_compile_receipt_v1(
        proposal_compile_receipt,
        proposal_input_context=selection_packet["proposal_input_context"],
        proposal_delivery=selection_packet["proposal_delivery"],
        proposal_consumption=selection_packet["proposal_consumption"],
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    if (
        selection_packet["compiled_dynamic_research_state"]
        != proposal_compile_receipt["compiled_dynamic_research_state"]
        or selection_packet["sealed_action_evaluation"]
        != proposal_compile_receipt["sealed_action_evaluation"]
        or proposal_compile_receipt["proposal_input_context_digest"]
        != selection_packet["proposal_input_context"][
            AGENT_INPUT_CONTEXT_DIGEST_FIELD
        ]
        or proposal_compile_receipt["proposal_delivery_digest"]
        != selection_packet["proposal_delivery"][AGENT_DELIVERY_DIGEST_FIELD]
        or proposal_compile_receipt["proposal_consumption_digest"]
        != selection_packet["proposal_consumption"][
            AGENT_CONSUMPTION_DIGEST_FIELD
        ]
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PROPOSAL_RECEIPT_DRIFT"
        )
    return digest


def compile_v32_selection_delivery_v1(
    *,
    proposal_compile_receipt: Mapping[str, Any],
    selection_input_context: Mapping[str, Any],
    selection_delivery: Mapping[str, Any],
    selection_consumption: Mapping[str, Any],
    compiled_at: str,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Consume Selection and expose exactly its already-sealed plan variant."""

    context_digest, delivery_digest, consumption_digest = _verify_stage_chain(
        expected_stage="SELECTION",
        agent_input_context=selection_input_context,
        agent_delivery=selection_delivery,
        agent_consumption=selection_consumption,
        lossless_context_package=selection_lossless_context_package,
    )
    try:
        packet = resolve_v32_agent_canonical_packet_v1(
            selection_input_context,
            lossless_context_package=selection_lossless_context_package,
        )
        verify_v32_selection_canonical_packet_v1(packet)
    except (V32AgentLifecycleError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_PACKET_INVALID"
        ) from exc
    proposal_receipt_digest = _verify_proposal_receipt_against_selection_packet(
        proposal_compile_receipt=proposal_compile_receipt,
        selection_packet=packet,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    compiled = _time(compiled_at, "V32_AGENT_SELECTION_COMPILE_TIME_INVALID")
    if (
        _moment(compiled, "V32_AGENT_SELECTION_COMPILE_TIME_INVALID")
        < _moment(
            selection_consumption["consumed_at"],
            "V32_AGENT_SELECTION_COMPILE_TIME_INVALID",
        )
        or _moment(packet["prepared_at"], "V32_AGENT_SELECTION_COMPILE_TIME_INVALID")
        < _moment(
            proposal_compile_receipt["compiled_at"],
            "V32_AGENT_SELECTION_COMPILE_TIME_INVALID",
        )
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_COMPILE_TIME_INVALID"
        )
    output = _strict_delivery_object(selection_delivery)
    output_digest = verify_v32_selection_semantic_output_v1(
        output,
        selection_input_context=selection_input_context,
        selection_lossless_context_package=selection_lossless_context_package,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    candidate_id = output["selected_candidate_id"]
    variant = next(
        (
            item
            for item in proposal_compile_receipt["sealed_plan_variants"]
            if item["candidate_id"] == candidate_id
        ),
        None,
    )
    if variant is None or variant["variant_id"] != output["selected_variant_id"]:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_VARIANT_INVALID"
        )
    final_plan = variant["dynamic_action_plan"]
    try:
        final_digest = verify_v32_dynamic_action_plan_v1(
            final_plan,
            dynamic_research_state=proposal_compile_receipt[
                "compiled_dynamic_research_state"
            ],
        )
    except (V32DynamicActionPlanError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_FINAL_PLAN_INVALID"
        ) from exc
    document = {
        "schema_id": SELECTION_COMPILE_RECEIPT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": selection_input_context["run_id"],
        "cycle_index": selection_input_context["cycle_index"],
        "compiled_at": compiled,
        "proposal_semantic_compile_receipt_digest": proposal_receipt_digest,
        "selection_input_context_digest": context_digest,
        "selection_delivery_digest": delivery_digest,
        "selection_consumption_digest": consumption_digest,
        "selection_payload_sha256": selection_delivery["payload_sha256"],
        "selection_semantic_output_digest": output_digest,
        "compiled_dynamic_research_state_digest": proposal_compile_receipt[
            "compiled_dynamic_research_state_digest"
        ],
        "sealed_action_evaluation_digest": proposal_compile_receipt[
            "sealed_action_evaluation_digest"
        ],
        "selected_variant_id": output["selected_variant_id"],
        "selected_candidate_id": candidate_id,
        "selection_reason_code": output["selection_reason_code"],
        "selection_reason_refs": list(output["selection_reason_refs"]),
        "final_dynamic_action_plan": dict(final_plan),
        "final_dynamic_action_plan_digest": final_digest,
        "compile_status": "SELECTION_TERMINAL_CONSUMED_AND_EXACT_VARIANT_EXPOSED",
        "source_scope": _SOURCE_SCOPE,
        "external_execution_authority": _AUTHORITY,
        "executable": False,
        "claim": _CLAIM,
    }
    return self_digest(document, SELECTION_COMPILE_RECEIPT_DIGEST_FIELD)


def verify_v32_selection_semantic_compile_receipt_v1(
    document: Mapping[str, Any],
    *,
    proposal_compile_receipt: Mapping[str, Any],
    selection_input_context: Mapping[str, Any],
    selection_delivery: Mapping[str, Any],
    selection_consumption: Mapping[str, Any],
    selection_lossless_context_package: Mapping[str, Any] | None = None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _SELECTION_RECEIPT_FIELDS:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_COMPILE_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, SELECTION_COMPILE_RECEIPT_DIGEST_FIELD
        )
        rebuilt = compile_v32_selection_delivery_v1(
            proposal_compile_receipt=proposal_compile_receipt,
            selection_input_context=selection_input_context,
            selection_delivery=selection_delivery,
            selection_consumption=selection_consumption,
            compiled_at=document["compiled_at"],
            selection_lossless_context_package=selection_lossless_context_package,
            proposal_lossless_context_package=proposal_lossless_context_package,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentSemanticCompilerError):
            raise
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_COMPILE_RECEIPT_INVALID"
        ) from exc
    _boundary(document, "V32_AGENT_SELECTION_COMPILE_BOUNDARY_INVALID")
    if dict(document) != rebuilt or supplied != rebuilt[
        SELECTION_COMPILE_RECEIPT_DIGEST_FIELD
    ]:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_SELECTION_COMPILE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def verify_v32_final_action_plan_exact_match_v1(
    final_dynamic_action_plan: Mapping[str, Any],
    *,
    selection_consumption_digest: str,
    proposal_compile_receipt: Mapping[str, Any],
    selection_compile_receipt: Mapping[str, Any],
    selection_input_context: Mapping[str, Any],
    selection_delivery: Mapping[str, Any],
    selection_consumption: Mapping[str, Any],
    selection_lossless_context_package: Mapping[str, Any] | None = None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    """Prove commit material is byte-semantic-equal to the selected variant."""

    supplied_consumption = _digest(
        selection_consumption_digest,
        "V32_AGENT_FINAL_PLAN_SELECTION_CONSUMPTION_INVALID",
    )
    receipt_digest = verify_v32_selection_semantic_compile_receipt_v1(
        selection_compile_receipt,
        proposal_compile_receipt=proposal_compile_receipt,
        selection_input_context=selection_input_context,
        selection_delivery=selection_delivery,
        selection_consumption=selection_consumption,
        selection_lossless_context_package=selection_lossless_context_package,
        proposal_lossless_context_package=proposal_lossless_context_package,
    )
    del receipt_digest
    if (
        supplied_consumption
        != selection_consumption[AGENT_CONSUMPTION_DIGEST_FIELD]
        or supplied_consumption
        != selection_compile_receipt["selection_consumption_digest"]
        or dict(final_dynamic_action_plan)
        != selection_compile_receipt["final_dynamic_action_plan"]
        or final_dynamic_action_plan.get(ACTION_PLAN_DIGEST_FIELD)
        != selection_compile_receipt["final_dynamic_action_plan_digest"]
    ):
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_FINAL_PLAN_NOT_EXACT_SELECTED_VARIANT"
        )
    try:
        return verify_v32_dynamic_action_plan_v1(
            final_dynamic_action_plan,
            dynamic_research_state=proposal_compile_receipt[
                "compiled_dynamic_research_state"
            ],
        )
    except (V32DynamicActionPlanError, KeyError, TypeError, ValueError) as exc:
        raise V32AgentSemanticCompilerError(
            "V32_AGENT_FINAL_PLAN_INVALID"
        ) from exc


__all__ = [
    "PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD",
    "PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID",
    "PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD",
    "PROPOSAL_SEMANTIC_OUTPUT_SCHEMA_ID",
    "SELECTION_COMPILE_RECEIPT_DIGEST_FIELD",
    "SELECTION_COMPILE_RECEIPT_SCHEMA_ID",
    "SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD",
    "SELECTION_SEMANTIC_OUTPUT_SCHEMA_ID",
    "V32AgentSemanticCompilerError",
    "build_v32_proposal_semantic_output_v1",
    "build_v32_selection_semantic_output_v1",
    "canonical_v32_agent_semantic_json_v1",
    "compile_v32_proposal_delivery_v1",
    "compile_v32_selection_delivery_v1",
    "verify_v32_final_action_plan_exact_match_v1",
    "verify_v32_proposal_semantic_compile_receipt_v1",
    "verify_v32_proposal_semantic_output_v1",
    "verify_v32_selection_semantic_compile_receipt_v1",
    "verify_v32_selection_semantic_output_v1",
]
