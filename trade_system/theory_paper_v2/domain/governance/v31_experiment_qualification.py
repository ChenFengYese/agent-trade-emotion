"""Typed local qualification over one frozen V3.1 contract.

The qualification subject deliberately omits ``qualification_gates`` and the
manifest self-digest.  This breaks the otherwise unavoidable digest cycle:
typed receipts bind the stable manifest subject, and the final manifest binds
the typed receipts.  Physical-byte verification remains an Infrastructure
responsibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..contracts.canonical import (
    CanonicalContractError,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    MONITOR_SCHEMA_ID,
    OUTCOME_SCHEMA_ID,
    verify_minimal_experiment_contract,
)


TYPED_QUALIFICATION_GATE_IDS = ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q8")
TYPED_QUALIFICATION_SCHEMA_ID = (
    "theory_paper_v31_typed_qualification_gate_receipt"
)
TYPED_QUALIFICATION_SCHEMA_VERSION = "1.0.0"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_CONTRACT_SOURCE = (
    "trade_system/theory_paper_v2/domain/v31_experiment_contracts.py"
)
_CONTRACT_TEST = "tests/test_theory_paper_v2_v31_experiment_contracts.py"
_QUALIFICATION_SOURCE = (
    "trade_system/theory_paper_v2/domain/governance/"
    "v31_experiment_qualification.py"
)
_QUALIFICATION_TEST = (
    "tests/test_theory_paper_v2_v31_experiment_qualification.py"
)
_COMMON_EVIDENCE_PATHS = (
    _CONTRACT_SOURCE,
    _CONTRACT_TEST,
    _QUALIFICATION_SOURCE,
    _QUALIFICATION_TEST,
)
_GATE_EVIDENCE_PATHS = {
    "Q0": _COMMON_EVIDENCE_PATHS,
    "Q1": _COMMON_EVIDENCE_PATHS,
    "Q2": _COMMON_EVIDENCE_PATHS
    + (
        "trade_system/theory_paper_v2/domain/dynamic_research.py",
        "trade_system/theory_paper_v2/domain/agent_research_contract.py",
        "trade_system/theory_paper_v2/application/v31_research_cycle.py",
        "trade_system/theory_paper_v2/application/v31_durable_cycle.py",
        "trade_system/theory_paper_v2/infrastructure/v31_research_store.py",
        "tests/test_theory_paper_v2_dynamic_research.py",
        "tests/test_theory_paper_v2_v31_agent_contract.py",
        "tests/test_theory_paper_v2_v31_cycle.py",
        "tests/test_theory_paper_v2_v31_research_store.py",
    ),
    "Q3": _COMMON_EVIDENCE_PATHS
    + (
        "trade_system/theory_paper_v2/domain/portfolio_truth.py",
        "trade_system/theory_paper_v2/domain/behavior_planning.py",
        "trade_system/theory_paper_v2/domain/financial_evaluation.py",
        "tests/test_theory_paper_v2_v31_behavior_planning.py",
    ),
    "Q4": _COMMON_EVIDENCE_PATHS
    + (
        "trade_system/theory_paper_v2/application/ports.py",
        "trade_system/theory_paper_v2/application/v31_durable_bundle.py",
        "trade_system/theory_paper_v2/application/v31_durable_cycle.py",
        "trade_system/theory_paper_v2/domain/v31_monitor_runtime.py",
        "trade_system/theory_paper_v2/application/v31_monitor_runtime.py",
        "trade_system/theory_paper_v2/infrastructure/v31_research_store.py",
        "trade_system/theory_paper_v2/infrastructure/v31_monitor_store.py",
        "tests/test_theory_paper_v2_v31_cycle.py",
        "tests/test_theory_paper_v2_v31_durable_bundle.py",
        "tests/test_theory_paper_v2_v31_monitor_runtime.py",
        "tests/test_theory_paper_v2_v31_research_store.py",
    ),
    "Q5": _COMMON_EVIDENCE_PATHS
    + (
        "trade_system/theory_paper_v2/domain/association_estimation.py",
        "tests/test_theory_paper_v2_v31_association_estimation.py",
    ),
    "Q8": _COMMON_EVIDENCE_PATHS
    + (
        "trade_system/theory_paper_v2/domain/behavior_planning.py",
        "trade_system/theory_paper_v2/domain/financial_evaluation.py",
        "trade_system/theory_paper_v2/domain/portfolio_truth.py",
        "trade_system/theory_paper_v2/domain/scenario_path.py",
        "trade_system/theory_paper_v2/domain/v31_monitor_runtime.py",
        "trade_system/theory_paper_v2/application/v31_monitor_runtime.py",
        "trade_system/theory_paper_v2/infrastructure/v31_monitor_store.py",
        "trade_system/theory_paper_v2/infrastructure/v31_public_outcome_adapter.py",
        "tests/test_theory_paper_v2_v31_behavior_planning.py",
        "tests/test_theory_paper_v2_v31_probability_path.py",
        "tests/test_theory_paper_v2_v31_monitor_runtime.py",
        "tests/test_theory_paper_v2_v31_public_outcome_adapter.py",
    ),
}
_GATE_CHECK_IDS = {
    "Q0": (
        "Q0_EXPERIMENT_CONTRACT_SELF_DIGEST",
        "Q0_MANIFEST_CONTRACT_BINDING",
        "Q0_CAPABILITY_MATRIX_EXACT",
        "Q0_USED_SUBSET_IMPLEMENTED",
        "Q0_EXCLUDED_NOT_USED",
    ),
    "Q1": (
        "Q1_APPROVAL_RECEIPT_RECONSTRUCTED",
        "Q1_FROZEN_THEORY_SHA_EXACT",
        "Q1_MANIFEST_THEORY_BINDINGS_EXACT",
        "Q1_AUTHORITY_REMAINS_NON_EXECUTABLE",
    ),
    "Q2": (
        "Q2_TWELVE_AXIS_CONTRACT_EXACT",
        "Q2_LEGACY_MIGRATION_AND_UNKNOWN_AXES_EXACT",
        "Q2_PIT_CONTRIBUTOR_AND_PRIOR_CHANGE_CHAIN_BOUND",
        "Q2_SIX_STAGE_AND_CHECKPOINT_HEADS_BOUND",
        "Q2_NO_TOTAL_PROBABILITY_AND_NATIVE_SCOPE_EXCLUDED",
    ),
    "Q3": (
        "Q3_STATIC_FLAT_SHADOW_MODE",
        "Q3_NO_PORTFOLIO_WRITEBACK",
        "Q3_NO_PORTFOLIO_PERFORMANCE_CLAIM",
        "Q3_NO_PORTFOLIO_MUTATION_AUTHORITY",
    ),
    "Q4": (
        "Q4_TYPED_CONTENT_ADDRESSED_BUNDLE_CONTRACT",
        "Q4_SIX_DOCUMENT_SEMANTIC_REPLAY_CONTRACT",
        "Q4_APPEND_ONLY_STORE_AND_CAS_CHECKPOINT_CONTRACT",
        "Q4_CHAT_MEMORY_NOT_AUTHORITY",
        "Q4_DURABLE_CROSS_CYCLE_MONITOR_RUNTIME_BOUND",
    ),
    "Q5": (
        "Q5_EXACT_OKX_SWAP_PAIR_UNIVERSE",
        "Q5_PEARSON_FISHER_V1",
        "Q5_EIGHT_CLOSED_1H_LAG_ZERO",
        "Q5_FAMILY_ONE_NO_CORRECTION",
        "Q5_DESCRIPTIVE_NONCAUSAL_ONLY",
    ),
    "Q8": (
        "Q8_EIGHT_CYCLES_ONE_HOUR_OUTCOME_GRACE",
        "Q8_TYPED_MONITOR_AND_OUTCOME_CONTRACT",
        "Q8_UNKNOWN_AND_OTHER_PRESERVED",
        "Q8_ENDPOINTS_EXACT",
        "Q8_STOP_RULES_EXACT",
        "Q8_FINANCIAL_SHADOW_ASSUMPTIONS_EXACT",
        "Q8_FORBIDDEN_CLAIMS_EXACT",
    ),
}
_MANIFEST_SUBJECT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "manifest_id",
        "created_at",
        "run_id",
        "operation",
        "theory_binding",
        "theory_approval_binding",
        "experiment_contract_binding",
        "symbol",
        "instrument",
        "data_scope",
        "source_plan",
        "agent_plan",
        "fresh_run",
        "predecessor_run_id",
        "experiment_used_capabilities",
        "implemented_and_verified_capabilities",
        "excluded_no_claim_capabilities",
        "portfolio_scope",
        "association_preregistration",
        "evaluation_contract",
        "total_cycles",
        "cadence_seconds",
        "legal_action_classes",
        "stop_rules",
        "implementation_bindings",
        "assembly_bundle_contract",
        "checkpoint_contract",
        "event_order",
        "authorization_cardinality",
        "legacy_runs_resumable",
        "chat_history_is_authority",
        "authority_boundary",
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_access",
        "funds_access",
        "external_execution_authority",
        "executable",
    }
)
_THEORY_APPROVAL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "approval_id",
        "approved_at",
        "approval_source",
        "user_statement",
        "theory_path",
        "theory_version",
        "theory_physical_sha256",
        "approval_scope",
        "experiment_authorization_status",
        "excluded_authority",
        "legacy_runs_resumable",
        "external_execution_authority",
        "executable",
        "approval_receipt_digest",
    }
)
_V31_SENTIMENT_AXES = (
    "PRICE_DIRECTIONAL_PRESSURE",
    "STRUCTURE_PERSISTENCE",
    "PARTICIPATION_AND_ACTIVE_FLOW",
    "CROWDING_DIRECTION",
    "LEVERAGE_CHANGE",
    "FORCED_DELEVERAGING_PRESSURE",
    "LIQUIDITY_RESILIENCE",
    "VOLATILITY_AND_TAIL_STRESS",
    "EVENT_AND_NARRATIVE_REACTION",
    "ATTENTION_AND_AUDIENCE_RESPONSE",
    "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
    "TIMEFRAME_COHERENCE",
)
_V31_SENTIMENT_LEGACY_AXIS_MAP = {
    "PRICE_DIRECTIONAL_PRESSURE": "PRICE_DIRECTIONAL_PRESSURE",
    "STRUCTURE_PERSISTENCE": "STRUCTURE_PERSISTENCE",
    "PARTICIPATION_AND_FLOW": "PARTICIPATION_AND_ACTIVE_FLOW",
    "CROWDING_DIRECTION": "CROWDING_DIRECTION",
    "LEVERAGE_CHANGE": "LEVERAGE_CHANGE",
    "LIQUIDITY_RESILIENCE": "LIQUIDITY_RESILIENCE",
    "VOLATILITY_STRESS": "VOLATILITY_AND_TAIL_STRESS",
    "EVENT_REACTION": "EVENT_AND_NARRATIVE_REACTION",
    "CROSS_MARKET_RISK_APPETITE": "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
    "TIMEFRAME_COHERENCE": "TIMEFRAME_COHERENCE",
}
_V31_SENTIMENT_UNMAPPED_AXES = (
    "FORCED_DELEVERAGING_PRESSURE",
    "ATTENTION_AND_AUDIENCE_RESPONSE",
)
_EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)
_Q2_CHAIN_BINDINGS = (
    "inputs_receipt.sentiment_state_digest+sentiment_change_digest",
    "agent_proposal.sentiment_state_digest+sentiment_change_digest",
    "cycle_preselection.sentiment_state_digest+sentiment_change_digest",
    "accepted_state.sentiment_state_digest+sentiment_change_digest",
    "completion_receipt.sentiment_state_digest+sentiment_change_digest",
    "checkpoint.accepted_sentiment_state_digest+accepted_sentiment_change_digest",
)
_Q4_ASSEMBLY_CONTRACT = {
    "schema_id": "theory_paper_v2_v31_durable_assembly_bundle",
    "schema_version": "1.0.0",
    "content_addressed": True,
    "chat_history_is_authority": False,
}
_Q4_CHECKPOINT_CONTRACT = {
    "schema_id": "theory_paper_v31_research_checkpoint",
    "schema_version": "1.2.0",
    "genesis_bindings_required": True,
}
_Q4_MONITOR_CHECKPOINT_CONTRACT = {
    "schema_id": "theory_paper_v31_monitor_checkpoint",
    "schema_version": "1.0.0",
    "one_plan_per_accepted_cycle": True,
    "one_reserved_public_attempt_per_plan": True,
    "retry_allowed": False,
    "outcome_receipt_chain_required": True,
    "artifact_write_once": True,
    "checkpoint_compare_and_swap": True,
}


class V31ExperimentQualificationError(ValueError):
    """A typed V3.1 qualification gate could not honestly pass."""


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ExperimentQualificationError(code)
    return value


def _timestamp(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31ExperimentQualificationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ExperimentQualificationError(code) from exc
    if parsed.tzinfo is None:
        raise V31ExperimentQualificationError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31ExperimentQualificationError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31ExperimentQualificationError(code)
    return value


def _relative_path(value: Any, code: str) -> str:
    value = _text(value, code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31ExperimentQualificationError(code)
    return value


def _verify_q1_theory_approval(
    theory_approval: Mapping[str, Any] | None,
) -> str:
    """Reconstruct the exact semantic approval, not merely a supplied digest."""

    if not isinstance(theory_approval, Mapping):
        raise V31ExperimentQualificationError("Q1_THEORY_APPROVAL_REQUIRED")
    try:
        approval_digest = verify_self_digest(
            theory_approval, "approval_receipt_digest"
        )
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31ExperimentQualificationError(
            "Q1_THEORY_APPROVAL_DIGEST_INVALID"
        ) from exc
    if (
        set(theory_approval) != _THEORY_APPROVAL_FIELDS
        or theory_approval.get("schema_id")
        != "theory_paper_v31_user_approval_receipt"
        or theory_approval.get("schema_version") != "1.0.0"
        or theory_approval.get("approval_source")
        != "CURRENT_CODEX_TASK_USER_MESSAGE"
        or theory_approval.get("user_statement") != "我批准，并授权实验"
        or theory_approval.get("theory_version") != "3.1"
        or theory_approval.get("approval_scope")
        != [
            "FROZEN_V3_1_THEORY_AUTHORITY",
            "SOLE_FRESH_BTC_USDT_PUBLIC_DATA_NON_EXECUTABLE_PROSPECTIVE_EXPERIMENT_AFTER_Q0_Q8",
        ]
        or theory_approval.get("experiment_authorization_status")
        != "CONDITIONAL_ON_Q0_Q8_AND_EXACT_RUN_MANIFEST_RECEIPT_BINDING"
        or theory_approval.get("excluded_authority")
        != [
            "RESUME_LEGACY_RUN",
            "ACCOUNT_ACCESS",
            "PAPER_TRADING",
            "LIVE_TRADING",
            "ORDER_SUBMISSION",
            "CREDENTIAL_ACCESS",
            "FUNDS_ACCESS",
        ]
        or theory_approval.get("legacy_runs_resumable") is not False
        or theory_approval.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or theory_approval.get("executable") is not False
    ):
        raise V31ExperimentQualificationError("Q1_THEORY_APPROVAL_INVALID")
    _text(theory_approval.get("approval_id"), "Q1_THEORY_APPROVAL_INVALID")
    _timestamp(
        theory_approval.get("approved_at"), "Q1_THEORY_APPROVAL_TIME_INVALID"
    )
    _relative_path(
        theory_approval.get("theory_path"), "Q1_THEORY_PATH_INVALID"
    )
    _digest(
        theory_approval.get("theory_physical_sha256"),
        "Q1_THEORY_SHA_INVALID",
    )
    return approval_digest


def _capability_row(
    experiment_contract: Mapping[str, Any], capability_id: str
) -> Mapping[str, Any]:
    matrix = experiment_contract.get("capability_matrix")
    if not isinstance(matrix, list):
        raise V31ExperimentQualificationError(
            "QUALIFICATION_CAPABILITY_MATRIX_INVALID"
        )
    matches = [
        row
        for row in matrix
        if isinstance(row, Mapping) and row.get("capability_id") == capability_id
    ]
    if len(matches) != 1:
        raise V31ExperimentQualificationError(
            "QUALIFICATION_CAPABILITY_MATRIX_INVALID"
        )
    return matches[0]


def _expected_capability_sets(
    experiment_contract: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    matrix = experiment_contract["capability_matrix"]
    if not isinstance(matrix, list) or not matrix:
        raise V31ExperimentQualificationError("Q0_CAPABILITY_MATRIX_INVALID")
    ids = [row.get("capability_id") for row in matrix if isinstance(row, Mapping)]
    if len(ids) != len(matrix) or any(not isinstance(value, str) for value in ids):
        raise V31ExperimentQualificationError("Q0_CAPABILITY_MATRIX_INVALID")
    if len(ids) != len(set(ids)):
        raise V31ExperimentQualificationError("Q0_CAPABILITY_MATRIX_DUPLICATE")
    implemented = sorted(
        row["capability_id"]
        for row in matrix
        if row.get("status") == "IMPLEMENTED_AND_VERIFIED"
    )
    excluded = sorted(
        row["capability_id"]
        for row in matrix
        if row.get("status") == "EXCLUDED_NO_CLAIM"
    )
    used = sorted(
        row["capability_id"]
        for row in matrix
        if row.get("used_or_evaluated") is True
    )
    if (
        len(implemented) + len(excluded) != len(matrix)
        or not set(used).issubset(implemented)
        or set(implemented) & set(excluded)
        or set(used) & set(excluded)
    ):
        raise V31ExperimentQualificationError("Q0_CAPABILITY_MATRIX_INVALID")
    return used, implemented, excluded


def manifest_qualification_subject_digest(manifest: Mapping[str, Any]) -> str:
    """Digest every manifest field except its receipt set and self-digest."""

    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema_id")
        != "theory_paper_v31_frozen_experiment_manifest"
        or manifest.get("schema_version") != "1.1.0"
    ):
        raise V31ExperimentQualificationError("QUALIFICATION_MANIFEST_INVALID")
    subject = dict(manifest)
    subject.pop("manifest_digest", None)
    subject.pop("qualification_gates", None)
    if set(subject) != _MANIFEST_SUBJECT_FIELDS:
        raise V31ExperimentQualificationError(
            "QUALIFICATION_MANIFEST_SUBJECT_SCHEMA_INVALID"
        )
    try:
        return canonical_digest(subject)
    except CanonicalContractError as exc:
        raise V31ExperimentQualificationError(
            "QUALIFICATION_MANIFEST_SUBJECT_INVALID"
        ) from exc


def validate_manifest_experiment_contract_alignment(
    manifest: Mapping[str, Any], experiment_contract: Mapping[str, Any]
) -> str:
    """Mechanically cross-check the full frozen manifest subject and contract."""

    _cross_validate_manifest_contract(manifest, experiment_contract)
    return manifest_qualification_subject_digest(manifest)


def _cross_validate_manifest_contract(
    manifest: Mapping[str, Any], experiment_contract: Mapping[str, Any]
) -> None:
    try:
        contract_digest = verify_minimal_experiment_contract(experiment_contract)
    except ValueError as exc:
        raise V31ExperimentQualificationError(
            "QUALIFICATION_EXPERIMENT_CONTRACT_INVALID"
        ) from exc
    binding = manifest.get("experiment_contract_binding")
    instrument = manifest.get("instrument")
    expected_instrument = {
        "venue": "OKX",
        "instrument_id": "BTC-USDT-SWAP",
        "market_type": "PERPETUAL_SWAP",
        "underlying_symbol": "BTC-USDT",
    }
    top_level_denials = (
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_access",
        "funds_access",
    )
    if (
        not isinstance(binding, Mapping)
        or set(binding)
        != {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
        or binding.get("schema_id") != EXPERIMENT_SCHEMA_ID
        or binding.get("digest_field") != "experiment_contract_digest"
        or binding.get("semantic_digest") != contract_digest
        or not isinstance(binding.get("path"), str)
        or not binding["path"]
        or _HEX_64.fullmatch(str(binding.get("physical_sha256") or "")) is None
        or manifest.get("run_id") != experiment_contract.get("run_id")
        or manifest.get("symbol") != "BTC-USDT"
        or instrument != expected_instrument
        or experiment_contract.get("instrument", {}).get("venue") != "OKX"
        or experiment_contract.get("instrument", {}).get("instrument_id")
        != "BTC-USDT-SWAP"
        or experiment_contract.get("instrument", {}).get("market_type")
        != "PERPETUAL_SWAP"
        or manifest.get("data_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or manifest.get("operation") != "RUN_V31_PROSPECTIVE"
        or manifest.get("fresh_run") is not True
        or manifest.get("predecessor_run_id") is not None
        or manifest.get("total_cycles") != 8
        or manifest.get("cadence_seconds") != 3600
        or manifest.get("legal_action_classes")
        != ["OPEN_LONG", "OPEN_SHORT", "WAIT"]
        or manifest.get("portfolio_scope")
        != experiment_contract.get("portfolio_scope")
        or manifest.get("association_preregistration")
        != experiment_contract.get("association_scope")
        or manifest.get("evaluation_contract")
        != experiment_contract.get("evaluation")
        or manifest.get("stop_rules")
        != experiment_contract.get("evaluation", {})
        .get("stop_rules", {})
        .get("stop_immediately_on")
        or any(manifest.get(field) is not False for field in top_level_denials)
        or manifest.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or manifest.get("executable") is not False
        or manifest.get("chat_history_is_authority") is not False
        or manifest.get("legacy_runs_resumable") is not False
    ):
        raise V31ExperimentQualificationError(
            "QUALIFICATION_MANIFEST_CONTRACT_MISMATCH"
        )
    used, implemented, excluded = _expected_capability_sets(experiment_contract)
    if (
        manifest.get("experiment_used_capabilities") != used
        or manifest.get("implemented_and_verified_capabilities") != implemented
        or manifest.get("excluded_no_claim_capabilities") != excluded
    ):
        raise V31ExperimentQualificationError(
            "QUALIFICATION_MANIFEST_CAPABILITY_MISMATCH"
        )
    boundary = manifest.get("authority_boundary")
    if boundary != experiment_contract.get("authority_boundary"):
        raise V31ExperimentQualificationError(
            "QUALIFICATION_MANIFEST_AUTHORITY_MISMATCH"
        )


def _evidence_bindings(
    gate_id: str,
    manifest: Mapping[str, Any],
    *,
    theory_approval: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    implementations = manifest.get("implementation_bindings")
    if not isinstance(implementations, Mapping):
        raise V31ExperimentQualificationError(
            "QUALIFICATION_IMPLEMENTATION_BINDINGS_INVALID"
        )
    result: list[dict[str, str]] = []
    if gate_id == "Q1":
        approval_digest = _verify_q1_theory_approval(theory_approval)
        theory_binding = manifest.get("theory_binding")
        approval_binding = manifest.get("theory_approval_binding")
        if not isinstance(theory_binding, Mapping) or not isinstance(
            approval_binding, Mapping
        ):
            raise V31ExperimentQualificationError(
                "Q1_MANIFEST_THEORY_BINDINGS_INVALID"
            )
        dynamic_rows = (
            (
                "FROZEN_THEORY_DOCUMENT",
                theory_binding.get("path"),
                theory_binding.get("physical_sha256"),
            ),
            (
                "THEORY_APPROVAL_RECEIPT",
                approval_binding.get("path"),
                approval_binding.get("physical_sha256"),
            ),
        )
        if approval_binding.get("semantic_digest") != approval_digest:
            raise V31ExperimentQualificationError(
                "Q1_MANIFEST_APPROVAL_BINDING_MISMATCH"
            )
        for evidence_kind, path, physical_sha256 in dynamic_rows:
            normalized_path = _relative_path(
                path, "Q1_DYNAMIC_EVIDENCE_PATH_INVALID"
            )
            normalized_sha = _digest(
                physical_sha256, "Q1_DYNAMIC_EVIDENCE_SHA_INVALID"
            )
            result.append(
                {
                    "evidence_id": f"Q1:{normalized_path}",
                    "evidence_kind": evidence_kind,
                    "path": normalized_path,
                    "physical_sha256": normalized_sha,
                    "binding_digest": canonical_digest(
                        {
                            "path": normalized_path,
                            "physical_sha256": normalized_sha,
                        }
                    ),
                }
            )
    for path in sorted(_GATE_EVIDENCE_PATHS[gate_id]):
        physical_sha256 = implementations.get(path)
        _digest(
            physical_sha256,
            "QUALIFICATION_REQUIRED_IMPLEMENTATION_OR_TEST_EVIDENCE_MISSING",
        )
        result.append(
            {
                "evidence_id": f"{gate_id}:{path}",
                "evidence_kind": (
                    "TEST_SOURCE" if path.startswith("tests/") else "IMPLEMENTATION_SOURCE"
                ),
                "path": path,
                "physical_sha256": physical_sha256,
                "binding_digest": canonical_digest(
                    {"path": path, "physical_sha256": physical_sha256}
                ),
            }
        )
    return sorted(result, key=lambda row: (row["path"], row["evidence_kind"]))


def _check_projections(
    gate_id: str,
    *,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    theory_approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if gate_id == "Q0":
        used, implemented, excluded = _expected_capability_sets(experiment_contract)
        return {
            "Q0_EXPERIMENT_CONTRACT_SELF_DIGEST": {
                "experiment_contract_digest": experiment_contract[
                    "experiment_contract_digest"
                ]
            },
            "Q0_MANIFEST_CONTRACT_BINDING": manifest[
                "experiment_contract_binding"
            ],
            "Q0_CAPABILITY_MATRIX_EXACT": {
                "contract_capability_matrix": experiment_contract[
                    "capability_matrix"
                ],
                "manifest_used": manifest["experiment_used_capabilities"],
                "manifest_implemented": manifest[
                    "implemented_and_verified_capabilities"
                ],
                "manifest_excluded": manifest[
                    "excluded_no_claim_capabilities"
                ],
            },
            "Q0_USED_SUBSET_IMPLEMENTED": {
                "used": used,
                "implemented": implemented,
            },
            "Q0_EXCLUDED_NOT_USED": {"used": used, "excluded": excluded},
        }
    if gate_id == "Q1":
        approval_digest = _verify_q1_theory_approval(theory_approval)
        assert theory_approval is not None
        theory_binding = manifest.get("theory_binding")
        approval_binding = manifest.get("theory_approval_binding")
        authority_boundary = experiment_contract.get("authority_boundary")
        if (
            not isinstance(theory_binding, Mapping)
            or set(theory_binding)
            != {"path", "version", "review_status", "physical_sha256"}
            or theory_binding.get("path") != theory_approval.get("theory_path")
            or theory_binding.get("version") != "3.1"
            or theory_binding.get("review_status") != "FROZEN_APPROVED"
            or theory_binding.get("physical_sha256")
            != theory_approval.get("theory_physical_sha256")
            or theory_binding.get("physical_sha256")
            != experiment_contract.get("approved_theory_sha256")
            or not isinstance(approval_binding, Mapping)
            or set(approval_binding)
            != {
                "path",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            }
            or approval_binding.get("schema_id")
            != "theory_paper_v31_user_approval_receipt"
            or approval_binding.get("digest_field") != "approval_receipt_digest"
            or approval_binding.get("semantic_digest") != approval_digest
            or not isinstance(authority_boundary, Mapping)
            or authority_boundary.get("executable") is not False
            or authority_boundary.get("account_access") is not False
            or authority_boundary.get("paper_trading") is not False
            or authority_boundary.get("live_trading") is not False
            or authority_boundary.get("order_submission") is not False
            or authority_boundary.get("credential_use") is not False
            or authority_boundary.get("funds_access") is not False
        ):
            raise V31ExperimentQualificationError(
                "Q1_THEORY_APPROVAL_OR_MANIFEST_BINDING_MISMATCH"
            )
        _relative_path(
            approval_binding.get("path"), "Q1_APPROVAL_BINDING_PATH_INVALID"
        )
        _digest(
            approval_binding.get("physical_sha256"),
            "Q1_APPROVAL_BINDING_SHA_INVALID",
        )
        return {
            "Q1_APPROVAL_RECEIPT_RECONSTRUCTED": {
                "approval_receipt_digest": approval_digest,
                "approved_at": theory_approval["approved_at"],
                "approval_source": theory_approval["approval_source"],
                "user_statement": theory_approval["user_statement"],
                "approval_scope": theory_approval["approval_scope"],
            },
            "Q1_FROZEN_THEORY_SHA_EXACT": {
                "approved_theory_sha256": experiment_contract[
                    "approved_theory_sha256"
                ],
                "approval_theory_sha256": theory_approval[
                    "theory_physical_sha256"
                ],
                "theory_path": theory_approval["theory_path"],
            },
            "Q1_MANIFEST_THEORY_BINDINGS_EXACT": {
                "theory_binding": theory_binding,
                "theory_approval_binding": approval_binding,
            },
            "Q1_AUTHORITY_REMAINS_NON_EXECUTABLE": authority_boundary,
        }
    if gate_id == "Q2":
        native_scope = _capability_row(
            experiment_contract,
            "NATIVE_TWELVE_AXIS_SOURCES_AND_FULL_GRAPH_PROJECTION",
        )
        if (
            native_scope
            != {
                "capability_id": (
                    "NATIVE_TWELVE_AXIS_SOURCES_AND_FULL_GRAPH_PROJECTION"
                ),
                "status": "EXCLUDED_NO_CLAIM",
                "used_or_evaluated": False,
                "evidence_scope": "NO_CLAIM",
            }
            or native_scope["capability_id"]
            not in manifest.get("excluded_no_claim_capabilities", ())
            or manifest.get("event_order") != list(_EVENT_ORDER)
            or manifest.get("checkpoint_contract") != _Q4_CHECKPOINT_CONTRACT
        ):
            raise V31ExperimentQualificationError(
                "Q2_SENTIMENT_SCOPE_OR_CHAIN_INVALID"
            )
        return {
            "Q2_TWELVE_AXIS_CONTRACT_EXACT": {
                "axis_count": 12,
                "axes": list(_V31_SENTIMENT_AXES),
                "representation": "ORDINAL_VECTOR_NOT_PROBABILITY",
                "unknown_is_neutral": False,
            },
            "Q2_LEGACY_MIGRATION_AND_UNKNOWN_AXES_EXACT": {
                "legacy_axis_map": dict(
                    sorted(_V31_SENTIMENT_LEGACY_AXIS_MAP.items())
                ),
                "unmapped_axes": list(_V31_SENTIMENT_UNMAPPED_AXES),
                "unmapped_axis_policy": "UNKNOWN_UNMAPPED_LEGACY_AXIS",
            },
            "Q2_PIT_CONTRIBUTOR_AND_PRIOR_CHANGE_CHAIN_BOUND": {
                "contributor_binding": (
                    "EXACT_PIT_DATUM_REF_DIGEST_VALUE_UNIT_WINDOW_SOURCE_RAW_TIME_DEPENDENCY"
                ),
                "path_action_minimum_admissibility": "INFERENCE_ADMISSIBLE",
                "prior_state_change_required": True,
                "missing_or_unmapped": "UNKNOWN_NOT_ZERO_NOT_NEUTRAL",
            },
            "Q2_SIX_STAGE_AND_CHECKPOINT_HEADS_BOUND": {
                "event_order": list(_EVENT_ORDER),
                "sentiment_digest_bindings": list(_Q2_CHAIN_BINDINGS),
                "checkpoint_contract": manifest["checkpoint_contract"],
            },
            "Q2_NO_TOTAL_PROBABILITY_AND_NATIVE_SCOPE_EXCLUDED": {
                "overall_numeric_score": None,
                "probability_status": "ORDINAL_VECTOR_NOT_PROBABILITY",
                "native_source_and_graph_projection_capability": native_scope,
            },
        }
    if gate_id == "Q3":
        scope = experiment_contract["portfolio_scope"]
        return {
            "Q3_STATIC_FLAT_SHADOW_MODE": {
                "mode": scope["mode"],
                "initial_position": scope["initial_position"],
                "manifest_scope": manifest["portfolio_scope"],
            },
            "Q3_NO_PORTFOLIO_WRITEBACK": {
                "next_cycle_portfolio_writeback": scope[
                    "next_cycle_portfolio_writeback"
                ]
            },
            "Q3_NO_PORTFOLIO_PERFORMANCE_CLAIM": {
                "portfolio_performance_claim": scope[
                    "portfolio_performance_claim"
                ]
            },
            "Q3_NO_PORTFOLIO_MUTATION_AUTHORITY": {
                "portfolio_mutation": experiment_contract["authority_boundary"][
                    "portfolio_mutation"
                ]
            },
        }
    if gate_id == "Q4":
        monitor_runtime = _capability_row(
            experiment_contract, "DURABLE_CROSS_CYCLE_MONITOR_RUNTIME"
        )
        if (
            manifest.get("assembly_bundle_contract") != _Q4_ASSEMBLY_CONTRACT
            or manifest.get("checkpoint_contract") != _Q4_CHECKPOINT_CONTRACT
            or manifest.get("event_order") != list(_EVENT_ORDER)
            or manifest.get("chat_history_is_authority") is not False
            or monitor_runtime
            != {
                "capability_id": "DURABLE_CROSS_CYCLE_MONITOR_RUNTIME",
                "status": "IMPLEMENTED_AND_VERIFIED",
                "used_or_evaluated": True,
                "evidence_scope": "LOCAL_DURABLE_RUNTIME",
            }
            or monitor_runtime["capability_id"]
            not in manifest.get("experiment_used_capabilities", ())
            or monitor_runtime["capability_id"]
            not in manifest.get("implemented_and_verified_capabilities", ())
            or monitor_runtime["capability_id"]
            in manifest.get("excluded_no_claim_capabilities", ())
        ):
            raise V31ExperimentQualificationError(
                "Q4_DURABLE_REPLAY_SCOPE_INVALID"
            )
        return {
            "Q4_TYPED_CONTENT_ADDRESSED_BUNDLE_CONTRACT": {
                **_Q4_ASSEMBLY_CONTRACT,
                "relative_ref_pattern": (
                    "cycles/{cycle_index:04d}/assembly-bundles/"
                    "{assembly_bundle_digest}.json"
                ),
                "type_language": "STRICT_WHITELISTED_CANONICAL_JSON",
            },
            "Q4_SIX_DOCUMENT_SEMANTIC_REPLAY_CONTRACT": {
                "event_order": list(_EVENT_ORDER),
                "rebuild_target": "ALL_SIX_SEMANTIC_ARTIFACTS",
                "replay_input": "DURABLE_TYPED_ASSEMBLY_BUNDLE_ONLY",
                "fresh_process_without_chat_or_process_objects": True,
                "re_signed_mutually_consistent_fiction_rejected": True,
            },
            "Q4_APPEND_ONLY_STORE_AND_CAS_CHECKPOINT_CONTRACT": {
                "checkpoint_contract": _Q4_CHECKPOINT_CONTRACT,
                "artifact_write_policy": "WRITE_ONCE_WITH_PHYSICAL_READBACK",
                "event_policy": "APPEND_ONLY_HASH_CHAIN_FIXED_ORDER",
                "checkpoint_policy": "COMPARE_AND_SWAP",
                "bundle_binding_policy": "ONE_CONTENT_ADDRESSED_BINDING_PER_COMPLETED_CYCLE",
            },
            "Q4_CHAT_MEMORY_NOT_AUTHORITY": {
                "chat_history_is_authority": False,
                "resume_source": "PHYSICALLY_VERIFIED_STORE_AND_TYPED_BUNDLE",
            },
            "Q4_DURABLE_CROSS_CYCLE_MONITOR_RUNTIME_BOUND": {
                "capability": monitor_runtime,
                "monitor_checkpoint_contract": _Q4_MONITOR_CHECKPOINT_CONTRACT,
                "schedule_boundary": (
                    "AFTER_PHYSICAL_ACCEPTED_STATE_BEFORE_DELAYED_OBSERVATION"
                ),
                "pre_horizon_action": "READ_ONLY_STATUS_ONLY",
                "observation_boundary": (
                    "EXPLICIT_OKX_PUBLIC_MARK_PRICE_GET_NO_ACCOUNT_OR_ORDER_PORT"
                ),
                "failure_policy": "PERMANENT_FAIL_CLOSED_NO_RETRY",
            },
        }
    if gate_id == "Q5":
        association = experiment_contract["association_scope"]
        pair = association["pair_universe"][0]
        return {
            "Q5_EXACT_OKX_SWAP_PAIR_UNIVERSE": {
                "instrument": experiment_contract["instrument"],
                "pair_universe": association["pair_universe"],
            },
            "Q5_PEARSON_FISHER_V1": {
                "estimator": association["estimator"],
                "model_version": association["model_version"],
            },
            "Q5_EIGHT_CLOSED_1H_LAG_ZERO": {
                "window": association["window"],
                "lag": pair["lag"],
            },
            "Q5_FAMILY_ONE_NO_CORRECTION": association["multiplicity"],
            "Q5_DESCRIPTIVE_NONCAUSAL_ONLY": {
                "use": association["use"],
                "action_or_probability_input": association[
                    "action_or_probability_input"
                ],
                "causal_claim": association["causal_claim"],
                "association_change_claim": association[
                    "association_change_claim"
                ],
            },
        }
    cycle = experiment_contract["cycle_protocol"]
    evaluation = experiment_contract["evaluation"]
    monitor_capability = next(
            row
            for row in experiment_contract["capability_matrix"]
            if row["capability_id"]
            == "TYPED_PATH_MONITOR_PLAN_AND_OUTCOME_RECEIPT"
    )
    durable_monitor_capability = next(
            row
            for row in experiment_contract["capability_matrix"]
            if row["capability_id"]
            == "DURABLE_CROSS_CYCLE_MONITOR_RUNTIME"
    )
    return {
        "Q8_EIGHT_CYCLES_ONE_HOUR_OUTCOME_GRACE": cycle,
        "Q8_TYPED_MONITOR_AND_OUTCOME_CONTRACT": {
            "monitor_schema_id": MONITOR_SCHEMA_ID,
            "outcome_schema_id": OUTCOME_SCHEMA_ID,
            "capability": monitor_capability,
            "durable_runtime_capability": durable_monitor_capability,
            "monitor_checkpoint_contract": _Q4_MONITOR_CHECKPOINT_CONTRACT,
            "horizon_observation_semantics": (
                "FIRST_PUBLIC_MARK_OBSERVATION_AT_OR_AFTER_1H_HORIZON"
            ),
        },
        "Q8_UNKNOWN_AND_OTHER_PRESERVED": evaluation["unknown_other_policy"],
        "Q8_ENDPOINTS_EXACT": {
            "primary_endpoints": evaluation["primary_endpoints"],
            "secondary_endpoints": evaluation["secondary_endpoints"],
        },
        "Q8_STOP_RULES_EXACT": evaluation["stop_rules"],
        "Q8_FINANCIAL_SHADOW_ASSUMPTIONS_EXACT": experiment_contract[
            "portfolio_scope"
        ]["financial_shadow"],
        "Q8_FORBIDDEN_CLAIMS_EXACT": {
            "excluded_metrics_and_claims": evaluation[
                "excluded_metrics_and_claims"
            ],
            "authority_boundary": experiment_contract["authority_boundary"],
        },
    }


def build_typed_qualification_receipt(
    *,
    gate_id: str,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    theory_approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one PASS receipt only after all exact gate checks succeed."""

    if gate_id not in TYPED_QUALIFICATION_GATE_IDS:
        raise V31ExperimentQualificationError("QUALIFICATION_GATE_ID_INVALID")
    _cross_validate_manifest_contract(manifest, experiment_contract)
    experiment_contract_digest = verify_minimal_experiment_contract(
        experiment_contract
    )
    evidence = _evidence_bindings(
        gate_id, manifest, theory_approval=theory_approval
    )
    projections = _check_projections(
        gate_id,
        experiment_contract=experiment_contract,
        manifest=manifest,
        theory_approval=theory_approval,
    )
    evidence_paths = [row["path"] for row in evidence]
    checks = [
        {
            "check_id": check_id,
            "status": "PASS",
            "verified_projection_digest": canonical_digest(projections[check_id]),
            "evidence_paths": evidence_paths,
        }
        for check_id in _GATE_CHECK_IDS[gate_id]
    ]
    limitations = [
        "Typed qualification proves frozen local contracts and bound evidence only.",
        "It does not create a manifest, start a run, or prove predictive validity.",
    ]
    if gate_id == "Q2":
        limitations.extend(
            [
                "Q2 covers the explicit legacy ten-to-twelve-axis migration and six-stage local digest chain only.",
                "Native twelve-axis sources and full sentiment graph projection remain excluded with no claim.",
            ]
        )
    elif gate_id == "Q4":
        limitations.extend(
            [
                "Q4 covers deterministic local bundle replay plus the tested durable cross-cycle monitor runtime.",
                "The fake public adapter test does not prove external network or automation reliability.",
            ]
        )
    document = {
        "schema_id": TYPED_QUALIFICATION_SCHEMA_ID,
        "schema_version": TYPED_QUALIFICATION_SCHEMA_VERSION,
        "gate_id": gate_id,
        "evaluated_at": _timestamp(
            evaluated_at, "QUALIFICATION_EVALUATED_AT_INVALID"
        ),
        "verdict": "PASS",
        "experiment_contract_digest": experiment_contract_digest,
        "manifest_qualification_subject_digest": (
            manifest_qualification_subject_digest(manifest)
        ),
        "evidence_bindings": evidence,
        "checks": checks,
        "limitations": limitations,
        "authority_boundary": experiment_contract["authority_boundary"],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "qualification_receipt_digest")


def verify_typed_qualification_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_gate_id: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    theory_approval: Mapping[str, Any] | None = None,
) -> str:
    """Reconstruct a typed receipt; arbitrary digest evidence cannot pass."""

    if not isinstance(receipt, Mapping) or expected_gate_id not in TYPED_QUALIFICATION_GATE_IDS:
        raise V31ExperimentQualificationError("QUALIFICATION_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(receipt, "qualification_receipt_digest")
        if (
            receipt.get("schema_id") != TYPED_QUALIFICATION_SCHEMA_ID
            or receipt.get("schema_version") != TYPED_QUALIFICATION_SCHEMA_VERSION
            or receipt.get("gate_id") != expected_gate_id
            or receipt.get("verdict") != "PASS"
        ):
            raise V31ExperimentQualificationError("QUALIFICATION_RECEIPT_INVALID")
        rebuilt = build_typed_qualification_receipt(
            gate_id=expected_gate_id,
            evaluated_at=receipt["evaluated_at"],
            experiment_contract=experiment_contract,
            manifest=manifest,
            theory_approval=theory_approval,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentQualificationError):
            raise
        raise V31ExperimentQualificationError(
            "QUALIFICATION_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(receipt) or supplied != rebuilt["qualification_receipt_digest"]:
        raise V31ExperimentQualificationError(
            "QUALIFICATION_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def required_gate_evidence_paths(gate_id: str) -> tuple[str, ...]:
    if gate_id not in TYPED_QUALIFICATION_GATE_IDS:
        raise V31ExperimentQualificationError("QUALIFICATION_GATE_ID_INVALID")
    return tuple(sorted(_GATE_EVIDENCE_PATHS[gate_id]))


__all__ = [
    "TYPED_QUALIFICATION_GATE_IDS",
    "TYPED_QUALIFICATION_SCHEMA_ID",
    "V31ExperimentQualificationError",
    "build_typed_qualification_receipt",
    "manifest_qualification_subject_digest",
    "required_gate_evidence_paths",
    "validate_manifest_experiment_contract_alignment",
    "verify_typed_qualification_receipt",
]
