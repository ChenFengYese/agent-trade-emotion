"""Frozen PIT adapter and digest store for action-discrimination E0."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ..application.formal_e0_batch import _load_dataset
from ..domain.action_discrimination.engine import build_decision_context
from ..domain.action_discrimination.model import (
    E0A_FINANCIAL_CONTRACT,
    E0B_FINANCIAL_CONTRACT,
    E0B_SAMPLE_INDICES,
    EVIDENCE_CLASS,
    EXECUTION_AUTHORITY,
    OUTPUT_SPECS,
    SAMPLE_INDICES,
    SEMANTIC_OUTPUT_SCHEMA,
    SYSTEM_MODE,
    ActionDiscriminationError,
    profile_for_window_index,
)
from ..domain.action_discrimination.validation import (
    arm_preoutcome_score,
    validate_semantic_output,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from .formal_e0_batch_store import load_prepared_formal_e0_run


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MUTABLE_NAMES = {"current", "latest"}
EXPECTED_ROLE_KEYS = tuple(OUTPUT_SPECS)
INITIAL_EVENT_HEAD = "0" * 64


class ActionExperimentStoreError(ValueError):
    """A frozen binding, write-once or checkpoint failure."""


def _sample_indices_from_range(value: Any) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(item) is not int for item in value)
        or value[1] - value[0] != 31
    ):
        raise ActionExperimentStoreError("ACTION_SAMPLE_WINDOW_INVALID")
    indices = tuple(range(value[0], value[1] + 1))
    if indices not in {SAMPLE_INDICES, E0B_SAMPLE_INDICES}:
        raise ActionExperimentStoreError("ACTION_SAMPLE_WINDOW_UNREGISTERED")
    return indices


def _manifest_sample_indices(manifest: Mapping[str, Any]) -> tuple[int, ...]:
    return _sample_indices_from_range(manifest.get("decision_indices_inclusive"))


def _financial_contract(value: Mapping[str, Any]) -> str:
    contract = value.get("financial_contract_version", E0A_FINANCIAL_CONTRACT)
    if contract not in {E0A_FINANCIAL_CONTRACT, E0B_FINANCIAL_CONTRACT}:
        raise ActionExperimentStoreError("FINANCIAL_CONTRACT_VERSION_INVALID")
    return str(contract)


def _safe_id(value: str, code: str) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_ID.fullmatch(value) is None
        or value.casefold() in _MUTABLE_NAMES
    ):
        raise ActionExperimentStoreError(code)
    return value


def _physical_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise ActionExperimentStoreError(f"ARTIFACT_MISSING:{path}") from exc


def _verify_context_self_digest(value: Mapping[str, Any]) -> str:
    supplied = value.get("context_digest")
    candidate = dict(value)
    candidate.pop("context_digest", None)
    if not isinstance(supplied, str) or canonical_digest(candidate) != supplied:
        raise ActionExperimentStoreError("CONTEXT_SELF_DIGEST_INVALID")
    return supplied


def _atomic_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value) + b"\n"
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


class FrozenActionDatasetAdapter:
    """Expose decision views only; this class deliberately has no outcome API."""

    def __init__(
        self,
        source_run_root: Path,
        *,
        sample_indices: tuple[int, ...] = SAMPLE_INDICES,
        financial_contract_version: str = E0A_FINANCIAL_CONTRACT,
    ) -> None:
        self.prepared = load_prepared_formal_e0_run(Path(source_run_root))
        self._dataset = _load_dataset(self.prepared)
        self.sample_indices = _sample_indices_from_range(
            [sample_indices[0], sample_indices[-1]]
        )
        if financial_contract_version not in {
            E0A_FINANCIAL_CONTRACT,
            E0B_FINANCIAL_CONTRACT,
        }:
            raise ActionExperimentStoreError(
                "FINANCIAL_CONTRACT_VERSION_INVALID"
            )
        self.financial_contract_version = financial_contract_version

    @property
    def source_bindings(self) -> dict[str, Any]:
        return {
            "source_run_id": self.prepared.run_id,
            "source_run_bindings_digest": self.prepared.run_bindings_digest,
            "dataset_manifest_digest": self.prepared.dataset_manifest_digest,
            "dataset_payload_digest": self.prepared.dataset_payload_digest,
        }

    def decision_context(self, sample_index: int) -> dict[str, Any]:
        if sample_index not in self.sample_indices:
            raise ActionExperimentStoreError("SAMPLE_OUTSIDE_FROZEN_WINDOW")
        profile, supervision = profile_for_window_index(
            sample_index, self.sample_indices
        )
        slot = self._dataset.decision_slot(sample_index)
        decision_at = str(slot.get("decision_at", ""))
        visible_1h = self._dataset.bars[sample_index - 95 : sample_index + 1]
        if len(visible_1h) != 96 or visible_1h[-1].get("bar_id") != slot.get(
            "visible_through_bar_id"
        ):
            raise ActionExperimentStoreError("DECISION_VISIBLE_WINDOW_INVALID")
        visible_4h = tuple(
            item
            for item in self._dataset.derived_4h
            if str(item.get("available_at", "")) <= decision_at
        )
        visible_1d = tuple(
            item
            for item in self._dataset.derived_1d
            if str(item.get("available_at", "")) <= decision_at
        )
        return build_decision_context(
            sample_index=sample_index,
            profile=profile,
            supervision=supervision,
            decision_slot=slot,
            visible_1h=visible_1h,
            visible_4h=visible_4h,
            visible_1d=visible_1d,
            source_bindings=self.source_bindings,
            financial_contract_version=self.financial_contract_version,
        )



class FrozenOutcomeDatasetAdapter:
    """Outcome reader admitted only by a verified terminal event chain."""

    def __init__(self, source_run_root: Path, completed_run_root: Path) -> None:
        status = verify_action_experiment(Path(completed_run_root))
        manifest = _manifest(Path(completed_run_root).resolve())
        sample_indices = _manifest_sample_indices(manifest)
        if (
            status.get("integrity") != "PASS"
            or status.get("completed_count") != len(sample_indices)
            or status.get("role_output_count")
            != len(sample_indices) * len(EXPECTED_ROLE_KEYS)
            or status.get("terminal") is not True
        ):
            raise ActionExperimentStoreError(
                "OUTCOME_ACCESS_BEFORE_TERMINAL_CHAIN"
            )
        decision_adapter = FrozenActionDatasetAdapter(
            source_run_root,
            sample_indices=sample_indices,
            financial_contract_version=_financial_contract(manifest),
        )
        receipt = _source_receipt(
            Path(completed_run_root).resolve(), manifest
        )
        expected_bindings = {
            key: receipt.get(key)
            for key in (
                "source_run_id",
                "source_run_bindings_digest",
                "dataset_manifest_digest",
                "dataset_payload_digest",
            )
        }
        if (
            decision_adapter.source_bindings != expected_bindings
            or receipt.get("source_run_root")
            != str(Path(source_run_root).resolve())
        ):
            raise ActionExperimentStoreError(
                "OUTCOME_SOURCE_BINDING_MISMATCH"
            )
        self._dataset = decision_adapter._dataset
        self.sample_indices = sample_indices

    def outcome_bars(
        self, sample_index: int
    ) -> tuple[Mapping[str, Any], ...]:
        if sample_index not in self.sample_indices:
            raise ActionExperimentStoreError("SAMPLE_OUTSIDE_FROZEN_WINDOW")
        rows = self._dataset.bars[sample_index + 1 : sample_index + 25]
        if len(rows) != 24:
            raise ActionExperimentStoreError("OUTCOME_WINDOW_INCOMPLETE")
        return rows


def _load_config(path: Path) -> dict[str, Any]:
    value = load_json_strict(path)
    verify_self_digest(value, "config_digest")
    schema_version = value.get("schema_version")
    sample_indices = _sample_indices_from_range(
        value.get("decision_indices_inclusive")
    )
    contract = _financial_contract(value)
    version_binding_valid = (
        schema_version in {"1.0.0", "1.1.0"}
        and sample_indices == SAMPLE_INDICES
        and contract == E0A_FINANCIAL_CONTRACT
    ) or (
        schema_version == "2.0.0"
        and sample_indices == E0B_SAMPLE_INDICES
        and contract == E0B_FINANCIAL_CONTRACT
    )
    if (
        value.get("schema_id") != "action_discrimination_experiment_config"
        or not version_binding_valid
        or value.get("sample_count") != 32
        or value.get("system_mode") != SYSTEM_MODE
        or value.get("external_execution_authority") != EXECUTION_AUTHORITY
        or value.get("executable") is not False
    ):
        raise ActionExperimentStoreError("ACTION_CONFIG_INVALID")
    if schema_version == "2.0.0":
        _validate_e0b_policy_bindings(value)
    return value


def _validate_e0b_policy_bindings(value: Mapping[str, Any]) -> None:
    """Fail closed when the frozen E0B policy drifts from implemented constants."""

    expected = {
        "evidence_class": EVIDENCE_CLASS,
        "action_ids": [
            "WAIT_WITH_REVIEW",
            "HOLD_CORE",
            "HOLD_CORE_TRAIL",
            "OPEN_CORE",
            "ADD_CONFIRMATION",
            "ADD_TREND",
            "REDUCE_TACTICAL",
            "PARTIAL_TAKE_PROFIT",
            "EXIT_WITH_REENTRY",
            "REENTER_CORE",
            "INVALIDATE_AND_EXIT",
        ],
        "account_policy": {
            "adverse_slippage_rate": "0.0002",
            "core_fraction": "0.0625",
            "funding_status": "UNKNOWN_EXCLUDED",
            "initial_equity": "10000",
            "maximum_gross_fraction": "0.125",
            "maximum_stop_risk_fraction": "0.0125",
            "minimum_net_reward_risk": "1.5",
            "stage_fraction": "0.03125",
            "tail_gap_fraction": "0.01",
            "taker_fee_rate": "0.0005",
        },
        "geometry_policy": {
            "normal_target_r_multiple": "2.00",
            "stop_atr_multiple": "1.50",
            "stop_floor_fraction_of_mark": "0.90",
            "stop_low24_atr_offset": "0.25",
            "trend_target_r_multiple": "3.50",
        },
        "action_transition_policy": {
            "failure_terminal_policy": (
                "EACH_POST_ACTION_LOT_AT_REGISTERED_STOP"
            ),
            "partial_close_fraction_each_existing_lot": "0.5",
            "reentry_is_separate_future_obligation": True,
            "review_obligation_policy": (
                "WAIT_OR_EXIT_CREATES_NEXT_CLOSED_1H_REVIEW_OBLIGATION"
            ),
            "same_bar_new_trail_stop_execution": False,
            "stop_fill_policy": (
                "MIN_REGISTERED_STOP_AND_BAR_OPEN_PLUS_FROZEN_EXIT_COST"
            ),
            "trailing_policy": (
                "OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR"
            ),
        },
        "outcome_policy": {
            "economic_metrics_are_descriptive": True,
            "horizons_hours": [1, 4, 8, 24],
            "maximum_drawdown_guardrail_delta_fraction": "0.0025",
            "drawdown_method": (
                "CONSERVATIVE_OHLC_GAP_AT_OPEN_THEN_HIGH_BEFORE_INTRABAR_LOW"
            ),
            "net_vector_dominance_required": True,
            "one_hour_cannot_independently_promote": True,
            "opportunity_loss_is_algebraic_mirror_not_independent_gate": True,
            "opportunity_loss_is_actual_loss": False,
            "outcome_authorization": (
                "EVALUATE_AFTER_ALL_ROLE_OUTPUTS_FROZEN"
            ),
            "overlapping_windows_no_iid_claim": True,
            "review_dependent_actions_after_one_hour_are_not_contract_comparable": True,
        },
        "quality_policy": {
            "action_benefit_from_language_checklist": False,
            "challenge_coverage_status": "DIAGNOSTIC_ONLY",
            "dedicated_review_roles": ["SELF_REVIEW", "CHALLENGE_BLIND"],
            "proposal_material_challenge_required": False,
            "topology_symmetric": True,
        },
        "profile_order": [
            "FLAT_ACTIVE",
            "CORE_ACTIVE",
            "CORE_CONFIRMATION_ELIGIBLE",
            "CORE_PLUS_TACTICAL",
            "TARGET_REVIEW_ACTIVE",
            "REENTRY_PENDING",
            "RISK_BUDGET_PRESSURE",
            "HARD_INVALIDATED_CONTROL",
        ],
        "supervision_order": [
            "ATTENDED",
            "UNATTENDED_PROTECTED",
            "UNATTENDED_NO_NEW_RISK",
            "ATTENDED",
        ],
        "terminal_verdict_order": [
            "INCOMPLETE_NO_DECISION",
            "NO_ACTION_DISCRIMINATION",
            "INCONCLUSIVE_SEQUENTIAL_CONTRACT_NOT_PROVEN",
            "INCONCLUSIVE_ACTION_TRADEOFF",
            "DESCRIPTIVE_CLUSTER_SELECTION_ADVANTAGE",
            "DESCRIPTIVE_SINGLE_SELECTION_ADVANTAGE",
        ],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ActionExperimentStoreError("E0B_POLICY_IMPLEMENTATION_BINDING_INVALID")
    autonomy = value.get("agent_autonomy")
    role = value.get("role_contract")
    if (
        not isinstance(autonomy, Mapping)
        or autonomy.get("selector_policy_id")
        != "BOUNDED_SELECTOR_POLICY_E0B_V2"
        or autonomy.get("agent_owned")
        != [
            "PATH_INTERPRETATION",
            "ORDINAL_TRADEOFF",
            "BOUNDED_SELECTION",
        ]
        or autonomy.get("kernel_owned")
        != [
            "PIT",
            "STATE",
            "RISK",
            "SUPERVISION",
            "PERMISSION",
            "ACTION_TRANSITION",
            "OUTCOME_ACCOUNTING",
        ]
        or not isinstance(role, Mapping)
        or role.get("arm_ids")
        != ["SINGLE_STRONG", "BLIND_THREE_ROLE_CLUSTER"]
        or role.get("transport")
        != "CODEX_NATIVE_SUBAGENT_COLLABORATION"
        or role.get("delivery_protocol")
        != "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1"
        or role.get("clean_fork_turns") != "none"
        or role.get("invocation_receipt_required") is not True
        or role.get("expected_outputs_per_sample") != len(EXPECTED_ROLE_KEYS)
        or role.get("role_keys") != list(EXPECTED_ROLE_KEYS)
        or role.get("model_identity_attestation")
        != "UNAVAILABLE_PRACTICAL_EVIDENCE"
        or role.get("token_budget_attestation")
        != "UNAVAILABLE_PRACTICAL_EVIDENCE"
        or not isinstance(role.get("transport_preflight"), Mapping)
        or role["transport_preflight"].get("result")
        != "PASS_DIRECT_INLINE_NO_TRUNCATION"
        or role["transport_preflight"].get("used_as_formal_role_output")
        is not False
    ):
        raise ActionExperimentStoreError("E0B_ROLE_POLICY_BINDING_INVALID")


_E0B_TRANSPORT_PREFLIGHT_KEYS = frozenset(
    {
        "formal_role_output",
        "child_task",
        "context_digest",
        "packet_byte_length",
        "packet_digest",
        "packet_physical_sha256",
        "received_complete",
        "result",
        "sample_index",
        "selector_choice_set_count",
        "tool_use_status",
        "used_as_formal_role_output",
    }
)


def _validate_e0b_transport_preflight(
    *,
    config: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    """Bind a nonformal clean-child preflight to the current packet bytes."""

    role_contract = config.get("role_contract")
    preflight = (
        role_contract.get("transport_preflight")
        if isinstance(role_contract, Mapping)
        else None
    )
    if (
        not isinstance(preflight, Mapping)
        or frozenset(preflight) != _E0B_TRANSPORT_PREFLIGHT_KEYS
        or preflight.get("formal_role_output") is not False
        or not isinstance(preflight.get("child_task"), str)
        or not str(preflight["child_task"]).strip()
        or preflight.get("received_complete") is not True
        or preflight.get("result") != "PASS_DIRECT_INLINE_NO_TRUNCATION"
        or preflight.get("tool_use_status") != "NO_TOOL_CALL_OBSERVED"
        or preflight.get("used_as_formal_role_output") is not False
    ):
        raise ActionExperimentStoreError("E0B_TRANSPORT_PREFLIGHT_INVALID")

    # Local import avoids an application/store import cycle at module load.
    # The builder consumes one PIT-frozen context and has no outcome access.
    from ..application.action_discrimination_experiment import (
        build_role_packet_from_context,
    )

    packet = build_role_packet_from_context(
        context=context,
        role="cluster-proposal",
    )
    raw_packet = canonical_bytes(packet)
    expected = {
        "sample_index": context.get("sample_index"),
        "context_digest": context.get("context_digest"),
        "packet_digest": packet.get("packet_digest"),
        "packet_byte_length": len(raw_packet),
        "packet_physical_sha256": hashlib.sha256(raw_packet).hexdigest(),
        "selector_choice_set_count": len(
            context.get("candidate_calculations", {}).get(
                "selector_choice_set", []
            )
        ),
    }
    if any(
        preflight.get(key) != expected_value
        for key, expected_value in expected.items()
    ):
        raise ActionExperimentStoreError(
            "E0B_TRANSPORT_PREFLIGHT_PACKET_BINDING_INVALID"
        )


def prepare_action_experiment(
    *,
    runtime_root: Path,
    run_id: str,
    source_run_root: Path,
    config_path: Path,
    design_path: Path,
    frozen_at: str,
) -> Path:
    """Freeze all contexts and bindings before any Agent role output exists."""

    run_id = _safe_id(run_id, "ACTION_RUN_ID_INVALID")
    if not isinstance(frozen_at, str) or not frozen_at.endswith("Z"):
        raise ActionExperimentStoreError("FROZEN_AT_INVALID")
    try:
        datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ActionExperimentStoreError("FROZEN_AT_INVALID") from exc
    run_root = Path(runtime_root).resolve() / run_id
    if any(part.casefold() in _MUTABLE_NAMES for part in run_root.parts):
        raise ActionExperimentStoreError("MUTABLE_RUN_PATH_FORBIDDEN")
    config = _load_config(Path(config_path))
    sample_indices = _sample_indices_from_range(
        config["decision_indices_inclusive"]
    )
    financial_contract_version = _financial_contract(config)
    role_contract = config.get("role_contract")
    if not isinstance(role_contract, Mapping):
        raise ActionExperimentStoreError("ROLE_CONTRACT_INVALID")
    adapter = FrozenActionDatasetAdapter(
        Path(source_run_root),
        sample_indices=sample_indices,
        financial_contract_version=financial_contract_version,
    )
    design_path = Path(design_path).resolve()
    if not design_path.is_file():
        raise ActionExperimentStoreError("DESIGN_DOCUMENT_MISSING")
    outputs_root = run_root / "outputs"
    if outputs_root.exists() and any(outputs_root.rglob("*.json")):
        raise ActionExperimentStoreError("OUTPUT_EXISTS_BEFORE_PREPARE")

    frozen_root = run_root / "frozen"
    contexts_root = frozen_root / "contexts"
    context_rows: list[dict[str, Any]] = []
    profile_counts: Counter[str] = Counter()
    supervision_counts: Counter[str] = Counter()
    registered_actions: set[str] = set()
    choice_actions: set[str] = set()
    singleton_rows: list[dict[str, Any]] = []
    for sample_index in sample_indices:
        context = adapter.decision_context(sample_index)
        if (
            financial_contract_version == E0B_FINANCIAL_CONTRACT
            and sample_index == sample_indices[0]
        ):
            _validate_e0b_transport_preflight(
                config=config,
                context=context,
            )
        context_path = contexts_root / f"sample-{sample_index:03d}.json"
        write_once_json(context_path, context)
        profile_id = str(context["state"]["profile_id"])
        supervision = str(context["state"]["supervision_mode"])
        profile_counts[profile_id] += 1
        supervision_counts[supervision] += 1
        candidate_rows = context["candidate_calculations"]["candidate_rows"]
        registered_actions.update(str(row["action_id"]) for row in candidate_rows)
        choice = context["candidate_calculations"]["selector_choice_set"]
        choice_actions.update(str(item) for item in choice)
        if len(choice) == 1:
            singleton_rows.append(
                {
                    "sample_index": sample_index,
                    "profile_id": profile_id,
                    "supervision_mode": supervision,
                    "selected_by_kernel": choice[0],
                    "reason": (
                        "HARD_POLICY_SINGLETON"
                        if profile_id == "HARD_INVALIDATED_CONTROL"
                        else "SUPERVISION_SINGLETON"
                    ),
                }
            )
        context_rows.append(
            {
                "sample_index": sample_index,
                "profile_id": profile_id,
                "supervision_mode": supervision,
                "context_digest": context["context_digest"],
                "state_digest": context["state"]["state_digest"],
                "calculation_digest": context["candidate_calculations"][
                    "calculation_digest"
                ],
                "matrix_digest": context["path_payoff_matrix"]["matrix_digest"],
                "physical_sha256": _physical_digest(context_path),
                "selector_choice_set": choice,
            }
        )
    if sorted(profile_counts.values()) != [4] * 8:
        raise ActionExperimentStoreError("PROFILE_COVERAGE_INVALID")
    if len(registered_actions) != 11 or len(choice_actions) != 11:
        raise ActionExperimentStoreError("ACTION_COVERAGE_INVALID")

    write_once_json(frozen_root / "semantic-output.schema.json", SEMANTIC_OUTPUT_SCHEMA)
    write_once_json(frozen_root / "config.json", config)
    source_receipt = self_digest(
        {
            "schema_id": "action_experiment_source_receipt",
            "schema_version": (
                "2.0.0"
                if financial_contract_version == E0B_FINANCIAL_CONTRACT
                else "1.0.0"
            ),
            **adapter.source_bindings,
            "source_run_root": str(Path(source_run_root).resolve()),
            "config_source_path": str(Path(config_path).resolve()),
            "config_digest": config["config_digest"],
            "financial_contract_version": financial_contract_version,
            "design_source_path": str(design_path),
            "design_physical_sha256": _physical_digest(design_path),
            "outcome_access_during_prepare": False,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "receipt_digest",
    )
    write_once_json(frozen_root / "source-receipt.json", source_receipt)
    manifest = self_digest(
        {
            "schema_id": "action_discrimination_manifest",
            "schema_version": (
                "2.0.0"
                if financial_contract_version == E0B_FINANCIAL_CONTRACT
                else "1.0.0"
            ),
            "run_id": run_id,
            "frozen_at": frozen_at,
            "frozen_before_first_role_output": True,
            "evidence_class": EVIDENCE_CLASS,
            "decision_indices_inclusive": [
                sample_indices[0],
                sample_indices[-1],
            ],
            "sample_count": len(sample_indices),
            "expected_role_outputs_per_sample": 6,
            "expected_role_output_count": 192,
            "profile_counts": dict(sorted(profile_counts.items())),
            "supervision_counts": dict(sorted(supervision_counts.items())),
            "registered_action_ids": sorted(registered_actions),
            "choice_set_action_ids": sorted(choice_actions),
            "deterministic_singletons": singleton_rows,
            "context_rows": context_rows,
            "source_receipt_digest": source_receipt["receipt_digest"],
            "config_digest": config["config_digest"],
            "financial_contract_version": financial_contract_version,
            "semantic_schema_digest": canonical_digest(SEMANTIC_OUTPUT_SCHEMA),
            "role_transport": {
                "kind": role_contract.get("transport"),
                "delivery_protocol": role_contract.get(
                    "delivery_protocol", "LEGACY_UNSPECIFIED"
                ),
                "clean_fork_turns": role_contract.get(
                    "clean_fork_turns", "UNSPECIFIED"
                ),
                "invocation_receipt_required": role_contract.get(
                    "invocation_receipt_required", False
                ),
                "transport_preflight": role_contract.get(
                    "transport_preflight"
                ),
                "served_model_attestation": "UNAVAILABLE",
                "exact_token_budget_attestation": "UNAVAILABLE",
                "workspace_tool_use_attestation": "CONTROLLER_OBSERVED_ONLY",
                "strict_transport_evidence": False,
            },
            "outcome_reader_authorization": (
                "EVALUATE_AFTER_ALL_ROLE_OUTPUTS_FROZEN"
            ),
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "manifest_digest",
    )
    write_once_json(frozen_root / "manifest.json", manifest)
    checkpoint = self_digest(
        {
            "schema_id": "action_experiment_checkpoint",
            "schema_version": (
                "2.0.0"
                if financial_contract_version == E0B_FINANCIAL_CONTRACT
                else "1.0.0"
            ),
            "run_id": run_id,
            "manifest_digest": manifest["manifest_digest"],
            "completed_count": 0,
            "next_sample_index": sample_indices[0],
            "role_output_count": 0,
            "event_head_digest": INITIAL_EVENT_HEAD,
            "terminal": False,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "checkpoint_digest",
    )
    _atomic_checkpoint(run_root / "checkpoint.json", checkpoint)
    return run_root


def _manifest(run_root: Path) -> dict[str, Any]:
    value = load_json_strict(run_root / "frozen" / "manifest.json")
    verify_self_digest(value, "manifest_digest")
    return value


def _source_receipt(run_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = load_json_strict(run_root / "frozen" / "source-receipt.json")
    digest = verify_self_digest(value, "receipt_digest")
    if digest != manifest.get("source_receipt_digest"):
        raise ActionExperimentStoreError("SOURCE_RECEIPT_MANIFEST_BINDING_INVALID")
    return value


def _context(
    run_root: Path,
    sample_index: int,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bound_manifest = dict(manifest) if manifest is not None else _manifest(run_root)
    sample_indices = _manifest_sample_indices(bound_manifest)
    if sample_index not in sample_indices:
        raise ActionExperimentStoreError("SAMPLE_OUTSIDE_FROZEN_WINDOW")
    rows = [
        row
        for row in bound_manifest.get("context_rows", [])
        if isinstance(row, Mapping) and row.get("sample_index") == sample_index
    ]
    if len(rows) != 1:
        raise ActionExperimentStoreError("MANIFEST_CONTEXT_ROW_INVALID")
    manifest_row = rows[0]
    context_path = (
        run_root
        / "frozen"
        / "contexts"
        / f"sample-{sample_index:03d}.json"
    )
    value = load_json_strict(
        context_path
    )
    context_digest = _verify_context_self_digest(value)
    if (
        value.get("sample_index") != sample_index
        or manifest_row.get("context_digest") != context_digest
        or manifest_row.get("state_digest")
        != value.get("state", {}).get("state_digest")
        or manifest_row.get("calculation_digest")
        != value.get("candidate_calculations", {}).get("calculation_digest")
        or manifest_row.get("matrix_digest")
        != value.get("path_payoff_matrix", {}).get("matrix_digest")
        or manifest_row.get("physical_sha256") != _physical_digest(context_path)
    ):
        raise ActionExperimentStoreError("CONTEXT_MANIFEST_BINDING_INVALID")
    return value


def load_frozen_action_context(
    run_root: Path, sample_index: int
) -> dict[str, Any]:
    """Load one context only after verifying every frozen manifest binding."""

    resolved = Path(run_root).resolve()
    return _context(resolved, sample_index, _manifest(resolved))


def _checkpoint_value(run_root: Path) -> dict[str, Any]:
    value = load_json_strict(run_root / "checkpoint.json")
    verify_self_digest(value, "checkpoint_digest")
    return value


_INVOCATION_RECEIPT_KEYS = frozenset(
    {
        "role_key",
        "agent_task_id",
        "delivery_protocol",
        "fork_turns",
        "packet_digest",
        "packet_byte_length",
        "context_digest",
        "tool_use_status",
        "external_data_status",
        "served_model_attestation",
        "token_budget_attestation",
        "formal_role_call",
        "response_json_only",
    }
)


def _validate_invocation_receipt(
    *,
    role_key: str,
    receipt: Mapping[str, Any],
    context_digest: str,
) -> None:
    if not isinstance(receipt, Mapping) or frozenset(receipt) != _INVOCATION_RECEIPT_KEYS:
        raise ActionExperimentStoreError("INVOCATION_RECEIPT_SHAPE_INVALID")
    if (
        receipt.get("role_key") != role_key
        or not isinstance(receipt.get("agent_task_id"), str)
        or not str(receipt["agent_task_id"]).strip()
        or receipt.get("delivery_protocol")
        != "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1"
        or receipt.get("fork_turns") != "none"
        or not isinstance(receipt.get("packet_digest"), str)
        or _DIGEST.fullmatch(str(receipt["packet_digest"])) is None
        or type(receipt.get("packet_byte_length")) is not int
        or int(receipt["packet_byte_length"]) <= 0
        or receipt.get("context_digest") != context_digest
        or receipt.get("tool_use_status") != "NO_TOOL_CALL_OBSERVED"
        or receipt.get("external_data_status")
        != "NO_EXTERNAL_DATA_OBSERVED"
        or receipt.get("served_model_attestation") != "UNATTESTED"
        or receipt.get("token_budget_attestation") != "UNATTESTED"
        or receipt.get("formal_role_call") is not True
        or receipt.get("response_json_only") is not True
    ):
        raise ActionExperimentStoreError("INVOCATION_RECEIPT_INVALID")


def _historical_agent_task_ids(
    *,
    run_root: Path,
    sample_index: int,
) -> set[str]:
    """Return event-bound task IDs and reject any prior cross-sample reuse."""

    manifest = _manifest(run_root)
    preflight_task = (
        manifest.get("role_transport", {})
        .get("transport_preflight", {})
        .get("child_task")
    )
    if not isinstance(preflight_task, str) or not preflight_task.strip():
        raise ActionExperimentStoreError(
            "TRANSPORT_PREFLIGHT_TASK_BINDING_INVALID"
        )
    task_owner: dict[str, int] = {preflight_task: -1}
    for prior_index in _manifest_sample_indices(manifest):
        if prior_index >= sample_index:
            break
        event_path = run_root / "events" / f"sample-{prior_index:03d}.json"
        if not event_path.exists():
            raise ActionExperimentStoreError(
                "HISTORICAL_EVENT_MISSING_BEFORE_NEXT_SAMPLE"
            )
        event = load_json_strict(event_path)
        verify_self_digest(event, "event_digest")
        if (
            event.get("sample_index") != prior_index
            or event.get("manifest_digest") != manifest.get("manifest_digest")
        ):
            raise ActionExperimentStoreError(
                "HISTORICAL_EVENT_BINDING_INVALID"
            )
        sample_task_ids: set[str] = set()
        for role_key in EXPECTED_ROLE_KEYS:
            output = load_json_strict(
                run_root
                / "outputs"
                / f"sample-{prior_index:03d}"
                / f"{role_key}.json"
            )
            output_digest = verify_self_digest(output, "output_digest")
            if output_digest != event.get("output_digests", {}).get(role_key):
                raise ActionExperimentStoreError(
                    "HISTORICAL_EVENT_OUTPUT_BINDING_INVALID"
                )
            receipt = output.get("invocation_receipt")
            task_id = (
                receipt.get("agent_task_id")
                if isinstance(receipt, Mapping)
                else None
            )
            if not isinstance(task_id, str) or not task_id.strip():
                raise ActionExperimentStoreError(
                    "HISTORICAL_INVOCATION_RECEIPT_INVALID"
                )
            sample_task_ids.add(task_id)
        for task_id in sample_task_ids:
            if task_id in task_owner:
                raise ActionExperimentStoreError(
                    "INVOCATION_RECEIPT_TASK_REUSED_ACROSS_SAMPLES"
                )
            task_owner[task_id] = prior_index
    return set(task_owner)


def _validate_invocation_receipt_bundle(
    *,
    run_root: Path,
    sample_index: int,
    context: Mapping[str, Any],
    semantic_outputs: Mapping[str, Mapping[str, Any]],
    receipts: Mapping[str, Mapping[str, Any]],
) -> None:
    for role_key in EXPECTED_ROLE_KEYS:
        _validate_invocation_receipt(
            role_key=role_key,
            receipt=receipts[role_key],
            context_digest=str(context["context_digest"]),
        )
    if context.get("financial_contract_version") != E0B_FINANCIAL_CONTRACT:
        return

    # Local import avoids making the application/store dependency cyclic at
    # module import time.  E0B binds receipts to the exact packet the kernel
    # can independently reconstruct from frozen context and upstream outputs.
    from ..application.action_discrimination_experiment import role_packet

    single_packet = role_packet(
        run_root=run_root,
        sample_index=sample_index,
        role="single-strong-bundle",
    )
    proposal_packet = role_packet(
        run_root=run_root,
        sample_index=sample_index,
        role="cluster-proposal",
    )
    challenge_packet = role_packet(
        run_root=run_root,
        sample_index=sample_index,
        role="cluster-challenge",
    )
    selector_packet = role_packet(
        run_root=run_root,
        sample_index=sample_index,
        role="cluster-selection",
        proposal=semantic_outputs["cluster-proposal"],
        challenge=semantic_outputs["cluster-challenge"],
    )
    expected_packets = {
        "single-proposal": single_packet,
        "single-self-review": single_packet,
        "single-selection": single_packet,
        "cluster-proposal": proposal_packet,
        "cluster-challenge": challenge_packet,
        "cluster-selection": selector_packet,
    }
    for role_key, packet in expected_packets.items():
        receipt = receipts[role_key]
        if (
            receipt.get("packet_digest") != packet.get("packet_digest")
            or receipt.get("packet_byte_length")
            != len(canonical_bytes(packet))
        ):
            raise ActionExperimentStoreError(
                "INVOCATION_RECEIPT_PACKET_BINDING_INVALID"
            )
    single_tasks = {
        str(receipts[key]["agent_task_id"])
        for key in (
            "single-proposal",
            "single-self-review",
            "single-selection",
        )
    }
    cluster_tasks = [
        str(receipts[key]["agent_task_id"])
        for key in (
            "cluster-proposal",
            "cluster-challenge",
            "cluster-selection",
        )
    ]
    if (
        len(single_tasks) != 1
        or len(set(cluster_tasks)) != 3
        or next(iter(single_tasks)) in set(cluster_tasks)
    ):
        raise ActionExperimentStoreError(
            "INVOCATION_RECEIPT_ROLE_ISOLATION_INVALID"
        )
    current_task_ids = single_tasks | set(cluster_tasks)
    if current_task_ids & _historical_agent_task_ids(
        run_root=run_root,
        sample_index=sample_index,
    ):
        raise ActionExperimentStoreError(
            "INVOCATION_RECEIPT_TASK_REUSED_ACROSS_SAMPLES"
        )


def record_action_case(
    *,
    run_root: Path,
    sample_index: int,
    semantic_outputs: Mapping[str, Mapping[str, Any]],
    invocation_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate all six outputs, then append one immutable case event."""

    run_root = Path(run_root).resolve()
    manifest = _manifest(run_root)
    sample_indices = _manifest_sample_indices(manifest)
    financial_contract_version = _financial_contract(manifest)
    checkpoint = _checkpoint_value(run_root)
    if checkpoint.get("terminal") is not False:
        raise ActionExperimentStoreError("RUN_ALREADY_TERMINAL")
    if sample_index != checkpoint.get("next_sample_index"):
        raise ActionExperimentStoreError("SAMPLE_NOT_NEXT")
    if frozenset(semantic_outputs) != frozenset(EXPECTED_ROLE_KEYS):
        raise ActionExperimentStoreError("ROLE_OUTPUT_KEYS_INVALID")
    context = _context(run_root, sample_index, manifest)
    direct_transport = (
        manifest.get("role_transport", {}).get("delivery_protocol")
        == "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1"
    )
    receipts = invocation_receipts or {}
    if direct_transport:
        if frozenset(receipts) != frozenset(EXPECTED_ROLE_KEYS):
            raise ActionExperimentStoreError(
                "DIRECT_INLINE_INVOCATION_RECEIPTS_REQUIRED"
            )
        _validate_invocation_receipt_bundle(
            run_root=run_root,
            sample_index=sample_index,
            context=context,
            semantic_outputs=semantic_outputs,
            receipts=receipts,
        )
    validations = {
        role_key: validate_semantic_output(
            role_key=role_key,
            output=semantic_outputs[role_key],
            context=context,
        )
        for role_key in EXPECTED_ROLE_KEYS
    }
    single_score = arm_preoutcome_score(
        arm="SINGLE_STRONG",
        validations=tuple(
            validations[key]
            for key in (
                "single-proposal",
                "single-self-review",
                "single-selection",
            )
        ),
    )
    cluster_score = arm_preoutcome_score(
        arm="BLIND_THREE_ROLE_CLUSTER",
        validations=tuple(
            validations[key]
            for key in (
                "cluster-proposal",
                "cluster-challenge",
                "cluster-selection",
            )
        ),
    )
    output_digests: dict[str, str] = {}
    for role_key in EXPECTED_ROLE_KEYS:
        receipt = receipts.get(role_key, {})
        envelope = self_digest(
            {
                "schema_id": "action_role_output",
                "schema_version": "1.0.0",
                "sample_index": sample_index,
                "role_key": role_key,
                "context_digest": context["context_digest"],
                "semantic_output": dict(semantic_outputs[role_key]),
                "semantic_digest": validations[role_key].semantic_digest,
                "validation": validations[role_key].document(),
                "invocation_receipt": dict(receipt),
                "system_mode": SYSTEM_MODE,
                "external_execution_authority": EXECUTION_AUTHORITY,
                "executable": False,
            },
            "output_digest",
        )
        output_path = (
            run_root
            / "outputs"
            / f"sample-{sample_index:03d}"
            / f"{role_key}.json"
        )
        write_once_json(output_path, envelope)
        output_digests[role_key] = str(envelope["output_digest"])
    event = self_digest(
        {
            "schema_id": "action_case_event",
            "schema_version": (
                "2.0.0"
                if financial_contract_version == E0B_FINANCIAL_CONTRACT
                else "1.0.0"
            ),
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "sample_index": sample_index,
            "previous_event_digest": checkpoint["event_head_digest"],
            "context_digest": context["context_digest"],
            "output_digests": output_digests,
            "single_arm_score": single_score,
            "cluster_arm_score": cluster_score,
            "selected_actions": {
                "single": single_score["selected_action"],
                "cluster": cluster_score["selected_action"],
            },
            "future_outcome_used": False,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "event_digest",
    )
    write_once_json(
        run_root / "events" / f"sample-{sample_index:03d}.json", event
    )
    completed = int(checkpoint["completed_count"]) + 1
    current_offset = sample_indices.index(sample_index)
    next_index = (
        sample_indices[current_offset + 1]
        if current_offset + 1 < len(sample_indices)
        else None
    )
    next_checkpoint = self_digest(
        {
            "schema_id": "action_experiment_checkpoint",
            "schema_version": (
                "2.0.0"
                if financial_contract_version == E0B_FINANCIAL_CONTRACT
                else "1.0.0"
            ),
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "completed_count": completed,
            "next_sample_index": next_index,
            "role_output_count": completed * len(EXPECTED_ROLE_KEYS),
            "event_head_digest": event["event_digest"],
            "terminal": completed == len(sample_indices),
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "checkpoint_digest",
    )
    _atomic_checkpoint(run_root / "checkpoint.json", next_checkpoint)
    return event


def verify_action_experiment(run_root: Path) -> dict[str, Any]:
    """Recompute the immutable event chain and compare the mutable checkpoint."""

    run_root = Path(run_root).resolve()
    manifest = _manifest(run_root)
    sample_indices = _manifest_sample_indices(manifest)
    previous = INITIAL_EVENT_HEAD
    completed = 0
    for sample_index in sample_indices:
        event_path = run_root / "events" / f"sample-{sample_index:03d}.json"
        if not event_path.exists():
            break
        event = load_json_strict(event_path)
        verify_self_digest(event, "event_digest")
        if (
            event.get("sample_index") != sample_index
            or event.get("previous_event_digest") != previous
            or event.get("manifest_digest") != manifest["manifest_digest"]
            or event.get("future_outcome_used") is not False
        ):
            raise ActionExperimentStoreError("EVENT_CHAIN_INVALID")
        context = _context(run_root, sample_index, manifest)
        if event.get("context_digest") != context["context_digest"]:
            raise ActionExperimentStoreError("EVENT_CONTEXT_BINDING_INVALID")
        verified_semantic_outputs: dict[str, Mapping[str, Any]] = {}
        verified_receipts: dict[str, Mapping[str, Any]] = {}
        for role_key in EXPECTED_ROLE_KEYS:
            output_path = (
                run_root
                / "outputs"
                / f"sample-{sample_index:03d}"
                / f"{role_key}.json"
            )
            output = load_json_strict(output_path)
            output_digest = verify_self_digest(output, "output_digest")
            if output_digest != event["output_digests"].get(role_key):
                raise ActionExperimentStoreError("EVENT_OUTPUT_BINDING_INVALID")
            validate_semantic_output(
                role_key=role_key,
                output=output["semantic_output"],
                context=context,
            )
            verified_semantic_outputs[role_key] = output["semantic_output"]
            verified_receipts[role_key] = output.get("invocation_receipt", {})
        if (
            manifest.get("role_transport", {}).get("delivery_protocol")
            == "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1"
        ):
            _validate_invocation_receipt_bundle(
                run_root=run_root,
                sample_index=sample_index,
                context=context,
                semantic_outputs=verified_semantic_outputs,
                receipts=verified_receipts,
            )
        previous = str(event["event_digest"])
        completed += 1
    checkpoint = _checkpoint_value(run_root)
    expected_next = (
        sample_indices[completed] if completed < len(sample_indices) else None
    )
    if (
        checkpoint.get("manifest_digest") != manifest["manifest_digest"]
        or checkpoint.get("completed_count") != completed
        or checkpoint.get("next_sample_index") != expected_next
        or checkpoint.get("role_output_count") != completed * len(EXPECTED_ROLE_KEYS)
        or checkpoint.get("event_head_digest") != previous
        or checkpoint.get("terminal") is not (completed == len(sample_indices))
    ):
        raise ActionExperimentStoreError("CHECKPOINT_DOES_NOT_MATCH_EVENT_CHAIN")
    return {
        "run_id": manifest["run_id"],
        "manifest_digest": manifest["manifest_digest"],
        "completed_count": completed,
        "next_sample_index": expected_next,
        "role_output_count": completed * len(EXPECTED_ROLE_KEYS),
        "event_head_digest": previous,
        "terminal": completed == len(sample_indices),
        "integrity": "PASS",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }


def utc_now_z() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = [
    "ActionExperimentStoreError",
    "EXPECTED_ROLE_KEYS",
    "FrozenActionDatasetAdapter",
    "FrozenOutcomeDatasetAdapter",
    "load_frozen_action_context",
    "prepare_action_experiment",
    "record_action_case",
    "utc_now_z",
    "verify_action_experiment",
]
